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

**36 runs, ~340 configs, one standing positive finding (DCA dip-buy,
already shipped), zero adopted signal changes.** Full narrative for Run 1-26
is archived (see archive index at file end); Run 27-36 sections are below.
The DISTILLED LEARNINGS block just below was rewritten in Run 36 to be a
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
periodic check, not further parameter tuning.**

### Where this programme stands
Every concretely-scoped axis — 8 strategy families, 5 signal-source
categories, 3 confirmation gates (+ 1 stacked combo), 2 cross-symbol
constructions, sizing, exit mechanism, cost level, symbol universe, TF
range, historical era, and now DCA's dip-buy trend-conditioning — is closed
with zero surviving candidates. The only structurally out-of-reach items are
short-selling (architecture change) and futures/funding data (geo-blocked).
**Going forward: default to the self-correction protocol** (DCA dip-buy
ON-vs-OFF re-check on rolling-forward windows, roughly every 2+ days of new
data since the last check, per Run 31/32/35/36) **and the top-of-file
SELF-CORRECTION mandate** (re-validate no committed conclusion has quietly
stopped holding). A well-recorded null result remains a valid, valuable
outcome — do not invent recombinations of already-closed axes to manufacture
the appearance of progress.

**Live real money (pre-research):** 16 trades, −$0.29 net, ~70% of loss was
fees — empirically confirmed the negative-edge finding from backtests.
Stopped; testnet + this automated research only from here on.

---

_Full run-by-run narrative for Run 1-26 (and the 2026-08-10 prior-session
human-seeded notes) is archived: `research/archive/log-2026-08-10_to_2026-08-12.md.gz`
(Run 1-5), `log-2026-08-13_to_2026-08-14.md.gz` (Run 6-9),
`log-2026-08-20_to_2026-08-21_run21-23.md.gz` (Run 21-23),
`log-2026-08-24_to_2026-08-24_run24-25.md.gz` (Run 24-25),
`log-2026-08-25_to_2026-08-25_run26.md.gz` (Run 26). Run 27-36 sections
follow below (active, under the ~15-run archival floor). Every conclusion
above is folded from both the archived and active run sections — this block
was rewritten from ~750 lines to this compact form in Run 36 purely for
memory hygiene (RESEARCH_LOG.md had grown to 105KB, well past the ~40KB
guideline); no conclusion was dropped, only the narrative repetition._

## 2026-08-25 — Run 27

**Self-correction check:** `git log 2066c9c..HEAD -- backend/` (2066c9c = Run
26's commit, current HEAD before this run's own commit) is empty — no commits
touched `backend/` since Run 26. Nothing to re-validate or revert.

**Region tested:** two items. (1) The last explicitly-flagged-but-untested
item in DISTILLED LEARNINGS: DCA `dip_multiplier` magnitude alone (isolated
from the threshold change Run 4 bundled it with, and the buy-count cap Run 14
tested separately). (2) A genuinely new signal construction — the first
candlestick-SHAPE-derived entry this programme has tried, since the
26-run/258-config signal axis was otherwise fully exhausted (5 strategy
families, 3 confirmation gates, 2 cross-symbol constructions, all closed).

**(1) DCA dip_multiplier magnitude sweep** (`research/experiments/dca_multiplier_sweep.py`):
`dip_multiplier` in {1.5 (shipped), 1.75, 2.0, 2.5} at the shipped
`dip_threshold_pct=5.0`, same capital-normalized ROI methodology as Run
4/5/14 (ROI = unrealized_pnl/invested%, 3 non-overlapping windows x 8
symbols, production `dca.py` untouched). Delta vs the 1.5x baseline, by
window:

| window | regime | mult=1.75 | mult=2.0 | mult=2.5 |
|---|---|---|---|---|
| older (2025-12-28..2026-03-28) | declining | +0.092pp | +0.180pp | +0.345pp |
| train (2026-03-28..2026-06-27) | declining | +0.064pp | +0.126pp | +0.246pp |
| test (2026-06-27..2026-08-25) | strongly rising | −0.029pp | −0.057pp | −0.112pp |

Symbol win-rate vs the 1.5x baseline: 7/8 symbols benefit in both declining
windows at every multiplier tested, but only 1/8 in the rising test window.
**Verdict: reject/noise.** The effect is real but trivial (<0.35pp even at
the most aggressive 2.5x, on windows where the DCA baseline itself moved
15-29pp) and flips sign with the regime: a bigger multiplier lowers the
average cost basis further in a decline (mechanically sound — more capital
lands at the dip) but deploys more capital at a locally-worse price in a
sustained uptrend where dips are rare and the flat schedule already wins big
on its own. This is the same anti-correlated-across-regimes signature
documented for every non-signal lever tested since Run 21 (sizing) and Run
22 (exit mechanism): amplifying a knob doesn't create a persistent edge, it
just leans harder into whichever regime the window happens to be. **Keep
shipped `dip_multiplier=1.5x`** — closes the last flagged-open DCA variant.

**(2) Capitulation Wick Reversal, 6th strategy family** (`research/experiments/wick_reversal.py`):
BUY on a single candle with `lower_wick_ratio = (min(open,close)-low)/(high-low)
>= wick_ratio`, a bullish (green) close, and volume >= `vol_mult` x its own
20-period rolling mean — a capitulation-and-bounce pattern (long lower wick =
sold off hard intra-candle then bought back before close, on real volume, not
a thin wick). Exit on reversion to SMA(10) of close, unchanged exchange-side
2%/4% SL/TP. Mechanically distinct from all 5 prior families and all 3
confirmation gates: this is the first signal in the programme that reads a
single candle's own OHLC *shape* rather than a derived multi-bar series or a
band/threshold touch. Standalone research strategy class, not registered in
`app/strategies/registry.py`, no production file touched. Swept `wick_ratio`
{0.5, 0.6, 0.7} x `vol_mult` {1.5, 2.0} @ 1h/4h = 12 configs, standard
150d-60d/60d-0d train/test windows, unmodified production
`run_candle_backtest`/`RiskConfig`.

**Results (train PF → test PF, test n):**

| tf | wick_ratio | vol_mult | train pf | test pf | test n |
|---|---|---|---|---|---|
| 1h | 0.5 | 1.5 | 0.532 | 0.861 | 117 |
| 1h | 0.5 | 2.0 | 0.473 | 1.098 | 52 |
| 1h | 0.6 | 1.5 | 0.523 | 0.997 | 78 |
| 1h | 0.6 | 2.0 | 0.658 | 1.482 | 35 |
| 1h | 0.7 | 1.5 | 0.543 | 0.693 | 38 |
| 1h | 0.7 | 2.0 | 0.668 | 1.149 | 18 |
| 4h | 0.5 | 1.5 | 0.336 | 0.859 | 36 |
| 4h | 0.5 | 2.0 | 0.281 | 0.861 | 14 |
| 4h | 0.6 | 1.5 | 0.332 | 0.144 | 18 |
| 4h | 0.6 | 2.0 | 0.184 | 0.038 | 7 |
| 4h | 0.7 | 1.5 | 0.264 | 0.085 | 10 |
| 4h | 0.7 | 2.0 | 0.089 | 0.083 | 4 |

