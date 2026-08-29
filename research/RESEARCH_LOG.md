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
position caps) held at repo defaults through Run 21. Run 22 opened the exit-
mechanism axis (a time-based forced exit, and SL/TP tightened — never
loosened — vs the shipped default); Run 23 opened the fee/cost-level axis
(fee_bps/slippage_bps swept down to a theoretical zero); Run 24 added a 5th
strategy family (Supertrend, ATR-adaptive trailing bands); Run 25 opened and
closed the symbol-universe axis (disjoint 8-symbol test); Run 26 closed the
1d-timeframe scope question for all 3 original families; Run 27 added and
closed a 6th strategy family (Capitulation Wick Reversal, first
candlestick-shape signal) and closed the last flagged-open DCA variant
(dip_multiplier magnitude); Run 28 opened and closed a 5th signal-source
category (UTC session-hour BUY gate — calendar-derived, not OHLCV-derived)
on trend_momentum@1h and mean_reversion@1h; Run 29 closed the day-of-week
granularity within that same calendar/session-time category; Run 30 tested
and closed the one remaining flagged combination — stacking two previously-
closed single-axis gates (session-hour + relative-volume) together; Run 31
confirmed Binance futures data (fapi.binance.com, needed for a funding-rate
signal — the only other concretely-scoped new-signal candidate) is
geo-restricted from this environment, closing that avenue definitively, then
opened and closed a genuinely new axis — historical **era**, not just TF/
param/gate — re-running the 3 original shipped-default strategies @1h on a
fully disjoint 2023 window (every prior run used only the recent ~240-day
2025-2026 span); with every concretely-scoped axis now exhausted, Run 32
switched to the self-correction protocol Run 31 recommended, re-validating
the shipped DCA dip-buy default against today's rolling-forward windows and
reproducing the same small, regime-dependent effect on record since Run 4;
Run 33 added a 7th strategy family (BB-width volatility-squeeze breakout —
compression-then-expansion, mechanically distinct from every prior family)
and closed it, the first case of both TEST and a 3rd non-overlapping window
clearing the numeric bar together while TRAIN decisively failed, resolved as
noise via per-symbol breakdown; Run 34 added an 8th strategy family
(Price-vs-RSI Bullish Divergence — the first oscillator-divergence
construction, comparing two series' shapes at confirmed swing lows rather
than reading one series in isolation) and closed it decisively, 0/8 configs
clearing both OOS bars, closing all 8 strategy families and 5 signal-source
categories concretely scoped in this programme; Run 35 isolated DCA's
`dip_threshold_pct` on its own (previously only tested bundled with a
multiplier change), the mirror case of Run 27's multiplier isolation,
reproducing the same small anti-correlated-across-regimes effect and
doubling as a self-correction re-check of the shipped default — still no
adopted change to shipped risk defaults.

---

## DISTILLED LEARNINGS (read this first; refreshed every run)

**No robust, generalizing edge has been found yet in the candle-strategy
families, across 35 sessions and ~333 configs — now confirmed across two
materially different historical eras (2025-2026 and, as of Run 31, a
disjoint 2023 window), not just one regime.** trend_momentum,
mean_reversion, and grid are now each **fully closed across the entire
5m/15m/1h/4h TF sweep** — every combo tested is either net-negative or only
clears the OOS bar by luck/small-sample noise. Donchian breakout, Supertrend,
Capitulation Wick Reversal, BB-width squeeze breakout, and Price-vs-RSI
Bullish Divergence (5 mechanically distinct trend/breakout/pattern/
volatility-regime/oscillator-divergence families) are also closed.
Honest baseline: simple RSI/BB/EMA/grid/ATR-band/candlestick-shape/
volatility-compression/divergence signals on these 8 majors appear
over-arbitraged; fees turn near-breakeven setups negative. The one
asymmetric, mechanically-explicable (not curve-fit) positive finding so far
is DCA's dip-buy feature — already shipped as the default, not a new
change. **Full evidence for every closed TF/param combo lives in
`research/decisions.jsonl` and archived run sections below/in
`research/archive/`; this section states only the conclusions and why, not
the blow-by-blow.**

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

