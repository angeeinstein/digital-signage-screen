import { useMemo, useState } from "react";
import { BusFront, TrainFront, TramFront } from "lucide-react";
import type { Departure, Source } from "../lib/types";
import { countdown, formatTime } from "../lib/format";
import { AutoFitList, type FitRow } from "./AutoFitList";
import { Empty, Panel, sourceMessage } from "./Panel";

interface Props {
  source: Source<Departure[], { stop_name?: string }>;
  timeZone: string;
  now: Date;
}

export function DeparturesPanel({ source, timeZone, now }: Props) {
  const [fit, setFit] = useState<[number, number]>([0, 0]);
  const minute = Math.floor(now.getTime() / 60_000);

  // Rebuilt once per minute (countdowns) or when new data arrives.
  const { rows, msg } = useMemo(() => {
    const t = minute * 60_000;
    // Hide departures that left while waiting for the next refresh.
    const deps = (source.data ?? []).filter((d) => new Date(d.expected).getTime() >= t);
    const at = new Date(t);
    return {
      msg: sourceMessage({ ...source, data: source.data ? deps : null }, "No departures in the next hour"),
      rows: deps.map<FitRow>((d, i) => ({
        key: `${d.line}-${d.planned ?? d.expected}-${i}`,
        node: <DepartureRow d={d} timeZone={timeZone} now={at} />,
      })),
    };
  }, [source, minute, timeZone]);

  return (
    <Panel
      className="panel-departures"
      title={source.meta?.stop_name ? `Departures · ${source.meta.stop_name}` : "Departures"}
      icon={<BusFront className="icon" aria-hidden />}
      source={source}
      now={now}
      extra={fit[0] < fit[1] ? `${fit[0]} of ${fit[1]}` : undefined}
    >
      {msg ? (
        <Empty>{msg}</Empty>
      ) : (
        <AutoFitList className="table departures" rows={rows} onFit={(v, t) => setFit([v, t])} />
      )}
    </Panel>
  );
}

function ModeIcon({ mode }: { mode: string }) {
  if (mode.includes("tram")) return <TramFront className="mode" aria-label="Tram" />;
  if (mode.includes("rail") || mode.includes("train") || mode.includes("metro"))
    return <TrainFront className="mode" aria-label="Train" />;
  return <BusFront className="mode" aria-label="Bus" />;
}

function DepartureRow({ d, timeZone, now }: { d: Departure; timeZone: string; now: Date }) {
  const delayed = (d.delay_min ?? 0) >= 2;
  return (
    <div className={`tr${d.cancelled ? " cancelled" : ""}`}>
      <span className="line-badge">
        <ModeIcon mode={d.mode} />
        <strong>{d.line}</strong>
      </span>
      <span className="dest">{d.destination}</span>
      <span className="num strong">{d.cancelled ? "cancelled" : countdown(d.expected, now)}</span>
      <span className="num">
        {d.planned && delayed ? (
          <>
            <s className="muted">{formatTime(d.planned, timeZone)}</s>{" "}
            <span className="late">{formatTime(d.expected, timeZone)}</span>
          </>
        ) : (
          formatTime(d.expected, timeZone)
        )}
      </span>
      <span className={`rt ${d.realtime ? (delayed ? "delayed" : "live") : "plan"}`} title={d.realtime ? "Real-time" : "Timetable"}>
        {d.realtime ? (delayed ? `+${d.delay_min}` : "live") : "plan"}
      </span>
    </div>
  );
}
