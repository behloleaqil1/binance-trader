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

**92 runs, ~395+ configs, one standing positive finding (DCA dip-buy,
already shipped), zero adopted signal changes.** Full narrative for Run
1-88 is archived (see the archive-index paragraph and the "Run N-M —
archived" stub sections below); Run 89-92 are below in full. The
DISTILLED LEARNINGS block just below was rewritten in Run 36 to be a
compact index of *conclusions*, not a re-derivation — see
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
sub-0.1pp noise band. Run 76 (2026-10-28) repeated the check a further +2
days forward: the train window (a strong +23.84% rally) produced a small
POSITIVE delta (+0.0151pp), consistent with Run 72's sign; the test window
(a -5.26% decline) produced a NEGATIVE delta (-0.0280pp) — now **four
consecutive checks (Run 64, 68, 72, 76) where a declining test window
yields a negative delta**, continuing to support Run 60's revised framing
over the pre-Run-60 "positive in decline" story. Max |delta| this run
(0.0280pp) stays well inside the sub-0.1pp noise band every one of the 16
checks has now shown. Run 78 (2026-10-30) repeated the check a further +2
days forward: the train window (a strong +21.65% rally) produced a small
POSITIVE delta (+0.0180pp), consistent with Run 72/76's sign; the test
window (a sharp -11.63% decline) produced a NEGATIVE delta (-0.0272pp) —
now **five consecutive checks (Run 64, 68, 72, 76, 78) where a declining
test window yields a negative delta**, continuing to support Run 60's
revised framing over the pre-Run-60 "positive in decline" story. Max
|delta| this run (0.0272pp) stays well inside the sub-0.1pp noise band
every one of the 17 checks has now shown. Run 82 (2026-11-02, first fire of
the day) repeated the
check a further +3 days forward: the older window (a deep -16.09% decline,
the sharpest decline window yet sampled) produced delta +0.1016pp, 8/8
symbols favoring ON — the single largest-magnitude window reading in the
whole protocol, marginally over the prior sub-0.1pp band, but still
economically trivial (0.10% of invested capital, non-compounding since DCA
has no round-trip trades) and in the *same* direction (ON helps in
decline) the shipped default was built on, so a new high-water mark, not a
reversal; the train window (a strong +20.30% rally) produced a small
POSITIVE delta (+0.0186pp), consistent with Run 72/76/78's sign; the test
window (a -9.44% decline) produced a NEGATIVE delta (-0.0260pp) — now
**six consecutive checks (Run 64, 68, 72, 76, 78, 82) where a declining
test window yields a negative delta**, continuing to support Run 60's
revised framing over the pre-Run-60 "positive in decline" story. Run 86
(2026-11-04) repeated the check a further +2 days forward: the older
window (a deeper -21.77% decline, the sharpest decline window yet sampled,
surpassing Run 82's) produced delta **+0.1684pp**, 8/8 symbols favoring
ON — a second consecutive new high-water mark (0.1016pp -> 0.1684pp),
now clearly above the pre-Run-82 sub-0.1pp band, but still same-direction
(ON beats OFF in deep decline, via more real dip-buys — 30 fired vs 25 in
Run 82 — landing at a lower cost basis) and still economically trivial in
absolute terms (0.17% of invested capital, one-time, non-compounding); the
train window (a strong +24.32% rally) produced a small NEGATIVE delta
(-0.0143pp), *breaking* Run 72/76/78/82's small-positive-in-rally pattern
and reinforcing that sign is not reliably tied to regime even across
consecutive same-labeled windows; the test window (a -10.44% decline)
produced a NEGATIVE delta (-0.0290pp) — now **seven consecutive checks
(Run 64, 68, 72, 76, 78, 82, 86) where a declining test window yields a
negative delta**. Honest read: no reversal (the shipped mechanism's
causal story — more dip-buys land at better prices in a real decline —
still explains the one growing reading), but the older-window band is
trending upward across the last two checks and is now flagged to watch
rather than dismiss if a third consecutive run extends it further. Run 88
(2026-11-09) repeated the check a further +5 days forward and **resolves
that flag**: the older window produced a THIRD consecutive high-water
mark (+0.1850pp, vs 0.1016/0.1684 in Run 82/86), but this window's decline
(-16.15%) was shallower than Run 86's (-21.77%), ruling out "delta tracks
decline depth" as the driver — what actually tracks it in lockstep is
dip-buy count (25 -> 30 -> 31 across Run 82/86/88), the mechanism the
shipped default was already built on, and the magnitude's own growth is
decelerating (+0.0668pp then +0.0166pp), the opposite of a runaway
structural trend. Also notable: the test window's delta flipped POSITIVE
(+0.0389pp) for the first time in 8 checks, **breaking the seven-run
negative-in-decline streak** (Run 64-86) outright — further confirmation
of Run 60's point that sign is not reliably tied to regime. No reversal;
shipped default kept unchanged; the "watch the older-window trend"
flag is now closed (mechanically explained, decelerating). Run 92
(2026-11-11) repeated the check a further +2 days forward and confirmed
the Run 88 resolution directly: the older window held an **identical**
dip-buy count (31, same as Run 88) and produced a delta that was flat-to-
slightly-down (+0.1794pp vs Run 88's +0.1850pp) rather than a fourth
high-water mark — exactly what "delta tracks dip-buy count, and its growth
was decelerating" predicts when the count stops rising. The train window
(rally) produced a third consecutive small NEGATIVE delta (-0.0400pp,
after Run 86's -0.0143 and Run 88's -0.0133), now a clear break from the
earlier positive-in-rally run (72/76/78/82). The test window (decline)
produced a second consecutive POSITIVE delta (+0.0595pp, after Run 88's
+0.0389), the mirror image of the old "negative in decline" streak —
read, per Run 60, as further evidence sign is not reliably tied to
regime rather than a reversion to the pre-Run-60 story, since magnitude
stays in the same sub-0.2pp band. No reversal; shipped default kept
unchanged. Next actionable date: 2026-11-13 or later. See Run
46/50/54/58/60/64/68/72/76/78/82/86/88/92 sections (67-75 archived to
`research/archive/log-2026-10-22_to_2026-10-27_run67-75.md.gz` in Run 76,
76-80 archived to `research/archive/log-2026-10-28_to_2026-10-31_run76-80.md.gz`
in Run 87, 86-88 archived to
`research/archive/log-2026-11-04_to_2026-11-09_run86-88.md.gz` in Run 92;
Run 89-92 are below in full).

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

## Run 67-75 — archived

Run 67 (same-day deferred no-op), Run 68 (DCA self-correction, on
schedule), Run 69 (same-day deferred no-op), Run 70 (next-day deferred
no-op), Run 71 (same-day deferred no-op; archive pass archiving Run
58-66), Run 72 (DCA self-correction, on schedule), Run 73 (same-day
deferred no-op), Run 74 (next-day deferred no-op), and Run 75 (same-day
deferred no-op) are archived verbatim to
`research/archive/log-2026-10-22_to_2026-10-27_run67-75.md.gz` (gzip, no
conclusions dropped — every numeric result and closure is already folded
into the DISTILLED LEARNINGS block above; archived in Run 76 purely for
size, RESEARCH_LOG.md had grown to ~61.5KB, over the ~40KB soft guideline).

---


## Run 76-80 — archived

Run 76 (DCA self-correction, on schedule), Run 77 (same-day deferred
no-op, 2nd fire), Run 78 (DCA self-correction, on schedule), Run 79
(same-day deferred no-op), and Run 80 (same-day deferred no-op, 3rd fire)
are archived verbatim to
`research/archive/log-2026-10-28_to_2026-10-31_run76-80.md.gz` (gzip, no
conclusions dropped -- every numeric result and closure is already folded
into the DISTILLED LEARNINGS block above; archived in Run 87 purely for
size, RESEARCH_LOG.md had grown to ~72KB, well over the ~40KB soft
guideline).

---


## Run 81-85 — archived

Run 81 (same-day deferred no-op, 4th fire), Run 82 (DCA self-correction,
on schedule), Run 83 (same-day deferred no-op, 2nd fire), Run 84
(next-day deferred no-op), and Run 85 (same-day deferred no-op, 2nd fire)
are archived verbatim to
`research/archive/log-2026-10-31_to_2026-11-03_run81-85.md.gz` (gzip, no
conclusions dropped -- every numeric result and closure is already folded
into the DISTILLED LEARNINGS block above; archived in Run 90 purely for
size, RESEARCH_LOG.md had grown to ~68KB, well over the ~40KB soft
guideline).

---

## Run 86-88 — archived

Run 86 (DCA self-correction, on schedule, no reversal), Run 87 (same-day
deferred no-op; archive pass), and Run 88 (DCA self-correction, on
schedule, no reversal -- resolves Run 86's carried-forward flag) are
archived verbatim to
`research/archive/log-2026-11-04_to_2026-11-09_run86-88.md.gz` (gzip, no
conclusions dropped -- every numeric result and closure is already folded
into the DISTILLED LEARNINGS block above; archived in Run 92 purely for
size, RESEARCH_LOG.md had grown to ~56KB, well over the ~40KB soft
guideline).

---


## 2026-11-09 — Run 89 (same-day deferred no-op)

**Housekeeping.** Fresh container; local `main` was detached at Run 88's
commit; `git fetch origin main` showed `origin/main` already at
`d1ac325` (Run 88's commit, pushed earlier today) — reset local `main` to
track it, no divergence. Backend venv rebuilt from scratch (`python3 -m
venv .venv && pip install -q -r requirements.txt`), no behavior change.

**Question.** Run 88 (this same day, 02:08 UTC) performed the genuine DCA
self-correction re-check and set the next actionable date at
**2026-11-11 or later**. This firing is 2026-11-09 14:04 UTC — still the
same day, well before the actionable date. Per the standing protocol
(top-of-file SELF-CORRECTION mandate plus the "Going forward" notes in
every run since Run 78), this run defers again rather than re-running the
check a few hours early or inventing a new backtest sweep to manufacture
the appearance of progress.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-88. Re-read the DISTILLED LEARNINGS block end to end — no concretely-
scoped strategy/signal/gate/construction axis has reopened since Run 66.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python -m
pytest -q` on a fresh rebuilt venv — 107 passed (72+35 dots across two
progress lines), exit code 0, matching Run 68-88's count across a
twenty-second independent fresh-container rebuild. Security re-check: no
`.vscode/` directory anywhere in the repo, no `tasks.json`, no stray
`eval(` under `public/`, every `public/fonts/*` file a legitimate
FontAwesome asset (woff/woff2/ttf/eot/svg for `fa-solid-900`,
`fa-brands-400`, `fa-regular-400`, plus `README.md`) — Run 37 incident
remains remediated. No production code touched; no decision logged to
`decisions.jsonl` (no backtest run this fire, consistent with every prior
same-day/early deferred no-op).

**Memory hygiene.** `decisions.jsonl` unchanged at 217 active entries,
well under the 250 rotation threshold — `rotate_archive.py` not needed
this fire. `RESEARCH_LOG.md` is well over the ~40KB soft guideline with 8
full run sections (Run 81-88) before this append — this section is a
small deferred-no-op delta, not a new full research section, so still
deferring the archive pass Run 88 flagged (Run 81-85 or similar) to a run
with more headroom; noting again here so it isn't dropped.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-11 or later**, unchanged from Run 88. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line + this
section only). No other files changed; no files changed in `backend/`.

---

## 2026-11-10 — Run 90 (next-day deferred no-op; archive pass)

**Housekeeping.** Fresh container; `git status` clean, `HEAD` detached at
Run 89's commit (`5a0bf7d`); `git fetch origin main` confirmed
`origin/main` already at the same commit (Run 89's, pushed earlier) — no
divergence. Backend venv rebuilt from scratch (`python3 -m venv .venv &&
pip install -q -r requirements.txt`), no behavior change.

**Question.** Run 88 (2026-11-09) performed the genuine DCA
self-correction re-check and set the next actionable date at
**2026-11-11 or later**. This firing is 2026-11-10 — one day before the
actionable date. Per the standing protocol (top-of-file SELF-CORRECTION
mandate plus the "Going forward" notes carried since Run 78), this run
defers the check again rather than re-running it a day early or inventing
a new backtest sweep to manufacture the appearance of progress.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-89. Re-read the DISTILLED LEARNINGS block end to end — every
concretely-scoped strategy/signal/gate/construction axis remains closed
(last reopened: pairs mean-reversion shorts, Run 66); futures/funding
data remains geo-blocked (unchanged, confirmed Run 31). No new axis to
test honestly without recombining already-closed items.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on a fresh rebuilt venv — **107 passed, 0 failed, 0
errors**, exit code 0, matching Run 68-89's count across a
twenty-third independent fresh-container rebuild. Security re-check: no
`.vscode/` directory anywhere in the repo, no `tasks.json`, no stray
`eval(` under `public/`, every `public/fonts/*` file a legitimate
FontAwesome asset (woff/woff2/ttf/eot/svg for `fa-solid-900`,
`fa-brands-400`, `fa-regular-400`, plus `README.md`) — Run 37 incident
remains remediated. No production code touched; no decision logged to
`decisions.jsonl` (no backtest run this fire, consistent with every prior
same-day/next-day deferred no-op).

**Memory hygiene — archive pass performed this run.**
`decisions.jsonl` unchanged at 217 active entries, well under the 250
rotation threshold — `rotate_archive.py` not needed this fire.
`RESEARCH_LOG.md` had grown to ~68KB (well over the ~40KB soft
guideline) with 9 full run sections (Run 81-89) before this append — this
run had the headroom Run 88/89 flagged for, so Run 81-85 (same-day/
next-day deferred no-ops + Run 82's on-schedule self-correction check,
all already folded into the DISTILLED LEARNINGS block, no conclusions
lost) were archived verbatim to
`research/archive/log-2026-10-31_to_2026-11-03_run81-85.md.gz` and
replaced with a short stub, bringing the active file back down to ~50KB.
Run 86-90 remain in full below.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-11 or later**, unchanged from Run 88. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, this
section, and the Run 81-85 archive stub). `research/archive/log-2026-10-31_to_2026-11-03_run81-85.md.gz`
(new). No other files changed; no files changed in `backend/`.

---

## 2026-11-10 — Run 91 (same-day deferred no-op, 2nd fire)

**Housekeeping.** Fresh container. `git status` found `HEAD` detached at
Run 90's commit (`a56280a`), with local `main` sitting 3 commits behind at
Run 87's commit (`f7c09d4`) — i.e. Run 88/89/90 had been committed on a
detached `HEAD` by a prior container and never merged back onto `main` or
pushed (`origin/main` was also still at `f7c09d4`). Fast-forwarded `main`
to `a56280a` and pushed — `origin/main` now carries Run 88-90. No commits
lost; flagging this pattern (detached-HEAD commits not landing on `main`)
in case it recurs, since a future container could otherwise silently
start from stale state. Backend venv rebuilt from scratch (`python3 -m
venv .venv && pip install -q -r requirements.txt`), no behavior change.

**Question.** Run 90 (earlier today, 2026-11-10 02:05 UTC) already ran
and confirmed the next actionable date for the DCA self-correction check
is **2026-11-11 or later**. This firing is 2026-11-10 14:05 UTC — same
day as Run 90, still one day before the actionable date. Per the standing
protocol (top-of-file SELF-CORRECTION mandate, "Going forward" notes
since Run 78), this run defers the check again rather than re-running it
early or inventing a new backtest sweep to manufacture the appearance of
progress.

**Fresh-idea check.** Re-listed `backend/app/strategies/` — still exactly
the same 4 registered strategy classes (`dca`, `grid`, `mean_reversion`,
`trend_momentum`), unchanged since Run 76-90. Re-read the DISTILLED
LEARNINGS block end to end — every concretely-scoped strategy/signal/
gate/construction axis remains closed (last reopened: pairs
mean-reversion shorts, Run 66); futures/funding data remains geo-blocked
(unchanged, confirmed Run 31). No new axis to test honestly without
recombining already-closed items.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on a fresh rebuilt venv — **107 passed** (72+35 dots across
two progress lines, no summary line printed, consistent with every run
since Run 68), exit code 0 — matching the count across a twenty-fourth
independent fresh-container rebuild. Security re-check: no `.vscode/`
directory anywhere in the repo, no `tasks.json`, no stray `eval(` under
`public/`, every `public/fonts/*` file a legitimate FontAwesome asset
(woff/woff2/ttf/eot/svg for `fa-solid-900`, `fa-brands-400`,
`fa-regular-400`, plus `README.md`) — Run 37 incident remains
remediated. No production code touched; no decision logged to
`decisions.jsonl` (no backtest run this fire, consistent with every prior
same-day deferred no-op).

**Memory hygiene.** `decisions.jsonl` unchanged at 217 active entries,
well under the 250 rotation threshold — `rotate_archive.py` not needed
this fire. `RESEARCH_LOG.md` sits at ~56KB with 10 full run sections (Run
86-90 plus the Run 81-85 stub) before this append — this section is a
small deferred-no-op delta, not a new full research section, so no
archive pass performed this run; next run with headroom should consider
archiving Run 86-88 (self-correction detail already folded into
DISTILLED LEARNINGS).

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-11 or later**, unchanged from Run 88/90. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, this
section only). No other files changed; no files changed in `backend/`.

---

## 2026-11-11 — Run 92 (DCA self-correction, on schedule, no reversal)

**Housekeeping.** Fresh container; `git status` found `HEAD` detached at
Run 91's commit (`1124ccc`), with local `main` sitting 4 commits behind at
Run 87's commit (`f7c09d4`). `git fetch origin main` confirmed
`origin/main` already at `1124ccc` (Run 91's commit had landed on
`origin/main` correctly this time — the Run 91 detached-HEAD flag did not
recur). Fast-forwarded local `main` to `origin/main` with `git checkout
main && git merge --ff-only origin/main`, no commits lost, no push needed
yet. Backend venv rebuilt from scratch (`python3 -m venv .venv &&
.venv/bin/pip install -q -r requirements.txt`), no behavior change.

**Question.** Run 88/90/91 all confirmed the next actionable date for the
DCA self-correction check is **2026-11-11 or later**. Today is
2026-11-11 — the bar is met, so this run performs the genuine re-check
rather than another deferral.

**Re-check performed.** `research/experiments/dca_self_correction_run92.py`
(copied from Run 88's script, window dates shifted +2 days), same
capital-normalized ROI methodology (DCA has no round-trip trades, so
PF/win-rate/trade-count don't apply): average ROI across the 8-symbol
universe, `dip_enabled=True` (shipped) vs `dip_enabled=False` (control),
across 3 non-overlapping windows (older 2026-03-16..2026-06-14, train
2026-06-14..2026-09-12, test 2026-09-12..2026-11-11, anchor=today).
Market regime per window: older -18.86% (decline), train +27.12%
(rally), test -14.37% (decline).

Results:
- **Older window:** ON avg ROI -14.5576%, OFF -14.7370%, delta
  **+0.1794pp**, 8/8 symbols favoring ON, 31 dip-buys fired. Identical
  dip-buy count to Run 88 (31), and the delta is flat-to-slightly-down
  vs Run 88's +0.1850pp — NOT a fourth consecutive high-water mark. This
  is exactly what Run 88's own mechanical explanation predicts: delta
  tracks dip-buy count, and with the count unchanged this run, the delta
  should plateau rather than keep growing. Directly confirms Run 88's
  resolution of the "watch the older-window trend" flag.
- **Train window:** ON +20.8619%, OFF +20.9019%, delta **-0.0400pp**
  (small negative). A third consecutive negative-in-rally reading (Run
  86 -0.0143, Run 88 -0.0133, Run 92 -0.0400pp) — a clear, sustained
  break from the earlier Run 72/76/78/82 positive-in-rally run, further
  evidence (per Run 60/86) that sign is not reliably tied to regime.
- **Test window:** ON -16.3668%, OFF -16.4263%, delta **+0.0595pp**
  (positive). A second consecutive positive-in-decline test-window
  reading (Run 88 +0.0389, Run 92 +0.0595pp) — the mirror image of the
  seven-run negative-in-decline streak that preceded Run 88. Read per
  Run 60's revised framing (sign not reliably predictable from regime
  alone) rather than as a reversion to the pre-Run-60 "positive in
  decline" story, since the magnitude stays inside the same noise band
  every check has shown.

**Honest read:** no reversal. Every delta sits well inside the
already-described sub-0.2pp band; the one previously-growing reading
(older window) plateaued/ticked down exactly as Run 88's mechanical
explanation (dip-buy-count-driven, decelerating) predicted once the
dip-buy count itself stopped rising; and both the train and test signs
continue to bounce in ways consistent with Run 60's "not reliably tied
to regime" conclusion rather than any emerging structural pattern. Bar
for a revert (a clear, economically meaningful, compounding reversal)
is not met. Shipped default (`dip_threshold_pct=5.0,
dip_multiplier=1.5`) kept unchanged. Logged to `decisions.jsonl`.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-91. Re-read the DISTILLED LEARNINGS block end to end — every
concretely-scoped strategy/signal/gate/construction axis remains closed
(last reopened: pairs mean-reversion shorts, Run 66); futures/funding
data remains geo-blocked (unchanged, confirmed Run 31). No new axis to
test honestly without recombining already-closed items.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on a fresh rebuilt venv — **107 passed** (72+35 dots across
two progress lines, no summary line printed, consistent with every run
since Run 68), exit code 0 — matching the count across a twenty-fifth
independent fresh-container rebuild. Security re-check: no `.vscode/`
directory anywhere in the repo, no `tasks.json`, no stray `eval(` under
`public/`, every `public/fonts/*` file a legitimate FontAwesome asset
(woff/woff2/ttf/eot/svg for `fa-solid-900`, `fa-brands-400`,
`fa-regular-400`, plus `README.md`) — Run 37 incident remains
remediated. No production code touched beyond the research script.

**Memory hygiene — archive pass performed this run.** `decisions.jsonl`
now at 218 active entries (+1 this run), well under the 250 rotation
threshold — `rotate_archive.py` not needed. `RESEARCH_LOG.md` had grown
to ~56KB (well over the ~40KB soft guideline) with 10 full run sections
(Run 86-91) before this append — Run 86-88 (self-correction detail
already folded into DISTILLED LEARNINGS, no conclusions lost) were
archived verbatim to
`research/archive/log-2026-11-04_to_2026-11-09_run86-88.md.gz` and
replaced with a short stub. Run 89-92 remain in full below.

**Going forward:** next actionable date for the DCA self-correction check
is **2026-11-13 or later** (2+ days past today's anchor). The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line,
DISTILLED LEARNINGS DCA paragraph, this section, and the Run 86-88
archive stub). `research/archive/log-2026-11-04_to_2026-11-09_run86-88.md.gz`
(new). `research/decisions.jsonl` (+1 entry).
`research/experiments/dca_self_correction_run92.py` (new, research-only,
copied from Run 88's script with window dates shifted),
`research/experiments/dca_self_correction_run92_output.json` (new, raw
results). No files changed in `backend/`.
