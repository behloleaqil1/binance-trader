"""Backtester tests: fills, SL/TP mechanics, fees, and metric sanity."""
import pytest

from app.backtest.metrics import compute_metrics, downsample_curve
from app.backtest.simulator import (SimConfig, run_candle_backtest,
                                    run_dca_backtest, run_grid_backtest)
from app.core.types import Signal, SignalAction
from app.risk.models import RiskConfig
from app.strategies.base import ParamSpec, Strategy
from app.strategies.dca import DCAStrategy
from app.strategies.grid import GridStrategy
from app.strategies.trend_momentum import TrendMomentumStrategy
from tests.conftest import make_df


class BuyAtIndex(Strategy):
    """Test stub: BUY once at a fixed row, never SELL — isolates SL/TP mechanics."""
    id = "stub"
    name = "Stub"
    description = "test"
    kind = "candle"

    @classmethod
    def param_specs(cls):
        return [ParamSpec("buy_at", "buy index", "int", 5)]

    def required_history(self):
        return 2

    def decide(self, symbol, df, i, position):
        if position is None and i == self.params["buy_at"]:
            return Signal(SignalAction.BUY, symbol, self.id, "stub entry")
        return self.hold(symbol, "stub hold")


def flat_df(n=30, price=100.0, **overrides):
    closes = [price] * n
    df = make_df(closes, opens=[price] * n, highs=[price] * n, lows=[price] * n)
    for col, changes in overrides.items():
        for idx, val in changes.items():
            df.loc[idx, col] = val
    return df


RISK = RiskConfig()  # 2% size, SL 2%, TP 4%
CFG = SimConfig(initial_equity=10_000, fee_bps=10, slippage_bps=0)


class TestCandleSim:
    def test_take_profit_fills_at_tp(self):
        # entry executes at open of row 6 (=100); TP=104; row 10 spikes to 105
        df = flat_df(20, high={10: 105.0})
        res = run_candle_backtest(BuyAtIndex({"buy_at": 5}), RISK, df, CFG)
        assert len(res.trades) == 1
        t = res.trades[0]
        assert t["exit_kind"] == "take_profit"
        assert t["exit"] == pytest.approx(104.0)
        assert t["pnl"] > 0

    def test_stop_loss_fills_at_stop(self):
        df = flat_df(20, low={12: 97.0})
        res = run_candle_backtest(BuyAtIndex({"buy_at": 5}), RISK, df, CFG)
        t = res.trades[0]
        assert t["exit_kind"] == "stop_loss"
        assert t["exit"] == pytest.approx(98.0)
        assert t["pnl"] < 0

    def test_pessimistic_stop_first_when_both_hit(self):
        df = flat_df(20, low={12: 97.0}, high={12: 106.0})
        res = run_candle_backtest(BuyAtIndex({"buy_at": 5}), RISK, df, CFG)
        assert res.trades[0]["exit_kind"] == "stop_loss"

    def test_gap_down_fills_at_open_not_stop(self):
        df = flat_df(20, open={12: 95.0}, low={12: 94.5})
        res = run_candle_backtest(BuyAtIndex({"buy_at": 5}), RISK, df, CFG)
        t = res.trades[0]
        assert t["exit_kind"] == "stop_loss"
        assert t["exit"] == pytest.approx(95.0)  # gapped through the stop

    def test_fees_and_slippage_reduce_pnl(self):
        df = flat_df(20, high={10: 105.0})
        gross = run_candle_backtest(BuyAtIndex({"buy_at": 5}), RISK, df,
                                    SimConfig(10_000, fee_bps=0, slippage_bps=0))
        net = run_candle_backtest(BuyAtIndex({"buy_at": 5}), RISK, df,
                                  SimConfig(10_000, fee_bps=10, slippage_bps=5))
        assert net.trades[0]["pnl"] < gross.trades[0]["pnl"]
        assert net.trades[0]["fees"] > 0

    def test_open_position_liquidated_at_end(self):
        df = flat_df(15)  # never hits SL/TP
        res = run_candle_backtest(BuyAtIndex({"buy_at": 5}), RISK, df, CFG)
        assert res.trades[0]["exit_kind"] == "end_of_backtest"
        assert res.equity.iloc[-1] == pytest.approx(10_000, rel=0.01)

    def test_real_strategy_end_to_end(self):
        closes = [100 * (1 - 0.004) ** i for i in range(60)]
        closes += [closes[-1] * (1 + 0.006) ** i for i in range(1, 81)]
        strat = TrendMomentumStrategy({"ema_fast": 5, "ema_slow": 15,
                                       "macd_fast": 6, "macd_slow": 13,
                                       "macd_signal": 5, "rsi_period": 7,
                                       "rsi_buy_min": 0, "rsi_buy_max": 100})
        res = run_candle_backtest(strat, RISK, make_df(closes), CFG)
        assert len(res.trades) >= 1
        assert len(res.equity) > 0
        assert res.equity.iloc[-1] > 9_000  # sane, no blow-up


