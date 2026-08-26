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
on trend_momentum@1h and mean_reversion@1h; still no adopted change to
shipped risk defaults.

---

## DISTILLED LEARNINGS (read this first; refreshed every run)

**No robust, generalizing edge has been found yet in the candle-strategy
families, across 28 sessions and ~283 configs.** trend_momentum,
mean_reversion, and grid are now each **fully closed across the entire
5m/15m/1h/4h TF sweep** — every combo tested is either net-negative or only
clears the OOS bar by luck/small-sample noise. Donchian breakout, Supertrend,
and Capitulation Wick Reversal (3 mechanically distinct trend/breakout/
pattern families) are also closed. Honest baseline: simple RSI/BB/EMA/grid/
ATR-band/candlestick-shape signals on these 8 majors appear over-arbitraged;
fees turn near-breakeven setups negative. The one asymmetric,
mechanically-explicable (not curve-fit) positive finding so far is DCA's
dip-buy feature — already shipped as the default, not a new change. **Full
evidence for every closed TF/param combo lives in `research/decisions.jsonl`
and archived run sections below/in `research/archive/`; this section states
only the conclusions and why, not the blow-by-blow.**

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

- **DCA dip_multiplier magnitude (Run 27, closes the last flagged-open DCA
  variant)**: dip_multiplier in {1.5 (shipped), 1.75, 2.0, 2.5} at the
  shipped dip_threshold_pct=5.0, isolated from the threshold change Run 4
  bundled it with and the buy-count cap Run 14 tested separately. Effect is
  real but trivial (<0.35pp even at 2.5x) and flips sign with the regime:
  +0.06 to +0.35pp in both declining windows tested (7/8 symbols benefit —
  a bigger multiplier lowers cost basis further when dips are frequent) but
  −0.03 to −0.11pp in a strongly-rising window (only 1/8 symbols benefit —
  more capital deployed at a locally-worse price when dips are rare and the
  flat schedule already wins big on its own). Same anti-correlated-across-
  regimes signature as every non-signal lever since Run 21/22. **Keep
  shipped dip_multiplier=1.5x — closed, no DCA variants remain flagged.**

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

**Where this research programme stands (as of Run 28):** the search has now
been exhausted along *six orthogonal axes* — three levers plus three scope
assumptions — and the **signal** axis spans six mechanically distinct
strategy families across five broad signal-source categories (price-level/
band, moving-average relationship, price *shape*, cross-symbol/volume, and
now calendar/session-time).
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
symbol losing). **The only scope assumption left untested is long-only**
(shorting is a larger architecture change, out of scope per the hard limits
— cannot be tested without expanding scope beyond params/code tuning, not a
param tune). **The honest recommendation remains that 28 runs and ~283
configs spanning per-symbol signals (6 strategy families across 5 signal-
source categories) across the full viable TF range on two disjoint 8-symbol
universes, cross-symbol signals, confirmation gates, position sizing, exit
mechanisms, trading-cost level, DCA parameter magnitude, and calendar/
session-time gating, with zero surviving candidates, is itself the
finding.** No item remains flagged as open in this section — the next run
should pick a genuinely new axis not listed above. Candidates: a 6th
signal-source category would need a data source this codebase doesn't
currently fetch (e.g. order-book/funding-rate data, likely out of reach via
`data-api.binance.vision`'s public kline endpoints — check what's fetchable
before committing to a design); alternatively, a day-of-week calendar
variant (distinct from hour-of-day, same category but untested granularity)
or combining two previously-closed single-axis levers (e.g. session-hour
gate + relative-volume gate together) remain unexplored combinations.
Nothing here is deploy-worthy; the shipped DCA dip-buy remains the only
positive result and needs no change.

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
