"""Risk engine unit tests — every hard limit must actually be hard."""
import pytest

from app.core.types import BotStatus, OrderPurpose, Signal, SignalAction
from app.risk.models import RiskConfig
from app.risk.risk_engine import RiskEngine
from tests.conftest import make_account, make_position


def sig(strategy="trend_momentum", symbol="BTCUSDT", **kw) -> Signal:
    return Signal(SignalAction.BUY, symbol, strategy, "test signal", price=100.0, **kw)


def engine(**overrides) -> RiskEngine:
    return RiskEngine(RiskConfig(**overrides))


PRICE = 100.0


class TestSizing:
    def test_pct_of_equity_sizing_with_sl_tp(self, rules):
        d = engine().evaluate_entry(sig(), PRICE, make_account(10_000), rules)
        assert d.approved, d.reason
        assert d.plan.qty == pytest.approx(2.0)          # 2% of 10k = $200 @ 100
        assert d.plan.sl_price == pytest.approx(98.0)    # −2%
        assert d.plan.tp_price == pytest.approx(104.0)   # +4%
        assert d.plan.side == "BUY" and d.plan.type == "MARKET"
        assert d.checks  # audit trail present

    def test_qty_rounds_down_to_step(self, rules):
        d = engine(position_size_pct=1.234).evaluate_entry(
            sig(), 99.7, make_account(10_000), rules)
        assert d.approved
        step = 0.001
        assert abs(d.plan.qty / step - round(d.plan.qty / step)) < 1e-9
        assert d.plan.qty * 99.7 <= 10_000 * 0.01234 + 1e-6  # never over-sized

    def test_below_min_notional_rejected(self, rules):
        d = engine(position_size_pct=2.0).evaluate_entry(
            sig(), PRICE, make_account(100.0), rules)  # $2 order < $5 min
        assert not d.approved
        assert "minimum" in d.reason.lower()

    def test_fixed_notional_override_dca(self, rules):
        s = Signal(SignalAction.BUY, "BTCUSDT", "dca", "dca buy",
                   notional_override=15.0, wants_protection=False)
        d = engine().evaluate_entry(s, PRICE, make_account(10_000), rules,
                                    purpose=OrderPurpose.DCA_BUY)
        assert d.approved
        assert d.plan.qty == pytest.approx(0.15)
        assert d.plan.sl_price is None and d.plan.tp_price is None  # exempt

    def test_dca_exemption_disabled_gets_stops(self, rules):
        s = Signal(SignalAction.BUY, "BTCUSDT", "dca", "dca buy",
                   notional_override=15.0, wants_protection=False)
        d = engine(exempt_dca_from_stops=False).evaluate_entry(
            s, PRICE, make_account(10_000), rules, purpose=OrderPurpose.DCA_BUY)
        assert d.approved
        assert d.plan.sl_price is not None and d.plan.tp_price is not None


class TestStateGates:
    @pytest.mark.parametrize("status", [BotStatus.STOPPED, BotStatus.PAUSED,
                                        BotStatus.DAILY_HALT, BotStatus.KILLED])
    def test_entries_blocked_unless_running(self, rules, status):
        d = engine().evaluate_entry(sig(), PRICE,
                                    make_account(status=status), rules)
        assert not d.approved

    def test_non_trading_symbol_rejected(self, rules):
        rules.status = "BREAK"
        d = engine().evaluate_entry(sig(), PRICE, make_account(), rules)
        assert not d.approved and "not tradable" in d.reason


class TestCircuitBreakers:
    def test_daily_loss_breach_detected_and_blocks(self, rules):
        acct = make_account(equity=9_600, day_start=10_000)  # −4% vs 3% limit
        e = engine()
        breach = e.check_daily_loss(acct)
        assert breach and breach.kind == "DAILY_LOSS"
        assert not e.evaluate_entry(sig(), PRICE, acct, rules).approved

    def test_daily_loss_under_limit_ok(self, rules):
        acct = make_account(equity=9_800, day_start=10_000)  # −2%
        assert engine().check_daily_loss(acct) is None

    def test_drawdown_kill_detected(self):
        acct = make_account(equity=8_900, peak=10_000)  # −11% vs 10% limit
        breach = engine().check_drawdown(acct)
        assert breach and breach.kind == "DRAWDOWN"
        assert "KILL" in breach.message

    def test_drawdown_respects_disable_flag(self):
        acct = make_account(equity=5_000, peak=10_000)
        assert engine(kill_switch_enabled=False).check_drawdown(acct) is None


