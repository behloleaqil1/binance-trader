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

**55 runs, ~341+ configs, one standing positive finding (DCA dip-buy,
already shipped), zero adopted signal changes.** Full narrative for Run
1-49 is archived (see archive index at file end); Run 50-55 sections are
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
first time at trivial magnitude (-0.02pp, 3/8 symbols); Run 54 (2026-10-14)
repeated it a further +2 days forward — deltas stayed at the same tiny
scale (max |delta| 0.0864pp) and the decline-window sign stayed negative a
second consecutive run (-0.0168pp, 3/8 symbols), essentially matching Run
50's magnitude. Two in a row on the same side is noted for continued
tracking, but both readings are an order of magnitude inside the <=0.40pp
noise envelope — read as the effect having settled at (not reversing
through) the noise floor, not a reversal of the shipped default. See Run
46/50/54 sections below.

### Where this programme stands
Every concretely-scoped axis — 8 strategy families, 5 signal-source
categories, 3 confirmation gates (+ 1 stacked combo), 2 cross-symbol
constructions, sizing, exit mechanism, cost level, symbol universe, TF
range, historical era, and now DCA's dip-buy trend-conditioning — is closed
with zero surviving candidates. The only structurally out-of-reach items are
short-selling (architecture change) and futures/funding data (geo-blocked).
**Going forward: default to the self-correction protocol** (DCA dip-buy
ON-vs-OFF re-check on rolling-forward windows, roughly every 2+ days of new
data since the last check, per Run 31/32/35/36/38/50) **and the top-of-file
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

## Run 50-51 — archived

Run 50 (self-correction, on schedule — numbers already folded into
DISTILLED LEARNINGS above) and Run 51 (same-day deferred no-op) are
archived verbatim to
`research/archive/log-2026-10-12_to_2026-10-12_run50-51.md.gz` (gzip, no
conclusions dropped).

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

---

## 2026-10-14 — Run 54 (self-correction, on schedule)