- **Supertrend (Run 24, 5th strategy family, first ATR-adaptive-band
  construction)**: ATR-scaled trailing bands with a stateful ratchet (band
  only ever tightens toward price within a trend — mechanically distinct
  from EMA-cross's two independent lagging lines and from Donchian's fixed
  N-period channel, which doesn't adapt to volatility at all). BUY on
  flip-to-uptrend, SELL on flip-to-downtrend, long-only, unchanged exchange
  SL/TP. Swept atr_period {10,14} x multiplier {2.0,3.0} @ 1h/4h = 8
  configs. **Decisive reject, no 3rd-window check warranted**: best test PF
  across all 8 is 0.769 (4h, atr=14, mult=3.0 — but train PF only 0.325,
  no support either side). The tightest-band 1h configs (mult=2.0) reach
  the closest-to-1.0 train PF of the sweep (1.02–1.03) but test PF
  collapses to 0.67–0.68 on those same rows — train near-breakeven that
  doesn't generalize, the same shape as every other closed family. Win
  rates are low throughout (15–34%), the signature of a trend-following
  flip signal getting whipsawed between real trend legs — the same failure
  mode Donchian breakout (Run 18) showed, now confirmed via a second,
  mechanically different (ATR-band-flip vs fixed-channel) trend-following
  construction. **Closed — do not re-tune atr_period/multiplier on this
  construction.** Together with Donchian, this now rules out both a fixed-
  lookback and a volatility-adaptive trend-following breakout on this
  8-symbol universe at 1h/4h.

- **Capitulation Wick Reversal (Run 27, 6th strategy family, first
  candlestick-SHAPE-derived signal)**: BUY on a single candle with a long
  lower wick (>= wick_ratio of its own high-low range), a bullish (green)
  close, and volume >= vol_mult x its own 20-period rolling mean — sold off
  hard intra-candle, bought back before close, on real participation.
  Mechanically distinct from every other closed family/gate: the first
  signal here that reads one candle's own OHLC shape rather than a
  multi-bar indicator series, a band/threshold touch, or a fixed channel.
  Exit on reversion to SMA(10) of close, unchanged exchange SL/TP. Swept
  wick_ratio {0.5,0.6,0.7} x vol_mult {1.5,2.0} @ 1h/4h = 12 configs.
  **Decisive reject, 12/12, no 3rd-window check warranted**: train PF never
  exceeds 0.668 anywhere in the sweep. 3 of 6 1h configs (all vol_mult=2.0)
  clear test PF>1.1 (1.098–1.482) but every one pairs with train PF 0.47–
  0.66 — the identical test-clears/train-doesn't regime-luck shape seen in
  mean_reversion since before Run 16, now reproduced by an unrelated
  candlestick-shape construction. 4h is a clean reject at every config
  (train PF 0.089–0.336, test PF 0.038–0.861) — tighter wick_ratio at 4h
  makes both sides worse, not better, while collapsing the sample to n=4–14,
  the opposite of what filtering toward "purer" capitulation candles should
  do if the pattern had real signal. **Closed — do not re-tune
  wick_ratio/vol_mult/exit_period.** With this, all four broad signal-source
  categories tried in this programme (price level/band, price shape,
  volume/cross-symbol) are now exhausted for the 8-symbol/1h-4h scope; a 7th
  family would need a genuinely different signal source entirely.

- **BB-width volatility-squeeze breakout (Run 33, 7th strategy family, first
  volatility-CONTRACTION-as-precondition construction)**: BB width
  ((upper-lower)/middle) tracked in its own rolling percentile; require a
  "squeeze" (width in its own bottom squeeze_pct%) within the last 3 candles
  before taking a close-above-upper-band breakout — mechanically distinct
  from Donchian's fixed-channel breakout (no volatility precondition at all)
  and from Supertrend's ATR-band flip (adapts band width to volatility but
  never requires *contraction* specifically). Exit on close back below the
  middle band. Swept squeeze_pct {10,20,30} x require_squeeze {True,False} @
  1h/4h = 12 configs. **1h: decisive reject, no 3rd-window check warranted**
  (train PF 0.47-0.69, test PF 0.65-0.99, nothing near the bar). **4h:
  produced this programme's first case of TEST and a 3rd non-overlapping
  OLDER window BOTH clearing the numeric bar together** (squeeze_pct=20:
  test PF 1.144/n=40, OLDER PF 1.442/n=63; squeeze_pct=30: test PF 1.376/
  n=48, OLDER PF 1.246/n=68) **while TRAIN — chronologically BETWEEN
  the two passing windows — decisively failed** (PF 0.32-0.50, 7-8 of 8
  symbols losing, several 0.0-PF all-losing symbol samples: a real,
  broad-based failure, not noise itself). Resolved as **noise, not
  adopted**, by per-symbol breakdown: each symbol contributes only 3-18
  trades per window in TEST/OLDER, with roughly half the symbols losing and
  a handful of high-PF winners (SOL, XRP, DOGE) driving the aggregate in
  both windows — the same single-symbol/small-per-symbol-sample pattern
  disqualifying since Run 16/19, just spread across 2 lucky windows instead
  of 1. The require_squeeze=False control (plain BB upper-band breakout, no
  squeeze precondition — isolates the squeeze's marginal value) fails the
  OLDER check outright (1.078, just under 1.1), showing the squeeze
  precondition adds nothing measurable either way. Same underlying read as
  Donchian/Supertrend: a trend-following breakout construction that does
  well when a window happens to contain real trend legs and gets whipsawed
  when it doesn't — which window is favorable is regime luck, not a
  property of the squeeze mechanism. **Closed — do not re-tune
  squeeze_pct/squeeze_lookback/squeeze_recency/bb_std on this construction.**
  With this, 4 mechanically distinct trend/breakout constructions (EMA-cross,
  Donchian, Supertrend, BB-squeeze) have now all failed the same way at
  1h/4h on these 8 majors.

- **Price-vs-RSI Bullish Divergence (Run 34, 8th strategy family, first
  oscillator-DIVERGENCE construction)**: compares two series' shapes at
  confirmed swing points — price makes a lower low while RSI makes a higher
  low at the matching pivot (momentum exhaustion) — rather than reading any
  one series against a fixed threshold/band/channel, mechanically distinct
  from every prior family including the RSI-threshold use inside
  mean_reversion. Swing lows confirmed only once `pivot_lookback` bars exist
  on both sides (no lookahead — confirmation lands at pivot_index +
  pivot_lookback). BUY on divergence confirmation, SELL on RSI recovering
  above exit_rsi, unchanged exchange SL/TP. Swept pivot_lookback {3,5} x
  exit_rsi {55,60} @ 1h/4h = 8 configs. **Decisive reject, 8/8, no
  3rd-window check warranted (0 configs cleared both OOS bars).** 1h: train
  PF never exceeds 0.644 across all 4 configs, test PF tops out at 1.011 —
  fails on PF alone with an adequate sample both sides (test n 52-78). 4h:
  train PF reaches 1.6-1.8 at pivot_lookback=5, but n=11 train / n=15 test —
  both sides under the 30-trade floor; confirmed bullish-divergence swings
  are simply too rare at 4h on 150d/60d windows to evaluate, not evidence of
  edge. **Closed — do not re-tune pivot_lookback/max_divergence_bars/
  oversold_max/exit_rsi on this construction.** With this, the "read one
  series against itself" and "compare two series' shapes" approaches have
  both now been tried and both show the same over-arbitraged baseline on
  these 8 majors — divergence does not sidestep the pattern any more than
  the 7 single-series families did.

- **DCA dip_multiplier magnitude (Run 27) and dip_threshold_pct (Run 35) —
  both dip-buy parameters now independently isolated and closed.**
  Run 27: dip_multiplier in {1.5 (shipped), 1.75, 2.0, 2.5} at the shipped
  dip_threshold_pct=5.0, isolated from the threshold change Run 4 bundled
  it with and the buy-count cap Run 14 tested separately. Effect is real
  but trivial (<0.35pp even at 2.5x) and flips sign with the regime:
  +0.06 to +0.35pp in both declining windows tested (7/8 symbols benefit —
  a bigger multiplier lowers cost basis further when dips are frequent) but
  −0.03 to −0.11pp in a strongly-rising window (only 1/8 symbols benefit —
  more capital deployed at a locally-worse price when dips are rare and the
  flat schedule already wins big on its own). Run 35: dip_threshold_pct in
  {3.0, 4.0, 5.0 (shipped), 7.0, 10.0} at the shipped dip_multiplier=1.5,
  the mirror isolation (Run 4 only ever changed threshold bundled with a
  multiplier change) — same monotonic, mechanically explicable, sign-
  flipping pattern: a looser (lower) threshold fires more dip-buys, which
  helps more in both declining windows (up to +0.40pp at 3.0, 7-8/8 symbols
  benefit) but hurts more in the strongly-rising window (down to -0.10pp at
  3.0, only 1/8 symbols benefit); a tight threshold (7.0/10.0) nearly
  disables the feature (2-32 dip-buys fire across 150d vs 28-99 at 5.0),
  muting both the benefit and the cost toward zero. Shipped 5.0 sits at a
  reasonable middle point on this tradeoff, not an extreme. Same anti-
  correlated-across-regimes signature as every non-signal lever since Run
  21/22, now confirmed for both DCA dip-buy parameters independently.
  **Keep shipped dip_threshold_pct=5.0 / dip_multiplier=1.5x — closed, no
  DCA dip-buy parameter axis remains flagged.**

- **UTC session-hour BUY gate (Run 28, 5th signal-source category)**: veto
  BUY unless the candle's own UTC open_time falls inside a configured
  session window — the first signal in this programme derived purely from
  calendar time, not from OHLCV at all (distinct from price-level/band,
  moving-average, price-shape, and cross-symbol/volume, the 4 categories
  Run 27 closed out). Applied as a thin decide()-wrapping veto (same pattern
  as the ADX/volume/MTF gates) to trend_momentum@1h and mean_reversion@1h,
  swept 4 windows {Asia 00-08 UTC, EU 07-15 UTC, US 13-21 UTC, EU/US overlap
  13-16 UTC} + baseline (off) x 2 bases = 10 configs. **Decisive reject,
  same "looks good until the 3rd window" shape documented since Run 16**:
  on trend_momentum@1h every gated window is flat-to-worse (best: US session
  train PF 0.889/test PF 0.804, still <1.1) or a small-sample fluke (EU/US
  overlap test PF 1.221 on n=9, an order of magnitude under the 30-trade
  floor). On mean_reversion@1h, 2 of 4 windows (EU 07-15, US 13-21) appeared
  to clear the OOS screen — EU session even paired it with train PF 1.088,
  the **highest train-side PF ever recorded for mean_reversion@1h in this
  programme** — but both failed the 3rd non-overlapping OLDER window
  decisively (PF 0.157/n=75 and PF 0.313/n=113, both real samples), with
  every one of 8 symbols losing in that window (a market-wide decline, not a
  per-symbol session mechanism). **Closed — do not re-tune session
  boundaries on this mechanism.** With this, the calendar/session-time axis
  is exhausted the same way the 4 OHLCV-derived categories already were: a
  new lever applied to a signal with no train-side edge just inherits
  whichever regime the test window happens to be, it doesn't create edge.
  The mean_reversion EU-session near-miss is notable only as the closest a
  train-side signal has ever come for this base — still not real.

- **Day-of-week BUY gate (Run 29, coarser granularity within the same
  calendar/session-time category Run 28 opened)**: veto BUY unless the
  candle's own UTC day-of-week is in an allowed set — weekdays Mon-Fri,
  weekend Sat-Sun, early-week Mon-Wed, late-week Thu-Sun — swept on
  trend_momentum@1h and mean_reversion@1h (+ baseline) = 10 configs, same
  thin decide()-wrapping veto pattern as every prior gate, same standard
  windows. **Decisive reject, 10/10, the same "looks good until the 3rd
  window" shape one more time.** trend_momentum: 4/4 gated configs fail
  outright or on undersized test samples (weekend Sat-Sun test n=30 exactly
  at the floor and still PF 0.568; late-week Thu-Sun reaches the highest
  train PF trend_momentum@1h has ever shown at this TF, 0.912, but test PF
  collapses to 0.46 — train-improves/test-doesn't, the Run 15-style overfit
  shape). mean_reversion produced this programme's **strongest-looking
  double-clear yet**: late-week Thu-Sun cleared both sides on first look
  (train PF 1.4/n=97, test PF 1.857/n=41, both comfortably over the bar with
  adequate samples) — stronger on paper than Run 28's EU-session near-miss.
  It still failed the 3rd non-overlapping OLDER window decisively (PF
  0.255/n=104, every one of 8 symbols losing in that market-wide decline).
  Two more mean_reversion configs (weekdays Mon-Fri, early-week Mon-Wed)
  test-cleared/train-didn't and also failed their OLDER checks (PF 0.351 and
  0.947). A fifth mean_reversion cell (weekend Sat-Sun) set a new
  programme-wide record train PF of 4.18 (n=48, 83% win rate) but test n=17
  is under the 30-trade floor — disqualified by sample size before any
  cross-check was warranted. **Closed — do not re-tune weekday boundaries on
  this mechanism.** Now even a genuine double-clear (train AND test both
  comfortably over 1.1 with adequate samples, not just a near-miss) has
  failed the 3rd-window check as decisively as every prior near-miss — the
  strongest evidence yet that this programme's train/test window pair can
  independently share a regime while a 3rd window doesn't, regardless of how
  convincing the train+test agreement looks, for any construction tried so
  far. The calendar/session-time category is now closed at both
  granularities tried (hour-of-day, day-of-week); a materially different
  calendar hypothesis (e.g. proximity to a known macro/crypto calendar
  event) would be a new category, not a re-run of this one, and is likely
  out of reach of `data-api.binance.vision`'s kline-only public data anyway.

