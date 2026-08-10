import { ReactNode, useState } from "react";
import { fmtMoney } from "../api/client";

/* ── Environment + status badges ── */
export function EnvBadge({ testnet }: { testnet: boolean }) {
  return testnet ? (
    <span className="pill pill-testnet" title="Paper trading against the Binance Spot Testnet">
      ◈ TESTNET
    </span>
  ) : (
    <span className="pill pill-live" title="Real funds at risk — orders go to live Binance">
      ● LIVE TRADING
    </span>
  );
}

const STATUS_STYLE: Record<string, { cls: string; icon: string }> = {
  RUNNING: { cls: "pill-good", icon: "▶" },
  PAUSED: { cls: "pill-warn", icon: "⏸" },
  STOPPED: { cls: "pill-muted", icon: "⏹" },
  DAILY_HALT: { cls: "pill-serious", icon: "⚠" },
  KILLED: { cls: "pill-crit", icon: "⛔" },
};

export function StatusPill({ status, reason }: { status: string; reason: string }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.STOPPED;
  return (
    <span className={`pill ${s.cls}`} title={reason}>
      <span className="dot" /> {s.icon} {status.replace("_", " ")}
    </span>
  );
}

/* ── Stat tile (hero numbers) ── */
export function StatTile({ label, value, sub, valueClass }: {
  label: string; value: ReactNode; sub?: ReactNode; valueClass?: string;
}) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className={`value num ${valueClass ?? ""}`}>{value}</div>
      {sub !== undefined && <div className="sub">{sub}</div>}
    </div>
  );
}

/* ── Risk meter: color + icon + explicit text (never color alone) ── */
export function Meter({ label, used, limit, unit = "%", inverse = false }: {
  label: string; used: number; limit: number; unit?: string; inverse?: boolean;
}) {
  const ratio = limit > 0 ? (used / limit) * 100 : 0;
  const state = ratio >= 100 ? "crit" : ratio >= 85 ? "serious" : ratio >= 60 ? "warn" : "good";
  const color = { good: "var(--good)", warn: "var(--warn)", serious: "var(--serious)", crit: "var(--crit)" }[state];
  const icon = { good: "✓", warn: "△", serious: "⚠", crit: "⛔" }[state];
  const word = { good: "ok", warn: "elevated", serious: "near limit", crit: "LIMIT HIT" }[state];
  return (
    <div className="meter">
      <div className="head">
        <span>{icon} {label} <span className="muted">— {word}</span></span>
        <span className="val">
          {fmtMoney(used, unit === "%" ? 2 : 0)}{unit} / {fmtMoney(limit, unit === "%" ? 1 : 0)}{unit}
        </span>
      </div>
      <div className="track">
        <div className="fill" style={{ width: `${Math.min(100, Math.max(ratio, inverse ? 0 : 1.5))}%`, background: color }} />
      </div>
    </div>
  );
}

/* ── Confirm modal ── */
export function ConfirmModal({ title, children, confirmLabel, danger, requireText, onConfirm, onClose }: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  requireText?: string;        // e.g. "STOP" for live-mode emergency actions
  onConfirm: () => void;
  onClose: () => void;
}) {
  const [typed, setTyped] = useState("");
  const blocked = !!requireText && typed !== requireText;
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        {children}
        {requireText && (
          <label className="field" style={{ marginTop: 10 }}>
            <span>Type <b>{requireText}</b> to confirm (live mode)</span>
            <input value={typed} onChange={(e) => setTyped(e.target.value)}
                   placeholder={requireText} autoFocus />
          </label>
        )}
        <div className="actions">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className={`btn ${danger ? "btn-danger" : "btn-primary"}`}
                  disabled={blocked}
                  onClick={() => { onConfirm(); onClose(); }}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
