"""Adaptive sizing & probation tests — anti-martingale behavior must hold."""
import pytest

from app.core.types import Signal, SignalAction
from app.risk.adaptive import evaluate_adaptive
from app.risk.models import RiskConfig
from app.risk.risk_engine import RiskEngine
from tests.conftest import make_account

CFG = RiskConfig()  # defaults: halve every 3 losses, pause at 6, PF pause < 0.6


class TestAdaptiveSizing:
    def test_no_history_full_size(self):
        s = evaluate_adaptive([], CFG)
        assert s.size_multiplier == 1.0 and not s.paused and s.n == 0

    def test_wins_keep_full_size(self):
        s = evaluate_adaptive([5.0, 3.0, 8.0], CFG)
        assert s.size_multiplier == 1.0 and not s.paused
        assert s.consecutive_wins == 3

    def test_three_losses_halve(self):
        s = evaluate_adaptive([5.0, -1.0, -1.0, -1.0], CFG)
        assert s.consecutive_losses == 3
        assert s.size_multiplier == 0.5
        assert not s.paused

    def test_six_losses_quarter_and_probation(self):
        s = evaluate_adaptive([-1.0] * 6, CFG)
        assert s.size_multiplier == 0.25
        assert s.paused and "PROBATION" in s.reason

    def test_floor_respected(self):
        cfg = RiskConfig(pause_after_consecutive_losses=30, auto_pause_enabled=True)
        s = evaluate_adaptive([-1.0] * 12, cfg)  # 4 halvings → 0.0625, floored
        assert s.size_multiplier == cfg.min_size_multiplier

    def test_win_resets_streak(self):
        s = evaluate_adaptive([-1.0, -1.0, -1.0, 4.0], CFG)
        assert s.consecutive_losses == 0
        assert s.size_multiplier == 1.0

    def test_never_upsizes_after_losses(self):
        # anti-martingale invariant: multiplier ≤ 1 whenever the last trade lost
        for streak in range(1, 10):
            s = evaluate_adaptive([-1.0] * streak, CFG)
            assert s.size_multiplier <= 1.0

    def test_disabled_is_inert(self):
        cfg = RiskConfig(adaptive_enabled=False, auto_pause_enabled=False)
        s = evaluate_adaptive([-1.0] * 20, cfg)
        assert s.size_multiplier == 1.0 and not s.paused


class TestProbation:
    def test_profit_factor_pause_needs_full_window(self):
        cfg = RiskConfig(adaptive_window=10)
        losing = [-2.0, 1.0] * 4  # PF = 4/8 = 0.5, but only 8 trades
        assert not evaluate_adaptive(losing, cfg).paused
        losing = [-2.0, 1.0] * 5  # 10 trades, PF 0.5 < 0.6, streak 0
        s = evaluate_adaptive(losing, cfg)
        assert s.paused and "profit factor" in s.reason

    def test_pause_disabled_only_shrinks(self):
        cfg = RiskConfig(auto_pause_enabled=False)
        s = evaluate_adaptive([-1.0] * 8, cfg)
        assert not s.paused and s.size_multiplier == 0.25


class TestWinBoost:
    def test_boost_off_by_default(self):
        s = evaluate_adaptive([1.0] * 8, CFG)
        assert s.size_multiplier == 1.0

    def test_boost_when_enabled(self):
        cfg = RiskConfig(win_boost_enabled=True, win_boost_after_wins=4,
                         win_boost_multiplier=1.25)
        s = evaluate_adaptive([1.0] * 4, cfg)
        assert s.size_multiplier == 1.25

    def test_boost_capped_by_validation(self):
        with pytest.raises(ValueError):
            RiskConfig(win_boost_multiplier=1.9)


class TestRiskEngineIntegration:
    def test_multiplier_scales_qty(self, rules):
        e = RiskEngine(RiskConfig())
        sig = Signal(SignalAction.BUY, "BTCUSDT", "trend_momentum", "t", price=100.0)
        full = e.evaluate_entry(sig, 100.0, make_account(10_000), rules)
        half = e.evaluate_entry(sig, 100.0, make_account(10_000), rules,
                                size_multiplier=0.5)
        assert half.approved and full.approved
        assert half.plan.qty == pytest.approx(full.plan.qty / 2)
        assert any("adaptive" in c for c in half.checks)
