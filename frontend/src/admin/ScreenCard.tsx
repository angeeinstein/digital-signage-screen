import { useEffect, useRef, useState } from "react";
import { Camera, HeartPulse, Power, RefreshCw, RotateCcw, Tv } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Config, Source } from "../lib/types";
import { ago } from "../lib/format";
import { Card, NumberInput, TextInput, Toggle } from "./fields";

interface KioskStatus {
  display_online: boolean;
  display_seen: number | null;
  agent_online: boolean;
  agent_seen: number | null;
  agent: { version?: string; browser_uptime?: string };
  screenshot_at: number | null;
  screenshot_pending: boolean;
  screenshot_timeout: boolean;
  screenshot_error: string | null;
  heartbeat: Source<{ healthy: boolean }>;
}

const iso = (t: number | null) => (t ? new Date(t * 1000).toISOString() : null);

function duration(seconds: number): string {
  if (seconds < 90) return `${Math.round(seconds)} s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}

/** Remote control of the TV: status, reload/restart/reboot, screenshot. */
export function ScreenCard() {
  const [status, setStatus] = useState<KioskStatus | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [shotUrl, setShotUrl] = useState<string | null>(null);
  const shotAt = useRef<number | null>(null);
  const now = new Date();

  const load = async () => {
    try {
      const s = await api<KioskStatus>("/api/admin/kiosk");
      setStatus(s);
      if (s.screenshot_at && s.screenshot_at !== shotAt.current) {
        shotAt.current = s.screenshot_at;
        setShotUrl(`/api/admin/kiosk/screenshot?t=${s.screenshot_at}`);
      }
    } catch {
      /* keep the last status */
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

  const run = async (action: string, confirmText?: string) => {
    if (confirmText && !confirm(confirmText)) return;
    setBusy(action);
    setNotice(null);
    try {
      const r = await api<{ message: string }>(`/api/admin/kiosk/${action}`, { method: "POST" });
      setNotice({ kind: "ok", text: r.message });
      setTimeout(load, 1500);
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const agentOff = !status?.agent_online;
  const uptime = Number(status?.agent.browser_uptime ?? 0);

  return (
    <Card title="Screen" icon={<Tv className="icon" />}>
      <div className="screen-status">
        <div className={`screen-status-row ${status?.display_online ? "ok" : "bad"}`}>
          <span className="dot" />
          <strong>Dashboard on the TV</strong>
          <span className="muted">
            {!status
              ? "…"
              : status.display_online
                ? `showing, last update ${ago(iso(status.display_seen), now)}`
                : status.display_seen
                  ? `not responding since ${ago(iso(status.display_seen), now)}`
                  : "not seen since the server started"}
          </span>
        </div>
        <div className={`screen-status-row ${status?.agent_online ? "ok" : "warn"}`}>
          <span className="dot" />
          <strong>Kiosk helper</strong>
          <span className="muted">
            {!status
              ? "…"
              : status.agent_online
                ? `running${uptime ? `, browser up for ${duration(uptime)}` : ""}`
                : "not running"}
          </span>
        </div>
      </div>
      {status && agentOff && (
        <p className="help">
          The kiosk helper starts the browser on the Pi, restarts it if it crashes or freezes, and carries out the buttons
          below. Run the installer's update on the Pi (it sets the helper up) and reboot. Reloading the display works
          without it.
        </p>
      )}

      <div className="screen-actions">
        <button className="btn btn-secondary" disabled={!!busy} onClick={() => run("reload")}>
          <RefreshCw className="icon" /> Reload display
        </button>
        <button className="btn btn-secondary" disabled={!!busy || agentOff} onClick={() => run("restart-browser")}>
          <RotateCcw className="icon" /> Restart browser
        </button>
        <button
          className="btn btn-secondary"
          disabled={!!busy || agentOff}
          onClick={() => run("reboot", "Restart the Raspberry Pi now? The screen is dark for about a minute.")}
        >
          <Power className="icon" /> Restart Pi
        </button>
        <button className="btn btn-secondary" disabled={!!busy || agentOff} onClick={() => run("screenshot")}>
          <Camera className="icon" /> {status?.screenshot_pending ? "Taking screenshot…" : "Screenshot"}
        </button>
      </div>
      {status?.screenshot_error ? (
        <div className="alert error" role="status">
          Screenshot failed: {status.screenshot_error}
        </div>
      ) : status?.screenshot_timeout ? (
        <div className="alert error" role="status">
          No screenshot from the kiosk helper after 20 seconds. It may be outdated: use Restart Pi, or update and reboot.
        </div>
      ) : (
        notice &&
        !(notice.text.startsWith("Taking") && !status?.screenshot_pending) && (
          <div className={`alert ${notice.kind}`} role="status" onClick={() => setNotice(null)}>
            {notice.text}
          </div>
        )
      )}
      {shotUrl && (
        <figure className="screen-shot">
          <a href={shotUrl} target="_blank" rel="noreferrer">
            <img src={shotUrl} alt="What the TV shows" />
          </a>
          <figcaption className="muted small">Taken {ago(iso(status?.screenshot_at ?? null), now)} · click to open full size</figcaption>
        </figure>
      )}
    </Card>
  );
}

/** Heartbeat settings (saved with the Save bar). */
export function MonitoringCard({ draft, setDraft }: { draft: Config; setDraft: (c: Config) => void }) {
  const m = draft.monitoring;
  const set = <K extends keyof Config["monitoring"]>(k: K) => (v: Config["monitoring"][K]) =>
    setDraft({ ...draft, monitoring: { ...m, [k]: v } });
  const [hb, setHb] = useState<Source<{ healthy: boolean }> | null>(null);

  useEffect(() => {
    const load = () =>
      api<KioskStatus>("/api/admin/kiosk")
        .then((s) => setHb(s.heartbeat))
        .catch(() => {});
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  const now = new Date();
  return (
    <Card title="Monitoring" icon={<HeartPulse className="icon" />}>
      <p className="help">
        The Pi checks in with a monitoring service (e.g.{" "}
        <a href="https://healthchecks.io" target="_blank" rel="noreferrer">
          healthchecks.io
        </a>
        ) every few minutes. If the check-ins stop (Pi off, network down) or report a problem, that service notifies you
        by e-mail, Telegram, Signal, Discord, Teams, push, etc.: whatever you set up there.
      </p>
      <TextInput
        label="Check-in URL"
        type="password"
        value={m.heartbeat_url}
        placeholder="https://hc-ping.com/…"
        onChange={set("heartbeat_url")}
        help="In healthchecks.io: create a check, copy its ping URL. Set its period to the interval below and the grace time to about 10 minutes."
      />
      <div className="grid-2">
        <NumberInput label="Check in every" unit="minutes" value={m.interval_minutes} min={1} max={60} onChange={set("interval_minutes")} />
        <div />
      </div>
      <Toggle
        label="Report a problem when the TV isn't showing the dashboard"
        checked={m.require_display}
        onChange={set("require_display")}
        help='Sends the check-in as a failure ("/fail") when the dashboard on the TV has stopped updating, e.g. the browser froze. Turn off if you only want to know whether the Pi is reachable.'
      />
      {m.heartbeat_url && hb && (
        <p className={`small ${hb.status === "error" ? "error-text" : "muted"}`}>
          {hb.status === "ok"
            ? `Last check-in ${ago(hb.updated_at, now)} (${hb.data?.healthy ? "all fine" : "reported a problem"}).`
            : hb.status === "error"
              ? `Check-in failed: ${hb.error}`
              : hb.status === "disabled"
                ? "Save to start checking in."
                : "Waiting for the first check-in…"}
        </p>
      )}
    </Card>
  );
}
