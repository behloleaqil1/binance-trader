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
families, across 11 sessions and ~97 configs.** Every trend_momentum /
mean_reversion / grid combo tested so far is either net-negative or only
clears the OOS bar by luck/small-sample noise. Honest baseline: simple
RSI/BB/EMA signals on these 8 majors appear over-arbitraged; fees turn
near-breakeven setups negative. The one asymmetric, mechanically-explicable
(not curve-fit) positive finding so far is DCA's dip-buy feature — see
below — which is already shipped as the default, not a new change.

- **trend_momentum + ADX(14) entry floor: second "genuinely new signal
  design" tried (Run 11) — 2-window pass, 3-window fail, closes as regime
  luck, not an edge.** Sibling idea to Run 10's grid+ADX gate, this time
  *requiring* ADX(14) >= a floor at entry (trend-strength confirmation, the
  opposite direction from grid's ceiling-gate) on top of the shipped-default
  1h EMA20/50+RSI+MACD combo (`research/experiments/adx_trend_momentum_gate.py`,
  research-only, not merged). Swept floor ∈ {none,15,20,25,30} on train
  2026-03-18→2026-06-16 / test 2026-06-16→2026-08-15. **floor=20 looked like
  a real candidate at first**: train PF 1.124/73 trades, test PF 1.176/35
  trades — both windows clear PF>1, both clear the 30-trade floor, PF and
  win% (34%→43%) move together rather than the usual train-fails/OOS-lucky
  shape. Per the standing precedent (mean_reversion@1h needed a 3rd window
  before Run 3 could reject it), ran a 3rd non-overlapping window
  (2025-12-15→2026-03-15, 240-150d ago) before calling it a candidate: **PF
  0.706/56 trades — clearly negative**, and per-symbol test breakdown is
  paper-thin under the encouraging aggregate (1-6 trades/symbol, 0% win on
  2 symbols). **Verdict: noise — 1 of 3 non-overlapping windows passing is
  not an edge, closes this exact regime-luck signature a second time.**
  floor=15 monotonically improves over baseline but both windows still <1;
  floor=25/30 are textbook small-sample noise (10 and 3 test trades). The
  ADX(14) implementation (shared with Run 10) is reusable for future work;
  **both flagged ADX applications (grid ceiling-gate, trend_momentum
  entry-floor) are now closed — a genuinely different indicator family is
  needed to reopen this line, not more ADX threshold tuning.**
- **grid + ADX trend-strength gate: first "genuinely new signal design"
  tried (Run 10) — clean negative result, does not reopen the family.**
  Implemented ADX(14) (Wilder) in a standalone research script
  (`research/experiments/adx_grid_gate.py`, not merged into production —
  no code shipped) and gated new grid buys off whenever ADX(14) >= a
  threshold (30/25/20/15 tested), leaving the existing stop_outside_range/
  flatten_on_stop safety mechanism untouched, at 1h on the two least-bad
  `flatten_on_stop=True` configs from Run 8 (range=10%/levels=13 and
  range=6%/levels=13). On this run's window (train 2026-03-18..2026-06-16,
  test 2026-06-16..2026-08-15 — notably worse for grid than Run 2/8's
  window even at threshold=None: baseline train/test PF 0.285/0.285 and
  0.236/0.481 vs Run 2's 1.506/0.655 and 1.169/0.647 for the identical
  params, underscoring how regime-dependent this strategy's headline
  numbers are), **every ADX threshold made results flat or modestly worse
  than the no-gate baseline, never better** — e.g. range=10 baseline train
  PF 0.285 vs gated 0.194-0.214 at every threshold; range=6 baseline train
  PF 0.236 vs gated 0.072-0.230. Mechanism: with the wide 6-10% auto-range
  already in place, grid's losses come from ordinary in-range chop and the
  eventual out-of-range exit, not specifically high-ADX periods — by the
  time ADX(14) actually elevates, price has typically already left the
  range and `stop_outside_range` has already fired, so the ADX gate is
  largely redundant with a mechanism that's already there and just prunes
  trade count for no PF benefit. **Closes the grid-ADX idea as tested; the
  ADX indicator function is reusable (kept in the research script) for a
  future trend_momentum-confirmation test, which remains open.**