class TestExposureLimits:
    def test_max_open_positions(self, rules):
        positions = [make_position(pid=i, symbol=f"S{i}USDT", strategy="trend_momentum")
                     for i in range(4)]  # cap is 4
        d = engine().evaluate_entry(sig(symbol="BTCUSDT"), PRICE,
                                    make_account(positions=positions), rules)
        assert not d.approved and "max open positions" in d.reason

    def test_duplicate_strategy_symbol_position_rejected(self, rules):
        pos = make_position(symbol="BTCUSDT", strategy="trend_momentum")
        d = engine().evaluate_entry(sig(), PRICE,
                                    make_account(positions=[pos]), rules)
        assert not d.approved and "already has an open position" in d.reason

    def test_grid_lots_share_one_slot(self, rules):
        # 3 grid lots on one symbol count as ONE position toward the cap.
        lots = [make_position(pid=i, symbol="BTCUSDT", strategy="grid", qty=0.001)
                for i in range(3)]
        s = Signal(SignalAction.BUY, "BTCUSDT", "grid", "grid buy",
                   notional_override=15.0, tags={"grid_level": 1})
        d = engine().evaluate_entry(s, PRICE, make_account(positions=lots), rules,
                                    purpose=OrderPurpose.GRID_BUY,
                                    order_type="LIMIT", limit_price=95.0)
        assert d.approved, d.reason
        assert d.plan.type == "LIMIT" and d.plan.price == pytest.approx(95.0)

    def test_per_asset_exposure_cap(self, rules):
        # cap 25% of 10k = 2500; existing 2400 + new 200 → reject
        pos = make_position(symbol="BTCUSDT", strategy="mean_reversion",
                            qty=24.0, entry=100.0, mark=100.0)
        d = engine().evaluate_entry(sig(strategy="trend_momentum"), PRICE,
                                    make_account(positions=[pos]), rules)
        assert not d.approved and "per-asset exposure" in d.reason

    def test_open_buy_orders_count_toward_exposure(self, rules):
        d = engine().evaluate_entry(
            sig(), PRICE, make_account(open_buys={"BTCUSDT": 2_400.0}), rules)
        assert not d.approved and "per-asset exposure" in d.reason

    def test_total_exposure_cap(self, rules):
        # 80% of 10k = 8000 deployed cap; 7900 in others + 200 new → reject
        pos = make_position(symbol="ETHUSDT", strategy="mean_reversion",
                            qty=79.0, entry=100.0, mark=100.0)
        d = engine(max_exposure_per_asset_pct=100).evaluate_entry(
            sig(), PRICE, make_account(positions=[pos]), rules)
        assert not d.approved and "total exposure" in d.reason


class TestUsageReport:
    def test_usage_shape_and_values(self):
        pos = make_position(qty=10.0, entry=100.0, mark=100.0)  # $1000
        acct = make_account(equity=10_000, day_start=10_200, peak=10_500,
                            positions=[pos])
        u = engine().usage(acct)
        assert u["daily_loss"]["used_pct"] == pytest.approx(1.961, abs=0.01)
        assert u["drawdown"]["used_pct"] == pytest.approx(4.762, abs=0.01)
        assert u["open_positions"] == {"used": 1, "limit": 4}
        assert u["total_exposure"]["used_pct"] == pytest.approx(10.0)
        assert u["per_asset"][0]["symbol"] == "BTCUSDT"


class TestConfigValidation:
    def test_drawdown_must_exceed_daily_loss(self):
        with pytest.raises(ValueError):
            RiskConfig(max_daily_loss_pct=10, max_drawdown_pct=5)

    def test_percent_bounds(self):
        with pytest.raises(ValueError):
            RiskConfig(position_size_pct=0)
        with pytest.raises(ValueError):
            RiskConfig(position_size_pct=96)
        assert RiskConfig(position_size_pct=75).position_size_pct == 75
