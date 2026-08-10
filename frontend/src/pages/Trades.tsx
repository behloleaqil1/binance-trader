import { Fragment, useMemo, useState } from "react";
import { deltaClass, downloadCsv, fmtMoney, fmtPct, fmtQty, fmtSigned, fmtTime, useApi } from "../api/client";
import type { Trade } from "../api/types";
import { useStore } from "../store/useStore";

const PAGE = 50;

export function Trades() {
  const version = useStore((s) => s.versions.trades);
  const [page, setPage] = useState(0);
  const [symbol, setSymbol] = useState("");
  const [strategy, setStrategy] = useState("");
  const [open, setOpen] = useState<number | null>(null);

  const qs = useMemo(() => {
    const p = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
    if (symbol) p.set("symbol", symbol.toUpperCase());
    if (strategy) p.set("strategy", strategy);
    return p.toString();
  }, [page, symbol, strategy]);

  const { data } = useApi<{ total: number; items: Trade[] }>(`/trades?${qs}`, version);
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  const pageStats = useMemo(() => {
    if (!items.length) return null;
    const pnl = items.reduce((a, t) => a + t.pnl, 0);
    const wins = items.filter((t) => t.pnl > 0).length;
    const fees = items.reduce((a, t) => a + t.fees, 0);
    return { pnl, winRate: (wins / items.length) * 100, fees, n: items.length };
  }, [items]);

  return (
    <div className="grid">
      <div className="card">
        <h3>Filters</h3>
        <div className="chart-controls">
          <input placeholder="Symbol (e.g. BTCUSDT)" value={symbol} style={{ width: 190 }}
                 onChange={(e) => { setSymbol(e.target.value); setPage(0); }} />
          <select value={strategy} style={{ width: 190 }}
                  onChange={(e) => { setStrategy(e.target.value); setPage(0); }}>
            <option value="">All strategies</option>
            <option value="trend_momentum">Trend / Momentum</option>
            <option value="mean_reversion">Mean Reversion</option>
            <option value="grid">Grid</option>
            <option value="dca">DCA</option>
          </select>
          <span className="spacer" style={{ flex: 1 }} />
          <button className="btn btn-sm" disabled={!items.length}
                  onClick={() => downloadCsv(`trades-page${page + 1}.csv`, items as any)}>
            Export CSV
          </button>
        </div>
        {pageStats && (
          <div className="muted" style={{ fontSize: 12 }}>
            This page: {pageStats.n} trades · PnL{" "}
            <b className={deltaClass(pageStats.pnl)}>{fmtSigned(pageStats.pnl)} USDT</b> ·
            win rate {pageStats.winRate.toFixed(1)}% · fees {fmtMoney(pageStats.fees)}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Trade history ({total})</h3>
        {!items.length ? <div className="empty">No closed trades yet</div> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Closed</th><th>Symbol</th><th>Strategy</th>
                  <th className="num">Qty</th><th className="num">Entry</th>
                  <th className="num">Exit</th><th className="num">PnL (USDT)</th>
                  <th className="num">PnL %</th><th className="num">Fees</th><th>Exit kind</th>
                </tr>
              </thead>
              <tbody>
                {items.map((t) => (
                  <Fragment key={t.id}>
                    <tr className="expandable" onClick={() => setOpen(open === t.id ? null : t.id)}>
                      <td className="muted">{fmtTime(t.closed_at)}</td>
                      <td><b>{t.symbol}</b></td>
                      <td>{t.strategy}</td>
                      <td className="num">{fmtQty(t.qty)}</td>
                      <td className="num">{fmtMoney(t.entry_price, 4)}</td>
                      <td className="num">{fmtMoney(t.exit_price, 4)}</td>
                      <td className={`num ${deltaClass(t.pnl)}`}>{fmtSigned(t.pnl, 4)}</td>
                      <td className={`num ${deltaClass(t.pnl_pct)}`}>{fmtPct(t.pnl_pct)}</td>
                      <td className="num muted">{fmtMoney(t.fees, 4)}</td>
                      <td>{t.exit_reason.split(":")[0]}</td>
                    </tr>
                    {open === t.id && (
                      <tr className="detail">
                        <td colSpan={10}>
                          <b>Entry</b> ({fmtTime(t.opened_at)}): {t.entry_reason || "—"}<br />
                          <b>Exit:</b> {t.exit_reason || "—"}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {total > PAGE && (
          <div className="chart-controls" style={{ marginTop: 10 }}>
            <button className="btn btn-sm" disabled={page === 0} onClick={() => setPage(page - 1)}>← Prev</button>
            <span className="muted">page {page + 1} / {Math.ceil(total / PAGE)}</span>
            <button className="btn btn-sm" disabled={(page + 1) * PAGE >= total}
                    onClick={() => setPage(page + 1)}>Next →</button>
          </div>
        )}
      </div>
    </div>
  );
}