- **Cross-symbol relative-strength / rotation (Run 19, first non-price-
  derived-per-symbol data axis)**: rank the 8 symbols cross-sectionally by
  lookback-period return each candle, BUY while a symbol is in the top-K,
  SELL once its rank falls below an exit threshold (with/without
  hysteresis), optionally requiring the leader's own momentum be positive.
  Mechanically distinct from all 4 closed strategy families and all 3
  closed gate mechanisms — the first signal here that depends on *other*
  symbols' behavior, not just a symbol's own price/volume history. Swept
  @ 4h, 3 lookbacks {20,50,90} x 4 (top_k,exit_k) pairs x 2
  momentum-filter settings = 24 configs. **Closed, same "near-miss ->
  noise" pattern as every prior confirmation-gate near-miss**: 23/24
  configs decisively fail the screen outright (test PF 0.72-1.09, several
  train PF <0.6); the one survivor (lookback=20, top_k=3, exit_k=5, no
  momentum filter: test PF 1.231/87 trades) failed BOTH required
  cross-checks — the 3rd non-overlapping window (older-window PF 0.75/65
  real trades) and the per-symbol breakdown, which showed the test
  window's 87 trades concentrated in only 3 of 8 symbols with ADA alone
  contributing 44 trades (PF 1.507, +45.6% return) driving the entire
  aggregate, while the train window's leaders were completely different
  symbols (BTC, DOGE) — a single-symbol rally getting picked up by the
  rotation rank, not a repeatable cross-sectional edge. Train PF for the
  survivor was only 1.039 (no real train-side support either). **Closed
  — do not re-tune lookback/top_k/exit_k on this mechanism absent a new
  hypothesis for why the rotation would have edge on only 8 symbols**
  (institutional-scale relative-strength rotation strategies typically
  need a much larger cross-section — 50-500+ assets — to average out
  single-name idiosyncratic noise the way ranking only 8 majors cannot).

