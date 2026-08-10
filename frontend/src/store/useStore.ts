import { create } from "zustand";
import type { RiskUsage, ScannedSymbol, StatusPayload, WsEvent } from "../api/types";

export interface FeedItem {
  id: number;
  ts: string;
  kind: string;        // signal | order | trade | risk | error
  text: string;
  dim?: boolean;       // HOLD signals render dimmed
}

export interface Toast {
  id: number;
  kind: string;        // fill | stop_loss | risk | kill | info
  title: string;
  body: string;
}

export interface LiveCandle {
  seq: number;
  symbol: string;
  tf: string;
  t: number; o: number; h: number; l: number; c: number; v: number;
}

interface AppState {
  status: StatusPayload | null;
  usage: RiskUsage | null;
  prices: Record<string, number>;
  scanned: ScannedSymbol[];
  equityLive: { ts: number; equity: number }[];
  feed: FeedItem[];
  toasts: Toast[];
  lastCandle: LiveCandle | null;
  wsConnected: boolean;
  authRequired: boolean;
  versions: { trades: number; positions: number; orders: number; strategies: number; risk: number };

  setStatus(s: StatusPayload): void;
  setWsConnected(b: boolean): void;
  setAuthRequired(b: boolean): void;
  applyEvent(e: WsEvent): void;
  pushToast(t: Omit<Toast, "id">): void;
  dismissToast(id: number): void;
}

let seq = 1;

export const useStore = create<AppState>((set, get) => ({
  status: null,
  usage: null,
  prices: {},
  scanned: [],
  equityLive: [],
  feed: [],
  toasts: [],
  lastCandle: null,
  wsConnected: false,
  authRequired: false,
  versions: { trades: 0, positions: 0, orders: 0, strategies: 0, risk: 0 },

  setStatus: (status) => set({ status }),
  setWsConnected: (wsConnected) => set({ wsConnected }),
  setAuthRequired: (authRequired) => set({ authRequired }),

  pushToast: (t) => {
    const id = seq++;
    set({ toasts: [...get().toasts.slice(-4), { ...t, id }] });
    setTimeout(() => get().dismissToast(id), t.kind === "kill" ? 30_000 : 8_000);
  },
  dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),

  applyEvent: (e) => {
    const st = get();
    const bump = (k: keyof AppState["versions"]) =>
      set({ versions: { ...get().versions, [k]: get().versions[k] + 1 } });
    const pushFeed = (kind: string, text: string, dim = false) =>
      set({ feed: [{ id: seq++, ts: e.ts || new Date().toISOString(), kind, text, dim },
                   ...get().feed].slice(0, 120) });

    switch (e.type) {
      case "hello":
        set({ status: e.data.status });
        for (const past of e.data.recent || []) st.applyEvent(past);
        break;
      case "status":
        set({ status: e.data });
        break;
      case "tick":
        set({ prices: { ...st.prices, [e.data.symbol]: e.data.price } });
        break;
      case "candle":
        set({ lastCandle: { seq: seq++, symbol: e.data.symbol, tf: e.data.tf,
                            t: e.data.t, o: e.data.o, h: e.data.h, l: e.data.l,
                            c: e.data.c, v: e.data.v } });
        break;
      case "equity":
        set({
          equityLive: [...st.equityLive, { ts: Date.now(), equity: e.data.equity }].slice(-600),
        });
        break;
      case "signal": {
        const d = e.data;
        pushFeed("signal", `${d.strategy} · ${d.symbol} · ${d.action} — ${d.reason}`,
                 d.action === "HOLD");
        break;
      }
      case "order": {
        const d = e.data;
        pushFeed("order", `${d.symbol} ${d.side} ${d.type} (${d.purpose}) → ${d.status}`);
        bump("orders");
        break;
      }
      case "trade": {
        const d = e.data;
        pushFeed("trade", `CLOSED ${d.symbol} ${d.strategy}: ${d.pnl >= 0 ? "+" : ""}${d.pnl} USDT (${d.exit_kind})`);
        bump("trades"); bump("positions");
        break;
      }
      case "position":
        bump("positions");
        break;
      case "risk":
        if (e.data.kind === "USAGE") set({ usage: e.data.usage });
        else {
          pushFeed("risk", `RISK ${e.data.kind}: ${e.data.reason || JSON.stringify(e.data)}`);
          bump("risk");
        }
        break;
      case "scanner":
        set({ scanned: e.data.symbols || [] });
        break;
      case "alert":
        st.pushToast({ kind: e.data.kind || "info", title: e.data.title || "Alert",
                       body: e.data.body || "" });
        break;
      case "error":
        pushFeed("error", `ERROR ${e.data.where || ""}: ${e.data.error || ""}`);
        break;
      default:
        break;
    }
  },
}));