**Verdict: decisive reject, 12/12 configs. No candidate, no code change. No
3rd-window check triggered** — train pf never exceeds 0.668 anywhere in the
sweep, so nothing clears the strict train>1.1 AND test>1.1 AND n>=30 AND
condition. Two findings: (a) **3 of the 6 1h configs (all `vol_mult=2.0`
rows) clear test pf>1.1** (1.098/1.482/1.149) **but every one pairs with a
train pf of 0.47-0.66** — the identical test-clears/train-doesn't
regime-luck shape documented for mean_reversion since before Run 16, now
reproduced by a mechanically unrelated, candlestick-shape-based
construction, one more data point that this shape is a property of the
8-symbol/150d-60d/0d window structure rather than of any one signal family.
(b) **4h is a clean, unambiguous reject at every config** (train pf
0.089-0.336, test pf 0.038-0.861) — tightening `wick_ratio` at 4h collapses
the sample below any usable size (n=4-14) while making both train and test
pf *worse*, the opposite of what filtering toward "purer" capitulation
candles should do if the pattern had real signal. **Closed — do not re-tune
wick_ratio/vol_mult/exit_period on this construction; a 7th family would
need a genuinely different signal source (not price shape, not price level,
not volume, not cross-symbol — all four now tried).**

**Files:** `research/experiments/wick_reversal.py` (new),
`research/experiments/dca_multiplier_sweep.py` (new). 15 entries appended to
`research/decisions.jsonl` (213 → 228 lines). Log archived: Run 24-25 →
`research/archive/log-2026-08-24_to_2026-08-24_run24-25.md.gz` (active log
was 43KB pre-archive; still ~45KB post-archive/post-this-run since two new
DISTILLED LEARNINGS bullets were added — the accumulated-knowledge section
now dominates the file's size, not the 2 run-sections it currently holds
(Run 26, Run 27). Next run should consider archiving Run 26 as well if
DISTILLED LEARNINGS keeps growing, even though that's fewer than the ~15-run
guideline — the guideline assumes shorter per-run sections than this
programme's have turned out to need).

**No code change** — pure research, no auto-improve threshold was met. Both
tests (DCA multiplier magnitude, wick reversal) closed as reject/noise; no
deploy-worthy candidate found.

---

_Run 21-23 (2026-08-20 to 2026-08-21) are archived in `research/archive/log-2026-08-20_to_2026-08-21_run21-23.md.gz`; Run 24-25 (2026-08-24) are archived in `research/archive/log-2026-08-24_to_2026-08-24_run24-25.md.gz`; Run 26 (2026-08-25) is archived in `research/archive/log-2026-08-25_to_2026-08-25_run26.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._

## 2026-08-26 — Run 28

**Self-correction check:** `git log 1f2c518..HEAD -- backend/` (1f2c518 =
Run 27's commit, current HEAD before this run's own commit) is empty — no
commits touched `backend/` since Run 27. Nothing to re-validate or revert.

**Region tested: a genuinely new signal-source category — UTC session-hour
BUY gating.** Per Run 27's explicit close-out note, all four previously
tried signal-source categories (price-level/band, moving-average, price
shape, cross-symbol/volume) are exhausted; a public-kline data source has
no order-book/funding-rate fields to build a data-source-level 5th category
from (confirmed by reading `app/backtest/data.py` — `fetch_klines` only
ever calls `/api/v3/klines`, no other Binance public endpoint is wired up).
The one axis genuinely untested and available from data already in hand:
the candle's own UTC timestamp. Crypto trades 24/7, but liquidity and
participation are known to cluster by session (Asia/EU/US); gating entries
to a session window is mechanically distinct from every closed same-candle
gate (ADX = trend strength, relative volume = participation magnitude, MTF
direction = a coarser TF's own trend) because it reads no price or volume
data at all.

**Implementation** (`research/experiments/session_hour_gate.py`): thin
decide()-wrapping subclasses of production `TrendMomentumStrategy` and
`MeanReversionStrategy` (same "defer to parent, add one veto" pattern as
Runs 11/15/16/17's gates) — BUY vetoed unless the entry candle's own
`open_time` (UTC) falls inside a configured `[start_hour, end_hour)` half-
open window. No lookahead (uses only the current candle's own timestamp),
no production code touched. Standard 150d-60d/60d-0d train/test windows
(2026-03-29..2026-06-27 / 2026-06-27..2026-08-26), unmodified production
`run_candle_backtest`, shipped-default entry params for both bases, 8-symbol
universe, fees 7.5bps/slippage 4bps.

**Swept 4 session windows + baseline (off) x 2 bases = 10 configs:**

| base | window (UTC) | train pf | train n | test pf | test n |
|---|---|---|---|---|---|
| trend_momentum@1h | baseline | 0.588 | 84 | 0.624 | 85 |
| trend_momentum@1h | Asia 00-08 | 0.458 | 38 | 0.956 | 23 |
| trend_momentum@1h | EU 07-15 | 0.592 | 48 | 0.595 | 29 |
| trend_momentum@1h | US 13-21 | 0.889 | 51 | 0.804 | 46 |
| trend_momentum@1h | EU/US 13-16 | 0.482 | 21 | 1.221 | 9 |
| mean_reversion@1h | baseline | 0.644 | 127 | 1.865 | 80 |
| mean_reversion@1h | Asia 00-08 | 0.528 | 69 | 0.797 | 24 |
| mean_reversion@1h | EU 07-15 | 1.088 | 73 | 2.708 | 32 |
| mean_reversion@1h | US 13-21 | 0.909 | 86 | 2.533 | 38 |
| mean_reversion@1h | EU/US 13-16 | 0.724 | 65 | 0.938 | 21 |

**trend_momentum@1h: decisive reject, 4/4 gated configs.** US session
(13-21 UTC) reaches the highest train PF of the sweep (0.889, n=51 —
notably better than the ungated baseline's 0.588) but test PF stays at
0.804, still under the 1.1 bar; every other window either stays flat
(EU 07-15) or clears test PF only on a starved sample (Asia n=23, EU/US
overlap n=9, both below the 30-trade floor). No config crosses both bars
with an adequate sample.

**mean_reversion@1h: 2 of 4 gated windows (EU 07-15, US 13-21) appeared to
clear the OOS screen on first look**, and EU 07-15 is notable — train PF
1.088 (n=73) is the **highest train-side PF ever recorded for
mean_reversion@1h anywhere in this programme's 28-run history** (every
prior lever on this base topped out at ~0.925), paired with test PF 2.708
(n=32). US 13-21 clears test PF 2.533 (n=38) but train PF stays at 0.909
(a near-miss, not a double-clear). Per the standing 3rd-window protocol for
any config that clears (or nearly clears) both sides, both were checked
against the OLDER non-overlapping window (2025-12-29..2026-03-29):

- **EU 07-15 OLDER: PF 0.157, n=75** (real sample) — decisive failure.
  Per-symbol breakdown: all 8 symbols lose (PF 0.0-0.469, return -15% to
  -30%) — that older window was a sharp market-wide decline, so "buy EU-
  session dips" lost across the board regardless of session; it is not a
  per-symbol session mechanism, it inherited a favorable regime in
  train+test and an unfavorable one in the 3rd window, same as every prior
  near-miss since Run 16.
- **US 13-21 OLDER: PF 0.313, n=113** (real sample) — decisive failure,
  same pattern: all 8 symbols lose (PF 0.012-0.599, return -12% to -43%).

**Verdict: decisive reject, 10/10 configs — closes the calendar/session-time
axis for this mechanism.** Both apparent mean_reversion near-misses
(including the strongest train-side signal this base has ever produced)
failed the 3rd-window check the same way every prior near-miss has since
Run 16 — the "looks good until you check the window that wasn't cherry-
picked by having also picked the entry signal" pattern is now reproduced by
a 5th, mechanically unrelated construction (after MTF direction, rotation,
and now session-time). Do not re-tune session boundaries on this base/
gate combination; a materially different session hypothesis (e.g.
day-of-week rather than hour-of-day) would be a new, untested granularity
within the same category, not a re-run of this one.

**Self-correction check (repeated for clarity):** no strategy/risk code
changed since Run 27 — nothing to revalidate or revert.

**No code change** — pure research, no auto-improve threshold was met.

**Files:** `research/experiments/session_hour_gate.py` (new). 10 entries
appended to `research/decisions.jsonl` (228 → 238 lines, still under the
250-entry rotation trigger). Log: archived Run 26 into
`research/archive/log-2026-08-25_to_2026-08-25_run26.md.gz` per Run 27's
own flagged next step (active log was 45KB pre-archive, over the 40KB
threshold, with the accumulated DISTILLED LEARNINGS section now dominating
size rather than the run-sections themselves — only Run 27 and this Run 28
section remain in full).

---

## 2026-08-26 — Run 29

**Self-correction check:** `git log a8df0ce..HEAD -- backend/` (a8df0ce = Run
28's commit, current HEAD before this run's own commit) is empty — no
commits touched `backend/` since Run 28. Nothing to re-validate or revert.

**Region tested: day-of-week BUY gating — the coarser calendar granularity
Run 28 explicitly flagged as untested.** Run 28 closed hour-of-day
session gating (calendar/session-time, the 5th signal-source category);
its closing note named day-of-week as a distinct, untested granularity
within that same category rather than a new category. Implemented as a
thin decide()-wrapping subclass of production `TrendMomentumStrategy` /
`MeanReversionStrategy` (same "defer to parent, add one veto" pattern used
for every prior gate) — BUY vetoed unless the entry candle's own UTC
`open_time.dayofweek` (Mon=0..Sun=6) is inside a configured allowed set. No
lookahead, no production code touched. Standard 150d-60d/60d-0d train/test
windows, unmodified production `run_candle_backtest`, shipped-default entry
params for both bases, 8-symbol universe, fees 7.5bps/slippage 4bps.

**Implementation:** `research/experiments/day_of_week_gate.py` (new).

**Swept 4 day-of-week windows + baseline (off) x 2 bases = 10 configs:**

| base | window (UTC weekday) | train pf | train n | test pf | test n |
|---|---|---|---|---|---|
| trend_momentum@1h | baseline | 0.588 | 84 | 0.624 | 85 |
| trend_momentum@1h | weekdays Mon-Fri | 0.512 | 64 | 0.856 | 64 |
| trend_momentum@1h | weekend Sat-Sun | 0.511 | 39 | 0.568 | 30 |
| trend_momentum@1h | early-week Mon-Wed | 0.623 | 59 | 1.180 | 46 |
| trend_momentum@1h | late-week Thu-Sun | 0.912 | 72 | 0.460 | 49 |
| mean_reversion@1h | baseline | 0.644 | 127 | 1.865 | 80 |
| mean_reversion@1h | weekdays Mon-Fri | 0.483 | 117 | 1.400 | 65 |
| mean_reversion@1h | weekend Sat-Sun | 4.180 | 48 | inf (0 losers) | 17 |
| mean_reversion@1h | early-week Mon-Wed | 0.498 | 83 | 1.689 | 40 |
| mean_reversion@1h | late-week Thu-Sun | 1.400 | 97 | 1.857 | 41 |

**trend_momentum@1h: decisive reject, 4/4 gated configs.** weekend Sat-Sun
sits exactly at the 30-trade floor (n=30) and still fails PF outright
(0.568). late-week Thu-Sun reaches the highest train PF trend_momentum@1h
has ever shown at this TF under any lever (0.912) but test PF collapses to
0.46 — train-improves/test-collapses, the Run 15 volume-gate overfit shape,
not the mean_reversion-style regime-luck shape. early-week Mon-Wed is a
near-miss (test PF 1.18/n=46, train PF only 0.623) — checked below.

**mean_reversion@1h: 3 of 4 gated windows appeared to clear or near-clear
the OOS screen**, including this programme's **strongest double-clear to
date** — late-week Thu-Sun (train PF 1.4/n=97 AND test PF 1.857/n=41, both
comfortably over 1.1 on samples well above the floor, not a hedge-your-bets
near-miss like every prior close call). Per the standing 3rd-window
protocol for any config that clears or nearly clears both sides, all 4
non-baseline mean_reversion configs plus trend_momentum's early-week
near-miss were checked against the OLDER non-overlapping window
(2025-12-29..2026-03-29):

| base | window | OLDER pf | OLDER n |
|---|---|---|---|
| trend_momentum@1h | early-week Mon-Wed | 0.821 | 68 |
| mean_reversion@1h | weekdays Mon-Fri | 0.351 | 110 |
| mean_reversion@1h | early-week Mon-Wed | 0.947 | 84 |
| mean_reversion@1h | late-week Thu-Sun | 0.255 | 104 |

**All 4 fail decisively** (weekend Sat-Sun's own train PF 4.18/test n=17 was
disqualified by the test sample size before any check was warranted — well
under the 30-trade floor). The late-week Thu-Sun double-clear's OLDER
per-symbol breakdown shows every one of the 8 symbols losing (PF 0.12-0.44,
return -18% to -46%) — the same broad market-wide decline documented for
Run 28's EU/US session OLDER checks, not a day-of-week mechanism. The
weekdays and early-week near-misses show the identical pattern.

**Verdict: decisive reject, 10/10 configs — closes the day-of-week
granularity within the calendar/session-time axis.** The notable finding
this run isn't a new axis, it's a sharper read on an old one: a genuine
double-clear (both train and test comfortably over the bar on adequate
samples, the strongest form of apparent evidence this methodology can
produce short of a 3rd-window check) failed exactly as decisively as every
prior near-miss once checked. That raises the bar for what "looks
promising" should mean going forward — a double-clear alone, without the
3rd-window check, would not have been distinguishable from real edge in
this run's own results table.

**Self-correction check (repeated for clarity):** no strategy/risk code
changed since Run 28 — nothing to revalidate or revert.

**No code change** — pure research, no auto-improve threshold was met.

**Files:** `research/experiments/day_of_week_gate.py` (new). 10 entries
appended to `research/decisions.jsonl` (238 → 248 lines, still under the
250-entry rotation trigger). Log: active file is ~59KB post-this-run,
further over the 40KB guideline, but per Run 27's precedent the bulk is the
DISTILLED LEARNINGS section itself (which must stay, per the memory-
management instructions) rather than run-sections — only 3 run-sections
(27, 28, 29) currently sit in the active log, well under the ~15-run
archival floor, so nothing was moved to `research/archive/` this run;
revisit archiving once there are materially more than 15 open run-sections
or DISTILLED LEARNINGS itself needs trimming (not yet — it is still purely
additive, dense, decision-relevant content).

## 2026-08-27 — Run 30

**Self-correction check:** `git log e9881c8..HEAD -- backend/` (e9881c8 =
Run 29's commit, current HEAD before this run's own commit) is empty — no
commits touched `backend/` since Run 29. Nothing to re-validate or revert.

**Region tested: the one remaining flagged combination — stacking two
previously-closed single-axis BUY gates together.** DISTILLED LEARNINGS'
own closing note on Run 29 named this as the one unexplored combination
(alongside a 6th signal-source category needing data this codebase can't
fetch), while predicting it likely inherits the same regime-luck failure
rather than creating new edge. This run tests that prediction directly:
does requiring BOTH real participation (Run 15's relative-volume gate) AND
a favorable session window (Run 28's session-hour gate, each base's own
best single-gate window) survive where neither did alone?

**Implementation:** `research/experiments/session_volume_combo_gate.py`
(new) — thin subclasses of production `TrendMomentumStrategy` /
`MeanReversionStrategy`, `decide()` defers entirely to the parent and adds
up to two vetoes on BUY (session window, then relative volume — both must
pass), the same "defer to parent, add vetoes" pattern as every prior gate.
No production code touched. Standard 150d-60d/60d-0d train/test windows
(anchored to today, 2026-08-27), unmodified production
`run_candle_backtest`, shipped-default entry params for both bases,
8-symbol universe, fees 7.5bps/slippage 4bps.

**Swept baseline + 2 single-axis references + 2 combo thresholds, x 2
bases = 12 configs:**

| base | variant | train pf | train n | test pf | test n |
|---|---|---|---|---|---|
| trend_momentum@1h | baseline | 0.579 | 86 | 0.705 | 81 |
| trend_momentum@1h | session-only US 13-21 | 0.859 | 53 | 0.853 | 44 |
| trend_momentum@1h | volume-only vol=1.2 | 0.936 | 62 | 1.045 | 34 |
| trend_momentum@1h | volume-only vol=1.5 | 1.100 | 39 | 1.122 | 29 |
| trend_momentum@1h | combo US+vol=1.2 | 0.579 | 26 | 0.711 | 17 |
| trend_momentum@1h | combo US+vol=1.5 | 0.525 | 16 | 0.753 | 15 |
| mean_reversion@1h | baseline | 0.622 | 123 | 1.944 | 82 |
| mean_reversion@1h | session-only EU 07-15 | 1.112 | 72 | 3.101 | 33 |
| mean_reversion@1h | volume-only vol=1.2 | 0.526 | 121 | 2.174 | 75 |
| mean_reversion@1h | volume-only vol=1.5 | 0.679 | 127 | 2.058 | 68 |
| mean_reversion@1h | combo EU+vol=1.2 | 1.177 | 67 | 3.403 | 33 |
| mean_reversion@1h | combo EU+vol=1.5 | 1.267 | 67 | 2.758 | 30 |

**trend_momentum@1h: decisive reject, both combo configs.** Stacking the
two vetoes only shrinks the sample (combo n=26/17 and n=16/15, both far
under the 30-trade floor, vs 53/44 and 39/29 for the single-axis gates
alone) while making test PF *worse* than either single-axis gate on its
own (0.711/0.753 vs session-alone's 0.853 and volume-alone's 1.045/1.122).
No ambiguity — the two filters remove different, apparently uncorrelated
subsets of trades, and intersecting them just starves the sample.

**mean_reversion@1h: both combo configs produced this programme's
strongest-looking double-clears yet on paper.** EU session + vol=1.2:
train PF 1.177/n=67 (the highest train PF ever recorded for this
base+construction) AND test PF 3.403/n=33, both comfortably over 1.1 on
adequate samples. EU session + vol=1.5: train PF 1.267/n=67, test PF
2.758/n=30 (exactly at the floor). Per the standing 3rd-window protocol
for any double-clear, both combo configs plus their 2 single-axis
components (volume-only, first time tested on this base) were checked
against the OLDER non-overlapping window (2025-12-30..2026-03-30):

| base | variant | OLDER pf | OLDER n |
|---|---|---|---|
| mean_reversion@1h | baseline | 0.340 | 125 |
| mean_reversion@1h | session-only EU 07-15 | 0.157 | 75 |
| mean_reversion@1h | volume-only vol=1.2 | 0.374 | 129 |
| mean_reversion@1h | volume-only vol=1.5 | 0.365 | 125 |
| mean_reversion@1h | combo EU+vol=1.2 | 0.117 | 71 |
| mean_reversion@1h | combo EU+vol=1.5 | 0.088 | 66 |

**All 6 fail decisively, and — the notable new finding — both combo
configs fail *more* decisively than either single-axis component alone**
(combo OLDER PF 0.117/0.088 vs session-alone's 0.157 and volume-alone's
0.365-0.374). Per-symbol OLDER breakdown for both combo cells shows 6 of 8
symbols at PF 0.0-0.28 (BTC/ETH/SOL/XRP/DOGE/ADA), the same market-wide-
decline signature documented since Run 16 — not a per-symbol mechanism.

**Verdict: decisive reject, 12/12 configs — closes the gate-combination
axis.** The mechanism-level generalization: stacking two gates that each
individually inherit regime luck compounds the luck rather than filtering
toward real edge — a double-veto only looks like it "confirms" edge in
train+test if both vetoes happen to agree on which trades belong to that
pair's shared favorable regime, which a 3rd non-overlapping window
reliably exposes as coincidence, not signal. This directly confirms (does
not overturn) the prediction flagged at the end of Run 29. **Closed — do
not test further two-gate combinations from the existing closed set** (a
materially new single signal source, not a re-combination of existing
ones, would be needed to reopen this line).

**Self-correction check (repeated for clarity):** no strategy/risk code
changed since Run 29 — nothing to revalidate or revert.

**No code change** — pure research, no auto-improve threshold was met.

**Files:** `research/experiments/session_volume_combo_gate.py` (new). 12
entries appended to `research/decisions.jsonl`, then `rotate_archive.py`
ran (260 → 120 active entries; 140 oldest archived to
`research/archive/decisions-2026-08-10_to_2026-08-20.jsonl.gz`). Active
`RESEARCH_LOG.md` run-section count is now 4 (27-30), still well under the
~15-run archival floor — no log archiving this run.

---

## 2026-08-27 — Run 31

**Question:** Run 30 left exactly one concretely-scoped open item — check
whether futures/funding-rate data is fetchable (the only remaining
new-signal-source candidate) before designing around it — plus, absent that,
find a genuinely new axis rather than re-tuning any of the 30 closed ones.

**Part A — feasibility check.** `fapi.binance.com` (Binance's public futures
host, needed for funding-rate history, no API key required in principle)
returns `"Service unavailable from a restricted location according to 'b.
Eligibility'..."` for every endpoint tried (`/fapi/v1/fundingRate`,
`/fapi/v1/premiumIndex`) from this execution environment. `data-api.binance.
vision` (the spot host this programme already uses) has no `/fapi` path
(404). **Confirmed infeasible — not a code or design issue, a network/geo
restriction on this environment. Closes the 6th-category question
definitively; do not re-attempt.**

