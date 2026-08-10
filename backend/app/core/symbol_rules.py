"""Per-symbol exchange trading rules (from GET /api/v3/exchangeInfo filters).

All quantity/price rounding for real orders happens here, with Decimal, so a
float artifact can never produce an order Binance rejects — or one a hair
larger than intended. Quantities always round DOWN.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, Decimal


def _dec(x: float | str) -> Decimal:
    return Decimal(str(x))


@dataclass(slots=True)
class SymbolRules:
    symbol: str
    base_asset: str
    quote_asset: str
    tick_size: Decimal      # PRICE_FILTER
    step_size: Decimal      # LOT_SIZE
    min_qty: Decimal        # LOT_SIZE
    min_notional: Decimal   # NOTIONAL / MIN_NOTIONAL
    status: str = "TRADING"

    @classmethod
    def from_exchange_info(cls, info: dict) -> "SymbolRules":
        tick = step = Decimal("0.00000001")
        min_qty = Decimal("0")
        min_notional = Decimal("5")
        for f in info.get("filters", []):
            ft = f.get("filterType")
            if ft == "PRICE_FILTER":
                tick = _dec(f["tickSize"]).normalize()
            elif ft == "LOT_SIZE":
                step = _dec(f["stepSize"]).normalize()
                min_qty = _dec(f["minQty"])
            elif ft in ("NOTIONAL", "MIN_NOTIONAL"):
                min_notional = _dec(f.get("minNotional", "5"))
        return cls(symbol=info["symbol"], base_asset=info["baseAsset"],
                   quote_asset=info["quoteAsset"], tick_size=tick, step_size=step,
                   min_qty=min_qty, min_notional=min_notional,
                   status=info.get("status", "TRADING"))

    # ── rounding helpers ────────────────────────────────────────────────────
    def quantize_qty(self, qty: float) -> Decimal:
        """Round a quantity DOWN to the lot step (never buy/sell more than sized)."""
        if qty <= 0:
            return Decimal("0")
        return (_dec(qty) / self.step_size).to_integral_value(ROUND_DOWN) * self.step_size

    def quantize_price(self, price: float, *, direction: str = "nearest") -> Decimal:
        """Round a price to the tick grid. direction: nearest | down | up."""
        d = _dec(price) / self.tick_size
        if direction == "down":
            n = d.to_integral_value(ROUND_FLOOR)
        elif direction == "up":
            n = d.to_integral_value(ROUND_CEILING)
        else:
            n = d.to_integral_value(ROUND_HALF_UP)
        return n * self.tick_size

    def meets_min(self, qty: Decimal, price: float) -> bool:
        return qty >= self.min_qty and qty * _dec(price) >= self.min_notional

    def fmt_qty(self, qty: Decimal) -> str:
        return format(qty.normalize(), "f")

    def fmt_price(self, price: Decimal) -> str:
        return format(price.normalize(), "f")
