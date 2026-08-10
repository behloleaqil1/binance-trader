# Binance Algorithmic Trading Bot + Dashboard

A self-hosted spot trading system: a Python (FastAPI) engine that trades on
Binance via REST + WebSocket, and a React dashboard to monitor and control it.

> **Risk disclaimer — read first.** Trading cryptocurrencies involves
> substantial risk of loss. This software can lose money on its own, quickly,
> and without asking again. Backtest results are **simulated historical
> performance and are not indicative of future results**. Nothing in this
> project is financial advice. Start on the testnet, stay small when live.

---

## Contents

1. [What's inside](#whats-inside)
2. [Security notes for THIS machine](#security-notes-for-this-machine)
3. [Setup](#setup)
4. [Creating restricted Binance API keys](#creating-restricted-binance-api-keys)
5. [Running](#running)
6. [The dashboard](#the-dashboard)
7. [Strategies](#strategies)
8. [The risk engine](#the-risk-engine)
9. [Backtesting](#backtesting)
10. [Alerting](#alerting)
11. [Testnet quirks](#testnet-quirks)
12. [Go-live checklist](#go-live-checklist)
13. [Troubleshooting](#troubleshooting)

---

## What's inside

```
binance-trader/
├── run.sh                  # dev runner (venv + uvicorn + vite)
├── docker-compose.yml      # containerized run (backend + nginx frontend)
├── .env.example            # copy to .env; TESTNET=true is the default
├── backend/
│   ├── app/
│   │   ├── core/           # engine, Binance gateway (retries, rate limits,
│   │   │                   #   clock sync, WS reconnect), order manager (OCO
│   │   │                   #   protection, trailing, reconciliation), portfolio
│   │   ├── risk/           # the risk engine — every order passes through it
│   │   ├── strategies/     # trend/momentum, mean reversion, grid, DCA + scanner
│   │   ├── backtest/       # public-data downloader + simulator + metrics
│   │   ├── db/             # SQLite (WAL) models: orders, trades, positions,
│   │   │                   #   equity history, signals, configs, bot state
│   │   ├── api/            # REST + /ws/stream for the dashboard
│   │   └── alerts/         # optional Telegram / webhook notifier
│   └── tests/              # 75 unit tests (risk, strategies, indicators, backtest)
└── frontend/               # React + TypeScript + Vite dashboard (dark theme)
```

Key design decisions:

- **The risk engine is a hard gate.** Strategies only *propose*; the risk
  engine sizes, approves, or rejects against equity-% sizing, daily-loss halt,
  drawdown kill switch, position/exposure caps, and Binance lot/notional
  filters. Kill-switch state is persisted in SQLite — restarts cannot
  resurrect trading.
- **Protection lives on the exchange.** Every entry immediately gets an OCO
  (take-profit + stop-loss) on Binance, so positions stay protected even if
  the bot process dies. If OCO placement fails, the engine monitors the
  position itself and keeps retrying, and the dashboard flags it.
- **Backtests reuse the live code.** The same indicator and decision functions
  run in both paths (decisions at candle close execute next open, no
  lookahead; fees + slippage modeled; stop-first pessimism inside a candle).
- **Testnet is the default** and the only way to go live is editing `.env` by
  hand. The dashboard shows a persistent red banner in live mode.
- **Spot is long-only.** SELL signals close positions; nothing is shorted.

## Security notes for THIS machine

This repo was scaffolded on a host that suffered an **npm supply-chain attack
with a destructive wiper on 2026-08-06** (see `~/purocoach-incident-2026-08-06.md`).
Until that machine is wiped and reinstalled:

1. **Do not run `npm install` / `npx` / Docker builds of the frontend on it.**
   The backend (pip) is unaffected and fully usable.
2. The frontend ships hardened for the eventual install: exact-pinned
   dependencies plus an `.npmrc` with `ignore-scripts=true` (no install hooks —
   the incident's exact vector) and `before=2026-08-01` (all packages,
   transitive included, resolve to pre-incident versions). After the first
   clean install, commit `package-lock.json` and use `npm ci --ignore-scripts`.
3. **Do not create or store LIVE Binance API keys on a machine where attacker
   code ran.** Testnet keys (fake funds, throwaway) are fine for now; create
   live keys only from a clean device, and only after the rebuild.
4. The API binds to `127.0.0.1` by default, and every endpoint (REST and
   WebSocket) sits behind the dashboard login.

## Dashboard login

The dashboard is protected by a single username/password:

- First boot seeds the login from `AUTH_USERNAME` / `AUTH_PASSWORD` in `.env`.
  If `AUTH_PASSWORD` is empty, a **random password is generated and printed to
  the backend console once** — copy it, log in, and change it in Settings.
- Passwords are stored as PBKDF2-SHA256 hashes (600k iterations); sessions are
  bearer tokens valid 7 days, with only their SHA-256 stored server-side.
  Five failed logins lock that IP for 60 seconds.
- Change the username/password anytime from **Settings → Dashboard login**
  (other sessions are signed out on change).
- Lost the password? Stop the backend, run
  `sqlite3 backend/data/bot.db "DELETE FROM kv_configs WHERE key='auth'"`,
  set `AUTH_PASSWORD` in `.env`, and restart — the login reseeds.

## Setup

Requirements: Python 3.11+ (3.14 tested), Node 20+ (for the dashboard), or Docker.

```bash
cp .env.example .env          # then edit:
# TESTNET=true                ← leave as-is for now
# AUTH_USERNAME / AUTH_PASSWORD ← dashboard login (or let it auto-generate)
# BINANCE_API_KEY=...         ← testnet key (next section) — can also be
# BINANCE_API_SECRET=...        added later from the Settings page
```

Secrets live in `.env` (gitignored) or the local SQLite DB when set from the
UI. Keys are never logged and never returned by the API; the UI and logs show
a fingerprint like `Ab3d…9xYz` at most.

### Testnet keys (do this first)

1. Go to **https://testnet.binance.vision** and log in with GitHub.
2. "Generate HMAC-SHA256 Key" → copy the API key + secret into `.env`.
3. The testnet gives you generous fake balances automatically.

## Creating restricted Binance API keys

For **live** keys (later, from a clean device):

1. Binance → Account → **API Management** → Create API.
2. Label it (e.g. `bot-2026`), complete 2FA.
3. Edit restrictions:
   - ✅ **Enable Reading**
   - ✅ **Enable Spot & Margin Trading**
   - ❌ **Enable Withdrawals — leave OFF.** The bot never needs it; with it
     off, a leaked key cannot drain funds to another wallet.
   - ❌ Futures, margin loans: off.
4. **Restrict access to trusted IPs only** and add your bot host's static IP.
   Unrestricted keys are disabled by Binance after 90 days and are a far
   bigger blast radius — treat the IP whitelist as mandatory.
5. Store the secret only in `.env` on the bot host. Never commit it, never
   paste it into chats or issue trackers. Rotate immediately if in doubt.

## Running

### Option A — dev script (no Docker)

```bash
./run.sh
# backend → http://127.0.0.1:8000   (interactive API docs at /docs)
# dashboard → http://127.0.0.1:5173 (requires frontend/node_modules — see
#                                    security notes; backend works without it)
```

### Option B — Docker

```bash
docker compose up --build
# dashboard → http://localhost:8080 · API → http://localhost:8000/docs
```

(Not on the compromised host until it's rebuilt — the frontend image build
runs `npm install`.)

First run creates `backend/data/bot.db` (SQLite, WAL mode) with safe defaults:
all strategies **disabled**, conservative risk limits, scanner off, bot
**STOPPED**. Nothing trades until you enable a strategy and press **Start**.

## The dashboard

- **Overview** — equity + day PnL tiles, live equity curve, candlestick chart
  (EMA/Bollinger overlays, SL/TP lines of open positions), open positions,
  live signal/order/trade feed.
- **Trades** — full history with entry/exit prices, net PnL, fees, and the
  exact strategy rationale for entry and exit. CSV export.
- **Strategies** — enable/disable each strategy, edit every parameter
  (forms are generated from the backend's parameter schemas), pick trading
  pairs, opt into the momentum scanner, and read each strategy's recent
  evaluations — including *why it is not trading* (HOLD reasons).
- **Backtesting** — run configurations against real historical data, compare
  up to three equity curves, inspect per-trade reasons.
- **Risk** — edit every limit, watch live proximity meters (daily loss,
  drawdown vs kill switch, positions, per-asset exposure), review risk events,
  reset the kill switch.
- **Settings** — everything else is configurable here too: Binance API keys
  (write-only: they can be replaced but never read back), Telegram/webhook
  alerting, engine flags (auto-start, orphan-order cleanup), and the dashboard
  username/password. The one deliberate exception: the **TESTNET/LIVE switch
  stays in `.env`** — going live requires filesystem access and a restart, so
  a stolen dashboard password can never move the bot onto real funds.
- **Topbar** — TESTNET/LIVE badge, bot status, Start / Pause / Stop, and the
  **EMERGENCY STOP** button: cancels every open order immediately, optionally
  market-closes all positions. In live mode it requires typing `STOP`.

## Strategies

| Strategy | Signal logic | Notes |
|---|---|---|
| **Trend / Momentum** | Fast-EMA crosses above slow-EMA + RSI in a healthy band + MACD histogram positive → BUY. Cross-down / RSI blow-off / MACD rollover → SELL. | Long-only trend rider. |
| **Mean Reversion** | Close below lower Bollinger Band + RSI oversold → BUY. Reversion to middle (or upper) band or RSI overbought → SELL. | Overbought *without* a position is logged but not shorted (spot). |
| **Grid** | Ladder of buy limits across a price range; each fill places a paired sell one level up. | Pauses (with an alert) if price exits the range; optional flatten. Ladder persists across restarts. |
| **DCA** | Fixed-amount scheduled buys (hourly/daily/weekly), optionally upsized when the 24h change shows a dip. | Accumulation carries **no stop-loss by default** — an explicit, visible risk-config exemption; it still counts toward every exposure and drawdown limit. |
| **Momentum scanner** | Ranks USDT pairs by 24h movement (liquidity floor; leveraged tokens & stablecoins excluded); strategies can opt in to trade the top picks. | Finds **movement, not guaranteed profit** — high movers cut both ways. Scanner trades pass the identical risk gate. |

Every BUY/SELL/HOLD decision carries a human-readable rationale which is
logged, stored (BUY/SELL and risk rejections), and shown in the UI.

## The risk engine

Enforced at the engine level — a strategy signal **cannot** bypass it:

- Position sizing as % of equity (default 2%), or fixed amounts for DCA/grid,
  always quantized to Binance lot/step/notional filters.
- Hard SL (default −2%) and TP (default +4%) placed as an exchange-side OCO on
  every position; optional trailing stop that ratchets the OCO upward.
- **Max daily loss** (default 3% vs UTC-day-start equity) → halts new entries
  until the next UTC day; exits stay active.
- **Max drawdown kill switch** (default 10% vs peak equity) → cancels entry
  orders, optionally flattens, and refuses to trade until you manually reset
  it on the Risk page. Survives restarts.
- Max open positions (default 4; a grid ladder counts once per symbol),
  per-asset exposure cap (default 25%), total exposure cap (default 80%) —
  open buy orders count toward exposure, not just filled positions.
- Emergency stop cancels all orders (and optionally flattens) regardless of
  engine state.

Every check that ran is recorded on every decision (see `signals` /
`risk_events` tables and the Risk page).

**Adaptive layer (anti-martingale):** each signal strategy's last 20 trades
feed back into sizing — every 3 consecutive losses halve its position size
(floor ×0.25; one win resets), and sustained losing (6-loss streak or rolling
profit factor < 0.6) puts the strategy on **probation**: no new entries until
you re-save it. Optional, capped win-streak boost is off by default. Grid and
DCA are exempt by design; the backtester applies identical rules. Configure it
all on the Risk page.

**Full documentation:** `docs/USER-GUIDE.pdf` — a complete plain-language
guide to every strategy, the decision pipeline, all risk limits, multi-strategy
behavior, going live, and a glossary of every abbreviation.

## Backtesting

- Historical klines come from Binance's public data host (no API key), cached
  in SQLite.
- Same strategy code as live; entries execute at next-candle open with
  slippage; SL/TP checked intra-candle with stop-first pessimism; taker fees
  both sides.
- Metrics: total return, buy & hold baseline, max drawdown, win rate, profit
  factor, Sharpe (daily, annualized √365), trade count, fees.
- Run and compare from the dashboard; results are labeled **simulated**.

## Alerting

Optional — set in `.env`:

```
TELEGRAM_BOT_TOKEN=...   TELEGRAM_CHAT_ID=...   # via @BotFather
ALERT_WEBHOOK_URL=https://...                    # receives JSON POSTs
```

Fires on entry/exit fills, stop-losses, daily halt, kill switch, emergency
stop, and OCO-protection failures.

## Testnet quirks

- The Spot Testnet lists a **limited symbol set**; symbols that don't exist
  there are skipped and listed in the dashboard (and in `/api/status`).
- Testnet prices track production loosely; volumes are simulated (the
  scanner's liquidity floor is ignored on testnet).
- Testnet balances/orders reset periodically (roughly monthly) — vanished
  balances are Binance, not the bot.
- Backtests always use **production** market history, even in testnet mode.

## Go-live checklist

Work through this in order; do not skip steps.

1. **Clean host.** The machine holding live keys has no history of running
   untrusted code (on this particular laptop: after the planned OS reinstall).
2. **Weeks, not days, on testnet.** The bot has run through enough market
   variety that you've seen: entries, TP exits, SL exits, a daily halt, the
   kill switch (force it with a tight limit once — verify it stops and stays
   stopped through a restart), an emergency stop, and a WebSocket drop
   (toggle Wi-Fi) with clean reconnection and reconciliation.
3. **Backtests + testnet results reviewed honestly**, including fees, versus
   buy-and-hold. If the strategy loses simulated money, it will lose real
   money faster.
4. **Restricted live keys** created from a clean device: trading on,
   withdrawals OFF, IP whitelist on. Confirm with a read-only call first.
5. **Risk limits set for real money** — position size 1–2%, daily loss and
   kill switch at values you can genuinely tolerate, `kill_switch_enabled`
   on. The live defaults are the same conservative ones as testnet.
6. **Flip `TESTNET=false`** in `.env`, restart, and confirm the red LIVE
   banner appears.
7. **Fund the account with a small amount you can afford to lose entirely**
   (e.g. $100–$200). Run one strategy on one pair for at least a week.
8. **Scale gradually**: one variable at a time (capital → pairs →
   strategies), reviewing the Trades page and risk events at each step.
9. **Set up alerting first** (Telegram), so stop-losses and kill-switch
   events reach you away from the screen.
10. Re-verify after every config change; pause the bot when you're changing
    several things at once.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Can't log in / lost password | See [Dashboard login](#dashboard-login) — reseed via sqlite + `.env`. |
| `no API keys` pill in topbar | Add keys on the Settings page (or in `.env` before first boot). |
| Start fails with key error | Wrong environment: testnet keys with `TESTNET=false` (or vice versa). |
| Symbol listed as invalid | Not on the testnet's limited list, or not a USDT pair. |
| `-1021 timestamp` warnings | Clock drift — the gateway resyncs automatically; persistent drift → enable NTP. |
| Position shows `⚠ engine` protection | OCO placement failed (often min-notional on tiny positions); engine monitors and retries — consider larger position size. |
| Backtest ERROR "no kline data" | Symbol/date range has no production history (new listings). |
| Dashboard blank on :5173 | Frontend deps not installed (see security notes) — use the API at :8000/docs meanwhile. |

---

*Built 2026-08-09. Testnet-first by design. Trading involves substantial risk
of loss; simulated performance does not indicate future results.*