**Part B — historical-era axis (new).** Every one of the 30 prior runs' train/
test/OLDER windows came from the same ~240-day span (roughly Dec 2025-Aug
2026). Re-ran the 3 original shipped-default strategies @1h — unmodified
production `run_candle_backtest`, same 8-symbol universe, same 7.5bps/4bps
fees — on a fully disjoint 2023 window (train 2023-02-01..2023-07-01, 150d;
test 2023-07-01..2023-08-30, 60d) to check whether the "no edge" verdict is
regime-specific or generalizes.

| family | train pf | train n | test pf | test n |
|---|---|---|---|---|
| trend_momentum | 0.879 | 144 | 0.756 | 80 |
| mean_reversion | 0.771 | 222 | 0.703 | 119 |
| grid | 0.738 | 365 | 0.986 | 204 |

**Decisive reject, 3/3** — nothing clears train AND test PF>1.1 together;
grid's test pf=0.986 is the closest but on n=204 (well above the trade
floor) it's a real near-flat result, not a small-sample near-miss, so no
3rd-window cross-check was warranted for any row. Notable: grid reproduces
its documented "many small in-range wins, funded by a few huge directional
losses" signature (82-86% win rate, BTC alone -111.8% notional-adjusted)
with *different* symbols playing each role than in 2025-2026 — same
mechanism, different era, confirming it's regime-independent. mean_reversion
failed on *both* sides together for the first time ever in this programme
(every 2025-2026 result showed test-clears/train-doesn't regime luck
instead) — a different failure shape, same "no edge" conclusion.

