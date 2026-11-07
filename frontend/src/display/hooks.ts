import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { DisplayState } from "../lib/types";

/** Current time, updated every `ms` milliseconds. */
export function useNow(ms = 1000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

export interface DisplayConnection {
  state: DisplayState | null;
  /** Time of the last successful poll. */
  lastOk: Date | null;
  /** True after several failed polls in a row. */
  offline: boolean;
}

const POLL_MS = 5000;

/**
 * Polls /api/display. The backend serves cached snapshots, so polling is
 * cheap. Config changes are picked up live (no page reload); a new backend
 * version or frontend build (after an update) triggers a full reload to load the new frontend.
 */
export function useDisplayState(): DisplayConnection {
  const [state, setState] = useState<DisplayState | null>(null);
  const lastOk = useRef<Date | null>(null);
  const lastKey = useRef("");
  const [failures, setFailures] = useState(0);
  const firstVersion = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const ctrl = new AbortController();
      const abort = setTimeout(() => ctrl.abort(), 8000);
      try {
        const s = await api<DisplayState>("/api/display", { signal: ctrl.signal });
        if (cancelled) return;
        const build = `${s.version}:${s.build}`;
        if (firstVersion.current === null) firstVersion.current = build;
        else if (build !== firstVersion.current) {
          window.location.reload();
          return;
        }
        // Most polls return the same data; re-rendering the whole dashboard
        // for nothing costs the Pi enough to make the ticker stutter.
        const key = JSON.stringify({ ...s, server_time: "" });
        if (key !== lastKey.current) {
          lastKey.current = key;
          setState(s);
        }
        lastOk.current = new Date();
        setFailures(0);
      } catch {
        if (!cancelled) setFailures((f) => f + 1);
      } finally {
        clearTimeout(abort);
        if (!cancelled) timer = setTimeout(tick, POLL_MS);
      }
    };
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  return { state, lastOk: lastOk.current, offline: failures >= 3 };
}
