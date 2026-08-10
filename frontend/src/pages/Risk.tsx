import { useEffect, useState } from "react";
import { fmtTime, post, put, useApi } from "../api/client";
import { ConfirmModal, Meter } from "../components/common";
import { useStore } from "../store/useStore";

const GROUPS: { title: string; fields: [string, string, string][] }[] = [
  {
    title: "Position sizing",
    fields: [
      ["position_size_pct", "Position size (% of equity)", "Notional per new position"],
    ],
  },
  {
    title: "Protective exits (every position, unless exempted below)",
    fields: [
      ["stop_loss_pct", "Stop-loss %", "Placed on Binance as an OCO immediately after entry"],
      ["take_profit_pct", "Take-profit %", ""],
      ["trailing_stop_pct", "Trailing distance %", "Below the high-water mark"],
      ["trailing_activation_pct", "Trailing arms after profit %", "0 = trail immediately"],
    ],
  },
  {
    title: "Hard limits",
    fields: [
      ["max_daily_loss_pct", "Max daily loss %", "Halts new entries until the next UTC day"],
      ["max_drawdown_pct", "Max drawdown % (kill switch)", "Stops the bot entirely; manual reset required"],
    ],
  },
  {
    title: "Concurrency & exposure",
    fields: [
      ["max_open_positions", "Max open positions", "Grid ladders count as one position per symbol"],
      ["max_exposure_per_asset_pct", "Max exposure per asset %", "Positions + open buy orders"],
      ["max_total_exposure_pct", "Max total exposure %", "Across all assets"],
    ],
  },
  {
    title: "Adaptive sizing & probation (reacts to each strategy's recent trades)",
    fields: [
      ["adaptive_window", "Rolling window (trades)", "How many recent closed trades are considered"],
      ["halve_size_after_losses", "Halve size every N consecutive losses", "Anti-martingale: losing streaks shrink size, never grow it"],
      ["min_size_multiplier", "Minimum size multiplier", "Floor for shrunken sizing (0.25 = quarter size)"],
      ["pause_after_consecutive_losses", "Probation after N consecutive losses", "Strategy stops opening new positions; exits unaffected"],
      ["pause_below_profit_factor", "Probation below profit factor", "Checked once the window is full"],
      ["win_boost_after_wins", "Win boost after N consecutive wins", "Only if the win boost switch is on"],
      ["win_boost_multiplier", "Win boost multiplier", "Capped at 1.5× — modest by design"],
    ],
  },
];

const CHECKS: [string, string, string][] = [
  ["trailing_stop_enabled", "Enable trailing stop", "Ratchets the OCO stop up as price rises"],
  ["kill_switch_enabled", "Enable drawdown kill switch", "Strongly recommended"],
  ["flatten_on_kill", "Flatten positions when killed", "Otherwise positions keep their SL/TP"],
  ["exempt_dca_from_stops", "Exempt DCA accumulation from SL/TP", "DCA still counts toward exposure, daily-loss and drawdown limits"],
  ["adaptive_enabled", "Enable adaptive sizing", "Shrink position size during losing streaks (signal strategies only)"],
  ["auto_pause_enabled", "Enable strategy probation", "Auto-pause strategies on long losing streaks or poor rolling profit factor"],
  ["win_boost_enabled", "Enable win-streak size boost", "Off by default — upsizing adds risk"],
];

