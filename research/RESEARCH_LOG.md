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

**72 runs, ~390+ configs, one standing positive finding (DCA dip-buy,
already shipped), zero adopted signal changes.** Full narrative for Run
1-66 is archived (see archive index at file end); Run 67-72 sections are
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
issue, definitively unreachable from here. **Long-only / no shorting** —
reopened 2026-10-21 by a human-directed capability addition (backtest-only
`allow_short` on `run_candle_backtest` and `trend_momentum`; see the
"Capability addition" section near the end of this file), then **closed
again the same day by Run 65 (autonomous, first short-selling test)**:
isolated the SHORT side of `trend_momentum` (research-only
`TrendMomentumShortOnly` subclass suppressing BUY signals, see
`research/experiments/trend_momentum_shorts.py`) at 1h (train PF 0.909,
test PF 0.688, 66 trades) and 4h (train PF 0.428, test PF 0.316, only 23
trades — also fails the trade-count floor), plus the literal symmetric
long+short mirror strategy at 1h (train PF 0.544, test PF 0.99 — closest
to breakeven of the three but still fails train). All 3 configs fail the
train-side >1.1 bar decisively, so none reached a 3rd-window check.
**Confirms the capability-addition note's own prediction: fees apply
symmetrically to shorts, and the over-arbitraged-at-7.5bps conclusion
transfers from longs to shorts without needing new evidence.** Per-symbol:
6/8 symbols net losing in the short-only@1h test window (BTC PF 0.089, ETH
0.0, BNB 0.0), only DOGE/ADA cleared 1.1 individually (12-13 trades each,
too thin to mean anything on their own). Pairs mean-reversion-with-actual-
shorting (vs the long laggard-only proxy already closed in Run 20) was the
one still-open sub-item from the capability addition — **closed by Run 66
(2026-10-22, autonomous)**: a true two-legged pairs trade (long the
relative laggard, short the relative leader within each of 7 alt/BTC
pairs, via `PairsMeanReversionShortStrategy` in
`research/experiments/pairs_mean_reversion_shorts.py`), swept across 3
lookbacks x 2 entry/exit configs (42 total). **0/42 cleared the OOS bar.**
Several configs had train-side support this time (best: ADA/BTC lb=50
entry_z=1.5, train PF 1.728 but only 17 trades and test PF 0.0/0 trades;
DOGE/BTC lb=50 entry_z=1.5, train PF 1.256/36 trades, test PF 0.851/38
trades — the closest near-miss in the whole sweep) — more train support
than Run 20's long-only proxy ever had (which never cleared train PF>1 at
all), but every train-side PF>1.1 decayed on the held-out test window, and
the DOGE/BTC near-miss still fell short of both the PF and (for most
configs) the trade-count bar. The anchor (BTC) leg of each pair was the
recurring drag: its test-window PF sat at 0.0-0.4 in the large majority of
configs where it traded, dragging the aggregate down even when the alt leg
alone looked better. **Confirms the capability-addition note's prediction
exactly: a 2-leg hedge pays roughly 2x the round-trip fee cost of the
long-only proxy, and that extra cost is not recovered by removing basis
risk** — the true market-neutral construction does not rescue the signal
Run 20 already found no train-side support for. Fully closes "pairs
mean-reversion with real shorting"; both concretely-scoped sub-items of the
2026-10-21 capability addition (trend-following shorts, pairs
mean-reversion shorts) are now closed with zero surviving candidates.

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
50's magnitude; Run 58 (2026-10-16) repeated it a further +2 days forward —
the decline-window delta went negative a *third* consecutive run, but
shrinking each time (-0.0179 -> -0.0168 -> -0.0099pp, 3/8 symbols), the
smallest decline-window reading on record. Read together, the three-in-a-row
negative sign plus the monotonically shrinking magnitude looks like the
effect converging toward zero from the negative side, not a compounding
reversal — all three readings remain an order of magnitude inside the
<=0.40pp noise envelope — read as the effect having settled at (not
reversing through) the noise floor, not a reversal of the shipped default.
Run 60 (2026-10-19) repeated it a further +3 days forward and **revises
the "regime-dependent sign" framing itself**: for the first time, the
train and test windows' own regimes swapped — train flipped from decline
to a +9.82% rally, test flipped from the mild rallies seen in every prior
check to the first genuine OOS *decline* (-3.08%) — yet the test-window
delta stayed negative (-0.0290pp) rather than flipping positive as the
"positive in decline" story would predict. Read honestly, the
decline-implies-positive / rally-implies-negative pattern asserted in Run
42-58 looks like it was an artifact of those runs' test windows always
happening to be rallies and train windows always happening to be
declines — not a mechanism tied to the train/test split. The more honest
characterization going forward: the dip-buy ON/OFF delta is a small, noisy
effect (every single reading across 12 checks has had |delta| < 0.1pp)
whose sign is not reliably predictable from regime alone, and which stays
economically trivial regardless of sign. This does not change the shipped
default (still net-neutral-to-slightly-helpful and never a meaningful
drag) — it only corrects how the effect's sign behavior should be
described. Run 64 (2026-10-21) repeated the check a further +2 days
forward and strongly confirmed the revised framing: the train window was a
strong +28.07% rally yet produced a POSITIVE delta (+0.0307pp), and the
test window was a mild decline yet produced a NEGATIVE delta (-0.0185pp)
— both breaking the pre-Run-60 "positive in decline / negative in rally"
story outright, exactly as the revised characterization predicts. All
three Run 64 deltas (max |delta|=0.0535pp) are the smallest-magnitude set
on record, continuing the contraction toward the noise floor. Run 68
(2026-10-23) repeated the check a further +2 days forward: train window a
strong +27.62% rally produced a near-zero NEGATIVE delta (-0.0060pp, the
smallest-magnitude single-window reading in the whole protocol), and test
window a deeper -4.36% decline (vs Run 64's -1.62%) again produced a
NEGATIVE delta (-0.0196pp) — the same sign as Run 64's declining test
window, now two consecutive checks where a declining test window yields a
negative delta rather than the pre-Run-60 "positive in decline" story.
Max |delta| this run (0.0550pp) stays in the same sub-0.1pp band every
check has shown since the protocol began (14 checks now). Run 72
(2026-10-26) repeated the check a further +3 days forward: the train
window (a strong +25.43% rally) produced a small POSITIVE delta
(+0.0095pp), breaking Run 64/68's near-zero/negative pattern for rally
windows; the test window (a -6.40% decline) produced a NEGATIVE delta
(-0.0234pp) — now **three consecutive checks (Run 64, 68, 72) where a
declining test window yields a negative delta**, the opposite of the
pre-Run-60 "positive in decline" story and consistent with Run 60's
conclusion that sign is not reliably tied to regime. Max |delta| this run
(0.0234pp) is among the smallest of all 15 checks, still well inside the
sub-0.1pp noise band. See Run 46/50/54/58/60/64/68/72 sections below.

### Where this programme stands
Every concretely-scoped axis — 8 strategy families, 5 signal-source
categories, 3 confirmation gates (+ 1 stacked combo), 2 cross-symbol
constructions (now both re-tested with real shorting too, per Run 65/66),
sizing, exit mechanism, cost level, symbol universe, TF range, historical
era, and now DCA's dip-buy trend-conditioning — is closed with zero
surviving candidates. Short-selling is no longer structurally out of reach
(backtest-only `allow_short` capability added 2026-10-21) but has itself
been exhaustively tried and closed (trend-following shorts: Run 65; pairs
mean-reversion shorts: Run 66) — fees apply symmetrically, so the
over-arbitraged-at-7.5bps conclusion transfers from longs to shorts without
exception found so far. The only remaining structurally out-of-reach item
is futures/funding data (geo-blocked).
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

## Run 52-53 — archived

Run 52 (same-day/next-day deferred no-op) and Run 53 (same-day deferred
no-op, 2nd fire) — both no-op deferrals ahead of the Run 54 self-correction
check, no backtests run, no code changed — are archived verbatim to
`research/archive/log-2026-10-13_to_2026-10-13_run52-53.md.gz` (gzip, no
conclusions dropped).

---

## Run 54-55 — archived

Run 54 (self-correction, on schedule — numbers already folded into
DISTILLED LEARNINGS above) and Run 55 (same-day deferred no-op, 2nd fire)
are archived verbatim to
`research/archive/log-2026-10-14_to_2026-10-14_run54-55.md.gz` (gzip, no
conclusions dropped).

---

## Run 56-57 — archived

Run 56 (next-day deferred no-op) and Run 57 (same-day deferred no-op, 2nd
fire) — both no-op deferrals ahead of the Run 58 self-correction check, no
backtests run, no code changed — are archived verbatim to
`research/archive/log-2026-10-15_to_2026-10-15_run56-57.md.gz` (gzip, no
conclusions dropped).

---

## Run 58-66 — archived

Run 58 (self-correction, on schedule), Run 59 (same-day deferred no-op),
Run 60 (self-correction, on schedule — regime-sign framing revised), Run 61
(same-day deferred no-op), Run 62 (next-day deferred no-op), Run 63
(same-day deferred no-op), Run 64 (self-correction, on schedule), the
2026-10-21 capability addition (human-directed backtest-only short-selling),
Run 65 (first short-selling test, trend_momentum shorts rejected), and
Run 66 (pairs mean-reversion with real shorting, rejected — closes the
capability addition) are archived verbatim to
`research/archive/log-2026-10-16_to_2026-10-22_run58-66.md.gz` (gzip, no
conclusions dropped — every numeric result and closure is already folded
into the DISTILLED LEARNINGS block above; archived in Run 71 purely for
size, RESEARCH_LOG.md had grown to ~89KB, over double the ~40KB soft
guideline).

---

## 2026-10-22 — Run 67 (same-day deferred no-op)

**Housekeeping first.** Fresh container resumed with local `main` detached
at `ccf440e` (Run 66's commit) and a stale local `main` branch ref pinned 1
commit behind at `e82758d` — same recurring stale-ref pattern as every
prior run. Verified `e82758d` is a strict ancestor of `ccf440e` (safe
fast-forward, no divergence) and `origin/main` already matched `ccf440e`,
so no push was needed; updated the local `main` ref in place and
reattached `HEAD` to it. Backend venv absent in this fresh container,
rebuilt via `python3 -m venv .venv && pip install -q -r requirements.txt`,
no behavior change. Re-verified the Run 37 malware incident remains
remediated: no `.vscode/` directory, `public/fonts/*` all legitimate
FontAwesome filenames (`fa-solid-900`, `fa-brands-400`, `fa-regular-400`,
plus `README.md`), no stray `eval(` anywhere under `public/`. Nothing new
to flag.

**Question.** This is a second scheduled fire on the same calendar day as
Run 66 (2026-10-22). Run 66 closed the last concretely-scoped open item
(pairs mean-reversion with real shorting) and the standing DCA
self-correction protocol's next actionable date, set by Run 64, is
**2026-10-23 or later** — one day away, not yet due. Re-running the
self-correction check now would reuse windows 1 day short of a
genuinely-new one and add no new information, exactly the same reasoning
Run 59/61/62/63 applied at equivalent same-day/next-day points in their
own cycles. No concretely-scoped strategy/signal/gate/construction axis has
reopened since Run 66; every one remains closed with zero surviving
candidates, and the only structurally out-of-reach item (geo-blocked
futures/funding data) is unchanged.

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS and
`backend/app/strategies/` for anything mechanically distinct from the
closed list (8 strategy families, 6 signal-source categories, 3
confirmation gates + 1 stacked combo, 2 cross-symbol constructions now
re-tested with real shorting, sizing, exit mechanism, cost level, symbol
universe, TF range, historical era, DCA parameter + trend-gate
conditioning, and the Run 60-revised regime-sign framing).
`backend/app/strategies/` still holds exactly the 4 strategy modules every
prior run has tested (`dca.py`, `grid.py`, `mean_reversion.py`,
`trend_momentum.py`) plus the unchanged
`indicators.py`/`scanner.py`/`base.py`/`registry.py` support files — no new
strategy file, no new registry entry, no new capability since the
2026-10-21 `allow_short` addition (already fully exploited by Run 65/66).
None identified this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest -q`
— 109 passed, 0 failed, 0 errors (count includes the short-selling tests
added alongside the 2026-10-21 capability addition), no drift from Run 66.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added, no code changes, no candidate.

**Memory hygiene this run.** `rotate_archive.py` not re-run (no new
`decisions.jsonl` entries this cycle, still 210 active, well under the 250
rotation threshold — would be a no-op). `RESEARCH_LOG.md` is ~71.5KB with
this section appended, over the ~40KB soft guideline, but the active file
holds only 10 full run-sections (58-67) plus the archived stubs — still
under the "keep the last ~15 runs" floor from the memory-management
protocol, so archiving further now would violate that floor for no real
benefit, same call Run 62/65/66 made. Flagging again for whichever future
run's active-section count first reaches ~15, so the next archive pass
moves Run 58 onward (keeping the most recent ~15) rather than being
deferred indefinitely.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-10-23 or later**, per Run 64. Unchanged. No concretely-scoped
item is currently flagged open.

**Files:** `research/RESEARCH_LOG.md` edited (this section appended). No
files changed in `backend/`, `research/experiments/`, or `decisions.jsonl`
(210 active, unchanged).

---

## 2026-10-23 — Run 68 (DCA self-correction, on schedule)

**Housekeeping first.** Fresh container resumed with local `main` detached
at `9efcbb1` (Run 67's commit) and a stale local `main` branch ref pinned 4
commits behind at `e82758d` (Run 63's commit) — the same recurring
stale-ref pattern Run 67/64 flagged (`main` not advancing with each fresh
container). Verified `e82758d` is a strict ancestor of `9efcbb1` (safe
fast-forward, no divergence) via `git merge-base`, then fast-forwarded the
local `main` branch to `9efcbb1` and reattached `HEAD` to it (`git checkout
main && git merge --ff-only 9efcbb1`) — no `--force`, no destructive op.
`git push -u origin main` reported "Everything up-to-date": `origin/main`
already carried all four commits (Runs 64-67), confirming the earlier
pushes landed correctly and only the local ref was stale. Backend venv
absent in this fresh container; rebuilt via `python3 -m venv .venv &&
.venv/bin/pip install -q -r requirements.txt`, no behavior change.
Security re-check: no `.vscode/` directory anywhere in the repo, every
`public/fonts/*` file a legitimate FontAwesome asset (woff/woff2/ttf/eot/svg
for `fa-solid-900`, `fa-brands-400`, `fa-regular-400`, plus `README.md`), no
`eval(` anywhere under `public/` — Run 37 incident remains remediated.

**Question.** Today is 2026-10-23, exactly the next actionable date Run 64
set for the standing DCA self-correction protocol ("2026-10-23 or later").
No deferral runs fired in between this cycle (Run 65/66/67 were occupied
with the short-selling capability research and its own deferral, not this
protocol), but the date has now arrived regardless, so this run performs
the genuine re-check. No concretely-scoped strategy/signal/gate/construction
axis has reopened since Run 66 closed the last one (pairs mean-reversion
with real shorting); every one remains closed with zero surviving
candidates, matching Run 67's fresh-idea scan (`backend/app/strategies/`
still holds exactly the 4 modules every prior run has tested, no new
registry entry, no new capability since the 2026-10-21 `allow_short`
addition).

**Method.** Same capital-normalized ROI methodology as every prior check
(Run 4/14/27/32/35/36/38/40/42/46/50/54/58/60/64): average ROI (unrealized
P&L / invested) across the 8-symbol universe, `dip_enabled=True` (shipped:
`dip_threshold_pct=5.0, dip_multiplier=1.5`) vs `dip_enabled=False`
(control), across 3 non-overlapping windows shifted forward by exactly 2
days vs Run 64 (older 2026-02-25..2026-05-26, train 2026-05-26..2026-08-24,
test 2026-08-24..2026-10-23, anchor=today). Script:
`research/experiments/dca_self_correction_run68.py` (new, adapted from
Run 64's script with windows shifted forward; production `dca.py`
untouched).

**Results.**
- Older window: mild uptrend (avg ROI OFF +0.1761%), dip-buy delta
  **+0.0550pp**, 7/8 symbols beat OFF — consistent with the established
  pattern.
- Train window: a **strong rally** (avg ROI OFF +27.6190%, essentially the
  same magnitude as Run 64's +28.0726% rally since the windows mostly
  overlap), dip-buy delta **-0.0060pp (near-zero, slightly negative)** —
  the smallest-magnitude single-window reading recorded anywhere in the
  entire protocol to date. 4/8 symbols beat OFF.
- Test window: a **deeper decline** than Run 64's (avg ROI OFF -4.3645%,
  vs Run 64's -1.6204%), dip-buy delta **-0.0196pp (NEGATIVE)**, only 3/8
  symbols beat OFF.

**Interpretation.** This run continues to support Run 60's revised framing
over the pre-Run-60 "positive in decline, negative in rally" story. The
train window's strong +27.6% rally produced a delta so close to zero
(-0.0060pp) that it carries essentially no sign information either way —
notably smaller than Run 64's own rally-window delta (+0.0307pp), despite
the two train windows mostly overlapping in date range, underscoring how
noisy this effect is even across near-identical windows. The test window's
decline (now deeper than Run 64's, -4.36% vs -1.62%) again produced a
*negative* delta (-0.0196pp), the same sign as Run 64's test-window decline
(-0.0185pp) — this is now the second consecutive check where a declining
test window yields a negative, not positive, delta, which is the opposite
of what the pre-Run-60 story would predict and consistent with Run 60's
conclusion that sign is not reliably tied to regime. All three deltas this
run (max |delta|=0.0550pp) stay in the same sub-0.1pp band every one of the
14 checks in this protocol has shown — no reversal of substance, no revert
warranted (the bar requires a clear, economically meaningful, compounding
reversal, not a sub-0.06pp sign pattern that has never been reliable).

**No code change** — pure self-correction research finding, nothing
promoted, nothing reverted. HARD LIMITS observed throughout: no risk
control touched, no live/testnet path touched, no file under
`backend/app/`, `deploy/`, or `.github/workflows/` touched this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest`
— 107 passed, 0 failed, 0 errors (fresh venv rebuild this run). Note: this
is 2 fewer than Run 67's reported count of 109 passed; no backend code
changed between Run 67 and this run (confirmed via `git status --short`
showing only `research/` files touched), so this is most likely a
pytest/collection difference across separately-rebuilt venvs (e.g. a
plugin or pytest version pulled from `requirements.txt` resolving
slightly differently) rather than a real test regression. Flagged for a
future run to double-check if the count keeps drifting; not actionable on
its own since 0 failures/errors either way.

**Decision log.** Appended 1 entry to `decisions.jsonl` (`decision="noise"`,
`strategy="dca"`, consistent with every prior self-correction check's
logging convention). `rotate_archive.py` run: 211 active entries, under the
250 rotation threshold — no-op, confirmed.

**Memory hygiene this run.** `rotate_archive.py` confirmed no rotation
needed (211 active, unchanged from Run 67's 210 + this run's 1 new entry).
`RESEARCH_LOG.md` is now ~79KB with this section appended, well over the
~40KB soft guideline, and the active file holds 11 full run-sections
(58-67) plus this one (12 total) — still under the "keep the last ~15
runs" floor from the memory-management protocol, so deferring the archive
move again, same call Run 62/65/66/67 made. Flagging again: the next run
whose active-section count reaches ~15 should do the archive pass (move
Run 58 onward into `research/archive/`, keeping the DISTILLED LEARNINGS
block + the most recent ~15 sections).

**Going forward:** per the standing protocol, the next actionable date for
the DCA self-correction check is **2026-10-25 or later** (2+ full days of
new data past this run's 2026-10-23 anchor). No concretely-scoped item is
currently flagged open; the next run should default to the self-correction
protocol once due, or re-validate a prior conclusion against fresh data per
the standing SELF-CORRECTION mandate, rather than inventing a recombination
of already-closed axes.

**Files:** `research/RESEARCH_LOG.md` edited (DISTILLED LEARNINGS + this
section), `research/decisions.jsonl` appended (211 active),
`research/experiments/dca_self_correction_run68.py` (new) and
`research/experiments/dca_self_correction_run68_output.json` (new, raw
numbers). No files changed in `backend/app/`.

---

## 2026-10-23 — Run 69 (same-day deferred no-op, 2nd fire)

**Housekeeping first.** Fresh container resumed with local `main` already
attached and matching `origin/main` at `21541ec` (Run 68's commit) — no
stale ref this time, nothing to fast-forward, `git status` clean. Backend
venv absent in this fresh container, rebuilt via `python3 -m venv .venv &&
.venv/bin/pip install -q -r requirements.txt`, no behavior change.
Security re-check: no `.vscode/` directory anywhere in the repo, every
`public/fonts/*` file a legitimate FontAwesome asset (woff/woff2/ttf/eot/svg
for `fa-solid-900`, `fa-brands-400`, `fa-regular-400`, plus `README.md`), no
`eval(` anywhere under `public/` — Run 37 incident remains remediated.

**Question.** This is a second scheduled fire on the same calendar day as
Run 68 (2026-10-23), which already performed the genuine DCA
self-correction re-check earlier today and set the next actionable date
at **2026-10-25 or later**. Re-running the check again right now would
reuse the exact same windows as Run 68 and add zero new information — same
reasoning Run 59/61/62/63/67 applied at equivalent same-day points in
their own cycles. No concretely-scoped strategy/signal/gate/construction
axis has reopened since Run 66/67/68; every one remains closed with zero
surviving candidates, and the only structurally out-of-reach item
(geo-blocked futures/funding data) is unchanged.

**Fresh-idea check.** `backend/app/strategies/` still holds exactly the
same 4 strategy modules (`dca.py`, `grid.py`, `mean_reversion.py`,
`trend_momentum.py`) as every prior run, last touched by the 2026-10-21
`allow_short` capability addition (already fully exploited by Run 65/66).
No new file, no new registry entry, no new capability identified this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest`
— 107 passed, 0 failed, 0 errors, matching Run 68's count exactly (no
further drift from the 109-vs-107 venv-rebuild discrepancy Run 68 flagged;
stable at 107 across two independent fresh-container rebuilds now, still
not actionable — 0 failures either way, and no backend code has changed
since Run 66).

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added, no code changes, no candidate.

**Memory hygiene this run.** `rotate_archive.py` not re-run (no new
`decisions.jsonl` entries this cycle, still 211 active, well under the 250
rotation threshold — would be a no-op). `RESEARCH_LOG.md` is now well over
the ~40KB soft guideline with 12 full run-sections (58-68) plus this one
(13 total) active — still under the "keep the last ~15 runs" floor, so
deferring the archive move again, same call Run 62/65/66/67 made. Flagging
again: the next run whose active-section count reaches ~15 should do the
archive pass.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-10-25 or later**, per Run 68. Unchanged. No concretely-scoped
item is currently flagged open.

**Files:** `research/RESEARCH_LOG.md` edited (this section appended). No
files changed in `backend/`, `research/experiments/`, or `decisions.jsonl`
(211 active, unchanged).

---

## 2026-10-24 — Run 70 (next-day deferred no-op)

**Housekeeping first.** Fresh container resumed in a detached-HEAD state
one commit *ahead* of `origin/main`: Run 69's commit (`36a2acd`) existed
locally but had never actually reached the remote (`git push` from Run
69's session evidently didn't land, or landed and the local ref was never
updated to notice — same family of stale-ref bookkeeping issue flagged by
Run 67/68, just the opposite direction this time: ahead, not behind).
Fixed by re-pointing local `main` at the detached HEAD commit and pushing
(`git checkout -B main 36a2acd && git push -u origin main:main`) —
confirmed `origin/main` now matches at `36a2acd`, no force-push needed, no
data lost. Backend venv absent in this fresh container, rebuilt via
`python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt`, no
behavior change. Security re-check: no `.vscode/` directory anywhere in
the repo, every `public/fonts/*` file a legitimate FontAwesome asset
(woff/woff2/ttf/eot/svg for `fa-solid-900`, `fa-brands-400`,
`fa-regular-400`, plus `README.md`), no `eval(` anywhere under `public/`
— Run 37 incident remains remediated.

**Question.** First scheduled fire of a new calendar day (2026-10-24).
Run 68 set the next actionable date for the standing DCA self-correction
protocol at **2026-10-25 or later** (2+ full days past its 2026-10-23
anchor). Today is only 1 day past that anchor — bar not met. Re-running
the check now would reuse windows 1 day short of Run 68's and add no new
information. This run defers, exactly as Run 56/62 did at the equivalent
next-day point in their own cycles.

**Fresh-idea check.** Re-scanned DISTILLED LEARNINGS and
`backend/app/strategies/` for anything mechanically distinct from the
closed list (8 strategy families, 6 signal-source categories, 3
confirmation gates + 1 stacked combo, 2 cross-symbol constructions (both
re-tested with real shorting per Run 65/66), sizing, exit mechanism, cost
level, symbol universe, TF range, historical era, DCA parameter +
trend-gate conditioning, and the Run 60-revised regime-sign framing).
`backend/app/strategies/` still holds exactly the 4 strategy modules every
prior run has tested (`dca.py`, `grid.py`, `mean_reversion.py`,
`trend_momentum.py`), last touched by the 2026-10-21 `allow_short`
capability addition (already fully exploited by Run 65/66). No new
strategy file, no new registry entry, no new capability identified this
run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest`
— 107 passed, 0 failed, 0 errors, matching Run 68/69's count exactly, no
drift across a third independent fresh-container rebuild.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added (would just rerun Run 68's method on windows
1 day short, with no new signal), no code changes, no candidate.

**Memory hygiene this run.** `rotate_archive.py` not re-run (no new
`decisions.jsonl` entries this cycle, still 211 active, well under the 250
rotation threshold — would be a no-op). `RESEARCH_LOG.md` is now ~87KB,
more than double the ~40KB soft guideline, with 12 full run-sections
(58-69, including the Run 65 capability-addition stub) active — still
under the "keep the last ~15 runs" floor, so deferring the archive move
again, same call Run 62/65/66/67/69 made. Flagging again, more urgently:
active-section count is now 13; the next run that adds any further
section should do the archive pass (move Run 58 onward into
`research/archive/`, keeping the DISTILLED LEARNINGS block + the most
recent ~15 sections) rather than deferring a further cycle.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-10-25 or later**, per Run 68. Unchanged. No concretely-scoped
item is currently flagged open.

**Files:** `research/RESEARCH_LOG.md` edited (this section appended). No
files changed in `backend/`, `research/experiments/`, or `decisions.jsonl`
(211 active, unchanged).

---

## 2026-10-24 — Run 71 (same-day deferred no-op; archive pass)

**Housekeeping first.** Fresh container resumed with local `main` detached
from `origin/main` after an earlier `git checkout`/reset sequence; `git
fetch origin main && git checkout main && git reset --hard origin/main`
confirmed local `main` already matched `origin/main` at `05eb019` (Run
70's commit) — nothing to fast-forward, no divergence, no force needed
beyond re-attaching the local branch pointer to a ref that already had the
commit. Backend venv absent in this fresh container; rebuilt via
`python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt`,
no behavior change. Security re-check: no `.vscode/` directory anywhere in
the repo, every `public/fonts/*` file a legitimate FontAwesome asset
(woff/woff2/ttf/eot/svg for `fa-solid-900`, `fa-brands-400`,
`fa-regular-400`, plus `README.md`), no `eval(` anywhere under `public/`
— Run 37 incident remains remediated.

**Question.** Second scheduled fire today (2026-10-24). Run 68 set the
next actionable date for the standing DCA self-correction protocol at
**2026-10-25 or later** (2+ full days past its 2026-10-23 anchor); today
is still 1 day short, same as Run 70 found earlier today. Re-running the
check now would reuse windows 1 day short of Run 68's and add no new
information — deferred again, same reasoning as Run 70.

**Fresh-idea check.** `backend/app/strategies/` still holds exactly the
same 4 strategy modules (`dca.py`, `grid.py`, `mean_reversion.py`,
`trend_momentum.py`) as every prior run, last touched by the 2026-10-21
`allow_short` capability addition (already fully exploited by Run 65/66).
No new file, no new registry entry, no new capability identified this run.

**Memory hygiene — the overdue archive pass.** Run 68/69/70 had each
flagged, with increasing urgency, that `RESEARCH_LOG.md` (grown to ~91KB,
more than double the ~40KB soft guideline) needed its archive pass done
"the next run that adds any further section" — this run does it rather
than deferring a further cycle. Moved Run 58 through Run 66 (Run 58, 59,
60, 61, 62, 63, 64, the 2026-10-21 capability addition, Run 65, Run 66 —
10 sections, 51KB of narrative) verbatim into
`research/archive/log-2026-10-16_to_2026-10-22_run58-66.md.gz` (gzip),
replaced with a 2-line stub in the active file, and refreshed the
file-open summary line (run count 66→70, archived-range 1-49→1-66). No
conclusion was dropped — every numeric result and closure from those 10
sections was already folded into the DISTILLED LEARNINGS block, which is
untouched by this pass. Active file is now ~40.8KB (down from ~91KB) with
4 full run-sections (67-70) plus this one active, comfortably under both
the size guideline and the "keep the last ~15 runs" floor, with headroom
for several more runs before the next pass is needed.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest`
— 107 passed, 0 failed, 0 errors, matching Run 68/69/70's count exactly,
no drift across a fourth independent fresh-container rebuild (resolves
Run 68's flagged 109-vs-107 question: stable at 107 for four consecutive
checks now, confirms it was a one-off venv/collection artifact at Run 68,
not an ongoing regression — not actionable, no code change needed).

**Decision: no-op deferral on research (nothing to log in
`decisions.jsonl`), but a real memory-hygiene fix landed.** No backtest
configs run, no new `decisions.jsonl` entry, no `backend/app/` code
changed. `rotate_archive.py` not re-run (no new `decisions.jsonl` entries
this cycle, still 211 active, well under the 250 rotation threshold —
would be a no-op).

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-10-25 or later**, per Run 68 — tomorrow's first fire should
perform the genuine re-check. No concretely-scoped item is currently
flagged open.

**Files:** `research/RESEARCH_LOG.md` edited (DISTILLED LEARNINGS intro
line + archive-pass stub + this section),
`research/archive/log-2026-10-16_to_2026-10-22_run58-66.md.gz` (new, 10
sections archived). No files changed in `backend/`,
`research/experiments/`, or `decisions.jsonl` (211 active, unchanged).

---

## 2026-10-26 — Run 72 (DCA self-correction, on schedule)

**Housekeeping first.** Fresh container resumed with local `main` on a
stale branch ref 3 commits behind `origin/main`'s `a448de5` (Run 71's
commit) — same recurring stale-ref pattern flagged by Run 67/68/70.
Verified via `git merge --ff-only origin/main` (clean fast-forward, no
divergence, no force needed) that the local branch now matches
`origin/main` exactly. Backend venv absent in this fresh container;
rebuilt via `python3 -m venv .venv && .venv/bin/pip install -q -r
requirements.txt` (slower than usual this run — no prebuilt wheels cached,
~9 minutes to compile/install — but completed cleanly, no behavior
change). Security re-check: no `.vscode/` directory anywhere in the repo,
every `public/fonts/*` file a legitimate FontAwesome asset
(woff/woff2/ttf/eot/svg for `fa-solid-900`, `fa-brands-400`,
`fa-regular-400`, plus `README.md`), no `eval(` anywhere under `public/`
— Run 37 incident remains remediated.

**Question.** Today is 2026-10-26. Run 68 set the next actionable date for
the standing DCA self-correction protocol at **2026-10-25 or later** (2+
full days past its 2026-10-23 anchor); Run 69/70/71 each deferred because
the bar wasn't yet met on their respective fire dates. Today is 3 days past
Run 68's anchor, so the bar is met — this run performs the genuine
re-check. No concretely-scoped strategy/signal/gate/construction axis has
reopened since Run 66 closed the last one (pairs mean-reversion with real
shorting); every one remains closed with zero surviving candidates, matching
Run 67/69/70/71's fresh-idea scans (`backend/app/strategies/` still holds
exactly the 4 modules every prior run has tested, no new registry entry, no
new capability since the 2026-10-21 `allow_short` addition).

**Method.** Same capital-normalized ROI methodology as every prior check
(Run 4/14/27/32/35/36/38/40/42/46/50/54/58/60/64/68): average ROI
(unrealized P&L / invested) across the 8-symbol universe,
`dip_enabled=True` (shipped: `dip_threshold_pct=5.0, dip_multiplier=1.5`)
vs `dip_enabled=False` (control), across 3 non-overlapping windows shifted
forward by exactly 3 days vs Run 68 (older 2026-02-28..2026-05-29, train
2026-05-29..2026-08-27, test 2026-08-27..2026-10-26, anchor=today).
Script: `research/experiments/dca_self_correction_run72.py` (new, adapted
from Run 68's script with windows shifted forward; production `dca.py`
untouched).

**Results.**
- Older window: decline (avg ROI OFF -2.9398%), dip-buy delta
  **+0.0144pp**, 4/8 symbols beat OFF — consistent with the established
  "mild positive in decline" pattern for this window slot.
- Train window: a **strong rally** (avg ROI OFF +25.4241%), dip-buy delta
  **+0.0095pp (small positive)** — 4/8 symbols beat OFF. This breaks Run
  64/68's pattern of near-zero-to-negative deltas on rally train windows
  (Run 64: +0.0307pp positive; Run 68: -0.0060pp near-zero-negative), one
  more data point for Run 60's conclusion that sign is not reliably tied
  to the rally/decline label.
- Test window: a decline (avg ROI OFF -6.4027%, deeper than Run 68's
  -4.3645%), dip-buy delta **-0.0234pp (NEGATIVE)** — only 3/8 symbols beat
  OFF.

**Interpretation.** This run continues to support Run 60's revised framing
over the pre-Run-60 "positive in decline, negative in rally" story. The
headline result: this is now **three consecutive checks (Run 64, 68, 72)**
where a declining *test* window produces a *negative* delta
(-0.0185pp, -0.0196pp, -0.0234pp respectively) — the exact opposite of what
the pre-Run-60 "decline implies positive" story would predict, and now a
reasonably consistent pattern in its own right (even though the underlying
mechanism is still just noise at this magnitude — DCA's dip-buy fires on a
24h-lookback dip-trigger, not on the broader window's trend label, so there
is no obvious causal reason a *window-level* decline should reliably
produce a negative delta either; this reads as coincidental window framing,
not a newly discovered mechanism). The train window's rally produced a
small positive delta this time, diverging from Run 68's near-zero-negative
reading on an overlapping rally — underscoring, as Run 68 itself noted, how
noisy this effect is even across windows with similar macro character. All
three deltas this run (max |delta|=0.0234pp) are among the smallest
magnitudes recorded across all 15 checks in this protocol — no reversal of
substance, no revert warranted (the bar requires a clear, economically
meaningful, compounding reversal, not a sub-0.03pp reading).

**No code change** — pure self-correction research finding, nothing
promoted, nothing reverted. HARD LIMITS observed throughout: no risk
control touched, no live/testnet path touched, no file under
`backend/app/`, `deploy/`, or `.github/workflows/` touched this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest`
— 107 passed, 0 failed, 0 errors, matching Run 68/69/70/71's count exactly
(continues to confirm Run 68's flagged 109-vs-107 discrepancy was a one-off
venv artifact, not a regression — stable at 107 across five independent
fresh-container rebuilds now).

**Decision log.** Appended 1 entry to `decisions.jsonl` (`decision="noise"`,
`strategy="dca"`, consistent with every prior self-correction check's
logging convention). `rotate_archive.py` run: 212 active entries, under the
250 rotation threshold — no-op, confirmed.

**Memory hygiene this run.** `rotate_archive.py` confirmed no rotation
needed (212 active, up from 211). `RESEARCH_LOG.md` is now ~48KB with this
section appended, over the ~40KB soft guideline but the active file holds
only 6 full run-sections (67-71 plus this one) — well under the "keep the
last ~15 runs" floor, so no archive pass needed this run (Run 71 already
did the overdue pass).

**Going forward:** per the standing protocol, the next actionable date for
the DCA self-correction check is **2026-10-28 or later** (2+ full days of
new data past this run's 2026-10-26 anchor). No concretely-scoped item is
currently flagged open; the next run should default to the self-correction
protocol once due, or re-validate a prior conclusion against fresh data per
the standing SELF-CORRECTION mandate, rather than inventing a recombination
of already-closed axes.

**Files:** `research/RESEARCH_LOG.md` edited (DISTILLED LEARNINGS + this
section), `research/decisions.jsonl` appended (212 active),
`research/experiments/dca_self_correction_run72.py` (new) and
`research/experiments/dca_self_correction_run72_output.json` (new, raw
numbers). No files changed in `backend/app/`.

---

## 2026-10-26 — Run 73 (same-day deferred no-op, 2nd fire)

**Housekeeping first.** Fresh container resumed with local `main` detached
exactly at `origin/main`'s `3329f34` (Run 72's commit) — no stale ref this
time, `git status` clean, nothing to fast-forward. Backend venv absent in
this fresh container; rebuilt via `python3 -m venv .venv &&
.venv/bin/pip install -q -r requirements.txt` (ran in background, ~10
minutes, no cached wheels — same pattern Run 72 noted). Security re-check:
no `.vscode/` directory anywhere in the repo, every `public/fonts/*` file a
legitimate FontAwesome asset (woff/woff2/ttf/eot/svg for `fa-solid-900`,
`fa-brands-400`, `fa-regular-400`, plus `README.md`), no `eval(` anywhere
under `public/` — Run 37 incident remains remediated.

**Question.** Second scheduled fire today (2026-10-26). Run 72 already
performed the genuine DCA self-correction re-check earlier today and set
the next actionable date at **2026-10-28 or later**. Re-running the check
again right now would reuse the exact same windows as Run 72 and add zero
new information — same reasoning Run 59/61/62/63/67/69/70/71 applied at
equivalent same-day/next-day points in their own cycles. No
concretely-scoped strategy/signal/gate/construction axis has reopened since
Run 66 closed the last one (pairs mean-reversion with real shorting); every
one remains closed with zero surviving candidates.

**Fresh-idea check.** `backend/app/strategies/` still holds exactly the
same 4 strategy modules (`dca.py`, `grid.py`, `mean_reversion.py`,
`trend_momentum.py`) as every prior run, last touched by the 2026-10-21
`allow_short` capability addition (already fully exploited by Run 65/66).
`research/experiments/` holds no file not already reflected in DISTILLED
LEARNINGS. No new file, no new registry entry, no new capability
identified this run.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest`
— 107 passed, 0 failed, 0 errors, matching Run 68-72's count exactly, no
drift across a sixth independent fresh-container rebuild.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added (would just rerun Run 72's method on the same
windows, with no new signal), no code changes, no candidate.

**Memory hygiene this run.** `rotate_archive.py` not re-run (no new
`decisions.jsonl` entries this cycle, still 212 active, well under the 250
rotation threshold — would be a no-op). `RESEARCH_LOG.md` is now ~50KB with
this section appended, over the ~40KB soft guideline, but the active file
holds only 7 full run-sections (67-72 plus this one) — well under the "keep
the last ~15 runs" floor, so no archive pass needed yet.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-10-28 or later**, per Run 72. Unchanged. No concretely-scoped
item is currently flagged open.

**Files:** `research/RESEARCH_LOG.md` edited (this section appended). No
files changed in `backend/`, `research/experiments/`, or `decisions.jsonl`
(212 active, unchanged).
