# Research Log

Automated quant-research runs against real Binance historical data
(`data-api.binance.vision`, no keys). Every run uses a strict train/test
split — params are only ever chosen on the train window, then judged once
on a held-out out-of-sample (OOS) window. Bar for "promising": **OOS profit
factor > 1.1 AND >= 30 OOS trades**. Small-sample high PF is treated as
noise, not signal. Honesty over optimism — a null result is a valid result.

Universe: BTC, ETH, SOL, BNB, XRP, LINK, DOGE, ADA vs USDT. Fees 7.5bps,
slippage 4bps, $10,000 initial equity per symbol in the sim. Risk config
(stop-loss 2%, take-profit 4%, daily-loss halt, drawdown kill switch,
position caps) held at repo defaults throughout — never tuned as part of
this research.

---

## 2026-08-11 — Run 1

**Self-correction check:** reviewed the most recent strategy-affecting
commit, `5c23fd9` (mean_reversion optional trend-filter EMA). It ships
`trend_ema=0` (off) by default in `param_specs()` — it's an opt-in knob,
not a default-behavior change, so there is nothing live to re-validate or
revert. No other recent commit changes a strategy default. No reverts this
run.

**Region A — trend_momentum @ 4h, all 8 symbols**
Train window 2026-03-14→2026-06-12 (150-60d ago), test window
2026-06-12→2026-08-11 (60-0d ago). Grid: `ema_fast/slow` ∈
{(10,30),(20,50),(12,26)} × `rsi_buy_min` ∈ {45,50,55} × `require_macd` ∈
{True,False} (18 combos), aggregated across all 8 symbols per combo.

Result: **every single combo had train profit_factor < 1** (best was 0.79,
worst 0.40). The train window was choppy/ranging for this strategy on this
timeframe — there was no in-sample edge to even validate OOS. Verdict:
**FAIL, not promising.** Did not proceed to OOS (nothing passed the train
screen). Default trend_momentum params on the same OOS window: PF 1.12,
24 trades — under the 30-trade floor, inconclusive either way.

**Region B — mean_reversion @ 15m, all 8 symbols**
Same train/test windows. Grid: `bb_std` ∈ {2.0,2.5} × `rsi_oversold` ∈
{25,30} × `exit_at` ∈ {middle,upper} × `trend_ema` ∈ {0,200} (16 combos).

Top train-ranked candidate (bb_std=2.0, rsi_oversold=30, exit_at=middle,
trend_ema=200, train PF 0.88, 31 train trades) **failed OOS**: PF 0.53,
21 trades, -$8.40 aggregate P&L.

Second-ranked candidate (bb_std=2.5, rsi_oversold=30, exit_at=upper,
trend_ema=0) technically **clears the numeric bar**: OOS PF 1.24, 231
trades, 59.3% win rate, +$78.89 aggregate P&L across 8×$10,000 sim
accounts over the 60-day test window. Per-symbol OOS PF: BTC 1.23, ETH
0.92, SOL 1.41, BNB 1.51, XRP 0.72, LINK 2.09, DOGE 1.62, ADA 0.93 — 5/8
symbols positive, reasonably broad-based rather than one symbol carrying
the whole result.

**Why I'm not calling this a candidate despite passing the numeric bar:**
1. Its own **train-window PF was 0.65** — this parameter set never showed
   an edge in-sample. It was the least-bad of 16 combos that were mostly
   in-sample losers, then got lucky OOS. That's the signature of noise
   surviving a screen, not a real effect strengthening out-of-sample.
2. **Economic magnitude is negligible**: +$78.89 on $80,000 deployed
   notional over 60 days ≈ 0.10% (roughly 0.6% annualized) — smaller than
   likely model/venue slippage error, and default (untuned) mean_reversion
   params scored almost the same on the same OOS window (PF 1.02, 336
   trades) — i.e. the "improvement" from this whole 16-combo search over
   just using the shipped defaults is within noise.
3. 16-combo grid search with only the top-3 validated OOS is enough
   multiple-comparison risk to produce a >1.1 PF by chance alone.

**Verdict: no promising candidate this run.** No code or default-param
changes made. Nothing to revert from prior runs.

**$100 / $1000 account translation (for the OOS-passing but rejected
candidate, purely illustrative — not deployed):** ~$0.10 profit per $100,
~$1.00 per $1000, over 60 days, before accounting for real-world execution
slippage beyond the simulated 4bps. Not worth the operational risk of
shipping a parameter change for.

**Next run should rotate to:** mean_reversion or trend_momentum @ 1h, and
the `grid` strategy (untested so far), on a different train/test anchor
if enough time has passed.

_No CANDIDATE FOUND this run — proving nothing works is a valid result._
