import { useEffect, useState, type FormEvent } from "react";
import { Route, Trash2 } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { CachedRoute } from "../lib/types";
import { Card } from "./fields";

/** View the flight route cache and add manual overrides. */
export function RouteCache() {
  const [routes, setRoutes] = useState<CachedRoute[] | null>(null);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [form, setForm] = useState({ callsign: "", origin: "", destination: "" });
  const [error, setError] = useState<string | null>(null);

  const load = () => api<{ routes: CachedRoute[] }>("/api/admin/routes").then((r) => setRoutes(r.routes));

  useEffect(() => {
    if (open && !routes) load().catch((e) => setError(e.message));
  }, [open, routes]);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/api/admin/routes", { method: "POST", body: form });
      setForm({ callsign: "", origin: "", destination: "" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  const remove = async (cs: string) => {
    await api(`/api/admin/routes/${encodeURIComponent(cs)}`, { method: "DELETE" }).catch(() => {});
    await load();
  };

  const clearAuto = async () => {
    if (!confirm("Remove all automatically looked-up routes? Manual routes are kept.")) return;
    await api("/api/admin/routes", { method: "DELETE" }).catch(() => {});
    await load();
  };

  const shown = (routes ?? []).filter((r) => r.callsign.includes(filter.trim().toUpperCase()));
  const label = (a?: { iata: string; icao: string }) => (a ? a.iata || a.icao : "");

  return (
    <Card
      title="Flight route cache"
      icon={<Route className="icon" />}
      actions={
        <button className="btn btn-ghost" onClick={() => setOpen(!open)}>
          {open ? "Hide" : "Show"}
        </button>
      }
    >
      <p className="help">
        Routes are looked up by callsign (adsbdb, optionally AirLabs) and cached. If a route is wrong or missing, add a
        manual entry — manual entries always win and never expire.
      </p>
      {open && (
        <>
          <form className="inline-form" onSubmit={add}>
            <input placeholder="Callsign (e.g. AUA123)" value={form.callsign} onChange={(e) => setForm({ ...form, callsign: e.target.value })} required />
            <input placeholder="From (VIE / LOWW)" value={form.origin} onChange={(e) => setForm({ ...form, origin: e.target.value })} required />
            <input placeholder="To (GRZ / LOWG)" value={form.destination} onChange={(e) => setForm({ ...form, destination: e.target.value })} required />
            <button className="btn btn-primary">Add</button>
          </form>
          {error && <div className="alert error">{error}</div>}
          <div className="row-between">
            <input className="filter" placeholder="Filter callsign…" value={filter} onChange={(e) => setFilter(e.target.value)} />
            <span className="muted small">{routes ? `${routes.length} entries` : "Loading…"}</span>
            <button className="btn btn-secondary" onClick={clearAuto}>
              Clear looked-up routes
            </button>
          </div>
          <div className="route-table">
            {shown.slice(0, 200).map((r) => (
              <div key={r.callsign} className="route-row">
                <strong>{r.callsign}</strong>
                <span>{r.found ? `${label(r.origin)} → ${label(r.destination)}` : r.error ? "lookup failed" : "not found"}</span>
                <span className="muted small">{r.source ?? ""}</span>
                <span className="muted small">{new Date(r.fetched_at * 1000).toLocaleDateString("en-GB")}</span>
                <button className="icon-btn" title="Remove" onClick={() => remove(r.callsign)}>
                  <Trash2 className="icon" />
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}
