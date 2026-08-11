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

## DISTILLED LEARNINGS (read this first; refreshed every run)

**No robust, generalizing edge has been found yet, across 2 sessions and
~40 configs.** Every strategy/timeframe combo tested so far is either
net-negative or only clears the OOS bar by luck/small-sample noise. Honest
baseline: simple RSI/BB/EMA signals on these 8 majors appear
over-arbitraged; fees turn near-breakeven setups negative.

- **1m: catastrophic, any strategy.** −34% to −42%, PF 0.01–0.09. Over-trades
  (~200+ trades/coin), fee drag (0.15% round-trip) dominates. Never retest 1m.
- **Timeframe generally: higher TF = less fee drag, not more edge.** Return
  ordering 1m ≪ 15m < 1h ≈ 4h, but none of mean_reversion/trend_momentum have
  shown a *stable* in-sample (train) edge at any TF 15m–4h — see below.
- **mean_reversion @ 15m:** default params ~breakeven OOS (PF 1.02). A
  16-combo grid's best OOS survivor (bb_std=2.5, rsi_os=30, exit=upper,
  trend_ema=0) hit OOS PF 1.24/231 trades but had **train PF 0.65** — didn't
  show an edge in-sample, just got lucky OOS. Rejected as noise (Run 1).
- **mean_reversion @ 1h:** 24-combo grid (bb_std×rsi_oversold×exit_at×
  trend_ema) — **22/24 combos have train PF < 1**; no bb_std/rsi setting
  shows an in-sample edge at this TF. The 2 combos with train PF > 1 only
  had 3–6 train trades (trend_ema=200 filter starves entries at 1h) — too
  small to trust, and OOS confirmed (0–4 trades). Shipped defaults happen to
  score OOS PF 1.9/120 trades on the current test window despite **train PF
  0.472** — flagged as regime-dependent, not adopted, needs a 3rd window
  before it means anything (Run 2).
- **trend_momentum @ 4h:** 18-combo grid (ema pairs × rsi_buy_min ×
  require_macd) — **every combo had train PF < 1** (best 0.79) on a choppy
  train window; no in-sample edge to even validate OOS (Run 1).
- **trend_momentum @ 1h:** only ever tested as a single default config
  (PF 0.82, 30 trades, -3.6%, no train/test split) — near-breakeven but
  negative. Not yet grid-searched with proper train/test rigor — do that
  next.
- **grid strategy:** profits from range oscillation in-sample but is a
  **directional bet in disguise** — bag-holds through downtrends. Confirmed
  twice now: informally at 15m/90d (−20% net, founding session) and
  rigorously at 1h with train/test split (best train PF 1.51 → OOS PF 0.66,
  **every** train-ranked config among 8 collapsed OOS, Run 2). Do not
  grid-search this strategy again without first finding a *range-detection*
  filter (e.g. only run it when ADX/volatility says "ranging") — parameter
  tuning alone (range width, level count, flatten-on-stop) cannot fix a
  strategy whose core risk is directional exposure.
- **mean_reversion trend_ema filter (opt-in, default off):** buy-the-dip
  only in uptrends. Near-breakeven at 1h with trend_ema=200 in the founding
  session (11 trades) and confirmed still tiny-sample (3–6 trades) in Run 2's
  grid. Kept in the codebase as a principled downside-reduction knob, not a
  proven edge. Do not flip its default on without a large-sample OOS pass.
- **DCA strategy: fully untested.** Next candidate for a research region.
- **Live real money (pre-research):** 16 trades, −$0.29 net, ~70% of loss
  was fees — empirically confirms the negative-edge finding from backtests.
  Stopped; testnet + this automated research only from here on.

---

## 2026-08-11 — Run 2

**Self-correction check:** no strategy-affecting commits landed since Run 1
(`5c23fd9` mean_reversion trend-filter is still the most recent, already
re-validated last run; still opt-in/off by default). Nothing to revert.

**Region A — mean_reversion @ 1h, all 8 symbols.** Same train/test anchors as
Run 1 (train 2026-03-14→2026-06-12, test 2026-06-12→2026-08-11). Grid:
`bb_std` ∈ {2.0,2.5,3.0} × `rsi_oversold` ∈ {25,30} × `exit_at` ∈
{middle,upper} × `trend_ema` ∈ {0,200} (24 combos).

