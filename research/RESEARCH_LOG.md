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
families, across 21 sessions and ~222 configs.** trend_momentum,
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

**Where this research programme stands (as of Run 21):** the search has now
been exhausted along *two orthogonal axes*, not one. On the **signal** axis:
all three original candle-strategy families are closed across the full TF
sweep, a fourth (Donchian breakout) was decisively rejected, all three
confirmation-gate mechanisms (ADX, relative volume, MTF direction) failed
identically, and both cross-symbol constructions (momentum rotation, pairs
convergence) closed the same way. On the **position-sizing** axis, opened
and closed in Run 21: scaling size by volatility regime cannot rescue any of
them, and produced the sharpest evidence yet that these apparent regime
effects are window artifacts (train and test PF moved in opposite directions
in 6 out of 6 tested pairs). Since sizing can only amplify existing edge and
every signal tested sits at PF<1, **this is the strongest form the null
result has taken: there is nothing here to amplify.** The remaining
untested items are low-priority param variants (1d timeframes; DCA
multiplier magnitude 2.0x between the shipped 1.5x and the rejected 2.5x),
neither of which is expected to change the verdict. **The honest
recommendation is no longer "try the next mechanism" — it is that 21 runs
and ~222 configs spanning per-symbol signals, cross-symbol signals,
confirmation gates, and position sizing, with zero surviving candidates, is
itself the finding, and further search should be directed at the programme's
scope assumptions (fee level, the 8-symbol majors universe, the 1h-4h TF
range, long-only/no-shorting) rather than at new constructions inside
them.** Nothing here is deploy-worthy; the shipped DCA dip-buy remains the
only positive result and needs no change.

**Prior status (as of Run 20, retained for continuity):** all three
original candle-strategy families are exhausted across the full TF sweep,
every confirmation-gate mechanism tried (same-candle: ADX, relative-volume;
cross-TF: MTF direction x 2 base strategies) has failed, a fourth,
mechanically distinct strategy family — Donchian breakout, the mirror
image of mean-reversion — has been decisively rejected (Run 18), and both
cross-symbol data-axis constructions tried so far — momentum rotation
(rs_rotation, Run 19: buy the cross-sectional leader) and relative-value
convergence (pairs_mean_reversion, Run 20: buy the pair laggard) — have
also closed, each failing the same "near-miss -> 3rd-window/per-symbol
check kills it" pattern. Run 20 is the cleanest version of that pattern
yet: 11/42 configs cleared the OOS screen but *zero* survived the follow-up
checks, and unlike Run 19's rotation (which had some train-side signal),
Run 20 had no train-side support anywhere in the 42-config sweep — the
test-window "edge" was regime luck from the first screen, confirmed by the
3rd window. The DCA dip-rebuy cap idea is closed too (reject — capping
never helps). The one DCA variant still open per Run 4's original list is
multiplier *magnitude* between the shipped 1.5x and the already-rejected
2.5x (e.g. 2.0x) — untested, low priority given the cap result suggests
this family's edge is already close to its natural shape. **"More
TF/param sweeps of the four closed strategy families", "more confirmation
gates on existing base signals", "range-relative signals in either
direction (fade or follow)", and "cross-symbol signals on this 8-symbol
long-only universe (rank-based rotation or pair-relative convergence)"
should all be treated as dead ends absent a new idea.** Both directions of
a price-range-relative signal (fade the band touch = mean_reversion,
follow the break = Donchian) fail the same way, and now both directions of
a cross-symbol signal (chase the leader = rs_rotation, buy the laggard =
pairs_mean_reversion) fail the same way too — for a specific structural
reason confirmed twice now: this engine is spot/long-only, so any
cross-symbol construction can only ever be a directional proxy bet on one
leg, never a true market-neutral spread trade, and an 8-name universe is
too small for a rank/pair-based signal to separate real relative strength
from single-name noise. This strengthens the "ceiling may be structural"
reading: it isn't just that price-derived per-symbol signals lack edge,
but that this specific 8-symbol/1h-4h/majors-only/long-only scope may be
too narrow for *any* signal construction tried so far to clear the noise
floor. **Next run should consider:** (a) DCA multiplier magnitude 2.0x
(low priority, per above); (b) a genuinely new construction is needed, not
another cross-symbol variant on 8 long-only names — e.g. a materially
different indicator family entirely (something not yet tried: volatility-
regime-conditioned position sizing rather than entry/exit signals, or a
multi-day 1d-timeframe DCA-style variant), since both rotation and pairs
have now closed the cross-symbol axis specifically; (c) increasingly,
treat this as grounds to question the research programme's own
scope/assumptions (fee level, 8-symbol universe, 1h-4h TF range,
long-only) rather than continuing to search for a signal within them — 20
runs and ~207 configs with zero surviving candidates, now spanning
per-symbol, cross-symbol-momentum, and cross-symbol-mean-reversion signal
constructions, is itself a strong, well-evidenced result.

---

