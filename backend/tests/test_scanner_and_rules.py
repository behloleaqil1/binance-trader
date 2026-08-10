"""Momentum scanner filtering/ranking + exchange-rule quantization tests."""
from decimal import Decimal

import pytest

from app.core.symbol_rules import SymbolRules
from app.strategies.scanner import select_symbols


def t(symbol, change, vol, price=1.0):
    return {"symbol": symbol, "priceChangePercent": str(change),
            "quoteVolume": str(vol), "lastPrice": str(price)}


TRADABLE = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "PEPEUSDT": "PEPE",
            "SOLUSDT": "SOL", "USDCUSDT": "USDC", "BTCUPUSDT": "BTCUP",
            "DOGEUSDT": "DOGE"}


class TestScanner:
    def test_ranks_top_gainers(self):
        picks = select_symbols(
            [t("BTCUSDT", 2, 5e8), t("ETHUSDT", 8, 3e8), t("SOLUSDT", 15, 1e8),
             t("DOGEUSDT", 4, 9e7)],
            TRADABLE, top_n=2, min_quote_volume=1e7)
        assert [p.symbol for p in picks] == ["SOLUSDT", "ETHUSDT"]

    def test_excludes_stables_and_leveraged_tokens(self):
        picks = select_symbols(
            [t("USDCUSDT", 30, 9e8), t("BTCUPUSDT", 40, 9e8), t("BTCUSDT", 1, 9e8)],
            TRADABLE, top_n=5, min_quote_volume=0)
        assert [p.symbol for p in picks] == ["BTCUSDT"]

    def test_liquidity_floor_and_unknown_symbols(self):
        picks = select_symbols(
            [t("PEPEUSDT", 50, 5_000), t("FAKEUSDT", 90, 9e9), t("ETHUSDT", 3, 9e8)],
            TRADABLE, top_n=5, min_quote_volume=1_000_000)
        assert [p.symbol for p in picks] == ["ETHUSDT"]  # PEPE illiquid, FAKE unknown

    def test_rank_by_volume(self):
        picks = select_symbols(
            [t("BTCUSDT", 1, 5e8), t("ETHUSDT", 9, 3e8)],
            TRADABLE, top_n=2, min_quote_volume=0, rank_by="volume")
        assert [p.symbol for p in picks] == ["BTCUSDT", "ETHUSDT"]


class TestSymbolRules:
    def make(self):
        return SymbolRules(symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
                           tick_size=Decimal("0.01"), step_size=Decimal("0.00001"),
                           min_qty=Decimal("0.00001"), min_notional=Decimal("5"))

    def test_qty_always_rounds_down(self):
        r = self.make()
        assert r.quantize_qty(0.123456789) == Decimal("0.12345")
        assert r.quantize_qty(0.00001999) == Decimal("0.00001")

    def test_price_rounding_directions(self):
        r = self.make()
        assert r.quantize_price(100.129, direction="down") == Decimal("100.12")
        assert r.quantize_price(100.121, direction="up") == Decimal("100.13")
        assert r.quantize_price(100.126) == Decimal("100.13")

    def test_min_notional_check(self):
        r = self.make()
        assert not r.meets_min(Decimal("0.00004"), 100_000)  # $4 < $5
        assert r.meets_min(Decimal("0.00006"), 100_000)      # $6 ≥ $5

    def test_from_exchange_info_parses_filters(self):
        rules = SymbolRules.from_exchange_info({
            "symbol": "ETHUSDT", "baseAsset": "ETH", "quoteAsset": "USDT",
            "status": "TRADING",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                {"filterType": "LOT_SIZE", "stepSize": "0.00010000",
                 "minQty": "0.00010000"},
                {"filterType": "NOTIONAL", "minNotional": "5.00000000"}]})
        assert rules.tick_size == Decimal("0.01")
        assert rules.step_size == Decimal("0.0001")
        assert rules.min_notional == Decimal("5")

    def test_formatting_has_no_exponent(self):
        r = self.make()
        assert r.fmt_qty(Decimal("0.00012")) == "0.00012"
        assert "E" not in r.fmt_price(Decimal("100.12")).upper()
