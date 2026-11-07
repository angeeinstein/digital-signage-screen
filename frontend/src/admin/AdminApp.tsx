import { useCallback, useEffect, useState, type ComponentType } from "react";
import {
  Activity,
  BusFront,
  CloudSun,
  GraduationCap,
  LogOut,
  MapPin,
  Megaphone,
  Monitor,
  MonitorUp,
  Newspaper,
  Plane,
  Save,
  Tv,
} from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Config } from "../lib/types";
import { Announcements } from "./Announcements";
import { MonitoringCard, ScreenCard } from "./ScreenCard";
import { ShareCard } from "./ShareCard";
import { Login } from "./Login";
import { PasswordDialog } from "./PasswordDialog";
import { RouteCache } from "./RouteCache";
import { Sections, type SettingsGroup } from "./Sections";
import { StatusOverview } from "./StatusOverview";
import "./admin.css";

type Session = { logged_in: boolean; username?: string; must_change?: boolean };

interface Page {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  /** Config sections edited on this page (for the "unsaved" dot). */
  keys: (keyof Config)[];
}

const PAGES: { title: string; pages: Page[] }[] = [
  {
    title: "General",
    pages: [
      { id: "status", label: "Status", icon: Activity, keys: [] },
      { id: "screen", label: "Screen", icon: Tv, keys: ["monitoring"] },
      { id: "location", label: "Location & display", icon: MapPin, keys: ["location", "display"] },
    ],
  },
  {
    title: "Panels",
    pages: [
      { id: "flights", label: "Flights", icon: Plane, keys: ["flights", "routes"] },
      { id: "weather", label: "Weather", icon: CloudSun, keys: ["weather"] },
      { id: "transport", label: "Departures", icon: BusFront, keys: ["transport"] },
      { id: "lectures", label: "Lectures", icon: GraduationCap, keys: ["timetable"] },
    ],
  },
  {
    title: "Extras",
    pages: [
      { id: "announcements", label: "Announcements", icon: Megaphone, keys: ["announcements"] },
      { id: "ticker", label: "News ticker", icon: Newspaper, keys: ["ticker"] },
      { id: "share", label: "Screen sharing", icon: MonitorUp, keys: ["share"] },
    ],
  },
];

const ALL_PAGES = PAGES.flatMap((g) => g.pages);

function pageFromHash(): string {
  const id = window.location.hash.replace(/^#/, "");
  return ALL_PAGES.some((p) => p.id === id) ? id : "status";
}

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
  const [page, setPage] = useState(pageFromHash);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // On phones the menu is a scrolling row; keep the selected item visible.
  useEffect(() => {
    const el = document.querySelector<HTMLElement>(".admin-nav-item.active");
    el?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [page]);

  const go = (id: string) => {
    setPage(id);
    history.replaceState(null, "", `#${id}`);
    window.scrollTo({ top: 0 });
  };

  const unsaved = (p: Page) =>
    !!draft && !!saved && p.keys.some((k) => JSON.stringify(draft[k]) !== JSON.stringify(saved[k]));

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

      <div className="admin-layout">
        <nav className="admin-nav" aria-label="Settings sections">
          {PAGES.map((g) => (
            <div key={g.title} className="admin-nav-group">
              <div className="admin-nav-title">{g.title}</div>
              {g.pages.map((p) => (
                <button
                  key={p.id}
                  className={`admin-nav-item${page === p.id ? " active" : ""}`}
                  aria-current={page === p.id ? "page" : undefined}
                  onClick={() => go(p.id)}
                >
                  <p.icon className="icon" />
                  <span>{p.label}</span>
                  {unsaved(p) && <span className="unsaved-dot" title="Unsaved changes" />}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="admin-content">
          {page === "status" && <StatusOverview />}
          {page === "screen" && <ScreenCard />}
          {draft && page === "screen" && <MonitoringCard draft={draft} setDraft={setDraft} />}
          {page !== "status" && !draft && <div className="card">Loading…</div>}
          {draft && page === "announcements" && (
            <>
              <Announcements />
              <Sections draft={draft} setDraft={setDraft} group="slides" />
            </>
          )}
          {draft && page === "share" && <ShareCard draft={draft} setDraft={setDraft} />}
          {draft && ["location", "weather", "flights", "transport", "lectures", "ticker"].includes(page) && (
            <Sections draft={draft} setDraft={setDraft} group={page as SettingsGroup} />
          )}
          {page === "flights" && <RouteCache />}
        </div>
      </div>

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
