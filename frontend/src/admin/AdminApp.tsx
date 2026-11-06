import { useCallback, useEffect, useState } from "react";
import { LogOut, Monitor, Save } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Config } from "../lib/types";
import { Login } from "./Login";
import { PasswordDialog } from "./PasswordDialog";
import { RouteCache } from "./RouteCache";
import { Sections } from "./Sections";
import { StatusOverview } from "./StatusOverview";
import "./admin.css";

type Session = { logged_in: boolean; username?: string; must_change?: boolean };

export default function AdminApp() {
  const [session, setSession] = useState<Session | null>(null);

  const refresh = useCallback(async () => {
    try {
      setSession(await api<Session>("/api/auth/session"));
    } catch {
      setSession({ logged_in: false });
    }
  }, []);

  useEffect(() => {
    document.title = "Dashboard admin";
    refresh();
  }, [refresh]);

  if (!session) return null;
  if (!session.logged_in) return <Login onLoggedIn={refresh} />;
  return <AdminPanel session={session} onSessionChange={refresh} />;
}

function AdminPanel({ session, onSessionChange }: { session: Session; onSessionChange: () => void }) {
  const [saved, setSaved] = useState<Config | null>(null);
  const [draft, setDraft] = useState<Config | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [pwOpen, setPwOpen] = useState(!!session.must_change);

  useEffect(() => {
    api<{ config: Config }>("/api/admin/config")
      .then((r) => {
        setSaved(r.config);
        setDraft(r.config);
      })
      .catch((e) => setNotice({ kind: "error", text: `Could not load configuration: ${e.message}` }));
  }, []);

  const dirty = !!draft && JSON.stringify(draft) !== JSON.stringify(saved);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const r = await api<{ config: Config }>("/api/admin/config", { method: "PUT", body: { config: draft } });
      setSaved(r.config);
      setDraft(r.config);
      setNotice({ kind: "ok", text: "Saved. The display updates within a few seconds." });
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    onSessionChange();
  };

  return (
    <div className="admin">
      <header className="admin-top">
        <h1>Dashboard settings</h1>
        <nav>
          <a className="btn btn-ghost" href="/" target="_blank" rel="noreferrer">
            <Monitor className="icon" /> Open display
          </a>
          <button className="btn btn-ghost" onClick={() => setPwOpen(true)}>
            Account
          </button>
          <button className="btn btn-ghost" onClick={logout}>
            <LogOut className="icon" /> Log out
          </button>
        </nav>
      </header>

      {session.must_change && (
        <div className="alert warn">You are using the default password. Please change it now.</div>
      )}
      {notice && (
        <div className={`alert ${notice.kind}`} role="status" onClick={() => setNotice(null)}>
          {notice.text}
        </div>
      )}

      <StatusOverview />

      {draft ? <Sections draft={draft} setDraft={setDraft} /> : <div className="card">Loading…</div>}

      <RouteCache />

      <div className={`save-bar${dirty ? " dirty" : ""}`}>
        <span>{dirty ? "You have unsaved changes" : "All changes saved"}</span>
        <button className="btn btn-secondary" disabled={!dirty || saving} onClick={() => setDraft(saved)}>
          Discard
        </button>
        <button className="btn btn-primary" disabled={!dirty || saving} onClick={save}>
          <Save className="icon" /> {saving ? "Saving…" : "Save"}
        </button>
      </div>

      {pwOpen && (
        <PasswordDialog
          username={session.username ?? "admin"}
          forced={!!session.must_change}
          onClose={() => setPwOpen(false)}
          onChanged={() => {
            setPwOpen(false);
            setNotice({ kind: "ok", text: "Password changed." });
            onSessionChange();
          }}
        />
      )}
    </div>
  );
}
