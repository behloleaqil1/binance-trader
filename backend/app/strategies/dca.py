"""DCA: scheduled fixed-amount buys, optionally upsized on 24h dips.

Accumulation positions default to *no* stop-loss (a stop defeats the purpose of
averaging in) — this exemption is explicit in the risk config and shown on the
Risk page. DCA inventory still counts toward exposure caps, equity, daily-loss
and drawdown checks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.types import Signal, SignalAction
from app.strategies.base import ParamSpec, Strategy

_WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


class DCAStrategy(Strategy):
    id = "dca"
    name = "DCA (Dollar-Cost Averaging)"
    description = ("Buys a fixed quote amount on a schedule (hourly/daily/weekly), "
                   "optionally increasing the buy when the 24h change shows a dip. "
                   "Accumulates inventory; no stop-loss by default (configurable).")
    kind = "schedule"

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("interval", "Buy interval", "select", "daily",
                      choices=["hourly", "daily", "weekly"]),
            ParamSpec("time_utc", "Time of day (UTC, HH:MM)", "time", "08:00",
                      help="Used for daily/weekly schedules"),
            ParamSpec("weekday", "Weekday", "select", "MON", choices=_WEEKDAYS,
                      help="Used for weekly schedule"),
            ParamSpec("quote_amount", "Buy amount (USDT)", "float", 15.0, min=1.0),
            ParamSpec("dip_enabled", "Buy more on dips", "bool", True),
            ParamSpec("dip_threshold_pct", "Dip threshold (24h drop %)", "float", 5.0,
                      min=0.5, max=50),
            ParamSpec("dip_multiplier", "Dip buy multiplier", "float", 1.5, min=1.0, max=5.0),
            ParamSpec("protect_with_stops", "Attach SL/TP to DCA buys", "bool", False),
        ]

    # ── schedule math (unit-tested, timezone-aware UTC) ─────────────────────
    def _parse_time(self) -> tuple[int, int]:
        try:
            hh, mm = self.params["time_utc"].split(":")
            return max(0, min(23, int(hh))), max(0, min(59, int(mm)))
        except (ValueError, AttributeError):
            return 8, 0

    def last_scheduled_at(self, now: datetime) -> datetime:
        """Most recent schedule point at or before `now`."""
        interval = self.params["interval"]
        if interval == "hourly":
            return now.replace(minute=0, second=0, microsecond=0)
        hh, mm = self._parse_time()
        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if interval == "daily":
            return candidate if candidate <= now else candidate - timedelta(days=1)
        target_wd = _WEEKDAYS.index(self.params["weekday"])
        days_back = (candidate.weekday() - target_wd) % 7
        candidate -= timedelta(days=days_back)
        if candidate > now:
            candidate -= timedelta(days=7)
        return candidate

    def is_due(self, last_run: datetime | None, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        scheduled = self.last_scheduled_at(now)
        return last_run is None or last_run < scheduled

    def build_signal(self, symbol: str, ticker_24h_change_pct: float | None) -> Signal:
        p = self.params
        amount = p["quote_amount"]
        reason = (f"scheduled DCA buy ({p['interval']}) of {amount:g} USDT")
        if (p["dip_enabled"] and ticker_24h_change_pct is not None
                and ticker_24h_change_pct <= -p["dip_threshold_pct"]):
            amount = round(amount * p["dip_multiplier"], 2)
            reason += (f"; 24h change {ticker_24h_change_pct:.2f}% ≤ "
                       f"−{p['dip_threshold_pct']}% → dip multiplier ×"
                       f"{p['dip_multiplier']:g} applied, buying {amount:g} USDT")
        elif p["dip_enabled"] and ticker_24h_change_pct is not None:
            reason += f" (24h change {ticker_24h_change_pct:.2f}%, no dip bonus)"
        return Signal(SignalAction.BUY, symbol, self.id, reason,
                      notional_override=amount,
                      wants_protection=bool(p["protect_with_stops"]))
