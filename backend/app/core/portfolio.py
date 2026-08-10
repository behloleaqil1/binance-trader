"""In-memory account view: balances, last prices, equity valuation.

Equity = quote balance (free+locked) + every *traded* base asset valued at its
latest USDT price (+ BNB if held, since fees can accrue there). Untraded
testnet confetti assets are ignored so equity reflects what the bot manages.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("portfolio")


class Portfolio:
    def __init__(self, quote_asset: str = "USDT"):
        self.quote = quote_asset
        self.balances: dict[str, tuple[float, float]] = {}  # asset -> (free, locked)
        self.prices: dict[str, float] = {}                  # symbol -> last price
        self.price_ts: dict[str, float] = {}
        self.tracked_bases: set[str] = set()                # bases of traded symbols

    # ── updates ─────────────────────────────────────────────────────────────
    def set_balances(self, balances: dict[str, tuple[float, float]]) -> None:
        self.balances = dict(balances)

    def update_balance(self, asset: str, free: float, locked: float) -> None:
        self.balances[asset] = (free, locked)

    def update_price(self, symbol: str, price: float) -> None:
        if price > 0:
            self.prices[symbol] = price
            self.price_ts[symbol] = time.time()

    def track_symbols(self, symbols: list[str], rules: dict) -> None:
        self.tracked_bases = {rules[s].base_asset for s in symbols if s in rules}

    # ── reads ───────────────────────────────────────────────────────────────
    def price_of(self, symbol: str) -> float | None:
        return self.prices.get(symbol)

    def free(self, asset: str) -> float:
        return self.balances.get(asset, (0.0, 0.0))[0]

    def asset_value_quote(self, asset: str, qty: float) -> float:
        """Value `qty` of an asset in the quote currency, 0 if no price known."""
        if qty == 0:
            return 0.0
        if asset == self.quote:
            return qty
        p = self.prices.get(f"{asset}{self.quote}")
        return qty * p if p else 0.0

    def equity(self) -> float:
        # Every held asset with a known price counts — restricting to tracked
        # bases made equity drop when a held asset left the watchlist, which
        # read as a phantom daily loss on live accounts.
        total = 0.0
        for asset, (free, locked) in self.balances.items():
            qty = free + locked
            v = self.asset_value_quote(asset, qty)
            if v == 0.0 and asset != self.quote and qty > 0:
                log.debug("no price for %s — excluded from equity", asset)
            total += v
        return total
