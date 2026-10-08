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
position caps) held at repo defaults throughout — never loosened.

**48 runs, ~341+ configs, one standing positive finding (DCA dip-buy,
already shipped), zero adopted signal changes.** Full narrative for Run
1-40 is archived (see archive index at file end); Run 41-48 sections are
below. The DISTILLED LEARNINGS block just below was rewritten in Run 36 to
be a compact index of *conclusions*, not a re-derivation — see
`research/decisions.jsonl` and the archived run sections for full evidence
on any closed item.

---

## DISTILLED LEARNINGS (read this first; refreshed every run)

**Headline: no robust, generalizing edge has been found in 36 runs / ~340
configs, across two disjoint historical eras (2025-2026 and 2023), two
disjoint 8-symbol universes, and every TF from 1m-1d.** Simple OHLCV
signals (price-level/band, moving-average, price-shape, volume/cross-symbol,
calendar/session-time, oscillator-divergence) on these majors are
over-arbitraged at 7.5bps fees — near-breakeven setups go negative. The one
positive, mechanically-explicable, already-shipped finding is **DCA's
dip-buy feature** — not a new adopted change. Full evidence for everything
below lives in `research/decisions.jsonl` (active + `research/archive/*.gz`)
and the archived run-section prose; this block states conclusions only.

### Closed — strategy families (do not re-test without a materially new signal)
All 8 tried are rejected at every TF swept (mostly 1h/4h, full 1m-4h sweep
for the first 3): **trend_momentum** (EMA-cross+RSI+MACD, best train PF ever
0.99 @15m); **mean_reversion** (BB+RSI, chronic "test clears/train doesn't"
regime-luck signature, reproduced on 10+ orthogonal levers since Run 16);
**grid** (range ladder — a directional bet in disguise, bag-holds through
trends, `flatten_on_stop=False` trade-PF is an accounting artifact — always
read account-level return for that mode); **Donchian breakout** (fixed
N-period channel, cleanest reject in the programme, win rates 4-38%);
**Supertrend** (ATR-adaptive trailing band, same whipsaw failure as
Donchian); **Capitulation Wick Reversal** (candlestick-shape+volume, 12/12
reject); **BB-width squeeze breakout** (volatility-contraction precondition
— produced the programme's first TEST+3rd-window double-clear while TRAIN
failed, resolved as noise via per-symbol breakdown, 3-18 trades/symbol);
**Price-vs-RSI Bullish Divergence** (oscillator-divergence, 0/8 configs
cleared both OOS bars). 1m/5m are catastrophic at any strategy (fee drag
dominates, PF 0.01-0.09 @1m). 1d starves trend_momentum/mean_reversion on
trade count; grid@1d has no economically meaningful return.

### Closed — gates / confirmation mechanisms (do not re-tune)
**ADX(14)** floor/ceiling gate (both directions tried); **relative-volume**
gate (train improves monotonically, test flat — classic overfit shape);
**MTF trend-direction gate** (4h EMA cross vetoing 1h entries, applied to
both trend_momentum and mean_reversion — closest-ever near-miss at
20/50 EMA, still failed per-symbol breakdown: lucky/unlucky single-symbol
noise, not a mechanism); **UTC session-hour BUY gate** and **day-of-week BUY
gate** (calendar/session-time category, both granularities — produced the
strongest-looking double-clears in the programme, both failed the 3rd
non-overlapping window decisively, every symbol losing in that window);
**stacked session-hour + relative-volume combo gate** (compounds regime luck
rather than filtering toward edge — do not combine any two already-closed
gates). **Generalization: a gate applied to a PF<1 entry signal just
inherits whichever regime the test window happens to be — it cannot create
edge that isn't already there on the train side.**

### Closed — cross-symbol constructions
**Momentum rotation** (rank 8 symbols by return, buy the leader — one
survivor concentrated 44/87 test trades in a single symbol, ADA, vs
different train-window leaders — not repeatable) and **pairs mean
reversion** (BTC/alt log-ratio z-score, buy the laggard — 11/42 near-misses
all had train PF<1, the cleanest "no train support" rejection in the
programme). Both closed. A true market-neutral pairs trade needs
short-selling, which this engine doesn't have (architecture change, out of
scope).

### Closed — non-signal levers (sizing, exit, cost cannot manufacture edge)
**Volatility-regime position sizing** (Run 21): train/test PF moved in
*opposite* directions in 6/6 tested pairs — sizing amplifies whichever
regime the window sampled, it doesn't reveal or create edge. **Exit
mechanism** (Run 22: time-based forced exit + tighter SL/TP, never
loosened): train PF never crossed 1 either sub-experiment — nothing to
amplify. **Fee/cost-level** (Run 23): swept 7.5bps down to a theoretical
0bps — 0/12 configs cleared both OOS bars at ANY tier, directly refuting
"fees are the bottleneck." **Generalization: no mechanism layered on a
PF<1 entry signal (size, exit timing, exit price, or cost) can manufacture
edge that isn't there.**