- **Pairs mean reversion (Run 20, mirror-image of the rotation construction)**:
  the flagged Run 19 follow-up — instead of ranking 8 symbols by momentum
  (rs_rotation, buy the leader), bet on relative-value convergence within a
  single pair (buy the laggard). For each of 7 alt/BTC pairs, compute the
  rolling z-score of the log price ratio and BUY whichever leg has lagged
  its partner by > entry_z std devs, exit once the gap closes below
  exit_z=0.3. Swept @ 1h: 7 pairs x lookback {20,50,100} x entry_z {1.5,2.0}
  = 42 configs. **Decisive reject, same "near-miss -> noise" shape as every
  prior confirmation-gate/rotation near-miss, now the cleanest version of it
  yet**: 31/42 configs fail the OOS screen outright; the other 11 clear it
  (test PF 1.10-1.98, n 30-45) but **every single one of the 11 has train PF
  < 1** (worst: 0.162, best: 0.991 — zero train-side support anywhere in the
  42-config sweep bar one n=8 fluke), a clean structural tell that the test
  window (60-0d ago) was a broadly favorable regime for "buy the BTC-pair
  laggard," not a per-pair edge. Checked all 11 against the OLDER
  non-overlapping window (240-150d ago): **10/11 fail decisively (PF
  0.44-0.86)**; the 1 survivor (ETH/BTC lb=50/entry=2.0, OLDER PF 1.25/34
  trades) fails the per-symbol check instead — BTC leg PF 1.731/+19.5%
  driving the aggregate while the ETH leg itself is negative (PF 0.707,
  -6.9%), i.e. buying BTC-the-anchor on relative dips carried the result,
  not a genuine pair-relative signal. **Closed — 0/11 near-misses survive
  either required check, the most decisive rejection of a near-miss cohort
  in this programme's history.** Mechanism-level read: this engine is
  spot/long-only (confirmed no shorting anywhere in
  app/core/types.py|app/backtest/simulator.py|app/risk/models.py), so
  "pairs trading" here can only ever be a directional proxy bet on one leg
  catching up — real basis risk, not a market-neutral spread trade — and
  the data shows that proxy has no edge distinct from the single-symbol
  price behavior (mostly BTC's own dip-buying tendency, already captured
  and adopted separately as the DCA dip-buy feature) it's built from.
  **Do not re-tune pair/lookback/entry_z/exit_z on this construction** —
  a genuine market-neutral pairs trade would need short-selling capability
  this engine doesn't have, which is out of scope (no risk-control
  loosening, and adding shorting is a much larger architecture change, not
  a param tune).

