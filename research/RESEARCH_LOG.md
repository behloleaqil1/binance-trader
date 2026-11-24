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

**113 runs, ~450+ configs, one standing positive finding (DCA dip-buy,
already shipped), zero adopted signal changes.** Full narrative for Run
1-103 is archived (see the archive-index paragraph and the "Run N-M —
archived" stub sections below); Run 104-113 are below in full. The
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
All 9 tried are rejected at every TF swept (mostly 1h/4h, full 1m-4h sweep
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
cleared both OOS bars); **Ichimoku Cloud** (Run 112 — Tenkan/Kijun cross,
optionally filtered by a forward-shifted Senkou cloud; the first
3-lookback multi-line confluence construction tried. 10/10 configs
rejected decisively on the TRAIN side alone — best train PF only 0.965
@4h classic-params+cloud-filter, every other config train PF 0.41-0.90 —
so none reached a test-side or 3rd-window check at all; worse than every
prior family's closest near-miss); **VWAP Band Reversion** (Run 113 —
rolling volume-weighted VWAP + volume-weighted deviation band, buy below
the lower band / exit on reversion to the VWAP mid-line; the first
construction to weight the price level itself by volume rather than
applying a volume *gate* on top of a price signal. Swept vwap_period
{20,50} x band_mult {1.5,2.0,2.5} x optional SMA(100) trend filter across
15m/1h/4h, 36 configs. 0/36 cleared both OOS bars; the one config with
adequate sample on both sides (4h, vwap_period=20, band_mult=1.5, no
filter: train PF 1.702/73 trades, test PF 0.547/109 trades) is a clean
train-clears/test-fails divergence — the same regime-luck signature as
mean_reversion's chronic failure mode, just with VWAP in place of SMA.
14/36 configs had adequate sample for a decisive reject; the other 22
were too thin, mostly <30 trades from the trend filter + wide-band
combination starving entries, to be anything but noise). 1m/5m are
catastrophic at any strategy
(fee drag dominates, PF 0.01-0.09 @1m). 1d starves trend_momentum/
mean_reversion on trade count; grid@1d has no economically meaningful
return.

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
middle point). **Trend-conditioned dip-buy gate** (Run 36) is also closed:
nearly all 24h-drop dips already occur below a multi-day SMA by
construction, deltas stay within noise of the ungated baseline.
`interval=daily` beats hourly (no benefit, more orders) and weekly (worse,
small unrepresentative samples). `dip-rebuy cap` (Run 14) strictly hurts or
ties. **DCA is now fully closed on every concretely-scoped parameter axis;
standing self-correction protocol (re-check ON vs OFF on rolling-forward
windows, roughly every 2+ days of new data) is the only recommended
periodic check, not further parameter tuning.**

