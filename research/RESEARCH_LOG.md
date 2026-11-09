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

**88 runs, ~395+ configs, one standing positive finding (DCA dip-buy,
already shipped), zero adopted signal changes.** Full narrative for Run
1-80 is archived (see the archive-index paragraph and the "Run N-M —
archived" stub sections below); Run 81-87 are below in full. The
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
flag is now closed (mechanically explained, decelerating). See Run
46/50/54/58/60/64/68/72/76/78/82/86/88 sections (67-75 archived to
`research/archive/log-2026-10-22_to_2026-10-27_run67-75.md.gz` in Run 76,
76-80 archived to `research/archive/log-2026-10-28_to_2026-10-31_run76-80.md.gz`
in Run 87, purely for size; Run 81-88 are below in full).

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


## 2026-10-31 — Run 81 (same-day deferred no-op, 4th fire)

**Housekeeping.** Fresh container resumed on a detached `HEAD` one commit
ahead of local `main`'s ref (`88eac17`, Run 80's own commit, already landed
on `origin/main` per `git fetch` + `git rev-parse origin/main HEAD`) — same
recurring stale-ref pattern flagged by every run since Run 67. Fast-forwarded
local `main` to `88eac17` via `git checkout main && git merge --ff-only`
(verified strict ancestry first, no divergence, no force-push); confirmed
`origin/main` already held the commit, so no push was actually needed.
Backend venv rebuilt (`python3 -m venv .venv && pip install -q -r
requirements.txt`), no behavior change.