**Housekeeping first.** Git was already on `main`, up to date with
`origin/main` at `4f27436` (Run 53's commit) — no detached-HEAD/stale-branch
issue this time. `.venv` was absent in this container; rebuilt via
`python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt`, no
behavior change. Re-verified the Run 37 malware incident remains
remediated: no `.vscode/` directory, `public/fonts/*` all legitimate
FontAwesome filenames, no stray `eval(` anywhere under `public/`. Nothing
new to flag.

**Question.** Run 50 set the next actionable date for the standing DCA
self-correction protocol at "2026-10-14 or later" (2+ full days past its
2026-10-12 anchor). Today is 2026-10-14 — the bar is exactly met, so this
run performs the genuine re-check rather than another deferral. No
concretely-scoped strategy/signal/gate axis has reopened since Run 53;
every one of them remains closed with zero surviving candidates, and the
only structurally out-of-reach items (short-selling, geo-blocked futures
data) are unchanged.

**Method.** Same methodology as Run 4/14/27/32/35/36/38/40/42/46/50
(capital-normalized average ROI across the 8-symbol universe,
dip_enabled=True (shipped, `dip_threshold_pct=5.0`, `dip_multiplier=1.5`)
vs dip_enabled=False (control), 1h entry timeframe, 7.5bps fees/4bps
slippage). All 3 non-overlapping windows shifted forward by exactly 2 days
vs Run 50 (same window lengths — older/train 90d, test 60d): older
2026-02-16..2026-05-17, train 2026-05-17..2026-08-15, test
2026-08-15..2026-10-14 (anchor = today's close).

**Result — smallest-delta set continues; second consecutive negative
train-window sign, still at the noise floor, no reversal.**

| window | OFF avg ROI% | ON-OFF delta (pp) | symbols beating OFF | dip-buys fired |
|---|---|---|---|---|
| older (mild uptrend) | +3.8441 | **+0.0605** | 6/8 | 17 |
| train (mild decline) | -1.6874 | **-0.0168** | 3/8 | 27 |
| test (mild rally, milder than Run 50) | +3.9623 | **-0.0864** | 0/8 | 15 |

The older and test windows reproduce the established sign pattern exactly
(positive-ish in uptrend/chop-adjacent conditions, unanimous drag in the
rally window — 0/8 symbols beating OFF, as in every rally window since
Run 4). The train window again went negative (-0.0168pp, only 3/8 symbols
beating OFF) — the second consecutive run with this sign, essentially
matching Run 50's -0.0179pp in both sign and magnitude. The decline itself
is real (OFF avg ROI -1.6874%, smaller in magnitude than Run 50's -2.5364%
but still a genuine decline), so two data points now sit on the same side
of zero where every check from Run 4 through Run 46 sat on the other side.
Both magnitudes remain an order of magnitude below the established
<=0.40pp noise envelope, and all 3 deltas this run are again the
smallest-magnitude set on record (max |delta| = 0.0864pp, essentially
tying Run 50's prior low of 0.0986pp) — the most honest reading remains
"the ON-vs-OFF effect is a weak, shrinking statistical tendency sitting at
the noise floor," not a mechanism reversing. Per Run 50's own
"worth watching" note, this is now two-in-a-row on the negative side for
the decline window specifically — flagged for continued tracking on the
next check, but still nowhere near a revert bar (which would require a
clear, compounding, economically meaningful reversal, not a sub-0.02pp
wobble).

**$ impact:** test-window delta (the decision-relevant window) is -$0.0864
on $100 invested notional / -$0.864 on $1000 — again among the smallest
magnitudes of any self-correction check to date, reinforcing "economically
trivial."

**Decision: noise — shipped default (`dip_threshold_pct=5.0`,
`dip_multiplier=1.5`) reconfirmed, no code change.** The train-window
negative sign (now 2 runs running) is recorded honestly above but does not
meet any revert bar: both magnitudes are far below the noise envelope and
the mechanism remains fully explicable (extra buys only fire on real
24h dips; the sign of the aggregate effect in a mild, choppy decline with
few dip triggers is inherently noisy regardless of direction).

**No code change** — pure self-correction re-check; no auto-improve
threshold was met, no revert was warranted. Full backend test suite re-run:
`cd backend && PYTHONPATH=. .venv/bin/python -m pytest` — 95 passed, 0
failed, matching every prior run's count exactly, no drift.

**Memory hygiene this run:** `RESEARCH_LOG.md` was ~29.8KB before this
section (under the ~40KB soft guideline) across 4 active run-sections
(50-53) — no archiving needed this cycle. `rotate_archive.py` run:
`decisions.jsonl` at 162 entries, still under the 250 rotation threshold,
no `.jsonl` rotation this cycle.

**Going forward:** next self-correction check due once 2+ full days of new
data have accumulated past this run's 2026-10-14 anchor, i.e. 2026-10-16 or
later; a same-day or next-day re-fire should defer as a no-op exactly as
prior same-day/next-day runs did. Specifically worth checking next time:
whether the train-window (decline) delta stays negative a third time
(would suggest the sign has genuinely settled, still trivial in magnitude)
or flips back positive (would just be more noise at the floor either way)
— not actionable yet either way. A fresh strategy/signal idea would need to
be mechanically distinct from every closed item in DISTILLED LEARNINGS to
be worth testing before then — none identified this run.

**Files:** `research/experiments/dca_self_correction_run54.py` (new,
copied from Run 50's script with windows rolled forward +2 days).
`research/experiments/dca_self_correction_run54_output.json` (new, raw
per-symbol output). 1 entry appended to `research/decisions.jsonl` (162
active, no rotation triggered).

---

## 2026-10-14 — Run 55 (same-day deferred no-op, 2nd fire this day)

**Housekeeping first.** On invocation, `HEAD` was detached at `70c7634`
(Run 54's commit) with local `main` still pinned 1 commit behind at
`4f27436` (Run 53) — matching `origin/main` exactly, i.e. Run 54's commit
had never been fast-forwarded onto `main` or pushed despite existing
locally. Fast-forwarded `main` to `70c7634` and pushed — `git push`
reported `origin/main` already up to date, confirming Run 54's commit had
in fact reached the remote and only the local branch pointer was stale
(same recurring stale-pointer pattern as every prior run's housekeeping
note; no work was at risk). Rebuilt the Python venv (absent in this fresh
container) via `python3 -m venv .venv && pip install -r requirements.txt`,
no behavior change. Re-verified the Run 37 malware incident remains
remediated: no `.vscode/` directory, `public/fonts/*` all legitimate
FontAwesome filenames (no swapped fake font), no stray `eval(` under
`public/`. Nothing new to flag.

**Question.** This is the second scheduled fire today, a few hours after
Run 54's commit (`70c7634`, 2026-10-14T02:12:12Z), same calendar day. Run
54 itself set the next actionable date for the DCA self-correction
protocol at "2026-10-16 or later" (2+ full days past its own anchor).
Today doesn't meet that bar — re-running the check now would reuse
identical windows and reproduce Run 54's numbers exactly. This run defers,
exactly as Run 39/41/43/44/45/47/48/49/51/52/53 did at the equivalent
point in their own cycles.

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS for anything
mechanically distinct from the closed list (8 strategy families, 6
signal-source categories, 3 confirmation gates + 1 stacked combo, 2
cross-symbol constructions, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate
conditioning). None identified. No new construction proposed this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest`
— 95 passed, 0 failed, matching every prior run's count exactly, no code,
params, or shipped defaults touched.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added, no code changes, no candidate.

**Memory hygiene this run.** `RESEARCH_LOG.md` was ~36.8KB before this
section (under the ~40KB soft guideline) across 5 active run-sections
(50-54) — no archiving needed this cycle. `rotate_archive.py` not run (no
new `decisions.jsonl` entries this cycle — still 162 active, under the
250 rotation threshold).

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-16 or later, per Run 54. Unchanged.

**Files:** `research/RESEARCH_LOG.md` edited (this section appended). No
files changed in `backend/` or `research/experiments/`. `decisions.jsonl`
unchanged (162 active).

---

## 2026-10-15 — Run 56 (next-day deferred no-op)

**Housekeeping first.** Fresh container clone had `HEAD` detached at
`a5d3f17` (Run 55's commit) with local `main` pinned 2 commits behind at
`4f27436` (Run 53) — matching `origin/main` exactly, i.e. Run 54 and Run
55's commits had reached the remote but the local `main` branch pointer
was stale (same recurring pattern as every prior run's housekeeping note;
no work was at risk). Fast-forwarded `main` to `a5d3f17` via `git checkout
main && git merge --ff-only` and confirmed `origin/main` already matched
(no-op push). Rebuilt the Python venv (absent in this fresh container) via
`python3 -m venv .venv && pip install -q -r requirements.txt`, no behavior
change. Re-verified the Run 37 malware incident remains remediated: no
`.vscode/` directory, `public/fonts/*` all legitimate FontAwesome filenames
(`fa-solid-900`, `fa-brands-400`, `fa-regular-400`, plus `README.md` — no
`-400`/`-500` swapped fake font), no stray `eval(` anywhere under
`public/`. Nothing new to flag.

**Question.** Today is 2026-10-15, one day past Run 54's 2026-10-14
anchor. Run 54 set the next actionable date for the standing DCA
self-correction protocol at "2026-10-16 or later" (2+ full days past its
own anchor) — that bar is not met today. Re-running the check now would
reuse windows overlapping Run 54's by all but one day and reproduce its
numbers with noise-level rounding, adding no information and violating the
"never repeat a config already recorded" rule. This run defers, exactly as
Run 39/41/43/44/45/47/48/49/51/52/53/55 did at the equivalent point in
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

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest -q`
— 95 passed (72+23 dots, exit code 0), matching every prior run's count
exactly, no drift. No code, params, or shipped defaults touched.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added (would just be a duplicate-window rerun of
Run 54 with no new signal), no code changes, no candidate.

**Memory hygiene this run.** `RESEARCH_LOG.md` was ~38.8KB before this
section (under the ~40KB soft guideline) across 6 active run-sections
(50-55); appending this section pushed it to ~42.1KB, over budget. Archived
Run 50-51 (the oldest 2 — Run 50's self-correction numbers already folded
into DISTILLED LEARNINGS, Run 51 a trivial same-day no-op) to
`research/archive/log-2026-10-12_to_2026-10-12_run50-51.md.gz` (gzip, no
conclusions dropped). Active run-section count is now 5 (52-56); file size
back down to ~32.2KB. `rotate_archive.py` not run (`decisions.jsonl` at 162
entries, unchanged, still under the 250 rotation threshold).

**Going forward:** next actionable date for the DCA self-correction check
remains 2026-10-16 or later, per Run 54. Unchanged.

**Files:** `research/archive/log-2026-10-12_to_2026-10-12_run50-51.md.gz`
(new archive, Run 50-51 narrative). `research/RESEARCH_LOG.md` edited (Run
50-51 sections folded into archive-pointer section, this section appended).
No files changed in `backend/` or `research/experiments/`. `decisions.jsonl`
unchanged (162 active).