- **mean_reversion @ 5m: first pass done (Run 9) — cleanest, most decisive
  failure of any mean_reversion TF tested.** 24-combo grid (bb_std x
  rsi_oversold x exit_at x trend_ema, same shape as 1h/4h), 150d train /
  60d test, all real samples (5m gives plenty of candles even at 90 days).
  All `trend_ema=0` combos have real train samples (11-274 trades) and
  **every one has train PF < 1** (best 0.748, `bb_std=3.0, rsi_os=25,
  exit=upper`) — a clean train-screen rejection with no small-sample
  ambiguity, unlike 1h/4h where the starved `trend_ema=200` half produced
  a few misleadingly-high-PF tiny samples. OOS-validated the top 3
  train-ranked real-sample combos anyway: best got PF 1.064/171 trades —
  doesn't even clear the 1.1 anti-noise bar despite a real sample — the
  other two stayed negative both windows (PF 0.836/0.745 OOS). **Shipped
  default reference is the most decisive default-failure yet**: train PF
  0.181/126 trades, test PF 0.347/146 trades — negative in BOTH windows,
  no train-fails/OOS-clears regime-luck story available at all (unlike the
  ambiguous pattern seen for the same default params at 1h and 4h). Fee
  drag likely plays a bigger role at 5m than 15m/1h/4h (more candles per
  day, more RSI/BB fire opportunities) without 1m's catastrophic
  over-trading — a genuine intermediate point on the TF spectrum, and it's
  unambiguously a loser. mean_reversion is now grid-searched with train/
  test rigor at 5m/15m/1h/4h — no edge at any TF from 5m to 4h; only 1m
  (catastrophic) and 1d (untested, low priority — even fewer candles per
  window than 4h, likely to hit the same starvation issues as
  `trend_ema=200` did at 4h) remain unexplored for this family.
- **grid: no edge at ANY grid-searched TF — family now closed across
  15m/1h/4h.** Fully grid-searched with train/test rigor at 1h (Run 2, 8
  combos, best train PF 1.51 collapses to OOS PF 0.66) and now 4h (Run 8,
  8 combos + shipped-default reference). At 4h, properly risk-managed
  (`flatten_on_stop=True`) combos fail even the train screen outright (PF
  0.31–0.69, all <1) and stay negative OOS (PF 0.35–0.83) — an even
  cleaner failure than 1h's train-passes/OOS-collapses pattern, no
  regime-luck ambiguity. Separately, Run 8 found and documented a **PF
  accounting artifact for `flatten_on_stop=False`**: a grid sell only ever
  fires above its paired buy, so every *closed* trade is a win by
  construction (100% win rate, trade-PF literally undefined/infinite)
  regardless of whether the strategy is actually profitable — losses on
  held-but-never-flattened inventory are invisible to trade-level PF and
  only show up in account-level mark-to-market return. That real return
  flip-flopped sign between windows for all 4 `flatten=False` combos and
  the shipped default (train −0.68pp to −1.01pp vs test +0.16pp to
  +0.39pp) — the same train-loses/test-gains flip-flop signature already
  seen elsewhere in this research, confirming (not contradicting) the
  standing conclusion that unflattened grid inventory is just unhedged
  directional spot exposure wearing a grid-strategy costume. **Do not
  trust `flatten_on_stop=False` trade-PF as a metric in any future grid
  run — always read account-level return instead.** Confirms the founding
  distilled learning (grid is a directional bet in disguise) at a third
  timeframe; don't re-grid this strategy without first building a
  range-detection filter (ADX/volatility gate), which no run has
  attempted yet.
- **trend_momentum: no edge at ANY grid-searched TF — family now closed
  across 15m/1h/4h.** Fully grid-searched with train/test rigor at 4h
  (Run 1, 18 combos, best train PF 0.79, all fail), 1h (Run 3, 18 combos,
  best train PF 0.90, all fail; OOS on the best-train combo confirms PF
  0.463/105 trades), and now 15m (Run 7, 12 combos, best train PF 0.993 —
  literally the shipped default — still <1; OOS confirms PF 0.325/74
  trades, real sample, clearly negative). Unlike 1h/4h's default-reference
  finding (train fails, OOS looks lucky = regime ambiguity), 15m's default
  fails BOTH windows consistently — the cleanest non-edge result yet for
  this family, no regime-luck story available. Faster EMA pairs (9/21,
  12/26) are strictly worse than 20/50 at 15m (train PF 0.08–0.22 vs
  0.99), and dropping MACD confirmation is strictly worse than requiring
  it. Do not re-grid trend_momentum at 15m/1h/4h without a materially
  different signal design (current ema-cross+RSI+MACD family is exhausted
  at every TF tested; 1m is catastrophic for any strategy, never tested
  here nor worth testing).