- **Volatility-regime POSITION SIZING (Run 21, first non-signal lever ever
  tested)**: every prior mechanism in this programme — all 4 strategy
  families, all 3 confirmation gates, both cross-symbol constructions —
  changes *which trades are taken*. Run 21 changes *how big they are*,
  leaving the entry/exit signal byte-for-byte untouched: bucket ATR(14)/close
  into tertiles by its own trailing-100-candle percentile (no lookahead) and
  scale the position notional by a per-tertile multiplier. Because PF is
  gross-win/gross-loss in dollars, this moves account-level PF even when the
  trade list and win-rate are *identical* — a lever no gate could pull.
  Tested 5 sizing variants (control 1/1/1; high_boost 0.5/1/1.5; low_boost
  1.5/1/0.5; and 2.0/0.25 "strong" versions of each) x 3 previously-closed
  base signals (trend_momentum@1h, trend_momentum@4h, mean_reversion@1h) =
  15 configs. **Decisive reject, with the cleanest structural tell this
  programme has produced.** The control was verified trade-for-trade
  identical to production `run_candle_backtest`, so the sized simulator adds
  no drift. Two findings:
  (1) **Train and test PF move in exactly OPPOSITE directions, in all 3 base
  signals, in both sizing directions — 6/6 mirrored pairs.** e.g.
  trend_momentum@4h high_boost_strong: train PF 0.644->0.312 (halved) while
  test PF 0.974->1.610 (up 65%); mean_reversion@1h low_boost_strong: train
  0.573->0.454 (worse) while test 2.174->4.066 (nearly doubled). If a
  vol-regime/trade-quality relationship were a persistent property of these
  instruments it would point the same way in both windows. It never does.
  (2) **The favorable direction is opposite for the two strategy types
  within the same test window** (trend_momentum likes high-vol sizing,
  mean_reversion likes low-vol sizing) — mechanically seductive (trends need
  movement, mean-reversion needs calm ranges) but the train window reverses
  *both*, which is what rules the story out.
  Nothing cleared the bar on its own merit: trend_momentum@1h stays at test
  PF 0.38-0.64 at every setting; @4h reaches test PF 1.61 but on n=28 (below
  the 30-trade floor) with catastrophic train degradation; the 4 configs that
  did clear the screen are all mean_reversion@1h, whose *own mult=1 control*
  already scores test PF 2.174 — i.e. they inherited the long-known
  mean_reversion@1h regime luck, not any sizing benefit — and all 4 fail the
  3rd non-overlapping window decisively (PF 0.39-0.50, n 109-121, real
  samples), with 2 of 8 symbols (ETH, ADA) contributing zero test trades.
  **Closed — do not re-tune tertile multipliers, ATR period, or percentile
  lookback.** The important generalization: **sizing cannot manufacture edge
  it can only amplify or attenuate what the signal already has**, and with
  every signal here at PF<1, amplifying by regime is just a leveraged bet on
  which regime the next window happens to be in. This closes the
  position-sizing axis flagged as Run 20's next step (b).

- **EXIT-mechanism axis (Run 22, first-ever test of a lever that is neither
  entry signal nor position size)**: two sub-experiments on trend_momentum@1h
  and mean_reversion@1h at shipped-default entry params, SL/TP/daily-loss/
  drawdown controls untouched or only tightened (never loosened). **(A) Time-
  based forced exit**: force-close any position still open after N candles,
  checked *after* SL/TP each bar (SL/TP still get first crack, so this only
  bounds worst-case holding time, it does not loosen anything). N chosen from
  each base's own no-cap train holding-duration distribution, not blind
  guessing: trend_momentum {8,16,33,52} bars (~P25/median/P75/P90 of a 24.7h-
  mean/113h-max distribution), mean_reversion {6,11,17,24} bars (~P25/median/
  P75/just-above-P90 of an 11.1h-mean/39h-max distribution). **(B) Tighter
  SL/TP** (never wider, per the hard limit): {1.5/3.0, 1.0/2.0, 1.5/4.0} vs
  shipped 2.0/4.0, run through *unmodified production* `run_candle_backtest`
  directly (RiskConfig is already parameterized — no new simulator code
  needed for this half). The new capped-exit simulator copy
  (`run_candle_backtest_capped`) was verified trade-for-trade identical to
  production at max_hold_bars=None before any deltas were trusted. **Decisive
  reject on trend_momentum, 8/8 configs**: test pf 0.379–0.686 at every N and
  every SL/TP tried, train pf never exceeds 0.65 — neither capping holding
  time nor tightening stops helps or reveals any train-side edge. **mean_
  reversion, 8/8 configs reproduce Run 21's regime-luck signature exactly, on
  two entirely different levers**: every variant clears the OOS screen (test
  pf 1.447–2.174, inherited from the base's own untouched control at test pf
  2.174) but train pf never exceeds 0.573 anywhere in the 8-config sweep, and
  every single variant fails the 3rd non-overlapping window decisively
  (older-window pf 0.387–0.510, real 63–113-trade samples), with 2–3 of 8
  symbols contributing zero trades in every per-symbol breakdown. **Closed —
  do not re-tune max_hold_bars or SL/TP magnitude on these two bases.** The
  sharpest reading yet: unlike Run 21's sizing experiment (train/test PF moved
  in *opposite* directions — an anti-correlated tell), here train pf simply
  never crosses 1 anywhere, in either sub-experiment, for either base — the
  exit mechanism has nothing to reveal in a signal with no underlying edge.
  Confirms Run 21's generalization from a new angle: it isn't specific to
  sizing — no additional mechanism layered on a PF<1 entry signal can
  manufacture edge, whether it changes size, exit timing, or exit price.
  **Closes the exit-mechanism axis** (self-correction check: no strategy/risk
  code has changed since Run 21, nothing to revalidate or revert).