class TestGridSim:
    def test_oscillation_produces_grid_profits(self):
        cycle = [100, 97, 94, 91, 94, 97, 100, 103, 106, 103]
        closes = cycle * 8
        g = GridStrategy({"lower_price": 88, "upper_price": 112, "levels": 7,
                          "quote_per_level": 50, "stop_outside_range": False})
        res = run_grid_backtest(g, make_df(closes), CFG)
        grid_tp = [t for t in res.trades if t["exit_kind"] == "grid_tp"]
        assert grid_tp, "oscillating price should complete grid round-trips"
        assert all(t["pnl"] != 0 for t in grid_tp)
        assert res.extras["grid_levels"][0] == pytest.approx(88)

    def test_range_break_pauses_grid(self):
        closes = [100, 98, 96, 94, 92, 90, 85, 80, 75, 70, 65, 60]
        g = GridStrategy({"lower_price": 90, "upper_price": 110, "levels": 5,
                          "quote_per_level": 50, "stop_outside_range": True,
                          "flatten_on_stop": True})
        res = run_grid_backtest(g, make_df(closes), CFG)
        assert res.extras["paused_at"] is not None
        assert res.extras["open_lots_at_end"] == 0  # flattened


class TestDCASim:
    def test_daily_buys_accumulate(self):
        n = 40
        closes = [100 + i * 0.5 for i in range(n)]
        d = DCAStrategy({"interval": "daily", "time_utc": "00:00",
                         "quote_amount": 15, "dip_enabled": False})
        res = run_dca_backtest(d, make_df(closes, step_ms=86_400_000), CFG,
                               timeframe_ms=86_400_000)
        assert res.extras["dca_buys"] == n
        assert res.extras["invested"] == pytest.approx(15 * n)
        assert res.extras["qty_accumulated"] > 0
        assert res.equity.iloc[-1] > CFG.initial_equity  # rising market

    def test_dip_multiplier_in_sim(self):
        # flat then a >5% drop within 24h triggers the multiplier
        closes = [100.0] * 30 + [93.0] * 10
        d = DCAStrategy({"interval": "daily", "time_utc": "00:00",
                         "quote_amount": 10, "dip_enabled": True,
                         "dip_threshold_pct": 5, "dip_multiplier": 2.0})
        res = run_dca_backtest(d, make_df(closes, step_ms=86_400_000), CFG,
                               timeframe_ms=86_400_000)
        amounts = {b["amount"] for b in res.extras["buys"]}
        assert 10.0 in amounts and 20.0 in amounts


class TestMetrics:
    def test_metrics_shape_and_values(self):
        df = flat_df(30, high={10: 105.0})
        res = run_candle_backtest(BuyAtIndex({"buy_at": 5}), RISK, df, CFG)
        m = compute_metrics(res.equity, res.trades, 10_000, df,
                            res.extras["warmup"])
        for key in ("total_return_pct", "max_drawdown_pct", "win_rate_pct",
                    "profit_factor", "sharpe_ratio", "n_trades",
                    "buy_hold_return_pct", "final_equity", "disclaimer"):
            assert key in m
        assert m["n_trades"] == 1
        assert m["win_rate_pct"] == 100.0
        assert m["total_return_pct"] > 0

    def test_max_drawdown_computed(self):
        import pandas as pd
        eq = pd.Series([100.0, 110.0, 99.0, 104.5, 121.0],
                       index=[1, 2, 3, 4, 5])
        m = compute_metrics(eq, [], 100, flat_df(5), 0)
        assert m["max_drawdown_pct"] == pytest.approx(10.0)  # 110 → 99

    def test_downsample_caps_points(self):
        import pandas as pd
        eq = pd.Series(range(10_000), index=range(10_000), dtype=float)
        pts = downsample_curve(eq, max_points=500)
        assert len(pts) <= 501
        assert pts[0][0] == 0 and pts[-1][0] == 9_999
