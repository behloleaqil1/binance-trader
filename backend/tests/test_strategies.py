"""Strategy signal logic tests on deterministic synthetic data."""
from datetime import datetime, timezone

import pytest

from app.core.types import SignalAction
from app.strategies.dca import DCAStrategy
from app.strategies.grid import GridOrderView, GridStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.trend_momentum import TrendMomentumStrategy
from tests.conftest import make_df, make_position


def run_decides(strategy, df, position=None):
    """Replay decide() over the frame; returns [(i, Signal)]."""
    idf = strategy.compute_indicators(df)
    out = []
    for i in range(strategy.required_history(), len(df)):
        out.append((i, strategy.decide("TESTUSDT", idf, i, position)))
    return out


class TestTrendMomentum:
    params = {"ema_fast": 5, "ema_slow": 15, "macd_fast": 6, "macd_slow": 13,
              "macd_signal": 5, "rsi_period": 7, "rsi_buy_min": 0,
              "rsi_buy_max": 100, "require_macd": True}

    @staticmethod
    def downtrend_then_rally(n_down=40, n_up=30):
        closes = [100 * (1 - 0.004) ** i for i in range(n_down)]
        last = closes[-1]
        closes += [last * (1 + 0.008) ** i for i in range(1, n_up + 1)]
        return make_df(closes)

    def test_buy_appears_after_crossover_with_reason(self):
        strat = TrendMomentumStrategy(self.params)
        signals = run_decides(strat, self.downtrend_then_rally())
        buys = [(i, s) for i, s in signals if s.action == SignalAction.BUY]
        assert buys, "expected a BUY after the rally crossover"
        i, first = buys[0]
        assert "crossed above" in first.reason
        assert len(self.downtrend_then_rally()) - 30 < i  # fires in rally region

    def test_no_buy_during_downtrend(self):
        strat = TrendMomentumStrategy(self.params)
        df = make_df([100 * (1 - 0.004) ** i for i in range(80)])
        signals = run_decides(strat, df)
        assert all(s.action == SignalAction.HOLD for _, s in signals)

    def test_rsi_filter_blocks_hot_entry(self):
        strat = TrendMomentumStrategy({**self.params, "rsi_buy_max": 70})
        signals = run_decides(strat, self.downtrend_then_rally(n_up=40))
        # steep sustained rally → RSI pegged high → crossover must be blocked
        crossover_holds = [s for _, s in signals
                          if s.action == SignalAction.HOLD and "RSI" in s.reason
                          and "crossed up" in s.reason]
        buys = [s for _, s in signals if s.action == SignalAction.BUY]
        assert crossover_holds and not buys

    def test_sell_on_cross_down_with_position(self):
        strat = TrendMomentumStrategy(self.params)
        closes = [100 * 1.006 ** i for i in range(40)]
        closes += [closes[-1] * (1 - 0.012) ** i for i in range(1, 26)]
        pos = make_position(symbol="TESTUSDT", entry=closes[35], mark=closes[-1])
        signals = run_decides(strat, make_df(closes), position=pos)
        sells = [s for _, s in signals if s.action == SignalAction.SELL]
        assert sells
        assert any(("crossed below" in s.reason) or ("RSI" in s.reason)
                   or ("MACD" in s.reason) for s in sells)


class TestMeanReversion:
    params = {"bb_period": 20, "bb_std": 2.0, "rsi_period": 5,
              "rsi_oversold": 35, "rsi_overbought": 65, "exit_at": "middle"}

    @staticmethod
    def flat_then_plunge_then_recover():
        closes = [100 + (0.25 if i % 2 == 0 else -0.25) for i in range(40)]
        closes += [99.0, 98.0, 97.0, 96.2, 95.5]           # sharp plunge
        closes += [96.5, 97.5, 98.5, 99.5, 100.3, 100.6]   # recovery through mid
        return make_df(closes)

    def test_buy_on_oversold_below_band(self):
        strat = MeanReversionStrategy(self.params)
        signals = run_decides(strat, self.flat_then_plunge_then_recover())
        buys = [(i, s) for i, s in signals if s.action == SignalAction.BUY]
        assert buys, "expected oversold BUY in the plunge"
        i, first = buys[0]
        assert 40 <= i <= 45  # inside the plunge region
        assert "below lower band" in first.reason

    def test_sell_on_reversion_with_position(self):
        # Hold a position bought at the plunge bottom (index 44) and replay the
        # recovery: the SELL must fire once price reverts to the middle band.
        strat = MeanReversionStrategy(self.params)
        df = self.flat_then_plunge_then_recover()
        idf = strat.compute_indicators(df)
        pos = make_position(symbol="TESTUSDT", entry=95.5, mark=95.5)
        sells = []
        for i in range(44, len(df)):
            s = strat.decide("TESTUSDT", idf, i, pos)
            if s.action == SignalAction.SELL:
                sells.append((i, s))
        assert sells and sells[0][0] >= 45  # fires in the recovery region
        assert ("reverted" in sells[0][1].reason) or ("RSI" in sells[0][1].reason)

    def test_overbought_without_position_stays_flat_long_only(self):
        strat = MeanReversionStrategy(self.params)
        closes = [100 + (0.2 if i % 2 == 0 else -0.2) for i in range(40)]
        closes += [101.5, 103.0, 104.5, 106.0, 107.5]  # blow-off top
        signals = run_decides(strat, make_df(closes))
        assert all(s.action != SignalAction.SELL for _, s in signals)
        assert any("long-only" in s.reason for _, s in signals)


