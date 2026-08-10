"""Risk & scanner configuration models (validated, DB-persisted, UI-editable).

Defaults are deliberately conservative and sized so orders stay above
Binance's ~$5 minimum notional even at small account sizes.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class RiskConfig(BaseModel):
    # Position sizing
    # Cap raised from 25 → 95 on 2026-08-10 at the user's explicit request so a
    # micro account (7.72 USDT) can clear Binance's ~5 USDT minimum notional.
    # Sizing above ~25% concentrates the account in a single position.
    position_size_pct: float = Field(2.0, gt=0, le=95,
        description="% of account equity per new position")

    # Protective exits (attached to every position unless exempted below)
    stop_loss_pct: float = Field(2.0, gt=0.1, le=50)
    take_profit_pct: float = Field(4.0, gt=0.1, le=200)
    trailing_stop_enabled: bool = False
    trailing_stop_pct: float = Field(1.5, gt=0.1, le=20,
        description="Trail distance below the high-water mark")
    trailing_activation_pct: float = Field(1.0, ge=0, le=50,
        description="Unrealized profit % required before the trail arms")

    # Hard limits
    max_daily_loss_pct: float = Field(3.0, gt=0.1, le=50,
        description="Equity loss vs UTC-day start that halts new entries until next day")
    max_drawdown_pct: float = Field(10.0, gt=0.5, le=90,
        description="Equity drawdown vs peak that trips the kill switch")
    kill_switch_enabled: bool = True
    flatten_on_kill: bool = Field(False,
        description="Also market-close all positions when the kill switch trips")

    # Concurrency / exposure
    max_open_positions: int = Field(4, ge=1, le=50)
    max_exposure_per_asset_pct: float = Field(25.0, gt=1, le=100,
        description="Max % of equity in a single base asset (positions + open buys)")
    max_total_exposure_pct: float = Field(80.0, gt=1, le=100,
        description="Max % of equity deployed across all positions + open buys")

    # Explicit, visible exemption: DCA accumulation carries no SL/TP by default.
    exempt_dca_from_stops: bool = True

    # ── Adaptive sizing & probation (reacts to each strategy's recent trades;
    #    applies to signal entries — grid ladders and DCA schedules excluded).
    adaptive_enabled: bool = True
    adaptive_window: int = Field(20, ge=5, le=100,
        description="Rolling number of closed trades per strategy considered")
    halve_size_after_losses: int = Field(3, ge=2, le=10,
        description="Every N consecutive losses halves that strategy's position size")
    min_size_multiplier: float = Field(0.25, gt=0.05, le=1.0)
    auto_pause_enabled: bool = True
    pause_after_consecutive_losses: int = Field(6, ge=3, le=30,
        description="Probation: stop new entries after this losing streak")
    pause_below_profit_factor: float = Field(0.6, gt=0.0, le=1.0,
        description="Probation when rolling profit factor drops below this (full window only)")
    win_boost_enabled: bool = False  # never on by default: upsizing adds risk
    win_boost_after_wins: int = Field(4, ge=2, le=20)
    win_boost_multiplier: float = Field(1.25, ge=1.0, le=1.5)

    @model_validator(mode="after")
    def _sane(self):
        if self.take_profit_pct <= 0 or self.stop_loss_pct <= 0:
            raise ValueError("SL/TP must be positive")
        if self.max_drawdown_pct <= self.max_daily_loss_pct:
            raise ValueError("max_drawdown_pct should exceed max_daily_loss_pct")
        return self


class ScannerConfig(BaseModel):
    enabled: bool = False  # opt-in
    top_n: int = Field(5, ge=1, le=15)
    rank_by: str = Field("top_gainers", pattern="^(top_gainers|top_losers|volume)$")
    min_quote_volume_24h: float = Field(10_000_000, ge=0,
        description="Liquidity floor (ignored on testnet, where volume is simulated)")
    refresh_minutes: int = Field(15, ge=5, le=240)
    max_symbols_total: int = Field(12, ge=1, le=30,
        description="Cap on total symbols the engine streams (static + scanned)")