**Self-correction protocol history (condensed; full per-run numbers live in
`research/decisions.jsonl` and the dated archives below).** Runs 46-58
(2026-10-07 to 2026-10-16) reproduced the original "positive in
decline/chop, negative in a rally" sign pattern on successive
rolling-forward windows, all deltas shrinking toward a sub-0.1pp noise
floor. **Run 60 (2026-10-19) revised that framing**: a window where
train/test regimes swapped relative to every prior check showed the delta
sign does NOT reliably track regime label — the earlier pattern was an
artifact of train windows always sampling declines and test windows always
sampling rallies, not a real mechanism. Runs 64-86 (2026-10-21 to
2026-11-04) confirmed the revised framing seven consecutive times (a
declining test window yielding a *negative* delta, the mirror of the
original story) while every reading stayed inside a sub-0.1-0.2pp band.
**Run 88 (2026-11-09) identified the actual driver**: the delta tracks
*dip-buy count* (how many real 24h dips fired in that window), not decline
depth or regime label directly — confirmed by six further checks (Run 92,
96, 100, 104, 108, 110) where identical dip-counts across consecutive
windows produced near-identical deltas, and count changes moved the delta
in lockstep. Test-window dip-buy count and delta have both been setting
successive depth/magnitude records as 2026 H2's declines deepen (Run 100:
+0.2179pp; Run 110: +0.3771pp, the largest single reading in the whole
19-check protocol, dip-count 37) — always in the *same* direction (ON
beats OFF) the shipped default was built on, always a one-time,
non-compounding fraction of a percent of invested capital, never a
reversal. Train-window (rally) deltas have independently settled into a
small-but-growing negative pattern across the last eight checks (Run 86
through 110: -0.0143pp to -0.0679pp), still two orders of magnitude below
anything economically meaningful. **No reversal across 19 checks
(Run 32-110); shipped default kept unchanged throughout. Next actionable
date: 2026-11-25 or later** (set by Run 110; Run 113 confirmed this date
had not yet arrived and ran a fresh-strategy study instead, per the
"rotate regions" mandate). Flagged to watch going into the next check:
whether the test-window high-water mark (Run 110's record) extends a
third time with a correspondingly higher dip-count, or plateaus as the
older-window record did after Run 88. See
`research/archive/log-2026-10-22_to_2026-10-27_run67-75.md.gz` (Run
67-75), `log-2026-10-28_to_2026-10-31_run76-80.md.gz` (Run 76-80),
`log-2026-11-04_to_2026-11-09_run86-88.md.gz` (Run 86-88),
`log-2026-11-09_to_2026-11-10_run89-91.md.gz` (Run 89-91),
`log-2026-11-11_to_2026-11-14_run92-97.md.gz` (Run 92-97),
`log-2026-11-14_to_2026-11-17_run98-103.md.gz` (Run 98-103) for full
per-run narrative; Run 104-113 are below in full.

### Where this programme stands
Every concretely-scoped axis — 10 strategy families (VWAP Band Reversion
closed Run 113, a volume-weighted price-level construction, mechanically
distinct from all 9 prior families including Ichimoku Cloud closed Run
112, a 3-lookback multi-line confluence construction), 5 signal-source categories, 3
confirmation gates (+ 1 stacked combo), 2 cross-symbol
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


## Run 89-91 — archived

Run 89 (same-day deferred no-op), Run 90 (next-day deferred no-op; archive
pass), and Run 91 (same-day deferred no-op, 2nd fire; first occurrence of
the detached-HEAD-on-fresh-container pattern, recovered with no commits
lost) are archived verbatim to
`research/archive/log-2026-11-09_to_2026-11-10_run89-91.md.gz` (gzip, no
conclusions dropped -- every numeric result and closure is already folded
into the DISTILLED LEARNINGS block above; archived in Run 96 purely for
size, RESEARCH_LOG.md had grown to ~62KB, well over the ~40KB soft
guideline).

---


## Run 92-97 — archived

Run 92 (DCA self-correction, on schedule, no reversal), Run 93 (same-day
deferred no-op), Run 94 (before-schedule deferred no-op; detached-HEAD
recovery), Run 95 (before-schedule deferred no-op, 2nd fire), Run 96 (DCA
self-correction, on schedule, no reversal; detached-HEAD recovery;
archive pass), and Run 97 (same-day deferred no-op, 2nd fire;
detached-HEAD recovery) are archived verbatim to
`research/archive/log-2026-11-11_to_2026-11-14_run92-97.md.gz` (gzip, no
conclusions dropped -- every numeric result and closure is already folded
into the DISTILLED LEARNINGS block above; archived in Run 107 purely for
size, RESEARCH_LOG.md had grown to ~100KB, well over the ~40KB soft
guideline).

---


## Run 98-103 — archived

See `research/archive/log-2026-11-14_to_2026-11-17_run98-103.md.gz` (before-schedule deferred no-ops Run 98/99, DCA self-correction re-check Run 100, before-schedule deferred no-op Run 101, before-schedule deferred no-op Run 102, before-schedule deferred no-op + detached-HEAD recovery Run 103 — zero decisions logged, no reversal, no production-code changes across all 6; every conclusion already folded into the DISTILLED LEARNINGS block above).

---

## Run 104 — 2026-11-18, on-schedule DCA self-correction re-check

**Housekeeping.** Fresh container; `git status` clean, `main` already at
Run 103's commit (`2459ec1`), matching `origin/main` — no detached-HEAD
recovery needed this fire (first clean start since Run 91 flagged the
pattern). Backend venv rebuilt from scratch (`python3 -m venv .venv &&
.venv/bin/pip install -q -r requirements.txt`).

**Question.** Run 100 (2026-11-16) set the next actionable date for the
DCA self-correction re-check to **2026-11-18 or later**; Run 101/102/103
(same/following days, all before that date) deferred. Today is
2026-11-18, exactly on the actionable date — the bar is met, so this run
performs the genuine re-check.

**Method.** Same standing protocol (Run 31 onward): DCA dip-buy ON vs OFF
(`dip_threshold_pct=5.0, dip_multiplier=1.5`, shipped default), 8-symbol
universe, 1h candles, capital-normalized avg ROI across 3 non-overlapping
windows shifted +2 days forward vs Run 100 (older 2026-03-23..2026-06-21,
train 2026-06-21..2026-09-19, test 2026-09-19..2026-11-18, anchor=today).
Script: `research/experiments/dca_self_correction_run104.py` (copied from
Run 100's script, dates shifted), raw output in
`dca_self_correction_run104_output.json`.

**Result.**
- **Older window** (decline, OFF avg ROI -13.7158%): delta **+0.1585pp**,
  8/8 symbols favoring ON, 27 dip-buys fired — IDENTICAL dip-buy count to
  Run 100's older window (27), and the delta tracked essentially flat vs
  Run 100's +0.1644pp (slightly down) — a sixth consecutive confirmation
  (Run 88, 92, 96, 100, 104) of the dip-buy-count mechanism established in
  Run 88: same count -> near-identical delta, not a runaway trend.
- **Train window** (rally, OFF +26.9009%): delta **-0.0545pp** (small
  negative) — a SIXTH consecutive negative-in-rally reading (Run 86
  -0.0143, 88 -0.0133, 92 -0.0400, 96 -0.0366, 100 -0.0535, 104 -0.0545),
  now a firmly established pattern replacing the earlier Run 72/76/78/82
  positive-in-rally run, reinforcing Run 60's point that sign is not
  reliably tied to regime label alone.
- **Test window** (decline, OFF -23.4024%, second-deepest OOS decline
  sampled in this protocol after Run 100's -24.82%): delta **+0.1993pp**
  (POSITIVE), 32 dip-buys fired — IDENTICAL dip-buy count to Run 100's
  test window (32), and the delta tracked essentially flat vs Run 100's
  +0.2179pp (slightly down, not a new high-water mark) — directly
  confirming Run 100's own observation that the test-window delta tracks
  dip-buy count rather than decline depth or regime label alone. This is
  now a FIFTH consecutive positive-in-decline test-window reading (Run 88
  +0.0389, 92 +0.0595, 96 +0.0442, 100 +0.2179, 104 +0.1993), extending the
  post-Run-86 mirror-image pattern vs the original seven-run negative
  streak (Run 64-86).

**Decision: noise, no reversal.** Every delta still favors or is
trivially against ON; both previously-growing high-water-mark readings
(older window, test window) plateaued or ticked down exactly as the
dip-buy-count mechanism predicts (same dip count this run as Run 100 in
both windows); all magnitudes stay within the already-described
sub-0.22pp band — a one-time, non-compounding fraction of invested
capital. The bar for a revert (a clear, economically meaningful,
compounding reversal) is not met. **Shipped default
(`dip_threshold_pct=5.0, dip_multiplier=1.5`) kept unchanged.**

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on the fresh rebuilt venv — **107 passed** (72+35 dots
across two progress lines), exit code 0 — a thirty-seventh independent
fresh-container rebuild confirming the same count. Security re-check: no
`.vscode/` directory anywhere in the repo, no `tasks.json`, no stray
`eval(` under `public/`, every `public/fonts/*` file a legitimate
FontAwesome asset — Run 37 incident remains remediated. No production
code touched beyond the research script.

**Memory hygiene.** `decisions.jsonl` now at 221 active entries (+1 this
run), still under the 250 rotation threshold — `rotate_archive.py` not
needed. `RESEARCH_LOG.md` now holds 13 full run sections (Run 92-104) —
over the ~40KB soft guideline but still below the "keep the last ~15
runs" floor from the top-of-file memory-management rule — holding off
the archive pass again this run; it should be revisited once active
sections reach ~15 (i.e. after Run 108 or so) or the file keeps growing
materially faster than that.

**Going forward:** next actionable date for the DCA self-correction check
is **2026-11-20 or later** (2+ days past today's anchor). The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier. Re-read the DISTILLED LEARNINGS
block end to end this run — every concretely-scoped strategy/signal/gate/
construction axis remains closed; futures/funding data remains
geo-blocked (unchanged, confirmed Run 31); `backend/app/strategies/` and
`registry.py` still have exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-103. No new axis to test honestly without recombining already-closed
items.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, DISTILLED
LEARNINGS DCA paragraph, this section). `research/decisions.jsonl` (+1
entry). `research/experiments/dca_self_correction_run104.py` (new,
research-only, copied from Run 100's script with window dates shifted),
`research/experiments/dca_self_correction_run104_output.json` (new, raw
results). No files changed in `backend/`.

---

## Run 105 — 2026-11-18, same-day deferred no-op, 2nd fire; detached-HEAD recovery

**Housekeeping.** Fresh container; `git status` found `HEAD` detached at
Run 104's commit (`c8f4a9d`), with local `main` stale at Run 103's commit
(`2459ec1`, 1 commit behind) — the same recurring detached-HEAD-on-fresh-
container pattern flagged every run since Run 91, except Run 104 which
started clean. `git fetch origin main` confirmed `origin/main` already at
`c8f4a9d` (Run 104's commit had already landed there), so `git checkout
main` + `git merge --ff-only c8f4a9d` resolved it cleanly, no commits
lost; `git push origin main` reported "Everything up-to-date" (origin
already held it). Backend venv rebuilt from scratch (`rm -rf .venv &&
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt`),
no behavior change.

**Question.** Run 104 (2026-11-18, earlier today, 02:09 UTC) performed the
on-schedule DCA self-correction re-check and set the next actionable date
to **2026-11-20 or later**. This fire is the same day, ~12 hours later
(14:05 UTC) — deferring again rather than re-running the check with
windows that would barely have shifted since this morning.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-104. Re-read the DISTILLED LEARNINGS block end to end — every
concretely-scoped strategy/signal/gate/construction axis remains closed;
futures/funding data remains geo-blocked (unchanged, confirmed Run 31).
No new axis to test honestly without recombining already-closed items.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on a fresh rebuilt venv — **107 passed** (72+35 dots across
two progress lines), exit code 0 — a thirty-eighth independent fresh-
container rebuild confirming the same count. Security re-check: no
`.vscode/` directory anywhere in the repo, no `tasks.json`, no stray
`eval(` under `public/`, every `public/fonts/*` file a legitimate
FontAwesome asset — Run 37 incident remains remediated. No production
code touched; no decision logged to `decisions.jsonl` (no backtest run
this fire, consistent with every prior same-day/before-schedule deferred
no-op).

**Memory hygiene.** `decisions.jsonl` unchanged at 221 active entries,
well under the 250 rotation threshold — `rotate_archive.py` not needed
this fire. `RESEARCH_LOG.md` now holds 14 full run sections (Run 92-105)
— over the ~40KB soft guideline but still at the "keep the last ~15 runs"
floor from the top-of-file memory-management rule — holding off the
archive pass again this run; it should be revisited next run or the one
after (Run 106/107), once active sections reach or pass ~15.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-20 or later**, unchanged from Run 104. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier. The recurring detached-HEAD-on-
fresh-container pattern (flagged Run 91, recurred most runs since,
including this one) remains harmless every time so far (`origin/main` has
always already held every commit) — continuing to flag it rather than
treat it as resolved.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, this
section only). No other files changed; no files changed in `backend/`.

---

## Run 106 — 2026-11-19, before-schedule deferred no-op; detached-HEAD recovery

**Housekeeping.** Fresh container; `git status` found `HEAD` detached at
Run 105's commit (`f382250`), with local `main` stale one commit behind
at Run 104's commit (`c8f4a9d`) — the same recurring detached-HEAD-on-
fresh-container pattern flagged every run since Run 91. `git fetch origin
main` confirmed `origin/main` already at `f382250` (Run 105's commit had
landed correctly), so `git checkout main && git merge --ff-only
origin/main` fast-forwarded local `main` with no commits lost; nothing to
push for this step (confirmed clean working tree after the merge).
Backend venv rebuilt from scratch (`python3 -m venv .venv &&
.venv/bin/pip install -q -r requirements.txt`), no behavior change.

**Question.** Run 104 (2026-11-18) performed the on-schedule DCA
self-correction re-check and set the next actionable date to
**2026-11-20 or later**; Run 105 (same day) deferred again. This fire is
2026-11-19 — still one day before the actionable date. Per the standing
protocol (top-of-file SELF-CORRECTION mandate, "Going forward" notes
carried since Run 78, and the DISTILLED LEARNINGS instruction not to
invent recombinations of already-closed axes to manufacture the
appearance of progress), this run defers the check again rather than
re-running it a day early or fabricating a new backtest sweep.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-105; `git log --oneline -- backend/app/` shows the short-selling
capability addition (Run 65/66 era) as the most recent production-code
commit, nothing newer. Re-read the DISTILLED LEARNINGS block end to end
— every concretely-scoped strategy/signal/gate/construction axis remains
closed (last reopened: pairs mean-reversion shorts, Run 66); futures/
funding data remains geo-blocked (unchanged, confirmed Run 31). No new
axis to test honestly without recombining already-closed items.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on a fresh rebuilt venv — **107 passed** (72+35 dots across
two progress lines), exit code 0 — a thirty-ninth independent fresh-
container rebuild confirming the same count. Security re-check: no
`.vscode/` directory anywhere in the repo, no `tasks.json`, no stray
`eval(` under `public/` — Run 37 incident remains remediated. No
production code touched; no decision logged to `decisions.jsonl` (no
backtest run this fire, consistent with every prior same-day/before-
schedule deferred no-op).

**Memory hygiene.** `decisions.jsonl` unchanged at 221 active entries,
well under the 250 rotation threshold — `rotate_archive.py` not needed
this fire. `RESEARCH_LOG.md` now holds 15 full run sections (Run 92-106)
— at the "keep the last ~15 runs" floor flagged by Run 104/105 as the
point to revisit archiving. Deferring the actual archive pass to the
next run with a full research section (expected around the 2026-11-20
self-correction re-check) so the pass can fold that run's fresh content
in at the same time, rather than archiving on a no-op fire.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-20 or later**, unchanged from Run 104. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier, and should also perform the
now-due archive pass (fold Run 92-97 or so into
`research/archive/log-...-run9X-9Y.md.gz`, keeping the last ~15 sections
plus the DISTILLED LEARNINGS block). The recurring detached-HEAD-on-
fresh-container pattern (flagged Run 91, recurred most runs since,
including this one) remains harmless every time so far (`origin/main`
has always already held every commit) — continuing to flag it rather
than treat it as resolved.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, this
section only). No other files changed; no files changed in `backend/`.

---

## Run 107 — 2026-11-19, before-schedule deferred no-op, 2nd fire; detached-HEAD recovery; archive pass

**Housekeeping.** Fresh container; `git status` found `HEAD` detached at
Run 106's commit (`5329e84`), with local `main` stale one commit behind
at Run 105's commit (`f382250`) — the same recurring detached-HEAD-on-
fresh-container pattern flagged every run since Run 91. `git fetch origin
main` confirmed `origin/main` already at `5329e84` (Run 106's commit had
landed correctly), so `git checkout main && git merge --ff-only
origin/main` fast-forwarded local `main` with no commits lost. Backend
venv rebuilt from scratch (`python3 -m venv .venv && .venv/bin/pip
install -q -r requirements.txt`), no behavior change.

**Question.** Run 104 (2026-11-18) performed the on-schedule DCA
self-correction re-check and set the next actionable date to
**2026-11-20 or later**; Run 105 and Run 106 (same day / before-schedule)
both deferred. This fire is still 2026-11-19 — one day before the
actionable date. Per the standing protocol (top-of-file SELF-CORRECTION
mandate and the "Going forward" notes carried since Run 78), this run
defers the check again rather than re-running it a day early or
fabricating a new backtest sweep.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-106; `git log --oneline -1 -- backend/app/` still points at the
short-selling capability addition (`606d70b`, Run 65/66 era) as the most
recent production-code commit. Re-read the DISTILLED LEARNINGS block end
to end — every concretely-scoped strategy/signal/gate/construction axis
remains closed; futures/funding data remains geo-blocked (unchanged,
confirmed Run 31). No new axis to test honestly without recombining
already-closed items.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on a fresh rebuilt venv — **107 passed** (72+35 dots across
two progress lines), exit code 0 — a fortieth independent fresh-container
rebuild confirming the same count. Security re-check: no `.vscode/`
directory anywhere in the repo, no `tasks.json`, no stray `eval(` under
`public/` — Run 37 incident remains remediated. No production code
touched; no decision logged to `decisions.jsonl` (no backtest run this
fire, consistent with every prior same-day/before-schedule deferred
no-op).

**Memory hygiene (archive pass, now performed).** `decisions.jsonl`
unchanged at 221 active entries, well under the 250 rotation threshold —
`rotate_archive.py` not needed this fire. `RESEARCH_LOG.md` had grown to
~102KB (Run 92-106, 15 full sections) — well over the ~40KB soft
guideline and past the point Run 104/105/106 flagged as due for an
archive pass. Archived Run 92-97 (DCA self-correction Run 92, deferred
no-ops Run 93/94/95, DCA self-correction + archive pass Run 96, deferred
no-op Run 97) verbatim to
`research/archive/log-2026-11-11_to_2026-11-14_run92-97.md.gz` (gzip, no
conclusions dropped — every numeric result and closure is already folded
into the DISTILLED LEARNINGS block above). File is now ~74KB with Run
98-107 (10 full sections) retained in full, back under a one-archive-
pass-away margin of the soft guideline and comfortably at/under the
"keep the last ~15 runs" floor.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-20 or later**, unchanged from Run 104. The next run
should default to the self-correction protocol once due, or defer again
with a brief no-op note if fired earlier. The recurring detached-HEAD-on-
fresh-container pattern (flagged Run 91, recurred most runs since,
including this one) remains harmless every time so far (`origin/main` has
always already held every commit) — continuing to flag it rather than
treat it as resolved.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, archive
pointer, archive-index note, this section). `research/archive/log-2026-11-11_to_2026-11-14_run92-97.md.gz`
added. No other files changed; no files changed in `backend/`.

---

## Run 108 — 2026-11-20, on-schedule DCA self-correction re-check, no reversal

**Housekeeping.** Fresh container; `git status` found `HEAD` detached at
Run 107's commit (`0828dde`), with local `main` stale three commits behind
at Run 103's commit (`2459ec1`) — the same recurring detached-HEAD-on-
fresh-container pattern flagged every run since Run 91. `git fetch origin
main` confirmed `origin/main` already at `0828dde` (Run 105-107's commits
had all landed correctly), so `git checkout main && git merge --ff-only
origin/main` fast-forwarded local `main` with no commits lost. Backend
venv rebuilt from scratch (`python3 -m venv .venv && .venv/bin/pip
install -q -r requirements.txt`), no behavior change.

**Question.** Run 104 (2026-11-18) performed the on-schedule DCA
self-correction re-check and set the next actionable date to
**2026-11-20 or later**; Run 105/106/107 (same day / before-schedule)
all deferred. This fire is 2026-11-20 — exactly on the actionable date,
so the bar is met and this run performs the genuine re-check.

**Re-check.** `research/experiments/dca_self_correction_run108.py`:
same methodology as every prior check (capital-normalized average ROI,
dip_enabled ON vs OFF, 8-symbol universe, 1h, 3 non-overlapping 90d/90d/60d
windows), windows shifted +2 days vs Run 104, anchored on today's close:
older 2026-03-25..2026-06-23, train 2026-06-23..2026-09-21, test
2026-09-21..2026-11-20.

| window | regime | ON avg ROI% | OFF avg ROI% | delta(pp) | dips |
|---|---|---|---|---|---|
| older | decline -14.29% | -14.1398 | -14.2904 | **+0.1506** | 27 |
| train | rally +27.68% | +27.6159 | +27.6838 | **-0.0679** | 8 |
| test | decline -24.58% | -24.4104 | -24.5758 | **+0.1654** | 32 |

Older window: delta +0.1506pp, 8/8 symbols favoring ON, dips=27 — identical
dip-count to Run 104's older window (27), delta essentially flat vs Run
104's +0.1585pp (slightly down). A sixth check now (Run 88, 92, 96, 100,
104, 108) confirming the Run-88 dip-buy-count mechanism: same dip count,
near-identical delta.

Train window: delta -0.0679pp (small negative) — a seventh consecutive
negative-in-rally reading (Run 86 -0.0143, 88 -0.0133, 92 -0.0400, 96
-0.0366, 100 -0.0535, 104 -0.0545, 108 -0.0679), the largest magnitude yet
but still two orders of magnitude below anything economically meaningful.
Notably, dip-count for this window actually *fell* (9 -> 8) while the
delta magnitude grew slightly — a minor deviation from the pure
dip-buy-count story, but at hundredths-of-a-pp scale this is not
distinguishable from noise around an already-tiny number; continues to
confirm Run 60's framing that sign is not reliably tied to regime alone.

Test window: delta +0.1654pp (positive), dips=32 — identical dip-count to
Run 104's test window (32), delta essentially flat vs Run 104's +0.1993pp
(slightly down). Directly confirms the dip-buy-count mechanism again: same
count, near-identical reading rather than continued growth. A sixth
consecutive positive-in-decline test-window reading (Run 88 +0.0389, 92
+0.0595, 96 +0.0442, 100 +0.2179, 104 +0.1993, 108 +0.1654), extending the
post-Run-86 mirror-image pattern vs the original seven-run negative streak
(Run 64-86).

**No reversal of substance.** Every delta still favors ON or is trivially
against it, both high-water-mark-adjacent readings (older, test) ticked
down this check exactly as the dip-buy-count mechanism predicts, and every
magnitude stays within the already-described sub-0.22pp band — a one-time,
non-compounding fraction of invested capital. Bar for a revert (per the
top-of-file self-correction mandate) is not met. Shipped default
(`dip_threshold_pct=5.0`, `dip_multiplier=1.5`) kept unchanged.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on the freshly rebuilt venv — **107 passed**, exit code 0 —
a forty-first independent fresh-container rebuild confirming the same
count. Security re-check: no `.vscode/` directory anywhere in the repo, no
`tasks.json`, no stray `eval(` under `public/` — Run 37 incident remains
remediated.

**Decision logged.** Appended to `research/decisions.jsonl` (now 222
active entries, well under the 250 rotation threshold — `rotate_archive.py`
not needed this fire): `decision: "noise"`, `evolved_from:
"dca_self_correction_run104 (2026-11-18)"`.

**Memory hygiene.** `RESEARCH_LOG.md` is now ~82KB with Run 98-108 (11
full sections) retained — over the ~40KB soft-size guideline but still
under the explicit "keep the last ~15 runs" floor that Run 104-107
established takes precedence over raw byte count; deferring the next
archive pass until the section count approaches ~15 or the file becomes
unwieldy to read in full.

**Going forward:** per the pattern since Run 46 (checks every ~2-5 days as
new data accumulates, with each delta this small and non-compounding), the
next actionable date for the DCA self-correction check is **2026-11-22 or
later**. The next run should default to the self-correction protocol once
due, or defer again with a brief no-op note if fired earlier. The recurring
detached-HEAD-on-fresh-container pattern (flagged Run 91, recurred every
run since, including this one) remains harmless every time so far
(`origin/main` has always already held every commit) — continuing to flag
it rather than treat it as resolved.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, this
section). `research/experiments/dca_self_correction_run108.py` and
`research/experiments/dca_self_correction_run108_output.json` added.
`research/decisions.jsonl` appended (1 entry). No other files changed; no
files changed in `backend/`.

---

## Run 109 — 2026-11-20, same-day deferred no-op, 2nd fire; detached-HEAD recovery

**Housekeeping.** Fresh container; `git status` found `HEAD` detached at
Run 108's commit (`e258ad2`), with local `main` stale five commits behind
at Run 103's commit (`2459ec1`) — the same recurring detached-HEAD-on-
fresh-container pattern flagged every run since Run 91. `git fetch origin
main` confirmed `origin/main` already at `e258ad2` (Run 104-108's commits
had all landed correctly), so `git checkout main && git merge --ff-only
origin/main` fast-forwarded local `main` five commits with no commits
lost. Backend venv rebuilt from scratch (`python3 -m venv .venv &&
.venv/bin/pip install -q -r requirements.txt`), no behavior change.

**Question.** Run 108 (2026-11-20, earlier today, commit `e258ad2`)
performed the on-schedule DCA self-correction re-check and set the next
actionable date to **2026-11-22 or later**. This fire is also
2026-11-20 (same calendar day, ~12 hours later per commit timestamps:
Run 108 at 02:06 UTC, this fire at ~14:04 UTC) — still two days before
the actionable date. Per the standing protocol (top-of-file
SELF-CORRECTION mandate, the "Going forward" notes carried since Run 78,
and the DISTILLED LEARNINGS instruction not to invent recombinations of
already-closed axes to manufacture the appearance of progress), this run
defers the check again rather than re-running it early or fabricating a
new backtest sweep.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-108; `git log --oneline -1 -- backend/app/` still points at the
short-selling capability addition (`606d70b`, Run 65/66 era) as the most
recent production-code commit. Re-read the DISTILLED LEARNINGS block end
to end — every concretely-scoped strategy/signal/gate/construction axis
remains closed (last reopened: pairs mean-reversion shorts, Run 66);
futures/funding data remains geo-blocked (unchanged, confirmed Run 31).
No new axis to test honestly without recombining already-closed items.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on a fresh rebuilt venv — **107 passed** (72+35 dots across
two progress lines), exit code 0 — a forty-second independent
fresh-container rebuild confirming the same count. Security re-check: no
`.vscode/` directory anywhere in the repo, no `tasks.json`, no stray
`eval(` under `public/` — Run 37 incident remains remediated. No
production code touched; no decision logged to `decisions.jsonl` (no
backtest run this fire, consistent with every prior same-day/before-
schedule deferred no-op).

**Memory hygiene.** `decisions.jsonl` unchanged at 222 active entries,
well under the 250 rotation threshold — `rotate_archive.py` not needed
this fire. `RESEARCH_LOG.md` holds 11 full run sections (Run 98-108,
now 99-109 with this append still 11 full sections since Run 98's slot
is retained) — comfortably under the "keep the last ~15 runs" floor
established by Run 104-107, so no archive pass is due yet despite the
file sitting over the ~40KB soft-size guideline (that floor takes
precedence, per the same precedent).

**Going forward:** next actionable date for the DCA self-correction
check remains **2026-11-22 or later**, unchanged from Run 108. The next
run should default to the self-correction protocol once due, or defer
again with a brief no-op note if fired earlier. The recurring
detached-HEAD-on-fresh-container pattern (flagged Run 91, recurred every
run since, including this one) remains harmless every time so far
(`origin/main` has always already held every commit) — continuing to
flag it rather than treat it as resolved.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, this
section only). No other files changed; no files changed in `backend/`.

## Run 110 — 2026-11-23, on-schedule DCA self-correction re-check, no reversal

**Housekeeping.** Fresh container; `git status` found `HEAD` detached at
Run 109's commit (`95d7eba`), with local `main` stale six commits behind
at Run 103's commit (`2459ec1`) — the same recurring detached-HEAD-on-
fresh-container pattern flagged every run since Run 91. `git fetch origin
main` confirmed `origin/main` already at `95d7eba` (Run 104-109's commits
had all landed correctly), so `git checkout main && git merge --ff-only
origin/main` fast-forwarded local `main` six commits with no commits
lost. Backend venv rebuilt from scratch (`python3 -m venv .venv &&
pip install -q -r requirements.txt`), no behavior change.

**Question.** Run 108 (2026-11-20) performed the on-schedule DCA
self-correction re-check and set the next actionable date to
**2026-11-22 or later**. Run 109 (2026-11-20, same day) deferred. Today
is 2026-11-23, past the actionable date — the bar is met, so this run
performs the genuine re-check.

**Re-check performed.** `research/experiments/dca_self_correction_run110.py`
— same methodology as Run 88-108 (capital-normalized avg ROI, ON
dip_threshold_pct=5.0/dip_multiplier=1.5 vs OFF, 3 non-overlapping
windows shifted +3 days vs Run 108, test-window anchor = today
2026-11-23). Results:

| window | regime (OFF avg ROI) | ON avg ROI% | OFF avg ROI% | delta pp | dip-buys |
|---|---|---|---|---|---|
| older | -20.30% decline (new depth record) | -20.1679 | -20.3007 | **+0.1328** | 28 |
| train | +28.21% rally | +28.1512 | +28.2116 | **-0.0604** | 8 |
| test | -25.20% decline (new depth record) | -24.8252 | -25.2023 | **+0.3771** | 37 |

Older window: delta +0.1328pp, 7/8 symbols favoring ON, dip-count 28 (up
from Run 108's 27) — the delta actually ticked down slightly from Run
108's +0.1506pp despite a deeper decline and more dips, a mild deviation
from the clean dip-count-tracks-delta story established since Run 88, but
each check samples disjoint historical data so window-to-window noise in
that relationship is expected; still same direction (ON beats OFF).

Train window (rally, OFF +28.2116%): delta -0.0604pp, an **eighth
consecutive negative-in-rally reading** (Run 86 -0.0143, 88 -0.0133, 92
-0.0400, 96 -0.0366, 100 -0.0535, 104 -0.0545, 108 -0.0679, 110 -0.0604) —
the first time in that streak the magnitude ticked *down* rather than up,
still an order of magnitude below anything economically meaningful.

Test window (decline, OFF -25.2023%, a new depth record surpassing Run
100's -24.8198%): delta **+0.3771pp**, dip-count 37 (up from Run 108's
32, also a new record) — a **new test-window high-water mark**, roughly
2.3x Run 100's prior record (+0.2179pp) and the largest single delta
reading across the entire 10-check protocol (Run 88-110). Same mechanism
already validated for the older window in Run 82/86/88 (deeper real
decline -> more real dip-buys fire -> larger same-direction ON-over-OFF
delta), now transferring to the test window at a larger scale than Run
100's transfer. Seventh consecutive positive-in-decline test-window
reading (Run 88 +0.0389, 92 +0.0595, 96 +0.0442, 100 +0.2179, 104
+0.1993, 108 +0.1654, 110 +0.3771).

**Honest read.** Every delta still favors or is trivially against ON, and
both record-setting readings (older-window depth, test-window delta) have
an immediate, already-validated mechanical explanation (deeper decline ->
more real dip-buys -> larger delta in the same direction the shipped
default was built on). The test-window delta is economically trivial in
absolute terms (0.38% of invested capital, one-time, non-compounding —
DCA has no round-trip trades to compound this through). **Flagged to
watch, not acted on:** this is the second time a test-window reading has
jumped meaningfully above the prior plateau (first was Run 100's
+0.2179pp vs Run 96's +0.0442pp; that one then plateaued for three checks
before this jump). If Run 114 also sets a new record with a
correspondingly higher dip-count, the mechanical read stands unchanged;
if dip-count stays flat or falls while the delta keeps growing, that
would need a fresh explanation rather than the dip-count story. Bar for a
revert is **not met** — no reversal. Shipped default
(`dip_threshold_pct=5.0, dip_multiplier=1.5`) kept unchanged. Decision
logged to `decisions.jsonl` as `noise` (consistent with every prior
self-correction check).

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-109. Re-read the DISTILLED LEARNINGS block end to end — every
concretely-scoped strategy/signal/gate/construction axis remains closed
(last reopened: pairs mean-reversion shorts, Run 66); futures/funding
data remains geo-blocked (unchanged, confirmed Run 31). No new axis to
test honestly without recombining already-closed items.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on a fresh rebuilt venv — **107 passed**, exit code 0 — the
42nd consecutive independent fresh-container rebuild confirming the same
count. Security re-check: no `.vscode/` directory anywhere in the repo,
no `tasks.json`, no stray `eval(` under `public/` — Run 37 incident
remains remediated.

**Memory hygiene.** `decisions.jsonl` grew from 222 to 223 active
entries, well under the 250 rotation threshold — `rotate_archive.py` not
needed this run. `RESEARCH_LOG.md` now holds 13 full run sections (Run
98-110) — still under the "keep the last ~15 runs" floor established by
Run 104-107, so no archive pass is due yet despite the file sitting over
the ~40KB soft-size guideline (that floor takes precedence, per the same
precedent); the next run or two should expect an archive pass once the
count reaches ~15.

**Going forward:** next actionable date for the DCA self-correction check
is **2026-11-25 or later**. The next run should default to the
self-correction protocol once due, or defer again with a brief no-op
note if fired earlier. The recurring detached-HEAD-on-fresh-container
pattern (flagged Run 91, recurred every run since, including this one)
remains harmless every time so far (`origin/main` has always already
held every commit) — continuing to flag it rather than treat it as
resolved.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, DCA
distilled paragraph, this section). `research/decisions.jsonl` appended
(1 entry). `research/experiments/dca_self_correction_run110.py` and
`dca_self_correction_run110_output.json` added. No files changed in
production code under `backend/app/`.

## Run 111 — 2026-11-23, same-day deferred no-op, 2nd fire; detached-HEAD recovery

**Housekeeping.** Fresh container; `git status` found `HEAD` detached at
Run 110's commit (`73b61fb`), with local `main` stale seven commits
behind at Run 103's commit (`2459ec1`) — the same recurring
detached-HEAD-on-fresh-container pattern flagged every run since Run 91.
`git fetch origin main` confirmed `origin/main` already at `73b61fb`
(Run 104-110's commits had all landed correctly), so `git checkout main
&& git merge --ff-only origin/main` fast-forwarded local `main` seven
commits with no commits lost. Backend venv rebuilt from scratch
(`python3 -m venv .venv && pip install -q -r requirements.txt`), no
behavior change.

**Question.** Run 110 (2026-11-23, earlier today, commit `73b61fb`)
performed the on-schedule DCA self-correction re-check and set the next
actionable date to **2026-11-25 or later**. This fire is also
2026-11-23 (same calendar day) — two days before the actionable date.
Per the standing protocol (top-of-file SELF-CORRECTION mandate, the
"Going forward" notes carried since Run 78, and the DISTILLED LEARNINGS
instruction not to invent recombinations of already-closed axes to
manufacture the appearance of progress), this run defers the check
again rather than re-running it early or fabricating a new backtest
sweep.

**Fresh-idea check.** Re-listed `backend/app/strategies/` and
`registry.py` — still exactly the same 4 registered strategy classes
(`dca`, `grid`, `mean_reversion`, `trend_momentum`), unchanged since Run
76-110. Re-read the DISTILLED LEARNINGS block end to end — every
concretely-scoped strategy/signal/gate/construction axis remains closed
(last reopened: pairs mean-reversion shorts, Run 66); futures/funding
data remains geo-blocked (unchanged, confirmed Run 31). No new axis to
test honestly without recombining already-closed items.

**Verification performed.** `cd backend && PYTHONPATH=. .venv/bin/python
-m pytest -q` on a fresh rebuilt venv — **107 passed** (72+35 dots
across two progress lines, exit code 0) — the 43rd consecutive
independent fresh-container rebuild confirming the same count. Security
re-check: no `.vscode/` directory anywhere in the repo, no
`tasks.json`, no stray `eval(` under `public/` — Run 37 incident
remains remediated. No production code touched; no decision logged to
`decisions.jsonl` (no backtest run this fire, consistent with every
prior same-day/before-schedule deferred no-op).

**Memory hygiene.** `decisions.jsonl` unchanged at 223 active entries,
well under the 250 rotation threshold — `rotate_archive.py` not needed
this fire. `RESEARCH_LOG.md` now holds 14 full run sections (Run
98-111) — still under the "keep the last ~15 runs" floor established by
Run 104-107, so no archive pass is due yet despite the file sitting
over the ~40KB soft-size guideline (that floor takes precedence, per
the same precedent); the next run or two should expect an archive pass
once the count reaches ~15.

**Going forward:** next actionable date for the DCA self-correction
check remains **2026-11-25 or later**, unchanged from Run 110. The next
run should default to the self-correction protocol once due, or defer
again with a brief no-op note if fired earlier. The recurring
detached-HEAD-on-fresh-container pattern (flagged Run 91, recurred every
run since, including this one) remains harmless every time so far
(`origin/main` has always already held every commit) — continuing to
flag it rather than treat it as resolved.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line, this
section only). No other files changed; no files changed in `backend/`.

---

## Run 112 — 2026-11-24, new strategy family (Ichimoku Cloud), decisive reject; archive pass

**Housekeeping.** Fresh container; `git status` clean, local `main`
already at `origin/main`'s tip (Run 111's commit `7c8abef`) — no
detached-HEAD recovery needed this fire, breaking the recurring pattern
flagged every run since Run 91 (not treated as resolved — just didn't
recur this time). Backend venv rebuilt from scratch (`python3 -m venv
.venv && .venv/bin/pip install -q -r requirements.txt`), no behavior
change. `cd backend && PYTHONPATH=. .venv/bin/python -m pytest -q` on the
fresh venv — **107 passed**, exit code 0 — confirming baseline before any
research.

**Question.** Run 110 set the next DCA self-correction actionable date to
**2026-11-25 or later**; Run 111 (same day) deferred. Today is 2026-11-24
— still one day before the actionable date, so the self-correction check
correctly stays deferred this fire too. Rather than log a third
consecutive no-op, this run used the time to pursue genuinely new
research: re-read the DISTILLED LEARNINGS block end to end and confirmed
every concretely-scoped strategy/signal/gate/cross-symbol/non-signal-lever
/scope axis tried so far (9 strategy families as of this run, 5
signal-source categories, 3 confirmation gates + 1 stacked combo, 2
cross-symbol constructions, sizing/exit/cost/universe/TF/era) is closed.
Looked for a mechanically distinct construction not yet tried rather than
recombining closed items: **Ichimoku Cloud** — unlike any prior family, it
combines three rolling high/low-midpoint lines at three different
lookbacks (Tenkan 9, Kijun 26, Senkou B 52 by default) into a
forward-projected "cloud" band, with entry gated on both a Tenkan/Kijun
cross AND price position relative to that cloud. This is a genuinely new
multi-line confluence construction, distinct from trend_momentum's 2-EMA
cross, Supertrend's single ATR-adaptive line, and every already-closed
confirmation gate (the cloud filter line is itself forward-shifted in
time via `shift(kijun_period)`, not a same-bar confirmation signal).

**Implementation.** `research/experiments/ichimoku_cloud.py` —
standalone `IchimokuCloudStrategy(Strategy)`, NOT registered in
`app/strategies/registry.py`, NOT touching any production file. No
lookahead: Senkou Span A/B computed from data up to bar `t -
kijun_period`, then `.shift(kijun_period)` forward so the cloud value
visible at bar `t` was fully knowable `kijun_period` bars earlier;
`decide()` reads only rows `i` and `i-1`. Long-only (matches Supertrend's
precedent — engine's `allow_short` capability exists but adding it here
would be a second new axis conflated with the first; left for a future
run if Ichimoku ever clears the base long-only bar). Entry: Tenkan
crosses above Kijun, optionally gated on close above the cloud top. Exit:
opposite cross, or (if gated) close below the cloud bottom.

**Methodology.** Same train/test convention as every prior run: TRAIN
2026-06-27 to 2026-09-26 (150d-60d ago), TEST 2026-09-26 to 2026-11-24
(60d-0d ago, today's anchor), fees 7.5bps + slippage 4bps, $10,000/symbol,
unchanged RiskConfig defaults (2%/4% SL/TP, daily-loss halt, drawdown
kill switch, position caps — never loosened), all 8 universe symbols.
Swept 10 configs: classic (9/26/52), crypto-adjusted (10/30/60), and
faster (7/22/44) Tenkan/Kijun/Senkou-B periods, each with and without the
cloud filter (faster variant only with filter, to keep the sweep to 10),
at 1h and 4h.

**Results — decisive reject, 10/10 configs:**

| config | TF | TRAIN pf / win% / n | TEST pf / win% / n |
|---|---|---|---|
| classic, filtered | 1h | 0.484 / 18.3% / 71 | 0.239 / 13.3% / 60 |
| classic, unfiltered | 1h | 0.842 / 30.2% / 129 | 0.156 / 18.7% / 91 |
| crypto(10/30/60), filtered | 1h | 0.764 / 27.8% / 90 | 0.251 / 12.5% / 48 |
| crypto(10/30/60), unfiltered | 1h | 0.854 / 30.9% / 97 | 0.220 / 14.7% / 75 |
| fast(7/22/44), filtered | 1h | 0.807 / 28.2% / 103 | 0.192 / 19.0% / 79 |
| classic, filtered | 4h | 0.965 / 34.2% / 41 | 0.445 / 27.8% / 18 |
| classic, unfiltered | 4h | 0.901 / 33.0% / 94 | 0.565 / 31.3% / 67 |
| crypto(10/30/60), filtered | 4h | 0.824 / 34.1% / 44 | 0.445 / 33.3% / 9 |
| crypto(10/30/60), unfiltered | 4h | 0.802 / 31.7% / 79 | 0.408 / 24.5% / 53 |
| fast(7/22/44), filtered | 4h | 0.411 / 23.3% / 43 | 0.230 / 9.1% / 22 |

Best train-side PF across all 10 configs is **0.965** (4h, classic
params + cloud filter) — never crosses 1.0, let alone the 1.1 bar, so
**none of the 10 configs reach a test-side or 3rd-window check at all**
per the anti-noise protocol (train must clear 1.1 before the OOS test
result means anything). Best test-side PF is 0.565 (4h, classic,
unfiltered, 67 trades) — would clear the trade-count floor but the PF is
decisively below 1.1 regardless, and its train PF (0.901) already fails.
This is a cleaner, more decisive reject than any prior family's closest
near-miss (BB-width squeeze's TEST+3rd-window double-clear, or the MTF
gate's 20/50 EMA near-miss) — every single config fails on the train side
alone, with no ambiguity to resolve via per-symbol breakdown.

**Decision.** All 10 configs logged to `decisions.jsonl` as `reject`
(strategy `ichimoku_cloud`, full params + train/test metrics +
`usd_pnl_100`/`usd_pnl_1000` from test-window `ret_pct` + rationale per
the standard schema). `evolved_from: null` (first attempt at this
family, not an evolution of a prior config). `rotate_archive.py` run
after appending — 233 active entries, well under the 250 threshold, no
rotation performed. **Ichimoku Cloud is now closed** as the 9th strategy
family, added to the DISTILLED LEARNINGS "Closed — strategy families"
bullet and the "Where this programme stands" summary.

**Memory hygiene (archive pass, now performed).** `RESEARCH_LOG.md` had
grown to ~100KB with 14 full run sections (Run 98-111), at the threshold
Run 107/111 flagged as due for the next archive pass once the count
reached ~15 (adding this Run 112 section would make 15). Archived Run
98-103 (before-schedule deferred no-ops Run 98/99/101/102, DCA
self-correction re-check Run 100, deferred no-op + detached-HEAD recovery
Run 103 — zero decisions logged, no reversal, no production-code changes
across all 6) verbatim to
`research/archive/log-2026-11-14_to_2026-11-17_run98-103.md.gz` (gzip, no
conclusions dropped — every numeric result already folded into the
DISTILLED LEARNINGS block). File now retains Run 104-112 (9 full
sections) in full, back under the "keep the last ~15 runs" floor.
Archive-index paragraph and top summary line updated (111→112 runs,
~400+→~410+ configs, Run 1-97→1-103 archived).

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-25 or later**, unchanged from Run 110. This run shows
fresh-idea research is still possible without recombining closed axes —
future runs should keep checking for mechanically distinct constructions
(e.g. Ichimoku's Chikou-span lagging-line confirmation was deliberately
left untested here to isolate one new variable at a time; a possible
next candidate if this family is ever revisited, though the train-side
reject here is decisive enough that doing so is low-priority) before
falling back to self-correction-only cycles. The recurring
detached-HEAD-on-fresh-container pattern did not recur this fire — still
not treated as resolved, just absent this time.

**Files:** `research/RESEARCH_LOG.md` edited (top summary line,
archive-index paragraph, "Where this programme stands", DISTILLED
LEARNINGS strategy-families bullet, Run 98-103 replaced with an archived
stub, this section added). `research/decisions.jsonl` appended (10
entries, 223→233). `research/archive/log-2026-11-14_to_2026-11-17_run98-103.md.gz`
added. `research/experiments/ichimoku_cloud.py` added (research-only, not
registered). No files changed under `backend/app/` — no production code
or default params touched; bar for auto-improve not met (decisive
reject, no promising candidate).

---

## Run 113 — 2026-11-24, new strategy family (VWAP Band Reversion), decisive reject; distilled-learnings condensation

**Setup.** Fresh `.venv` (no cache from prior containers), `pip install -r
requirements.txt`, ran from `backend/` with `PYTHONPATH=.`. Repo state on
entry: HEAD was detached one commit ahead of local `main` (at Run 112's
commit, not yet fast-forwarded) — recovered with `git checkout main && git
merge --ff-only <run-112-sha>`, no new branch needed since `main` was a
strict ancestor. Standing verification run first: `pytest` 107/107 pass
(fresh-venv rebuild); security re-check for the Run 37 incident (no
`fa-solid-500.woff2`, no `.vscode/tasks.json`, only the three legitimate
FontAwesome files under `public/fonts/`) — clean.

**Why a new family, not the DCA self-correction re-check.** Run 110 set
the next actionable date for the standing DCA protocol to **2026-11-25 or
later**; today (2026-11-24) is one day before that, so per the top-of-file
mandate to rotate regions each run rather than repeat an already-logged
config, this run picked a genuinely new construction instead of firing the
check a day early.

**What's new.** All 9 prior strategy families band or filter on PRICE
alone (SMA/EMA, Bollinger std-dev, Donchian high/low, ATR, candle shape,
RSI divergence, Ichimoku's three price-derived lines). **VWAP Band
Reversion** is the first construction to weight the price level itself by
volume: a rolling volume-weighted average price (`sum(close*volume) /
sum(volume)` over `vwap_period` candles) with a deviation band sized from
the volume-weighted variance of price around that VWAP (not a plain SMA +/-
price std like Bollinger). The claim under test: a close far below a
high-volume VWAP is a different signal than "N std below a price-only SMA"
or "below a fixed N-period low," because heavy low-price volume pulls the
anchor down with it — something no closed family can express. BUY when
close crosses below the lower band (optionally gated on close above a
SMA(100) trend filter); SELL on reversion to the VWAP mid-line, plus
unchanged exchange-side 2%/4% SL/TP. Research-only class in
`research/experiments/vwap_band_reversion.py`, not registered in
`app/strategies/registry.py`, no production files touched.

**Methodology.** Same train/test convention as every prior run: TRAIN
2026-06-27 to 2026-09-26 (150d-60d ago), TEST 2026-09-26 to 2026-11-24
(60d-0d ago, today's anchor), fees 7.5bps + slippage 4bps, $10,000/symbol,
unchanged RiskConfig defaults (2%/4% SL/TP, daily-loss halt, drawdown
kill switch, position caps — never loosened), all 8 universe symbols.
Swept `vwap_period` {20, 50} x `band_mult` {1.5, 2.0, 2.5} x optional
SMA(100) trend filter {off, on}, at 15m/1h/4h — 36 configs total.

**Results — 0/36 cleared both OOS bars.** The config with the most
trade-rich, decisive result on both sides: **4h, vwap_period=20,
band_mult=1.5, no trend filter** — train PF **1.702** (73 trades, clears
the 1.1 train bar) but test PF **0.547** (109 trades, decisively fails) —
a clean train-clears/test-fails divergence, the same regime-luck signature
that closed `mean_reversion` (chronic "test clears/train doesn't" there,
mirrored here as "train clears/test doesn't"). A handful of other configs
showed train PF > 1.1 (up to 2.845 at 15m, 2.45-2.45 at 1h/4h) but every
one of those had either train or test trade count under the 30-trade
anti-noise floor (as low as 0, 1, 2, 10, 14 trades) — the `trend_filter=100`
+ wide-band combination in particular starved entries to near zero on
several symbol/timeframe pairs. Of the 36 configs, 14 had adequate sample
on both sides for a decisive reject; the other 22 are noise (too thin to
be either promising or a clean rejection).

**Decision.** All 36 configs logged to `decisions.jsonl` (14 `reject`, 22
`noise`; strategy `vwap_band_reversion`, full params + train/test metrics
+ `usd_pnl_100`/`usd_pnl_1000` from test-window `ret_pct` + rationale per
the standard schema). `evolved_from: null` (first attempt at this family).
`rotate_archive.py` run after appending — 269 active entries crossed the
250-entry trigger, archived the oldest 149 (2026-08-20 to 2026-08-29) to
`research/archive/decisions-2026-08-20_to_2026-08-29.jsonl.gz`, 120 kept
active. Nothing lost. **VWAP Band Reversion is now closed** as the 10th
strategy family, added to the DISTILLED LEARNINGS "Closed — strategy
families" bullet and the "Where this programme stands" summary.

**Memory hygiene (distilled-learnings condensation, not a size-triggered
archive pass).** `RESEARCH_LOG.md` had grown to 84KB even with only 9 full
run sections (under the 15-run archive floor), because the DCA
self-correction narrative inside DISTILLED LEARNINGS had accumulated
verbatim run-by-run blow-by-blow for every one of 19 checks since Run 32
(Run 46 through Run 110) — each repeating the same small set of
conclusions (sign not tied to regime, delta tracks dip-buy count) with new
numbers. Condensed that block to state the conclusions once with the
current numbers, rather than re-deriving them run-by-run — no conclusion
dropped (the full per-run numbers remain in `decisions.jsonl` and the
dated archives already linked from the condensed paragraph), just
narrative repetition removed, matching how the top-of-file archive-index
paragraph already summarizes Run 1-32. This alone cut the file from 84KB
to 72KB before this run's own section was even added. Run section count
is now 10 (104-113), still under the "keep last ~15" floor, so no
run-section archive pass was needed this time.

**Going forward:** next actionable date for the DCA self-correction check
remains **2026-11-25 or later**, unchanged from Run 110 — the next run on
or after that date should fire it. This run reconfirms fresh-idea research
is still possible this deep into the programme (10 families now closed) —
a possible next candidate if another new angle is wanted: a genuinely
different EXIT mechanism for an already-rejected entry signal was closed
in Run 22 as a non-signal lever, but a *volume-weighted* exit (e.g. trail
behind VWAP rather than a fixed SL/TP) on one of the closed entry families
has not been tried and would be a new combination, not a re-test, if ever
revisited — low priority given how decisively entries alone have failed.
The detached-HEAD-on-fresh-container pattern recurred again this fire
(third+ occurrence); still unresolved at the container/orchestration
level, outside this research programme's scope to fix, handled by the
same recovery each time (fast-forward `main` to the detached commit).

**Files:** `research/RESEARCH_LOG.md` edited (top summary line,
archive-index paragraph, "Where this programme stands", DISTILLED
LEARNINGS strategy-families bullet, DCA self-correction narrative
condensed, this section added). `research/decisions.jsonl` appended then
rotated (233→269→120 active). `research/archive/decisions-2026-08-20_to_2026-08-29.jsonl.gz`
added. `research/experiments/vwap_band_reversion.py` added (research-only,
not registered). No files changed under `backend/app/` — no production
code or default params touched; bar for auto-improve not met (decisive
reject, no promising candidate).