- **mean_reversion @ 4h: first pass done (Run 6), no edge, and the TF is
  now too short-window to say more.** 24-combo grid (bb_std x
  rsi_oversold x exit_at x trend_ema, 90-day train / 60-day test — only
  540 / 360 4h-candles respectively). All `trend_ema=200` combos (half
  the grid) produced **zero train trades across all 8 symbols** — at 4h
  the 200-EMA warmup (≈33 days) plus the rarity of "oversold dip AND
  above a slow trend EMA" simultaneously never fired in a 90-day window;
  worse starvation than the 3-6 trades trend_ema=200 got at 1h (Run 2),
  confirming trend_ema=200 needs far more history than any window this
  research uses to be testable at all — don't retry it at 4h without a
  multi-year window. Best real-sample train combo (bb_std=2.5,
  rsi_oversold=30, exit=middle, trend_ema=0, train PF 1.143/35 trades)
  hit OOS PF 1.241 but only 14 trades — clears the PF bar, misses the
  30-trade floor by a wide margin (60-day test window is just too short
  at 4h to accumulate a trustworthy sample even when train showed a weak
  edge). Shipped-default reference repeated the same train-fails/OOS-
  clears pattern already debunked at 1h (train PF 0.663, OOS PF
  1.786/27 trades) — not re-opened, 1h's 3-window check already closed
  this question for the same params.
- **mean_reversion @ 1h default params: 3-window check now CLOSES this
  question — it's regime luck, not an edge.** Run 2 found the shipped
  defaults (bb_std=2.0, rsi_oversold=30, exit_at=middle, trend_ema=0) at
  OOS PF 1.903/120 trades on the 60-0d window despite train PF 0.472, and
  flagged it as needing a 3rd window before trusting either way. Run 3
  tested a 3rd, older, non-overlapping window (240-150d ago): PF 0.441/136
  trades, all 8 symbols individually negative. 2 of 3 windows negative for
  the identical untouched param set — confirms this is not a stable edge,
  just one lucky 60-day slice. No further action; matches the broader
  no-edge finding, don't re-test this specific combo again.

- **1m: catastrophic, any strategy.** −34% to −42%, PF 0.01–0.09. Over-trades
  (~200+ trades/coin), fee drag (0.15% round-trip) dominates. Never retest 1m.
- **Timeframe generally: higher TF = less fee drag, not more edge.** Return
  ordering 1m ≪ 15m < 1h ≈ 4h, but none of mean_reversion/trend_momentum have
  shown a *stable* in-sample (train) edge at any TF 15m–4h — see below.
- **mean_reversion @ 15m:** default params ~breakeven OOS (PF 1.02). A
  16-combo grid's best OOS survivor (bb_std=2.5, rsi_os=30, exit=upper,
  trend_ema=0) hit OOS PF 1.24/231 trades but had **train PF 0.65** — didn't
  show an edge in-sample, just got lucky OOS. Rejected as noise (Run 1).
- **mean_reversion @ 1h:** 24-combo grid (bb_std×rsi_oversold×exit_at×
  trend_ema) — **22/24 combos have train PF < 1**; no bb_std/rsi setting
  shows an in-sample edge at this TF. The 2 combos with train PF > 1 only
  had 3–6 train trades (trend_ema=200 filter starves entries at 1h) — too
  small to trust, and OOS confirmed (0–4 trades). Shipped defaults happen to
  score OOS PF 1.9/120 trades on the current test window despite **train PF
  0.472** — flagged as regime-dependent, not adopted, needs a 3rd window
  before it means anything (Run 2).
- **trend_momentum @ 4h:** 18-combo grid (ema pairs × rsi_buy_min ×
  require_macd) — **every combo had train PF < 1** (best 0.79) on a choppy
  train window; no in-sample edge to even validate OOS (Run 1).
- **trend_momentum @ 1h:** grid-searched with train/test rigor in Run 3
  (18 combos: ema pairs x rsi_buy_min x require_macd) — every combo train
  PF < 1 (best 0.90); OOS on the best-train combo confirms PF 0.463/105
  trades. See summary bullet above; no edge, don't re-test this family.
- **grid strategy:** profits from range oscillation in-sample but is a
  **directional bet in disguise** — bag-holds through downtrends. Confirmed
  three times now: informally at 15m/90d (−20% net, founding session),
  rigorously at 1h with train/test split (best train PF 1.51 → OOS PF 0.66,
  Run 2), and at 4h (Run 8) — see full summary bullet above. Family now
  closed at 15m/1h/4h; do not grid-search this strategy again without first
  finding a *range-detection* filter (e.g. only run it when ADX/volatility
  says "ranging") — parameter tuning alone (range width, level count,
  flatten-on-stop) cannot fix a strategy whose core risk is directional
  exposure.
- **mean_reversion trend_ema filter (opt-in, default off):** buy-the-dip
  only in uptrends. Near-breakeven at 1h with trend_ema=200 in the founding
  session (11 trades) and confirmed still tiny-sample (3–6 trades) in Run 2's
  grid. Kept in the codebase as a principled downside-reduction knob, not a
  proven edge. Do not flip its default on without a large-sample OOS pass.
