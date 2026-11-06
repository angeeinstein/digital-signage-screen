import {
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudLightning,
  CloudMoon,
  CloudRain,
  CloudRainWind,
  CloudSnow,
  CloudSun,
  Droplets,
  Eye,
  Gauge,
  Moon,
  Sun,
  Thermometer,
  Wind,
  type LucideIcon,
} from "lucide-react";
import type { Source, Weather } from "../lib/types";
import { formatDate, formatTime, num, windText } from "../lib/format";
import { StatusDot } from "./Panel";

const ICONS: Record<Weather["icon"], [LucideIcon, LucideIcon]> = {
  clear: [Sun, Moon],
  partly: [CloudSun, CloudMoon],
  cloudy: [Cloud, Cloud],
  fog: [CloudFog, CloudFog],
  drizzle: [CloudDrizzle, CloudDrizzle],
  rain: [CloudRain, CloudRain],
  showers: [CloudRainWind, CloudRainWind],
  snow: [CloudSnow, CloudSnow],
  thunder: [CloudLightning, CloudLightning],
};

interface Props {
  now: Date;
  timeZone: string;
  locationName: string;
  weather: Source<Weather>;
}

export function Header({ now, timeZone, locationName, weather }: Props) {
  return (
    <section className="panel header-panel">
      <div className="clock">
        <div className="clock-time">{formatTime(now, timeZone, true)}</div>
        <div className="clock-date">{formatDate(now, timeZone)}</div>
      </div>
      {weather.status !== "disabled" && <WeatherBlock weather={weather} now={now} locationName={locationName} />}
    </section>
  );
}

function WeatherBlock({ weather, now, locationName }: { weather: Source<Weather>; now: Date; locationName: string }) {
  const w = weather.data;
  if (!w) {
    return (
      <div className="weather weather-empty">
        <StatusDot source={weather} now={now} />
      </div>
    );
  }
  const Icon = ICONS[w.icon]?.[w.is_day ? 0 : 1] ?? Cloud;
  return (
    <div className="weather">
      <div className="weather-main">
        <Icon className="weather-icon" aria-hidden />
        <div>
          <div className="weather-temp">{num(w.temp_c, 0, "°")}</div>
          <div className="weather-cond">
            {w.condition}
            {locationName && <span className="muted"> · {locationName}</span>}
          </div>
        </div>
        <span className="weather-status">
          <StatusDot source={weather} now={now} />
        </span>
      </div>
      <dl className="weather-grid">
        <Item icon={Wind} label="Wind" value={windText(w.wind_dir_deg, w.wind_kt, w.gust_kt)} />
        <Item icon={Gauge} label="QNH" value={num(w.pressure_hpa, 0, " hPa")} />
        <Item icon={Eye} label="Visibility" value={w.visibility_km != null ? (w.visibility_km >= 10 ? "≥ 10 km" : `${w.visibility_km} km`) : "–"} />
        <Item icon={Thermometer} label="Dew point" value={num(w.dew_point_c, 0, "°")} />
        <Item icon={Droplets} label="Humidity" value={num(w.humidity_pct, 0, " %")} />
        <Item icon={Cloud} label="Clouds" value={num(w.cloud_cover_pct, 0, " %")} />
      </dl>
    </div>
  );
}

function Item({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="weather-item" title={label}>
      <dt>
        <Icon className="icon" aria-hidden />
        <span className="sr-only">{label}</span>
      </dt>
      <dd>{value}</dd>
    </div>
  );
}
