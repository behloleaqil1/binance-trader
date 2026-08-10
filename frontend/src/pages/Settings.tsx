import { useEffect, useState } from "react";
import { post, put, useApi } from "../api/client";
import { EnvBadge } from "../components/common";
import { useStore } from "../store/useStore";

interface SettingsView {
  testnet: boolean;
  api_host: string;
  api_port: number;
  quote_asset: string;
  auto_start: boolean;
  cancel_orphan_orders: boolean;
  telegram_chat_id: string;
  alert_webhook_url: string;
  whatsapp_phone: string;
  meta_wa_phone_id: string;
  meta_wa_template: string;
  api_key_fingerprint: string;
  api_secret_set: boolean;
  telegram_token_set: boolean;
  whatsapp_apikey_set: boolean;
  meta_wa_token_set: boolean;
  username: string;
}

export function Settings() {
  const status = useStore((s) => s.status);
  const pushToast = useStore((s) => s.pushToast);
  const { data, reload } = useApi<SettingsView>("/settings");

  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [tgToken, setTgToken] = useState("");
  const [tgChat, setTgChat] = useState<string | null>(null);
  const [webhook, setWebhook] = useState<string | null>(null);
  const [waPhone, setWaPhone] = useState<string | null>(null);
  const [waKey, setWaKey] = useState("");
  const [metaToken, setMetaToken] = useState("");
  const [metaPhoneId, setMetaPhoneId] = useState<string | null>(null);
  const [autoStart, setAutoStart] = useState<boolean | null>(null);
  const [cancelOrphans, setCancelOrphans] = useState<boolean | null>(null);
  const [curPw, setCurPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [newPw2, setNewPw2] = useState("");
  const [newUser, setNewUser] = useState("");

  useEffect(() => {
    if (data) {
      setTgChat((v) => v ?? data.telegram_chat_id);
      setWebhook((v) => v ?? data.alert_webhook_url);
      setWaPhone((v) => v ?? data.whatsapp_phone);
      setMetaPhoneId((v) => v ?? data.meta_wa_phone_id);
      setAutoStart((v) => v ?? data.auto_start);
      setCancelOrphans((v) => v ?? data.cancel_orphan_orders);
      setNewUser((v) => v || data.username);
    }
  }, [data]);

  const running = status ? !["STOPPED", "KILLED"].includes(status.status) : false;

  const saveSettings = async (body: Record<string, unknown>, okMsg: string) => {
    try {
      await put("/settings", body);
      pushToast({ kind: "info", title: okMsg, body: "" });
      reload();
    } catch (e: any) {
      pushToast({ kind: "risk", title: "Save failed", body: e.message });
    }
  };

  const changePassword = async () => {
    if (newPw !== newPw2) {
      pushToast({ kind: "risk", title: "Passwords don't match", body: "" });
      return;
    }
    try {
      await post("/auth/change-password", {
        current_password: curPw, new_password: newPw,
        new_username: newUser || undefined,
      });
      pushToast({ kind: "info", title: "Credentials updated",
                  body: "Other sessions were signed out." });
      setCurPw(""); setNewPw(""); setNewPw2("");
      reload();
    } catch (e: any) {
      pushToast({ kind: "risk", title: "Change failed", body: e.message });
    }
  };

  if (!data) return <div className="empty">Loading…</div>;

  return (
    <div className="grid cols-2">
      <div className="grid" style={{ alignContent: "start" }}>
        <div className="card">
          <h3>Environment</h3>
          <p style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <EnvBadge testnet={data.testnet} />
            <span className="muted">API on {data.api_host}:{data.api_port}</span>
          </p>
          <p className="muted" style={{ fontSize: 12 }}>
            The TESTNET/LIVE switch is deliberately <b>not</b> editable here: going
            live requires editing <code>TESTNET</code> in <code>.env</code> and
            restarting, so a compromised dashboard login can never move the bot onto
            real funds. See the go-live checklist in the README first.
          </p>
        </div>

        <div className="card">
          <h3>Binance API keys</h3>
          <p className="muted" style={{ fontSize: 12 }}>
            Current key: <b>{data.api_key_fingerprint}</b>
            {" · "}secret {data.api_secret_set ? "set" : "not set"}. Keys are
            write-only — they can be replaced here but never read back. Create keys
            with <b>trading enabled, withdrawals disabled, IP-whitelisted</b>.
          </p>
          {data.testnet && (
            <div className="banner banner-info">
              TESTNET mode: use keys generated at <b>testnet.binance.vision</b>
              {" "}(GitHub login) — keys from the real Binance site are rejected
              with error −2015.
            </div>
          )}
          {running && (
            <div className="banner banner-warn">Stop the bot to change API keys.</div>
          )}
          <div className="field-row">
            <label className="field"><span>API key</span>
              <input type="password" value={apiKey} placeholder="unchanged"
                     autoComplete="off" onChange={(e) => setApiKey(e.target.value)} /></label>
            <label className="field"><span>API secret</span>
              <input type="password" value={apiSecret} placeholder="unchanged"
                     autoComplete="off" onChange={(e) => setApiSecret(e.target.value)} /></label>
          </div>
          <button className="btn btn-primary btn-sm" disabled={running || (!apiKey && !apiSecret)}
                  onClick={() => {
                    const body: Record<string, unknown> = {};
                    if (apiKey) body.binance_api_key = apiKey.trim();
                    if (apiSecret) body.binance_api_secret = apiSecret.trim();
                    saveSettings(body, "API keys updated");
                    setApiKey(""); setApiSecret("");
                  }}>
            Save keys
          </button>
        </div>

        <div className="card">
          <h3>Engine</h3>
          <label className="check-row">
            <input type="checkbox" checked={!!autoStart}
                   onChange={(e) => setAutoStart(e.target.checked)} />
            Auto-start trading when the server boots
          </label>
          <label className="check-row">
            <input type="checkbox" checked={!!cancelOrphans}
                   onChange={(e) => setCancelOrphans(e.target.checked)} />
            Cancel orphaned bot orders found during startup reconciliation
          </label>
          <button className="btn btn-primary btn-sm"
                  onClick={() => saveSettings({ auto_start: !!autoStart,
                                                cancel_orphan_orders: !!cancelOrphans },
                                              "Engine settings saved")}>
            Save engine settings
          </button>
        </div>
      </div>

      <div className="grid" style={{ alignContent: "start" }}>
        <div className="card">
          <h3>Alerting</h3>
          <p className="muted" style={{ fontSize: 12 }}>
            Telegram and/or webhook notifications for fills, stop-losses, daily
            halts, kill-switch and emergency events. Applied immediately.
          </p>
          <div className="field-row">
            <label className="field"><span>Telegram bot token {data.telegram_token_set ? "(set)" : ""}</span>
              <input type="password" value={tgToken} placeholder={data.telegram_token_set ? "unchanged" : "from @BotFather"}
                     autoComplete="off" onChange={(e) => setTgToken(e.target.value)} /></label>
            <label className="field"><span>Telegram chat id</span>
              <input value={tgChat ?? ""} onChange={(e) => setTgChat(e.target.value)} /></label>
          </div>
          <label className="field"><span>Webhook URL (receives JSON POSTs)</span>
            <input value={webhook ?? ""} placeholder="https://…"
                   onChange={(e) => setWebhook(e.target.value)} /></label>
          <div className="field-row">
            <label className="field"><span>WhatsApp phone (intl. format)</span>
              <input value={waPhone ?? ""} placeholder="+923001234567"
                     onChange={(e) => setWaPhone(e.target.value)} /></label>
            <label className="field"><span>CallMeBot API key {data.whatsapp_apikey_set ? "(set)" : ""}</span>
              <input type="password" value={waKey}
                     placeholder={data.whatsapp_apikey_set ? "unchanged" : "reply from CallMeBot"}
                     autoComplete="off" onChange={(e) => setWaKey(e.target.value)} /></label>
          </div>
          <p className="muted" style={{ fontSize: 12 }}>
            WhatsApp setup: message “I allow callmebot to send me messages” to
            +34 623 76 13 63 on WhatsApp once — the reply contains your API key.
            (Number current as of Aug 2026 — if no reply, check callmebot.com.)
          </p>
          <div className="field-row">
            <label className="field"><span>Meta Cloud API token {data.meta_wa_token_set ? "(set)" : ""}</span>
              <input type="password" value={metaToken}
                     placeholder={data.meta_wa_token_set ? "unchanged" : "EAA… from developers.facebook.com"}
                     autoComplete="off" onChange={(e) => setMetaToken(e.target.value)} /></label>
            <label className="field"><span>Meta phone number ID</span>
              <input value={metaPhoneId ?? ""} placeholder="from WhatsApp → API Setup"
                     onChange={(e) => setMetaPhoneId(e.target.value)} /></label>
          </div>
          <p className="muted" style={{ fontSize: 12 }}>
            Meta WhatsApp (official): uses the same WhatsApp phone number above
            as the recipient. Alternative to CallMeBot — either works alone.
          </p>
          <button className="btn btn-primary btn-sm"
                  onClick={() => {
                    const body: Record<string, unknown> = {
                      telegram_chat_id: tgChat ?? "", alert_webhook_url: webhook ?? "",
                      whatsapp_phone: (waPhone ?? "").trim(),
                    };
                    if (tgToken) body.telegram_bot_token = tgToken.trim();
                    if (waKey) body.whatsapp_apikey = waKey.trim();
                    if (metaToken) body.meta_wa_token = metaToken.trim();
                    if (metaPhoneId !== null) body.meta_wa_phone_id = metaPhoneId.trim();
                    saveSettings(body, "Alerting saved");
                    setTgToken(""); setWaKey(""); setMetaToken("");
                  }}>
            Save alerting
          </button>
        </div>

        <div className="card">
          <h3>Dashboard login</h3>
          <div className="field-row">
            <label className="field"><span>Username</span>
              <input value={newUser} autoComplete="username"
                     onChange={(e) => setNewUser(e.target.value)} /></label>
            <label className="field"><span>Current password</span>
              <input type="password" value={curPw} autoComplete="current-password"
                     onChange={(e) => setCurPw(e.target.value)} /></label>
            <label className="field"><span>New password (min 8 chars)</span>
              <input type="password" value={newPw} autoComplete="new-password"
                     onChange={(e) => setNewPw(e.target.value)} /></label>
            <label className="field"><span>Repeat new password</span>
              <input type="password" value={newPw2} autoComplete="new-password"
                     onChange={(e) => setNewPw2(e.target.value)} /></label>
          </div>
          <button className="btn btn-primary btn-sm"
                  disabled={!curPw || newPw.length < 8 || newPw !== newPw2}
                  onClick={changePassword}>
            Update credentials
          </button>
        </div>
      </div>
    </div>
  );
}
