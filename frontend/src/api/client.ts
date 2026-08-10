import { useCallback, useEffect, useRef, useState } from "react";
import { useStore } from "../store/useStore";

// Same-origin by default (dev proxy / backend-served); override at build time
// with VITE_API_BASE when the dashboard is hosted apart from the backend.
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

const TOKEN_KEY = "session_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY) || "";
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) || {}),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api${path}`, { ...init, headers });
  if (res.status === 401) {
    useStore.getState().setAuthRequired(true);
    throw new ApiError(401, "authentication required");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export const post = <T = any>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const del = <T = any>(path: string) => api<T>(path, { method: "DELETE" });

/** Fetch-on-mount hook; refetches whenever `refreshKey` changes. */
export function useApi<T = any>(path: string | null, refreshKey: unknown = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const alive = useRef(true);
  // Re-arm on every mount: StrictMode mounts → cleans up → mounts again, and
  // the ref survives that cycle — without this line the second mount would be
  // permanently "dead" and all fetched data silently discarded.
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const reload = useCallback(() => {
    if (!path) return;
    setLoading(true);
    api<T>(path)
      .then((d) => { if (alive.current) { setData(d); setError(null); } })
      .catch((e: Error) => { if (alive.current) setError(e.message); })
      .finally(() => { if (alive.current) setLoading(false); });
  }, [path]);

  useEffect(() => { reload(); }, [reload, refreshKey]);
  return { data, error, loading, reload };
}

/* ── formatting helpers ── */
export const fmtMoney = (v: number | null | undefined, dp = 2) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });

/** Signed formatting: the sign is the accessible channel, color is backup. */
export const fmtSigned = (v: number, dp = 2) => `${v >= 0 ? "+" : "−"}${fmtMoney(Math.abs(v), dp)}`;
export const fmtPct = (v: number, dp = 2) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(dp)}%`;
export const deltaClass = (v: number) => (v >= 0 ? "delta-up" : "delta-down");

export const fmtQty = (v: number) =>
  v >= 1 ? v.toLocaleString("en-US", { maximumFractionDigits: 4 }) : v.toPrecision(4);

export const fmtTime = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", {
    month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
};

export function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const cols = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
