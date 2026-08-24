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
strategy family (Supertrend, ATR-adaptive trailing bands); still no adopted
change to shipped risk defaults.

---

## DISTILLED LEARNINGS (read this first; refreshed every run)

**No robust, generalizing edge has been found yet in the candle-strategy
families, across 24 sessions and ~258 configs.** trend_momentum,
mean_reversion, and grid are now each **fully closed across the entire
5m/15m/1h/4h TF sweep** — every combo tested is either net-negative or only
clears the OOS bar by luck/small-sample noise. Donchian breakout and
Supertrend (2 mechanically distinct trend/breakout families) are also
closed at 1h/4h. Honest baseline: simple RSI/BB/EMA/grid/ATR-band signals
on these 8 majors appear over-arbitraged; fees turn near-breakeven setups
negative. The one asymmetric, mechanically-explicable (not curve-fit)
positive finding so far is DCA's dip-buy feature — already shipped as the
default, not a new change. **Full evidence for every closed TF/param combo
lives in `research/decisions.jsonl` and archived run sections below/in
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

**Where this research programme stands (as of Run 24):** the search has now
been exhausted along *four orthogonal axes* — three levers plus one scope
assumption — and the **signal** axis now spans five mechanically distinct
strategy families, not four. All three original candle-strategy families
are closed across the full TF sweep; Donchian breakout (fixed-lookback
channel) and Supertrend (ATR-adaptive trailing band, Run 24) are both
decisively rejected as trend-following breakout constructions; all three
confirmation-gate mechanisms (ADX, relative volume, MTF direction) failed
identically; and both cross-symbol constructions (momentum rotation, pairs
convergence) closed the same way. On the **position-sizing** axis (Run 21):
scaling size by volatility regime cannot rescue any of them, with train/test
PF moving in opposite directions in 6/6 tested pairs — the signature of a
window artifact, not a persistent relationship. On the **exit-mechanism**
axis (Run 22): neither a time-based forced exit nor tighter SL/TP rescues
either base signal — trend_momentum rejects decisively (8/8 configs),
mean_reversion reproduces the regime-luck signature on two new levers (8/8
configs). On the **fee/cost-level** axis (Run 23): swept fee_bps/
slippage_bps from shipped 7.5/4.0 down to a theoretical zero on
trend_momentum (15m, 1h) and mean_reversion@1h — 0/12 configs cleared both
train and test PF>1.1 at ANY cost tier including zero, directly refuting the
informal "fees are eating a near-breakeven edge" narrative. **Run 24 adds no
new axis but closes the second of two possible trend-following breakout
mechanisms (fixed-lookback vs volatility-adaptive)** — both fail for the
same underlying reason (low win-rate, whipsawed by chop between the rare
real trend legs), which strengthens the read that the absence of edge is a
property of these 8 majors/this fee level/this TF range, not of which
breakout construction is used. **The honest recommendation remains that 24
runs and ~258 configs spanning per-symbol signals (5 families), cross-symbol
signals, confirmation gates, position sizing, exit mechanisms, and
trading-cost level, with zero surviving candidates, is itself the finding.**
Remaining scope assumptions not yet tested: the 8-symbol majors universe
(would need a larger cross-section, flagged as out of reach in Run 19/20 for
the cross-symbol constructions specifically, but not yet tried for the
per-symbol families) and the 1h-4h TF range / long-only constraint (shorting
is a larger architecture change, out of scope per the hard limits). The
remaining low-priority untested items (1d timeframes; DCA multiplier
magnitude 2.0x) are not expected to change the verdict. Nothing here is
deploy-worthy; the shipped DCA dip-buy remains the only positive result and
needs no change.

**Prior status (as of Run 21, retained for continuity):** the search had
been exhausted along two orthogonal axes, not three. On the **signal** axis:
all three original candle-strategy families closed across the full TF
sweep, a fourth (Donchian breakout) decisively rejected, all three
confirmation-gate mechanisms (ADX, relative volume, MTF direction) failed
identically, and both cross-symbol constructions (momentum rotation, pairs
convergence) closed the same way. On the **position-sizing** axis, opened
and closed in Run 21: scaling size by volatility regime cannot rescue any of
them, and produced the sharpest evidence yet (at the time) that apparent
regime effects are window artifacts (train and test PF moved in opposite
directions in 6 out of 6 tested pairs). Since sizing can only amplify
existing edge and every signal tested sits at PF<1, that was "the strongest
form the null result has taken: there is nothing here to amplify" — Run 22
then tested the remaining major lever (exit mechanism) and found the same
thing again, from a still-cleaner angle (train pf never crosses 1 anywhere
in that sweep, not even an anti-correlated tell — just no signal at all).

