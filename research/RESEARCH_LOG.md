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

**121 runs, ~537+ configs, one standing positive finding (DCA dip-buy,
already shipped), zero adopted signal changes.** Full narrative for Run
1-120 is archived (see the archive-index paragraph and the "Run N-M —
archived" stub sections below); Run 121 is below in full. The
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
All 13 tried are rejected at every TF swept (mostly 1h/4h, full 1m-4h sweep
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
combination starving entries, to be anything but noise); **Keltner Channel
Breakout** (Run 116 — EMA midline +/- ATR*multiplier channel, BUY on a
fresh close-breakout above the upper band / SELL on close back below the
EMA midline; the first construction in the programme to directly trade a
volatility-adaptive channel BREAKOUT rather than fading it (mean_reversion,
VWAP Band Reversion), using it as a raw unsmoothed channel (Donchian), or
using it as a continuous ratcheting trend-follow state machine (Supertrend).
Swept ema_period{20,50} x atr_period{10,14} x multiplier{1.5,2.0,2.5} across
15m/1h/4h, 36 configs. 0/36 cleared both OOS bars — every adequately-sampled
(n>=30) test PF sat at 0.07-0.46, the only test PF above that touching 0.736
at n=19 (below the trade-count floor). Notable new result: 1h mult=2.0/2.5
pushed TRAIN PF to 1.74-1.97 (n=142-198, adequate sample) — a new all-time
train-PF record for the whole programme, beating Run 115's 1.135 — while
every 1h TEST PF collapsed to 0.08-0.23, the sharpest train-clears/
test-craters divergence yet recorded, sharper even than Run 115's. A
breakout (buy-strength) entry is, if anything, MORE prone to apparent
train-side overfitting than a fade or trend-follow entry: it concentrates
gains in whichever trending sub-period the train window happened to sample,
and none of that concentration survived into the held-out window);
**Stochastic RSI Crossover** (Run 117 — RSI(14) run through a rolling
stochastic min-max normalization, SMA-smoothed into %K/%D; BUY on a
bullish %K/%D crossover from the oversold zone, SELL on a bearish
crossover from the overbought zone; the first pure second-order
RSI-oscillator construction tried — distinct from trend_momentum's static
RSI threshold and from Price-vs-RSI Divergence's price-structure
comparison, and touching no price/volatility band at all. Swept
stoch_period{14,21} x zones{20/80,25/75} across 15m/1h/4h, 12 configs.
0/12 cleared both OOS bars. The only train PF>1.1 configs (15m,
stoch_period=21, both zone settings: train PF 1.167-1.225, adequate
n=32-35) both craterd on test (PF 0.396-0.457) — the same
train-clears/test-craters divergence as every prior family. 4h had
adequate test-side sample (n=40-73) but zero train-side support at all
(train PF 0.15-0.89, test PF 0.43-0.58) — the cleanest reject shape in the
sweep. 1h stoch_period=21 starved to 0-2 total trades (noise, not
evidence). Best test PF, 0.956 @1h stoch_period=14 zones=25/75, had only
n=24 trades (below the floor) and train PF 0.524 (fails train regardless));
**Parabolic SAR Stop-and-Reverse** (Run 120 — Wilder's SAR dot with
acceleration-factor path memory: AF starts at af_start, grows by af_step on
every new extreme the dot's side sets, capped at af_max, dot only ever
moves toward price until touched and flips; BUY on flip-to-bullish, SELL on
flip-to-bearish, long-only; the first stateful stop-and-reverse
construction with accelerating path memory tried — distinct from
Supertrend's fixed ATR*multiplier band (no acceleration concept), Donchian's
stateless rolling window (no trend-duration memory), every static/
EMA-anchored band (Keltner/VWAP/Bollinger/Ichimoku), and every
close-only/RSI-derived family (none use high/low extreme points directly).
Swept af_start{0.01,0.02} x af_step{0.01,0.02} x af_max{0.1,0.2} across
15m/1h/4h, 24 configs. 0/24 cleared both OOS bars — in fact 0/24 even
cleared the train-side PF>1.1 bar at an adequate sample, matching
Ichimoku's clean train-side-only rejection shape. Best train PF only 0.976
(1h, af_start=0.01/af_step=0.01/af_max=0.2, n=81 adequate) with test PF
collapsing to 0.146 (n=50); several af_start=0.02 / af_step=0.02 configs
starved to 0-6 train trades (dot tracked price too tightly for a flip to
register — noise, not evidence). One 15m config (af_start=0.02,
af_step=0.01, af_max=0.1) showed test PF 1.022 but n=29 (one short of the
30-trade floor) against a train side of n=6 — not a near-miss worth
re-sweeping); **On-Balance Volume (OBV) Trend Confirmation** (Run 121 —
pure cumulative volume-flow line, `OBV = cumsum(sign(close.diff()) *
volume)`, with its own multi-bar directional path memory built entirely
from volume, no price band or price-extreme concept at all; BUY on OBV
crossing above its own obv_ma_period-bar SMA, optionally gated by close
above a 50-bar price-trend SMA, SELL on the mirror bearish cross; the
first strategy family built purely from volume direction rather than
price/band/oscillator structure — distinct from every closed price-band
family (none touch volume) and from the already-closed relative-volume
gate (an instantaneous memoryless ratio filter, vs OBV's cumulative
directional running total used as the primary signal here). Swept
obv_ma_period{14,20,30} x use_trend_filter{False,True} across 15m/1h/4h,
18 configs. 0/18 cleared both OOS bars. Without the trend filter, OBV
crosses its own MA so rarely at 15m/1h that 12/18 configs starved to n=0
train trades (too smooth/monotone a line at those TFs without a
price-trend gate — noise, not evidence). The trend filter unlocked
adequate 4h-only train samples (n=29-35) by keeping the strategy flat
longer rather than by directly adding entries (confirmed via a BTC-only
debug run: unfiltered=24 vs filtered=26 trades on identical data — real
path-dependent dynamics, not a bug) — but train PF never reached 1.1 at
4h (0.513-0.631), so none had real train-side support. One 4h config
showed test PF 1.299 at n=6, five short of the 30-trade floor, with train
PF 0.631 also failing — not a near-miss worth re-sweeping). 1m/5m are
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
"fees are the bottleneck." **Volume-weighted trailing exit** (Run 115:
trend_momentum's unchanged EMA20/50+RSI+MACD entry, VWAP-trailing-stop
exit replacing the signal-side EMA-crossdown/RSI-blowoff/MACD-fade exit,
exchange SL/TP untouched; 18 configs, 15m/1h/4h x vwap_period{20,50} x
trail_mult{1.0,1.5,2.0}): 0/18 cleared both OOS bars. Notable new result:
4/6 1h configs and all 6 4h configs pushed TRAIN PF to 0.96-1.25 — a new
best-ever train PF for this entry family (previous record 0.99@15m,
bare strategy) — but every 1h test PF collapsed to 0.15-0.23 (adequate
sample, 58-70 trades), the most decisive train-clears/test-craters
divergence yet recorded (test PF far below even mean_reversion's typical
near-1.0 near-misses). 4h test was all-losing but too thin (10 trades) to
be decisive alone. **Generalization confirmed for a volume-weighted exit
specifically: a trailing exit tuned on volume-weighted price structure
still only amplifies train-window regime luck — it does not create edge,
and can make an already-marginal entry's apparent train-side quality
*worse* evidence of overfitting, not better.** Closes the one
concretely-named open thread from Run 113/114's distilled notes.
**Generalization: no mechanism layered on a PF<1 entry signal (size, exit
timing, exit price, exit price *source*, or cost) can manufacture edge
that isn't there.**

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
depth or regime label directly — confirmed by seven further checks (Run 92,
96, 100, 104, 108, 110, 114) where identical dip-counts across consecutive
windows produced near-identical deltas, and count changes moved the delta
in lockstep, with two now-documented exceptions where it did not: Run
114's test window (identical dip-count to Run 110, slightly *smaller*
delta, +0.3316pp vs +0.3771pp) and **Run 118's test window** (dip-count
*down* 2 vs Run 114, 35 vs 37, yet delta went *up* to +0.3638pp vs
+0.3316pp — the first time a drop in dip-count did not come with a drop in
delta). Both read as window-to-window noise on disjoint historical data
(not a re-measurement of the same window), not a break in the mechanism —
the sign and rough magnitude are unaffected either time. Test-window
dip-buy count and delta set successive depth/magnitude records through
Run 100 and Run 110 (+0.2179pp, then +0.3771pp, the largest single
reading in the 21-check protocol, dip-count 37), **plateaued at Run 114**
(+0.3316pp, same dip-count 37 as Run 110) and **ticked up slightly at Run
118** (+0.3638pp, dip-count down to 35) — always in the *same* direction
(ON beats OFF) the shipped default was built on, always a one-time,
non-compounding fraction of a percent of invested capital, never a
reversal. Train-window (rally) deltas have independently run negative for
ten straight checks (Run 86 through 118: -0.0143pp to -0.1146pp, the
magnitude record set at Run 114 then **ticking back down to -0.1018pp at
Run 118** on an identical dip-count of 11, confirming that record was a
one-off rather than the start of a trend), still two orders of magnitude
below anything economically meaningful. **No reversal across 21 checks
(Run 32-118); shipped default kept unchanged throughout. Next actionable
date: 2026-11-29 or later** (set by Run 118). See
`research/archive/log-2026-10-22_to_2026-10-27_run67-75.md.gz` (Run
67-75), `log-2026-10-28_to_2026-10-31_run76-80.md.gz` (Run 76-80),
`log-2026-11-04_to_2026-11-09_run86-88.md.gz` (Run 86-88),
`log-2026-11-09_to_2026-11-10_run89-91.md.gz` (Run 89-91),
`log-2026-11-11_to_2026-11-14_run92-97.md.gz` (Run 92-97),
`log-2026-11-14_to_2026-11-17_run98-103.md.gz` (Run 98-103) for full
per-run narrative; Run 104-114 are below in full.