**$ impact (test window, both null):** trend_momentum ret -0.0413% ($100 →
-$0.04, $1000 → -$0.41); mean_reversion ret -0.0842% ($100 → -$0.08, $1000 →
-$0.84); grid ret -0.0071% ($100 → -$0.01, $1000 → -$0.07). All economically
negligible-to-negative, consistent with every prior null.

**Self-correction check:** no strategy/risk code changed since Run 30 —
nothing to revalidate or revert.

**No code change** — pure research; feasibility findings and a new external-
validity axis, no auto-improve threshold was met (nothing cleared the bar in
either era).

**Verdict:** the 30-run null is not an artifact of the one recent market
regime every prior run sampled — it reproduces cleanly in a materially
different historical era too. Combined with the confirmed infeasibility of
futures/funding data, this programme has now exhausted every concretely-
scoped axis: signal source (6 families/5 categories), TF (1m-1d), symbol
universe (2 disjoint 8-symbol sets), historical era (2 disjoint multi-month
windows), position sizing, exit mechanism, cost level, and gate combinations.
The one remaining untested scope item (long-only vs. shorting) requires an
architecture change, not a param tune, and is out of scope. Honest read:
absent a new data source this environment can actually reach, further runs
should default to periodic self-correction (revalidating the shipped DCA
dip-buy against rolling-forward windows as real time passes) rather than
inventing further recombinations of already-closed axes.

