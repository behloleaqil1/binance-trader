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

**No robust, generalizing edge has been found yet in the candle-strategy
families, across 4 sessions and ~62 configs.** Every trend_momentum /
mean_reversion / grid combo tested so far is either net-negative or only
clears the OOS bar by luck/small-sample noise. Honest baseline: simple
RSI/BB/EMA signals on these 8 majors appear over-arbitraged; fees turn
near-breakeven setups negative. The one asymmetric, mechanically-explicable
(not curve-fit) positive finding so far is DCA's dip-buy feature — see
below — which is already shipped as the default, not a new change.

- **trend_momentum: no edge at any grid-searched TF.** Fully grid-searched
  with train/test rigor at 4h (Run 1, 18 combos, best train PF 0.79, all
  fail) and now 1h (Run 3, 18 combos, best train PF 0.90, all fail; OOS on
  the best-train combo confirms PF 0.463/105 trades). Do not re-grid
  trend_momentum at 1h/4h without a materially different signal design
  (current ema-cross+RSI+MACD family is exhausted at these TFs).
- **mean_reversion @ 1h default params: 3-window check now CLOSES this
  question — it's regime luck, not an edge.** Run 2 found the shipped
  defaults (bb_std=2.0, rsi_oversold=30, exit_at=middle, trend_ema=0) at
  OOS PF 1.903/120 trades on the 60-0d window despite train PF 0.472, and
  flagged it as needing a 3rd window before trusting either way. Run 3
  tested a 3rd, older, non-overlapping window (240-150d ago): PF 0.441/136
  trades, all 8 symbols individually negative. 2 of 3 windows negative for
  the identical untouched param set — confirms this is not a stable edge,
  just one lucky 60-day slice. No further action; matches the broader
  no-edge finding, don't re-test this specific combo again.

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
- **trend_momentum @ 1h:** grid-searched with train/test rigor in Run 3
  (18 combos: ema pairs x rsi_buy_min x require_macd) — every combo train
  PF < 1 (best 0.90); OOS on the best-train combo confirms PF 0.463/105
  trades. See summary bullet above; no edge, don't re-test this family.
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
- **DCA strategy: methodology now defined and first pass run (Run 4).**
  `run_dca_backtest` produces zero round-trip `trades`, so the PF/trade-count
  bar doesn't apply. New metric: capital-normalized ROI
  (`unrealized_pnl/invested %`) of a variant vs. a flat fixed-schedule
  baseline, same total-invested-dollar basis (raw "avg_cost % below last
  close" is misleading here — a dip-buy variant deploys *more* total
  capital, so a cheaper unit cost doesn't by itself mean a better dollar
  outcome; always normalize by invested $ before comparing DCA variants).
  Finding: the **shipped default dip-buy feature** (`dip_enabled=True,
  dip_threshold_pct=5.0, dip_multiplier=1.5`) beats a flat schedule on ROI
  in 2 of 3 non-overlapping windows (choppy/declining regimes: +0.26pp to
  +0.61pp) and is ~neutral, not negative, in a trending-up window (-0.07pp,
  noise-level) — mechanically explicable (extra buys only land at
  locally-lower prices when a 24h dip actually occurs, so the feature is a
  no-op, not a loss, when the market doesn't dip) and consistent with why
  it's already the default. A more aggressive variant (3%/2.5×) shows a
  stronger version of the same pattern but only wins 4/8 symbols (noise
  level) in the trending-up window and requires 13–30% more deployed
  capital — not adopted; no clean win in a trending-up regime plus a real
  capital/exposure cost is enough to reject it. **No code/param change —
  validates the existing default, doesn't argue for changing it.**
- **Live real money (pre-research):** 16 trades, −$0.29 net, ~70% of loss
  was fees — empirically confirms the negative-edge finding from backtests.
  Stopped; testnet + this automated research only from here on.

---

## 2026-08-12 — Run 4

**Self-correction check:** reviewed commits since Run 3 — only `765defe`
(scanner: exclude newer USD stablecoins from the coin scanner). Doesn't
touch the fixed 8-symbol research universe, any strategy default, or any
backtest code. Nothing strategy-affecting to revert.

**Region — DCA strategy, first-ever pass, new evaluation methodology
(per Run 3's flagged next step).** `run_dca_backtest` accumulates inventory
and returns zero round-trip `trades`, so the PF>1.1/≥30-trades bar used for
candle strategies doesn't apply. Defined a DCA-specific bar: compare
**capital-normalized ROI** (`unrealized_pnl / invested`, in %) of a variant
against a flat fixed-schedule baseline (same `interval=daily,
quote_amount=$15`, `dip_enabled=False`) — NOT raw avg-cost-vs-last-close,
which is misleading here since dip-buy variants deploy *more* total
capital than the flat baseline (extra $ on qualifying dip days), so a
lower unit cost doesn't automatically mean a better dollar outcome without
normalizing by $ invested first.

Tested 3 variants (`flat` baseline, `dip_default` = shipped default
`dip_threshold_pct=5.0/dip_multiplier=1.5`, `dip_aggressive` =
`3.0/2.5`) × 8 symbols × 3 non-overlapping windows (train 2026-03-14→
2026-06-12, test 2026-06-12→2026-08-11, plus an older window
2025-12-15→2026-03-14 — same anchors as the candle-strategy research) =
72 backtests, hourly candles (for the 24h dip lookback), fees 7.5bps /
slippage 4bps.

**`dip_default` (shipped default) vs flat:** ROI beats flat on 6/8 symbols
in train (+0.26pp avg), 8/8 in the older window (+0.61pp avg), but only
2/8 in the test window (-0.07pp avg, noise-level, not a real loss).
**Verdict: mixed across windows, doesn't clear a majority-of-symbols win
in every window** — so not an unconditional edge by this research's own
anti-noise standard. But the mechanism is explicable, not curve-fit: extra
buys land at locally-lower prices only when a 24h dip actually happens, so
the feature is a no-op (not a loss) in a trending-up market and a real
help in choppy/declining ones — consistent with 2/3 windows meaningfully
positive and the 3rd being ~flat rather than negative. **This is already
the shipped default; the run validates keeping it, doesn't argue for
changing it either direction.**

**`dip_aggressive` (3%/2.5×) vs shipped default:** beats it on ROI in the
older window (8/8, +1.72pp) and train (7/8, +0.55pp), but only 4/8 (50%,
+0.09pp, noise) in the trending-up test window — not a clean win in every
regime. It also deploys **13–30% more total capital** than the default
across symbols (lower threshold triggers more often), a real
capital/liquidity requirement and larger concentration of exposure into
still-declining assets that isn't captured by the ROI-% comparison alone.
**Verdict: reject** — no clean win in a trending-up window, plus a real
added capital/exposure cost, isn't enough to justify shipping a more
aggressive default.

**$100 / $1000 translation:** `dip_default` vs flat: -$0.07/-$0.70 (test
window, the regime that matters most for "is this still working now"),
+$0.26/+$2.63 (train window), on the ROI-normalized basis. `dip_aggressive`
vs default: +$0.02/+$0.24 (test window, noise-level). No candidate found —
smallest of the three verdicts is "keep the untouched default."

**Verdict: no promising candidate this run.** No code or default-param
changes made (the one interesting finding — dip-buy helps and never
meaningfully hurts — describes the *existing* shipped default, not a
change). Nothing to revert (no strategy-affecting commits since Run 3).

**Next run should rotate to:** a genuinely new region — candle-strategy
families (mean_reversion, trend_momentum, grid) are exhausted at
15m/1h/4h; DCA now has a working methodology and first-pass result. Worth
trying: (a) a 5m timeframe sweep for mean_reversion/trend_momentum
(untested, low priority given 1m's catastrophic result, but 15m/1h/4h are
all exhausted); (b) re-testing `dip_default` vs flat on a 4th window if a
genuinely trending-up historical window can be found deliberately (the
test window here was the only trending-up one of the three tried, so its
verdict rests on a single window); (c) DCA `interval` (hourly vs
daily vs weekly) has never been varied — only `dip_*` params were, this
run assumed daily throughout.

_No CANDIDATE FOUND this run._

---

## 2026-08-11 — Run 3

**Self-correction check:** reviewed commits since Run 2 — none landed
(`abec798` was Run 2's own log commit). Nothing strategy-affecting to
revert.

**Region A — trend_momentum @ 1h, all 8 symbols, train/test grid search
(closes the gap flagged after Runs 1-2).** Same anchors as prior runs
(train 2026-03-14→2026-06-12, test 2026-06-12→2026-08-11). Grid:
`ema_fast/slow` ∈ {(10,30),(20,50),(12,26)} × `rsi_buy_min` ∈ {45,50,55} ×
`require_macd` ∈ {True,False} (18 combos, same grid shape as the Run 1
4h search).

Train screen: **all 18 combos had train PF < 1** (range 0.55–0.90; best
was ema_fast=10, ema_slow=30, rsi_buy_min=45/50 [identical result — no
train trades fell between RSI 45 and 50], require_macd=True, PF 0.901,
122 trades). OOS on the best-train combo: PF 0.463, 105 trades (real
sample, well over the 30-trade floor), ret -0.113%. **Verdict: FAIL.**
trend_momentum now has full train/test grid coverage at both 4h (Run 1)
and 1h (this run) — no in-sample edge at either timeframe with this
ema-cross+RSI+MACD signal family. Don't re-grid this strategy at these
TFs without a different signal design.

**Region B — mean_reversion @ 1h shipped-default params, THIRD
non-overlapping window (follow-up to Run 2's explicit flag).** Run 2 found
the shipped defaults (`bb_std=2.0, rsi_oversold=30, exit_at=middle,
trend_ema=0`) scored OOS PF 1.903/120 trades on the 60-0d test window
despite train PF 0.472 on the 150-60d window — flagged as regime-dependent
and *not adopted*, pending a third window. This run tested the identical,
untouched param set on window 2025-12-15→2026-03-14 (240-150d ago, doesn't
overlap either prior window): **PF 0.441, 136 trades, -$187.93 aggregate,
every one of the 8 symbols individually negative** (PF 0.20–0.85, per
symbol trade counts 14–20). **Verdict: FAIL.** 2 of 3 windows now negative
for this exact param set — the Run 2 result was regime luck on one 60-day
slice, not a stable edge. This closes the open question from Run 2: no
code/param change was made either time (it's already what ships), and this
result doesn't argue for changing it — it argues no config in this family
is worth shipping over the current default.

**$100 / $1000 translation:** both regions this run are net negative OOS.
Region A: -$0.11/-$1.13 over 60d on the best-train combo. Region B:
-$0.23/-$2.35 over the 90-day third window. No positive candidate.

**Verdict: no promising candidate this run.** No code or default-param
changes made. Nothing to revert (no strategy-affecting commits since Run 2).

**Next run should rotate to:** define a DCA-specific evaluation
methodology first (avg_cost vs. buy-hold baseline across >=2 windows —
the existing PF/trade-count bar doesn't apply, `run_dca_backtest` produces
no round-trip trades), then run it. Standard candle-strategy families
(mean_reversion, trend_momentum) are now exhausted at 15m/1h/4h and grid
at 1h — DCA and possibly a 5m timeframe sweep (untested, low priority
given 1m's catastrophic result) are the remaining unexplored regions.

_No CANDIDATE FOUND this run._

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
