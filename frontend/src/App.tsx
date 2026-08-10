import { useEffect, useState } from "react";
import { clearToken, fmtMoney, getToken, post } from "./api/client";
import { connectWs } from "./api/ws";
import { ConfirmModal, EnvBadge, StatusPill } from "./components/common";
import { Backtesting } from "./pages/Backtesting";
import { Login } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { Risk } from "./pages/Risk";
import { Settings } from "./pages/Settings";
import { Strategies } from "./pages/Strategies";
import { Trades } from "./pages/Trades";
import { useStore } from "./store/useStore";

const PAGES = [
  { id: "overview", label: "Overview", icon: "◫" },
  { id: "trades", label: "Trades", icon: "⇄" },
  { id: "strategies", label: "Strategies", icon: "ƒ" },
  { id: "backtesting", label: "Backtesting", icon: "◷" },
  { id: "risk", label: "Risk", icon: "🛡" },
  { id: "settings", label: "Settings", icon: "⚙" },
] as const;

type PageId = (typeof PAGES)[number]["id"];

function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismissToast);
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind === "kill" ? "kill" : t.kind === "risk" || t.kind === "stop_loss" ? "risk" : ""}`}
             onClick={() => dismiss(t.id)}>
          <div className="t">{t.title}</div>
          {t.body && <div className="b">{t.body}</div>}
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const status = useStore((s) => s.status);
  const wsConnected = useStore((s) => s.wsConnected);
  const authRequired = useStore((s) => s.authRequired);
  const pushToast = useStore((s) => s.pushToast);
  const [page, setPage] = useState<PageId>(
    () => ((location.hash.replace("#", "") || "overview") as PageId));
  const [emergency, setEmergency] = useState(false);
  const [flatten, setFlatten] = useState(false);
  const authed = !!getToken() && !authRequired;

  useEffect(() => { if (authed) connectWs(); }, [authed]);
  useEffect(() => {
    const onHash = () => setPage((location.hash.replace("#", "") || "overview") as PageId);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  if (!authed) {
    if (authRequired) clearToken(); // stale/expired session — force re-login
    return <Login />;
  }

  const nav = (id: PageId) => { location.hash = id; setPage(id); };

  const ctl = (path: string, okMsg: string) => async () => {
    try {
      await post(path);
      pushToast({ kind: "info", title: okMsg, body: "" });
    } catch (e: any) {
      pushToast({ kind: "risk", title: "Action failed", body: e.message });
    }
  };

  const logout = async () => {
    try { await post("/auth/logout"); } catch { /* session may already be dead */ }
    clearToken();
    location.reload();
  };

  const st = status?.status ?? "STOPPED";
  const running = st === "RUNNING" || st === "DAILY_HALT";
  const Page = { overview: Overview, trades: Trades, strategies: Strategies,
                 backtesting: Backtesting, risk: Risk, settings: Settings }[page] ?? Overview;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">📈 Binance Trader
          <small>algorithmic spot bot</small>
        </div>
        {PAGES.map((p) => (
          <button key={p.id} className={`nav-item ${page === p.id ? "active" : ""}`}
                  onClick={() => nav(p.id)}>
            <span>{p.icon}</span> {p.label}
          </button>
        ))}
        <div className="foot">
          <div>{wsConnected ? "● live stream connected" : "○ stream reconnecting…"}</div>
          <button className="btn btn-ghost btn-sm" style={{ margin: "8px 0", width: "100%" }}
                  onClick={logout}>Sign out</button>
          <div>
            Trading involves substantial risk of loss. Nothing here is financial advice.
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          {status && <EnvBadge testnet={status.testnet} />}
          <StatusPill status={st} reason={status?.status_reason ?? ""} />
          {status && status.equity > 0 && (
            <span className="muted num">equity {fmtMoney(status.equity)} USDT</span>
          )}
          <span className="spacer" />
          {!status?.has_keys && (
            <button className="pill pill-warn" style={{ cursor: "pointer", background: "none" }}
                    title="Add Binance API keys on the Settings page"
                    onClick={() => nav("settings")}>
              ⚠ no API keys
            </button>
          )}
          {st === "KILLED" ? (
            <button className="btn btn-sm" onClick={() => nav("risk")}>⛔ Kill switch — review</button>
          ) : running ? (
            <>
              <button className="btn btn-sm" onClick={ctl("/bot/pause", "Paused — no new entries")}>⏸ Pause</button>
              <button className="btn btn-sm" onClick={ctl("/bot/stop", "Stopped — OCO protection stays on Binance")}>⏹ Stop</button>
            </>
          ) : st === "PAUSED" ? (
            <>
              <button className="btn btn-primary btn-sm" onClick={ctl("/bot/resume", "Resumed")}>▶ Resume</button>
              <button className="btn btn-sm" onClick={ctl("/bot/stop", "Stopped")}>⏹ Stop</button>
            </>
          ) : (
            <button className="btn btn-primary btn-sm"
                    disabled={!status?.has_keys}
                    onClick={ctl("/bot/start", "Bot started")}>▶ Start</button>
          )}
          <button className="btn btn-danger btn-sm" onClick={() => setEmergency(true)}>
            ⛔ EMERGENCY STOP
          </button>
        </header>

        <main className="content">
          {status && st === "DAILY_HALT" && (
            <div className="banner banner-warn">
              ⚠ Daily loss limit reached — new entries are halted until the next UTC
              day. Exits and protective orders remain active. ({status.status_reason})
            </div>
          )}
          {status && st === "KILLED" && (
            <div className="banner banner-crit">
              ⛔ KILL SWITCH — {status.status_reason} · Reset it on the Risk page after
              reviewing what happened.
            </div>
          )}
          {status && !status.testnet && (
            <div className="banner banner-crit">
              ● LIVE MODE — orders use real funds on Binance. Position sizes, limits
              and the kill switch on the Risk page apply.
            </div>
          )}
          <Page />
        </main>
      </div>

      {emergency && (
        <ConfirmModal title="Emergency stop" confirmLabel="STOP EVERYTHING" danger
                      requireText={status && !status.testnet ? "STOP" : undefined}
                      onClose={() => setEmergency(false)}
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
          <p>Immediately cancels <b>every open order</b> (including protective
             OCOs) and stops the bot.</p>
          <label className="check-row">
            <input type="checkbox" checked={flatten} onChange={(e) => setFlatten(e.target.checked)} />
            Also market-close all open positions (flatten)
          </label>
          {!flatten && (
            <p className="muted">
              Without flatten, positions remain open <b>without exchange-side
              protection</b> until the bot is restarted.
            </p>
          )}
        </ConfirmModal>
      )}
      <Toasts />
    </div>
  );
}
