import { useMemo, useState } from "react";
import { BusFront, CloudSun, GraduationCap, MapPin, Monitor, Plane, Search } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Config, Stop } from "../lib/types";
import { Card, NumberInput, Select, TestButton, TextInput, Toggle } from "./fields";

type SetDraft = (fn: (c: Config) => Config) => void;

interface Props {
  draft: Config;
  setDraft: (c: Config) => void;
}

/** All settings cards. Each edit produces a new draft; nothing is saved until "Save". */
export function Sections({ draft, setDraft }: Props) {
  const update: SetDraft = (fn) => setDraft(fn(draft));
  const set =
    <S extends keyof Config, K extends keyof Config[S]>(section: S, key: K) =>
    (value: Config[S][K]) =>
      update((c) => ({ ...c, [section]: { ...c[section], [key]: value } }));

  return (
    <div className="sections">
      <LocationCard draft={draft} set={set} update={update} />
      <DisplayCard draft={draft} set={set} />
      <WeatherCard draft={draft} set={set} />
      <FlightsCard draft={draft} set={set} update={update} />
      <TransportCard draft={draft} set={set} update={update} />
      <TimetableCard draft={draft} set={set} />
    </div>
  );
}

type Setter = <S extends keyof Config, K extends keyof Config[S]>(section: S, key: K) => (value: Config[S][K]) => void;

