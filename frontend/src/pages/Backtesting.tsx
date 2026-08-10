import { useEffect, useMemo, useState } from "react";
import { api, del, deltaClass, fmtMoney, fmtSigned, post, useApi } from "../api/client";
import type { BacktestDetail, BacktestSummary, StrategyInfo } from "../api/types";
import { EquityChart, EquitySeries } from "../components/EquityChart";
import { ParamsForm } from "../components/ParamsForm";
import { useStore } from "../store/useStore";

const SERIES_COLORS = ["#3987e5", "#d95926", "#199e70"]; // validated slots 1–3
const MAX_COMPARE = 3;

const isoDaysAgo = (d: number) => new Date(Date.now() - d * 86_400_000).toISOString().slice(0, 10);

function MetricCell({ label, value, signed }: { label: string; value: any; signed?: boolean }) {
  const num = typeof value === "number" ? value : null;
  return (
    <div className="tile" style={{ padding: "8px 12px" }}>
      <div className="label">{label}</div>
      <div className={`value num ${signed && num !== null ? deltaClass(num) : ""}`}
           style={{ fontSize: 16 }}>
        {num === null ? String(value ?? "—") : signed ? fmtSigned(num) : fmtMoney(num)}
      </div>
    </div>
  );
}

export function Backtesting() {
  const pushToast = useStore((s) => s.pushToast);
  const { data: strategies } = useApi<StrategyInfo[]>("/strategies");
  const [listKey, setListKey] = useState(0);
  const { data: runs, reload } = useApi<BacktestSummary[]>("/backtests", listKey);

  const [form, setForm] = useState({
    strategy_id: "trend_momentum", symbol: "BTCUSDT", timeframe: "1h",
    start: isoDaysAgo(180), end: isoDaysAgo(0), initial_equity: 10_000,
    fee_bps: 10, slippage_bps: 5, label: "",
  });
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [compare, setCompare] = useState<number[]>([]);
  const [detailId, setDetailId] = useState<number | null>(null);
  const { data: detail } = useApi<BacktestDetail>(detailId ? `/backtests/${detailId}` : null, detailId);
  const [compareData, setCompareData] = useState<BacktestDetail[]>([]);

  const spec = useMemo(
    () => strategies?.find((s) => s.id === form.strategy_id), [strategies, form.strategy_id]);
  useEffect(() => { if (spec) setParams({ ...spec.params }); }, [spec]);

  /* poll while any run is RUNNING */
  const anyRunning = (runs ?? []).some((r) => r.status === "RUNNING");
  useEffect(() => {
    if (!anyRunning) return;
    const t = setInterval(reload, 2500);
    return () => clearInterval(t);
  }, [anyRunning, reload]);

  /* fetch details of compared runs for curve overlay */
  useEffect(() => {
    let dead = false;
    Promise.all(compare.map((id) =>
      api<BacktestDetail>(`/backtests/${id}`).catch(() => null)))
      .then((ds) => !dead && setCompareData(ds.filter(Boolean) as BacktestDetail[]));
    return () => { dead = true; };
  }, [compare]);

  const run = async () => {
    try {
      const res = await post("/backtests", { ...form, params });
      pushToast({ kind: "info", title: `Backtest #${res.id} started`, body: "Downloading data and simulating…" });
      setListKey((k) => k + 1);
    } catch (e: any) {
      pushToast({ kind: "risk", title: "Backtest failed to start", body: e.message });
    }
  };

  const toggleCompare = (id: number) =>
    setCompare((c) => c.includes(id) ? c.filter((x) => x !== id)
      : c.length >= MAX_COMPARE ? c : [...c, id]);

  const compareSeries: EquitySeries[] = compareData
    .filter((d) => d.equity_curve?.length)
    .map((d, i) => ({
      label: d.label || `#${d.id} ${d.strategy_id} ${d.symbol}`,
      color: SERIES_COLORS[i % SERIES_COLORS.length],
      points: d.equity_curve,
    }));

  const m = detail?.metrics ?? {};

  return (
    <div className="grid">
      <div className="banner banner-info">
        Backtests run on <b>production market history</b> with modeled fees and
        slippage. Results are <b>simulated historical performance</b> and are not
        indicative of future results.
      </div>

      <div className="card">
        <h3>New backtest</h3>
        <div className="field-row">
          <label className="field"><span>Strategy</span>
            <select value={form.strategy_id}
                    onChange={(e) => setForm({ ...form, strategy_id: e.target.value })}>
              {(strategies ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select></label>
          <label className="field"><span>Symbol</span>
            <input value={form.symbol}
                   onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} /></label>
          <label className="field"><span>Timeframe</span>
            <select value={form.timeframe}
                    onChange={(e) => setForm({ ...form, timeframe: e.target.value })}>
              {["1m", "5m", "15m", "1h", "4h", "1d"].map((t) => <option key={t}>{t}</option>)}
            </select></label>
          <label className="field"><span>Start</span>
            <input type="date" value={form.start}
                   onChange={(e) => setForm({ ...form, start: e.target.value })} /></label>
          <label className="field"><span>End</span>
            <input type="date" value={form.end}
                   onChange={(e) => setForm({ ...form, end: e.target.value })} /></label>
          <label className="field"><span>Initial equity (USDT)</span>
            <input type="number" min={100} value={form.initial_equity}
                   onChange={(e) => setForm({ ...form, initial_equity: parseFloat(e.target.value || "10000") })} /></label>
          <label className="field"><span>Fee (bps)</span>
            <input type="number" min={0} max={100} value={form.fee_bps}
                   onChange={(e) => setForm({ ...form, fee_bps: parseFloat(e.target.value || "10") })} />
            <small>10 bps = 0.10% taker</small></label>
          <label className="field"><span>Slippage (bps)</span>
            <input type="number" min={0} max={100} value={form.slippage_bps}
                   onChange={(e) => setForm({ ...form, slippage_bps: parseFloat(e.target.value || "5") })} /></label>
          <label className="field"><span>Label</span>
            <input placeholder="optional name" value={form.label}
                   onChange={(e) => setForm({ ...form, label: e.target.value })} /></label>
        </div>
        {spec && (
          <>
            <h3 style={{ marginTop: 4 }}>Strategy parameters</h3>
            <ParamsForm specs={spec.param_specs} values={params}
                        onChange={(n, v) => setParams((p) => ({ ...p, [n]: v }))} />
          </>
        )}
        <button className="btn btn-primary" onClick={run}>Run backtest</button>
      </div>

      <div className="card">
        <h3>Runs {compare.length > 0 && <span className="muted">— comparing {compare.length}/{MAX_COMPARE}</span>}</h3>
        {!(runs?.length) ? <div className="empty">No backtests yet</div> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th></th><th>#</th><th>Label</th><th>Strategy</th><th>Symbol</th>
                  <th>TF</th><th>Range</th><th className="num">Return</th>
                  <th className="num">Buy&hold</th><th className="num">Max DD</th>
                  <th className="num">Win rate</th><th className="num">PF</th>
                  <th className="num">Sharpe</th><th className="num">Trades</th>
                  <th>Status</th><th></th>
                </tr>
              </thead>
              <tbody>
                {(runs ?? []).map((r) => (
                  <tr key={r.id} className="expandable"
                      onClick={() => setDetailId(detailId === r.id ? null : r.id)}>
                    <td onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={compare.includes(r.id)}
                             disabled={r.status !== "DONE" || (!compare.includes(r.id) && compare.length >= MAX_COMPARE)}
                             onChange={() => toggleCompare(r.id)} />
                    </td>
                    <td className="muted">{r.id}</td>
                    <td>{r.label || "—"}</td>
                    <td>{r.strategy_id}</td>
                    <td><b>{r.symbol}</b></td>
                    <td>{r.timeframe}</td>
                    <td className="muted">{r.start} → {r.end}</td>
                    <td className={`num ${r.metrics.total_return_pct !== undefined ? deltaClass(r.metrics.total_return_pct) : ""}`}>
                      {r.metrics.total_return_pct !== undefined ? `${r.metrics.total_return_pct >= 0 ? "+" : "−"}${Math.abs(r.metrics.total_return_pct).toFixed(2)}%` : "—"}
                    </td>
                    <td className="num muted">
                      {r.metrics.buy_hold_return_pct !== undefined ? `${r.metrics.buy_hold_return_pct.toFixed(1)}%` : "—"}
                    </td>
                    <td className="num">{r.metrics.max_drawdown_pct !== undefined ? `${r.metrics.max_drawdown_pct.toFixed(1)}%` : "—"}</td>
                    <td className="num">{r.metrics.win_rate_pct !== undefined ? `${r.metrics.win_rate_pct.toFixed(0)}%` : "—"}</td>
                    <td className="num">{r.metrics.profit_factor ?? "—"}</td>
                    <td className="num">{r.metrics.sharpe_ratio ?? "—"}</td>
                    <td className="num">{r.metrics.n_trades ?? "—"}</td>
                    <td>{r.status === "RUNNING" ? "⏳ running" : r.status === "ERROR"
                      ? <span className="delta-down" title={r.error}>✕ error</span> : "✓ done"}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button className="btn btn-ghost btn-sm" title="delete"
                              onClick={async () => { await del(`/backtests/${r.id}`); setCompare((c) => c.filter((x) => x !== r.id)); setListKey((k) => k + 1); }}>
                        🗑
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {compareSeries.length > 1 && (
        <div className="card">
          <h3>Equity curves — comparison (simulated)</h3>
          <EquityChart series={compareSeries} height={300} />
        </div>
      )}

      {detail && detail.status === "DONE" && (
        <div className="card">
          <h3>#{detail.id} {detail.label || `${detail.strategy_id} · ${detail.symbol}`} — detail</h3>
          <div className="tiles" style={{ marginBottom: 12 }}>
            <MetricCell label="Return %" value={m.total_return_pct} signed />
            <MetricCell label="Buy & hold %" value={m.buy_hold_return_pct} signed />
            <MetricCell label="Max drawdown %" value={m.max_drawdown_pct} />
            <MetricCell label="Win rate %" value={m.win_rate_pct} />
            <MetricCell label="Profit factor" value={m.profit_factor ?? "∞/0"} />
            <MetricCell label="Sharpe" value={m.sharpe_ratio} />
            <MetricCell label="Trades" value={m.n_trades} />
            <MetricCell label="Fees paid" value={m.fees_paid} />
            <MetricCell label="Final equity" value={m.final_equity} />
          </div>
          {detail.equity_curve?.length > 0 && (
            <EquityChart series={[{ label: "Equity", color: "#3987e5", points: detail.equity_curve }]} />
          )}
          {detail.trades?.length > 0 && (
            <details className="data-table">
              <summary>Trades ({detail.trades.length})</summary>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Entry reason</th><th>Exit</th><th className="num">Entry</th>
                    <th className="num">Exit</th><th className="num">PnL</th><th className="num">PnL %</th></tr></thead>
                  <tbody>
                    {detail.trades.slice(0, 100).map((t: any, i: number) => (
                      <tr key={i}>
                        <td style={{ whiteSpace: "normal", maxWidth: 380 }}>{t.entry_reason ?? t.reason ?? "—"}</td>
                        <td>{t.exit_kind ?? "—"}</td>
                        <td className="num">{t.entry !== undefined ? fmtMoney(t.entry, 4) : fmtMoney(t.price, 4)}</td>
                        <td className="num">{t.exit !== undefined ? fmtMoney(t.exit, 4) : "—"}</td>
                        <td className={`num ${t.pnl !== undefined ? deltaClass(t.pnl) : ""}`}>
                          {t.pnl !== undefined ? fmtSigned(t.pnl, 4) : "—"}</td>
                        <td className="num">{t.pnl_pct !== undefined ? `${t.pnl_pct.toFixed(2)}%` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
          <div className="disclaimer">{m.disclaimer ?? "Simulated historical performance; not indicative of future results."}</div>
        </div>
      )}
    </div>
  );
}
