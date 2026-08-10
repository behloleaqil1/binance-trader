import { useEffect, useMemo, useState } from "react";
import { deltaClass, fmtMoney, fmtPct, fmtSigned, useApi } from "../api/client";
import type { Account, Position } from "../api/types";
import { CandleChart } from "../components/CandleChart";
import { EquityChart } from "../components/EquityChart";
import { PositionsTable } from "../components/PositionsTable";
import { SignalsFeed } from "../components/SignalsFeed";
import { StatTile } from "../components/common";
import { useStore } from "../store/useStore";

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];
const DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"];

export function Overview() {
  const status = useStore((s) => s.status);
  const usage = useStore((s) => s.usage);
  const equityLive = useStore((s) => s.equityLive);
  const versions = useStore((s) => s.versions);

  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 30_000);
    return () => clearInterval(t);
  }, []);

  const { data: account } = useApi<Account>("/account",
    `${versions.trades}:${versions.positions}:${tick}`);
  const { data: positions } = useApi<Position[]>("/positions", versions.positions);
  const { data: history } = useApi<{ ts: string; equity: number }[]>("/equity-history?hours=168", tick);

  const symbols = status?.active_symbols?.length ? status.active_symbols : DEFAULT_SYMBOLS;
  const [symbol, setSymbol] = useState(symbols[0]);
  const [tf, setTf] = useState("1h");
  useEffect(() => {
    if (!symbols.includes(symbol)) setSymbol(symbols[0]);
  }, [symbols, symbol]);

  const equityPoints = useMemo(() => {
    const pts: [number, number][] = (history ?? []).map((h) => [new Date(h.ts).getTime(), h.equity]);
    for (const e of equityLive) pts.push([e.ts, e.equity]);
    return pts;
  }, [history, equityLive]);

  const dayPnl = account ? account.day_pnl : 0;
  const dayPct = account && account.day_start_equity
    ? (dayPnl / account.day_start_equity) * 100 : 0;

  return (
    <div className="grid">
      <div className="tiles">
        <StatTile label="Equity (USDT)" value={fmtMoney(account?.equity)}
                  sub={`peak ${fmtMoney(account?.peak_equity)}`} />
        <StatTile label="Day PnL" value={account ? fmtSigned(dayPnl) : "—"}
                  valueClass={deltaClass(dayPnl)}
                  sub={account ? `${fmtPct(dayPct)} vs UTC day start` : ""} />
        <StatTile label="Realized today" value={account ? fmtSigned(account.realized_pnl_today) : "—"}
                  valueClass={account ? deltaClass(account.realized_pnl_today) : ""}
                  sub="closed trades, net of fees" />
        <StatTile label="Unrealized PnL" value={account ? fmtSigned(account.unrealized_pnl) : "—"}
                  valueClass={account ? deltaClass(account.unrealized_pnl) : ""}
                  sub={`${positions?.length ?? 0} open position${(positions?.length ?? 0) === 1 ? "" : "s"}`} />
        <StatTile label="Daily loss used"
                  value={usage ? `${usage.daily_loss.used_pct.toFixed(2)}%` : "—"}
                  sub={usage ? `halts at ${usage.daily_loss.limit_pct}%` : ""} />
        <StatTile label="Drawdown"
                  value={usage ? `${usage.drawdown.used_pct.toFixed(2)}%` : "—"}
                  sub={usage ? `kill switch at ${usage.drawdown.limit_pct}%` : ""} />
      </div>

      <div className="card">
        <h3>Equity — last 7 days</h3>
        {equityPoints.length ? (
          <EquityChart series={[{ label: "Equity", color: "#3987e5", points: equityPoints }]} />
        ) : (
          <div className="empty">No equity snapshots yet — start the bot to begin recording</div>
        )}
      </div>

      <div className="card">
        <h3>Market</h3>
        <div className="chart-controls">
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            {symbols.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select value={tf} onChange={(e) => setTf(e.target.value)}>
            {TIMEFRAMES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        <CandleChart symbol={symbol} tf={tf} positions={positions ?? []} />
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h3>Open positions</h3>
          <PositionsTable positions={positions ?? []} />
        </div>
        <div className="card">
          <h3>Live activity</h3>
          <SignalsFeed />
        </div>
      </div>
    </div>
  );
}
