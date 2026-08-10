"""Grid trading: a ladder of buy limits below price; each fill places a paired
sell one level up. Pure functions here compute the *desired* ladder; the engine
diffs it against open orders and routes every new order through the risk gate.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.types import PositionView
from app.strategies.base import ParamSpec, Strategy


@dataclass(slots=True)
class GridOrderView:
    """Minimal view of an existing open grid order (from the DB/exchange)."""
    side: str          # BUY / SELL
    level: int         # index into levels()
    client_order_id: str


@dataclass(slots=True)
class GridPlan:
    side: str
    level: int
    price: float
    quote_amount: float | None = None  # buys sized in quote
    qty: float | None = None           # sells sized by the lot being exited


class GridStrategy(Strategy):
    id = "grid"
    name = "Grid Trading"
    description = ("Places buy limit orders at fixed levels below price and sells each "
                   "filled lot one level higher. Profits from oscillation inside the "
                   "range; pauses (with an alert) if price leaves the range.")
    kind = "grid"

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("lower_price", "Lower bound", "float", 0.0, min=0.0,
                      help="0 = auto: current price − auto range %"),
            ParamSpec("upper_price", "Upper bound", "float", 0.0, min=0.0,
                      help="0 = auto: current price + auto range %"),
            ParamSpec("auto_range_pct", "Auto range ± %", "float", 5.0, min=0.5, max=50),
            ParamSpec("levels", "Grid levels", "int", 8, min=3, max=50),
            ParamSpec("quote_per_level", "Quote per level (USDT)", "float", 15.0, min=1.0,
                      help="Order size per grid level; must clear Binance's min notional (~$5)"),
            ParamSpec("mode", "Spacing", "select", "arithmetic",
                      choices=["arithmetic", "geometric"]),
            ParamSpec("stop_outside_range", "Pause when price exits range", "bool", True),
            ParamSpec("flatten_on_stop", "Sell inventory when paused", "bool", False),
        ]

    def required_history(self) -> int:
        return 2  # grid does not use indicators

    # ── pure grid math (unit-tested) ────────────────────────────────────────
    def levels(self, ref_price: float) -> list[float]:
        p = self.params
        lower, upper = p["lower_price"], p["upper_price"]
        if lower <= 0 or upper <= 0 or upper <= lower:
            span = p["auto_range_pct"] / 100.0
            lower, upper = ref_price * (1 - span), ref_price * (1 + span)
        n = p["levels"]
        if p["mode"] == "arithmetic":
            step = (upper - lower) / (n - 1)
            return [lower + step * k for k in range(n)]
        ratio = (upper / lower) ** (1 / (n - 1))
        return [lower * ratio ** k for k in range(n)]

    def in_range(self, price: float, levels: list[float]) -> bool:
        # Small tolerance so the boundary level itself doesn't flap the grid.
        return levels[0] * 0.998 <= price <= levels[-1] * 1.002

    def desired_orders(self, price: float, levels: list[float],
                       open_orders: list[GridOrderView],
                       inventory: list[PositionView]) -> list[GridPlan]:
        """Compute the ladder that *should* exist right now.

        inventory: OPEN positions created by grid buys; PositionView must carry
        grid_level via its strategy-tagged position row (engine supplies it).
        """
        p = self.params
        open_buy_levels = {o.level for o in open_orders if o.side == "BUY"}
        open_sell_levels = {o.level for o in open_orders if o.side == "SELL"}
        # Levels whose lot is bought and awaiting its paired sell at level+1.
        lot_by_level: dict[int, PositionView] = {}
        for lot in inventory:
            lvl = getattr(lot, "grid_level", None)
            if lvl is not None:
                lot_by_level[lvl] = lot

        plans: list[GridPlan] = []
        for idx, level_price in enumerate(levels):
            if level_price >= price:
                break  # buys only below current price
            if idx in open_buy_levels or idx in lot_by_level:
                continue  # already working or already holding this level's lot
            if idx + 1 < len(levels) and (idx + 1) in open_sell_levels:
                continue  # paired sell still open from a previous cycle
            plans.append(GridPlan("BUY", idx, level_price,
                                  quote_amount=p["quote_per_level"]))

        for idx, lot in lot_by_level.items():
            sell_level = idx + 1
            if sell_level >= len(levels):
                continue  # topmost lot: held until range logic exits it
            if sell_level in open_sell_levels:
                continue
            plans.append(GridPlan("SELL", sell_level, levels[sell_level], qty=lot.qty))
        return plans
