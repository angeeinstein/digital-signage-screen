import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { Megaphone, Newspaper, Plane, TriangleAlert } from "lucide-react";
import type { DisplayState, TickerItem } from "../lib/types";

type Speed = DisplayState["ticker"]["speed"];

/** Scroll speed in rem per second, so it looks the same at any resolution. */
const SPEED_REM_PER_S: Record<Speed, number> = { slow: 5, normal: 8, fast: 12 };

const ICONS = {
  emergency: TriangleAlert,
  aircraft: Plane,
  news: Newspaper,
  announcement: Megaphone,
} as const;

interface ShownItem extends TickerItem {
  /** "Austrian Wings · 3 h ago", fixed when the item starts scrolling. */
  label?: string;
}

interface Shown {
  sig: string;
  items: ShownItem[];
}

interface Motion {
  from: number;
  to: number;
  seconds: number;
}

export function tickerSignature(items: TickerItem[]): string {
  return items.map((i) => `${i.id}|${i.text}`).join("\n");
}

function newsLabel(item: TickerItem, now: Date): string | undefined {
  if (item.kind !== "news") return undefined;
  const parts = [item.source];
  if (item.published) {
    const h = Math.round((now.getTime() - new Date(item.published).getTime()) / 3_600_000);
    parts.push(h < 1 ? "just now" : `${h} h ago`);
  }
  return parts.filter(Boolean).join(" · ");
}

function prepare(items: TickerItem[]): Shown {
  const now = new Date();
  return { sig: tickerSignature(items), items: items.map((i) => ({ ...i, label: newsLabel(i, now) })) };
}

/**
 * One line of scrolling text at the bottom of the screen. New content is
 * swapped in only when the current pass has scrolled out, so text never
 * jumps mid-sentence. If everything fits, it stands still.
 * The parent hides the ticker entirely when there is nothing to show.
 */
export function Ticker({ items, speed }: { items: TickerItem[]; speed: Speed }) {
  const sig = tickerSignature(items);
  const latest = useRef(items);
  latest.current = items;
  const [shown, setShown] = useState<Shown>(() => prepare(items));
  const [motion, setMotion] = useState<Motion | null>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const vp = viewport.current;
    const tr = track.current;
    if (!vp || !tr) return;
    const vw = vp.clientWidth;
    const tw = tr.scrollWidth;
    if (tw <= vw) {
      setMotion(null);
      return;
    }
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    setMotion({ from: vw, to: -tw, seconds: (vw + tw) / (SPEED_REM_PER_S[speed] * rem) });
  }, [shown.sig, speed]);

  // Standing still: show new content right away. Scrolling: wait for the pass to end.
  useEffect(() => {
    if (sig !== shown.sig && !motion) setShown(prepare(items));
  }, [sig, shown.sig, motion, items]);

  const onPassEnd = () => {
    if (tickerSignature(latest.current) !== shown.sig) setShown(prepare(latest.current));
  };

  const urgent = shown.items.some((i) => i.kind === "emergency");

  return (
    <div className={`ticker${urgent ? " urgent" : ""}`} role="marquee" aria-live="off">
      <div className="ticker-viewport" ref={viewport}>
        <div
          key={shown.sig}
          ref={track}
          className={`ticker-track${motion ? " moving" : ""}`}
          style={
            motion
              ? ({
                  "--from": `${motion.from}px`,
                  "--to": `${motion.to}px`,
                  animationDuration: `${motion.seconds}s`,
                } as CSSProperties)
              : undefined
          }
          onAnimationIteration={onPassEnd}
        >
          {shown.items.map((item) => {
            const Icon = ICONS[item.kind] ?? Newspaper;
            return (
              <span key={item.id} className={`ticker-item kind-${item.kind}`}>
                <Icon className="icon" aria-hidden />
                {item.label && <span className="ticker-source">{item.label}</span>}
                <span>{item.text}</span>
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