### Closed — scope assumptions
**Symbol universe** (Run 25): disjoint 8-symbol universe, 0/3 configs
cleared both OOS bars — not "wrong coins." **TF range** (Run 26): full
1m-1d sweep exhausted (1m catastrophic, 1d starves trade count). **Historical
era** (Run 31): 2023 disjoint window (post-crash recovery/chop, materially
different regime) — 3/3 original families decisively rejected, same "no
edge" conclusion via a different failure shape than 2025-2026. **Futures/
funding-rate data** (Run 31): confirmed geo-restricted (`fapi.binance.com`
returns "Service unavailable from a restricted location" from this
environment; `data-api.binance.vision` has no `/fapi` path) — not a code
issue, definitively unreachable from here. **Long-only / no shorting**: an
architecture change out of scope, not a param tune — the one scope
assumption left structurally untestable, not just untested.

### DCA dip-buy — fully characterized, shipped default kept
`dip_enabled=True, dip_threshold_pct=5.0, dip_multiplier=1.5` beats a flat
schedule on capital-normalized ROI in declining/choppy regimes, is
near-neutral (small negative) in a strongly-rising regime — mechanically
explicable (extra buys only land on real 24h dips, so it's a no-op or small
drag otherwise, never a big loss). Both parameters now independently
isolated and closed: **dip_multiplier magnitude** (Run 27: 1.5-2.5x, effect
<0.35pp, sign flips with regime) and **dip_threshold_pct** (Run 35: 3-10%,
same monotonic sign-flipping pattern, shipped 5.0 sits at a reasonable
middle point). **Trend-conditioned dip-buy gate** (Run 36: only widen the
buy when price is below/above its own rolling SMA(50/100/200) — the first
test conditioning the dip trigger on a second signal) is also closed: nearly
all 24h-drop dips already occur below a multi-day SMA by construction (gate
barely changes which buys fire), and deltas stay within noise of the
ungated baseline in every window. `interval=daily` beats hourly (no
benefit, more orders) and weekly (worse, small unrepresentative samples).
`dip-rebuy cap` (Run 14, capping the count of dip-multiplied buys) strictly
hurts or ties — more dip-buying in a decline lowers cost basis further, cap
only removes the buys that would've helped most. **DCA is now fully closed
on every concretely-scoped parameter axis; standing self-correction protocol
(re-check ON vs OFF on rolling-forward windows) is the only recommended
periodic check, not further parameter tuning.** Run 40 (2026-09-30) repeated
this check on windows shifted +2 days vs Run 38 and reproduced the identical
regime-dependent sign pattern (positive in decline/chop, negative in a
strong rally, all deltas <=0.17pp); Run 42 (2026-10-05) repeated it again on
windows shifted +5 more days and again reproduced the identical pattern
(deltas <=0.15pp) — still no reversal, see Run 40/42 sections below.

### Where this programme stands
Every concretely-scoped axis — 8 strategy families, 5 signal-source
categories, 3 confirmation gates (+ 1 stacked combo), 2 cross-symbol
constructions, sizing, exit mechanism, cost level, symbol universe, TF
range, historical era, and now DCA's dip-buy trend-conditioning — is closed
with zero surviving candidates. The only structurally out-of-reach items are
short-selling (architecture change) and futures/funding data (geo-blocked).
**Going forward: default to the self-correction protocol** (DCA dip-buy
ON-vs-OFF re-check on rolling-forward windows, roughly every 2+ days of new
data since the last check, per Run 31/32/35/36/38) **and the top-of-file
SELF-CORRECTION mandate** (re-validate no committed conclusion has quietly
stopped holding). A well-recorded null result remains a valid, valuable
outcome — do not invent recombinations of already-closed axes to manufacture
the appearance of progress. **Run 38 (2026-09-28) re-ran this check after a
29-day gap in the schedule (no runs fired 2026-08-30 to 2026-09-28) and
confirmed the shipped default's regime-dependent signature is unchanged; Run
40 (2026-09-30) repeated it on windows shifted +2 days and again confirmed
no reversal; Run 42 (2026-10-05) repeated it a 3rd time on windows shifted a
further +5 days and again confirmed no reversal — see Run 38/40/42 sections
below.**

