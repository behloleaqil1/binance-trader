"""Research script (NOT production code): cross-symbol relative-strength /
rotation, a mechanically new data axis for this programme.

Per DISTILLED LEARNINGS after Run 18: all four strategy families tried so
far (trend_momentum EMA-cross, mean_reversion BB/RSI, grid range-ladder,
Donchian breakout) and every confirmation-gate mechanism (ADX, relative-
volume, MTF direction) are per-symbol, price-derived signals — and every
one of them has failed on this 8-symbol/1h-4h universe. The flagged next
step (b) is a genuinely different data axis: rank the 8 symbols by recent
relative performance and rotate into the leaders, rather than deriving a
signal from any single symbol's own price/volume history in isolation.

Mechanism: at each candle, compute each symbol's lookback-period return
(momentum), rank all 8 symbols cross-sectionally (1 = strongest), and BUY
a symbol only while it is in the top-K by rank. Exit (SELL) when its rank
falls below an exit threshold (>= top_k, i.e. hysteresis to reduce
whipsaw/turnover) or, in the no-hysteresis variant, as soon as it drops
out of the top-K. An optional require_positive_momentum filter additionally
requires the leader's own lookback return to be positive (so in a
universe-wide selloff we don't buy "least-bad losers").

This requires cross-symbol context that Strategy.decide() does not get by
default (it only sees one symbol's own df) — so the rank/momentum are
computed once across the whole universe and merged into each symbol's df
as ordinary columns before compute_indicators/decide ever run. No
lookahead: rank at row i uses only closes up to and including row i,
which is standard for this codebase (candle i's close is already known
when decide() is called for row i, same convention as every existing
strategy).

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file — only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS
trades) on a genuine held-out window.
"""
import asyncio
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.core.types import PositionView, Signal, SignalAction
from app.risk.models import RiskConfig
from app.strategies.base import TIMEFRAMES, ParamSpec, Strategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-21", "2026-06-19"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-19", "2026-08-19"     # 60d-0d ago (today's anchor)
OLDER_START, OLDER_END = "2025-12-21", "2026-03-21"   # 240d-150d ago, 3rd-window check