- **Fee/cost-level sensitivity (Run 23, first test of a scope assumption
  rather than a new construction)**: DISTILLED LEARNINGS had asserted "fees
  turn near-breakeven setups negative" without ever quantifying it. Swept
  `SimConfig.fee_bps`/`slippage_bps` down from the shipped 7.5/4.0 through a
  realistic BNB-discount tier (4.0/2.0), a near-zero tier (1.0/0.5), to a
  theoretical zero (0/0) — no strategy code or param changes, shipped-default
  entry params throughout, unmodified production `run_candle_backtest`.
  Tested trend_momentum@15m and @1h (its two best-performing TFs) plus
  mean_reversion@1h (contrast: a base whose train PF has never once exceeded
  ~0.6 under any prior lever) x 4 cost tiers = 12 configs. **Decisive: 0/12
  configs clear train PF>1.1 AND test PF>1.1 with n>=30 at ANY cost tier,
  including theoretical zero — directly refutes the "fees are the
  bottleneck" hypothesis.** Three distinct patterns, each informative:
  (1) **trend_momentum@1h** — train and test PF move the *same* direction as
  cost drops (train 0.586->0.792, test 0.484->0.755), i.e. real, measurable
  cost drag exists — but even at zero cost neither crosses 1.0. There is
  real edge-adjacent behavior here, just not enough of it.
  (2) **trend_momentum@15m** — a new failure signature not seen in 22 prior
  runs: TRAIN pf clears 1.1 at *every* tier (1.226 shipped -> 1.516 at zero
  cost, n=125-142) but TEST pf stays decisively stuck at 0.67-0.78 and
  moves the *wrong* direction as cost drops (down, not up) — a clean
  overfit-to-train-window signature, the mirror image of mean_reversion's
  "test looks good, train doesn't" regime luck. Removing all cost cannot
  rescue a signal that was never real out-of-sample to begin with.
  (3) **mean_reversion@1h** — reproduces the long-documented regime-luck
  pattern on a *third* orthogonal lever (after sizing in Run 21 and exit
  mechanism in Run 22): test pf clears the screen at every tier and rises
  further as cost drops (2.174->2.838), but train pf never crosses 1.0
  anywhere (0.573->0.774) — cost reduction amplifies the inherited luck, it
  doesn't create train-side support. **Closes the fee-level scope-assumption
  question — do not re-sweep cost tiers; the null here is not fee-driven,
  it is an absence of underlying edge (trend_momentum) or a window-specific
  artifact (mean_reversion), and lower fees change neither.**

**1d timeframe, all three families (Run 26) — closed, confirms the
prediction with measured numbers instead of leaving it assumed.**
trend_momentum@1d and mean_reversion@1d are both starved on trade count
before PF can even be judged (train/test n=8/4 and n=9/0 respectively —
mean_reversion literally produced zero out-of-sample trades in the 60-day
test window). grid@1d is NOT starved (205/112 trades — it fires on price
levels, not indicator events) but has no economically meaningful
account-level return either way (+0.571%/+0.3206% train/test on $10k,
~flat) — a different failure mode than grid's "bag-holds through trend"
rejection at every faster TF. **Closes the TF-range scope question for all
3 original families — do not re-test 1d; combined with 1m's earlier close
(Run 6/7), the full originally-in-scope TF range is now exhausted.**

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
- **DCA dip_multiplier magnitude** (Run 27): {1.5 shipped, 1.75, 2.0, 2.5} at
  the shipped 5% threshold — closed as noise (see bullet above in the
  signal-axis list). Effect real but trivial (<0.35pp) and regime-dependent
  (helps in declines, hurts in a strong uptrend). Keep shipped 1.5x.

**Live real money (pre-research):** 16 trades, −$0.29 net, ~70% of loss was
fees — empirically confirmed the negative-edge finding from backtests.
Stopped; testnet + this automated research only from here on.

