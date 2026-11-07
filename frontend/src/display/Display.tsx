import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { WifiOff } from "lucide-react";
import type { Config } from "../lib/types";
import { ago } from "../lib/format";
import { sameProps } from "../lib/sameProps";
import { DeparturesPanel } from "./DeparturesPanel";
import { FlightsPanel } from "./FlightsPanel";
import { Header } from "./Header";
import { useDisplayState, useNow } from "./hooks";
import { LecturesPanel } from "./LecturesPanel";
import { ShareLayer } from "./ShareLayer";
import { SlideLayer, usePreloadSlides } from "./Slides";
import { Ticker } from "./Ticker";
import "./display.css";

// Each panel re-renders only when its own data changed (or the 10-second
// clock moved). A full re-render on every poll was enough work to make the
// ticker stutter on the Pi.
const Flights = memo(FlightsPanel, sameProps);
const Departures = memo(DeparturesPanel, sameProps);
const Lectures = memo(LecturesPanel, sameProps);
const HeaderPanel = memo(Header, sameProps);

export function Display() {
  // Countdowns ("15 min") and "updated x ago" only need a coarse clock.
  // Re-rendering the whole dashboard every second made the ticker stutter
  // on the Pi; the clock and the slides have their own 1-second timers.
  const now = useNow(10_000);
  const { state, lastOk, offline } = useDisplayState();
  const config = state?.config;
  const [sharing, setSharing] = useState(false);
  const onSharing = useCallback((on: boolean) => setSharing(on), []);

  useEffect(() => {
    document.documentElement.style.setProperty("--scale", String(config?.display.font_scale ?? 1));
  }, [config?.display.font_scale]);

  usePreloadSlides(state?.slides?.items ?? []);

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
  // Shown while loading a configured stop, but never when switched off in admin.
  const showTransport =
    config.transport.enabled && (sources.transport.status !== "disabled" || !!config.transport.stop_id);
  const showLectures = sources.timetable.status !== "disabled";
  // While a laptop is shown, the ticker and slides pause.
  const tickerItems = sharing ? [] : (state.ticker?.items ?? []);

  // Layout: the dashboard fills the screen; the ticker (only when it has
  // content) takes a strip at the bottom and the dashboard shrinks to fit.
  // Slides cover the dashboard but not the ticker. The dashboard stays
  // mounted underneath, so the map doesn't reload after each slide.
  return (
    <div className={`screen${tickerItems.length ? " has-ticker" : ""}`}>
      <div className="screen-main">
        <div className={`display${showMap ? "" : " no-map"}${showFlights ? "" : " no-flights"}`}>
          <div className="col-left">
            {showMap && <MapPanel config={config} />}
            {showFlights && <Flights source={sources.flights} radiusKm={config.flights.radius_km} now={now} />}
          </div>
          <div className="col-right">
            <HeaderPanel now={now} timeZone={tz} locationName={config.location.name} weather={sources.weather} />
            {showTransport && <Departures source={sources.transport} timeZone={tz} now={now} />}
            {showLectures && (
              <Lectures source={sources.timetable} timeZone={tz} windowHours={config.timetable.time_window_hours} now={now} />
            )}
          </div>
        </div>
        {!sharing && state.slides && <SlideLayer slides={state.slides} />}
      </div>
      {tickerItems.length > 0 && <Ticker items={tickerItems} speed={state.ticker.speed} />}
      {config.share?.enabled && <ShareLayer onActiveChange={onSharing} />}
      {offline && (
        <div className="offline-banner" role="status">
          <WifiOff className="icon" aria-hidden /> Connection to server lost · last update {ago(lastOk?.toISOString() ?? null, now)}
        </div>
      )}
    </div>
  );
}

const MapPanel = memo(function MapPanel({ config }: { config: Config }) {
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
}, sameProps);