class RelativeStrengthRotationStrategy(Strategy):
    """BUY while this symbol ranks in the top-K of the 8-symbol universe by
    lookback-period return. SELL once its rank falls below exit_k (>=
    top_k gives hysteresis, reducing rank-flicker turnover). rs_rank /
    rs_momentum columns must already be present on df (merged in by the
    caller — see build_universe_frame below) since ranking needs the
    whole universe, not just this symbol's own history."""
    id = "rs_rotation"
    name = "Relative-Strength Rotation"
    description = ("Cross-symbol momentum rotation: buy while a symbol "
                    "ranks in the top-K of the universe by lookback "
                    "return, exit once it drops out of favor.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "4h", choices=TIMEFRAMES),
            ParamSpec("lookback_period", "Momentum lookback (bars)", "int", 50, min=5, max=300),
            ParamSpec("top_k", "Enter if rank <=", "int", 2, min=1, max=8),
            ParamSpec("exit_k", "Exit if rank >", "int", 2, min=1, max=8),
            ParamSpec("require_positive_momentum", "Require own momentum > 0", "bool", False),
        ]

    def required_history(self) -> int:
        return self.params["lookback_period"] + 5

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return df  # rs_rank / rs_momentum already merged in by the caller

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        row = df.iloc[i]
        rank, mom = row.get("rs_rank"), row.get("rs_momentum")
        close = float(row["close"])
        if pd.isna(rank) or pd.isna(mom):
            return self.hold(symbol, "rank warming up", price=close)
        rank = int(rank)
        state = f"close={close:.6g} rank={rank}/8 momentum={mom:.4f}"

        if position is None:
            if rank <= p["top_k"] and (not p["require_positive_momentum"] or mom > 0):
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"entered top-{p['top_k']} by relative strength. {state}",
                              price=close)
            return self.hold(symbol, f"not a leader. {state}", price=close)

        if rank > p["exit_k"]:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"rank fell below exit threshold {p['exit_k']}. {state}",
                          price=close)
        return self.hold(symbol, f"still a leader, holding. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def build_universe_frame(dfs: dict, lookback: int):
    """Cross-sectional momentum + rank, indexed by open_time. rank 1 =
    strongest lookback-period return among the 8 symbols at that candle."""
    closes = pd.DataFrame({sym: df.set_index("open_time")["close"] for sym, df in dfs.items()})
    closes = closes.sort_index()
    mom = closes / closes.shift(lookback) - 1
    rank = mom.rank(axis=1, ascending=False, method="min")
    return mom, rank


def with_universe_columns(dfs: dict, mom: pd.DataFrame, rank: pd.DataFrame) -> dict:
    out = {}
    for sym, df in dfs.items():
        d = df.copy()
        d["rs_momentum"] = d["open_time"].map(mom[sym])
        d["rs_rank"] = d["open_time"].map(rank[sym])
        out[sym] = d
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = RelativeStrengthRotationStrategy(params)
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym, df in dfs.items():
        result = run_candle_backtest(strategy, risk, df, cfg, symbol=sym)
        window_trades = [t for t in result.trades if start_ms <= t["opened_at"] < end_ms]
        all_trades.extend(window_trades)
        eq = result.equity
        in_win = [(ts, v) for ts, v in zip(eq.index, eq.values) if start_ms <= ts < end_ms]
        ret = (in_win[-1][1] / in_win[0][1] - 1) * 100 if len(in_win) >= 2 else 0.0
        rets.append(ret)
        sw = [t for t in window_trades if t["pnl"] > 0]
        sl = [t for t in window_trades if t["pnl"] <= 0]
        gw = sum(t["pnl"] for t in sw)
        gl = -sum(t["pnl"] for t in sl)
        spf = gw / gl if gl > 1e-9 else (float("inf") if gw > 0 else None)
        sym_stats[sym] = {"pf": round(spf, 3) if spf not in (None, float("inf")) else spf,
                           "trades": len(window_trades), "ret_pct": round(ret, 4)}

    wins = [t for t in all_trades if t["pnl"] > 0]
    losses = [t for t in all_trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = gross_win / gross_loss if gross_loss > 1e-9 else (float("inf") if gross_win > 0 else 0.0)
    win_pct = len(wins) / len(all_trades) * 100 if all_trades else 0.0
    avg_ret = sum(rets) / len(rets) if rets else 0.0
    out = {"pf": round(pf, 3) if pf != float("inf") else None, "win_pct": round(win_pct, 2),
           "trades": len(all_trades), "avg_ret_pct": round(avg_ret, 4)}
    if per_symbol:
        out["per_symbol"] = sym_stats
    return out


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    risk = RiskConfig()

    results = []
    tf, buffer_days = "4h", 25  # covers max lookback (90 bars * 4h = 15d) + safety margin
    print(f"\n=== timeframe {tf} ===")
    print("Fetching train window...")
    train_raw = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
    print("Fetching test window...")
    test_raw = await fetch_all(TEST_START, TEST_END, tf, buffer_days)

    lookbacks = [20, 50, 90]
    topk_exitk_pairs = [(2, 2), (2, 4), (3, 3), (3, 5)]
    for lookback in lookbacks:
        train_mom, train_rank = build_universe_frame(train_raw, lookback)
        test_mom, test_rank = build_universe_frame(test_raw, lookback)
        train_dfs = with_universe_columns(train_raw, train_mom, train_rank)
        test_dfs = with_universe_columns(test_raw, test_mom, test_rank)
        for top_k, exit_k in topk_exitk_pairs:
            for require_pos in (False, True):
                params = {"timeframe": tf, "lookback_period": lookback, "top_k": top_k,
                          "exit_k": exit_k, "require_positive_momentum": require_pos}
                train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
                test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
                label = (f"{tf} rs_rotation(lb={lookback},top={top_k},exit={exit_k},"
                        f"pos_mom={require_pos})")
                results.append({"label": label, "params": params, "train": train_m, "test": test_m})
                print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                      f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                      f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                      f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/3b82e44f-332d-50bd-b43d-2193701b62f1/scratchpad/rs_rotation_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
