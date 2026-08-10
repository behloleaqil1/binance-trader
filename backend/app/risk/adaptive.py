"""Adaptive risk governance: react to each strategy's recent wins and losses.

Principles (deliberately anti-martingale):
  • Losing streaks SHRINK position size — size is halved for every
    `halve_size_after_losses` consecutive losses, floored at
    `min_size_multiplier`. Size is never increased to "win back" losses.
  • Persistent losers get PAUSED (probation): a long losing streak, or a
    rolling profit factor below threshold once the window is full, stops that
    strategy from opening new positions until the user re-saves it. Exits and
    protective orders are never affected.
  • Winning streaks may modestly increase size, only if explicitly enabled,
    capped well below 2×.

Honest framing: this improves discipline and survival — cutting losers'
exposure quickly — but it cannot create edge. Profitability still depends on
the strategy actually working, which is what backtesting measures.

Pure functions over a list of trade PnLs → trivially unit-testable and reused
verbatim by the backtester.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.risk.models import RiskConfig


@dataclass(slots=True)
class AdaptiveState:
    n: int                      # trades in the rolling window
    wins: int
    losses: int
    win_rate_pct: float
    profit_factor: float | None  # None until any losses exist
    expectancy: float           # mean PnL per trade in the window
    consecutive_losses: int
    consecutive_wins: int
    size_multiplier: float
    paused: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_adaptive(pnls: list[float], cfg: RiskConfig) -> AdaptiveState:
    """pnls: closed-trade PnLs for ONE strategy, oldest → newest."""
    window = pnls[-cfg.adaptive_window:] if cfg.adaptive_window else list(pnls)
    n = len(window)
    wins = sum(1 for p in window if p > 0)
    losses = n - wins
    gross_win = sum(p for p in window if p > 0)
    gross_loss = -sum(p for p in window if p <= 0)
    profit_factor = (gross_win / gross_loss) if gross_loss > 1e-12 else None
    expectancy = (sum(window) / n) if n else 0.0

    consecutive_losses = 0
    for p in reversed(window):
        if p <= 0:
            consecutive_losses += 1
        else:
            break
    consecutive_wins = 0
    for p in reversed(window):
        if p > 0:
            consecutive_wins += 1
        else:
            break

    multiplier = 1.0
    paused = False
    reason = "adaptive sizing at full size"

    if cfg.adaptive_enabled and n:
        halvings = consecutive_losses // cfg.halve_size_after_losses
        if halvings > 0:
            multiplier = max(cfg.min_size_multiplier, 0.5 ** halvings)
            reason = (f"{consecutive_losses} consecutive losses → size ×"
                      f"{multiplier:g}")
        elif (cfg.win_boost_enabled
              and consecutive_wins >= cfg.win_boost_after_wins):
            multiplier = cfg.win_boost_multiplier
            reason = (f"{consecutive_wins} consecutive wins → size ×"
                      f"{multiplier:g}")

        if cfg.auto_pause_enabled:
            if consecutive_losses >= cfg.pause_after_consecutive_losses:
                paused = True
                reason = (f"PROBATION: {consecutive_losses} consecutive losses "
                          f"(≥ {cfg.pause_after_consecutive_losses}) — no new "
                          f"entries until the strategy is re-saved")
            elif (n >= cfg.adaptive_window and profit_factor is not None
                  and profit_factor < cfg.pause_below_profit_factor):
                paused = True
                reason = (f"PROBATION: profit factor {profit_factor:.2f} < "
                          f"{cfg.pause_below_profit_factor} over the last {n} "
                          f"trades — no new entries until re-saved")

    return AdaptiveState(
        n=n, wins=wins, losses=losses,
        win_rate_pct=round(wins / n * 100, 2) if n else 0.0,
        profit_factor=round(profit_factor, 3) if profit_factor is not None else None,
        expectancy=round(expectancy, 6),
        consecutive_losses=consecutive_losses,
        consecutive_wins=consecutive_wins,
        size_multiplier=multiplier, paused=paused, reason=reason)
