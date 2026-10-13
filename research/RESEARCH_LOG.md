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

**51 runs, ~341+ configs, one standing positive finding (DCA dip-buy,
already shipped), zero adopted signal changes.** Full narrative for Run
1-42 is archived (see archive index at file end); Run 43-51 sections are
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
periodic check, not further parameter tuning.** Run 46 (2026-10-07) repeated
this check on windows shifted +2 days vs Run 42 and reproduced the identical
regime-dependent sign pattern (positive in decline/chop, negative in a
strong rally, all deltas <=0.13pp); Run 50 (2026-10-12) repeated it again on
windows shifted +5 more days — deltas shrank further (all <=0.10pp, the
smallest set yet) and the decline-window sign flipped negative for the
first time at trivial magnitude (-0.02pp, 3/8 symbols), read as the effect
wobbling at the noise floor rather than a reversal — still no reversal of
the shipped default, see Run 46/50 sections below.

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

## Run 41-42 — archived

Run 41 (same-day deferred no-op) and Run 42 (self-correction, on schedule;
memory hygiene) are archived verbatim to
`research/archive/log-2026-09-30_to_2026-10-05_run41-42.md.gz` (gzip, no
conclusions dropped — Run 42's self-correction numbers are already folded into
DISTILLED LEARNINGS above).

---

## Run 43-45 — archived

Run 43 (same-day deferred no-op), Run 44 (deferred no-op), and Run 45
(same-day deferred no-op) — all no-op deferrals ahead of the Run 46
self-correction check, no backtests run, no code changed — are archived
verbatim to `research/archive/log-2026-10-05_to_2026-10-08_run43-45.md.gz`
(gzip, no conclusions dropped — nothing in them was outside what DISTILLED
LEARNINGS already states).

---

## Run 46-49 — archived

Run 46 (self-correction, on schedule — numbers already folded into DISTILLED
LEARNINGS above) and Run 47/48/49 (same-day/next-day deferred no-ops) are
archived verbatim to
`research/archive/log-2026-10-07_to_2026-10-08_run46-49.md.gz` (gzip, no
conclusions dropped).

---

## 2026-10-12 — Run 50 (self-correction, on schedule; memory hygiene)

