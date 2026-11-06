import { useEffect, useMemo } from "react";
import { WifiOff } from "lucide-react";
import type { Config } from "../lib/types";
import { ago } from "../lib/format";
import { DeparturesPanel } from "./DeparturesPanel";
import { FlightsPanel } from "./FlightsPanel";
import { Header } from "./Header";
import { useDisplayState, useNow } from "./hooks";
import { LecturesPanel } from "./LecturesPanel";
import "./display.css";

export function Display() {
  const now = useNow(1000);
  const { state, lastOk, offline } = useDisplayState();
  const config = state?.config;

  useEffect(() => {
    document.documentElement.style.setProperty("--scale", String(config?.display.font_scale ?? 1));
  }, [config?.display.font_scale]);

  if (!state || !config) {
    return (
      <div className="display boot">
        <div className="boot-msg">{offline ? "Waiting for server…" : "Loading…"}</div>
      </div>
    );
  }

  const tz = config.location.timezone;
  const { sources } = state;
  const showMap = config.display.map_enabled;
  const showFlights = sources.flights.status !== "disabled";
  const showTransport = sources.transport.status !== "disabled" || !!config.transport.stop_id;
  const showLectures = sources.timetable.status !== "disabled";

  return (
    <div className={`display${showMap ? "" : " no-map"}${showFlights ? "" : " no-flights"}`}>
      <div className="col-left">
        {showMap && <MapPanel config={config} />}
        {showFlights && <FlightsPanel source={sources.flights} radiusKm={config.flights.radius_km} now={now} />}
      </div>
      <div className="col-right">
        <Header now={now} timeZone={tz} locationName={config.location.name} weather={sources.weather} />
        {showTransport && <DeparturesPanel source={sources.transport} timeZone={tz} now={now} />}
        {showLectures && (
          <LecturesPanel source={sources.timetable} timeZone={tz} windowHours={config.timetable.time_window_hours} now={now} />
        )}
      </div>
      {offline && (
        <div className="offline-banner" role="status">
          <WifiOff className="icon" aria-hidden /> Connection to server lost · last update {ago(lastOk?.toISOString() ?? null, now)}
        </div>
      )}
    </div>
  );
}

function MapPanel({ config }: { config: Config }) {
  const { lat, lon } = config.location;
  const zoom = config.display.map_zoom;
  // Only rebuild the iframe URL when location/zoom actually change; otherwise
  // every poll would reload the map.
  const src = useMemo(
    () =>
      `https://globe.adsbexchange.com/?lat=${lat}&lon=${lon}&zoom=${zoom}&SiteLat=${lat}&SiteLon=${lon}` +
      `&hideSidebar&hideButtons&enableLabels&extendedLabels=1&trackLabels`,
    [lat, lon, zoom],
  );
  return (
    <section className="panel map-panel">
      <iframe src={src} title="Live air traffic map" referrerPolicy="no-referrer" loading="eager" />
    </section>
  );
}
