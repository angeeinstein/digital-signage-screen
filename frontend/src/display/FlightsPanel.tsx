import { useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Plane } from "lucide-react";
import type { Flight, Source } from "../lib/types";
import { formatAltitude } from "../lib/format";
import { AutoFitList, type FitRow } from "./AutoFitList";
import { Empty, Panel, sourceMessage } from "./Panel";

interface Props {
  source: Source<Flight[], { provider?: string; total_in_range?: number }>;
  radiusKm: number;
  now: Date;
}

export function FlightsPanel({ source, radiusKm, now }: Props) {
  const [shown, setShown] = useState(0);
  const flights = source.data ?? [];
  const msg = sourceMessage(source, `No aircraft within ${radiusKm} km`);
  const total = source.meta?.total_in_range;

  const rows: FitRow[] = useMemo(
    () => [
      { key: "__head", node: <FlightHeader /> },
      ...flights.map((f) => ({ key: f.id, node: <FlightRow f={f} /> })),
    ],
    [flights],
  );

  const extra = total ? (shown < total ? `${shown} of ${total} nearby` : `${total} nearby`) : undefined;

  return (
    <Panel
      className="panel-flights"
      title="Nearest aircraft"
      icon={<Plane className="icon" aria-hidden />}
      source={source}
      now={now}
      extra={extra}
    >
      {msg ? (
        <Empty>{msg}</Empty>
      ) : (
        // The header row counts as one fitted row.
        <AutoFitList className="table flights" rows={rows} onFit={(v) => setShown(Math.max(v - 1, 0))} />
      )}
    </Panel>
  );
}

function FlightHeader() {
  return (
    <div className="tr th">
      <span />
      <span>Flight</span>
      <span>Airline</span>
      <span>Route</span>
      <span>Type</span>
      <span className="num">Altitude</span>
      <span className="num">Speed</span>
      <span className="num">Dist.</span>
    </div>
  );
}

function FlightRow({ f }: { f: Flight }) {
  const vr = f.vertical_rate_fpm ?? 0;
  const trend =
    vr > 300 ? (
      <ArrowUpRight className="trend up" aria-label="climbing" />
    ) : vr < -300 ? (
      <ArrowDownRight className="trend down" aria-label="descending" />
    ) : null;
  const label = f.callsign || f.registration || f.hex.toUpperCase();
  const sub = f.flight_iata && f.flight_iata !== f.callsign ? f.flight_iata : f.callsign ? f.registration : "";
  return (
    <div className={`tr${f.emergency ? " emergency" : ""}`}>
      <span className="ac-icon">
        <img src={`/static/icons/adsb_icons/${f.icon}.svg`} alt="" />
      </span>
      <span className="cell-stack">
        <strong>{label}</strong>
        {sub && <small>{sub}</small>}
      </span>
      <span className="muted">{f.airline || "–"}</span>
      <span className="cell-stack">
        {f.route ? (
          <>
            <strong>
              {code(f.route.origin)} → {code(f.route.destination)}
            </strong>
            <small>
              {place(f.route.origin)} – {place(f.route.destination)}
            </small>
          </>
        ) : (
          <span className="muted">–</span>
        )}
      </span>
      <span className="cell-stack">
        <span>{f.type || "–"}</span>
        {f.type_name && <small>{f.type_name}</small>}
      </span>
      <span className="num">
        {formatAltitude(f.altitude_ft, f.on_ground)}
        {trend}
      </span>
      <span className="num">{f.speed_kt != null ? `${f.speed_kt} kt` : "–"}</span>
      <span className="num strong">{f.distance_km.toFixed(f.distance_km < 10 ? 1 : 0)} km</span>
    </div>
  );
}

function code(a: { iata: string; icao: string }): string {
  return a.iata || a.icao || "?";
}

function place(a: { city: string; name: string; iata: string; icao: string }): string {
  return a.city || a.name || code(a);
}
