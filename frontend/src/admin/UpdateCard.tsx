import { useEffect, useRef, useState } from "react";
import { Download, Loader2, RefreshCw, Search } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { Card } from "./fields";

interface UpdateStatus {
  version: string;
  current: { commit: string | null; short: string | null; subject: string | null; date: string | null; branch: string | null };
  supported: boolean;
  state: "idle" | "starting" | "running";
  result: { code: number; finished: number } | null;
  log: string;
  log_updated: number | null;
}

interface CheckResult {
  remote_short: string;
  available: boolean;
}

/** Update the dashboard from the admin page, with the installer's output as progress. */
export function UpdateCard() {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [offline, setOffline] = useState(false);
  const [check, setCheck] = useState<CheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [watching, setWatching] = useState(false);
  const firstCommit = useRef<string | null>(null);
  const logRef = useRef<HTMLPreElement>(null);

  const load = async () => {
    try {
      const s = await api<UpdateStatus>("/api/admin/update");
      setStatus(s);
      setOffline(false);
      if (firstCommit.current === null) firstCommit.current = s.current.commit ?? "";
      if (s.state !== "idle") setWatching(true);
    } catch (e) {
      // While the update restarts the server, requests fail for a minute or two.
      if (!(e instanceof ApiError) || e.status >= 500) setOffline(true);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const active = watching && (offline || status?.state !== "idle");
  useEffect(() => {
    if (!watching) return;
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [watching]);

  // Stop polling a little after the update finished. (Depends on the
  // finished flag, not the status object, which is new on every poll.)
  const done = status?.state === "idle" && !!status?.result && !offline;
  useEffect(() => {
    if (watching && done) {
      const t = setTimeout(() => setWatching(false), 4000);
      return () => clearTimeout(t);
    }
  }, [watching, done]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [status?.log]);

  const runCheck = async () => {
    setBusy(true);
    setError(null);
    try {
      setCheck(await api<CheckResult>("/api/admin/update/check", { method: "POST" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    if (!confirm("Update now? The dashboard is offline for about 1–3 minutes while it updates and restarts.")) return;
    setError(null);
    try {
      await api("/api/admin/update/start", { method: "POST" });
      setWatching(true);
      setCheck(null);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  const cur = status?.current;
  const updated = !!status && firstCommit.current !== null && !!cur?.commit && cur.commit !== firstCommit.current;
  const finished = status?.state === "idle" && status.result && !offline;

  return (
    <Card title="Updates" icon={<Download className="icon" />}>
      {status && (
        <p>
          Installed: <strong>v{status.version}</strong>
          {cur?.branch && (
            <>
              {" "}
              · branch <code>{cur.branch}</code>
            </>
          )}
          {cur?.short && (
            <>
              {" "}
              · <code>{cur.short}</code> <span className="muted">{cur.subject}</span>
              {cur.date && <span className="muted"> ({new Date(cur.date).toLocaleDateString("en-GB")})</span>}
            </>
          )}
        </p>
      )}

      {status && !status.supported && (
        <p className="help">
          Updating from here needs the update service on the Pi. Run the installer's update once in the Pi's terminal; it
          sets it up.
        </p>
      )}

      <div className="screen-actions">
        <button className="btn btn-secondary" onClick={runCheck} disabled={busy || active}>
          <Search className="icon" /> {busy ? "Checking…" : "Check for updates"}
        </button>
        <button className="btn btn-primary" onClick={start} disabled={!status?.supported || active}>
          {active ? <Loader2 className="icon spin" /> : <Download className="icon" />} {active ? "Updating…" : "Update now"}
        </button>
      </div>

      {check && !active && (
        <div className={`alert ${check.available ? "warn" : "ok"}`}>
          {check.available
            ? `A newer version is available (${check.remote_short}).`
            : "You have the newest version."}
        </div>
      )}
      {error && <div className="alert error">{error}</div>}

      {active && (
        <div className="alert warn">
          {offline
            ? "The dashboard server is restarting as part of the update. This page reconnects by itself…"
            : status?.state === "starting"
              ? "Starting the update…"
              : "Updating… The dashboard restarts in between; this takes 1–3 minutes."}
        </div>
      )}
      {finished && watching === false && status?.result && (
        <div className={`alert ${status.result.code === 0 ? "ok" : "error"}`}>
          {status.result.code === 0
            ? `Last update finished ${new Date(status.result.finished * 1000).toLocaleString("en-GB")}.`
            : `The last update failed (exit code ${status.result.code}). See the log below.`}
        </div>
      )}
      {updated && (
        <div className="alert ok">
          Updated to <code>{cur?.short}</code>. Reload this page to use the new version of the admin page.{" "}
          <button className="btn btn-secondary" onClick={() => window.location.reload()}>
            <RefreshCw className="icon" /> Reload
          </button>
        </div>
      )}

      {status?.log && (
        <details open={active || (!!status.result && status.result.code !== 0)}>
          <summary className="muted small">Output of the {active ? "running" : "last"} update</summary>
          <pre ref={logRef} className="update-log">
            {status.log}
          </pre>
        </details>
      )}
    </Card>
  );
}
