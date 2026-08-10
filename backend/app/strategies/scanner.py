"""Momentum scanner: ranks USDT pairs by short-term movement so strategies can
opt into trading the current top movers.

Honest framing (also shown in the UI): the scanner finds *movement*, not
guaranteed profit — recent top gainers are exactly as capable of dumping as
pumping. Scanner symbols pass the identical risk gate as static pairs.
"""
from __future__ import annotations

from dataclasses import dataclass

# Leveraged-token suffixes and stable/fiat bases we never auto-trade.
_LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
_EXCLUDED_BASES = {
    "USDC", "TUSD", "FDUSD", "DAI", "USDP", "AEUR", "EUR", "EURI", "GBP", "TRY",
    "BRL", "ARS", "UST", "BUSD", "PAX", "USDS", "XUSD", "USD1",
}


@dataclass(slots=True)
class ScannedSymbol:
    symbol: str
    price_change_pct: float
    quote_volume: float
    last_price: float


def select_symbols(tickers: list[dict], tradable_symbols: dict[str, str],
                   *, quote_asset: str = "USDT", top_n: int = 5,
                   min_quote_volume: float = 10_000_000.0,
                   rank_by: str = "top_gainers") -> list[ScannedSymbol]:
    """Filter + rank 24h tickers.

    tickers: raw items from GET /api/v3/ticker/24hr
    tradable_symbols: symbol -> base asset, for symbols with status TRADING
    """
    candidates: list[ScannedSymbol] = []
    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith(quote_asset) or sym not in tradable_symbols:
            continue
        base = tradable_symbols[sym]
        if base in _EXCLUDED_BASES:
            continue
        if any(base.endswith(suf) for suf in _LEVERAGED_SUFFIXES):
            continue
        try:
            change = float(t.get("priceChangePercent", 0.0))
            qvol = float(t.get("quoteVolume", 0.0))
            last = float(t.get("lastPrice", 0.0))
        except (TypeError, ValueError):
            continue
        if last <= 0 or qvol < min_quote_volume:
            continue
        candidates.append(ScannedSymbol(sym, change, qvol, last))

    if rank_by == "top_losers":
        candidates.sort(key=lambda c: c.price_change_pct)
    elif rank_by == "volume":
        candidates.sort(key=lambda c: c.quote_volume, reverse=True)
    else:  # top_gainers
        candidates.sort(key=lambda c: c.price_change_pct, reverse=True)
    return candidates[:top_n]