**Security note (non-research, resolved, handed off — see Run 39):** Run
37's commit (2026-08-30) was made to smuggle in a disguised
crypto-stealer C2 loader (`public/fonts/fa-solid-500.woff2`, a fake font)
plus a VS Code `tasks.json` auto-run-on-folderOpen trigger, undetected for
~4 weeks until a separate commit (`67b2af0`, 2026-09-28) removed it. Fully
remediated as of Run 38/39; re-verified clean in Run 39. Root cause (how a
prior invocation of this unattended routine was made to commit it) is
still unknown — flagged to the human operator via push notification in
Run 39. Nothing for this research programme to act on beyond that handoff;
noted here so it isn't lost when older run-sections are archived.

**Live real money (pre-research):** 16 trades, −$0.29 net, ~70% of loss was
fees — empirically confirmed the negative-edge finding from backtests.
Stopped; testnet + this automated research only from here on.

---

_Full run-by-run narrative for Run 1-32 (and the 2026-08-10 prior-session
human-seeded notes) is archived: `research/archive/log-2026-08-10_to_2026-08-12.md.gz`
(Run 1-5), `log-2026-08-13_to_2026-08-14.md.gz` (Run 6-9),
`log-2026-08-20_to_2026-08-21_run21-23.md.gz` (Run 21-23),
`log-2026-08-24_to_2026-08-24_run24-25.md.gz` (Run 24-25),
`log-2026-08-25_to_2026-08-25_run26.md.gz` (Run 26),
`log-2026-08-25_to_2026-08-28_run27-32.md.gz` (Run 27-32, archived in Run 38),
`log-2026-08-28_to_2026-08-30_run33-36.md.gz` (Run 33-36, archived in
Run 42 purely for size), and now `log-2026-08-30_to_2026-09-30_run37-40.md.gz`
(Run 37-40, archived in Run 46 purely for size — RESEARCH_LOG.md had grown
to ~46KB, over the ~40KB soft guideline, across 9 active run-sections. The
Run 39 security-incident handoff narrative is preserved verbatim in that
archive). Run 41-46 sections follow below (active). Every conclusion above
is folded from both the archived and active run sections — no conclusion
was dropped, only narrative repetition moved out of the active file._

---

## 2026-09-30 — Run 41 (same-day deferred no-op)

**Housekeeping first.** This container's clone again had local `main`
pinned one commit behind (`67b2af0`) with `origin/main` already at Run 40's
`820a0aa`, same stale-pointer pattern as Run 40's own housekeeping note (a
fresh container clone predates the previous session's push). Fast-forwarded
local `main` to `origin/main` (`820a0aa`) via `git checkout main && git
merge --ff-only origin/main` — clean fast-forward, no divergent commits, no
work at risk. Re-verified the Run 37 malware incident remains remediated:
no `.vscode/` directory, `public/fonts/*` all legitimate FontAwesome
filenames (no `-400`/`-500` swapped fake font), no stray `eval(` in
`public/`. Nothing new to flag.