class TestGrid:
    def test_arithmetic_levels(self):
        g = GridStrategy({"lower_price": 90, "upper_price": 110, "levels": 5})
        assert g.levels(100) == pytest.approx([90, 95, 100, 105, 110])

    def test_geometric_levels(self):
        g = GridStrategy({"lower_price": 100, "upper_price": 400, "levels": 3,
                          "mode": "geometric"})
        assert g.levels(200) == pytest.approx([100, 200, 400])

    def test_auto_range_from_price(self):
        g = GridStrategy({"auto_range_pct": 10, "levels": 3})
        assert g.levels(100) == pytest.approx([90, 100, 110])

    def test_desired_orders_buys_below_price_only(self):
        g = GridStrategy({"lower_price": 90, "upper_price": 110, "levels": 5,
                          "quote_per_level": 20})
        plans = g.desired_orders(101.0, g.levels(101.0), [], [])
        assert [(p.side, p.level) for p in plans] == [("BUY", 0), ("BUY", 1),
                                                      ("BUY", 2)]
        assert all(p.quote_amount == 20 for p in plans)

    def test_filled_lot_gets_paired_sell_one_level_up(self):
        g = GridStrategy({"lower_price": 90, "upper_price": 110, "levels": 5,
                          "quote_per_level": 20})
        lot = make_position(pid=7, symbol="TESTUSDT", strategy="grid", qty=0.21)
        lot_ns = type("Lot", (), {"qty": 0.21, "grid_level": 1, "id": 7})()
        plans = g.desired_orders(101.0, g.levels(101.0), [], [lot_ns])
        sells = [p for p in plans if p.side == "SELL"]
        buys = [p for p in plans if p.side == "BUY"]
        assert [(s.level, s.price) for s in sells] == [(2, 100.0)]
        assert sells[0].qty == pytest.approx(0.21)
        assert [b.level for b in buys] == [0, 2]  # level 1 held, not re-bought

    def test_no_duplicate_orders_for_existing_ladder(self):
        g = GridStrategy({"lower_price": 90, "upper_price": 110, "levels": 5,
                          "quote_per_level": 20})
        open_orders = [GridOrderView("BUY", 0, "a"), GridOrderView("BUY", 1, "b"),
                       GridOrderView("BUY", 2, "c")]
        assert g.desired_orders(101.0, g.levels(101.0), open_orders, []) == []

    def test_range_detection(self):
        g = GridStrategy({"lower_price": 90, "upper_price": 110, "levels": 5})
        lv = g.levels(100)
        assert g.in_range(100, lv)
        assert not g.in_range(115, lv)
        assert not g.in_range(85, lv)


class TestDCA:
    def test_daily_schedule_due_once(self):
        d = DCAStrategy({"interval": "daily", "time_utc": "08:00"})
        now = datetime(2026, 8, 9, 9, 0, tzinfo=timezone.utc)
        assert d.is_due(None, now)
        assert d.is_due(datetime(2026, 8, 8, 8, 30, tzinfo=timezone.utc), now)
        assert not d.is_due(datetime(2026, 8, 9, 8, 30, tzinfo=timezone.utc), now)

    def test_daily_not_due_before_time(self):
        d = DCAStrategy({"interval": "daily", "time_utc": "08:00"})
        now = datetime(2026, 8, 9, 7, 0, tzinfo=timezone.utc)
        assert not d.is_due(datetime(2026, 8, 8, 8, 30, tzinfo=timezone.utc), now)

    def test_hourly_schedule(self):
        d = DCAStrategy({"interval": "hourly"})
        now = datetime(2026, 8, 9, 10, 30, tzinfo=timezone.utc)
        assert d.is_due(datetime(2026, 8, 9, 9, 59, tzinfo=timezone.utc), now)
        assert not d.is_due(datetime(2026, 8, 9, 10, 1, tzinfo=timezone.utc), now)

    def test_weekly_schedule(self):
        d = DCAStrategy({"interval": "weekly", "weekday": "MON",
                         "time_utc": "08:00"})
        sat = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)   # Saturday
        assert d.last_scheduled_at(sat) == datetime(2026, 8, 3, 8, 0,
                                                    tzinfo=timezone.utc)  # Monday
        assert d.is_due(datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc), sat)
        assert not d.is_due(datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc), sat)

    def test_dip_multiplier_applied(self):
        d = DCAStrategy({"quote_amount": 15, "dip_enabled": True,
                         "dip_threshold_pct": 5, "dip_multiplier": 1.5})
        s = d.build_signal("BTCUSDT", -6.2)
        assert s.notional_override == pytest.approx(22.5)
        assert "dip multiplier" in s.reason
        assert s.wants_protection is False  # default: accumulation has no stops

    def test_no_dip_multiplier_on_small_move(self):
        d = DCAStrategy({"quote_amount": 15, "dip_threshold_pct": 5})
        assert d.build_signal("BTCUSDT", -2.0).notional_override == pytest.approx(15)