**Where this research programme stands (as of Run 31):** the search has now
been exhausted along *six orthogonal axes* — three levers plus three scope
assumptions — and the **signal** axis spans six mechanically distinct
strategy families across five broad signal-source categories (price-level/
band, moving-average relationship, price *shape*, cross-symbol/volume, and
now calendar/session-time, itself now tested at both hour-of-day and
day-of-week granularity).
All three original candle-strategy families are closed across the full TF
sweep; Donchian breakout (fixed-lookback channel), Supertrend (ATR-adaptive
trailing band, Run 24), and Capitulation Wick Reversal (candlestick shape +
volume, Run 27) are all decisively rejected; all three confirmation-gate
mechanisms (ADX, relative volume, MTF direction) failed identically; and both
cross-symbol constructions (momentum rotation, pairs convergence) closed the
same way. On the **position-sizing** axis (Run 21): scaling size by
volatility regime cannot rescue any of them, with train/test PF moving in
opposite directions in 6/6 tested pairs. On the **exit-mechanism** axis
(Run 22): neither a time-based forced exit nor tighter SL/TP rescues either
base signal. On the **fee/cost-level** axis (Run 23): 0/12 configs cleared
both train and test PF>1.1 at ANY cost tier including a theoretical zero,
directly refuting the "fees are eating a near-breakeven edge" narrative. **Run
25 opened and closed a second scope assumption: the 8-symbol majors universe
itself** — re-ran trend_momentum@1h/4h and mean_reversion@1h on a disjoint
8-symbol universe, 0/3 configs cleared both sides of the OOS bar, ruling out
"wrong coins" as an explanation. **Run 26 closed the third scope assumption,
the TF range**: 1d starves trend_momentum/mean_reversion on trade count
before PF can even be judged, and grid@1d has no economically meaningful
account-level return; combined with 1m's earlier catastrophic close, the
entire originally-in-scope TF range (1m-1d) is exhausted. **Run 27 closed
the last two open items**: the 6th strategy family (wick reversal, decisive
12/12 reject, train PF never exceeds 0.668) and the last flagged DCA
variant (dip_multiplier magnitude — real but trivial and regime-dependent
effect, keep shipped 1.5x). **Run 28 opened and closed a 5th signal-source
category, calendar/session-time**: a UTC session-hour BUY gate on
trend_momentum@1h and mean_reversion@1h, 10 configs — decisive reject, same
"looks good until the 3rd window" shape as every prior near-miss (2
mean_reversion session windows appeared to double-clear train+test, one
even setting a new high-water mark for mean_reversion@1h train PF at 1.088,
but both failed the OLDER non-overlapping window decisively with every
symbol losing). **Run 29 closed the day-of-week granularity within the same
calendar/session-time category**: 10 configs (weekdays/weekend/early-week/
late-week x 2 bases + baseline) — decisive reject, 10/10, and this run
produced the programme's **strongest-looking double-clear yet**
(mean_reversion@1h late-week Thu-Sun: train PF 1.4/n=97, test PF 1.857/n=41,
both comfortably over the bar on adequate samples) which still failed the
3rd-window check as decisively as every prior near-miss (OLDER PF 0.255,
every symbol losing) — the strongest evidence to date that a convincing
train+test agreement in this methodology can still be two overlapping
favorable regimes rather than real edge. **The only scope assumption left
untested is long-only** (shorting is a larger architecture change, out of
scope per the hard limits — cannot be tested without expanding scope beyond
params/code tuning, not a param tune). Futures/funding-rate data (the one
concretely-scoped new-signal-source candidate) is confirmed geo-restricted
from this environment (Run 31) — not just untested but unreachable. **The
honest recommendation remains that 31 runs and ~308 configs spanning
per-symbol signals (6 strategy families across 5 signal-source categories,
the calendar one now at 2 granularities) across the full viable TF range on
two disjoint 8-symbol universes and now two disjoint historical eras (Run
31), cross-symbol signals, confirmation gates, position sizing, exit
mechanisms, trading-cost level, DCA parameter magnitude, calendar/
session-time gating, and now a stacked combination of two closed gates,
with zero surviving candidates, is itself the finding.**

- **Session-hour + relative-volume combo gate (Run 30, tests the one
  remaining flagged combination)**: stacks Run 28's UTC session-hour BUY
  veto and Run 15's relative-volume BUY veto as two independent conditions
  (both must pass) on the same trend_momentum@1h/mean_reversion@1h bases,
  using each base's own best single-gate session window (trend_momentum:
  US 13-21 UTC; mean_reversion: EU 07-15 UTC, Run 28's highest-ever
  train-PF window for this base) x 2 volume thresholds {1.2, 1.5} = 6
  configs per base. **Decisive reject, 12/12 — confirms the prediction
  flagged at the end of Run 29 rather than overturning it.** On
  trend_momentum@1h, stacking the two vetoes only shrinks the sample
  (n=26/17 and n=16/15 vs 53/44 and 39/29 for the single-axis gates,
  both combos far under the 30-trade floor) without any PF improvement —
  the combo's test PF (0.711, 0.753) is worse than either single-axis
  gate on its own. On mean_reversion@1h, both combo configs produced this
  programme's **strongest-looking double-clears yet on paper**
  (EU+vol=1.2: train PF 1.177/n=67, test PF 3.403/n=33; EU+vol=1.2's train
  PF is the highest ever recorded for this base+construction) — but the
  standard 3rd-window check (2025-12-30..2026-03-30) shows both **fail
  more decisively than either single-axis component alone**: combo OLDER
  PF 0.117 and 0.088, both *worse* than the EU-session-alone OLDER PF
  (0.157) or the volume-alone OLDER PF (0.365-0.374). Per-symbol
  breakdowns in the OLDER window show 6 of 8 symbols at PF 0.0-0.28 in
  every combo cell, the same market-wide-decline signature documented
  since Run 16. **The mechanism-level generalization: stacking two gates
  that each individually inherit regime luck compounds the luck rather
  than filtering toward real edge** — a double-veto only survives the
  train+test pair if both vetoes happen to agree on which trades belong to
  the favorable regime, which is exactly what a 3rd non-overlapping window
  cannot confirm. **Closed — do not test further combinations of any two
  gates already individually closed in this programme**; a materially new
  single signal source (not a re-combination of existing ones) is needed
  to reopen this line. No item remains flagged as open. A 6th signal-source
  category would need a data source this codebase doesn't currently fetch
  (e.g. order-book/funding-rate data, likely out of reach via
  `data-api.binance.vision`'s public kline endpoints — check what's
  fetchable before committing to a design) — this is now the only
  concretely-scoped candidate remaining; absent that, the honest read is
  that this programme has exhausted what OHLCV-only signals on 8 major
  spot pairs can support.
  Nothing here is deploy-worthy; the shipped DCA dip-buy remains the only
  positive result and needs no change.