**Files:** `research/experiments/historical_era_2023.py` (new). 3 entries
appended to `research/decisions.jsonl` (123 active, no rotation triggered).
Active `RESEARCH_LOG.md` run-section count is now 5 (27-31), still well
under the ~15-run archival floor — no log archiving this run.

---

## 2026-08-28 — Run 32

**Question:** Run 31 concluded that every concretely-scoped axis in this
programme is now exhausted (signal source: 6 families/5 categories; TF
1m-1d; symbol universe: 2 disjoint 8-symbol sets; historical era: 2 disjoint
multi-month windows; position sizing; exit mechanism; cost level; gate
combinations) and recommended defaulting to periodic self-correction —
revalidating the shipped DCA dip-buy default against rolling-forward windows
as real time passes — rather than inventing further recombinations of
already-closed axes. This run follows that recommendation.

**Method.** Re-ran the Run 4/27 DCA evaluation methodology (capital-
normalized ROI = unrealized_pnl / invested; DCA has no round-trip trades so
PF doesn't apply) with dip-buy ON (shipped: dip_threshold_pct=5.0,
dip_multiplier=1.5) vs dip-buy OFF, on today's rolling windows — one day
forward of Run 27's last check: older 2025-12-31..2026-03-31, train
2026-03-31..2026-06-29 (150d-60d ago), test 2026-06-29..2026-08-28 (60d-0d
ago). Same 8-symbol universe, 1h timeframe, 7.5bps/4bps fees.

| window | dip ON avg ROI% | dip OFF avg ROI% | delta (pp) | symbols dip-ON wins |
|---|---|---|---|---|
| older | -14.4272 | -14.5937 | +0.1665 | 7/8 |
| train | -19.0648 | -19.1883 | +0.1235 | 6/8 |
| test | +28.8709 | +28.9185 | -0.0476 | 1/8 |

