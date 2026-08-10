import { API_BASE, getToken } from "./client";
import { useStore } from "../store/useStore";

let socket: WebSocket | null = null;
let backoff = 1000;
let closedByApp = false;

export function connectWs() {
  closedByApp = false;
  const base = API_BASE
    ? API_BASE.replace(/^http/, "ws")
    : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;
  const token = getToken();
  const url = `${base}/ws/stream${token ? `?token=${encodeURIComponent(token)}` : ""}`;
  socket = new WebSocket(url);

  socket.onopen = () => {
    backoff = 1000;
    useStore.getState().setWsConnected(true);
  };
  socket.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data);
      if (event.type !== "ping") useStore.getState().applyEvent(event);
    } catch { /* ignore malformed frames */ }
  };
  socket.onclose = (ev) => {
    useStore.getState().setWsConnected(false);
    if (closedByApp) return;
    if (ev.code === 4401) {
      useStore.getState().setAuthRequired(true);
      return; // reconnect after the user provides a token
    }
    setTimeout(connectWs, backoff);
    backoff = Math.min(backoff * 2, 30_000);
  };
  socket.onerror = () => socket?.close();
}

export function reconnectWs() {
  closedByApp = true;
  socket?.close();
  connectWs();
}
