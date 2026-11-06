import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

export interface FitRow {
  key: string;
  node: ReactNode;
  /** Group headers (e.g. "Tomorrow") are never shown as the last visible row. */
  header?: boolean;
}

interface Props {
  rows: FitRow[];
  className?: string;
  /** Called with (visible item rows, total item rows) whenever the fit changes. */
  onFit?: (visible: number, total: number) => void;
}

/**
 * Renders rows into a fixed-height container and hides every row that would
 * not fit completely. Nothing is ever cut in half: rows either show fully or
 * not at all. Hidden rows stay in the layout (visibility: hidden), so
 * measuring never feeds back into layout and cannot loop.
 */
export function AutoFitList({ rows, className, onFit }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(rows.length);
  const onFitRef = useRef(onFit);
  onFitRef.current = onFit;

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const limit = el.clientHeight + 0.5;
      const kids = Array.from(el.children) as HTMLElement[];
      let n = 0;
      for (const kid of kids) {
        if (kid.offsetTop + kid.offsetHeight <= limit) n++;
        else break;
      }
      // Don't end on a dangling group header.
      while (n > 0 && kids[n - 1]?.dataset.header === "1") n--;
      setVisible(n);
      const items = (from: number, to: number) => rows.slice(from, to).filter((r) => !r.header).length;
      onFitRef.current?.(items(0, n), items(0, rows.length));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    // Fonts loading late can change row heights.
    document.fonts?.ready.then(measure).catch(() => {});
    return () => ro.disconnect();
  }, [rows]);

  return (
    <div ref={ref} className={`fit-list ${className ?? ""}`}>
      {rows.map((r, i) => (
        <div
          key={r.key}
          data-header={r.header ? "1" : undefined}
          className={`fit-row${r.header ? " fit-header" : ""}${i >= visible ? " is-clipped" : ""}`}
          aria-hidden={i >= visible || undefined}
        >
          {r.node}
        </div>
      ))}
    </div>
  );
}