- **DCA strategy: methodology now defined and first pass run (Run 4).**
  `run_dca_backtest` produces zero round-trip `trades`, so the PF/trade-count
  bar doesn't apply. New metric: capital-normalized ROI
  (`unrealized_pnl/invested %`) of a variant vs. a flat fixed-schedule
  baseline, same total-invested-dollar basis (raw "avg_cost % below last
  close" is misleading here — a dip-buy variant deploys *more* total
  capital, so a cheaper unit cost doesn't by itself mean a better dollar
  outcome; always normalize by invested $ before comparing DCA variants).
  Finding: the **shipped default dip-buy feature** (`dip_enabled=True,
  dip_threshold_pct=5.0, dip_multiplier=1.5`) beats a flat schedule on ROI
  in 2 of 3 non-overlapping windows (choppy/declining regimes: +0.26pp to
  +0.61pp) and is ~neutral, not negative, in a trending-up window (-0.07pp,
  noise-level) — mechanically explicable (extra buys only land at
  locally-lower prices when a 24h dip actually occurs, so the feature is a
  no-op, not a loss, when the market doesn't dip) and consistent with why
  it's already the default. A more aggressive variant (3%/2.5×) shows a
  stronger version of the same pattern but only wins 4/8 symbols (noise
  level) in the trending-up window and requires 13–30% more deployed
  capital — not adopted; no clean win in a trending-up regime plus a real
  capital/exposure cost is enough to reject it. **No code/param change —
  validates the existing default, doesn't argue for changing it.**
- **Live real money (pre-research):** 16 trades, −$0.29 net, ~70% of loss
  was fees — empirically confirms the negative-edge finding from backtests.
  Stopped; testnet + this automated research only from here on.
- **DCA schedule `interval` (hourly/daily/weekly): now swept (Run 5).**
  Hourly vs shipped daily: noise (<=0.11pp ROI delta in any window, sign
  flips between windows) — makes sense, hourly just re-slices the same
  buying period daily already averages over, so cost basis barely moves;
  also a real live-trading cost (24x more orders/window) for zero benefit.
  Weekly vs daily: **reject, don't recommend** — systematically worse in
  ALL 3 windows (older -1.10pp/0% win, train -0.29pp/31% win, test
  -0.61pp/25% win), unlike dip-buying's "helps in declines, neutral in
  uptrends" pattern weekly has no offsetting upside anywhere. Mechanism:
  only ~10-14 buys/window on one fixed weekday samples a far less
  representative slice of the price path than daily's ~90. **Validates
  keeping `interval=daily` as the default; no code change.**

---

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

## 2026-08-12 — Run 5

**Self-correction check:** reviewed commits since Run 4 — only `a4798a2`
(auto-deploy: poll health for ~40s instead of one-shot, fixes a startup
race). Deploy-tooling only; doesn't touch any strategy default, risk
config, or backtest code. Nothing strategy-affecting to revert.

**Region — DCA `interval` sweep (hourly/daily/weekly), first-ever variation
of this param** (per Run 4's flagged next step (c); prior DCA runs only
varied `dip_*` params, always on the `daily` schedule). Same 3-window
methodology as Run 4 (capital-normalized ROI = `unrealized_pnl/invested %`,
since `run_dca_backtest` has no round-trip trades): older
2025-12-15→2026-03-14, train 2026-03-14→2026-06-12, test
2026-06-12→2026-08-11. Klines fetched once per (symbol, window) at 1h
granularity — schedule interval is independent of candle granularity, so
all three schedule variants reuse the same cached candles. Ran both `flat`
(dip disabled) and shipped `dip_default` on each interval × window ×
symbol = 144 backtests total. `quote_amount` scaled per interval
(hourly=$1, daily=$15, weekly=$105) to keep a roughly similar deploy rate;
ROI is capital-normalized so this doesn't bias the comparison.

**Hourly vs daily:** avg ROI delta +0.11pp (older, 87.5% symbol-win),
+0.06pp (train, 93.8% win), **-0.03pp (test, 43.8% win — sign flips)**.
Magnitude is trivial everywhere (≤0.11pp — cents on $100) and the sign
isn't even stable across windows. Mechanically expected: hourly just
finely re-slices the same buying period daily already covers, so the
average purchase price barely moves — no reason to expect an edge, and
none found. Also carries a real, uncaptured-by-ROI operational cost: 2160
buy events per symbol per 90-day window vs 90 for daily — 24x more live
orders per dollar deployed (minimum-notional issues, API/exchange load)
for zero measurable benefit. **Verdict: noise, reject.**

**Weekly vs daily:** avg ROI delta **-1.10pp (older, 0/16 = 0% win)**,
**-0.29pp (train, 31% win)**, **-0.61pp (test, 25% win)** — worse in
**every one of the 3 independent windows**, never close to a majority
win, and even its best window (train) is still a net loss vs daily, not a
wash. This is qualitatively different from the dip-buying pattern (helps
in declines, neutral in uptrends, Run 4) — weekly shows no offsetting
upside in any regime tested. Mechanism: only ~10-14 buys per 90-day window
on a single fixed weekday/time samples a far less representative slice of
the price path than daily's ~90 buys, so each lump-sum buy carries more
single-draw timing risk — and that risk realized negative in all 3
non-overlapping windows, not just down-trending ones. **Verdict: reject —
do not recommend weekly as a DCA schedule.**

**$100 / $1000 translation (test window, most decision-relevant):**
hourly vs daily: -$0.03/-$0.30 (noise-level, don't act on the sign).
Weekly vs daily: -$0.61/-$6.08 — small in absolute terms but consistently
negative across all 3 windows with no compensating upside anywhere.

**Verdict: no promising candidate this run.** No code or default-param
change (the finding validates the existing shipped default, `interval=
daily`, over both alternatives — hourly is a no-op with extra operational
cost, weekly is a real net negative). Nothing to revert (no
strategy-affecting commits since Run 4).

**Next run should rotate to:** DCA's interval/dip axes are now both
explored (this run + Run 4) — candle-strategy families (mean_reversion,
trend_momentum, grid) remain exhausted at 15m/1h/4h. Worth trying next:
(a) a 5m timeframe sweep for mean_reversion/trend_momentum (still
untested, low priority given 1m's catastrophic result); (b) DCA
`time_utc` sensitivity (does the specific hour-of-day for a daily buy
matter, given weekly's day-of-week/lump-size finding this run suggests
schedule *granularity* matters more than *anchor point*, worth a
quick confirmatory check); (c) re-testing `dip_default` vs flat on a
genuinely different trending-up window if one can be found, per Run 4's
still-open flag (only tested in one trending-up window so far).

_No CANDIDATE FOUND this run._

---

## 2026-08-12 — Run 4

**Self-correction check:** reviewed commits since Run 3 — only `765defe`
(scanner: exclude newer USD stablecoins from the coin scanner). Doesn't
touch the fixed 8-symbol research universe, any strategy default, or any
backtest code. Nothing strategy-affecting to revert.

**Region — DCA strategy, first-ever pass, new evaluation methodology
(per Run 3's flagged next step).** `run_dca_backtest` accumulates inventory
and returns zero round-trip `trades`, so the PF>1.1/≥30-trades bar used for
candle strategies doesn't apply. Defined a DCA-specific bar: compare
**capital-normalized ROI** (`unrealized_pnl / invested`, in %) of a variant
against a flat fixed-schedule baseline (same `interval=daily,
quote_amount=$15`, `dip_enabled=False`) — NOT raw avg-cost-vs-last-close,
which is misleading here since dip-buy variants deploy *more* total
capital than the flat baseline (extra $ on qualifying dip days), so a
lower unit cost doesn't automatically mean a better dollar outcome without
normalizing by $ invested first.

Tested 3 variants (`flat` baseline, `dip_default` = shipped default
`dip_threshold_pct=5.0/dip_multiplier=1.5`, `dip_aggressive` =
`3.0/2.5`) × 8 symbols × 3 non-overlapping windows (train 2026-03-14→
2026-06-12, test 2026-06-12→2026-08-11, plus an older window
2025-12-15→2026-03-14 — same anchors as the candle-strategy research) =
72 backtests, hourly candles (for the 24h dip lookback), fees 7.5bps /
slippage 4bps.

**`dip_default` (shipped default) vs flat:** ROI beats flat on 6/8 symbols
in train (+0.26pp avg), 8/8 in the older window (+0.61pp avg), but only
2/8 in the test window (-0.07pp avg, noise-level, not a real loss).
**Verdict: mixed across windows, doesn't clear a majority-of-symbols win
in every window** — so not an unconditional edge by this research's own
anti-noise standard. But the mechanism is explicable, not curve-fit: extra
buys land at locally-lower prices only when a 24h dip actually happens, so
the feature is a no-op (not a loss) in a trending-up market and a real
help in choppy/declining ones — consistent with 2/3 windows meaningfully
positive and the 3rd being ~flat rather than negative. **This is already
the shipped default; the run validates keeping it, doesn't argue for
changing it either direction.**

**`dip_aggressive` (3%/2.5×) vs shipped default:** beats it on ROI in the
older window (8/8, +1.72pp) and train (7/8, +0.55pp), but only 4/8 (50%,
+0.09pp, noise) in the trending-up test window — not a clean win in every
regime. It also deploys **13–30% more total capital** than the default
across symbols (lower threshold triggers more often), a real
capital/liquidity requirement and larger concentration of exposure into
still-declining assets that isn't captured by the ROI-% comparison alone.
**Verdict: reject** — no clean win in a trending-up window, plus a real
added capital/exposure cost, isn't enough to justify shipping a more
aggressive default.

**$100 / $1000 translation:** `dip_default` vs flat: -$0.07/-$0.70 (test
window, the regime that matters most for "is this still working now"),
+$0.26/+$2.63 (train window), on the ROI-normalized basis. `dip_aggressive`
vs default: +$0.02/+$0.24 (test window, noise-level). No candidate found —
smallest of the three verdicts is "keep the untouched default."

**Verdict: no promising candidate this run.** No code or default-param
changes made (the one interesting finding — dip-buy helps and never
meaningfully hurts — describes the *existing* shipped default, not a
change). Nothing to revert (no strategy-affecting commits since Run 3).

**Next run should rotate to:** a genuinely new region — candle-strategy
families (mean_reversion, trend_momentum, grid) are exhausted at
15m/1h/4h; DCA now has a working methodology and first-pass result. Worth
trying: (a) a 5m timeframe sweep for mean_reversion/trend_momentum
(untested, low priority given 1m's catastrophic result, but 15m/1h/4h are
all exhausted); (b) re-testing `dip_default` vs flat on a 4th window if a
genuinely trending-up historical window can be found deliberately (the
test window here was the only trending-up one of the three tried, so its
verdict rests on a single window); (c) DCA `interval` (hourly vs
daily vs weekly) has never been varied — only `dip_*` params were, this
run assumed daily throughout.

_No CANDIDATE FOUND this run._

---

## 2026-08-11 — Run 3

**Self-correction check:** reviewed commits since Run 2 — none landed
(`abec798` was Run 2's own log commit). Nothing strategy-affecting to
revert.

**Region A — trend_momentum @ 1h, all 8 symbols, train/test grid search
(closes the gap flagged after Runs 1-2).** Same anchors as prior runs
(train 2026-03-14→2026-06-12, test 2026-06-12→2026-08-11). Grid:
`ema_fast/slow` ∈ {(10,30),(20,50),(12,26)} × `rsi_buy_min` ∈ {45,50,55} ×
`require_macd` ∈ {True,False} (18 combos, same grid shape as the Run 1
4h search).

Train screen: **all 18 combos had train PF < 1** (range 0.55–0.90; best
was ema_fast=10, ema_slow=30, rsi_buy_min=45/50 [identical result — no
train trades fell between RSI 45 and 50], require_macd=True, PF 0.901,
122 trades). OOS on the best-train combo: PF 0.463, 105 trades (real
sample, well over the 30-trade floor), ret -0.113%. **Verdict: FAIL.**
trend_momentum now has full train/test grid coverage at both 4h (Run 1)
and 1h (this run) — no in-sample edge at either timeframe with this
ema-cross+RSI+MACD signal family. Don't re-grid this strategy at these
TFs without a different signal design.

**Region B — mean_reversion @ 1h shipped-default params, THIRD
non-overlapping window (follow-up to Run 2's explicit flag).** Run 2 found
the shipped defaults (`bb_std=2.0, rsi_oversold=30, exit_at=middle,
trend_ema=0`) scored OOS PF 1.903/120 trades on the 60-0d test window
despite train PF 0.472 on the 150-60d window — flagged as regime-dependent
and *not adopted*, pending a third window. This run tested the identical,
untouched param set on window 2025-12-15→2026-03-14 (240-150d ago, doesn't
overlap either prior window): **PF 0.441, 136 trades, -$187.93 aggregate,
every one of the 8 symbols individually negative** (PF 0.20–0.85, per
symbol trade counts 14–20). **Verdict: FAIL.** 2 of 3 windows now negative
for this exact param set — the Run 2 result was regime luck on one 60-day
slice, not a stable edge. This closes the open question from Run 2: no
code/param change was made either time (it's already what ships), and this
result doesn't argue for changing it — it argues no config in this family
is worth shipping over the current default.

**$100 / $1000 translation:** both regions this run are net negative OOS.
Region A: -$0.11/-$1.13 over 60d on the best-train combo. Region B:
-$0.23/-$2.35 over the 90-day third window. No positive candidate.

**Verdict: no promising candidate this run.** No code or default-param
changes made. Nothing to revert (no strategy-affecting commits since Run 2).

**Next run should rotate to:** define a DCA-specific evaluation
methodology first (avg_cost vs. buy-hold baseline across >=2 windows —
the existing PF/trade-count bar doesn't apply, `run_dca_backtest` produces
no round-trip trades), then run it. Standard candle-strategy families
(mean_reversion, trend_momentum) are now exhausted at 15m/1h/4h and grid
at 1h — DCA and possibly a 5m timeframe sweep (untested, low priority
given 1m's catastrophic result) are the remaining unexplored regions.

_No CANDIDATE FOUND this run._

---

## 2026-08-11 — Run 2

**Self-correction check:** no strategy-affecting commits landed since Run 1
(`5c23fd9` mean_reversion trend-filter is still the most recent, already
re-validated last run; still opt-in/off by default). Nothing to revert.

**Region A — mean_reversion @ 1h, all 8 symbols.** Same train/test anchors as
Run 1 (train 2026-03-14→2026-06-12, test 2026-06-12→2026-08-11). Grid:
`bb_std` ∈ {2.0,2.5,3.0} × `rsi_oversold` ∈ {25,30} × `exit_at` ∈
{middle,upper} × `trend_ema` ∈ {0,200} (24 combos).

Train screen: 22/24 combos had train PF < 1 (`trend_ema=0` variants ranged
0.05–0.60 across bb_std/rsi settings — 1h mean_reversion is not profitable
in-sample at any bb_std/rsi setting tested). The only two combos with train
PF > 1 both used `trend_ema=200`, which at 1h restricts entries to 3–6
train trades total across all 8 symbols — too few to mean anything. OOS on
the top 3: PF 0.0/0/trades, PF 1.105/4 trades, PF 0.961/4 trades — none
clear the 30-trade floor. **Verdict: FAIL**, no candidate from the grid.

Notable side-finding while running the reference baseline: the **shipped
default params** (`bb_std=2.0, rsi_oversold=30, exit_at=middle,
trend_ema=0` — not selected by this search, just the repo default) scored
OOS PF **1.903, 120 trades, +$118.36 on $80k notional (+0.148%, ~$0.15 per
$100 / $1.48 per $1000 over 60d)** on the same held-out window — numerically
clears the anti-noise bar (real sample size this time, not small-N luck).
**Not treated as a candidate or acted on**, because this identical param
combo scored **train PF 0.472** in the grid above — it would have been
rejected by the very screen used to pick candidates. It only "works" on
this specific 60-day slice; that is the signature of regime dependence, not
a discovered edge. No code or param change — it's already what ships.
Logged so a future run can re-check it against a **third, non-overlapping
window**; if it holds up there too it becomes more credible, not less.

**Region B — grid strategy @ 1h, all 8 symbols, proper train/test (first
time — prior grid tests were single-window, no split).** Grid:
`auto_range_pct` ∈ {6,10} × `levels` ∈ {8,13} × `flatten_on_stop` ∈
{True,False} (8 combos, `stop_outside_range=True` always).

Every train-ranked config collapsed OOS: best train PF 1.506 (190 trades,
+$130) → OOS PF 0.655 (140 trades, **-$147**); 2nd 1.421→0.639 (-$85); 3rd
1.169→0.647 (-$109). **Verdict: FAIL** across the board — this directly
confirms, with a rigorous split this time, the founding session's informal
finding that grid's in-sample oscillation profit is a directional/regime
bet, not a generalizing edge. `flatten_on_stop=False` variants weren't even
worth OOS-checking: all had 0 gross losses recorded in-sample terms that
collapse to `pf=None`/near-zero once a losing streak actually closes a lot
(inventory accumulates as unrealized loss without flattening, masking risk
in-sample).

**$100 / $1000 translation:** best OOS result across both regions this run
is the default-baseline observation above (+$0.15 / +$1.48 over 60d, not
acted on). Every actively-searched grid combo (both regions) was flat or
negative OOS.

**Verdict: no promising candidate this run.** No code or default-param
changes made.

**Next run should rotate to:** trend_momentum @ 1h with the same
train/test grid-search rigor (only ever tested as a single default config
at 1h so far, not searched); or the DCA strategy (fully untested so far in
this research). Also worth a rolling 3rd-window re-check of the mean_reversion
1h default-params side-finding above before it's fully dismissed.

_No CANDIDATE FOUND this run._

---

## 2026-08-11 — Run 1

**Self-correction check:** reviewed the most recent strategy-affecting
commit, `5c23fd9` (mean_reversion optional trend-filter EMA). It ships
`trend_ema=0` (off) by default in `param_specs()` — it's an opt-in knob,
not a default-behavior change, so there is nothing live to re-validate or
revert. No other recent commit changes a strategy default. No reverts this
run.

**Region A — trend_momentum @ 4h, all 8 symbols**
Train window 2026-03-14→2026-06-12 (150-60d ago), test window
2026-06-12→2026-08-11 (60-0d ago). Grid: `ema_fast/slow` ∈
{(10,30),(20,50),(12,26)} × `rsi_buy_min` ∈ {45,50,55} × `require_macd` ∈
{True,False} (18 combos), aggregated across all 8 symbols per combo.

Result: **every single combo had train profit_factor < 1** (best was 0.79,
worst 0.40). The train window was choppy/ranging for this strategy on this
timeframe — there was no in-sample edge to even validate OOS. Verdict:
**FAIL, not promising.** Did not proceed to OOS (nothing passed the train
screen). Default trend_momentum params on the same OOS window: PF 1.12,
24 trades — under the 30-trade floor, inconclusive either way.

**Region B — mean_reversion @ 15m, all 8 symbols**
Same train/test windows. Grid: `bb_std` ∈ {2.0,2.5} × `rsi_oversold` ∈
{25,30} × `exit_at` ∈ {middle,upper} × `trend_ema` ∈ {0,200} (16 combos).

Top train-ranked candidate (bb_std=2.0, rsi_oversold=30, exit_at=middle,
trend_ema=200, train PF 0.88, 31 train trades) **failed OOS**: PF 0.53,
21 trades, -$8.40 aggregate P&L.

Second-ranked candidate (bb_std=2.5, rsi_oversold=30, exit_at=upper,
trend_ema=0) technically **clears the numeric bar**: OOS PF 1.24, 231
trades, 59.3% win rate, +$78.89 aggregate P&L across 8×$10,000 sim
accounts over the 60-day test window. Per-symbol OOS PF: BTC 1.23, ETH
0.92, SOL 1.41, BNB 1.51, XRP 0.72, LINK 2.09, DOGE 1.62, ADA 0.93 — 5/8
symbols positive, reasonably broad-based rather than one symbol carrying
the whole result.

**Why I'm not calling this a candidate despite passing the numeric bar:**
1. Its own **train-window PF was 0.65** — this parameter set never showed
   an edge in-sample. It was the least-bad of 16 combos that were mostly
   in-sample losers, then got lucky OOS. That's the signature of noise
   surviving a screen, not a real effect strengthening out-of-sample.
2. **Economic magnitude is negligible**: +$78.89 on $80,000 deployed
   notional over 60 days ≈ 0.10% (roughly 0.6% annualized) — smaller than
   likely model/venue slippage error, and default (untuned) mean_reversion
   params scored almost the same on the same OOS window (PF 1.02, 336
   trades) — i.e. the "improvement" from this whole 16-combo search over
   just using the shipped defaults is within noise.
3. 16-combo grid search with only the top-3 validated OOS is enough
   multiple-comparison risk to produce a >1.1 PF by chance alone.

**Verdict: no promising candidate this run.** No code or default-param
changes made. Nothing to revert from prior runs.

**$100 / $1000 account translation (for the OOS-passing but rejected
candidate, purely illustrative — not deployed):** ~$0.10 profit per $100,
~$1.00 per $1000, over 60 days, before accounting for real-world execution
slippage beyond the simulated 4bps. Not worth the operational risk of
shipping a parameter change for.

**Next run should rotate to:** mean_reversion or trend_momentum @ 1h, and
the `grid` strategy (untested so far), on a different train/test anchor
if enough time has passed.

_No CANDIDATE FOUND this run — proving nothing works is a valid result._

---

## 2026-08-10 — Prior session findings (human-seeded, for the agent's memory)

Configs already tested in the founding live+backtest session — **do not re-test these**:
- **1m any strategy**: catastrophic (−34% to −42%, PF 0.01–0.09) — fee drag from over-trading. Avoid 1m entirely.
- **Timeframe sweep** (mean_reversion/trend_momentum): 1m −34%/−42%, 15m −8%/−22%, 1h −5.8%/−3.6%, 4h −3.9%/−5.4%. Higher TF cuts fee drag hugely but none reach profit. 1h is the least-bad base.
- **mean_reversion trend_ema=200 @ 1h**: near-breakeven (−0.8%) but tiny sample (~11 trades) — filter adopted as principled downside reduction, not proven edge.
- **grid ±12%/13 levels @ 15m**: oscillation engine profits per-cycle but bag-holds in downtrends → −20% net over 90d (−9.5% even with range-exit stop). Directional bet, not signal edge; also needs $40+ capital.
- **Live real-money** (1m volatile scanner): 16 trades, −$0.29 net, ~70% of loss was fees. Empirically confirmed negative edge. Stopped; moved to testnet + this automated research.

Structured versions of these in `research/decisions.jsonl`. Overarching prior: no robust
edge found; simple RSI/BB/EMA signals appear over-arbitraged, fees turn ~breakeven negative.