- **Futures/funding-rate data feasibility check + historical-ERA axis (Run
  31)**: Run 30 left exactly one concretely-scoped candidate open — a 6th
  signal-source category would need order-book/funding-rate data, "likely
  out of reach via `data-api.binance.vision`'s public kline endpoints —
  check what's fetchable before committing to a design." This run checked:
  `fapi.binance.com` (Binance's futures host, which serves funding-rate
  history publicly with no API key) returns `"Service unavailable from a
  restricted location"` from this execution environment for every futures
  endpoint tried (`fundingRate`, `premiumIndex`); `data-api.binance.vision`
  (the spot host this programme already uses) has no `/fapi` path at all
  (404). **Confirmed infeasible, not a code issue — closes the 6th-category
  question definitively; do not re-attempt fetching futures/funding data
  from this environment.**
  With no new signal source testable, this run opened a genuinely different
  axis instead of re-tuning a closed one: **historical era**. Every one of
  the prior 30 runs' train/test/OLDER windows was drawn from the same
  recent ~240-day span (roughly Dec 2025 - Aug 2026) — the "no edge" verdict
  has never been checked against a *different macro regime*. Re-ran the 3
  original shipped-default strategies (trend_momentum, mean_reversion, grid)
  @1h, unmodified production `run_candle_backtest`, on a fully disjoint 2023
  window (train 2023-02-01..2023-07-01 150d, test 2023-07-01..2023-08-30
  60d — post-2022-crash recovery/chop, a materially different volatility/
  trend character than 2025-2026) = 3 configs. **Decisive reject, 3/3, no
  near-misses so no 3rd-window check was warranted**: trend_momentum train
  pf 0.879/test pf 0.756 (n=144/80); mean_reversion train pf 0.771/test pf
  0.703 (n=222/119); grid train pf 0.738/test pf 0.986 (n=365/204, the
  closest-to-bar result but still a decisive real-sample fail, not a
  small-sample near-miss). Two things stand out: (1) **grid's 82-86% win
  rate reproduces the exact "many small in-range wins, funded by a few huge
  directional losses" accounting signature** documented since Run 8/13, with
  BTC alone losing -111.8% notional-adjusted while several small-caps show
  `inf` pf on win-only samples — the same failure mode, just different
  symbols playing each role than in 2025-2026, confirming grid's
  "directional bet in disguise" finding is regime-independent, not an
  artifact of which coins happened to trend in the tested window. (2)
  **mean_reversion@1h failed on *both* sides together for the first time
  ever in this programme** (every prior 2025-2026 result showed the
  regime-luck signature: test clears, train doesn't) — in 2023 neither side
  clears, a structurally different failure shape but the same "no real
  edge" conclusion. **Closed — do not re-test the 2023 window on these 3
  families.** The generalization: the 30-run null is not an artifact of the
  one recent market regime every prior run happened to sample from — it
  reproduces cleanly in a materially different historical era too, which is
  stronger evidence for "no exploitable edge in these simple OHLCV signals
  on these 8 majors" than any single-era result could provide on its own.
  Nothing here is deploy-worthy; the shipped DCA dip-buy remains the only
  positive result and needs no change.

- **DCA dip-buy self-correction check (Run 32)**: with every concretely-
  scoped axis exhausted per Run 31's verdict, this run followed Run 31's own
  recommendation instead of inventing a new recombination — re-validated the
  shipped DCA dip-buy default (dip_threshold_pct=5.0, dip_multiplier=1.5)
  against today's rolling windows (older/train/test all shifted one day
  forward of Run 27's last check), dip-buy ON vs OFF, same capital-
  normalized ROI methodology as Run 4/14/27. **Reproduces the exact
  regime-dependent signature on record since Run 4/27, unchanged**: dip-buy
  ON beats OFF in both declining windows (older delta +0.1665pp, 7/8
  symbols; train delta +0.1235pp, 6/8 symbols) but trails OFF in the
  strongly-rising test window (delta -0.0476pp, only 1/8 symbols better,
  dip mechanism barely fires — 4 dip-buys across 8 symbols in 60 days of a
  strong uptrend). Effect magnitude stays under 0.2pp either direction, same
  order of magnitude as every prior check; no degradation, no new evidence
  for a change. **Keep shipped defaults as-is — no code change.** This
  establishes the going-forward protocol for future runs absent a new
  concretely-scoped axis: periodic self-correction on the one standing
  positive finding (DCA dip-buy) via this same script
  (`research/experiments/dca_self_correction_run32.py`, or a copy with
  updated window dates), not re-tuning any of the 30+ closed levers.

---

_Older run sections (Run 1-5, and the 2026-08-10 prior-session human-seeded notes) are archived in `research/archive/log-2026-08-10_to_2026-08-12.md.gz`; Run 6-9 are archived in `research/archive/log-2026-08-13_to_2026-08-14.md.gz`; Run 21-23 are archived in `research/archive/log-2026-08-20_to_2026-08-21_run21-23.md.gz`; Run 24-25 are archived in `research/archive/log-2026-08-24_to_2026-08-24_run24-25.md.gz`; Run 26 (1d-timeframe closure, folded into the intro paragraph and this note) is archived in `research/archive/log-2026-08-25_to_2026-08-25_run26.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._

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