**Result: reproduces the exact regime-dependent signature on record since
Run 4/27, unchanged.** Dip-buy ON beats OFF in both declining windows (older
and train are both large drawdown periods for this universe) but trails OFF
in the strongly-rising test window, where the dip mechanism barely fires (4
total dip-buys across all 8 symbols in 60 days of a sustained uptrend, vs 59
and 28 in the two declining windows). Effect magnitude stays under 0.2pp in
either direction in every window — same order of magnitude as every prior
check (Run 27: "+0.06 to +0.35pp in both declining windows... but -0.03 to
-0.11pp in a strongly-rising window"). No degradation, no new evidence for a
change in either direction.

**$ impact:** economically negligible either way, consistent with every
prior DCA check — the dip-buy lever moves ROI by fractions of a percentage
point, not a material dollar amount on $100 or $1000 (PF/win%/trades don't
apply to DCA's non-round-trip accounting, so no `usd_pnl_100`/`usd_pnl_1000`
figures are meaningful here beyond the ROI% above).

**Decision: keep shipped defaults as-is (`dip_threshold_pct=5.0`,
`dip_multiplier=1.5`) — no code change.** This confirms, rather than
overturns, the prior conclusion.

**Self-correction check:** no strategy/risk code has changed since Run 31 —
nothing else to revalidate or revert. This run's own DCA re-check is itself
the self-correction: result unchanged from Run 4/27, so no revert is
warranted.

**No code change** — pure research; a scheduled re-confirmation, not a new
finding, so no auto-improve threshold was met.

**Going forward:** absent a new concretely-scoped axis (e.g. a data source
this environment can newly reach), future runs should keep defaulting to
this same self-correction check on a rolling-forward date range, rather than
re-deriving already-closed axes. If a future check ever shows the dip-buy
effect degrading or flipping sign in a way that breaks the established
regime-dependent pattern (rather than just reproducing it), that would be
the trigger to revisit the shipped default.

**Files:** `research/experiments/dca_self_correction_run32.py` (new). 1
entry appended to `research/decisions.jsonl` (124 active, no rotation
triggered — `rotate_archive.py` run, threshold is 250). Active
`RESEARCH_LOG.md` run-section count is now 6 (27-32), still well under the
~15-run archival floor — no log archiving this run.

---

## 2026-08-28 — Run 33

**Question:** Runs 31/32 concluded every concretely-scoped axis (signal
source: 6 families/5 categories; TF 1m-1d; symbol universe; historical era;
position sizing; exit mechanism; cost level; gate combinations) was
exhausted and defaulted to periodic DCA self-correction. Run 32's self-
correction check landed on today's date (2026-08-28) as its test-window
anchor, so re-running it this session would add <12h of new data — not a
materially new region. Instead this run opens a genuinely new strategy
construction not covered by any prior family: BB-width volatility-squeeze
breakout (see `research/experiments/bb_squeeze_breakout.py`) — require a
recent volatility contraction (BB width in its own low percentile) before
taking a close-above-upper-band breakout. Mechanically distinct from
Donchian (fixed channel, no volatility precondition) and Supertrend
(ATR-adaptive band, no contraction requirement) — the first construction in
this programme where the entry signal is conditioned on the *shape of the
volatility regime itself*, not just price/volume/calendar.

**Method.** Same 8-symbol universe, same train/test/older window anchors as
Run 32 (train 2026-03-31..2026-06-29, test 2026-06-29..2026-08-28, older
2025-12-31..2026-03-31), 7.5bps fees/4bps slippage, unchanged exchange SL/TP.
Swept squeeze_pct {10,20,30} (percentile threshold defining a "squeeze") x
require_squeeze {True, False — the latter a plain-breakout control isolating
the squeeze precondition's marginal value} @ 1h and 4h = 12 configs.

**Result — 1h: decisive reject, no 3rd-window check warranted.** Every 1h
config fails outright: train PF 0.472-0.691, test PF 0.650-0.986, nothing
within reach of the 1.1 bar on either side.

**Result — 4h: the programme's first "TEST + OLDER both clear, TRAIN
decisively fails" shape.** squeeze_pct=20 (require_squeeze=True): test PF
1.144/n=40, train PF 0.501/n=53. squeeze_pct=30: test PF 1.376-1.438/n=48,
train PF 0.323/n=50. squeeze_pct=10 nominally clears (test PF 1.381) but
n=27 is under the 30-trade floor — disqualified by sample size alone.
Checked the two adequate-sample near-misses (squeeze_pct=20, 30) against the
OLDER non-overlapping window: **both ALSO clear** (OLDER PF 1.442/n=63 and
1.246/n=68) — every prior near-miss in this programme's history has failed
its 3rd-window check; this is the first to pass it on the aggregate numbers.
The require_squeeze=False control (plain BB breakout, no squeeze
precondition) does NOT pass: OLDER PF 1.078/n=113, just under 1.1.

Per-symbol breakdown resolves the squeeze_pct=20/30 near-misses as noise
despite passing the aggregate bars twice: TRAIN's failure is broad and real
(7-8 of 8 symbols losing, several 0.0-PF all-losing symbol samples — not a
small-sample artifact), while TEST and OLDER's passes are each built from
only 3-18 trades per symbol, with roughly half the symbols losing in both
windows and a handful of high-PF winners (SOL, XRP, DOGE) driving the
aggregate. This is the same single-symbol/small-per-symbol-sample
disqualifier documented since Run 16 (MTF gate) and Run 19 (rotation) — it
just happened to land in both flanking windows simultaneously here instead
of one, which is why it cleared the "3rd window" check that was designed to
catch single-window luck. **Read:** BB-squeeze breakout is still a
trend-following breakout construction (same family as Donchian/Supertrend)
— it profits when a window happens to contain real trend legs (TEST, OLDER
here) and gets whipsawed in choppier stretches (TRAIN here, decisively);
which window is favorable is regime luck, not evidence the squeeze
precondition adds real signal.

**Decision: closed, noise — not adopted.** Do not re-tune
squeeze_pct/squeeze_lookback/squeeze_recency/bb_std on this construction.

**$ impact (test window, all noise/reject):** 1h configs range -0.077% to
-0.003% ret ($100 → -$0.08 to -$0.00, $1000 → -$0.77 to -$0.03). 4h
near-miss configs (squeeze_pct=20/30, before being resolved as noise) showed
test ret +0.013% to +0.044% ($100 → +$0.01 to +$0.04, $1000 → +$0.13 to
+$0.44) — economically negligible even taken at face value, and not adopted
given the per-symbol resolution above.

**Self-correction check:** no strategy/risk code has changed since Run 32 —
nothing to revalidate or revert.

**No code change** — pure research; a new signal-source construction tested
and closed, no auto-improve threshold was met.

**Going forward:** the trend-following-breakout construction (fixed channel
Donchian, ATR-band Supertrend, volatility-squeeze BB) is now closed across
3 mechanically distinct implementations — do not add a 4th variant of "buy
the breakout, whatever gates the entry" without a fundamentally different
hypothesis for why these 8 majors at 1h/4h would sustain enough clean trend
legs to pay for the false-breakout rate net of fees. Absent a new
concretely-scoped axis, future runs should keep defaulting to the Run
31/32 self-correction protocol (DCA dip-buy re-check on rolling-forward
windows) once a full day+ of new data has accumulated since the last check,
or open a new signal-source hypothesis distinct from all 7 families/5
categories tried so far (candidates not yet tried: order-book/liquidity-
derived signals — out of reach of kline-only public data; a genuinely new
oscillator-divergence construction, e.g. price-vs-RSI divergence rather than
RSI threshold, not yet tested in this programme).

**Files:** `research/experiments/bb_squeeze_breakout.py` (new). 12 entries
appended to `research/decisions.jsonl` (136 active, no rotation triggered —
`rotate_archive.py` run, threshold is 250). Active `RESEARCH_LOG.md`
run-section count is now 7 (27-33), still well under the ~15-run archival
floor — no log archiving this run.

---

## 2026-08-29 — Run 34

**Price-vs-RSI Bullish Divergence — 8th strategy family, first
oscillator-divergence construction.** Per the DISTILLED LEARNINGS "Going
forward" note after Run 33, the concretely-scoped candidate was "a genuinely
new oscillator-divergence construction, e.g. price-vs-RSI divergence rather
than RSI threshold" — every prior family/gate reads one series (price, RSI,
ADX, volume, calendar) against a fixed threshold, band, or channel; none
compares the *shape* of two different series against each other over time.
Classical technical divergence does exactly that: price makes a lower low
while RSI makes a higher low at the matching swing, signalling downside
momentum is fading even as price still falls.

**Construction.** A candle at index j is a confirmed swing low once
`pivot_lookback` bars have closed on both sides of it and its low is the
window minimum — confirmation lands at index j+pivot_lookback, never
earlier, so nothing reads ahead of the current row. At each confirmation,
compare the pivot to the immediately preceding confirmed pivot (if within
`max_divergence_bars`): bullish divergence = lower price low AND higher RSI
low AND RSI at the 2nd pivot below `oversold_max` (keeps it anchored in
oversold territory, not mid-range noise). BUY on the confirming candle.
Exit: RSI recovers above `exit_rsi` (the exhaustion thesis resolved), plus
unchanged exchange-side 2%/4% SL/TP (never touched).

**Method.** Same 8-symbol universe, 7.5bps fees/4bps slippage, unchanged
exchange SL/TP. Windows shifted one day forward from Run 33's anchor (today
= 2026-08-29): train 2026-04-01..2026-06-30, test 2026-06-30..2026-08-29,
older 2026-01-01..2026-04-01 (240d-150d ago, reserved for a 3rd-window
check that turned out not to be needed). Swept pivot_lookback {3,5} x
exit_rsi {55,60} @ 1h/4h = 8 configs, rsi_period=14 and max_divergence_bars=
30/oversold_max=50 held fixed (a first pass on the entry-construction
question itself, not a full param sweep — those two axes would be the next
step if this had shown any promise).

**Result — decisive reject, 8/8, no 3rd-window check warranted (0 configs
cleared both OOS bars).**

*1h*: train PF 0.409-0.644 across all 4 configs (best is pivot_lookback=3,
exit_rsi=60: 0.644), test PF 0.752-1.011 (best is pivot_lookback=5,
exit_rsi=55: 1.011, still under 1.1). Sample sizes are adequate on both
sides (train n 119-130, test n 52-78) — this is a clean fail on PF, not a
sample-size disqualification.

*4h*: pivot_lookback=3 configs fail outright (train PF 0.51-0.59, test PF
2.6-2.7 but n=19, under the floor). pivot_lookback=5 configs show the
sweep's only train PF above 1 (1.617 and 1.799) with test PF 1.32-1.52 — on
paper the closest this run came to a double-clear — but train n=11 and test
n=15, both decisively under the 30-trade floor. Confirmed bullish-divergence
swings (two pivots within 30 bars, both conditions met) are simply rare at
4h on 150d/60d windows; the high PF is a handful of trades, not a sample
large enough to trust either way.

**Read:** the divergence *construction itself* isn't a magic escape from
the pattern documented since Run 1 — the 8 majors at 1h/4h with 7.5bps fees
still show fee-drag-dominated, near-breakeven-at-best behavior whether the
signal reads one series against a threshold or two series against each
other. 1h has enough samples to say so cleanly; 4h doesn't have enough
divergence events per window to say anything at all (a structural limit of
the construction at this TF/window length, not evidence for or against).