_Older run sections (Run 1-5, and the 2026-08-10 prior-session human-seeded notes) are archived in `research/archive/log-2026-08-10_to_2026-08-12.md.gz`; Run 6-9 are archived in `research/archive/log-2026-08-13_to_2026-08-14.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._

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

## 2026-08-20 — Run 20

**Self-correction check:** reviewed commits since Run 19 — only Run 19's
own log commit landed. No strategy/risk/backtest code touched since Run
19; nothing to re-validate or revert. This programme has never adopted a
code/param change across all 20 runs — a well-recorded string of null
results.

**Region chosen:** per Run 19's flagged next step (b), the mirror-image
cross-symbol construction to rs_rotation — pairs / relative-value mean
reversion. rs_rotation bets on momentum (buy the cross-sectional leader,
ranked across all 8 symbols); this bets on convergence within a single
pair (buy whichever leg has lagged its partner, expecting the gap to
close). Mechanically distinct from every prior signal: not a same-symbol
range/oscillator fade (mean_reversion, grid), not a momentum/breakout
signal (trend_momentum, Donchian, rs_rotation), but a bet on the
relationship between two specific symbols reverting.

**Method:** standalone `PairsMeanReversionStrategy` in
`research/experiments/pairs_mean_reversion.py`. For each of 7 alt/BTC
pairs (every alt in the universe paired against BTC as the natural crypto
market anchor — chosen up front, not by searching for the highest
in-sample correlation), compute the causal rolling z-score of
spread = log(close_alt) - log(close_anchor) over `lookback` bars. BUY
whichever leg has underperformed its partner by more than `entry_z` std
devs (positive "underperformance" score, symmetric across both legs of the
pair); exit once the gap closes back below `exit_z=0.3`. Confirmed this
engine has no shorting anywhere (`app/core/types.py`,
`app/backtest/simulator.py`, `app/risk/models.py`) — so this is a
directional proxy for the relative-value thesis (long the laggard leg
outright), not a market-neutral spread trade, same simplification
rs_rotation already made buying the leader outright. Unchanged exchange-
side 2%/4% SL/TP, same fee/slippage assumptions and train/test/older-
window methodology as every prior run. Swept @ 1h (finer than rs_rotation's
4h — pair divergences are shorter-lived than universe-wide momentum
regimes, and 1h gives enough bars per lookback window): lookback in
{20, 50, 100} x entry_z in {1.5, 2.0} x 7 pairs = 42 configs.

**Results:** 31/42 configs fail the OOS screen (test PF<=1.1 or <30
trades) outright. The other 11 clear it (test PF 1.10-1.98, 30-45 trades)
but **every one of the 11 has train PF < 1** (range 0.162-0.991 — the
42-config sweep has zero train-side support anywhere, bar one n=8 fluke at
train PF 1.046) — the same train-fails/test-looks-great shape this
programme has flagged as regime luck every time it's appeared before, and
here it appears across a majority of pairs simultaneously (a window-level
effect, not a per-pair one). Checked all 11 against the OLDER
non-overlapping window (2025-12-23 to 2026-03-23, same as every prior
3rd-window check): 10/11 fail decisively (PF 0.444-0.856), 1 more
(LINK/BTC lb=20/entry=1.5) numerically clears PF (1.466) but on only 10
trades — noise by sample size. The lone survivor of the PF screen,
ETH/BTC lb=50/entry=2.0 (OLDER PF 1.25/34 trades), fails the per-symbol
consistency check instead: BTC leg PF 1.731 (+19.5% return) is carrying
the whole result while the ETH leg itself is negative (PF 0.707, -6.9%) —
buying BTC-the-anchor on relative dips, not a genuine pair-relative
signal (and directionally consistent with BTC dip-buying being the one
proven edge this programme has found, via DCA — see below). **0/11
near-misses survive either required check — closed, the most decisive
rejection of a near-miss cohort in this programme's 20-run history.**
Full per-config train/test numbers and rationale for all 42 configs are
in `research/decisions.jsonl` (11 logged `noise`, 31 `reject`).

**Verdict:** REJECT — no code or param change. `research/decisions.jsonl`
carries all 42 configs. Both cross-symbol data-axis constructions this
programme has now tried (rs_rotation's momentum-chase, pairs_mean_
reversion's convergence-chase) are closed for the same structural reason:
this engine is spot/long-only, so a cross-symbol "edge" can only ever be a
directional proxy on one leg, and an 8-name universe is too small to
separate real cross-sectional signal from single-name noise either way.
DISTILLED LEARNINGS refreshed above with the full finding and updated
programme-status paragraph.

**Commit:** (recorded after this run's commit — see git log for hash.)

_Run 17-19 (2026-08-18 to 2026-08-19) are archived in `research/archive/log-2026-08-18_to_2026-08-19.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._

_Run 14-16 (2026-08-17 to 2026-08-18) are archived in `research/archive/log-2026-08-17_to_2026-08-18.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._

_Run 10-13 (2026-08-15 to 2026-08-16) are archived in `research/archive/log-2026-08-15_to_2026-08-16.md.gz`; their conclusions are folded into DISTILLED LEARNINGS above._