**Question.** Run 78 (2026-10-30) set the next actionable date for the DCA
self-correction check at **2026-11-01 or later**; Run 79 and Run 80 (both
2026-10-30/31) deferred since the bar wasn't yet met. This firing is still
2026-10-31 — one day before the actionable date. Per the standing protocol
(see "Going forward" in Run 78/79/80 and the top-of-file SELF-CORRECTION
mandate), this run defers again rather than re-running the check a day
early or inventing a new backtest sweep to manufacture the appearance of
progress.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-80. Re-read the DISTILLED LEARNINGS block end to end — no concretely-
scoped strategy/signal/gate/construction axis has reopened since Run 66.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python -m
pytest -q` on a fresh rebuilt venv — 107 passed (72+35 dots), 0 failed,
exit code 0, matching Run 68-80's count across a fourteenth independent
fresh-container rebuild. Security re-check: no `.vscode/` directory
anywhere in the repo, no `tasks.json`, no stray `eval(` under `public/`,
every `public/fonts/*` file a legitimate FontAwesome asset (woff/woff2/
ttf/eot/svg for `fa-solid-900`, `fa-brands-400`, `fa-regular-400`, plus
`README.md`) — Run 37 incident remains remediated. No production code
touched; no decision logged to `decisions.jsonl` (no backtest run this
fire, consistent with every prior same-day/early deferred no-op).

**Memory hygiene.** `decisions.jsonl` unchanged at 214 active entries,
well under the 250 rotation threshold — `rotate_archive.py` not needed
this fire. `RESEARCH_LOG.md` was ~44KB before this edit, over the ~40KB
soft guideline, but the active file holds only 6 full run sections (Run
76-81) after this append — still under the "keep the last ~15 runs" floor
set out in Run 80 — so no archive pass performed this run; will revisit
once Run 76-81+ exceeds ~15 full sections.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-01 or later**, unchanged from Run 78/79/80. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier.

**Files:** `research/RESEARCH_LOG.md` edited (this section + top summary
line only). No other files changed; no files changed in `backend/`.

---

## 2026-11-02 — Run 82 (DCA self-correction, on schedule, no reversal)

**Housekeeping.** Fresh container; `git fetch origin main` showed local
`main` already at `origin/main` (`f02fe08`, Run 81's commit) — no
fast-forward needed. Backend venv rebuilt (`python3 -m venv .venv && pip
install -q -r requirements.txt`), no behavior change.

**Question.** Run 78 (2026-10-30) set the next actionable date for the DCA
self-correction check at **2026-11-01 or later**; Run 79/80/81 (all
2026-10-30/31) deferred since the bar wasn't yet met. Today is 2026-11-02,
past the actionable date — the bar is met, so this run performs the genuine
re-check rather than another deferral or a new backtest sweep invented to
manufacture the appearance of progress. No concretely-scoped strategy/
signal/gate/construction axis has reopened since Run 66;
`backend/app/strategies/` and `registry.py` are unchanged — still exactly
the 4 registered strategy classes, no new file.

**Re-check performed.** Re-ran the standing protocol
(`research/experiments/dca_self_correction_run82.py`, same methodology as
Run 78 and all prior checks): shipped DCA dip-buy default
(`dip_threshold_pct=5.0`, `dip_multiplier=1.5`) vs dip-buy OFF, across all 8
universe symbols, 3 non-overlapping windows shifted +3 days vs Run 78
(older 2026-03-07..2026-06-05, train 2026-06-05..2026-09-03, test
2026-09-03..2026-11-02, anchor=today). Older window a deep decline (OFF avg
ROI -16.0862%, the sharpest decline window yet sampled in this protocol),
delta **+0.1016pp** with 8/8 symbols favoring ON — the largest single-window
delta magnitude recorded across all 18 checks, marginally exceeding the
sub-0.1pp band every prior check stayed inside. Read honestly this is a new
high-water mark for the band, not a reversal: the direction (ON beats OFF
in a decline) is exactly the mechanism the shipped default was built on —
deeper, sharper declines simply let more real dip-buys fire (25 dip-buys
this window vs ~8-18 in the milder windows), each landing at a materially
lower cost basis — and the magnitude (0.10% of invested capital, one-time,
non-compounding since DCA has no round-trip trades) stays economically
negligible. Train window a strong rally (OFF +20.2853%), delta +0.0186pp
(small positive, consistent with Run 72/76/78's train-window sign, only
3/8 symbols favored ON — most buys land above the dip threshold in a rally
so dip-buy is mostly a no-op there, matching the mechanism's design). Test
window a decline (OFF -9.4124%), delta **-0.0260pp** (negative) — the
**sixth consecutive check** (Run 64, 68, 72, 76, 78, 82) where a declining
test window yields a negative delta, continuing to refute the pre-Run-60
"positive in decline" story and support Run 60's revised, more honest
characterization: the dip-buy ON/OFF delta's sign is not reliably
predictable from decline/rally regime alone (it depends on exactly which
day's declines happen to cross the -5% 24h threshold, not the window's net
direction), and the magnitude stays economically trivial either way,
including this run's new high-water-mark older-window reading. **No
reversal of substance — the bar for a revert (a clear, economically
meaningful, compounding reversal) is not met. Shipped default kept
unchanged.**

**Decision logged.** One entry appended to `research/decisions.jsonl`
(strategy `dca`, decision `noise`, full rationale inline) — see that file
for the exact JSON. `usd_pnl_100`/`usd_pnl_1000` reported as the
test-window delta (-$0.0260 / -$0.260 on $100/$1000 respectively) —
economically negligible, consistent with every prior check in this
protocol.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest -q`
— 107 passed, 0 failed, 0 errors, exit code 0, matching Run 68-81's count
across a fifteenth independent fresh-container rebuild. No production code
touched this run (self-correction check only reads `app.strategies.dca`
and `app.backtest.*`, writes nothing outside `research/`), so no test
changes were needed.

**Security re-check.** No `.vscode/` directory anywhere in the repo, no
`tasks.json`, no stray `eval(` under `public/`, every `public/fonts/*` file
a legitimate FontAwesome asset (woff/woff2/ttf/eot/svg for `fa-solid-900`,
`fa-brands-400`, `fa-regular-400`, plus `README.md`) — Run 37 incident
remains remediated.

**Memory hygiene this run.** `rotate_archive.py` run after appending the
new decision: `decisions.jsonl` at 215 active entries, still well under
the 250 rotation threshold — no-op, as expected. `RESEARCH_LOG.md` was
~47.9KB before this edit, over the ~40KB soft guideline, but the active
file holds only 7 full run sections (Run 76-82) after this append — still
under the "keep the last ~15 runs" floor set out in Run 80/81 — so no
archive pass performed this run; will revisit once Run 76-82+ exceeds ~15
full sections, consistent with Run 80/81's stated plan.

**Going forward:** next actionable date for the DCA self-correction check
is **2026-11-04 or later** (2 days past this run's anchor, per the
standing +2-day protocol). No concretely-scoped item is currently flagged
open; the next run should default to the self-correction protocol once
due, or defer with a brief no-op note if fired earlier.

**Files:** `research/RESEARCH_LOG.md` edited (DISTILLED LEARNINGS DCA
paragraph + top summary line refreshed, this section appended).
`research/decisions.jsonl` (215 active, +1 this run).
`research/experiments/dca_self_correction_run82.py` (new, research-only),
`research/experiments/dca_self_correction_run82_output.json` (new, raw
results). No files changed in `backend/`.

---

## 2026-11-02 — Run 83 (same-day deferred no-op, 2nd fire)

**Housekeeping.** Fresh container; `git fetch origin main` showed local
`main` already at `origin/main` (`439fa28`, Run 82's commit) — no
fast-forward needed. Backend venv rebuilt from scratch (`python3 -m venv
.venv && pip install -q -r requirements.txt`), no behavior change.

**Question.** Run 82 (this same day, 02:07 UTC) performed the genuine DCA
self-correction re-check and set the next actionable date at **2026-11-04
or later**. This firing is 2026-11-02 14:28 UTC — still the same day, well
before the actionable date. Per the standing protocol (top-of-file
SELF-CORRECTION mandate plus the "Going forward" notes in every run since
Run 78), this run defers again rather than re-running the check a few
hours early or inventing a new backtest sweep to manufacture the
appearance of progress.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-82. Re-read the DISTILLED LEARNINGS block end to end — no concretely-
scoped strategy/signal/gate/construction axis has reopened since Run 66.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python -m
pytest -q` on a fresh rebuilt venv — 107 passed, 0 failed, exit code 0,
matching Run 68-82's count across a sixteenth independent fresh-container
rebuild. Security re-check: no `.vscode/` directory anywhere in the repo,
no `tasks.json`, no stray `eval(` under `public/`, every `public/fonts/*`
file a legitimate FontAwesome asset (woff/woff2/ttf/eot/svg for
`fa-solid-900`, `fa-brands-400`, `fa-regular-400`, plus `README.md`) — Run
37 incident remains remediated. No production code touched; no decision
logged to `decisions.jsonl` (no backtest run this fire, consistent with
every prior same-day/early deferred no-op).

**Memory hygiene.** `decisions.jsonl` unchanged at 215 active entries,
well under the 250 rotation threshold — `rotate_archive.py` not needed
this fire. `RESEARCH_LOG.md` was ~48.6KB before this edit, over the ~40KB
soft guideline, with 8 full run sections (Run 76-82) before this append —
now 8 after adding this short deferred-no-op section (this section is a
small delta, not a new full research section). Will do the archive pass
(move the oldest of Run 76-82 into `research/archive/`, keep the last
~15 runs per the standing floor) once the active file meaningfully
exceeds 15 full sections or size becomes unwieldy — neither threshold is
hit yet.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-04 or later**, unchanged from Run 82. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier.

**Files:** `research/RESEARCH_LOG.md` edited (this section + top summary
line only). No other files changed; no files changed in `backend/`.

---

## 2026-11-03 — Run 84 (next-day deferred no-op)

**Housekeeping first.** Fresh container; local `main` was detached at
Run 83's commit, 4 commits behind `origin/main` (`b3ec37a..ee28969`, Runs
80-83 landed on the remote but not the local branch ref) — the same
recurring stale-local-ref pattern flagged by every run since Run 67.
Checked out `main` and fast-forwarded with `git merge --ff-only
origin/main` (verified strict-ancestor fast-forward, no divergence, no
force-push needed). Backend venv absent in this fresh container; rebuilt
via `python3 -m venv .venv && .venv/bin/pip install -q -r
requirements.txt`, clean install, no behavior change.

**Question.** Run 82 (2026-11-02) ran the genuine DCA self-correction
re-check and set the next actionable date at **2026-11-04 or later**.
Today is 2026-11-03 — one day short. Re-running the check now would reuse
windows nearly identical to Run 82's (one extra day of data) and add
negligible new information, the same reasoning Run 74 (and the chain of
same/next-day deferrals before it) applied at equivalent points in prior
cycles. Per the standing protocol (top-of-file SELF-CORRECTION mandate
plus the "Going forward" notes in every run since Run 78), this run
defers rather than re-running the check a day early or inventing a new
backtest sweep to manufacture the appearance of progress.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-83. `research/experiments/` holds no file not already reflected in
DISTILLED LEARNINGS. Re-read the DISTILLED LEARNINGS block end to end —
no concretely-scoped strategy/signal/gate/construction axis has reopened
since Run 66 closed the last one (pairs mean-reversion with real
shorting); every one remains closed with zero surviving candidates, and
the only structurally out-of-reach item (geo-blocked futures/funding
data) is unchanged.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on the freshly rebuilt venv — 107 passed (72+35 dots across
the two progress lines), 0 failed, exit code 0, matching Run 68-83's
count across a seventeenth independent fresh-container rebuild. Security
re-check: no `.vscode/` or `tasks.json` anywhere in the repo, no `eval(`
under `public/`, `public/fonts/` holds only the expected 16 legitimate
FontAwesome asset files plus `README.md` — Run 37 incident remains
remediated.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added (would just rerun Run 82's method a day
early, with no new signal), no code changes, no candidate.

**Memory hygiene.** `decisions.jsonl` unchanged at 215 active entries,
well under the 250 rotation threshold — `rotate_archive.py` not needed
this fire. `RESEARCH_LOG.md` was ~60KB before this edit, over the ~40KB
soft guideline, with 9 full run sections (Run 76-83) before this append
— now 9 after adding this short deferred-no-op section (a small delta,
not a new full research section). Still well under the "keep the last
~15 runs" floor, so no archive pass needed yet.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-04 or later**, unchanged from Run 82. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier.

**Files:** `research/RESEARCH_LOG.md` edited (this section + top summary
line only). No other files changed; no files changed in `backend/`.

---

## 2026-11-03 — Run 85 (same-day deferred no-op, 2nd fire)

**Housekeeping first.** Fresh container resumed with local `main` stale
(detached `HEAD` at Run 84's commit, local `main` ref 5 commits behind on
`origin/main`) — same recurring stale-ref pattern flagged by every run
since Run 67. Checked out `main` and fast-forwarded with `git merge
--ff-only origin/main` (verified strict-ancestor fast-forward, no
divergence, no force-push needed; `origin/main` already held Run 84's
commit `7e598f1`). Backend venv absent in this fresh container; rebuilt
via `python3 -m venv .venv && .venv/bin/pip install -q -r
requirements.txt`, clean install, no behavior change.

**Question.** Run 82 (2026-11-02) set the next actionable date for the DCA
self-correction check at **2026-11-04 or later**; Run 83/84 (both
2026-11-02/03) deferred since the bar wasn't yet met. This firing is
2026-11-03 14:04 UTC — still a day short of the actionable date. Per the
standing protocol (top-of-file SELF-CORRECTION mandate plus the "Going
forward" notes in every run since Run 78), this run defers again rather
than re-running the check a day early or inventing a new backtest sweep to
manufacture the appearance of progress.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-84. `research/experiments/` holds no file not already reflected in
DISTILLED LEARNINGS. Re-read the DISTILLED LEARNINGS block end to end —
no concretely-scoped strategy/signal/gate/construction axis has reopened
since Run 66 closed the last one (pairs mean-reversion with real
shorting); every one remains closed with zero surviving candidates, and
the only structurally out-of-reach item (geo-blocked futures/funding
data) is unchanged.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on the freshly rebuilt venv — 107 passed (72+35 dots across
the two progress lines), 0 failed, exit code 0, matching Run 68-84's
count across an eighteenth independent fresh-container rebuild. Security
re-check: no `.vscode/` or `tasks.json` anywhere in the repo, no `eval(`
under `public/`, `public/fonts/` holds only the expected 16 legitimate
FontAwesome asset files plus `README.md` — Run 37 incident remains
remediated.

**Decision: no-op deferral, nothing to log.** No backtest configs run, no
`decisions.jsonl` entry added (would just rerun Run 82's method a day
early, with no new signal), no code changes, no candidate.

**Memory hygiene.** `decisions.jsonl` unchanged at 215 active entries,
well under the 250 rotation threshold — `rotate_archive.py` not needed
this fire. `RESEARCH_LOG.md` was ~60KB before this edit, over the ~40KB
soft guideline, with 9 full run sections (Run 76-84) before this append —
now 10 after adding this short deferred-no-op section (a small delta, not
a new full research section). Still under the "keep the last ~15 runs"
floor set out in Run 80/81, so no archive pass needed yet; will revisit
once the active file meaningfully exceeds 15 full sections.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-04 or later**, unchanged from Run 82. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier.

**Files:** `research/RESEARCH_LOG.md` edited (this section + top summary
line only). No other files changed; no files changed in `backend/`.

---

## 2026-11-04 — Run 86 (DCA self-correction, on schedule, no reversal)

**Housekeeping.** Fresh container; `git fetch origin main` showed local
`main` detached at Run 85's commit (`d76bcbb`), 0 commits behind
`origin/main` (already current). Checked out `main` directly (no
fast-forward needed this time). Backend venv absent in this fresh
container; rebuilt via `python3 -m venv .venv && .venv/bin/pip install -q
-r requirements.txt`, clean install, no behavior change.

**Question.** Run 82 (2026-11-02) set the next actionable date for the DCA
self-correction check at **2026-11-04 or later**; Run 83/84/85 (all
2026-11-02/03) deferred since the bar wasn't yet met. Today is 2026-11-04,
exactly the actionable date — the bar is met, so this run performs the
genuine re-check rather than another deferral. No concretely-scoped
strategy/signal/gate/construction axis has reopened since Run 66;
`backend/app/strategies/` and `registry.py` are unchanged — still exactly
the 4 registered strategy classes, no new file.

**Re-check performed.** Re-ran the standing protocol
(`research/experiments/dca_self_correction_run86.py`, same methodology as
Run 82 and all prior checks): shipped DCA dip-buy default
(`dip_threshold_pct=5.0`, `dip_multiplier=1.5`) vs dip-buy OFF, across all 8
universe symbols, 3 non-overlapping windows shifted +2 days vs Run 82
(older 2026-03-09..2026-06-07, train 2026-06-07..2026-09-05, test
2026-09-05..2026-11-04, anchor=today). Older window a deeper decline (OFF
avg ROI -21.7687%, the sharpest decline window yet sampled, surpassing Run
82's -16.0862%), delta **+0.1684pp** with 8/8 symbols favoring ON — a
*second consecutive* new high-water mark for this protocol's magnitude
(Run 82: +0.1016pp -> Run 86: +0.1684pp), now clearly above the sub-0.1pp
band every check before Run 82 stayed inside. Read honestly, the direction
is unchanged and mechanically consistent (ON beats OFF in a deep decline
because more real 24h dips cross the -5% threshold and each dip-buy lands
at a materially lower cost basis — 30 dip-buys fired this window vs 25 in
Run 82's older window, itself the prior record), so this is not a
reversal signal; but two consecutive high-water marks in the same
direction, growing by 66% run-over-run, is worth explicitly flagging as a
trend to watch rather than waving away as a one-off. In absolute terms it
remains economically negligible (0.17% of invested capital, a one-time,
non-compounding effect since DCA issues no round-trip trades to compound
gains across). Train window a strong rally (OFF +24.3294%), delta
**-0.0143pp** (small negative) — this *breaks* Run 72/76/78/82's
small-positive-in-rally pattern, which is itself useful evidence: it shows
the sign is not reliably tied to regime even across consecutive
same-labeled (rally) windows, reinforcing Run 60's revised framing rather
than the simpler "positive in decline / negative in rally" story Run 60
already retired. Test window a decline (OFF -10.4155%), delta
**-0.0290pp** (negative) — the **seventh consecutive check** (Run 64, 68,
72, 76, 78, 82, 86) where a declining test window yields a negative
delta, continuing to refute the pre-Run-60 "positive in decline" story.
**No reversal of substance — the bar for a revert (a clear, economically
meaningful, compounding reversal) is not met. Shipped default kept
unchanged.** Noting for the next check: if the older-window magnitude
extends a third consecutive high-water mark, that would be the point to
investigate whether something structural (not just "this window happened
to have the deepest decline yet") is driving the growth, rather than
treating it as more of the same noise.

**Decision logged.** One entry appended to `research/decisions.jsonl`
(strategy `dca`, decision `noise`, full rationale inline) — see that file
for the exact JSON. `usd_pnl_100`/`usd_pnl_1000` reported as the
test-window delta (-$0.029 / -$0.29 on $100/$1000 respectively) —
economically negligible, consistent with every prior check in this
protocol.

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest -q`
— 107 passed (72+35 dots across the two progress lines), 0 failed, 0
errors, exit code 0, matching Run 68-85's count across a nineteenth
independent fresh-container rebuild. No production code touched this run
(self-correction check only reads `app.strategies.dca` and
`app.backtest.*`, writes nothing outside `research/`), so no test changes
were needed.

**Security re-check.** No `.vscode/` directory anywhere in the repo, no
`tasks.json`, no stray `eval(` under `public/`, `public/fonts/` holds only
the expected 16 legitimate FontAwesome asset files (woff/woff2/ttf/eot/svg
for `fa-solid-900`, `fa-brands-400`, `fa-regular-400`) plus `README.md` —
Run 37 incident remains remediated.

**Memory hygiene this run.** `rotate_archive.py` run after appending the
new decision (see output below): `decisions.jsonl` at 216 active entries
before rotation, still well under the 250 rotation threshold. `RESEARCH_LOG.md`
is well over the ~40KB soft guideline and now holds 11 full run sections
(Run 76-86) after this append — exceeding the "keep the last ~15 runs"
floor is not yet true by section count, but file size has grown
substantially; will perform the archive pass (move Run 76-80 or similar
into `research/archive/`, per the plan set out in Run 80/81) on the next
run that has headroom to do so carefully, since this run's primary
obligation is the self-correction re-check itself.

**Going forward:** next actionable date for the DCA self-correction check
is **2026-11-06 or later** (2 days past this run's anchor, per the
standing +2-day protocol). No concretely-scoped item is currently flagged
open; the next run should default to the self-correction protocol once
due, or defer with a brief no-op note if fired earlier. Flag carried
forward: watch whether the older-window high-water-mark magnitude extends
a third consecutive run (Run 82 -> Run 86 -> next); if so, investigate
structurally rather than continuing to label it noise by default.

**Files:** `research/RESEARCH_LOG.md` edited (DISTILLED LEARNINGS DCA
paragraph + top summary line refreshed, this section appended).
`research/decisions.jsonl` (216 active, +1 this run).
`research/experiments/dca_self_correction_run86.py` (new, research-only),
`research/experiments/dca_self_correction_run86_output.json` (new, raw
results). No files changed in `backend/`.

---

## 2026-11-04 — Run 87 (same-day deferred no-op; archive pass)

**Housekeeping.** Fresh container; local `main` was detached (`HEAD`
pointing at `031f615`, Run 86's commit) with the `main` branch ref itself
still at `b3ec37a` (Run 79), 7 commits behind — Runs 80-86's commits had
never been fast-forwarded onto `main` or pushed by the sessions that made
them. Fast-forwarded local `main` to `031f615` and pushed; `origin/main`
now holds Run 86's commit (confirmed fast-forward only, no force-push, no
history rewrite). Backend venv rebuilt from scratch (`python3 -m venv
.venv && pip install -q -r requirements.txt`), no behavior change.

**Question.** Run 86 (this same day, earlier) performed the genuine DCA
self-correction re-check and set the next actionable date at **2026-11-06
or later**. This firing is still 2026-11-04 — well before the actionable
date. Per the standing protocol (top-of-file SELF-CORRECTION mandate plus
the "Going forward" notes in every run since Run 78), this run defers
again rather than re-running the check early or inventing a new backtest
sweep to manufacture the appearance of progress.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-86. Re-read the DISTILLED LEARNINGS block end to end — no concretely-
scoped strategy/signal/gate/construction axis has reopened since Run 66.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python -m
pytest -q` on a fresh rebuilt venv — 107 passed, 0 failed, exit code 0,
matching Run 68-86's count across a twentieth independent fresh-container
rebuild. Security re-check: no `.vscode/` directory anywhere in the repo,
no `tasks.json`, no stray `eval(` under `public/`, every `public/fonts/*`
file a legitimate FontAwesome asset (woff/woff2/ttf/eot/svg for
`fa-solid-900`, `fa-brands-400`, `fa-regular-400`, plus `README.md`) — Run
37 incident remains remediated. No production code touched; no decision
logged to `decisions.jsonl` (no backtest run this fire, consistent with
every prior same-day/early deferred no-op).

**Memory hygiene — archive pass performed.** `decisions.jsonl` unchanged
at 216 active entries, well under the 250 rotation threshold —
`rotate_archive.py` not needed this fire. `RESEARCH_LOG.md` had grown to
~72KB (well over the ~40KB soft guideline) with 11 full run sections (Run
76-86) — Run 86 itself flagged this as due "on the next run that has
headroom," and this deferred-no-op fire has exactly that headroom.
Archived the oldest 5 of those sections (Run 76: DCA self-correction;
Run 77: same-day deferred no-op; Run 78: DCA self-correction; Run 79:
same-day deferred no-op; Run 80: same-day deferred no-op) verbatim to
`research/archive/log-2026-10-28_to_2026-10-31_run76-80.md.gz` (gzip, no
conclusions dropped — every numeric result and closure from those
sections is already folded into the DISTILLED LEARNINGS block above, and
is unaffected by this archive pass since the block wasn't touched beyond
its existing text). Replaced the archived range with a short "Run 76-80 —
archived" stub, matching the format of the Run 41-75 stubs above it.
Active file now holds 6 full run sections (Run 81-86) plus this Run 87
no-op, down from 72KB to ~55KB after this section's own append — still
over the 40KB guideline but well under the "last ~15 runs" floor by
section count, so no further archiving needed this run. Top summary line
(run count, archived range) refreshed to match.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-06 or later**, unchanged from Run 86. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier. Flag carried forward unchanged
from Run 86: watch whether the older-window high-water-mark magnitude
extends a third consecutive run when the next genuine check runs; if so,
investigate structurally rather than continuing to label it noise by
default.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, this
section appended, Run 76-80 sections replaced with an archived stub).
`research/archive/log-2026-10-28_to_2026-10-31_run76-80.md.gz` (new).
No other files changed; no files changed in `backend/`. No
`decisions.jsonl` entry this run (no backtest performed).

---

## 2026-11-09 — Run 88 (DCA self-correction, on schedule, no reversal — resolves Run 86's carried-forward flag)

**Housekeeping.** Fresh container; `main` already at Run 87's commit
(`f7c09d4`), no detached-HEAD or unpushed-commit issue this time. Backend
venv rebuilt from scratch (`python3 -m venv .venv && pip install -q -r
requirements.txt`), no behavior change.

**Question.** Run 86 set the next actionable date for the DCA
self-correction check at 2026-11-06 or later; this fire (2026-11-09) is
+5 days past that, well past due, so this run performs the genuine
re-check rather than deferring.

**Method.** Same methodology as every prior check in the protocol (Run
4/14/27/32/35/36/38/40/42/46/50/54/58/60/64/68/72/76/78/82/86): DCA
dip-buy ON (`dip_threshold_pct=5.0, dip_multiplier=1.5`, shipped) vs OFF
(`dip_enabled=False`), capital-normalized average ROI across the 8-symbol
universe at 1h, 3 non-overlapping windows (older/train 90d, test 60d)
shifted +5 days vs Run 86, anchored on today's close: older
2026-03-14..2026-06-12, train 2026-06-12..2026-09-10, test
2026-09-10..2026-11-09. Script:
`research/experiments/dca_self_correction_run88.py` (copied from Run 86's
script with only the window-date constants and output filename changed).

**Results.**
- Older window (decline, OFF avg ROI -16.1499%): ON -15.9649%, **delta
  +0.1850pp**, 8/8 symbols favoring ON, 31 dip-buys fired.
- Train window (rally, OFF avg ROI +22.3379%): ON +22.3246%, **delta
  -0.0133pp** (small negative), 2/8 symbols favoring ON, 5 dip-buys fired.
- Test window (decline, OFF avg ROI -14.2862%): ON -14.2473%, **delta
  +0.0389pp** (positive), 7/8 symbols favoring ON, 23 dip-buys fired.

**Analysis — resolving Run 86's carried-forward flag.** Run 86 flagged
the older-window high-water mark (0.1016pp Run 82 -> 0.1684pp Run 86) to
"investigate structurally" if a third consecutive run extended it
further. It did: +0.1850pp this run. But the investigation resolves it as
routine, not structural: this run's older-window decline (-16.15%) is
*shallower* than Run 86's (-21.77%) yet produced a *larger* delta, which
rules out "delta simply tracks total decline depth." What tracks it in
lockstep instead is the dip-buy count across the three checks: 25 (Run
82) -> 30 (Run 86) -> 31 (Run 88), rising alongside the delta (0.1016 ->
0.1684 -> 0.1850pp). That is exactly the mechanism the shipped default
was already built on — more real 24h-dip triggers in a window means more
buys landing at a lower cost basis, so the ON-OFF gap scales with how
*many* dip-buys fired, not with the window's net % move. This is a
refinement of the existing causal story, not a new or hidden edge. It is
also reassuring on its own terms: the magnitude's growth is *decelerating*
(+0.0668pp from Run 82->86, +0.0166pp from Run 86->88), the opposite
of a runaway structural trend that would warrant real concern.

Separately, the test-window delta flipped **positive** (+0.0389pp) this
run — the first positive test-window reading in 8 checks, breaking the
seven-run streak (Run 64, 68, 72, 76, 78, 82, 86) of negative deltas on
declining test windows. Combined with the train window's second
consecutive small-negative-in-rally reading (Run 86 was also negative),
this further confirms Run 60's revised framing: the ON/OFF delta's sign
is not reliably predictable from regime (decline vs rally) alone — it is
a small, noisy effect whose direction varies run to run, and which stays
economically trivial regardless of sign.

**Decision.** No reversal of substance. All three deltas stay far below
anything economically meaningful (max |delta| this run 0.185pp, i.e.
$0.185 on $100 invested, one-time and non-compounding since DCA has no
round-trip trades); the one growing reading (older window) now has a
mechanical explanation (dip-buy count) rather than looking like a hidden
edge, and its growth is slowing, not accelerating. **Shipped default
(`dip_threshold_pct=5.0, dip_multiplier=1.5`) kept unchanged.** One entry
appended to `research/decisions.jsonl` (strategy `dca`, decision
`noise`, full rationale inline — see that file). `usd_pnl_100`/
`usd_pnl_1000` reported as the test-window delta (+$0.0389 / +$0.389 on
$100/$1000).

**Verification.** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest
-q` on a fresh rebuilt venv — **107 passed, 0 failed, 0 errors**, exit
code 0, matching Run 68-87's count across a twenty-first independent
fresh-container rebuild. No production code touched this run
(self-correction check only reads `app.strategies.dca` and
`app.backtest.*`, writes nothing outside `research/`), so no test changes
were needed.

**Security re-check.** No `.vscode/` directory anywhere in the repo, no
`tasks.json`, no stray `eval(` under `public/`, `public/fonts/` holds only
the expected 16 legitimate FontAwesome asset files (woff/woff2/ttf/eot/svg
for `fa-solid-900`, `fa-brands-400`, `fa-regular-400`) plus `README.md` —
Run 37 incident remains remediated.

**Memory hygiene this run.** `rotate_archive.py` run after appending the
new decision: `decisions.jsonl` at 217 active entries, well under the 250
rotation threshold — no rotation performed. `RESEARCH_LOG.md` is well
over the ~40KB soft guideline (~62KB before this section) with 7 full run
sections (Run 81-87); this run's append pushes it further over, but
section count (8 after this append) stays well under the "last ~15 runs"
floor, so no archive pass performed this run — flagging for the next run
with headroom to archive the oldest sections (Run 81-85 or similar),
matching the pattern Run 87 used.

**Going forward:** next actionable date for the DCA self-correction check
is **2026-11-11 or later** (2 days past this run's anchor, per the
standing +2-day protocol). The "watch the older-window high-water-mark"
flag carried since Run 86 is now **closed** (mechanically explained via
dip-buy count, decelerating growth) — no open flag carried forward from
this run. No concretely-scoped strategy/signal/gate/construction item is
open; the next run should default to the self-correction protocol once
due, or defer with a brief no-op note if fired earlier.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, DCA
DISTILLED LEARNINGS paragraph extended, this section appended).
`research/decisions.jsonl` (217 active, +1 this run).
`research/experiments/dca_self_correction_run88.py` (new, research-only,
copied from Run 86's script with window dates shifted),
`research/experiments/dca_self_correction_run88_output.json` (new, raw
results). No files changed in `backend/`.