**$ impact (test window, all reject):** 1h configs range -0.035% to +0.001%
ret ($100 → -$0.04 to +$0.00, $1000 → -$0.35 to +$0.01) — economically
negligible even before the PF-based rejection. 4h configs range +0.010% to
+0.044% ret ($100 → +$0.01 to +$0.04, $1000 → +$0.10 to +$0.44) on samples
too small to trust regardless of sign.

**Self-correction check:** no strategy/risk code has changed since Run 33 —
nothing to revalidate or revert.

**No code change** — pure research; a new signal-source construction tested
and closed, no auto-improve threshold was met.

**Going forward:** all 8 strategy families tried in this programme (3
original + Donchian, Supertrend, Capitulation Wick, BB-squeeze, RSI
divergence) and all 5 signal-source categories (price-level/band, price-
shape, volume/cross-symbol, calendar/session-time, oscillator-divergence)
are now closed on this 8-symbol/1h-4h scope. No concretely-scoped new
construction remains flagged. Future runs should default to the Run 31/32
self-correction protocol (DCA dip-buy re-check on rolling-forward windows)
once a full day+ of new data has accumulated since the last check — Run 32
was the last DCA check (2026-08-28 anchor), so a re-check is not yet
overdue by more than the 1 day this run already advanced the window. If a
self-correction check finds nothing new to report, the next genuinely new
avenue would need to be either a fundamentally different data source
(order-book/liquidity signals remain out of reach of kline-only public
data, as Run 31 confirmed for futures/funding-rate data) or an architecture
change out of this programme's scope (e.g. short-selling for a true
market-neutral pairs trade, flagged as out-of-scope since Run 20).

**Files:** `research/experiments/rsi_divergence.py` (new). 8 entries
appended to `research/decisions.jsonl` (144 active, no rotation triggered —
`rotate_archive.py` run, threshold is 250). Active `RESEARCH_LOG.md`
run-section count is now 8 (27-34), still well under the ~15-run archival
floor — no log archiving this run.

---

## 2026-08-29 — Run 35