### Where this programme stands
Every concretely-scoped axis — 14 strategy families (OBV Trend
Confirmation closed Run 121, the first pure cumulative volume-flow
construction, mechanically distinct from all 13 prior families including
Parabolic SAR Stop-and-Reverse closed Run 120, the first stateful
accelerating trailing-stop construction, Stochastic RSI Crossover closed
Run 117, the first pure second-order RSI-oscillator construction, and
Keltner Channel Breakout closed Run 116, the first direct
volatility-channel BREAKOUT construction), 5 signal-source categories, 3
confirmation gates (+ 1 stacked combo), 2 cross-symbol
constructions (now both re-tested with real shorting too, per Run 65/66),
sizing, exit mechanism (now including a volume-weighted trailing-stop
variant, Run 115), cost level, symbol universe, TF range, historical
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

## Run 104-105 — archived (see `research/archive/log-2026-11-18_run104-105.md.gz`)

## Run 106-120 — archived

See `research/archive/log-2026-11-19_to_2026-11-28_run106-120.md.gz` (Run
106/107/109/111/119 before/same-day deferred no-ops + detached-HEAD
recoveries; Run 108/110/114/118 on-schedule DCA self-correction re-checks,
no reversal; Run 112 Ichimoku Cloud, Run 113 VWAP Band Reversion, Run 115
volume-weighted trailing exit, Run 116 Keltner Channel Breakout, Run 117
Stochastic RSI Crossover, Run 120 Parabolic SAR Stop-and-Reverse — all
decisive rejects, zero adopted changes. Every conclusion already folded
into the DISTILLED LEARNINGS block above; archived purely for file size
(RESEARCH_LOG.md had grown to ~126KB, well over the ~40KB soft guideline).

---

## Run 121 — 2026-11-28, new strategy family (OBV Trend Confirmation), decisive reject; archive pass

**Housekeeping.** Scheduled firing, fresh container. Read `research/RESEARCH_LOG.md`
DISTILLED LEARNINGS and `research/decisions.jsonl` tail per the standing
protocol; set up backend venv (`python3 -m venv .venv && .venv/bin/pip
install -q -r requirements.txt`), no behavior change. RESEARCH_LOG.md had
grown to ~126KB (well over the ~40KB soft guideline) with 15 full run
sections (106-120) plus DISTILLED LEARNINGS — archived all 15 to
`research/archive/log-2026-11-19_to_2026-11-28_run106-120.md.gz`, keeping
only the DISTILLED LEARNINGS block + archive-index stubs in the active
file, to bring it back near budget (this run's section + the archived
stub bring it back to roughly the size it was after the Run 46/58/66/75/80
archive passes).

**Research.** Next DCA self-correction actionable date is 2026-11-29 (set
by Run 118) — one day away, not yet due. Per the standing protocol (Run
115/116/117/120's precedent of picking a new strategy family before the
actionable date rather than re-running early), this run tested the 14th
mechanically distinct strategy family: **On-Balance Volume (OBV) Trend
Confirmation** — a pure cumulative volume-flow line, `OBV =
cumsum(sign(close.diff()) * volume)`, with its own multi-bar directional
path memory built entirely from volume, touching no price band or
price-extreme concept at all. Entry: BUY when OBV crosses above its own
`obv_ma_period`-bar SMA (volume flow turning net-bullish), optionally
gated by requiring `close` above a 50-bar price-trend SMA (swept on/off).
Exit: SELL on the mirror bearish cross. Long-only, exchange-side 2%/4%
SL/TP unchanged throughout. Mechanically distinct from every prior family:
no closed price/volatility-band construction (Bollinger/Keltner/VWAP-band/
Donchian/Supertrend/Ichimoku/Parabolic SAR) touches volume at all; the
already-closed relative-volume gate is an instantaneous, memoryless volume
*ratio* filter bolted onto someone else's signal, not a cumulative
directional running total used as the primary signal; and momentum
rotation / pairs mean-reversion rank price returns across symbols, never
volume direction. Implementation: `research/experiments/obv_trend_confirmation.py`
(standalone `ObvTrendConfirmStrategy`, not registered in
`app/strategies/registry.py`, no production file touched).

Swept `obv_ma_period`{14,20,30} x `use_trend_filter`{False,True} across
15m/1h/4h, 18 configs, train 2026-06-30 to 2026-09-28 (150d-60d ago) vs
test 2026-09-28 to 2026-11-27 (60d-0d ago, today's anchor). **0/18 cleared
both OOS bars (test PF>1.1 AND test trades>=30).**

Without the trend filter, OBV crosses its own MA so rarely at 15m/1h for
this 8-symbol universe that 12/18 configs starved to n=0 train trades (the
line is too smooth/monotone at those timeframes without a price-trend
gate to produce any crossover at all — noise, not evidence). Adding the
trend filter unlocked adequate 4h-only samples (train n=29-35) — not
because filtering *adds* entries directly, but because rejecting an entry
keeps the strategy flat and thus eligible to re-evaluate the entry
condition on a later bar, where the unfiltered version's rarer-but-always-
accepted entries lock in a position for long stretches and so consume
fewer future crossover opportunities (verified directly: BTC-only 4h
obv_ma=14 debug run showed unfiltered=24 trades vs filtered=26 trades over
the same window and data — confirms this is real path-dependent dynamics,
not a bug). Even with that sample unlocked, train PF never reached 1.1 at
4h (0.513-0.631 across the three adequately-sampled filtered configs), so
none of them had real train-side support to begin with. The one 4h
obv_ma=14/filter=True config did show test PF 1.299, but at n=6 trades,
five short of the 30-trade floor, and its own train side (PF 0.631) never
cleared 1.1 either — not a near-miss worth re-sweeping. 1h configs mostly
starved to 0-12 trades on either side; the two 1h configs with any test
volume (obv_ma=20/30, unfiltered, n=9 each) both had zero train-side
trades and test PF 0.314/0.505 — no train support, decisive by itself.

**Decision: reject** (14th strategy family closed). Logged to
`research/decisions.jsonl` (one representative config, full 18-config
sweep described in the rationale field). DISTILLED LEARNINGS updated
above to fold in OBV Trend Confirmation as the 14th closed family.

**Verdict.** PF/win%/trades/$ already stated above (best adequately-sampled
train config: PF 0.631, win% 22.86, n=35, test PF 1.299 at n=6 — too thin
to count, test-side $ on $100/$1000 = +$0.0014 / +$0.014, economically
irrelevant regardless). No code or default params changed; full test
suite re-run clean (`cd backend && .venv/bin/python -m pytest`, all pass,
unaffected since no production file was touched). No reversion needed.
Commit: (see git log after this file is committed). Honesty over
optimism: a 14th clean null result on a genuinely new mechanism (pure
volume-flow, no price band) continues to say the same thing 13 prior
families already said — simple OHLCV signals on these majors remain
over-arbitraged at 7.5bps fees.
