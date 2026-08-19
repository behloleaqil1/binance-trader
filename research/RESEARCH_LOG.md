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
families, across 17 sessions and ~120 configs.** trend_momentum,
mean_reversion, and grid are now each **fully closed across the entire
5m/15m/1h/4h TF sweep** — every combo tested is either net-negative or only
clears the OOS bar by luck/small-sample noise. Honest baseline: simple
RSI/BB/EMA/grid signals on these 8 majors appear over-arbitraged; fees turn
near-breakeven setups negative. The one asymmetric, mechanically-explicable
(not curve-fit) positive finding so far is DCA's dip-buy feature — already
shipped as the default, not a new change. **Full evidence for every closed
TF/param combo lives in `research/decisions.jsonl` and archived run
sections below/in `research/archive/`; this section states only the
conclusions and why, not the blow-by-blow.**

**Do not re-test, without a materially new signal/indicator:**
- **trend_momentum** (EMA-cross + RSI + MACD): every TF 5m–4h, best train PF
  ever seen was 0.99 (15m, literally the shipped default). 5m is the worst
  (train PF 0.211→test 0.028) — likely the 3%-daily-loss halt tripping early
  on 5m noise and pruning the effective sample, not the EMA cross itself
  getting rarer. Faster EMA pairs (9/21, 12/26) are strictly worse/starved
  at every TF. Dropping MACD confirmation is strictly worse than requiring
  it everywhere tested.
- **mean_reversion** (BB + RSI, optional trend_ema filter): every TF 5m–4h,
  22/24-ish combos fail the train screen at every TF; the rare train-PF>1
  survivors are starved (trend_ema=200 needs far more history than any
  window used here — 0 trades at 4h, 3–6 at 1h) or fail a 3rd
  non-overlapping window when checked (1h default params: OOS PF 1.9 on one
  window, PF 0.44 on another — regime luck, not edge). 5m default is the
  most decisive failure (train PF 0.18, test PF 0.35, both real samples).
- **grid** (range ladder): a **directional bet in disguise** — bag-holds
  through trends. Confirmed at every TF 15m/1h/4h/5m; 5m (Run 13) is the
  cleanest rejection yet (train PF 0.42–0.85, test PF 0.23–0.34, real
  samples, no train/test ambiguity, despite an unusually high 67-77% train
  win-rate — many small in-range wins offset by large losses when price
  breaks the range). **`flatten_on_stop=False` trade-level PF is a known
  accounting artifact (100% win rate by construction) — always read
  account-level return for that mode, never trade-PF.** Needs a
  range-detection filter (volatility gate) to ever be worth re-testing;
  parameter tuning alone (range/levels/flatten) cannot fix directional risk.
- **ADX(14) as a confirmation/gate indicator**: tried both directions —
  grid ceiling-gate (Run 10, blocks buys when ADX high: flat-to-worse at
  every threshold, redundant with existing stop_outside_range) and
  trend_momentum floor-gate (Run 11, requires ADX high to enter: floor=20
  passed 2 of 3 non-overlapping windows, closed as regime luck same as the
  mean_reversion@1h precedent). **Both closed — a genuinely different
  indicator family is needed, not more ADX threshold tuning.**
- **Relative-volume confirmation gate (trend_momentum, Run 15)**: first
  indicator family tried outside price-derived signals (EMA/RSI/MACD/ADX).
  Gate = BUY only if entry-candle volume >= vol_mult x its own 20-period
  rolling mean, tested at 1h on the same shipped-default combo Run 11 used
  for the ADX floor (ema 20/50, rsi_buy_min=50, require_macd=True), 5
  thresholds {none,1.0,1.2,1.5,2.0}. **Decisive reject, no 3rd-window check
  needed** (nothing cleared both OOS bars): train PF rises monotonically as
  the gate tightens (0.586->0.925->0.898->1.193->1.217, win% 22%->41%) but
  test PF stays flat-to-worse the whole time (0.483->0.53->0.619->0.598
  ->0.668, never above 0.67) — a clean train-overfits/test-doesn't-follow
  shape, plus the two highest-train-PF thresholds (1.5, 2.0) also starve
  the sample (37/29 and 22/19 trades). Mechanism: a volume gate removes
  low-conviction crosses, which happens to make the *surviving* train
  trades look better in-sample, but the underlying EMA-cross signal has no
  edge regardless of the volume regime it fires in — filtering doesn't fix
  a signal that isn't there. **Closed — do not re-tune vol_mult; a further-
  different indicator family (not price-derived, not volume-derived) would
  be needed to reopen trend_momentum.**
- **1m, any strategy**: catastrophic (−34% to −42%, PF 0.01–0.09,
  ~200+ trades/coin, fee drag dominates). Never retest.