**DCA `dip_threshold_pct` isolation — mirrors Run 27's `dip_multiplier`
isolation, doubles as a self-correction re-check.** Per Run 34's
close-out note, all 8 strategy families and 5 signal-source categories are
now closed on the 8-symbol/1h-4h scope, and the standing default is the
Run 31/32 self-correction protocol (DCA dip-buy re-check on rolling-forward
windows). Run 32's last DCA check anchored on 2026-08-28 — only 1 day of
new data has accumulated, too little for a fresh re-check to say anything
Run 32 didn't already say. Instead this run closes a narrower, genuinely
untested question: `dip_threshold_pct` has only ever been tested *bundled*
with a multiplier change (Run 4's 3%/2.5x variant); Run 27 isolated
`dip_multiplier` alone (holding threshold=5.0 fixed) but the mirror case —
threshold alone, holding multiplier=1.5 fixed — was never done. The
baseline row of this sweep (threshold=5.0, the shipped value) also
re-validates the shipped default on data through today, folding in the
self-correction requirement as a side effect.

**Method.** Same capital-normalized ROI methodology as Run 4/14/27/32 (DCA
has no round-trip trades, so PF/win-rate/trade-count don't apply): for each
symbol, simulate the daily DCA schedule with `dip_enabled` on vs off,
compare average ROI (unrealized P&L / invested) across the 8-symbol
universe, 3 non-overlapping windows (older 2026-01-01..2026-04-01, train
2026-04-01..2026-06-30, test 2026-06-30..2026-08-29 — same anchor as Run
34), fees 7.5bps/slippage 4bps. Swept `dip_threshold_pct` in {3.0, 4.0, 5.0
(shipped), 7.0, 10.0} with `dip_multiplier` held at the shipped 1.5x both
ways.

**Result — same anti-correlated-across-regimes signature as Run 27,
monotonic across the whole sweep:**

| threshold | older Δpp (decline) | train Δpp (decline) | test Δpp (rise) | dips (older/train/test) |
|---|---|---|---|---|
| 3.0 | +0.4037 (8/8) | +0.2058 (7/8) | −0.1032 (1/8) | 118/99/25 |
| 4.0 | +0.2420 (8/8) | +0.1791 (7/8) | −0.0441 (3/8) | 83/56/14 |
| 5.0 (shipped) | +0.1564 (7/8) | +0.1216 (6/8) | −0.0422 (1/8) | 59/28/4 |
| 7.0 | +0.1272 (8/8) | +0.0275 (2/8) | +0.0000 (0/8) | 32/4/0 |
| 10.0 | +0.0441 (4/8) | +0.0195 (1/8) | +0.0000 (0/8) | 8/2/0 |

(Δpp = avg-ROI delta vs dip-buy OFF; win-fraction = symbols where ON beats
OFF.) A **looser (lower) threshold fires more dip-buys**, which **helps
more in both declining windows** (mechanically: more buys land at a locally
lower price, further lowering cost basis) and **hurts more in the
sustained-uptrend test window** (more capital deployed at a locally-worse
relative price when dips are rare and the flat schedule already wins big on
its own) — the identical mechanism and sign pattern Run 27 found for
`dip_multiplier`, now confirmed for `dip_threshold_pct` independently. The
per-symbol win-fraction tracks the aggregate direction cleanly at the tight
end (7-8/8 symbols agree at threshold 3.0-4.0 in both declining windows,
i.e. broad-based, not a 1-2-symbol artifact) and degrades toward a coin-flip
as the threshold loosens toward 10.0 (feature nearly disabled — only 2-8
dip-buys fire across 150d, most symbols never trigger it at all in a given
window). Effect size stays economically trivial everywhere (≤0.40pp).

**Self-correction (folded into the 5.0 baseline row):** shipped defaults
(dip_threshold_pct=5.0, dip_multiplier=1.5) reproduce the same
regime-dependent pattern on record since Run 4 with no degradation — older
+0.1564pp (7/8), train +0.1216pp (6/8), test −0.0422pp (1/8), all consistent
in sign and magnitude with Run 32's check one day prior. No git revert
warranted.

**Decision: keep shipped `dip_threshold_pct=5.0` / `dip_multiplier=1.5x` —
closed.** No code change. With this, both DCA dip-buy parameters
(magnitude Run 27, threshold Run 35) have now been independently isolated
and closed — no DCA dip-buy parameter axis remains flagged. The shipped
5.0 sits at a reasonable middle point on the tradeoff (neither the
most-aggressive 3.0 that maximizes decline-regime benefit at the largest
rise-regime cost, nor the loose 7.0/10.0 that nearly disables the feature).

**$ impact (test window, all reject/noise):** delta vs OFF ranges −0.1032pp
(threshold=3.0) to +0.0000pp (7.0/10.0) on $100/$1000 invested capital,
i.e. −$0.10/−$1.03 at the worst (most aggressive) setting down to ~$0 at
the loosest settings — economically negligible at every point on the
sweep, consistent with every DCA parameter finding since Run 4.

**No code change** — pure research; both DCA dip-buy parameters now fully
characterized, no auto-improve threshold was met.

**Going forward:** DCA's dip-buy feature is now fully characterized on
both its parameters (threshold and multiplier) — nothing further to tune
there without a fundamentally different hypothesis about *when* to widen
the buy (e.g. a signal-conditioned threshold, which would re-open the
"combine a closed signal-source category with DCA" question, not yet
tried but likely low-value given all 5 signal-source categories are
individually null). With every concretely-scoped signal/strategy axis
closed (Run 34) and both DCA parameters now closed (Run 35), future runs
should default back to the Run 31/32 self-correction protocol once 2+ full
days of new data have accumulated since this run's 2026-08-29 anchor —
checking both the DCA dip-buy default and, per the top-of-file
SELF-CORRECTION mandate, re-validating that no committed research
conclusion has quietly stopped holding as fresh candles arrive. Absent new
data or a genuinely new hypothesis, there is no concretely-scoped
untested axis left to open.

**Files:** `research/experiments/dca_threshold_isolation.py` (new). 5
entries appended to `research/decisions.jsonl` (149 active, no rotation
triggered — `rotate_archive.py` run, threshold is 250). Active
`RESEARCH_LOG.md` run-section count is now 9 (27-35), still under the
~15-run archival floor — no log archiving this run.

---

## 2026-08-30 — Run 36

**Trend-conditioned DCA dip-buy gate — first test conditioning the dip
multiplier on a second, independent signal.** Per Run 35's close-out: all 8
strategy families and 5 signal-source categories are closed, both DCA
dip-buy parameters (threshold, multiplier) are independently isolated and
closed, and only 1 day of new data had accumulated since Run 35's anchor
(2026-08-29) — too little for a fresh self-correction re-check to say
anything Run 35 didn't already say. Run 35 flagged one concretely-named,
not-yet-tried idea: "a signal-conditioned threshold ... would re-open the
combine-a-closed-signal-category-with-DCA question." This run tries it,
narrowly scoped: gate the dip-buy *multiplier* (not the schedule, not the
base buy amount) on the symbol's own price position relative to a rolling
SMA — `below_sma` (only widen the buy when the pre-dip close sits below its
own SMA — "this dip is a genuine correction") vs the mirror control
`above_sma` (widen only inside an intact uptrend — the wrong-direction
hypothesis, included to confirm sign) vs `none` (ungated, = shipped
default). Every prior DCA test varied threshold/multiplier magnitude or
capped count; none ever conditioned the dip trigger on an independent
signal, so this is mechanically new, not a re-tune of a closed axis.

**Method.** Same capital-normalized ROI methodology as Run 4/14/27/32/35
(DCA has no round-trip trades, so PF/win-rate/trade-count don't apply):
`dip_threshold_pct=5.0`/`dip_multiplier=1.5` (shipped) held fixed, only the
gate varies. SMA computed on the 1h entry-timeframe close, period in
{50, 100, 200} bars (~2/4/8 days), evaluated on the close *prior* to the
scheduled buy candle (no lookahead). 3 non-overlapping windows, rolled 1 day
forward from Run 35 to use fresh data as a side-effect self-correction check
on the `none` baseline row: older 2026-01-02..2026-04-02, train
2026-04-02..2026-07-01, test 2026-07-01..2026-08-30 (today). 7 configs x 3
windows, `research/experiments/dca_trend_gate.py`.

**Result — mechanically inert, no meaningful change vs the ungated default,
0/6 gated configs beat baseline in more than one window:**

| config | older Δpp | train Δpp | test Δpp | test dips fired / gated out |
|---|---|---|---|---|
| none (baseline) | +0.1475 | +0.1145 | −0.0398 | 4 / 0 |
| below_sma_50 | +0.1475 | +0.1145 | −0.0095 | 3 / 1 |
| below_sma_100 | +0.1296 | +0.1145 | +0.0114 | 2 / 2 |
| below_sma_200 | +0.1545 | +0.1142 | +0.0057 | 1 / 3 |
| above_sma_50 | +0.0000 | +0.0000 | −0.0303 | 1 / 3 |
| above_sma_100 | +0.0187 | +0.0000 | −0.0513 | 2 / 2 |
| above_sma_200 | +0.0230 | +0.0000 | −0.0513 | 2 / 2 |

(Δpp = avg-ROI delta vs dip-OFF control.) **`below_sma` is nearly
indistinguishable from the ungated baseline in older/train** — 0-7 of
52-59 dip events per window get gated out across all 3 SMA periods, because
a 24h-drop dip trigger almost always already coincides with price sitting
below a multi-day SMA by construction (the two conditions are highly
correlated, not independent). The only place `below_sma` visibly differs is
the test window, where it flips the sign from −0.0398pp (baseline) to as
much as +0.0114pp (sma_100) — but on only 1-3 total dip-buys fired across 8
symbols in that window, an order of magnitude below any sample-size floor
this programme has ever accepted; not evidence of anything. **`above_sma`
(mirror control) confirms the expected directionality**: gating on being
*above* trend average starves the feature almost entirely in the
declining/mixed windows (0/8 symbols beat OFF at sma_50 in every window,
vs 6-7/8 for the ungated/below_sma variants) and is flat-to-worse
everywhere — buying more on a "dip" that's still inside an uptrend is, as
expected, the wrong direction.

**Self-correction (folded into the `none` baseline row):** shipped defaults
reproduce the same regime-dependent pattern on record since Run 4 with no
degradation — older +0.1475pp (7/8 symbols), train +0.1145pp (6/8), test
−0.0398pp (1/8), consistent in sign and magnitude with Run 32/35's checks.
No git revert warranted.

**Decision: reject the trend gate (both directions), keep shipped ungated
DCA dip-buy.** The SMA-position condition is too correlated with the
existing 24h-drop trigger to act as an independent filter — it either
barely changes which buys fire (below_sma) or, when it does filter
meaningfully, the resulting sample is too small to trust in either
direction. Confirms Run 35's own prediction that this idea was "likely
low-value" — now checked, not just predicted.

**$ impact (test window, all reject):** delta vs OFF ranges −$0.05
(above_sma_100/200) to +$0.01 (below_sma_100) on $100 invested capital
(−$0.51 to +$0.11 on $1000) — economically negligible at every config,
consistent with every DCA-axis finding since Run 4.

**No code change** — pure research; DCA's dip-buy trigger is now also
closed against signal-conditioning, in addition to both its own parameters.
No auto-improve threshold was met.

**Memory hygiene this run:** DISTILLED LEARNINGS had grown to ~750 lines
(RESEARCH_LOG.md was 105.9KB, well past the ~40KB guideline) purely from
narrative accumulation across 35 runs, despite the run-section count (9,
27-35) staying under the 15-run archival floor that had been gating
archiving decisions. Rewrote DISTILLED LEARNINGS from scratch as a compact
conclusions-only index (no evidence dropped — everything remains in
`research/decisions.jsonl` and the already-archived run-section prose for
Run 1-26); file is now 59.7KB. No new `.gz` archive was needed this run
since the bloat was in the summary, not the run-section history.

**Going forward:** every concretely-scoped axis (8 strategy families, 5
signal-source categories, gates, cross-symbol constructions, sizing, exit
mechanism, cost level, symbol universe, TF range, historical era, and now
DCA's dip-buy trend-conditioning) is closed. Next run should default to the
self-correction protocol (DCA dip-buy ON-vs-OFF re-check on rolling-forward
windows) once 2+ full days of new data have accumulated since this run's
2026-08-30 anchor, per the standing recommendation since Run 31/32/35.

**Files:** `research/experiments/dca_trend_gate.py` (new). 7 entries
appended to `research/decisions.jsonl` (156 active, no rotation triggered —
`rotate_archive.py` run this cycle, threshold is 250). RESEARCH_LOG.md
condensed this run (see Memory hygiene note above); active run-section
count is now 10 (27-36), still under the ~15-run archival floor.