---

_Older run sections (Run 1-5, and the 2026-08-10 prior-session human-seeded notes) are archived in `research/archive/log-2026-08-10_to_2026-08-12.md.gz`; Run 6-9 are archived in `research/archive/log-2026-08-13_to_2026-08-14.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._

## 2026-08-24 — Run 24

**Self-correction check:** `git log ae5ded7..HEAD -- backend/` (ae5ded7 =
Run 23's commit, current HEAD before this run's own commit) is empty — no
commits touched `backend/` since Run 23. Nothing to re-validate or revert.

**Region tested:** signal axis, 5th strategy family. Prior runs closed 4
mechanically distinct families (trend_momentum EMA-cross, mean_reversion
BB/RSI, grid range-ladder, Donchian fixed-lookback breakout) plus 3
confirmation-gate mechanisms and 2 cross-symbol constructions. This run adds
**Supertrend**: ATR-scaled trailing bands with a stateful ratchet (the band
only ever tightens toward price within a trend; flips when close crosses
the opposite band) — the first *volatility-adaptive* trend-following
construction tested, versus Donchian's fixed N-period channel. BUY on
flip-to-uptrend, SELL on flip-to-downtrend, long-only, unchanged exchange-
side 2%/4% SL/TP. Implemented in `research/experiments/supertrend.py`,
standalone (not registered in `app/strategies/registry.py`, no production
file touched).

**Design:** atr_period {10, 14} x multiplier {2.0, 3.0} @ 1h and 4h = 8
configs. Same train/test windows as Runs 21-23: train 2026-03-21..2026-06-19,
test 2026-06-19..2026-08-19, older 2025-12-21..2026-03-21 (3rd window,
reserved for anything clearing the screen).

**Results (train PF → test PF, test n):**

| tf | atr_period | multiplier | train pf | test pf | test n |
|---|---|---|---|---|---|
| 1h | 10 | 2.0 | 1.027 | 0.673 | 71 |
| 1h | 10 | 3.0 | 0.668 | 0.598 | 96 |
| 1h | 14 | 2.0 | 1.020 | 0.676 | 54 |
| 1h | 14 | 3.0 | 0.734 | 0.633 | 91 |
| 4h | 10 | 2.0 | 0.596 | 0.468 | 41 |
| 4h | 10 | 3.0 | 0.488 | 0.654 | 31 |
| 4h | 14 | 2.0 | 0.699 | 0.372 | 40 |
| 4h | 14 | 3.0 | 0.325 | 0.769 | 33 |

**$ on $100 / $1000 (test window, avg per-symbol return):** every config
loses money, from −$0.02/−$0.23 (4h atr=14 mult=3.0, the best row) to
−$0.13/−$1.27 (4h atr=10 mult=2.0, the worst row).

**Verdict: decisive reject, 8/8 configs. No candidate, no code change. No
3rd-window check triggered** — the best test PF in the whole sweep (0.769,
4h atr=14 mult=3.0) comes with the worst train PF in the sweep (0.325), so
there's no near-miss to check further. The two tightest-band 1h configs
(mult=2.0) reach the closest-to-1.0 train PF anywhere in the sweep
(1.020–1.027) but test PF on those same rows collapses to 0.673–0.676 — a
train-side near-breakeven reading that does not generalize, the same
train/test disconnect shape seen in every other closed family. Win rates
are low throughout (15–34%), the signature of a trend-following flip
getting whipsawed by chop between the (rare) real trend legs — mechanically
the same failure mode Donchian breakout (Run 18) showed, now reproduced via
a second, structurally different (ATR-adaptive band-flip vs fixed-lookback
channel) trend-following construction. **Closed — do not re-tune
atr_period/multiplier on this construction.** Combined with Donchian, this
rules out both a fixed-lookback and a volatility-adaptive breakout signal on
this 8-symbol universe at 1h/4h; the absence of edge looks structural to the
instruments/fee level/TF range rather than to either channel construction.

**Files:** `research/experiments/supertrend.py` (new). 8 entries appended to
`research/decisions.jsonl` (199 → 207 lines pre-rotation).

---

## 2026-08-21 — Run 23

**Self-correction check:** `git log f992508..HEAD -- backend/` (f992508 =
Run 22's commit, current HEAD before this run's own commit) is empty — no
commits touched `backend/` since Run 22. Nothing to re-validate or revert.
Also caught and fixed unrelated repo-hygiene issue at the start of this run:
the working tree was on a detached HEAD 7 commits ahead of local `main` and
`origin/main` (Runs 16-22 had been committed but never merged/pushed by a
prior session) — fast-forwarded `main` to that HEAD and pushed, so no
research history was at risk of being lost, but flagging it in case a future
session needs to know why the commit count here doesn't match a prior
session's expectation.

**Region tested (scope assumption, not a new construction):** trading
cost level. All 22 prior runs held `SimConfig.fee_bps=7.5`/`slippage_bps=4.0`
fixed and varied signal, sizing, or exit mechanism instead. DISTILLED
LEARNINGS asserted "fees turn near-breakeven setups negative" without ever
quantifying it — this run tests that claim directly by sweeping cost down
to a theoretical zero, isolating whether the 22-run null result is a
trading-cost artifact or a genuine absence of edge. No strategy code or
param search — shipped-default entry params throughout (all already
exhaustively characterized), unmodified production `run_candle_backtest`,
only `SimConfig.fee_bps`/`slippage_bps` vary. Implemented in
`research/experiments/fee_sensitivity.py`.

**Design:** 4 cost tiers — shipped (7.5/4.0), bnb_discount (4.0/2.0, a
realistic reduced-fee tier), near_zero (1.0/0.5), theoretical_zero (0/0) — x
3 bases: trend_momentum@15m and @1h (its two best-performing/most
fee-adjacent TFs; @15m's shipped-default train PF of 1.226 is the closest
to breakeven-and-above of any config in the whole programme's history) plus
mean_reversion@1h (contrast base: train PF has never exceeded ~0.6 under
sizing or exit-mechanism levers, to see whether cost reduction can create
train-side support where those levers couldn't) = 12 configs. Same
train/test windows as Run 21/22 for direct comparability: train
2026-03-19..2026-06-18, test 2026-06-18..2026-08-18, older
2025-12-19..2026-03-19 (3rd window, reserved for anything clearing the
screen).

**Results (train PF → test PF, test n):**

| base | tier | fee/slip bps | train pf | test pf | test n |
|---|---|---|---|---|---|
| trend_momentum@15m | shipped | 7.5/4.0 | 1.226 | 0.780 | 25 |
| trend_momentum@15m | bnb_discount | 4.0/2.0 | 1.376 | 0.683 | 36 |
| trend_momentum@15m | near_zero | 1.0/0.5 | 1.437 | 0.679 | 40 |
| trend_momentum@15m | theoretical_zero | 0/0 | 1.516 | 0.666 | 43 |
| trend_momentum@1h | shipped | 7.5/4.0 | 0.586 | 0.484 | 83 |
| trend_momentum@1h | bnb_discount | 4.0/2.0 | 0.662 | 0.649 | 91 |
| trend_momentum@1h | near_zero | 1.0/0.5 | 0.713 | 0.732 | 91 |
| trend_momentum@1h | theoretical_zero | 0/0 | 0.792 | 0.755 | 91 |
| mean_reversion@1h | shipped | 7.5/4.0 | 0.573 | 2.174 | 97 |
| mean_reversion@1h | bnb_discount | 4.0/2.0 | 0.676 | 2.468 | 97 |
| mean_reversion@1h | near_zero | 1.0/0.5 | 0.768 | 2.741 | 97 |
| mean_reversion@1h | theoretical_zero | 0/0 | 0.774 | 2.838 | 97 |

**$ on $100 / $1000 (test window, avg per-symbol return):**
trend_momentum@15m loses money at every tier, −$0.01 to −$0.02 per $100
(worst at zero cost, −$0.19 per $1000 — see below, this is the overfit
signature, not a real cost effect). trend_momentum@1h loses at every tier
too but the loss shrinks as cost drops, −$0.04 to −$0.10 per $100 (−$0.44 to
−$0.99 per $1000). mean_reversion@1h gains at every tier and gains more as
cost drops, +$0.13 to +$0.18 per $100 (+$1.25 to +$1.75 per $1000) — but see
below, this is inherited regime luck, not a cost effect either.

**Verdict: reject (8 configs, both trend_momentum TFs) / noise (4 configs,
mean_reversion@1h). No candidate, no code change. 0/12 configs clear train
PF>1.1 AND test PF>1.1 with n>=30 at any cost tier — no 3rd-window check was
triggered by the screen, but all three patterns below were still checked
against known priors for consistency.**

**trend_momentum@1h — real, quantified cost sensitivity, still short of
breakeven at zero cost:** train and test PF move the *same* direction as
cost drops (train 0.586→0.792, +35%; test 0.484→0.755, +56%) — unlike every
sizing/exit lever tested on this base, which never showed a consistent
cost-like relationship. This is the first evidence in the whole programme
that trading cost measurably suppresses this signal. But the theoretical
zero-cost ceiling is PF 0.792 train / 0.755 test — both still decisively
below 1.0. Quantifies the "fees hurt" claim precisely: yes, but not enough
edge exists underneath to matter even with the drag fully removed.

**trend_momentum@15m — a new failure signature, not seen in Runs 1-22:**
train PF clears the 1.1 screen at *every* single cost tier (1.226 shipped,
rising to 1.516 at zero cost, n=125-142, a real sample) — the first time any
config in this programme has shown train-side PF>1.1 outside of tiny/starved
samples. But test PF stays stuck at 0.666-0.780 throughout, and moves the
*wrong* direction as cost drops (down, from 0.780 to 0.666) while train
moves up. This is the mirror image of mean_reversion@1h's familiar pattern
(there, test looks good and train doesn't; here, train looks good and test
doesn't) — a clean overfit-to-the-train-window signature. Removing cost
cannot rescue a signal whose apparent train edge was never real
out-of-sample to begin with; if anything, zero cost makes the divergence
from test *worse*, which is further evidence the train-side PF>1.1 here is
noise/regime-specific rather than a suppressed real edge.

**mean_reversion@1h — regime luck reproduced on a third orthogonal lever:**
same shape as Run 21 (sizing) and Run 22 (exit mechanism) — test PF clears
the screen at every tier and climbs further as cost drops (2.174→2.838), but
train PF never crosses 1.0 anywhere in the sweep (0.573→0.774). Cost
reduction amplifies whatever is driving the test-window number; it creates
no train-side support, so it cannot be distinguishing signal from noise
here. Same conclusion as always: this base's test-window outperformance is a
window artifact, and no lever tested across three separate runs (sizing,
exit, now cost) has ever produced train-side confirmation for it.

**Why this closes the fee-level scope assumption:** DISTILLED LEARNINGS
previously treated "fees eat a near-breakeven edge" as background context,
not a tested claim. This run tested it to its logical floor (zero cost) on
the two most fee-adjacent bases in the programme and found: (a) for
trend_momentum, cost matters but isn't the binding constraint — the ceiling
without any cost at all is still unprofitable; (b) the one config that *did*
look promising pre-cost (15m train PF 1.226-1.516) fails on generalization,
not cost; (c) mean_reversion's known regime luck is completely orthogonal to
cost. None of the three outcomes leaves fee level as an open question worth
re-testing.

**Files:** `research/experiments/fee_sensitivity.py` (new). 12 entries
appended to `research/decisions.jsonl` (199 total, still under the 250
rotation trigger — `research/rotate_archive.py` run, no rotation needed
this time). Active log is now ~53KB, over the ~40KB advisory threshold, but
only 3 full run-sections remain (21-23, well under the "keep last ~15"
floor) — the excess is entirely inside the DISTILLED LEARNINGS block itself
(lines 21-437), which the archiving mechanism doesn't touch. Flagging for a
future run: a compression pass over DISTILLED LEARNINGS' older/more verbose
bullets (the original per-family closure writeups) could tighten this
without losing conclusions, if it keeps growing.

**Commit:** (recorded after this run's commit — see git log for hash.)

## 2026-08-21 — Run 22

**Self-correction check:** `git log a2a45bc..HEAD -- backend/` (a2a45bc =
Run 21's commit, current HEAD before this run's own commit) is empty — no
commits touched `backend/` since Run 21. Nothing to re-validate or revert.
This programme has never shipped a strategy-code change (DCA dip-buy
predates it) — still true after 22 runs.

**Region tested (NEW axis, neither signal nor sizing):** the EXIT
mechanism. All 21 prior runs varied *which trades are taken* (signal axis)
or *how big they are* (Run 21, sizing axis); risk config (SL 2%, TP 4%,
daily-loss halt, drawdown kill switch, position caps) had been held at repo
defaults throughout, untouched. Run 22 opens that axis with two
sub-experiments, both layered onto trend_momentum@1h and mean_reversion@1h
at shipped-default entry params (both deeply characterized already, giving
known train/test baselines to compare against) — isolating the exit change,
not reopening a closed entry question.

**(A) Time-based forced exit.** If a position is still open N candles after
entry, force-close it at market on the next candle's open (same no-lookahead
fill convention the simulator already uses for every other signal exit).
SL/TP are checked intra-candle *first*, every bar, unchanged from
production — so they can still fire before the cap ever gets a chance to.
This only bounds worst-case holding time; it loosens nothing. Implemented as
`run_candle_backtest_capped` in `research/experiments/exit_mechanism.py`, a
standalone copy of `run_candle_backtest` with exactly one addition (the
forced-exit check after the strategy's own decision). The `max_hold_bars=
None` control was verified trade-for-trade identical to unmodified
production `run_candle_backtest` on BTCUSDT/1h for both base strategies
before any deltas were trusted (18 vs 18 trades, 20 vs 20 trades, identical
final equity to the cent).

N was chosen from each base's own no-cap train holding-duration
distribution, not blind 12h/24h/48h/96h guessing — the two strategies hold
trades for very different lengths of time:
- trend_momentum@1h no-cap TRAIN durations (n=94): mean 24.7h, median 16.5h,
  P25 8h, P75 33.8h, P90 52h, max 113h → swept **{8, 16, 33, 52}** (≈P25/
  median/P75/P90).
- mean_reversion@1h no-cap TRAIN durations (n=141): mean 11.1h, median 11h,
  P25 6h, P75 17h, P90 20h, max 39h → swept **{6, 11, 17, 24}** (≈P25/
  median/P75/just-above-P90).

**(B) Tighter SL/TP (secondary).** Hard limit respected strictly: only
SL<=2.0%/TP<=4.0% combinations were tested, never wider. Swept **{1.5/3.0,
1.0/2.0, 1.5/4.0}** vs the shipped 2.0/4.0 control. RiskConfig is already a
parameter of production `run_candle_backtest`, so (B) needed no new
simulator code at all — every (B) row is unmodified production code, a
custom `RiskConfig` only.

**Results (train PF → test PF, test n):**

| base | mechanism | value | train pf | test pf | test n |
|---|---|---|---|---|---|
| trend_momentum@1h | control (no cap, SL/TP 2.0/4.0) | — | 0.586 | 0.484 | 83 |
| trend_momentum@1h | max_hold_bars | 8 | 0.650 | 0.417 | 83 |
| trend_momentum@1h | max_hold_bars | 16 | 0.584 | 0.522 | 91 |
| trend_momentum@1h | max_hold_bars | 33 | 0.464 | 0.686 | 92 |
| trend_momentum@1h | max_hold_bars | 52 | 0.535 | 0.615 | 83 |
| trend_momentum@1h | SL/TP | 1.5/3.0 | 0.524 | 0.487 | 72 |
| trend_momentum@1h | SL/TP | 1.0/2.0 | 0.512 | 0.379 | 71 |
| trend_momentum@1h | SL/TP | 1.5/4.0 | 0.518 | 0.405 | 72 |
| mean_reversion@1h | control (no cap, SL/TP 2.0/4.0) | — | 0.573 | 2.174 | 97 |
| mean_reversion@1h | max_hold_bars | 6 | 0.495 | 1.749 | 98 |
| mean_reversion@1h | max_hold_bars | 11 | 0.476 | 1.673 | 98 |
| mean_reversion@1h | max_hold_bars | 17 | 0.544 | 1.976 | 97 |
| mean_reversion@1h | max_hold_bars | 24 | 0.569 | 2.158 | 97 |
| mean_reversion@1h | SL/TP | 1.5/3.0 | 0.493 | 1.569 | 76 |
| mean_reversion@1h | SL/TP | 1.0/2.0 | 0.488 | 1.447 | 98 |
| mean_reversion@1h | SL/TP | 1.5/4.0 | 0.488 | 1.626 | 62 |

**$ on $100 / $1000 (test window, avg per-symbol return):** every
trend_momentum row loses money, −$0.07 to −$0.10 per $100 (−$0.67 to −$0.99
per $1000) at every N/SL-TP setting, no better than its own control.
mean_reversion@1h rows show +$0.05 to +$0.12 per $100 (+$0.51 to +$1.25 per
$1000) — but see below, this is inherited regime luck that fails the 3rd
window on every config.

**Verdict: reject (8 configs, both trend_momentum sub-experiments) / noise
(8 configs, both mean_reversion sub-experiments). No candidate, no code
change.**

**trend_momentum — decisive reject, no 3rd-window check warranted:** test pf
never exceeds 0.686 at any N or any SL/TP tried (control 0.484), and train
pf never exceeds 0.650 anywhere in the 8-config sweep. Neither bounding
holding time nor tightening stops helps or reveals train-side edge — there
is no edge to protect or extract in the underlying EMA-cross signal.

**mean_reversion — all 8 configs clear the OOS screen (test pf 1.447–2.174,
n 62–98) but inherit it from the base's own untouched control**, which
already scores test pf 2.174 with train pf only 0.573 (the long-documented
mean_reversion@1h regime luck first flagged in earlier runs and confirmed
again in Run 21). Checked all 8 against the OLDER non-overlapping window
(2025-12-19..2026-03-19): **8/8 fail decisively**, older-window pf 0.387–
0.510 on real 63–113-trade samples. Per-symbol TEST breakdown for every one
of the 8 shows 2–3 of 8 symbols contributing **zero** trades (ETH and ADA in
every (A) config; BTC joined by SOL/ETH/ADA at various (B) settings) — the
aggregate rests on a shrinking handful of symbols in one favorable window,
the same small-sample signature as every prior mean_reversion@1h near-miss.

**Why this is the cleanest version of the null yet:** Run 21's sizing
experiment found train and test PF moving in *opposite* directions — an
anti-correlated tell that at least proved something was happening (just not
something real). Here, train pf simply **never crosses 1 anywhere**, in
either sub-experiment, for either base, regardless of how the exit is
changed. There is no tell to explain because there is nothing to explain —
the exit mechanism has no lever to pull on a signal with no underlying edge.
This confirms Run 21's generalization from a third angle: it was never
specific to sizing. No mechanism layered on top of a PF<1 entry signal —
changing size, changing exit timing, or changing exit price — can
manufacture edge that was never there. **Closed — do not re-tune
max_hold_bars or SL/TP magnitude on trend_momentum@1h or mean_reversion@1h.**
This closes the exit-mechanism axis; DISTILLED LEARNINGS refreshed above
with the full finding and updated programme-status paragraph.

**Files:** `research/experiments/exit_mechanism.py` (new). 16 entries
appended to `research/decisions.jsonl` (187 total, still under the 250
rotation trigger — `research/rotate_archive.py` run, no rotation needed
this time).

**Commit:** (recorded after this run's commit — see git log for hash.)

## 2026-08-20 — Run 21

**Self-correction check:** reviewed all commits touching `backend/` since the
programme began — the only strategy-code change ever committed is
`5c23fd9 mean_reversion: optional trend-filter EMA`, which is opt-in and
default-off, and no research run has ever flipped a production default. There
is nothing this programme has shipped that needs re-validating, and nothing to
revert. (Same conclusion as Runs 19-20; recorded again rather than skipped so
the check is visible in the record.)

**Region tested (NEW axis, not a new signal):** volatility-regime **position
sizing**. Every one of the 20 prior runs varied *which trades are taken* —
strategy family, timeframe, indicator params, or a confirmation gate that
vetoes entries. Run 21 varies *how large each trade is*, leaving the
entry/exit signal completely untouched. This is the first non-signal lever
tested, and it is available precisely because profit factor is a
dollar-weighted ratio: rescaling positions changes account-level PF even when
the trade list, trade count, and win-rate are byte-for-byte identical.

**Mechanism:** ATR(14) normalized by close, ranked into a percentile against
its own trailing 100 candles (rolling window, current-and-past values only —
no lookahead), bucketed into tertiles at the entry candle, with a size
multiplier applied per tertile on top of the normal `position_size_pct`
notional. Implemented in `research/experiments/vol_regime_sizing.py` as a
standalone copy of `run_candle_backtest` with exactly one added line
(`notional *= size_mult`); fees, slippage, SL/TP, trailing stops and the
adaptive-sizing layer are copied verbatim. **No production code touched, and
no risk control altered** — the multipliers scale the position-size input
only; stop-loss, take-profit, daily-loss halt and drawdown kill switch are
untouched at repo defaults.

**Control validation:** the mult=1/1/1 control was checked against unmodified
production `run_candle_backtest` on BTCUSDT 1h — 16 trades vs 16 trades,
identical opened_at/closed_at/entry/exit/pnl on every one, identical final
equity. The sized simulator introduces no drift, so all deltas below are
attributable to sizing alone.

**Design:** 5 sizing variants x 3 previously-closed base signals = 15 configs.
Variants: control (1/1/1), high_boost (0.5/1/1.5), low_boost (1.5/1/0.5),
high_boost_strong (0.25/1/2.0), low_boost_strong (2.0/1/0.25), given as
low/mid/high-vol tertile multipliers. Bases: trend_momentum@1h, trend_momentum@4h,
mean_reversion@1h — all at shipped defaults, all previously closed as no-edge,
chosen to span both a deeply-negative base and a base with known
regime-luck-inflated test numbers. Train 2026-03-19..2026-06-18 (150d-60d ago),
test 2026-06-18..2026-08-18 (60d-0d, held out), 3rd window
2025-12-19..2026-03-19 (240d-150d) for anything clearing the screen.

**Results (PF train -> test):**

| base | variant | train PF | test PF | test n |
|---|---|---|---|---|
| trend_momentum@1h | control | 0.586 | 0.484 | 83 |
| trend_momentum@1h | high_boost | 0.572 | 0.568 | 83 |
| trend_momentum@1h | low_boost | 0.603 | 0.412 | 83 |
| trend_momentum@1h | high_boost_strong | 0.575 | 0.637 | 83 |
| trend_momentum@1h | low_boost_strong | 0.628 | 0.379 | 83 |
| trend_momentum@4h | control | 0.644 | 0.974 | 28 |
| trend_momentum@4h | high_boost | 0.450 | 1.249 | 28 |
| trend_momentum@4h | low_boost | 0.795 | 0.851 | 28 |
| trend_momentum@4h | high_boost_strong | 0.312 | 1.610 | 28 |
| trend_momentum@4h | low_boost_strong | 0.881 | 0.798 | 28 |
| mean_reversion@1h | control | 0.573 | 2.174 | 97 |
| mean_reversion@1h | high_boost | 0.607 | 1.940 | 97 |
| mean_reversion@1h | low_boost | 0.502 | 2.823 | 97 |
| mean_reversion@1h | high_boost_strong | 0.658 | 1.843 | 97 |
| mean_reversion@1h | low_boost_strong | 0.454 | 4.066 | 97 |

**$ on $100 / $1000 (test window, avg per-symbol return):** every
trend_momentum row is a loss — @1h between −$0.07 and −$0.14 per $100
(−$0.67 to −$1.44 per $1000); @4h between −$0.02 and +$0.02 per $100
(+$0.24 per $1000 at best). mean_reversion@1h rows show +$0.10 to +$0.17
per $100 (+$0.97 to +$1.75 per $1000), but see below — that is the base
signal's known regime luck, and it reverses to −$0.09 to −$0.36 per $100 on
the 3rd window.

**Verdict: reject (13 configs) / noise (4 configs). No candidate. No code
change.** Two independent reasons, either sufficient:

1. **Train and test PF move in exactly opposite directions — 6 out of 6
   mirrored pairs.** In every base signal, whichever sizing direction helps
   the test window hurts the train window by a comparable margin, and vice
   versa. The starkest: trend_momentum@4h high_boost_strong halves train PF
   (0.644 -> 0.312) while lifting test PF 65% (0.974 -> 1.610);
   mean_reversion@1h low_boost_strong drops train PF (0.573 -> 0.454) while
   nearly doubling test PF (2.174 -> 4.066). A genuine vol-regime/trade-quality
   relationship would point the same way in both windows. Perfect
   anti-correlation across three unrelated base signals and both sizing
   directions is the signature of a window-specific artifact, and it is the
   cleanest such tell this programme has produced.

2. **The four configs that cleared the OOS screen are all mean_reversion@1h,
   and they inherited the clearing from their own control.** That base's
   mult=1 control already scores test PF 2.174 — the long-documented
   mean_reversion@1h regime luck (train PF 0.573, no train-side edge at all).
   All four fail the 3rd non-overlapping window decisively: PF 0.401, 0.457,
   0.393, 0.495 on 109-121 real trades, avg returns −8.8% to −35.9%. The
   per-symbol test breakdown adds a second failure — ETH and ADA contribute
   **zero** trades in the test window, so the aggregate rests on 6 symbols in
   one favorable regime.

Nothing cleared the bar on its own merit. trend_momentum@1h sits at test PF
0.38-0.64 at every setting — no multiplier arrangement comes close.
trend_momentum@4h high_boost_strong is the only row that looks tempting in
isolation (test PF 1.610) and it fails two ways at once: n=28 is below the
30-trade floor, and its train PF of 0.312 is the worst in the entire sweep.

**A tangent worth recording, because it is seductive and wrong:** within the
test window the favorable direction is *opposite for the two strategy types* —
trend_momentum prefers high-vol sizing, mean_reversion prefers low-vol sizing.
That has a tidy mechanical story (trend-following needs movement to profit
from; mean-reversion needs calm ranges that actually revert). It is exactly
the kind of narrative that would justify shipping a change. The train window
reverses **both** of them, which is what rules it out. Noting it explicitly so
a future run recognizes the story and does not re-derive it as a new idea.

**Generalization (the durable lesson):** position sizing cannot manufacture
edge — it can only amplify or attenuate whatever the signal already has. With
every signal in this programme sitting at PF < 1, scaling size by regime is
just a leveraged bet on which regime the next window happens to be in. This
closes the position-sizing axis flagged as Run 20's next step (b), and it
closes it more informatively than a simple null: it explains *why* no sizing
scheme could have worked here, which applies to any future sizing idea
(Kelly-style, volatility-targeting, drawdown-scaled) without needing to test
each one.

**Files:** `research/experiments/vol_regime_sizing.py` (new). 15 entries
appended to `research/decisions.jsonl`. Log rotated: Run 10-13 -> 
`research/archive/log-2026-08-15_to_2026-08-16.md.gz`, Run 14-16 ->
`research/archive/log-2026-08-17_to_2026-08-18.md.gz` (active log was 76KB,
over the 40KB threshold; now 39KB with all conclusions preserved in DISTILLED
LEARNINGS).

_Run 20 (2026-08-20) is archived in `research/archive/log-2026-08-20_to_2026-08-20.md.gz`; its conclusions are folded into DISTILLED LEARNINGS above._

_Run 17-19 (2026-08-18 to 2026-08-19) are archived in `research/archive/log-2026-08-18_to_2026-08-19.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._

_Run 14-16 (2026-08-17 to 2026-08-18) are archived in `research/archive/log-2026-08-17_to_2026-08-18.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._

_Run 10-13 (2026-08-15 to 2026-08-16) are archived in `research/archive/log-2026-08-15_to_2026-08-16.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._
