import { FormEvent, useState } from "react";
import { setToken } from "../api/client";

export function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || "login failed");
      setToken(body.token);
      location.reload(); // clean boot with the session in place
    } catch (err: any) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="modal-back" style={{ background: "var(--bg)" }}>
      <form className="modal" onSubmit={submit} style={{ width: "min(380px, 92vw)" }}>
        <div className="brand" style={{ padding: 0, marginBottom: 14 }}>
          📈 Binance Trader
          <small>algorithmic spot bot — sign in</small>
        </div>
        <label className="field">
          <span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)}
                 autoComplete="username" autoFocus />
        </label>
        <label className="field">
          <span>Password</span>
          <input type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)}
                 autoComplete="current-password" />
        </label>
        {error && <div className="banner banner-warn">{error}</div>}
        <button className="btn btn-primary" style={{ width: "100%" }}
                disabled={busy || !username || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="disclaimer" style={{ marginTop: 12 }}>
          First boot: credentials come from AUTH_USERNAME / AUTH_PASSWORD in .env —
          if no password was set, the generated one was printed to the backend console.
        </p>
      </form>
    </div>
  );
}