function LocationCard({ draft, set, update }: { draft: Config; set: Setter; update: SetDraft }) {
  const [query, setQuery] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const zones = useMemo(() => {
    try {
      return (Intl as unknown as { supportedValuesOf(k: string): string[] }).supportedValuesOf("timeZone");
    } catch {
      return ["Europe/Vienna"];
    }
  }, []);

  const search = async () => {
    if (!query.trim()) return;
    setMsg("Searching…");
    try {
      const r = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(query)}`);
      const items = (await r.json()) as { lat: string; lon: string; display_name: string }[];
      const hit = items[0];
      if (!hit) return setMsg("No place found.");
      update((c) => ({
        ...c,
        location: { ...c.location, lat: +(+hit.lat).toFixed(4), lon: +(+hit.lon).toFixed(4), name: hit.display_name.split(",")[0] ?? c.location.name },
      }));
      setMsg(`Found: ${hit.display_name}`);
    } catch (e) {
      setMsg(`Search failed: ${String(e)}`);
    }
  };

  return (
    <Card title="Location" icon={<MapPin className="icon" />}>
      <div className="field">
        <label>Find a place</label>
        <div className="input-row">
          <input value={query} placeholder="e.g. FH Joanneum Graz" onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} />
          <button type="button" className="btn btn-secondary" onClick={search}>
            <Search className="icon" /> Search
          </button>
        </div>
        {msg && <div className="help">{msg}</div>}
      </div>
      <div className="grid-3">
        <TextInput label="Name" value={draft.location.name} onChange={set("location", "name")} help="Also used to improve stop search" />
        <NumberInput label="Latitude" value={draft.location.lat} step={0.0001} min={-90} max={90} onChange={set("location", "lat")} />
        <NumberInput label="Longitude" value={draft.location.lon} step={0.0001} min={-180} max={180} onChange={set("location", "lon")} />
      </div>
      <Select label="Time zone" value={draft.location.timezone} options={zones.map((z) => ({ value: z, label: z }))} onChange={set("location", "timezone")} />
    </Card>
  );
}

function DisplayCard({ draft, set }: { draft: Config; set: Setter }) {
  return (
    <Card title="Display" icon={<Monitor className="icon" />}>
      <div className="field">
        <label>Text size: {Math.round(draft.display.font_scale * 100)} %</label>
        <input type="range" min={0.6} max={1.6} step={0.05} value={draft.display.font_scale} onChange={(e) => set("display", "font_scale")(+e.target.value)} />
        <div className="help">Everything scales with the screen size already; use this to fine-tune.</div>
      </div>
      <div className="grid-2">
        <Toggle label="Show live map" checked={draft.display.map_enabled} onChange={set("display", "map_enabled")} help="ADS-B Exchange map in the top left" />
        <NumberInput label="Map zoom" value={draft.display.map_zoom} min={3} max={14} step={0.5} onChange={set("display", "map_zoom")} />
      </div>
    </Card>
  );
}

function WeatherCard({ draft, set }: { draft: Config; set: Setter }) {
  const w = draft.weather;
  return (
    <Card title="Weather" icon={<CloudSun className="icon" />}>
      <Toggle label="Show weather" checked={w.enabled} onChange={set("weather", "enabled")} />
      <Select
        label="Provider"
        value={w.provider}
        options={[
          { value: "open-meteo", label: "Open-Meteo (free, no API key)" },
          { value: "openweathermap", label: "OpenWeatherMap (API key)" },
        ]}
        onChange={set("weather", "provider")}
      />
      {w.provider === "openweathermap" && (
        <TextInput
          label="OpenWeatherMap API key"
          type="password"
          value={w.openweathermap_api_key ?? ""}
          onChange={set("weather", "openweathermap_api_key")}
          help={
            <>
              From <a href="https://home.openweathermap.org/api_keys" target="_blank" rel="noreferrer">openweathermap.org</a>. New keys can take up to 2 hours to activate.
            </>
          }
        />
      )}
      <NumberInput label="Refresh every" unit="seconds" value={w.refresh_seconds} min={60} max={3600} onChange={set("weather", "refresh_seconds")} />
      <TestButton source="weather" draft={draft} />
    </Card>
  );
}

const PROVIDERS = [
  { id: "adsb.lol", label: "adsb.lol" },
  { id: "adsb.fi", label: "adsb.fi" },
  { id: "airplanes.live", label: "airplanes.live (requires registration with them)" },
];

function FlightsCard({ draft, set, update }: { draft: Config; set: Setter; update: SetDraft }) {
  const f = draft.flights;
  const r = draft.routes;
  const toggleProvider = (id: string, on: boolean) =>
    update((c) => {
      const current = c.flights.providers.filter((p) => p !== id);
      const next = on ? PROVIDERS.map((p) => p.id).filter((p) => p === id || current.includes(p)) : current;
      return { ...c, flights: { ...c.flights, providers: next.length ? next : c.flights.providers } };
    });
  return (
    <Card title="Flights" icon={<Plane className="icon" />}>
      <Toggle label="Show nearest aircraft" checked={f.enabled} onChange={set("flights", "enabled")} />
      <div className="field">
        <label>Data providers</label>
        <div className="help">Tried in this order; if one fails the next is used. All are free community ADS-B feeds.</div>
        {PROVIDERS.map((p) => (
          <Toggle key={p.id} label={p.label} checked={f.providers.includes(p.id)} onChange={(on) => toggleProvider(p.id, on)} />
        ))}
      </div>
      <div className="grid-3">
        <NumberInput label="Radius" unit="km" value={f.radius_km} min={5} max={250} step={5} onChange={set("flights", "radius_km")} />
        <NumberInput label="Max. aircraft" value={f.max_items} min={1} max={20} onChange={set("flights", "max_items")} help="Fewer are shown if they don't fit" />
        <NumberInput label="Refresh every" unit="seconds" value={f.refresh_seconds} min={5} max={300} onChange={set("flights", "refresh_seconds")} />
      </div>
      <Toggle label="Include aircraft on the ground" checked={f.include_ground} onChange={set("flights", "include_ground")} />
      <TestButton source="flights" draft={draft} />

      <h3>Routes (origin → destination)</h3>
      <Toggle label="Look up routes" checked={r.enabled} onChange={set("routes", "enabled")} help="Uses adsbdb.com by callsign (free). Implausible routes are hidden." />
      <NumberInput label="Keep found routes for" unit="days" value={r.cache_days} min={1} max={90} onChange={set("routes", "cache_days")} />
      <Toggle label="Use AirLabs as fallback" checked={r.airlabs_enabled} onChange={set("routes", "airlabs_enabled")} />
      {r.airlabs_enabled && (
        <>
          <div className="grid-2">
            <TextInput label="AirLabs API key" type="password" value={r.airlabs_api_key ?? ""} onChange={set("routes", "airlabs_api_key")} />
            <NumberInput label="Max. AirLabs calls per day" value={r.airlabs_daily_limit} min={0} max={1000} onChange={set("routes", "airlabs_daily_limit")} help="Free tier: 1000 per month" />
          </div>
          <TestButton source="airlabs" draft={draft} label="Test AirLabs key" />
        </>
      )}
    </Card>
  );
}

function TransportCard({ draft, set, update }: { draft: Config; set: Setter; update: SetDraft }) {
  const t = draft.transport;
  const [query, setQuery] = useState("");
  const [stops, setStops] = useState<Stop[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ stops: Stop[] }>(`/api/admin/stops?q=${encodeURIComponent(query.trim())}`);
      setStops(r.stops);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const choose = (s: Stop) => {
    update((c) => ({ ...c, transport: { ...c.transport, stop_id: s.stop_id, stop_name: s.name } }));
    setStops(null);
  };

  return (
    <Card title="Public transport" icon={<BusFront className="icon" />}>
      <Toggle label="Show departures" checked={t.enabled} onChange={set("transport", "enabled")} help="Austrian TRIAS API (Verbund Linie), no key needed" />
      <div className="field">
        <label>Find stop</label>
        <div className="input-row">
          <input value={query} placeholder="Stop name, or leave empty for stops nearby" onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} />
          <button type="button" className="btn btn-secondary" onClick={search} disabled={busy}>
            <Search className="icon" /> {busy ? "Searching…" : "Search"}
          </button>
        </div>
        {error && <div className="help error-text">{error}</div>}
        {stops && (
          <div className="stop-results">
            {stops.length === 0 && <div className="muted">No stops found. Try adding the town name.</div>}
            {stops.map((s) => (
              <button type="button" key={s.stop_id} className={`stop${s.stop_id === t.stop_id ? " selected" : ""}`} onClick={() => choose(s)}>
                <strong>{s.name}</strong>
                <span className="muted">
                  {s.locality}
                  {s.distance_km != null && ` · ${s.distance_km} km away`} · {s.stop_id}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="grid-2">
        <TextInput label="Display name" value={t.stop_name} onChange={set("transport", "stop_name")} help="Shown in the panel title" />
        <TextInput label="Stop ID" value={t.stop_id} onChange={set("transport", "stop_id")} help="Filled in by the search" />
      </div>
      <div className="grid-2">
        <NumberInput label="Max. departures" value={t.max_items} min={1} max={20} onChange={set("transport", "max_items")} help="Fewer are shown if they don't fit" />
        <NumberInput label="Refresh every" unit="seconds" value={t.refresh_seconds} min={30} max={600} onChange={set("transport", "refresh_seconds")} />
      </div>
      <TestButton source="transport" draft={draft} />
    </Card>
  );
}

function TimetableCard({ draft, set }: { draft: Config; set: Setter }) {
  const t = draft.timetable;
  return (
    <Card title="Lectures" icon={<GraduationCap className="icon" />}>
      <Toggle label="Show lectures" checked={t.enabled} onChange={set("timetable", "enabled")} help="FH JOANNEUM timetable (almaty.fh-joanneum.at)" />
      <TextInput
        label="Cohorts"
        value={t.cohorts}
        placeholder="Automatic: current LAV and MAV year groups"
        onChange={set("timetable", "cohorts")}
        help='Comma separated, e.g. "LAV 2024, MAV 2025". Leave empty to follow the academic year automatically (switches in October).'
      />
      <div className="grid-3">
        <NumberInput label="Max. lectures" value={t.max_items} min={1} max={30} onChange={set("timetable", "max_items")} help="Fewer are shown if they don't fit" />
        <NumberInput label="Look ahead" unit="hours" value={t.time_window_hours} min={1} max={168} onChange={set("timetable", "time_window_hours")} />
        <NumberInput label="Refresh every" unit="seconds" value={t.refresh_seconds} min={60} max={3600} onChange={set("timetable", "refresh_seconds")} />
      </div>
      <Toggle label="Show lectures that are in progress" checked={t.show_ongoing} onChange={set("timetable", "show_ongoing")} />
      <TestButton source="timetable" draft={draft} />
    </Card>
  );
}
