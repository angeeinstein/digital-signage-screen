// Formatting helpers. All times are shown in the dashboard's configured time zone.

export function formatTime(iso: string | Date, timeZone: string, seconds = false): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return d.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    ...(seconds ? { second: "2-digit" } : {}),
    timeZone,
  });
}

export function formatDate(d: Date, timeZone: string): string {
  return d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone });
}

/** Calendar day key (YYYY-MM-DD) in the given zone. */
export function dayKey(d: Date, timeZone: string): string {
  return d.toLocaleDateString("en-CA", { timeZone });
}

export function dayLabel(iso: string, now: Date, timeZone: string): string {
  const d = new Date(iso);
  const k = dayKey(d, timeZone);
  if (k === dayKey(now, timeZone)) return "Today";
  const tomorrow = new Date(now.getTime() + 86_400_000);
  if (k === dayKey(tomorrow, timeZone)) return "Tomorrow";
  return d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short", timeZone });
}

/** "now", "3 min", "1 h 05" */
export function countdown(iso: string, now: Date): string {
  const mins = Math.floor((new Date(iso).getTime() - now.getTime()) / 60_000);
  if (mins <= 0) return "now";
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  return `${h} h ${String(mins % 60).padStart(2, "0")}`;
}

export function ago(iso: string | null, now: Date): string {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s} s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  return `${Math.round(m / 60)} h ago`;
}

export function formatAltitude(ft: number | null, onGround: boolean): string {
  if (onGround) return "Ground";
  if (ft == null) return "–";
  return `${ft.toLocaleString("en-GB")} ft`;
}

export function num(v: number | null | undefined, digits = 0, unit = ""): string {
  if (v == null || Number.isNaN(v)) return "–";
  return `${v.toFixed(digits)}${unit}`;
}

export function windText(dir: number | null, kt: number | null, gust: number | null): string {
  if (kt == null) return "–";
  if (kt < 1) return "Calm";
  const d = dir == null ? "VRB" : String(Math.round(dir / 10) * 10 || 360).padStart(3, "0");
  const g = gust != null && gust >= kt + 10 ? ` G${gust}` : "";
  return `${d}° ${kt} kt${g}`;
}
