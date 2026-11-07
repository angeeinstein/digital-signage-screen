import { useMemo, useState } from "react";
import { GraduationCap } from "lucide-react";
import type { Lecture, Source } from "../lib/types";
import { countdown, dayKey, dayLabel, formatTime } from "../lib/format";
import { AutoFitList, type FitRow } from "./AutoFitList";
import { Empty, Panel, sourceMessage } from "./Panel";

interface Props {
  source: Source<Lecture[]>;
  timeZone: string;
  windowHours: number;
  now: Date;
}

export function LecturesPanel({ source, timeZone, windowHours, now }: Props) {
  const [fit, setFit] = useState<[number, number]>([0, 0]);
  const minute = Math.floor(now.getTime() / 60_000);

  // Rebuilt once per minute (progress, countdowns) or when new data arrives.
  const { rows, msg } = useMemo(() => {
    const at = new Date(minute * 60_000);
    const lectures = (source.data ?? []).filter((l) => new Date(l.end).getTime() > at.getTime());
    const out: FitRow[] = [];
    let lastDay = dayKey(at, timeZone);
    for (const l of lectures) {
      const k = dayKey(new Date(l.start), timeZone);
      if (k !== lastDay) {
        out.push({ key: `day-${k}`, header: true, node: <div className="day-sep">{dayLabel(l.start, at, timeZone)}</div> });
        lastDay = k;
      }
      out.push({ key: l.id, node: <LectureRow l={l} timeZone={timeZone} now={at} /> });
    }
    return {
      rows: out,
      msg: sourceMessage({ ...source, data: source.data ? lectures : null }, `No lectures in the next ${windowHours} h`),
    };
  }, [source, minute, timeZone, windowHours]);

  return (
    <Panel
      className="panel-lectures"
      title="Lectures"
      icon={<GraduationCap className="icon" aria-hidden />}
      source={source}
      now={now}
      extra={fit[0] < fit[1] ? `${fit[0]} of ${fit[1]}` : undefined}
    >
      {msg ? (
        <Empty>{msg}</Empty>
      ) : (
        <AutoFitList className="table lectures" rows={rows} onFit={(v, t) => setFit([v, t])} />
      )}
    </Panel>
  );
}

function LectureRow({ l, timeZone, now }: { l: Lecture; timeZone: string; now: Date }) {
  const start = new Date(l.start).getTime();
  const end = new Date(l.end).getTime();
  const ongoing = start <= now.getTime();
  const soon = !ongoing && start - now.getTime() < 30 * 60_000;
  const progress = ongoing ? Math.min(1, Math.max(0, (now.getTime() - start) / (end - start))) : 0;
  const cls = ["tr", ongoing && "ongoing", soon && "soon", l.kind === "EXAM" && "exam"].filter(Boolean).join(" ");
  const status = ongoing ? `now · ends in ${countdown(l.end, now)}` : soon ? `starts in ${countdown(l.start, now)}` : "";
  const details = [status, l.lecturer, l.group].filter(Boolean).join(" · ");
  return (
    <div className={cls}>
      <span className="cell-stack time">
        <strong>{formatTime(l.start, timeZone)}</strong>
        <small>–{formatTime(l.end, timeZone)}</small>
      </span>
      <span className="cell-stack">
        <span className="course">
          {l.cohort && <span className="tag">{l.cohort}</span>}
          {l.kind && <span className={`tag kind-${l.kind.toLowerCase()}`}>{l.kind === "EXAM" ? "Exam" : l.kind}</span>}
          <strong>{l.course}</strong>
        </span>
        {details && <small>{details}</small>}
      </span>
      <span className="num room">{l.room || (l.online ? "Online" : "–")}</span>
      {ongoing && <span className="progress" style={{ transform: `scaleX(${progress})` }} />}
    </div>
  );
}