Train screen: 22/24 combos had train PF < 1 (`trend_ema=0` variants ranged
0.05–0.60 across bb_std/rsi settings — 1h mean_reversion is not profitable
in-sample at any bb_std/rsi setting tested). The only two combos with train
PF > 1 both used `trend_ema=200`, which at 1h restricts entries to 3–6
train trades total across all 8 symbols — too few to mean anything. OOS on
the top 3: PF 0.0/0/trades, PF 1.105/4 trades, PF 0.961/4 trades — none
clear the 30-trade floor. **Verdict: FAIL**, no candidate from the grid.

Notable side-finding while running the reference baseline: the **shipped
default params** (`bb_std=2.0, rsi_oversold=30, exit_at=middle,
trend_ema=0` — not selected by this search, just the repo default) scored
OOS PF **1.903, 120 trades, +$118.36 on $80k notional (+0.148%, ~$0.15 per
$100 / $1.48 per $1000 over 60d)** on the same held-out window — numerically
clears the anti-noise bar (real sample size this time, not small-N luck).
**Not treated as a candidate or acted on**, because this identical param
combo scored **train PF 0.472** in the grid above — it would have been
rejected by the very screen used to pick candidates. It only "works" on
this specific 60-day slice; that is the signature of regime dependence, not
a discovered edge. No code or param change — it's already what ships.
Logged so a future run can re-check it against a **third, non-overlapping
window**; if it holds up there too it becomes more credible, not less.

**Region B — grid strategy @ 1h, all 8 symbols, proper train/test (first
time — prior grid tests were single-window, no split).** Grid:
`auto_range_pct` ∈ {6,10} × `levels` ∈ {8,13} × `flatten_on_stop` ∈
{True,False} (8 combos, `stop_outside_range=True` always).

Every train-ranked config collapsed OOS: best train PF 1.506 (190 trades,
+$130) → OOS PF 0.655 (140 trades, **-$147**); 2nd 1.421→0.639 (-$85); 3rd
1.169→0.647 (-$109). **Verdict: FAIL** across the board — this directly
confirms, with a rigorous split this time, the founding session's informal
finding that grid's in-sample oscillation profit is a directional/regime
bet, not a generalizing edge. `flatten_on_stop=False` variants weren't even
worth OOS-checking: all had 0 gross losses recorded in-sample terms that
collapse to `pf=None`/near-zero once a losing streak actually closes a lot
(inventory accumulates as unrealized loss without flattening, masking risk
in-sample).

**$100 / $1000 translation:** best OOS result across both regions this run
is the default-baseline observation above (+$0.15 / +$1.48 over 60d, not
acted on). Every actively-searched grid combo (both regions) was flat or
negative OOS.

**Verdict: no promising candidate this run.** No code or default-param
changes made.

**Next run should rotate to:** trend_momentum @ 1h with the same
train/test grid-search rigor (only ever tested as a single default config
at 1h so far, not searched); or the DCA strategy (fully untested so far in
this research). Also worth a rolling 3rd-window re-check of the mean_reversion
1h default-params side-finding above before it's fully dismissed.

_No CANDIDATE FOUND this run._

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

---

## 2026-08-10 — Prior session findings (human-seeded, for the agent's memory)

Configs already tested in the founding live+backtest session — **do not re-test these**:
- **1m any strategy**: catastrophic (−34% to −42%, PF 0.01–0.09) — fee drag from over-trading. Avoid 1m entirely.
- **Timeframe sweep** (mean_reversion/trend_momentum): 1m −34%/−42%, 15m −8%/−22%, 1h −5.8%/−3.6%, 4h −3.9%/−5.4%. Higher TF cuts fee drag hugely but none reach profit. 1h is the least-bad base.
- **mean_reversion trend_ema=200 @ 1h**: near-breakeven (−0.8%) but tiny sample (~11 trades) — filter adopted as principled downside reduction, not proven edge.
- **grid ±12%/13 levels @ 15m**: oscillation engine profits per-cycle but bag-holds in downtrends → −20% net over 90d (−9.5% even with range-exit stop). Directional bet, not signal edge; also needs $40+ capital.
- **Live real-money** (1m volatile scanner): 16 trades, −$0.29 net, ~70% of loss was fees. Empirically confirmed negative edge. Stopped; moved to testnet + this automated research.

Structured versions of these in `research/decisions.jsonl`. Overarching prior: no robust
edge found; simple RSI/BB/EMA signals appear over-arbitraged, fees turn ~breakeven negative.