export function Risk() {
  const status = useStore((s) => s.status);
  const usageLive = useStore((s) => s.usage);
  const versions = useStore((s) => s.versions);
  const pushToast = useStore((s) => s.pushToast);

  const { data: stored, reload } = useApi<Record<string, any>>("/risk");
  const { data: usageInit } = useApi<{ usage: any }>("/risk/usage", versions.positions);
  const { data: events } = useApi<any[]>("/risk/events", versions.risk);
  const [cfg, setCfg] = useState<Record<string, any> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [modal, setModal] = useState<"emergency" | "reset" | null>(null);
  const [flatten, setFlatten] = useState(false);
  useEffect(() => { if (stored && !cfg) setCfg(stored); }, [stored, cfg]);

  const usage = usageLive ?? usageInit?.usage ?? null;
  const killed = status?.status === "KILLED";

  const save = async () => {
    if (!cfg) return;
    setErr(null);
    try {
      await put("/risk", cfg);
      pushToast({ kind: "info", title: "Risk limits saved", body: "Applied immediately to all future orders" });
      reload();
    } catch (e: any) {
      setErr(e.message);
    }
  };

  return (
    <div className="grid cols-2">
      <div className="card">
        <h3>Risk limits</h3>
        {killed && (
          <div className="banner banner-crit">
            ⛔ Kill switch engaged — {status?.status_reason}. Reset below, then Start the bot again.
          </div>
        )}
        {!cfg ? <div className="empty">Loading…</div> : (
          <>
            {GROUPS.map((g) => (
              <div key={g.title}>
                <h3 style={{ marginTop: 14 }}>{g.title}</h3>
                <div className="field-row">
                  {g.fields.map(([name, label, help]) => (
                    <label key={name} className="field">
                      <span>{label}</span>
                      <input type="number" step="any" value={cfg[name] ?? ""}
                             onChange={(e) => setCfg({ ...cfg, [name]: parseFloat(e.target.value || "0") })} />
                      {help && <small>{help}</small>}
                    </label>
                  ))}
                </div>
              </div>
            ))}
            <h3 style={{ marginTop: 14 }}>Switches</h3>
            {CHECKS.map(([name, label, help]) => (
              <label key={name} className="check-row" title={help}>
                <input type="checkbox" checked={!!cfg[name]}
                       onChange={(e) => setCfg({ ...cfg, [name]: e.target.checked })} />
                {label} <small className="muted">— {help}</small>
              </label>
            ))}
            {err && <div className="banner banner-warn">Validation failed: {err}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button className="btn btn-primary" onClick={save}>Save limits</button>
              <button className="btn btn-ghost btn-sm" onClick={() => { setCfg(stored); setErr(null); }}>Revert</button>
            </div>
          </>
        )}
      </div>

      <div className="grid" style={{ alignContent: "start" }}>
        <div className="card">
          <h3>Proximity to limits</h3>
          {!usage ? <div className="empty">Start the bot to see live usage</div> : (
            <>
              <Meter label="Daily loss" used={usage.daily_loss.used_pct} limit={usage.daily_loss.limit_pct} />
              <Meter label={`Drawdown ${usage.drawdown.kill_switch_enabled ? "(kill switch armed)" : "(kill switch OFF)"}`}
                     used={usage.drawdown.used_pct} limit={usage.drawdown.limit_pct} />
              <Meter label="Open positions" used={usage.open_positions.used}
                     limit={usage.open_positions.limit} unit="" />
              <Meter label="Total exposure" used={usage.total_exposure.used_pct}
                     limit={usage.total_exposure.limit_pct} />
              {usage.per_asset.map((a: any) => (
                <Meter key={a.symbol} label={`Exposure · ${a.symbol}`}
                       used={a.used_pct} limit={a.limit_pct} />
              ))}
            </>
          )}
        </div>

        <div className="card">
          <h3>Manual controls</h3>
          <p className="muted" style={{ fontSize: 12 }}>
            Emergency stop cancels <b>all open orders immediately</b> (including
            protective OCOs) and optionally market-closes every position.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-danger" onClick={() => setModal("emergency")}>⛔ Emergency stop</button>
            {killed && (
              <button className="btn" onClick={() => setModal("reset")}>Reset kill switch</button>
            )}
          </div>
        </div>

        <div className="card">
          <h3>Risk events</h3>
          {!(events?.length) ? <div className="empty">No risk events</div> : (
            <div className="feed" style={{ maxHeight: 260 }}>
              {(events ?? []).map((ev, i) => (
                <div key={i} className="feed-item">
                  <span className="when">{fmtTime(ev.ts)}</span>
                  <b>{ev.kind}</b> {JSON.stringify(ev.detail).slice(0, 220)}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {modal === "emergency" && (
        <ConfirmModal title="Emergency stop" confirmLabel="STOP EVERYTHING" danger
                      requireText={status && !status.testnet ? "STOP" : undefined}
                      onClose={() => setModal(null)}
                      onConfirm={async () => {
                        try {
                          const r = await post("/bot/emergency-stop", { flatten });
                          pushToast({ kind: "kill", title: "Emergency stop executed",
                                      body: `Canceled ${r.orders_canceled} orders` +
                                            (flatten ? `, closed ${r.positions_closed} positions` : "") });
                        } catch (e: any) {
                          pushToast({ kind: "risk", title: "Emergency stop failed", body: e.message });
                        }
                      }}>
          <p>Cancels every open order now. The bot goes to STOPPED.</p>
          <label className="check-row">
            <input type="checkbox" checked={flatten} onChange={(e) => setFlatten(e.target.checked)} />
            Also market-close all open positions (flatten)
          </label>
          {!flatten && <p className="muted">Without flatten, positions stay open <b>without exchange-side protection</b> until you restart the bot.</p>}
        </ConfirmModal>
      )}
      {modal === "reset" && (
        <ConfirmModal title="Reset kill switch" confirmLabel="Reset" danger
                      onClose={() => setModal(null)}
                      onConfirm={async () => {
                        try {
                          await post("/bot/reset-kill");
                          pushToast({ kind: "info", title: "Kill switch reset", body: "Peak equity re-anchored. Press Start when ready." });
                        } catch (e: any) {
                          pushToast({ kind: "risk", title: "Reset failed", body: e.message });
                        }
                      }}>
          <p>
            This re-anchors peak equity to the current value and returns the bot to
            STOPPED. Review what caused the drawdown before trading again.
          </p>
        </ConfirmModal>
      )}
    </div>
  );
}
