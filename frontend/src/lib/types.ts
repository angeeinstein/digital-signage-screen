// Mirrors the JSON produced by the Flask backend (signage/…).

export type SourceStatus = "pending" | "ok" | "error" | "disabled";

export interface Source<T, M = Record<string, unknown>> {
  status: SourceStatus;
  stale: boolean;
  error: string | null;
  updated_at: string | null;
  data: T | null;
  meta?: M;
}

export interface Airport {
  iata: string;
  icao: string;
  name: string;
  city: string;
  lat: number | null;
  lon: number | null;
}

export interface Flight {
  id: string;
  hex: string;
  callsign: string;
  flight_iata?: string;
  registration: string;
  type: string;
  type_name: string;
  icon: string;
  airline_code: string;
  airline: string;
  lat: number;
  lon: number;
  altitude_ft: number | null;
  on_ground: boolean;
  vertical_rate_fpm: number | null;
  speed_kt: number | null;
  track_deg: number | null;
  distance_km: number;
  bearing_deg: number;
  squawk: string | null;
  emergency: boolean;
  emergency_kind?: string | null;
  military?: boolean;
  route: { origin: Airport; destination: Airport; source: string } | null;
}

export interface Weather {
  provider: string;
  observed_at: string | null;
  condition: string;
  icon: "clear" | "partly" | "cloudy" | "fog" | "drizzle" | "rain" | "showers" | "snow" | "thunder";
  is_day: boolean;
  temp_c: number | null;
  feels_like_c: number | null;
  dew_point_c: number | null;
  humidity_pct: number | null;
  pressure_hpa: number | null;
  wind_dir_deg: number | null;
  wind_kt: number | null;
  gust_kt: number | null;
  visibility_km: number | null;
  cloud_cover_pct: number | null;
}

export interface Departure {
  line: string;
  destination: string;
  mode: string;
  platform: string | null;
  planned: string | null;
  expected: string;
  realtime: boolean;
  delay_min: number | null;
  cancelled: boolean;
}

export interface Lecture {
  id: string;
  start: string;
  end: string;
  ongoing: boolean;
  course: string;
  kind: string;
  room: string;
  cohort: string;
  online: boolean;
  lecturer: string;
  group: string;
}

export interface Config {
  location: { name: string; lat: number; lon: number; timezone: string };
  display: { font_scale: number; map_enabled: boolean; map_zoom: number };
  weather: { enabled: boolean; provider: "open-meteo" | "openweathermap"; openweathermap_api_key?: string; refresh_seconds: number };
  flights: {
    enabled: boolean;
    providers: string[];
    radius_km: number;
    max_items: number;
    include_ground: boolean;
    refresh_seconds: number;
  };
  routes: {
    enabled: boolean;
    cache_days: number;
    airlabs_enabled: boolean;
    airlabs_api_key?: string;
    airlabs_daily_limit: number;
  };
  transport: { enabled: boolean; stop_id: string; stop_name: string; max_items: number; refresh_seconds: number };
  timetable: {
    enabled: boolean;
    cohorts: string;
    max_items: number;
    time_window_hours: number;
    show_ongoing: boolean;
    refresh_seconds: number;
  };
  ticker: {
    enabled: boolean;
    speed: "slow" | "normal" | "fast";
    emergencies: boolean;
    notable_aircraft: boolean;
    news_enabled: boolean;
    news_feeds: string;
    news_keywords: string;
    news_max_age_hours: number;
    news_max_items: number;
    refresh_seconds: number;
  };
  announcements: { slides_enabled: boolean; slide_every_minutes: number; slide_seconds: number };
  share: { enabled: boolean; relay_enabled: boolean; public_url: string; max_minutes: number };
}

export interface TickerItem {
  id: string;
  kind: "emergency" | "aircraft" | "news" | "announcement";
  text: string;
  source?: string;
  published?: string | null;
}

export interface Slide {
  id: string;
  title: string;
  text: string;
  image: string | null;
}

export interface Announcement {
  id: string;
  title: string;
  text: string;
  image: string;
  start_date: string;
  end_date: string;
  in_ticker: boolean;
  as_slide: boolean;
  enabled: boolean;
  active?: boolean;
  /** Set when the announcement would not appear anywhere. */
  problem?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface DisplayState {
  ok: true;
  version: string;
  build: string;
  revision: number;
  server_time: string;
  config: Config;
  sources: {
    flights: Source<Flight[], { provider?: string; total_in_range?: number }>;
    weather: Source<Weather>;
    transport: Source<Departure[], { stop_name?: string }>;
    timetable: Source<Lecture[]>;
  };
  ticker: { speed: Config["ticker"]["speed"]; items: TickerItem[] };
  slides: { items: Slide[]; every_minutes: number; seconds: number; preview: (Slide & { until: number }) | null };
}

export interface Stop {
  stop_id: string;
  name: string;
  locality: string;
  lat: number | null;
  lon: number | null;
  distance_km?: number | null;
}

export interface CachedRoute {
  callsign: string;
  found: boolean;
  source?: string;
  origin?: Airport;
  destination?: Airport;
  airline?: string;
  fetched_at: number;
  error?: string;
}
