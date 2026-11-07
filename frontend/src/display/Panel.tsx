import type { ReactNode } from "react";
import type { Source } from "../lib/types";
import { ago } from "../lib/format";

interface Props {
  title: ReactNode;
  icon?: ReactNode;
  source?: Source<unknown>;
  now: Date;
  /** Extra info on the right of the header, e.g. "6 of 9". */
  extra?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** Card with a header and a per-source freshness indicator. */
export function Panel({ title, icon, source, now, extra, className, children }: Props) {
  return (
    <section className={`panel ${className ?? ""}`}>
      <header className="panel-head">
        <h2 className="panel-title">
          {icon}
          <span>{title}</span>
        </h2>
        <div className="panel-meta">
          {extra && <span className="panel-extra">{extra}</span>}
          {source && <StatusDot source={source} now={now} />}
        </div>
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function StatusDot({ source, now }: { source: Source<unknown>; now: Date }) {
  let cls = "ok";
  let label = "";
  if (source.status === "pending") {
    cls = "pending";
    label = "loading";
  } else if (source.status === "error" && !source.data) {
    cls = "error";
    label = "unavailable";
  } else if (source.stale || source.status === "error") {
    cls = "stale";
    label = `updated ${ago(source.updated_at, now)}`;
  }
  return (
    <span className={`status status-${cls}`} title={source.error ?? undefined}>
      <span className="status-dot" />
      {label && <span className="status-label">{label}</span>}
    </span>
  );
}

/** Centered message for empty/disabled/error states. */
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function sourceMessage(source: Source<unknown>, emptyText: string): string | null {
  if (source.status === "pending") return "Loading…";
  if (source.status === "disabled") return source.error ?? "Disabled";
  if (source.status === "error" && !source.data) return "Currently unavailable";
  if (Array.isArray(source.data) && source.data.length === 0) return emptyText;
  return null;
}