**Housekeeping first.** Fresh container clone had `HEAD` detached at
`4f26b0d` (Run 49's commit, matching `origin/main`) with local `main`
pinned 5 commits behind at `5fa7d2a` (Run 44) — same stale-branch-pointer
pattern as every prior run's housekeeping note (a fresh clone predates the
previous session's `git checkout main`). Fast-forwarded local `main` to
`origin/main` (`4f26b0d`) via `git checkout main && git merge --ff-only` —
clean fast-forward, no divergent commits, no work at risk. Re-verified the
Run 37 malware incident remains remediated: no `.vscode/` directory,
`public/fonts/*` all legitimate FontAwesome filenames (`fa-solid-900`,
`fa-brands-400`, `fa-regular-400`, plus `README.md` — no `-400`/`-500`
swapped fake font), no stray `eval(` anywhere under `public/`. Nothing new
to flag.

**Question.** Run 46 set the next actionable date for the standing DCA
self-correction protocol at "2026-10-09 or later" (2+ full days past its
2026-10-07 anchor). Today is 2026-10-12 — 5 days past that anchor, well
past the bar — so this run performs the genuine re-check rather than
another deferral. No concretely-scoped strategy/signal/gate axis has
reopened since Run 49; every one of them (8 strategy families, 6
signal-source categories, gates, cross-symbol constructions, sizing, exit
mechanism, cost level, symbol universe, TF range, historical era, DCA
parameter + trend-gate conditioning) remains closed with zero surviving
candidates, and the only structurally out-of-reach items (short-selling,
geo-blocked futures data) are unchanged.

**Method.** Same methodology as Run 4/14/27/32/35/36/38/40/42/46
(capital-normalized average ROI across the 8-symbol universe,
dip_enabled=True (shipped, `dip_threshold_pct=5.0`, `dip_multiplier=1.5`)
vs dip_enabled=False (control), 1h entry timeframe, 7.5bps fees/4bps
slippage). All 3 non-overlapping windows shifted forward by exactly 5 days
vs Run 46 (same window lengths — older/train 90d, test 60d): older
2026-02-14..2026-05-15, train 2026-05-15..2026-08-13, test
2026-08-13..2026-10-12 (anchor = today's close).

**Result — smallest deltas yet; one sign wobble at trivial magnitude, no
reversal.**

| window | OFF avg ROI% | ON-OFF delta (pp) | symbols beating OFF | dip-buys fired |
|---|---|---|---|---|
| older (mild uptrend) | +10.5403 | **+0.0633** | 6/8 | 21 |
| train (mild decline) | -2.5364 | **-0.0179** | 3/8 | 28 |
| test (rally, milder than Run 46) | +7.9824 | **-0.0986** | 0/8 | 14 |

The older and test windows reproduce the established sign pattern exactly
(mild positive in uptrend/chop-adjacent conditions is noisy either way, but
the test-window drag in a sustained rally is unanimous and consistent with
every prior check since Run 4). The train window is the one new wrinkle:
for the first time since Run 4, the decline-window delta went **negative**
(-0.0179pp, only 3/8 symbols beating OFF) instead of the small positive
seen in every prior check (Run 42: +0.0061pp, Run 46: +0.0509pp). The
decline itself is real (OFF avg ROI -2.5364%, comparable in magnitude to
Run 46's -3.2139%), so this isn't just "the window wasn't really a
decline." However the magnitude is the smallest of any window measured
this run and sits deep inside the established <=0.40pp noise envelope —
read together with the fact that all three deltas this run are the
smallest-magnitude set seen since the protocol began (max |delta| =
0.0986pp, vs the prior low of 0.1285pp in Run 46), the most honest reading
is that the whole ON-vs-OFF effect is shrinking toward (and occasionally
crossing) the noise floor, not that the mechanism has reversed. This is
consistent with — in fact reinforces — the standing characterization of
DCA dip-buy as "near-neutral, mechanically explicable, economically
trivial," not a dependable edge.

**$ impact:** test-window delta (the decision-relevant window) is -$0.0986
on $100 invested notional / -$0.986 on $1000 — the smallest magnitude of
any self-correction check to date, reinforcing "economically trivial."

**Decision: noise — shipped default (`dip_threshold_pct=5.0`,
`dip_multiplier=1.5`) reconfirmed, no code change.** The train-window sign
wobble is recorded honestly above but does not meet any revert bar: it is
an order of magnitude below the noise envelope and does not compound into
the test-window (decision-relevant) result.

**No code change** — pure self-correction re-check; no auto-improve
threshold was met, no revert was warranted. Full backend test suite re-run:
`cd backend && PYTHONPATH=. .venv/bin/python -m pytest` — 95 passed, 0
failed, matching every prior run's count exactly, no drift.

**Memory hygiene this run:** `RESEARCH_LOG.md` had grown to ~42.7KB (over
the ~40KB soft guideline) across 9 active run-sections (41-49), exactly as
Run 49 flagged. Archived Run 41-42 (the oldest 2 — Run 41 same-day
deferred no-op, Run 42 self-correction superseded by Run 46/50; all
conclusions already folded into DISTILLED LEARNINGS) to
`research/archive/log-2026-09-30_to_2026-10-05_run41-42.md.gz` (gzip, no
conclusions dropped). Active run-section count is now 8 (43-50); file size
reduced to ~35KB, back under the ~40KB guideline. `rotate_archive.py` run:
`decisions.jsonl` at 161 entries, still under the 250 rotation threshold,
no `.jsonl` rotation this cycle.

**Going forward:** next self-correction check due once 2+ full days of new
data have accumulated past this run's 2026-10-12 anchor, i.e. 2026-10-14 or
later; a same-day or next-day re-fire should defer as a no-op exactly as
Run 39/41/43/44/45/47/48/49 did. A fresh strategy/signal idea would need to
be mechanically distinct from every closed item in DISTILLED LEARNINGS to
be worth testing before then — none identified this run. Worth watching on
the next check: whether the shrinking-delta / sign-wobble trend observed
this run continues (would strengthen the "noise floor" read) or reverses
back to the established pattern (would just be more noise either way) —
not actionable yet either way.

**Files:** `research/experiments/dca_self_correction_run50.py` (new,
copied from Run 46's script with windows rolled forward +5 days).
`research/experiments/dca_self_correction_run50_output.json` (new, raw
per-symbol output). 1 entry appended to `research/decisions.jsonl` (161
active, no rotation triggered). `research/archive/log-2026-09-30_to_2026-10-05_run41-42.md.gz`
(new archive, Run 41-42 narrative). Active `RESEARCH_LOG.md` run-section
count is now 8 (43-50); archiving brought the file to ~35KB before this
section was appended, but this section's own narrative pushes the final
size to ~41.7KB — just over the ~40KB guideline again. The next run that
does real work should fold Run 43-45 (3 short, already-closed/deferred
sections) into an archive to bring it back under budget.

---

## 2026-10-12 — Run 51 (same-day deferred no-op)

**Housekeeping first.** Fresh container clone had `HEAD` detached at
`34c9866` (Run 50's commit, matching `origin/main`) with local `main`
pinned 6 commits behind at `5fa7d2a` (Run 44) — same stale-branch-pointer
pattern as every prior run's housekeeping note (a fresh clone predates the
previous session's `git checkout main`). This time the gap had grown to 6
commits (Run 45-50) sitting only on the detached `HEAD`, unreferenced by
any local or remote branch — worth flagging explicitly since one more
missed fast-forward could have left them orphaned for garbage collection.
Fast-forwarded local `main` to `34c9866` via `git checkout main && git
merge --ff-only` and confirmed `origin/main` already matched (no-op push,
already in sync) — clean fast-forward, no divergent commits, no work lost.
Re-verified the Run 37 malware incident remains remediated: no `.vscode/`
directory, `public/fonts/*` all legitimate FontAwesome filenames
(`fa-solid-900`, `fa-brands-400`, `fa-regular-400`, plus `README.md` — no
`-400`/`-500` swapped fake font), no stray `eval(` anywhere under
`public/`. Nothing new to flag.

**Question.** This scheduled fire lands on 2026-10-12 — the same calendar
day as Run 50's commit (`34c9866`, 2026-10-12T02:13:47Z), ~12h later. Run
50 set the next actionable date for the standing DCA self-correction
protocol at "2026-10-14 or later" (2+ full days past its own 2026-10-12
anchor). That bar is not met today. Re-running the check now would reuse
windows overlapping Run 50's by all but a few hours and reproduce its
numbers with noise-level rounding, adding no information and violating
the "never repeat a config already recorded" rule. This run defers,
exactly as Run 39/41/43/44/45/47/48/49 did at the equivalent point in
their own cycles.

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS for anything
mechanically distinct from the closed list (8 strategy families, 6
signal-source categories, 3 confirmation gates + 1 stacked combo, 2
cross-symbol constructions, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate
conditioning). None identified — the only structurally out-of-reach items
remain short-selling (architecture change, out of scope per the task's own
auto-improve boundaries) and geo-blocked futures/funding data. No new
construction proposed this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest`
— 95 passed, 0 failed, matching every prior run's count exactly, no drift.
No code, params, or shipped defaults touched.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added (would just be a duplicate-window rerun of
Run 50 with no new signal), no code changes, no candidate.

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-14 or later, per Run 50. Unchanged.

**Files:** none changed in `backend/` or `research/experiments/`.
`decisions.jsonl` unchanged (161 active). `rotate_archive.py` not run (no
new entries to rotate). `RESEARCH_LOG.md` run-section count is now 9
(43-51); file size (~44KB) is now over the ~40KB soft guideline — the next
run that does real work (the 2026-10-14 self-correction check, if the
schedule lands on or after that date) should fold Run 43-45 (3 short,
already-closed/deferred sections, as flagged since Run 50) into an archive
to bring it back under budget.

---

## 2026-10-13 — Run 52 (same-day/next-day deferred no-op; memory hygiene)

**Housekeeping first.** Fresh container clone had `HEAD` detached at
`dd6bd4b` (Run 51's commit, matching `origin/main`) with local `main`
pinned 7 commits behind at `5fa7d2a` (Run 44) — same stale-branch-pointer
pattern as every prior run's housekeeping note (a fresh clone predates the
previous session's `git checkout main`). Fast-forwarded local `main` to
`origin/main` (`dd6bd4b`) via `git checkout main && git merge --ff-only` —
clean fast-forward, no divergent commits, no work at risk. Re-verified the
Run 37 malware incident remains remediated: no `.vscode/` directory,
`public/fonts/*` all legitimate FontAwesome filenames (`fa-solid-900`,
`fa-brands-400`, `fa-regular-400`, plus `README.md` — no `-400`/`-500`
swapped fake font), no stray `eval(` anywhere under `public/`. Nothing new
to flag.

**Question.** Run 50 set the next actionable date for the standing DCA
self-correction protocol at "2026-10-14 or later" (2+ full days past its
2026-10-12 anchor). Today is 2026-10-13 — only 1 day past that anchor, so
the bar is not yet met. Re-running the check now would reuse windows
overlapping Run 50's by all but one day and reproduce its numbers with
noise-level rounding, adding no information and violating the "never
repeat a config already recorded" rule. This run defers, exactly as Run
39/41/43/44/45/47/48/49/51 did at the equivalent point in their own cycles.

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
Run 50 with no new signal), no code changes, no candidate.

**Memory hygiene this run.** `RESEARCH_LOG.md` had grown to ~45.5KB (over
the ~40KB soft guideline) across 9 active run-sections (43-51), exactly as
Run 50/51 flagged. Archived Run 43-45 (the oldest 3 — all no-op deferrals
ahead of the Run 46 self-correction check; nothing in them beyond what
DISTILLED LEARNINGS already states) to
`research/archive/log-2026-10-05_to_2026-10-08_run43-45.md.gz` (gzip, no
conclusions dropped). Active run-section count is now 7 (46-52) after this
section is appended; file size reduced to ~37KB before this section, back
under the ~40KB guideline. `rotate_archive.py` not run (no new
`decisions.jsonl` entries this cycle — still 161 active, under the 250
rotation threshold).

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-14 or later, per Run 50. Unchanged.

**Files:** `research/archive/log-2026-10-05_to_2026-10-08_run43-45.md.gz`
(new archive, Run 43-45 narrative). `research/RESEARCH_LOG.md` edited
(Run 43-45 sections removed, archive-pointer section added, this section
appended). No files changed in `backend/` or `research/experiments/`.
`decisions.jsonl` unchanged (161 active).

---

## 2026-10-13 — Run 53 (same-day deferred no-op, 2nd fire this day; memory hygiene)

**Housekeeping first.** Fresh container clone had `HEAD` detached at
`e17ac7f` (Run 52's commit, matching `origin/main`) with local `main`
pinned 8 commits behind at `5fa7d2a` (Run 44) — same stale-branch-pointer
pattern as every prior run. Rebuilt the Python venv (`.venv` was absent in
this container; `python3 -m venv .venv && .venv/bin/pip install -q -r
requirements.txt`, no behavior change, standard setup). Fast-forwarded
local `main` to `origin/main` (`e17ac7f`) via `git checkout main && git
merge --ff-only` — clean, no divergent commits. Re-verified the Run 37
malware incident remains remediated: no `.vscode/` directory,
`public/fonts/*` all legitimate FontAwesome filenames, no stray `eval(`
anywhere under `public/`. Nothing new to flag.

**Question.** This is the second scheduled fire today, ~12h after Run 52's
commit (`e17ac7f`, 2026-10-13T02:11:42Z), same calendar day. Run 50 set the
next actionable date for the DCA self-correction protocol at "2026-10-14 or
later" (2+ full days past its 2026-10-12 anchor); Run 52 already confirmed
today doesn't meet that bar. Nothing has changed since Run 52 ran 12 hours
ago — re-running the check now would reuse the same windows and reproduce
Run 50's numbers with noise-level rounding. This run defers, exactly as
Run 39/41/43/44/45/47/48/49/51/52 did at the equivalent point in their own
cycles.

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS for anything
mechanically distinct from the closed list (8 strategy families, 6
signal-source categories, 3 confirmation gates + 1 stacked combo, 2
cross-symbol constructions, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate
conditioning). None identified. No new construction proposed this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest` —
95 passed, 0 failed, matching every prior run's count exactly, no drift. No
code, params, or shipped defaults touched.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added, no code changes, no candidate.

**Memory hygiene this run.** `RESEARCH_LOG.md` had grown to ~41.3KB
(fractionally over the ~40KB soft guideline) across 7 active run-sections
(46-52). Archived Run 46 (self-correction, superseded by Run 50, numbers
already folded into DISTILLED LEARNINGS) together with Run 47-49 (trivial
same-day/next-day no-op deferrals) to
`research/archive/log-2026-10-07_to_2026-10-08_run46-49.md.gz` (gzip, no
conclusions dropped). Active run-section count is now 4 (50-53); file size
reduced to ~27KB before this section was appended. `rotate_archive.py` not
run (no new `decisions.jsonl` entries this cycle — still 161 active, under
the 250 rotation threshold).

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-14 or later, per Run 50. Unchanged.

**Files:** `research/archive/log-2026-10-07_to_2026-10-08_run46-49.md.gz`
(new archive, Run 46-49 narrative). `research/RESEARCH_LOG.md` edited (Run
46-49 sections folded into archive-pointer section, this section appended).
No files changed in `backend/` or `research/experiments/`. `decisions.jsonl`
unchanged (161 active).