**Question.** This scheduled fire lands on 2026-09-30 — the same calendar
date as Run 40's commit (`820a0aa`, 2026-09-30 02:11:47 UTC). Run 40 itself
set the next actionable date for the standing DCA self-correction protocol
at "2026-10-02 or later" (2+ full days past its own 2026-09-30 anchor) and
explicitly said a same-day or next-day re-fire should defer as a no-op,
exactly as Run 39 did for Run 38. That bar is not yet met today, so this
run defers rather than re-running the self-correction check on <24h of new
data (which would just reproduce Run 40's numbers with noise-level
rounding, adding no information).

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS for anything
mechanically distinct from the closed list (8 strategy families, 6
signal-source categories, 3 confirmation gates + 1 stacked combo, 2
cross-symbol constructions, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate
conditioning) that would be worth testing before the next scheduled
self-correction date. None identified — the only structurally out-of-reach
items remain short-selling (architecture change, out of scope per the
task's own auto-improve boundaries) and geo-blocked futures/funding data.
No new construction proposed this run.

**Verification.** `cd backend && .venv/bin/python -m pytest` — 95 passed, 0
failed, matching Run 37/38/40's count exactly, no drift. No code, params,
or shipped defaults touched.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added (would just be a duplicate-window rerun of
Run 40 with no new signal), no code changes, no candidate.

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-02 or later, per Run 40. Unchanged from Run 40's guidance.

**Files:** none changed in `backend/` or `research/experiments/`.
`decisions.jsonl` unchanged (158 active). `rotate_archive.py` not run (no
new entries to rotate). `RESEARCH_LOG.md` run-section count is now 9
(33-41); file size (~53KB) is further over the ~40KB soft guideline with 9
active sections — still under the ~15-run archival floor, but the next run
that does real work should fold Run 33-36 (the oldest, already-closed
strategy-family sections whose conclusions are fully captured in DISTILLED
LEARNINGS) into a new `research/archive/log-2026-08-28_to_2026-09-XX.md.gz`
to bring the active file back under budget.

---

## 2026-10-05 — Run 42 (self-correction, on schedule; memory hygiene)

**Housekeeping first.** Fresh container clone, `HEAD` detached at
`refs/heads/main` pointing at `f697c2b` (Run 41's commit), already matching
`origin/main` — no stale-pointer fast-forward needed this time, just
`git checkout main`. Re-verified the Run 37 malware incident remains
remediated: no `.vscode/` directory, `public/fonts/*` all legitimate
FontAwesome filenames (`fa-solid-900`, `fa-brands-400`, `fa-regular-400` —
no `-400`/`-500` swapped fake font), no stray `eval(` anywhere under
`public/`. Nothing new to flag.

**Question.** Run 40 set the next actionable date for the standing DCA
self-correction protocol at "2026-10-02 or later" (2+ full days past its
2026-09-30 anchor). Run 41 fired the same day as Run 40 and correctly
deferred. No run fired between Run 41 (2026-09-30) and today (2026-10-05) —
a 5-day gap, the bar is well met, so this run performs the genuine re-check.
No concretely-scoped strategy/signal/gate axis has reopened since Run 41;
every one of them (8 strategy families, 6 signal-source categories, gates,
cross-symbol constructions, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate conditioning)
remains closed with zero surviving candidates, and the only structurally
out-of-reach items (short-selling, geo-blocked futures data) are unchanged.

**Method.** Same methodology as Run 4/14/27/32/35/36/38/40 (capital-
normalized average ROI across the 8-symbol universe, dip_enabled=True
(shipped, `dip_threshold_pct=5.0`, `dip_multiplier=1.5`) vs dip_enabled=False
(control), 1h entry timeframe, 7.5bps fees/4bps slippage). All 3
non-overlapping windows shifted forward by exactly 5 days vs Run 40 (same
window lengths — older/train 90d, test 60d): older
2026-02-07..2026-05-08, train 2026-05-08..2026-08-06, test
2026-08-06..2026-10-05 (anchor = today's close).

**Result — same regime-dependent signature, no reversal.**

| window | OFF avg ROI% | ON-OFF delta (pp) | symbols beating OFF | dip-buys fired |
|---|---|---|---|---|
| older (mild uptrend) | +5.8615 | **+0.0466** | 6/8 | 21 |
| train (real decline) | -3.7354 | **+0.0144** | 5/8 | 28 |
| test (strong rally) | +19.9811 | **-0.1515** | 0/8 | 13 |

Identical sign pattern to every prior check since Run 4: mild positive when
the window contains a real decline or chop, a small unanimous drag when the
window is a sustained rally (only 13 dip-buys fired across all 8 symbols in
60 days of a +20% rally). All 3 deltas are inside the established <=0.40pp
noise envelope (this run's max magnitude is 0.1515pp, between Run 38's
0.1182pp and Run 40's 0.1651pp — no trend of growing magnitude). **No
reversal, no quiet degradation of the shipped default — no git revert
warranted.**

**$ impact:** test-window delta (the decision-relevant window) is -$0.1515
on $100 invested notional / -$1.515 on $1000 — economically trivial, as
established since Run 4.

**Decision: noise — shipped default (`dip_threshold_pct=5.0`,
`dip_multiplier=1.5`) reconfirmed, no code change.**

**No code change** — pure self-correction re-check; no auto-improve
threshold was met, no revert was warranted. Full backend test suite re-run:
`cd backend && .venv/bin/python -m pytest` — 95 passed, 0 failed, matching
Run 37/38/39/40/41's count exactly, no drift.

**Memory hygiene this run:** `RESEARCH_LOG.md` had grown to ~53KB (over the
~40KB soft guideline) across 9 active run-sections (33-41), exactly as Run
41 flagged. Archived Run 33-36 (the oldest, already-closed strategy-family
sections — BB-squeeze breakout, DCA multiplier/threshold isolation, trend-
gate conditioning; all conclusions already folded into DISTILLED LEARNINGS)
to `research/archive/log-2026-08-28_to_2026-08-30_run33-36.md.gz` (gzip, no
conclusions dropped). Active run-section count is now 6 (37-42); file size
reduced to ~30KB, back under budget. `rotate_archive.py` run:
`decisions.jsonl` at 159 entries, still under the 250 rotation threshold, no
`.jsonl` rotation this cycle.

**Going forward:** next self-correction check due once 2+ full days of new
data have accumulated past this run's 2026-10-05 anchor, i.e. 2026-10-07 or
later; a same-day or next-day re-fire should defer as a no-op exactly as Run
39/41 did. A fresh strategy/signal idea would need to be mechanically
distinct from every closed item in DISTILLED LEARNINGS to be worth testing
before then — none identified this run.

**Files:** `research/experiments/dca_self_correction_run42.py` (new, copied
from Run 40's script with windows rolled forward +5 days).
`research/experiments/dca_self_correction_run42_output.json` (new, raw
per-symbol output). 1 entry appended to `research/decisions.jsonl` (159
active, no rotation triggered). `research/archive/log-2026-08-28_to_2026-08-30_run33-36.md.gz`
(new archive, Run 33-36 narrative). Active `RESEARCH_LOG.md` run-section
count is now 6 (37-42), file size ~30KB, back under the ~40KB guideline.

---

## 2026-10-05 — Run 43 (same-day deferred no-op)

**Housekeeping first.** Fresh container clone had local `main` pinned one
commit behind (`f697c2b`, Run 41) with `origin/main` already at Run 42's
`7241ded` — same stale-pointer pattern noted in Run 40/41's own
housekeeping (a fresh container clone predates the previous session's
push). Fast-forwarded local `main` to `origin/main` (`7241ded`) via `git
checkout main && git merge --ff-only`. Re-verified the Run 37 malware
incident remains remediated: no `.vscode/` directory, `public/fonts/*` all
legitimate FontAwesome filenames (`fa-solid-900`, `fa-brands-400`,
`fa-regular-400` — no `-400`/`-500` swapped fake font), no stray `eval(`
anywhere under `public/`. Nothing new to flag.

**Question.** This scheduled fire lands on 2026-10-05 — the same calendar
date as Run 42's commit (`7241ded`, 2026-10-05T02:12:32Z). Run 42 itself set
the next actionable date for the standing DCA self-correction protocol at
"2026-10-07 or later" (2+ full days past its own 2026-10-05 anchor) and
explicitly said a same-day or next-day re-fire should defer as a no-op,
exactly as Run 39/41 did. That bar is not yet met today, so this run defers
rather than re-running the self-correction check on <12h of new data (which
would just reproduce Run 42's numbers with noise-level rounding, adding no
information, and would violate the "never repeat a config already recorded"
rule).

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS for anything
mechanically distinct from the closed list (8 strategy families, 6
signal-source categories, 3 confirmation gates + 1 stacked combo, 2
cross-symbol constructions, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate
conditioning) that would be worth testing before the next scheduled
self-correction date. None identified — the only structurally out-of-reach
items remain short-selling (architecture change, out of scope per the
task's own auto-improve boundaries) and geo-blocked futures/funding data.
No new construction proposed this run.

**Verification.** `cd backend && .venv/bin/python -m pytest` — 95 passed, 0
failed, matching every prior run's count exactly, no drift. No code,
params, or shipped defaults touched.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added (would just be a duplicate-window rerun of
Run 42 with no new signal), no code changes, no candidate.

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-07 or later, per Run 42. Unchanged from Run 42's guidance.

**Files:** none changed in `backend/` or `research/experiments/`.
`decisions.jsonl` unchanged (159 active). `rotate_archive.py` not run (no
new entries to rotate). `RESEARCH_LOG.md` run-section count is now 7
(37-43); file size still comfortably under the ~40KB guideline.

---

## 2026-10-06 — Run 44 (deferred no-op)

**Housekeeping first.** Fresh container clone had local `main` pinned one
commit behind (`f697c2b`, Run 41) with `origin/main` already at Run 43's
`2611d4a`. Fast-forwarded local `main` to `origin/main` via `git checkout
main && git merge --ff-only` — clean, no divergent commits. Re-verified the
Run 37 malware incident remains remediated: no `.vscode/` directory,
`public/fonts/*` all legitimate FontAwesome filenames (`fa-solid-900`,
`fa-brands-400`, `fa-regular-400` — no `-400`/`-500` swapped fake font), no
stray `eval(` anywhere under `public/`. Nothing new to flag.

**Question.** Run 42 set the next actionable date for the standing DCA
self-correction protocol at "2026-10-07 or later" (2+ full days past its
own 2026-10-05 anchor). Today is 2026-10-06 — only 1 day past that anchor,
so the bar is not yet met. Re-running the check now would reuse windows
overlapping Run 42's by all but one day and reproduce its numbers with
noise-level rounding, adding no information and violating the "never
repeat a config already recorded" rule. This run defers, exactly as Run
39/41/43 did at the equivalent point in their own cycles.

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS for anything
mechanically distinct from the closed list (8 strategy families, 6
signal-source categories, 3 confirmation gates + 1 stacked combo, 2
cross-symbol constructions, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate
conditioning). None identified — the only structurally out-of-reach items
remain short-selling (architecture change, out of scope) and geo-blocked
futures/funding data. No new construction proposed this run.

**Verification.** `cd backend && .venv/bin/python -m pytest` — 95 passed, 0
failed, matching every prior run's count exactly, no drift. No code,
params, or shipped defaults touched.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added, no code changes, no candidate.

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-07 or later, per Run 42. Unchanged.

**Files:** none changed in `backend/` or `research/experiments/`.
`decisions.jsonl` unchanged (159 active). `rotate_archive.py` not run (no
new entries to rotate). `RESEARCH_LOG.md` run-section count is now 8
(37-44); file size still comfortably under the ~40KB guideline.

---

## 2026-10-06 — Run 45 (same-day deferred no-op)

**Housekeeping first.** Local `main` was already fast-forwarded to
`origin/main` (`5fa7d2a`, Run 44's commit) — no stale-pointer issue this
time, `git fetch`/`git status` confirmed clean and in sync. Re-verified the
Run 37 malware incident remains remediated: no `.vscode/` directory,
`public/fonts/*` contains only legitimate FontAwesome files
(`fa-solid-900.woff2`, `fa-brands-400.woff2`, `fa-regular-400.woff2` — no
`-400`/`-500` swapped fake font), no stray `eval(` anywhere under
`public/`. Nothing new to flag.

**Question.** This scheduled fire lands on 2026-10-06, ~12h after Run 44's
commit (`5fa7d2a`, 2026-10-06T02:09:37Z) — the same calendar day. Run 42
set the next actionable date for the standing DCA self-correction protocol
at "2026-10-07 or later" (2+ full days past its own 2026-10-05 anchor);
Run 44 confirmed that bar was still unmet on 2026-10-06. It remains unmet
now. Re-running the check this cycle would reuse windows overlapping Run
42's by all but one day and reproduce its numbers with noise-level
rounding — not new evidence, and would violate the "never repeat a config
already recorded" rule. This run defers, exactly as Run 39/41/43/44 did at
the equivalent point in their own cycles.

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS for anything
mechanically distinct from the closed list (8 strategy families, 6
signal-source categories, 3 confirmation gates + 1 stacked combo, 2
cross-symbol constructions, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate
conditioning). None identified — the only structurally out-of-reach items
remain short-selling (architecture change, out of scope) and geo-blocked
futures/funding data. No new construction proposed this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest -q`
— exit code 0, 95 dots printed (72 + 23, matching every prior run's count
exactly), no drift. No code, params, or shipped defaults touched.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added, no code changes, no candidate.

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-07 or later, per Run 42/44. Unchanged.

**Files:** none changed in `backend/` or `research/experiments/`.
`decisions.jsonl` unchanged (159 active). `rotate_archive.py` not run (no
new entries to rotate). `RESEARCH_LOG.md` run-section count is now 9
(37-45); file size (~43KB) is modestly over the ~40KB soft guideline but
still well under the ~15-run archival floor — the next run that does real
work (the 2026-10-07 self-correction check) should fold the oldest 1-2
already-closed sections into an archive to bring it back under budget, as
Run 42 did for Run 33-36.

---

## 2026-10-07 — Run 46 (self-correction, on schedule; memory hygiene)

**Housekeeping first.** Fresh container clone had local `main` pinned one
commit behind (`5fa7d2a`, Run 44) with `origin/main` already at Run 45's
`3abddf6`. Fast-forwarded local `main` to `origin/main` via `git checkout
main && git merge --ff-only` — clean, no divergent commits. Re-verified the
Run 37 malware incident remains remediated: no `.vscode/` directory,
`public/fonts/*` all legitimate FontAwesome filenames (`fa-solid-900`,
`fa-brands-400`, `fa-regular-400` — no `-400`/`-500` swapped fake font), no
stray `eval(` anywhere under `public/`. Nothing new to flag.

**Question.** Run 42 set the next actionable date for the standing DCA
self-correction protocol at "2026-10-07 or later" (2+ full days past its
2026-10-05 anchor). Run 43/44/45 each fired before that bar was met and
correctly deferred. Today is 2026-10-07 — the bar is exactly met, so this
run performs the genuine re-check. No concretely-scoped strategy/signal/gate
axis has reopened since Run 45; every one of them (8 strategy families, 6
signal-source categories, gates, cross-symbol constructions, sizing, exit
mechanism, cost level, symbol universe, TF range, historical era, DCA
parameter + trend-gate conditioning) remains closed with zero surviving
candidates, and the only structurally out-of-reach items (short-selling,
geo-blocked futures data) are unchanged.

**Method.** Same methodology as Run 4/14/27/32/35/36/38/40/42
(capital-normalized average ROI across the 8-symbol universe,
dip_enabled=True (shipped, `dip_threshold_pct=5.0`, `dip_multiplier=1.5`)
vs dip_enabled=False (control), 1h entry timeframe, 7.5bps fees/4bps
slippage). All 3 non-overlapping windows shifted forward by exactly 2 days
vs Run 42 (same window lengths — older/train 90d, test 60d): older
2026-02-09..2026-05-10, train 2026-05-10..2026-08-08, test
2026-08-08..2026-10-07 (anchor = today's close).

**Result — same regime-dependent signature, no reversal.**

| window | OFF avg ROI% | ON-OFF delta (pp) | symbols beating OFF | dip-buys fired |
|---|---|---|---|---|
| older (mild uptrend) | +8.5266 | **+0.0509** | 6/8 | 21 |
| train (real decline) | -3.2139 | **+0.0061** | 5/8 | 28 |
| test (strong rally) | +17.0383 | **-0.1285** | 0/8 | 13 |

Identical sign pattern to every prior check since Run 4: mild positive when
the window contains a real decline or chop, a small unanimous drag when the
window is a sustained rally (only 13 dip-buys fired across all 8 symbols in
60 days of a +17% rally). All 3 deltas are inside the established <=0.40pp
noise envelope (this run's max magnitude is 0.1285pp, the smallest test-
window drag seen since Run 38 — no trend of growing magnitude). **No
reversal, no quiet degradation of the shipped default — no git revert
warranted.**

**$ impact:** test-window delta (the decision-relevant window) is -$0.1285
on $100 invested notional / -$1.285 on $1000 — economically trivial, as
established since Run 4.

**Decision: noise — shipped default (`dip_threshold_pct=5.0`,
`dip_multiplier=1.5`) reconfirmed, no code change.**

**No code change** — pure self-correction re-check; no auto-improve
threshold was met, no revert was warranted. Full backend test suite re-run:
`cd backend && PYTHONPATH=. .venv/bin/python -m pytest -q` — 95 passed, 0
failed, matching every prior run's count exactly, no drift.

**Memory hygiene this run:** `RESEARCH_LOG.md` had grown to ~46KB (over the
~40KB soft guideline) across 9 active run-sections (37-45), as Run 45
flagged. Archived Run 37-40 (the oldest 4 of those, all deferred/no-op or
already-superseded self-correction sections — Run 37 no-op, Run 38
self-correction superseded by Run 40/42/46, Run 39 no-op+security handoff
(handoff text preserved below, not dropped), Run 40 self-correction
superseded by Run 42/46) to
`research/archive/log-2026-08-30_to_2026-09-30_run37-40.md.gz` (gzip, no
conclusions dropped — all folded into DISTILLED LEARNINGS already; the
security-incident handoff narrative is preserved verbatim in the archive
and this run's own DISTILLED LEARNINGS security note is unchanged).
Active run-section count is now 6 (41-46); file size reduced back under
the ~40KB guideline. `rotate_archive.py` run: `decisions.jsonl` at 160
entries, still under the 250 rotation threshold, no `.jsonl` rotation this
cycle.

**Going forward:** next self-correction check due once 2+ full days of new
data have accumulated past this run's 2026-10-07 anchor, i.e. 2026-10-09 or
later; a same-day or next-day re-fire should defer as a no-op exactly as
Run 39/41/43/44/45 did. A fresh strategy/signal idea would need to be
mechanically distinct from every closed item in DISTILLED LEARNINGS to be
worth testing before then — none identified this run.

**Files:** `research/experiments/dca_self_correction_run46.py` (new, copied
from Run 42's script with windows rolled forward +2 days).
`research/experiments/dca_self_correction_run46_output.json` (new, raw
per-symbol output). 1 entry appended to `research/decisions.jsonl` (160
active, no rotation triggered). `research/archive/log-2026-08-30_to_2026-09-30_run37-40.md.gz`
(new archive, Run 37-40 narrative). Active `RESEARCH_LOG.md` run-section
count is now 6 (41-46), file size back under the ~40KB guideline.

---

## 2026-10-07 — Run 47 (same-day deferred no-op)

**Housekeeping first.** Fresh container clone had local `main` pinned one
commit behind (`5fa7d2a`, Run 44) with `origin/main` already at Run 46's
`61f16ab` (detached `HEAD` was already at `61f16ab`, matching origin — only
the local `main` branch pointer was stale). Fast-forwarded local `main` to
`origin/main` via `git checkout main && git merge --ff-only` — clean, no
divergent commits. Re-verified the Run 37 malware incident remains
remediated: no `.vscode/` directory, `public/fonts/*` all legitimate
FontAwesome filenames (`fa-solid-900`, `fa-brands-400`, `fa-regular-400` —
no `-400`/`-500` swapped fake font), no stray `eval(` anywhere under
`public/`. Nothing new to flag.

**Question.** This scheduled fire lands on 2026-10-07, ~hours after Run 46's
commit (`61f16ab`, 2026-10-07T02:11:52Z) — the same calendar day. Run 46 set
the next actionable date for the standing DCA self-correction protocol at
"2026-10-09 or later" (2+ full days past its own 2026-10-07 anchor). That
bar is not met today. Re-running the check now would reuse windows
overlapping Run 46's by all but a few hours and reproduce its numbers with
noise-level rounding, adding no information and violating the "never
repeat a config already recorded" rule. This run defers, exactly as Run
39/41/43/44/45 did at the equivalent point in their own cycles.

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS for anything
mechanically distinct from the closed list (8 strategy families, 6
signal-source categories, 3 confirmation gates + 1 stacked combo, 2
cross-symbol constructions, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate
conditioning). None identified — the only structurally out-of-reach items
remain short-selling (architecture change, out of scope per the task's own
auto-improve boundaries) and geo-blocked futures/funding data. No new
construction proposed this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest` —
95 passed, 0 failed, matching every prior run's count exactly, no drift. No
code, params, or shipped defaults touched.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added (would just be a duplicate-window rerun of
Run 46 with no new signal), no code changes, no candidate.

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-09 or later, per Run 46. Unchanged.

**Files:** none changed in `backend/` or `research/experiments/`.
`decisions.jsonl` unchanged (160 active). `rotate_archive.py` not run (no
new entries to rotate). `RESEARCH_LOG.md` run-section count is now 7
(41-47); file size (~35KB) still comfortably under the ~40KB guideline.

---

## 2026-10-08 — Run 48 (same-day deferred no-op)

**Housekeeping first.** Fresh container clone had `HEAD` detached at
`e159c05` (Run 47's commit) with local `main` pinned 3 commits behind at
`5fa7d2a` (Run 44) — `origin/main` was already at `e159c05`, matching the
detached `HEAD`; only the local `main` branch pointer was stale (same
pattern as Run 40/41/43/44/46's own housekeeping notes — a fresh clone
predates the previous session's `git checkout main`). Fast-forwarded local
`main` to `e159c05` via `git checkout main && git merge --ff-only` and
pushed (`origin/main` confirmed already there, no-op push). Re-verified the
Run 37 malware incident remains remediated: no `.vscode/` directory,
`public/fonts/*` all legitimate FontAwesome filenames (`fa-solid-900`,
`fa-brands-400`, `fa-regular-400`, plus `README.md` — no `-400`/`-500`
swapped fake font), no stray `eval(` anywhere under `public/`. Nothing new
to flag.

**Question.** This scheduled fire lands on 2026-10-08, ~1 day after Run
46's commit (`61f16ab`, 2026-10-07T02:11:52Z) and the same day as Run 47's
deferral. Run 46 set the next actionable date for the standing DCA
self-correction protocol at "2026-10-09 or later" (2+ full days past its
own 2026-10-07 anchor). Today is only 1 day past that anchor — the bar is
not yet met. Re-running the check now would reuse windows overlapping Run
46's by all but one day and reproduce its numbers with noise-level
rounding, adding no information and violating the "never repeat a config
already recorded" rule. This run defers, exactly as Run 39/41/43/44/45/47
did at the equivalent point in their own cycles.

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS for anything
mechanically distinct from the closed list (8 strategy families, 6
signal-source categories, 3 confirmation gates + 1 stacked combo, 2
cross-symbol constructions, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate
conditioning). None identified — the only structurally out-of-reach items
remain short-selling (architecture change, out of scope per the task's own
auto-improve boundaries) and geo-blocked futures/funding data. No new
construction proposed this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest` —
95 passed, 0 failed, matching every prior run's count exactly, no drift. No
code, params, or shipped defaults touched.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added (would just be a duplicate-window rerun of
Run 46 with no new signal), no code changes, no candidate.

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-09 or later, per Run 46. Unchanged.

**Files:** none changed in `backend/` or `research/experiments/`.
`decisions.jsonl` unchanged (160 active). `rotate_archive.py` not run (no
new entries to rotate). `RESEARCH_LOG.md` run-section count is now 8
(41-48); file size (~37KB) still under the ~40KB guideline.