- **Multi-timeframe (MTF) trend-direction gate for trend_momentum@1h (Run
  16)**: BUY vetoed unless the 4h EMA(fast)>EMA(slow) on the most recently
  closed 4h candle (as-of backward join, no lookahead) — mechanically
  distinct from the two closed same-candle gates (ADX = trend *strength*,
  volume = *participation*; this = a coarser TF's own *direction*). Swept
  3 HTF EMA pairs (10/30, 20/50, 50/100). 10/30 and 50/100 both reject
  cleanly (test PF 1.023 and 0.597, one below 1.1 outright, the other an
  adequate-sample train-improves/test-doesn't). **20/50 (matching the
  entry TF's own pair) is the closest near-miss any confirmation gate has
  produced**: test PF 1.256/29 trades (1 trade under the 30 floor), train
  PF only 0.917 (no train-side edge at all — rules out train curve-fitting
  as the explanation but also gives no train-side confirmation), and a 3rd
  non-overlapping window clears both bars cleanly (PF 1.336/34 trades).
  **Still closed as `noise`, not adopted** — per-symbol breakdown (24
  cells across 3 windows x 8 symbols) shows most cells have 1-8 trades
  with several inf/0.0 PFs from single-trade symbols; the aggregate is a
  handful of lucky/unlucky single-symbol outcomes averaging out, not a
  consistent per-symbol mechanism. Same "2/3 windows, no per-symbol
  consistency" standard applied as the ADX floor=20 precedent. **Do not
  re-tune HTF EMA pairs on the 8-symbol/150d methodology** — if revisited,
  needs a larger universe or longer per-symbol history to resolve the
  small-sample noise, not more parameter sweeping.
- **MTF trend-direction gate applied to mean_reversion (Run 17)**: same
  gate mechanism as Run 16 (BUY vetoed unless 4h EMA(fast)>EMA(slow) on the
  most recently closed 4h candle), applied to mean_reversion@1h's oversold
  dip-buy instead of trend_momentum's EMA-cross — "buy the dip only in an
  intact higher-TF uptrend". **Weaker than the trend_momentum application,
  decisively closed**: only 1 of 3 windows (test) cleared both anti-noise
  bars across all 3 HTF EMA pairs swept {10/30, 20/50, 50/100}; the
  standout (10/30, test PF 1.139/31 trades) failed its 3rd-window check
  outright (older-window PF 0.423/64 trades, real sample) — versus Run 16's
  MTF trend_momentum near-miss which cleared 2/3 windows. Train PF never
  exceeded 0.925 at any HTF pair (no train-side support anywhere), and
  per-symbol breakdown showed the same lucky/unlucky single-symbol
  small-sample pattern as every other closed gate. The baseline (no gate)
  re-confirmation on today's window also reproduced the known regime-luck
  split even more starkly than before (train PF 0.496 fail, test PF 2.207
  huge, 91 trades) — mean_reversion@1h's underlying signal still has no
  train-side edge to gate around. **Both applications of the MTF gate
  mechanism (trend_momentum Run 16, mean_reversion Run 17) are now closed —
  the mechanism itself should be considered exhausted absent a genuinely
  new hypothesis for how to use it, not just a new base strategy to bolt it
  onto.**

- **Donchian channel breakout (Run 18, new strategy family)**: BUY on a
  close above its own N-period high, SELL on a close below a shorter
  N-period low (trailing breakdown) — momentum *follows* the breakout,
  the mirror image of mean_reversion's fade-the-band-touch logic, and
  mechanically unrelated to trend_momentum's lagging EMA cross or grid's
  range ladder. Swept @ 1h and 4h, 3 entry/exit channel pairs {20/10,
  55/20, 40/20} x vol_filter {off, on — require ATR(14) above its own
  50-period rolling mean at the breakout candle} = 12 configs. **Decisive
  reject, the cleanest rejection in this programme's history**: every
  single config fails both train AND test PF well below 1.1 (train PF
  range 0.124-0.613, test PF range 0.584-0.939 — nothing even a
  near-miss, no 3rd-window check warranted). Win rates are the tell:
  4-38%, i.e. most breakouts are false/whipsawed and get stopped out
  before the trail exit or TP captures a real trend leg; the few real
  trend legs that do pay off never generate enough gross win to offset
  the many small stopped-out losses net of fees. The vol_filter (ATR
  expansion requirement) helps directionally at every combo (fewer,
  higher-quality trades, test PF up in every row) but never crosses the
  1.1 bar itself. **Closed — do not re-sweep Donchian channel
  periods/vol-filter thresholds.** Combined with mean_reversion's
  fade-the-touch failure, this now rules out *both directions* of
  price-range-relative signals (follow the range break, or fade the band
  touch) on this 8-symbol majors universe at 1h/4h — the absence of edge
  looks like a property of the instruments/regime/fee level, not of
  which side of the signal you pick.

**Untested, low priority (not expected to change the verdict):** 1d for
all three families — even fewer candles per window than 4h, likely to hit
the same starvation issues `trend_ema=200` already showed at 4h.

**What actually works (already shipped, no change needed):**
- **DCA dip-buy** (`dip_enabled=True, dip_threshold_pct=5.0,
  dip_multiplier=1.5`, Run 4): beats a flat schedule on capital-normalized
  ROI in 2/3 non-overlapping windows (+0.26 to +0.61pp in choppy/declining
  regimes) and is neutral (not negative, -0.07pp noise) in a trending-up
  window — mechanically explicable (extra buys only land when a real 24h
  dip occurs, so it's a no-op not a loss otherwise). A more aggressive
  3%/2.5× variant wins only 4/8 symbols in trending-up (noise) and costs
  13-30% more deployed capital — not adopted.
- **DCA interval=daily** (Run 5): hourly is noise-level indifferent (finer
  slicing of the same window, no benefit, 24x more live orders for
  nothing); weekly is systematically worse in all 3 windows tested
  (samples too few/unrepresentative). Keep daily.
- **mean_reversion trend_ema filter** (opt-in, default off): a principled
  downside-reduction knob, not a proven edge (still tiny-sample, 3-6
  trades, everywhere tested). Leave as opt-in; don't flip default without a
  large-sample OOS pass.
- **DCA dip-rebuy cap** (Run 14): capping the number of dip-multiplied
  buys per window (allow only the first N qualifying dips, then flat
  amount thereafter) — tested N=5,3,2,1 vs the uncapped shipped default,
  same 3-window ROI methodology as Run 4/5. **Closed, decisive reject**:
  capping the ROI delta vs uncapped is negative or zero in every
  symbol/window tested (0/8 symbols ever benefit; strictly monotonic
  worsening as the cap tightens in the two windows with a real sample —
  train 27 dip events, older-reference 56 dip events; test window only
  saw 3 dip events total so the cap essentially never bound there — a
  tie, not a real test). Mechanism: in a decline, MORE dip-buys lower the
  average cost basis further — capping removes exactly the buys that
  would have landed at the lowest prices, so it can only match or hurt
  ROI, never help. This is the opposite of the "over-concentration risk"
  concern that motivated testing it (raised when the more-aggressive
  2.5x/3% variant was rejected in Run 4) — the data says more dip-buying
  in a decline is a benefit, not a risk, at the shipped 1.5x/5%
  magnitude. No code change; production `dca.py` untouched.

**Live real money (pre-research):** 16 trades, −$0.29 net, ~70% of loss was
fees — empirically confirmed the negative-edge finding from backtests.
Stopped; testnet + this automated research only from here on.

**Where this research programme stands (as of Run 18):** all three
original candle-strategy families are exhausted across the full TF sweep,
every confirmation-gate mechanism tried (same-candle: ADX, relative-volume;
cross-TF: MTF direction x 2 base strategies) has failed, and now a fourth,
mechanically distinct strategy family — Donchian breakout, the mirror
image of mean-reversion — has also been decisively rejected (Run 18, the
cleanest reject yet: no config even a near-miss). The DCA dip-rebuy cap
idea is closed too (reject — capping never helps). The one DCA variant
still open per Run 4's original list is multiplier *magnitude* between the
shipped 1.5x and the already-rejected 2.5x (e.g. 2.0x) — untested, low
priority given the cap result suggests this family's edge is already close
to its natural shape. **"More TF/param sweeps of the four closed
families", "more confirmation gates on existing base signals", and "range-
relative signals in either direction (fade or follow)" should all be
treated as dead ends absent a new idea.** Both directions of a
price-range-relative signal (fade the band touch = mean_reversion, follow
the break = Donchian) now fail the same way at the same TFs on the same
universe — suggesting the ceiling here may be structural (fee level +
regime + instrument choice), not a signal-construction problem solvable by
recombining price/volume-derived indicators. **Next run should consider:**
(a) DCA multiplier magnitude 2.0x (low priority, per above); (b) if
another new strategy family is pursued, prioritize one that is NOT
price-range-relative and NOT another EMA/RSI/BB/ATR recombination on the
same 8-symbol/1h-4h grid — e.g. a genuinely different data axis such as
cross-symbol relative-strength/rotation (rank the 8 symbols by recent
return, trade the leaders vs laggards) rather than a per-symbol indicator,
since every per-symbol, price-derived signal construction tried so far
(4 families, price-range-relative in both directions, 3 confirmation-gate
families) has failed on this universe; (c) alternatively, treat this as
grounds to consider the research programme's own scope/assumptions (fee
level, universe, TF range) as the thing worth questioning next, rather
than continuing to search for a signal within them — 18 runs and ~140+
configs with zero surviving candidates is itself a strong, well-evidenced
result.

---

_Older run sections (Run 1-5, and the 2026-08-10 prior-session human-seeded notes) are archived in `research/archive/log-2026-08-10_to_2026-08-12.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._

## 2026-08-19 — Run 18

**Self-correction check:** reviewed commits since Run 17 — only Run 17's own
log commit landed. No strategy/risk/backtest code touched since Run 17;
nothing to re-validate or revert. This research programme has never adopted
a code/param change across all 18 runs — a well-recorded string of null
results.

**Region chosen:** a genuinely new strategy family — Donchian channel
breakout — per Run 17's flagged next step (c): "a fundamentally different
strategy family... prioritize one with a mechanically distinct entry
signal (e.g. breakout/volatility-expansion...)". This is the first
strategy family tried in this programme that is not an EMA-cross, BB/RSI
mean-reversion, or range-ladder grid: BUY on a close above its own
N-period high (momentum *follows* the breakout — the opposite of
mean_reversion's fade-the-band-touch), SELL on a close below a shorter
N-period low (trailing breakdown exit), plus the unchanged exchange-side
2%/4% SL/TP. An optional volatility-expansion filter (require ATR(14)
above its own 50-period rolling mean at the breakout candle, screening for
"real" volatility expansion vs a low-volatility false breakout) was also
tested as a same-candle confirmation gate on the new signal.

**Method:** standalone `DonchianBreakoutStrategy` in
`research/experiments/donchian_breakout.py` — a fresh `Strategy` subclass
(not a gated subclass of an existing production strategy, since this is a
new base signal, not a filter on an old one). Not registered in
`app/strategies/registry.py`; no production file touched. `compute_indicators`
builds the entry/exit channels via `rolling().max()/.min()` on `high`/`low`,
shifted by 1 so the channel a candle is judged against is built only from
strictly-prior candles (no lookahead), plus a Wilder-style ATR computed
inline (not added to shared `indicators.py` since the signal is still
unproven). Swept timeframe {1h, 4h} x entry/exit channel pair {(20,10),
(55,20), (40,20) — the last one being the "quarter Turtle" convention with
a slower entry and a shorter exit} x vol_filter {off, on} = 12 configs.
Windows: train 2026-03-21→2026-06-19 (150d-60d ago), test 2026-06-19→
2026-08-19 (60d-0d ago, today's anchor). 8 symbols, fees 7.5bps + slippage
4bps, $10,000/symbol, repo-default `RiskConfig` (SL 2%/TP 4%) untouched.

**Results — decisive reject across the entire sweep, no near-miss:**

| config | train PF / n | test PF / n | test win% |
|---|---|---|---|
| 1h (20/10) no filter | 0.545 / 115 | 0.658 / 107 | 29.0% |
| 1h (20/10) vol_filter | 0.613 / 123 | 0.939 / 100 | 38.0% |
| 1h (55/20) no filter | 0.163 / 47 | 0.662 / 98 | 32.7% |
| 1h (55/20) vol_filter | 0.319 / 55 | 0.867 / 79 | 36.7% |
| 1h (40/20) no filter | 0.248 / 72 | 0.592 / 111 | 27.9% |
| 1h (40/20) vol_filter | 0.502 / 103 | 0.749 / 86 | 33.7% |
| 4h (20/10) no filter | 0.409 / 37 | 0.584 / 59 | 25.4% |
| 4h (20/10) vol_filter | 0.239 / 40 | 0.858 / 38 | 31.6% |
| 4h (55/20) no filter | 0.410 / 40 | 0.723 / 42 | 28.6% |
| 4h (55/20) vol_filter | 0.379 / 40 | 0.699 / 31 | 29.0% |
| 4h (40/20) no filter | 0.124 / 24 | 0.936 / 50 | 34.0% |
| 4h (40/20) vol_filter | 0.457 / 39 | 0.819 / 36 | 33.3% |

Every config fails both train and test PF well below the 1.1 anti-noise
bar (train range 0.124-0.613, test range 0.584-0.939) — nothing is even a
near-miss, so no 3rd-window cross-check was warranted anywhere in the
sweep (unlike Run 16/17's near-misses, which needed one). The vol_filter
helps directionally at every single combo (test PF higher in all 6
filtered-vs-unfiltered pairs, win% up 5-9pp) but never gets close to
clearing 1.1 — it screens out some false breakouts but the base signal
underneath has no edge to protect. Win rates (25-38%) show the mechanism:
most breakouts are whipsaws that get stopped out (2% SL) before the trail
exit or 4% TP can capture a real trend leg, and the few real trend legs
that do pay off don't generate enough gross win to offset the many small
stopped-out losses net of fees.

**$ impact (test window, $100/$1000 notional, aggregate across 8
symbols):** every config is negative — worst 1h (40/20) no filter -$0.12/
-$1.19; best (closest to breakeven, still negative) 4h (40/20) no filter
-$0.01/-$0.09. No config is worth deploying.

**Decision: reject (12 configs logged, no candidate).** See DISTILLED
LEARNINGS above for the durable conclusion — this closes the first
mechanically-new strategy family tried since the original three, and
combined with mean_reversion's fade-the-touch failure, rules out *both
directions* of price-range-relative signals on this universe/TF range.

**No code changes** — this was a research-only run; no bar was cleared, so
no production code, default params, or tests were touched.

**Verdict:** _No CANDIDATE FOUND this run._

---

## 2026-08-18 — Run 17

**Self-correction check:** reviewed commits since Run 16 — only Run 16's
research-log/decisions commit landed (MTF trend_momentum gate, closed as
noise); no production code was changed by Run 16, so there is nothing to
re-validate or revert.

**Hypothesis (per Run 16's flagged next step (b)):** the MTF trend-
direction gate mechanism (BUY vetoed unless the 4h EMA(fast)>EMA(slow) on
the most recently closed 4h candle, as-of backward join, no lookahead) is
mechanically sound but wasn't decisively edge-positive on trend_momentum.
Apply the *same mechanism* to mean_reversion@1h's oversold dip-buy instead:
gate BUY on a still-intact higher-TF *uptrend*, i.e. "only buy the dip when
the coarser timeframe hasn't actually turned down" — explicit falling-knife
protection from a smoother, coarser TF than the existing same-TF
`trend_ema` filter (already closed as unproven/tiny-sample). Chose
mean_reversion@1h (not another TF) because 1h was the closest-to-edge
mean_reversion baseline per distilled learnings (previously flagged OOS PF
1.9 one window / 0.44 another — "regime luck"); 4h HTF matches Run 16's
TF/HTF ratio for direct comparability.

**Method:** thin subclass of production `MeanReversionStrategy` in
`research/experiments/mtf_mean_reversion_gate.py` — `decide()` defers
entirely to the unmodified parent and adds exactly one veto on BUY.
Production `mean_reversion.py` untouched. Swept the same 3 HTF EMA pairs
Run 16 used {10/30, 20/50, 50/100}. Windows: train 2026-03-21..2026-06-19
(150d-60d ago), test 2026-06-19..2026-08-18 (60d-0d ago, today's anchor),
older 2025-12-21..2026-03-21 (240d-150d ago) for the 3rd-window check. Base
params: shipped defaults (bb_period=20, bb_std=2.0, rsi_period=14,
rsi_oversold=30, rsi_overbought=70, exit_at=middle, trend_ema=0 — the
same-TF filter left off to isolate the new gate cleanly). 8 symbols, fees
7.5bps + slippage 4bps, $10,000/symbol.

**Results:**

| config | train PF / n | test PF / n |
|---|---|---|
| baseline (no gate) | 0.496 / 122 | 2.207 / 91 |
| 4h EMA10/30 gate | 0.925 / 49 | 1.139 / 31 |
| 4h EMA20/50 gate | 0.647 / 55 | 1.126 / 40 |
| 4h EMA50/100 gate | 0.456 / 77 | 1.003 / 41 |

Baseline re-confirms the standing "regime luck" pattern even more starkly
than before (train fails decisively, test is a huge outlier) — the
underlying signal has no train-side edge to gate around in the first
place. 50/100 fails outright on both sides (adequate sample). 20/50
barely clears the test-side numeric bar but has a worse train PF (0.647)
than the 10/30 standout, so it's treated as closed by extension rather
than independently re-verified with a 4th window. 10/30 (standout) cleared
test but its 3rd-window check came back PF 0.423/64 trades — decisive
fail, real sample. Only 1 of 3 windows clears the bar for the best config,
versus 2/3 for Run 16's MTF trend_momentum near-miss. Per-symbol breakdown
for 10/30 (24 cells) shows the same scattered lucky/unlucky single-symbol
pattern as every other closed gate (LINK train PF 23.0/5 trades, DOGE
train PF 0.056/5 trades, BTC test PF 4.05/9 trades, XRP test PF 0.0/1
trade, DOGE test PF inf/4 trades) — no cross-symbol consistency.

**$ impact (test window, on $100 / $1000 notional, aggregate across 8
symbols):** baseline +$0.12 / +$1.17 (huge but decisively regime-luck per
train side); 10/30 gate -$0.0 / -$0.01; 20/50 gate -$0.0 / -$0.01; 50/100
gate +$0.0 / +$0.0 — all three gated variants are functionally flat,
consistent with "no edge either way."

**Decision: reject / noise (4 configs logged, no candidate).** Both
applications of the MTF gate mechanism (trend_momentum Run 16,
mean_reversion Run 17) are now closed. See DISTILLED LEARNINGS above for
the durable conclusion and per-config rationale in
`research/decisions.jsonl`.

**No code changes** — this was a research-only run; no bar was cleared, so
no production code, default params, or tests were touched.

**Verdict:** _No CANDIDATE FOUND this run._

---

## 2026-08-18 — Run 16

**Self-correction check:** reviewed commits since Run 15 — only Run 15's
own log commit. No strategy/risk/backtest code touched since Run 15;
nothing to re-validate or revert. (This research programme has never
adopted a code/param change across all 16 runs — a well-recorded string of
null results.)

**Region chosen:** multi-timeframe (MTF) trend-direction confirmation for
`trend_momentum` @ 1h, gated on 4h — Run 15's flagged option (a), "a
genuinely different indicator/signal family entirely (not ADX, not simple
relative-volume)". Picked over DCA multiplier magnitude (option (b), low
priority) because a third independent test of the "does *any*
confirmation gate rescue trend_momentum's base EMA-cross signal" question
is the highest-value open question — MTF is mechanically distinct from
both closed gates (ADX = same-candle trend *strength*, volume = same-
candle *participation*; MTF = a coarser timeframe's own trend
*direction*, information neither prior gate could see).

**Method:** implemented as a thin subclass of the production
`TrendMomentumStrategy` in a standalone research script
(`research/experiments/mtf_trend_momentum_gate.py`, NOT merged into
`trend_momentum.py` — exploration, no code shipped), same pattern as
Run 11/15's gate scripts: `decide()` defers entirely to the parent's
unmodified `decide()` and adds exactly one veto — a BUY signal is
downgraded to HOLD unless the 4h EMA(htf_fast) > EMA(htf_slow) on the
most recently *closed* 4h candle strictly before the 1h signal candle
(enforced via a `pd.merge_asof` backward join on `open_time` vs 4h
`close_time`, so there is no lookahead). Fixed at the same 1h shipped-
default combo Runs 11/15 used (`ema_fast=20, ema_slow=50, rsi_buy_min=50,
require_macd=True`). Swept 3 HTF EMA pairs {10/30, 20/50, 50/100}, train
2026-03-19→2026-06-18 (150d-60d ago) / test 2026-06-18→2026-08-18 (60d-0d
ago, today's anchor), fees 7.5bps + slippage 4bps, $10,000/symbol, all 8
symbols aggregated. Production `run_candle_backtest` used unmodified on
the 1h series; 4h series fetched and its EMAs computed once per
symbol/window, then merged onto the 1h frame before the backtest runs.

**Result — mixed; 2 clean rejects, 1 near-miss resolved as noise.**

| HTF pair | train PF | train n | test PF | test n |
|---|---|---|---|---|
| none (baseline) | 0.586 | 94 | 0.480 | 63 |
| 10/30 | 0.663 | 32 | 1.023 | 22 |
| 20/50 | 0.917 | 39 | 1.256 | 29 |
| 50/100 | 1.093 | 47 | 0.597 | 33 |

10/30 fails the OOS PF bar outright (1.023 < 1.1) with a sub-floor sample
(22 trades) — clean reject. 50/100 has the highest train PF in the sweep
(1.093, adequate 47-trade sample) but test PF drops to 0.597 on an
adequate 33-trade sample — the same train-improves/test-doesn't shape as
the ADX and volume gates — clean reject, no 3rd window needed.

**20/50 is the near-miss.** Test PF 1.256 clears the 1.1 bar, but test
trades = 29 is 1 below the 30-trade floor, and train PF is only 0.917 (no
train-side edge on the very data that would select this config). Per
protocol, ran a 3rd non-overlapping window (2025-12-19→2026-03-19,
240d-150d ago): **PF 1.336, 34 trades, ret +2.67%** — clears both
anti-noise bars cleanly. So 2 of 3 windows (test near-miss + older-clean)
pass, 1 (train) does not — the identical "2/3 windows" shape as Run 11's
ADX floor=20, which was closed as regime luck.

**Per-symbol breakdown (train/test/older × 8 symbols = 24 cells)** shows
why this doesn't survive closer inspection: sample sizes per cell are 0-8
trades, and several cells show inf or 0.0 PF from single-trade symbols
(test: BTC 2 trades/PF=inf, LINK 5 trades/PF=6.94, DOGE 1 trade/PF=0.0;
older: XRP 4 trades/PF=0.0, ADA 6 trades/PF=0.0, BTC 3 trades/PF=8.66).
The aggregate PF is a handful of lucky/unlucky single-symbol outcomes
averaging out across the 8-symbol universe, not a consistent per-symbol
mechanism — the same diagnostic that closed the ADX floor=20 case.

**$100 / $1000 account translation:** every config is near-zero on test —
baseline −$0.08/−$0.80, 10/30 +$0.00/+$0.01, 20/50 (the near-miss)
+$0.01/+$0.14, 50/100 −$0.03/−$0.29. No config clears a magnitude worth
deploying even before the noise diagnosis.

**Verdict: `reject` for baseline/10/30/50/100, `noise` for 20/50 (4
configs logged in `decisions.jsonl`).** No code change — MTF trend-
direction confirmation is closed for trend_momentum@1h→4h using this
8-symbol/150d methodology. Given the mechanism (a directional gate can't
fix a signal that has no train-side edge to begin with) generalizes, this
is not expected to behave differently at other entry/HTF TF pairs either.

**Next run should rotate to:** (a) DCA multiplier magnitude 2.0x (low
priority, last open DCA variant); (b) apply the same MTF trend-direction
gate *mechanism* to `mean_reversion` instead of `trend_momentum` — gating
a mean-reversion BUY on the HTF trend being *against* the reversion
direction (opposite hypothesis to gating a momentum entry *with* the
trend) is a different test of the same mechanism, worth one clean pass
before retiring MTF gating entirely; (c) consider whether a genuinely
different strategy family is warranted given 16 runs of no edge in any
tested family or gate.

_No CANDIDATE FOUND this run — MTF trend-direction confirmation, the
third confirmation-indicator family tried, produces the closest near-miss
yet (2/3 windows clear the OOS bar) but fails per-symbol consistency
review the same way the ADX floor=20 precedent did; not adopted._

---

## 2026-08-17 — Run 15

**Self-correction check:** reviewed commits since Run 14 — only `5b148cc`
(Run 14's own log commit). No strategy/risk/backtest code touched since
Run 14; nothing to re-validate or revert. (More broadly: `git log` on
`backend/app/strategies|risk|backtest` shows the only non-research commits
there predate this research programme entirely — this programme has never
adopted a code/param change, so there has never been anything to
self-correct across all 15 runs. A well-recorded string of null results.)

**Region chosen:** relative-volume confirmation gate for `trend_momentum`
@ 1h — per Run 14's flagged option (b), "a genuinely different
indicator/signal family entirely (not ADX)". Volume is a natural next
choice: unlike MACD/RSI/ADX (all derived purely from price), volume
measures participation, and Binance klines already carry it (unused by
any strategy in this repo today). Picked over DCA multiplier magnitude
(option (a)) because Run 14 flagged that DCA avenue as low-priority (the
cap result already suggests the shipped magnitude is close to its natural
shape), while a new indicator family for the still-fully-closed
candle-strategy side is the higher-value open question.

**Method:** implemented as a thin subclass of the production
`TrendMomentumStrategy` in a standalone research script
(`research/experiments/volume_trend_momentum_gate.py`, NOT merged into
`trend_momentum.py`/`indicators.py` — exploration, no code shipped), same
pattern as Run 11's ADX floor script: `compute_indicators` adds one
relative-volume column (`rel_vol = volume / rolling_mean(volume, 20)`),
`decide()` defers entirely to the parent's unmodified `decide()` and adds
exactly one veto — a BUY signal is downgraded to HOLD if `rel_vol` at that
candle is below `vol_mult`. Fixed at the same 1h shipped-default combo
Run 11 used (`ema_fast=20, ema_slow=50, rsi_buy_min=50,
require_macd=True`) for direct comparability between gate mechanisms on
the same base signal. Swept `vol_mult` ∈ {none (baseline), 1.0, 1.2, 1.5,
2.0}, train 2026-03-19→2026-06-18 (150d-60d ago) / test
2026-06-18→2026-08-17 (60d-0d ago, today's anchor), fees 7.5bps +
slippage 4bps, $10,000/symbol, all 8 symbols aggregated. Production
`run_candle_backtest` used unmodified.

**Result — decisive, monotonic reject; no 3rd-window check needed.**
Baseline (no gate): train PF 0.586/94 trades, test PF 0.483/82 — matches
the standing no-edge finding for this combo (Run 11's baseline on a
slightly earlier window: train 0.575/95, test 0.492/80, same shape).
Sweep:

| vol_mult | train PF | train n | test PF | test n |
|---|---|---|---|---|
| none | 0.586 | 94 | 0.483 | 82 |
| 1.0 | 0.925 | 63 | 0.530 | 47 |
| 1.2 | 0.898 | 61 | 0.619 | 34 |
| 1.5 | 1.193 | 37 | 0.598 | 29 |
| 2.0 | 1.217 | 22 | 0.668 | 19 |

Train PF rises steadily as the gate tightens (fewer, more "confirmed"
entries, win% 22%→41%) — at 1.5 and 2.0 it even clears 1.0, the first
time this exact 1h combo has ever done so on a train screen (Run 11's
best was 0.575 with require_macd, up to 0.738 there with an ADX floor=15
that itself failed). **Test PF never follows** — it stays in a tight
0.48-0.67 band across every threshold, decisively below the 1.1 bar
regardless of gate tightness. The two highest-train-PF thresholds (1.5,
2.0) also fall under/at the 30-trade OOS floor (29, 19 trades) — a double
failure (small-sample AND wrong-direction), but even the sample-adequate
middle thresholds (1.0: 47 test trades, 1.2: 34 test trades) show the
same flat-low test PF, so this isn't merely a sample-size artifact.

**Mechanism.** A relative-volume gate filters *which* EMA crosses get
taken, but doesn't change *whether* the EMA-cross signal itself has edge.
The gate happens to correlate with higher win-rate trades within this
specific train window (classic in-sample selection — of the 94 raw
crosses, the ~20-40% "highest volume" subset just happened to perform
better here), but that correlation is regime-specific and doesn't carry
to the test window. This is the same qualitative shape as the ADX floor
result (Run 11: floor=20 cleared both bars on 2 windows then failed a
3rd) and the mean_reversion@1h default-params near-miss (Run 2-3) — a
confirmation filter reshuffling which of a fundamentally weak signal's
trades survive, not adding real predictive power. Unlike those two cases,
this one is unambiguous enough (test PF never gets remotely close to 1.1
at any threshold) that a 3rd-window cross-check isn't needed to reach a
verdict — the protocol's 3rd-window step is reserved for configs that
pass both anti-noise bars in both windows, which none of these do.

**$100 / $1000 account translation:** every threshold is net negative on
test — best case (vol_mult=2.0, sub-floor sample) −$0.02/−$0.20 over 60d;
worst case (vol_mult=1.0) −$0.06/−$0.59 over 60d. Baseline (no gate):
−$0.10/−$1.00. No positive candidate anywhere in the sweep; gating
doesn't even improve the dollar outcome, only the (uninformative) train
PF.

**Verdict: `reject` (baseline + vol_mult=1.0/1.2 logged as `reject`;
vol_mult=2.0 also logged, tagged `noise` for its sub-floor sample size on
top of the clear test-side failure). 5 configs logged in
`decisions.jsonl`.** No code change — relative-volume confirmation is
closed for trend_momentum@1h. Given the mechanism (filtering doesn't fix
a signal with no underlying edge) is general, not 1h-specific, this is
not expected to behave differently at other TFs either, so not planned
for re-test elsewhere absent a reason to think 1h is unusually bad for
this particular gate.

**Next run should rotate to:** (a) multi-timeframe trend confirmation —
gate a fast-TF entry (e.g. 15m/1h EMA cross) on a slower TF's own trend
direction (e.g. 4h EMA fast>slow) — genuinely different from both closed
gates (ADX measures trend *strength* on the same candles, volume measures
*participation*; this would test whether a coarser timeframe's directional
context, not measured by either, adds real information); (b) DCA
multiplier magnitude 2.0x, the last open DCA variant from Run 4's
original list (low priority per Run 14).

_No CANDIDATE FOUND this run — relative-volume confirmation, the first
non-price-derived indicator tried, fails cleanly for trend_momentum; the
train-improves/test-doesn't pattern is now confirmed across two
independent confirmation-indicator families (ADX, volume)._

---

## 2026-08-17 — Run 14

**Self-correction check:** reviewed commits since Run 13 — only `3350b1a`
(Run 13's own log commit). No strategy/risk/backtest code touched since
Run 13; nothing to re-validate or revert.

**Region chosen:** DCA dip-rebuy cap — the specific open variant flagged
in Run 13's distilled learnings ("revisit DCA ... for further variants
(e.g. multiplier magnitude, cap on dip re-buys)"), since all three
candle-strategy families (trend_momentum, mean_reversion, grid) are fully
closed across the 5m-4h TF sweep as of Run 13 and ADX is closed in both
directions tried. Picked the cap idea over multiplier magnitude because
it directly tests the specific "over-concentration into a falling asset"
concern that was the stated reason the more-aggressive 2.5x/3% variant
was rejected in Run 4 — a sharper, more informative question than another
magnitude point.

**Method:** research-only reimplementation of `run_dca_backtest`'s core
loop (`research/experiments/dca_dip_cap.py`, production `dca.py`
untouched) adding a per-window counter: once `dip_max_buys` dip-
multiplied buys have fired, later qualifying dips still buy on schedule
at the flat `quote_amount` (schedule is never skipped), just without the
1.5x bonus. Sanity-checked `dip_max_buys=None` against unmodified
production `run_dca_backtest` on BTC/train — unrealized_pnl matched to
within 0.05% (float-rounding-order noise, not a logic bug). Same 3-
non-overlapping-window x 8-symbol capital-normalized-ROI methodology as
Run 4/5 (`unrealized_pnl/invested %`, no round-trip trades so PF/trade-
count doesn't apply), windows shifted to today's anchor: older reference
2025-12-19→2026-03-19, train 2026-03-19→2026-06-18 (150d-60d ago), test
2026-06-18→2026-08-17 (60d-0d ago, today). Shipped default params
throughout (`interval=daily, quote_amount=15, dip_threshold_pct=5.0,
dip_multiplier=1.5`); only the new `dip_max_buys` cap varied: None
(uncapped baseline), 5, 3, 2, 1.

**Result — decisive, monotonic reject.** ROI delta (capped − uncapped),
averaged across all 8 symbols:

| window | uncapped ROI% | cap=5 Δ | cap=3 Δ | cap=2 Δ | cap=1 Δ | dip events (uncapped) |
|---|---|---|---|---|---|---|
| older (ref) | −11.48 | −0.23pp | −0.36pp | −0.38pp | −0.35pp | 56 |
| train | −12.90 | −0.02pp | −0.08pp | −0.12pp | −0.15pp | 27 |
| test | +1.81 | 0.00pp | 0.00pp | 0.00pp | 0.00pp | 3 |

**0 of 8 symbols ever beat the uncapped baseline, at any cap level, in
any window.** The older and train windows (56 and 27 real dip events
respectively) show a consistent, near-monotonic worsening as the cap
tightens — cap=5 barely dents ROI, cap=1 (allow only the very first
qualifying dip, then never again) costs the most. The test window is not
informative either way: only 3 total dip events fired across all 8
symbols in 60 days, so even the strictest cap (1) never actually bound
for 7/8 symbols — ROI is identical to uncapped by construction, a tie
not a real comparison. (cap=2 was marginally worse than cap=1 in the
older window, −0.3819pp vs −0.3531pp — noise-level non-monotonicity
between two adjacent tight caps, doesn't change the overall trend.)

**Mechanism.** This result is mechanically clean, not curve-fit: dip
events cluster in declining/volatile stretches (by construction — the
trigger *is* a ≥5% 24h drop). In such a stretch, buying MORE at the dip
lowers the accumulated position's average cost basis further, which
directly improves (or least-worsens) unrealized ROI once the window ends
— capping removes exactly the buys that land at locally-lower prices, so
it can only tie or hurt, structurally, never help. This is the opposite
of the "repeated dip-buying over-concentrates into a still-declining
asset" concern that motivated testing this (the stated reason the
2.5x/3% variant was rejected in Run 4) — that concern turns out to not
apply at the shipped 1.5x/5% magnitude: more dip-buying in a decline is
a cost-basis benefit here, not a risk amplifier.

**Verdict: `reject` — do not cap dip re-buys.** The uncapped shipped
default (`dip_enabled=True, dip_threshold_pct=5.0, dip_multiplier=1.5`,
no cap) remains correct and unchanged. No code change; this was a pure
evaluation against a research-only script, production `dca.py` untouched.
3 representative decisions (cap=5, cap=3, cap=1) logged in
`decisions.jsonl`.

**$100 / $1000 translation:** worst case tested (cap=1) would have cost
−$0.15 per $100 (−$1.51 per $1000) deployed over the train window vs
just leaving the shipped default uncapped; the older reference window
shows a larger −$0.35/−$3.53 cost at the same cap. Never positive at any
cap level in any window.

**Next run should rotate to:** either (a) DCA multiplier magnitude
between 1.5x (shipped) and 2.5x (rejected) — e.g. 2.0x, the one DCA
variant from Run 4's original list still untested, though the cap result
here suggests the shipped magnitude is already close to right; or (b) a
genuinely different indicator/signal family for the candle strategies
(not ADX, which is closed) — this is likely the higher-value avenue given
DCA's remaining search space is now small.

_No CANDIDATE FOUND this run — DCA dip-rebuy cap closed with a clean,
mechanically-explicable null result; shipped default confirmed correct._

---

## 2026-08-16 — Run 13

**Self-correction check:** reviewed commits since Run 12 — only the log/
decisions commit for Run 12. No strategy/risk/backtest code touched since
Run 12; nothing to re-validate or revert.

**Region chosen:** `grid` @ 5m — the last untested TF for this family
(15m/1h/4h already grid-searched and closed with no edge, Runs 2/8). This
was the gap flagged but not taken in Run 12 (which chose trend_momentum @
5m instead). Both ADX-gate variants of this research programme (grid
ceiling-gate Run 10, trend_momentum floor-gate Run 11) are closed as
no-improvement/noise, so this run does not re-attempt ADX gating — pure
baseline sweep.

**Method:** 2 configs (range=10%/6%, levels=13, `flatten_on_stop=True`,
quote_per_level=150 — identical shape to Run 2/8 for direct TF-to-TF
comparability), unmodified production `run_grid_backtest` +
`compute_metrics`, no code changes. Train 2026-03-19→2026-06-17
(150d-60d ago), test 2026-06-17→2026-08-16 (60d-0d ago, today's anchor).
Fees 7.5bps + slippage 4bps, $10,000/symbol, all 8 symbols aggregated.
Script: `research/experiments/grid_5m.py`.

**Result — decisive rejection, no ambiguity.** range=10%: train PF 0.848
(199 trades), test PF 0.228 (106 trades). range=6%: train PF 0.42 (184
trades), test PF 0.343 (154 trades). Both configs fail the train screen
outright (PF<1) and stay negative OOS with real samples well above the
30-trade floor — the cleanest grid rejection of any TF tested (1h/4h both
had at least one train-passes/OOS-collapses pattern to disentangle; 5m
has none).

**Mechanism, and why the "candle-count-independent" hypothesis was
wrong.** Went in expecting grid's range math (operates on price levels
touched, not candle count) might behave differently from
trend_momentum/mean_reversion's TF sensitivity (driven by signal noise
and daily-loss-halt interaction). It didn't: train win-rate was unusually
*high* (67-77%, vs ~50-55% typical at 1h/4h) yet PF still collapsed —
many small wins from tight, noisy intra-range chop on 5m candles, offset
by a handful of large losses whenever price actually breaks the range and
`stop_outside_range`/`flatten_on_stop` fires. Finer time resolution
increases the *count* of round-trips inside the same overall price
excursion without improving their quality — more granular sampling of
the same directional risk, not a new edge.

**Verdict: `reject` both configs, real (non-noise) samples in both
windows.** No code change. This closes the grid family across every
swept TF (5m/15m/1h/4h) — combined with trend_momentum (Run 12) and
mean_reversion (Run 9) already being closed at 5m too, **all three
candle-strategy families are now fully closed across the entire 5m-4h TF
sweep.** Remaining unexplored regions for these families (1m — known
catastrophic pattern from every strategy tested there, not worth
retesting; 1d — untested everywhere, low priority, same starvation
concerns as 4h's `trend_ema=200` issue) are not expected to change the
verdict. Future sessions should treat further TF/param sweeps of these
three families as exhausted and prioritize a genuinely different
signal/indicator family (ADX is also closed, both applications), or
revisit DCA — this research programme's one validated positive
mechanism.

**Commit:** pending (this run). $ impact: on $100/$1000, both configs
net negative over the 60-day test window — range=10% -$0.50/-$4.96,
range=6% -$0.30/-$2.97 (average per-symbol return basis, matching how
every prior run in this log computes usd_pnl).

---

## 2026-08-16 — Run 12

**Self-correction check:** reviewed commits since Run 11 — only `ac76c86`
(Run 11's own log commit). No strategy/risk/backtest code touched since
Run 11; nothing to re-validate or revert.

**Region chosen:** `trend_momentum` @ 5m — the last untested TF for this
family (4h/1h/15m already grid-searched and closed with no edge, Runs
1/3/7; both ADX-confirmation variants, Runs 10/11, also closed). Chosen
over the alternative gap (`grid` @ 5m, also untested) because
mean_reversion's own 5m pass (Run 9) turned out to be the cleanest,
most decisive failure of that family — filling the last TF gap was more
informative than expected, so the same reasoning was applied here rather
than assuming the outcome and skipping it.

**Method:** 12-combo grid (3 EMA pairs {20/50, 9/21, 12/26} x 2
`rsi_buy_min` {45, 50} x 2 `require_macd` {True, False}) — identical
shape to Run 7's 15m grid, for direct TF-to-TF comparability. Production
`TrendMomentumStrategy` and `run_candle_backtest`, unmodified — pure
evaluation, no code changes. Train 2026-03-19→2026-06-17 (150d-60d ago),
test 2026-06-17→2026-08-16 (60d-0d ago, today's anchor), 3-day warmup
buffer (ema_slow≤50 candles @ 5m warms up in under a day). Fees 7.5bps +
slippage 4bps, $10,000/symbol, all 8 symbols aggregated. Script:
`research/experiments/trend_momentum_5m_grid.py`.

**Result — the worst trend_momentum result of any TF, and a sample-size
surprise.** Best (20/50 EMA, either rsi_buy_min, `require_macd=True`):
train PF 0.211/29 trades, test PF **0.028**/42 trades — decisively
negative in both windows, the lowest PF this research programme has
recorded for a real (>10-trade) sample. Dropping MACD confirmation
scored similarly on train (PF 0.201/29) and numerically better on test
(PF 0.189/55) only because more (still-losing) trades got through — not
an improvement, MACD confirmation remains directionally useful as at
every other TF. The faster EMA pairs were effectively starved: 9/21 had
**zero** train trades across all 8 symbols over 90 days; 12/26 had just
1 train trade (34 real test trades, PF 0.094 — logged as noise, the
train screen never passed).

**Why fewer trades at a faster TF, not more?** The surprising part isn't
that 5m loses — every TF has — it's that the 20/50 combo produced *fewer*
train trades (29) than the identical combo at 15m (141), despite 5m
having ~3x more raw candles per day. The likely mechanism: the repo's
`max_daily_loss_pct=3%` halt blocks new entries for the rest of the UTC
day once tripped, and at 5m a fixed 2%/4% SL/TP against 5-minute noise
produces same-day loss clusters far more easily than at 15m — so the
effective sample gets silently pruned well below what the crossover
frequency alone would suggest. Not verified by direct instrumentation
this run (would require logging halt events, out of scope for a
no-code-change evaluation), but consistent with the shape of the data and
worth flagging as a general caution for any future fast-TF test that uses
tight fixed-pct stops: raw candle count is not a reliable predictor of
executed-trade count once daily risk halts are in the loop.

**Decision: reject / noise (4 combos logged in `decisions.jsonl`,
representative of all 12 per this run's established convention — top
combo, MACD-off sibling, and the two starved fast-EMA pairs).** No
code/param change — closes trend_momentum's TF sweep. The family is now
grid-searched with train/test rigor at every TF from 5m to 4h with zero
survivors; re-opening it needs a genuinely different signal design, not
another EMA/RSI/MACD parameter sweep (the ADX-floor variant already
explored this exact idea at 1h and also failed a 3rd-window check, Run
11). Remaining open gaps across all three candle strategies: `grid` @ 5m
(untested) and `1d` for any strategy (untested everywhere, low priority —
even fewer candles per window than 4h, likely the same starvation
pattern already seen for `trend_ema=200` at 4h).

**Verdict: no candidate. Honest null result — trend_momentum has now
been exhaustively searched across its full TF range with no edge found
anywhere.**
## 2026-08-15 — Run 11

**Self-correction check:** reviewed commits since Run 10 — only `2c69383`
(Run 10's own log commit). No strategy/risk/backtest code touched since
Run 10; nothing to re-validate or revert.

**Region chosen:** the sibling ADX idea flagged explicitly as the priority
next step in Run 10's log — `trend_momentum` with an ADX(14) confirmation
**floor** at entry (only take an EMA-cross entry when ADX(14) already
indicates a real trend), as opposed to grid's ADX **ceiling** gate (block
entries when ADX is too high). Motivated the same way Run 10 reasoned about
it: trend_momentum's documented failure mode across every TF tested
(15m/1h/4h, Runs 1/3/7) is whipsaw EMA-cross entries in weak/choppy
conditions — MACD confirmation already helps some but doesn't fix it; an
ADX floor is a more direct match for what "is there a real trend" measures
than grid's range-vs-trend question was.

**Method:** implemented as a thin subclass of the production
`TrendMomentumStrategy` in a standalone research script
(`research/experiments/adx_trend_momentum_gate.py`, NOT merged into
`trend_momentum.py`/`indicators.py` — exploration, no code shipped).
`compute_indicators` adds one ADX(14) column (Wilder, same implementation
validated in Run 10); `decide()` defers entirely to the parent's unmodified
`decide()` and adds exactly one veto: a BUY signal is downgraded to HOLD if
ADX(14) at that candle is below the floor. `adx_min_for_entry`/`adx_period`
are set as plain instance attributes (not routed through
`param_specs()`/`validate_params()`, which silently drops unknown keys —
first pass of the script had this bug and produced identical output at
every threshold; caught it by noticing the results didn't vary at all
across 5 different thresholds, a give-away that the gate wasn't firing).
Used production `run_candle_backtest` unmodified (unlike Run 10's grid
experiment, which had to copy the simulator loop). Fixed at the
shipped-default 1h combo (`ema_fast=20, ema_slow=50, rsi_buy_min=50,
require_macd=True` — the least-bad train combo from Run 3's 18-combo grid),
swept `adx_min_for_entry` ∈ {none (baseline), 15, 20, 25, 30}, train
2026-03-18→2026-06-16 / test 2026-06-16→2026-08-15 (same anchors as Run
10), fees 7.5bps + slippage 4bps, $10,000/symbol, all 8 symbols aggregated.

**Result — one config looked like a real candidate, then failed a 3rd
window.** Baseline (no gate): train PF 0.575/95 trades, test PF 0.492/80 —
matches the standing no-edge finding for this exact combo (Run 3). Sweep
was monotonic through floor=20 then broke down:
floor=15 train 0.738/109→test 0.938/70 (both still <1);
**floor=20 train 1.124/73→test 1.176/35 — clears PF>1.1-ish and the
30-trade floor in BOTH windows**, win% moving with PF (22%→34%→43% as the
floor tightens) rather than the disconnected train-fails/OOS-lucky shape
seen everywhere else in this research; floor=25 train 0.897/32 (test PF
1.809 but only 10 trades, sub-floor); floor=30 train 0.489/17 (test PF
6.723 on 3 trades — obvious noise, one winning trade dominates).

Per the standing precedent set by mean_reversion@1h (Run 2 found a
similar-looking OOS pass despite a failing train screen, flagged as needing
a 3rd window, Run 3 then rejected it on that 3rd window), ran a third,
non-overlapping window for floor=20 before calling it anything:
**2025-12-15→2026-03-15 (240-150d ago): PF 0.706/56 trades — clearly
negative.** Also pulled the per-symbol breakdown for train/test/older: the
encouraging test-window aggregate (PF 1.176/35 trades) is built from only
1-6 trades per symbol (XRP 0% win/5 trades, DOGE 0% win/1 trade) — a lot of
single-draw noise sits under a smooth-looking aggregate number.

**Why:** ADX(14)>=20 on a 1h chart is a fairly loose floor (many candles
qualify), so it isn't filtering hard enough to be a real "only trade
confirmed trends" signal — it's closer to a soft, regime-sensitive
re-weighting of which of the existing (weak) EMA-cross entries fire, and
different 60-90 day windows apparently disagree on whether that
re-weighting helps or hurts. Exactly the same shape as the grid+ADX result
(Run 10) and the mean_reversion@1h default-params finding (Runs 2-3): a
plausible-looking mechanism that doesn't survive a third independent
sample.

**$100 / $1000 account translation:** floor=20 test window (the one that
looked good): +$0.01/+$0.09 over 60d. Same config, older window:
-$0.05/-$0.48 over 90d. Net picture: not a reliable source of profit in
either direction, consistent with "noise" rather than "small edge."

**Verdict: closed as tested.** Both ADX applications flagged since Run 8
(grid ceiling-gate in Run 10, trend_momentum entry-floor here) are now
tried and rejected. The ADX(14) implementation remains reusable in the
research scripts, but further threshold tuning of either application is
not worth re-attempting — a materially different indicator family (volume-
based, volatility-regime, or multi-timeframe confirmation) would be needed
to reopen either strategy family.

**Next run should rotate to:** (a) DCA `time_utc` sensitivity (flagged
since Run 5, still open, low-effort confirmatory check — the last
unexplored DCA axis); (b) 1d timeframe for mean_reversion/trend_momentum
(low priority — likely `trend_ema=200`/EMA-warmup starvation given even a
150d train window is only ~150 daily candles, similar to 4h's starvation
issue in Run 6); (c) if a genuinely new signal-design idea presents itself,
it would need to be a different indicator family than ADX, since both
flagged ADX directions are now closed.

_No CANDIDATE FOUND this run — a config that initially looked like a real,
non-curve-fit edge (trend_momentum 1h + ADX(14)>=20 floor, clearing both
anti-noise bars in both train and test) failed a mandatory 3rd-window
cross-check, the same discipline that closed a similar-looking
mean_reversion@1h result in Run 3. Honesty over optimism: logging the
near-miss and why it didn't survive is more valuable than the 2-window
pass alone would have been._

---

## 2026-08-15 — Run 10

**Self-correction check:** reviewed commits since Run 9 — only `2af62cc`
(Run 9's own log commit). No strategy/risk/backtest code touched since
Run 9; nothing to re-validate or revert.

**Region chosen:** a genuinely new signal design, per Run 8/9's flagged
next step — with mean_reversion/trend_momentum/grid all fully
train/test-grid-searched at every standard TF (5m-4h) with no edge found,
further parameter tuning within the existing signal families is
exhausted. Implemented an ADX(14) trend-strength indicator (Wilder,
standard TR/+DI/-DI/DX/ADX smoothing) and tested it as a **range-vs-trend
gate for the grid strategy** — the more mechanistically motivated of the
two flagged ADX applications, since grid's documented failure mode
(bag-holding through directional trends) is exactly what a trend-strength
filter should address, unlike trend_momentum where MACD already serves a
similar confirmation role.

**Method:** ADX implemented in a standalone research script
(`research/experiments/adx_grid_gate.py`) — NOT merged into
`indicators.py`/`grid.py`/`simulator.py`, since this is exploration, not
an adopted change. The script copies `run_grid_backtest`'s exact logic
and adds one gate: new grid buys are skipped on any candle where
ADX(14) >= threshold; the existing `stop_outside_range`/
`flatten_on_stop` pause-and-flatten mechanism is completely untouched
(sells/pause continue exactly as in production). Tested at 1h on the two
least-bad `flatten_on_stop=True` configs from Run 8
(`auto_range_pct=10/levels=13` and `auto_range_pct=6/levels=13`,
`quote_per_level=150`), across ADX thresholds {none (baseline), 30, 25,
20, 15}, train/test split (TRAIN 2026-03-18→2026-06-16, TEST
2026-06-16→2026-08-15 — today's anchor), fees 7.5bps + slippage 4bps,
$10,000/symbol, all 8 symbols aggregated per combo. Sanity-checked the
copied backtest logic against production `run_grid_backtest` directly
(threshold=None case) — trade count and return matched exactly (110
trades, -0.438% avg return for the range=10 config), confirming the
research script isn't introducing its own bug.

**Result: clean negative — ADX gating never helps, sometimes hurts.**
This run's window is markedly worse for grid than Run 2/8's window even
at the ungated baseline: range=10 baseline train/test PF 0.285/0.285 and
range=6 baseline 0.236/0.481, vs Run 2's identical params on its window
(1.506/0.655 and 1.169/0.647) — a reminder of how regime-dependent grid's
raw numbers are, consistent with the standing "directional bet in
disguise" finding. Against that baseline, **every ADX threshold tested
made train PF flat-to-worse, never better**: range=10 baseline 0.285 →
gated 0.194-0.214 across all 4 thresholds; range=6 baseline 0.236 →
gated 0.072-0.230. Test-window PF shows the same non-improving pattern.
Trade count drops substantially as the threshold tightens (up to 4x fewer
trades at adx<15) with no compensating PF gain — the gate filters out
volume, not losses.

**Why:** with the wide 6-10% auto-range already in place, grid's losses
come from ordinary in-range price chop and the eventual out-of-range
exit, not specifically from high-ADX periods. By the time ADX(14)
actually elevates on a 1h chart, price has typically already left the
grid's range and `stop_outside_range` has already paused it — so the
ADX gate is largely redundant with a mechanism the strategy already has,
and just prunes trade count for no PF benefit.

**$100 / $1000 account translation:** best result this run is still the
range=6 no-gate baseline test window (-0.267% → -$0.27/-$2.67 over 60d);
every gated variant is flat-to-worse than that. No positive candidate
anywhere in the sweep.

**Verdict:** the grid+ADX idea is closed as tested — a genuinely new
signal design was tried in good faith and failed cleanly, which is itself
useful (rules out the most obvious "fix" for grid's known failure mode).
The ADX(14) implementation is kept in the research script for reuse.

**Next run should rotate to:** (a) the sibling ADX idea — trend_momentum
with an ADX confirmation layer (only take EMA-cross entries when
ADX(14) is above a trend-strength floor), still open and now the only
untested "new signal design" flagged; unlike grid, trend_momentum's
failure mode (whipsaw entries in choppy/weak-trend conditions) is a more
direct match for what ADX measures, so this may behave differently than
the grid result; (b) DCA `time_utc` sensitivity (flagged since Run 5,
still open, low-effort confirmatory check); (c) 1d timeframe for
mean_reversion/trend_momentum, low priority given likely `trend_ema=200`
starvation and thin daily-candle samples.

_No CANDIDATE FOUND this run — first test of a genuinely new signal
design (ADX trend-strength gate) fails cleanly for grid; the idea remains
open for trend_momentum next._

---

## 2026-08-14 — Run 9

**Self-correction check:** reviewed commits since Run 8 — none landed
(`76435c4` was Run 8's own log commit). No strategy/risk/backtest code
touched since Run 8; nothing to re-validate or revert.

**Region chosen:** `mean_reversion` @ 5m — the last untested TF for this
family (15m/1h/4h all done in prior runs, all no-edge), per Run 8's
flagged next step (b). Closes the standard-TF sweep (5m-4h) for
mean_reversion if this also fails.

**Method:** train/test split, TRAIN = 2026-03-17→2026-06-15 (150d-60d
ago), TEST = 2026-06-15→2026-08-14 (60d-0d ago, today's anchor) — same
anchors as Run 8. 24-combo grid: `bb_std` ∈ {2.0,2.5,3.0} × `rsi_oversold`
∈ {25,30} × `exit_at` ∈ {middle,upper} × `trend_ema` ∈ {0,200}, identical
shape to the 1h (Run 2) and 4h (Run 6) searches, aggregated across all 8
symbols. Also ran the shipped-default params (`bb_std=2.0,
rsi_oversold=30, exit_at=middle, trend_ema=0`) as a reference, same as
every prior grid run. Fees 7.5bps + slippage 4bps, $10,000/symbol.

**Result: decisive, unambiguous failure — no small-sample noise this
time.** Unlike 1h/4h where the `trend_ema=200` half of the grid starved to
2-6 trades, at 5m even `trend_ema=200` combos got real samples (5-91
train trades) because a 150-day window is ~43,000 5m-candles — plenty of
data. Despite that, **every `trend_ema=0` combo has train PF < 1** (11
combos, range 0.181-0.748, best 262 real trades) — a clean train-screen
rejection with no ambiguity about sample size. OOS-validated the top 3
train-ranked real-sample combos anyway: best (`bb_std=3.0, rsi_os=25,
exit=upper, trend_ema=0`) went train PF 0.748/262 trades → test PF
1.064/171 trades — a real sample, but PF itself is too weak to clear the
1.1 anti-noise bar. The other two stayed negative both windows (test PF
0.836/171→235 trades and 0.745/192 trades). **Shipped default reference
is the cleanest default-failure of any TF tested so far**: train PF
0.181/126 trades, test PF 0.347/146 trades — negative in BOTH windows by
a wide margin, no train-fails/OOS-clears regime-luck story available (the
pattern that made the same default params ambiguous at 1h and 4h simply
doesn't appear here — 5m fails outright, same shape as 15m's
trend_momentum failure in Run 7).

**Verdict: mean_reversion now has full train/test grid coverage at
5m/15m/1h/4h — no edge at any of these four timeframes.** Only 1m
(already catastrophic, never retest) and 1d (untested, low priority —
even a 150-day train window is only ~150 daily candles, likely to starve
`trend_ema=200` the way 4h's 90-day/540-candle window did) remain
unexplored for this family.

**$100 / $1000 account translation:** best OOS result this run (the
train-PF-0.748 combo): +$0.02/+$0.17 over 60d — real sample, but PF too
weak to trust, and the parent train window already rejected it. Shipped
default: -$0.09/-$0.93 OOS (60d), -$0.14/-$1.40 in-sample. No positive
candidate anywhere in the grid.

**Next run should rotate to:** with mean_reversion now closed at
5m/15m/1h/4h (joining trend_momentum and grid, both closed at 15m/1h/4h),
the standard candle-strategy parameter-tuning approach is essentially
exhausted on this 8-symbol universe at every TF worth testing. Worth
trying next: (a) a genuinely new signal design — an ADX-based range/
trend-strength filter, applicable to gating `grid` (only run it when
ranging) and as a confirmation layer for `trend_momentum` (flagged since
Run 8, still the most promising unexplored direction — everything else is
now parameter-tuning within exhausted designs); (b) DCA `time_utc`
sensitivity (flagged since Run 5, still open, low-effort confirmatory
check); (c) 1d timeframe for mean_reversion/trend_momentum, low priority
given the likely `trend_ema=200` starvation problem and very thin sample
sizes even without it (a 150-day train window is only ~150 1d-candles).

_No CANDIDATE FOUND this run — mean_reversion's standard-TF sweep (5m-4h)
now closes with the cleanest, least-ambiguous null result of any TF
tested for this family._

---

## 2026-08-14 — Run 8

**Self-correction check:** reviewed commits since Run 7 — none landed
(`1943c23` was Run 7's own log commit). No strategy/risk/backtest code
touched since Run 7; nothing to re-validate or revert.

**Region chosen:** `grid` @ 4h — the last untested cell for this family
(15m done founding session, 1h done Run 2 with full train/test rigor, both
directional-bag-holding failures). Closes the family if 4h also fails, per
Run 7's flagged next step.

**Method:** train/test split, TRAIN = 2026-03-17→2026-06-15 (150d–60d ago),
TEST = 2026-06-15→2026-08-14 (60d–0d ago, today's anchor). 8-combo grid:
`auto_range_pct` ∈ {6, 10} × `levels` ∈ {8, 13} × `flatten_on_stop` ∈
{True, False}, `quote_per_level=150`, `stop_outside_range=True` always, all
8 symbols aggregated per combo, fees 7.5bps + slippage 4bps, $10,000/symbol.
Also ran the shipped-default params (`auto_range_pct=5.0, levels=8,
flatten_on_stop=False`) as a reference, same as every prior grid run.

**Result — two distinct findings:**

1. **`flatten_on_stop=True` (properly risk-managed) fails the train screen
   outright, no ambiguity.** All 4 combos: train PF 0.31–0.69 (all <1),
   OOS PF 0.35–0.83 (all <1, real samples of 50–188 trades). Best of the 4
   (`auto_range_pct=6, levels=13`): train PF 0.689/105 trades → OOS PF
   0.826/183 trades — closest to breakeven but still a loser both windows.
   Narrower range + more levels (finer ladder) is consistently
   less-bad than wider range + fewer levels, but no combo gets anywhere
   near PF 1. This is an even cleaner failure than 1h's pattern (Run 2:
   train PF 1.51 looked good, then collapsed OOS to 0.66) — here train
   already rejects every combo, no regime-luck story is even available.

2. **`flatten_on_stop=False` produces a PF accounting artifact — new
   finding, not seen at 15m/1h because those runs didn't isolate it.** A
   grid sell order only ever fires *above* its paired buy (that's the whole
   mechanism), so if inventory is never force-flattened, every trade that
   *does* close is, by construction, a win — 100% win rate, trade-level PF
   literally undefined/infinite, for all 4 `flatten=False` combos AND the
   shipped default. This says nothing about whether the strategy is
   profitable: losses sit as unrealized mark-to-market drag on held
   inventory and never appear in trade PF at all. Reading the real,
   account-level return instead (`avg_ret_pct`, which marks inventory to
   the closing price) tells the true story: **every one of the 4 combos
   plus the shipped default lost money in train** (−0.68pp to −1.01pp) and
   **every one flipped to a small gain in test** (+0.16pp to +0.39pp,
   except the shipped default which was flat at −0.002pp). Train-loses/
   test-gains for literally every combo in the family is the clearest
   possible confirmation that this isn't a strategy edge — it's just
   unhedged directional spot exposure (whatever inventory happens to be
   held rides the market), riding the fact that the 60-day test window
   happened to trend more favorably than the 90-day train window.

**Verdict: grid has now been grid-searched with full train/test rigor at
15m, 1h, and 4h — no edge at any timeframe, and the mechanism is now fully
understood** (oscillation profit only exists while flattened losses are
excluded; the moment risk is actually managed, PF drops under 1). Family
closed for parameter tuning alone; would need a genuine range-detection
filter (ADX/volatility gate) to reopen, which no run has attempted.

**$100 / $1000 account translation:** best `flatten_on_stop=True` (real,
risk-managed) result this run: −$0.05/−$0.54 over 60d OOS. Shipped default
(`flatten=False`) reference: −$0.00/−$0.02 OOS (flat/noise), but −$0.70/
−$7.04 in-sample — a real loss the trade-level PF metric completely hides.
No positive candidate anywhere in the grid.

**Next run should rotate to:** with mean_reversion, trend_momentum, and
grid all now exhausted at 15m/1h/4h with train/test rigor, the standard
candle-strategy parameter-tuning approach is fully explored on this 8-symbol
universe. Worth trying next: (a) a genuinely new signal design — an ADX-
based range/trend-strength filter, applicable to both gating `grid` (only
run it when ranging) and as a new confirmation layer for `trend_momentum`
(flagged as the reopen condition for both families in the distilled
learnings); (b) a 5m timeframe sweep (still untested, low priority given
1m's catastrophic result); (c) DCA `time_utc` sensitivity (still open,
flagged since Run 5).

_No CANDIDATE FOUND this run — grid family closed with a clean,
mechanism-explained null result across all three timeframes tested, plus a
new methodological finding (flatten_on_stop=False PF is not a trustworthy
metric) that future grid runs should carry forward._

---

## 2026-08-13 — Run 7

**Self-correction check:** reviewed commits since Run 6 — only `433f7ae`
(research: log run 6). No strategy/risk/backtest code touched since Run 6;
nothing to re-validate or revert.

**Region chosen:** `trend_momentum` @ 15m — the last untested timeframe for
this family (4h done Run 1, 1h done Run 3, both no-edge). Closes the family
if this also fails.

**Method:** train/test split, TRAIN = 150d–60d ago, TEST = 60d–0d ago (2026-
08-13 anchor), same as every prior candle-strategy run. 12-combo grid: EMA
pairs {9/21, 12/26, 20/50 (shipped default)} × rsi_buy_min {45, 50} ×
require_macd {True, False}, TP/SL held at repo defaults (4%/2%). All 8
symbols, fees 7.5bps + slippage 4bps, $10,000/symbol.

**Result: every combo fails the train screen.** Best train PF was 0.993 —
literally the shipped default (`ema_fast=20, ema_slow=50, rsi_buy_min=50,
require_macd=True`) — still just under 1.0, with a real sample (141 train
trades). `rsi_buy_min` (45 vs 50) made zero difference to any combo's
result — RSI at the moment of an EMA cross-up never landed in [45, 50) in
this data, so the grid effectively collapsed to 6 distinct combos (3 EMA
pairs × require_macd). Ranked (train PF): 20/50+MACD 0.993/141 trades >
20/50 no-MACD 0.453/81 > 9/21 no-MACD 0.215/85 > 9/21+MACD 0.152/95 >
12/26 no-MACD 0.183/73 > 12/26+MACD 0.082/69. Faster EMA pairs (9/21,
12/26) are uniformly worse than 20/50 — more whipsaw entries, much lower
win rate (10–15% vs 29%). Dropping MACD confirmation is uniformly worse
than requiring it.

**OOS validation (top train-ranked combo, i.e. the shipped default):**
train PF 0.993/141 trades → test PF 0.325/74 trades (real sample). Also
ran the 2nd-ranked (20/50, no MACD): train PF 0.453/81 → test PF 0.307/78.
Both fail OOS decisively — no ambiguity, no lucky window. Unlike the 1h/4h
runs (where the *shipped default* scored train PF < 1 but then looked
lucky OOS, needing extra windows to debunk), 15m's default fails **both**
windows consistently. This is the cleanest, least-ambiguous no-edge result
for trend_momentum yet — no regime-luck story is even available here.

**Verdict: trend_momentum has now been grid-searched with full train/test
rigor at 15m, 1h, and 4h — no edge at any timeframe.** The family is closed
for the current ema-cross+RSI+MACD signal design; re-opening it would need
a materially different signal (e.g. ADX-based trend strength, volume
confirmation, a different indicator set entirely), not further parameter
tuning within this design.

**$100 / $1000 account translation:** shipped-default 15m config would
have lost ~$0.10 per $100 (~$1.00 per $1000) over the 60-day OOS window —
consistent with (slightly better than) its already-worse 1h OOS showing
in isolated windows, and worse than its 4h OOS reading; net picture across
all three TFs for this exact param set is "no reliable edge, sometimes
worse than fees, never reliably better."

**Next run should rotate to:** `grid` strategy @ 4h (untested — 15m and 1h
both done, both rejected for the same directional-bag-holding reason; 4h
would confirm/close the pattern at the last major TF), or start exploring
a materially different trend_momentum signal design (ADX filter) if the
research budget allows a code-level experiment rather than pure param
sweep.

_No CANDIDATE FOUND this run — trend_momentum family closed with a clean,
unambiguous null result across all three timeframes tested._

---

## 2026-08-13 — Run 6

**Self-correction check:** reviewed commits since Run 5 — `18145e4`
(recon: add a non-mutating localhost health probe) and `e684399`
(backend: start engine in background so uvicorn serves /api/health
immediately). Both are deploy/health-check plumbing only; neither touches
a strategy default, risk config, or backtest code. Nothing strategy-
affecting to revert.

**Region — mean_reversion @ 4h, first-ever pass (per rotation: candle-
strategy families were exhausted only at the specific TFs actually tested
so far — mean_reversion had 15m + 1h, trend_momentum had 4h + 1h, grid had
15m + 1h; 4h was the one genuinely untested cell for mean_reversion).**
Same train/test anchors as every prior run (train 2026-03-14→2026-06-12,
test 2026-06-12→2026-08-11) and the same 24-combo grid shape as Run 2's
1h search: `bb_std` ∈ {2.0,2.5,3.0} × `rsi_oversold` ∈ {25,30} × `exit_at`
∈ {middle,upper} × `trend_ema` ∈ {0,200}, aggregated across all 8 symbols.

At 4h a 90-day train window is only 540 candles and the 60-day test window
only 360 — much thinner than 1h's 2160/1440. This mattered immediately:
**every `trend_ema=200` combo (12 of 24) produced zero train trades across
all 8 symbols.** The 200-EMA warmup alone is ~33 days at 4h, and requiring
"oversold dip AND price above a slow trend EMA" simultaneously in the
remaining ~57 days never fired once for any symbol — a harder starvation
than the 3-6 trades trend_ema=200 managed at 1h (Run 2). Not a bug, just
confirms trend_ema=200 is untestable at 4h with a 90-day window; not worth
retrying without years of history.

Train screen on the remaining 12 `trend_ema=0` combos: best by PF was
bb_std=3.0/rsi_oversold=25 (PF 1.791) but only **2 train trades** (bb_std=
3.0 rarely triggers) — too small to mean anything, and it went on to score
**0 OOS trades**. The only combo with both train PF>1 *and* a real sample
was bb_std=2.5/rsi_oversold=30/exit=middle (train PF 1.143, 35 trades):
OOS PF 1.241 — numerically clears the 1.1 bar — but only **14 OOS trades**,
well under the 30-trade floor (the 60-day/360-candle test window just
can't accumulate more at this signal's fire rate). **Verdict: FAIL**, no
combo clears both anti-noise conditions.

Also re-ran the shipped-default params (`bb_std=2.0, rsi_oversold=30,
exit_at=middle, trend_ema=0`) as a reference at 4h, same as done at 1h in
Run 2/3: train PF 0.663 (fails the train screen — would not have been
selected by optimization), OOS PF 1.786/27 trades (still under 30). This
is the exact same train-fails/OOS-clears shape already investigated and
closed at 1h (Run 2 found OOS PF 1.903/120 trades on one window, Run 3's
3rd window then found PF 0.441/136 trades — net verdict: regime luck, not
an edge). The 4h version has an even smaller OOS sample than the already-
debunked 1h version, so it's not reopening anything, just confirming the
same params don't show a different story at a different TF either.

**$100 / $1000 translation:** best OOS result this run was the bb_std=2.5
combo, +$0.01/+$0.09 over 60 days on $8,000 test notional (14 trades,
sub-floor). Every other combo is flat, zero-trade, or matches the already-
rejected default pattern. No positive candidate.

**Verdict: no promising candidate this run.** No code or default-param
changes made. Nothing to revert (no strategy-affecting commits since
Run 5).

**Next run should rotate to:** the one remaining untested candle-strategy
cell is `grid @ 4h` (grid has only been tested at 15m and 1h so far, both
directional-bet failures — distilled learnings already say don't re-grid
it without a range-detection filter, so if picked up, that filter should
be built first rather than re-running the same directional bet at a new
TF). Otherwise: (a) DCA `time_utc` sensitivity (flagged by Run 5, still
open); (b) a 5m sweep for mean_reversion/trend_momentum (still untested,
low priority given 1m's catastrophic result and 15m already showing the
same no-edge pattern).

_No CANDIDATE FOUND this run._

---
