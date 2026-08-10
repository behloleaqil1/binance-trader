import { useEffect, useState } from "react";
import { api, put, useApi } from "../api/client";
import type { ScannedSymbol, StrategyInfo } from "../api/types";
import { ParamsForm } from "../components/ParamsForm";
import { useStore } from "../store/useStore";

const KIND_LABEL: Record<string, string> = {
  candle: "candle-driven", grid: "order ladder", schedule: "scheduled",
};

function SymbolsEditor({ symbols, onChange }: {
  symbols: string[]; onChange: (s: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const s = draft.toUpperCase().trim();
    if (s && !symbols.includes(s)) onChange([...symbols, s]);
    setDraft("");
  };
  return (
    <div>
      <div className="chips" style={{ marginBottom: 6 }}>
        {symbols.map((s) => (
          <span key={s} className="chip">{s}
            <button onClick={() => onChange(symbols.filter((x) => x !== s))} title="remove">✕</button>
          </span>
        ))}
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <input list="common-symbols" placeholder="Add pair, e.g. BTCUSDT" value={draft}
               onChange={(e) => setDraft(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && add()} style={{ maxWidth: 220 }} />
        <button className="btn btn-sm" onClick={add}>Add</button>
        <datalist id="common-symbols">
          {["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT"]
            .map((s) => <option key={s} value={s} />)}
        </datalist>
      </div>
    </div>
  );
}

function StrategyCard({ s, onSaved }: { s: StrategyInfo; onSaved: () => void }) {
  const pushToast = useStore((st) => st.pushToast);
  const [enabled, setEnabled] = useState(s.enabled);
  const [params, setParams] = useState<Record<string, unknown>>({ ...s.params });
  const [symbols, setSymbols] = useState<string[]>([...s.symbols]);
  const [useScanner, setUseScanner] = useState(s.use_scanner);
  const [busy, setBusy] = useState(false);
  const [showEvals, setShowEvals] = useState(false);
  const { data: evals } = useApi<any[]>(showEvals ? `/strategies/${s.id}/evaluations` : null, showEvals);

  const dirty = enabled !== s.enabled || useScanner !== s.use_scanner
    || JSON.stringify(params) !== JSON.stringify(s.params)
    || JSON.stringify(symbols) !== JSON.stringify(s.symbols);

  const save = async () => {
    setBusy(true);
    try {
      await put(`/strategies/${s.id}`, { enabled, params, symbols, use_scanner: useScanner });
      pushToast({ kind: "info", title: `${s.name} saved`, body: enabled ? "Strategy enabled" : "Strategy disabled" });
      onSaved();
    } catch (e: any) {
      pushToast({ kind: "risk", title: `Save failed: ${s.name}`, body: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <h3 style={{ margin: 0, flex: 1 }}>{s.name}
          <span className="muted" style={{ textTransform: "none", letterSpacing: 0 }}> · {KIND_LABEL[s.kind]}</span>
        </h3>
        <label className="check-row" style={{ margin: 0 }}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Enabled
        </label>
      </div>
      <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>{s.description}</p>
      {s.adaptive && s.adaptive.n > 0 && (
        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Last {s.adaptive.n} trades: {s.adaptive.win_rate_pct}% wins
          {s.adaptive.profit_factor !== null && <> · profit factor {s.adaptive.profit_factor}</>}
          {" · "}sizing ×{s.adaptive.size_multiplier}
          {s.adaptive.paused && (
            <span className="pill pill-crit" style={{ marginLeft: 8 }}
                  title={s.adaptive.reason}>⛔ probation — save to reset</span>
          )}
        </div>
      )}
      {s.note && <div className="banner banner-warn">{s.note}</div>}

      <ParamsForm specs={s.param_specs} values={params}
                  onChange={(name, v) => setParams((p) => ({ ...p, [name]: v }))} />

      <label className="field"><span>Trading pairs</span></label>
      <SymbolsEditor symbols={symbols} onChange={setSymbols} />

      {s.kind === "candle" && (
        <label className="check-row" title="Adds the momentum scanner's current picks to this strategy's pairs">
          <input type="checkbox" checked={useScanner} onChange={(e) => setUseScanner(e.target.checked)} />
          Also trade momentum-scanner picks
        </label>
      )}
      {s.effective_symbols.length > 0 && (
        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          Currently effective: {s.effective_symbols.join(", ")}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button className="btn btn-primary btn-sm" disabled={!dirty || busy} onClick={save}>
          {busy ? "Saving…" : "Save"}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => setShowEvals(!showEvals)}>
          {showEvals ? "Hide" : "Show"} recent evaluations
        </button>
      </div>

      {showEvals && (
        <div className="feed" style={{ marginTop: 10, maxHeight: 220 }}>
          {!(evals?.length) && <div className="empty">No evaluations yet (enable the strategy and start the bot)</div>}
          {(evals ?? []).map((ev, i) => (
            <div key={i} className={`feed-item ${ev.action === "HOLD" ? "hold" : ""}`}>
              <span className="when">{new Date(ev.ts).toLocaleTimeString("en-GB")}</span>
              <b>{ev.symbol}</b> {ev.action} — {ev.reason}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ScannerCard({ onSaved }: { onSaved: () => void }) {
  const pushToast = useStore((st) => st.pushToast);
  const scannedLive = useStore((st) => st.scanned);
  const { data, reload } = useApi<{ config: any; current: ScannedSymbol[] }>("/scanner");
  const [cfg, setCfg] = useState<any | null>(null);
  useEffect(() => { if (data && !cfg) setCfg(data.config); }, [data, cfg]);
  const picks = scannedLive.length ? scannedLive : (data?.current ?? []);

  if (!cfg) return <div className="card"><h3>Momentum scanner</h3><div className="empty">Loading…</div></div>;

  const save = async () => {
    try {
      await put("/scanner", cfg);
      pushToast({ kind: "info", title: "Scanner saved", body: cfg.enabled ? "Scanner enabled" : "Scanner disabled" });
      reload(); onSaved();
    } catch (e: any) {
      pushToast({ kind: "risk", title: "Scanner save failed", body: e.message });
    }
  };

  return (
    <div className="card">
      <h3>Momentum scanner</h3>
      <p className="muted" style={{ fontSize: 12 }}>
        Ranks USDT pairs by 24h movement (leveraged tokens and stablecoins excluded,
        liquidity floor applied) and feeds the top picks to strategies that opt in.
        The scanner finds <b>movement, not guaranteed profit</b> — top movers cut both
        ways, and every scanner trade passes the same risk gate as any other.
      </p>
      <div className="field-row">
        <label className="check-row"><input type="checkbox" checked={cfg.enabled}
          onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} /> Enabled</label>
        <label className="field"><span>Top N picks</span>
          <input type="number" min={1} max={15} value={cfg.top_n}
                 onChange={(e) => setCfg({ ...cfg, top_n: parseInt(e.target.value || "5", 10) })} /></label>
        <label className="field"><span>Rank by</span>
          <select value={cfg.rank_by} onChange={(e) => setCfg({ ...cfg, rank_by: e.target.value })}>
            <option value="top_gainers">Top gainers (24h %)</option>
            <option value="top_losers">Top losers (24h %)</option>
            <option value="volume">Volume</option>
          </select></label>
        <label className="field"><span>Min 24h quote volume</span>
          <input type="number" min={0} step={1000000} value={cfg.min_quote_volume_24h}
                 onChange={(e) => setCfg({ ...cfg, min_quote_volume_24h: parseFloat(e.target.value || "0") })} />
          <small>ignored on testnet (volumes there are simulated)</small></label>
        <label className="field"><span>Refresh every (min)</span>
          <input type="number" min={5} max={240} value={cfg.refresh_minutes}
                 onChange={(e) => setCfg({ ...cfg, refresh_minutes: parseInt(e.target.value || "15", 10) })} /></label>
      </div>
      <button className="btn btn-primary btn-sm" onClick={save}>Save scanner</button>

      {picks.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table>
            <thead><tr><th>Symbol</th><th className="num">24h change</th><th className="num">Quote volume</th><th className="num">Price</th></tr></thead>
            <tbody>
              {picks.map((p) => (
                <tr key={p.symbol}>
                  <td><b>{p.symbol}</b></td>
                  <td className={`num ${p.change_pct >= 0 ? "delta-up" : "delta-down"}`}>
                    {p.change_pct >= 0 ? "+" : "−"}{Math.abs(p.change_pct).toFixed(2)}%
                  </td>
                  <td className="num">{Math.round(p.quote_volume).toLocaleString()}</td>
                  <td className="num">{p.price}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function Strategies() {
  const status = useStore((s) => s.status);
  const [reloadKey, setReloadKey] = useState(0);
  const { data: strategies, reload } = useApi<StrategyInfo[]>("/strategies", reloadKey);
  const onSaved = () => { setReloadKey((k) => k + 1); reload(); };

  return (
    <div className="grid">
      {status && status.invalid_symbols.length > 0 && (
        <div className="banner banner-warn">
          Not tradable in this environment (the Spot Testnet lists a limited symbol
          set): {status.invalid_symbols.join(", ")} — these are skipped.
        </div>
      )}
      <ScannerCard onSaved={onSaved} />
      {(strategies ?? []).map((s) => <StrategyCard key={s.id} s={s} onSaved={onSaved} />)}
    </div>
  );
}
