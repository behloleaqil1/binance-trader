import { Fragment, useState } from "react";
import { deltaClass, fmtMoney, fmtQty, fmtSigned, fmtPct, fmtTime } from "../api/client";
import type { Position } from "../api/types";

export function PositionsTable({ positions }: { positions: Position[] }) {
  const [open, setOpen] = useState<number | null>(null);
  if (!positions.length) return <div className="empty">No open positions</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Symbol</th><th>Strategy</th><th className="num">Qty</th>
            <th className="num">Entry</th><th className="num">Mark</th>
            <th className="num">Value</th><th className="num">Unrealized PnL</th>
            <th>Protection</th><th>Opened</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <Fragment key={p.id}>
              <tr className="expandable" onClick={() => setOpen(open === p.id ? null : p.id)}>
                <td><b>{p.symbol}</b>{p.grid_level !== null ? <span className="muted"> · L{p.grid_level}</span> : null}</td>
                <td>{p.strategy}</td>
                <td className="num">{fmtQty(p.qty)}</td>
                <td className="num">{fmtMoney(p.avg_entry, 4)}</td>
                <td className="num">{fmtMoney(p.mark, 4)}</td>
                <td className="num">{fmtMoney(p.value)}</td>
                <td className={`num ${deltaClass(p.unrealized_pnl)}`}>
                  {fmtSigned(p.unrealized_pnl)} ({fmtPct(p.unrealized_pnl_pct)})
                </td>
                <td>
                  {p.sl || p.tp ? (
                    <span title={p.protected ? "OCO order live on Binance" : "engine-monitored (OCO unavailable)"}>
                      {p.sl ? `SL ${fmtMoney(p.sl, 4)}` : ""}{p.sl && p.tp ? " · " : ""}
                      {p.tp ? `TP ${fmtMoney(p.tp, 4)}` : ""}
                      {p.trailing ? " · trail" : ""}
                      {!p.protected && <span className="delta-down"> ⚠ engine</span>}
                    </span>
                  ) : (
                    <span className="muted">none (DCA accumulation)</span>
                  )}
                </td>
                <td className="muted">{fmtTime(p.opened_at)}</td>
              </tr>
              {open === p.id && (
                <tr className="detail">
                  <td colSpan={9}><b>Entry rationale:</b> {p.entry_reason || "—"}</td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
