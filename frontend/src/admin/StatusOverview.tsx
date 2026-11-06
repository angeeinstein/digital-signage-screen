import { useEffect, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import type { DisplayState } from "../lib/types";
import { ago } from "../lib/format";
import { Card } from "./fields";

type Sources = DisplayState["sources"];
const LABELS: Record<keyof Sources, string> = {
  flights: "Flights",
  weather: "Weather",
  transport: "Departures",
  timetable: "Lectures",
};

/** Live health of each data source, refreshed every 10 s. */
export function StatusOverview() {
  const [sources, setSources] = useState<Sources | null>(null);
  const [now, setNow] = useState(new Date());

  const load = () =>
    api<{ sources: Sources }>("/api/admin/status")
      .then((r) => {
        setSources(r.sources);
        setNow(new Date());
      })
      .catch(() => {});

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  const refreshAll = async () => {
    await api("/api/admin/refresh", { method: "POST" }).catch(() => {});
    setTimeout(load, 2500);
  };

  return (
    <Card
      title="Data sources"
      icon={<Activity className="icon" />}
      actions={
        <button className="btn btn-ghost" onClick={refreshAll}>
          <RefreshCw className="icon" /> Refresh now
        </button>
      }
    >
      <div className="status-grid">
        {sources &&
          (Object.keys(LABELS) as (keyof Sources)[]).map((k) => {
            const s = sources[k];
            if (!s) return null;
            const state = s.status === "error" ? "error" : s.stale ? "stale" : s.status;
            const count = Array.isArray(s.data) ? `${s.data.length} items` : s.data ? "ok" : "";
            const provider = (s.meta as { provider?: string } | undefined)?.provider;
            return (
              <div key={k} className={`status-tile ${state}`}>
                <div className="status-tile-head">
                  <span className="dot" />
                  <strong>{LABELS[k]}</strong>
                  <span className="muted">{state}</span>
                </div>
                <div className="small muted">
                  {s.status === "disabled"
                    ? s.error ?? "Turned off"
                    : `Updated ${ago(s.updated_at, now)}${count ? ` · ${count}` : ""}${provider ? ` · via ${provider}` : ""}`}
                </div>
                {s.status === "error" && s.error && <div className="small error-text">{s.error}</div>}
              </div>
            );
          })}
      </div>
    </Card>
  );
}
