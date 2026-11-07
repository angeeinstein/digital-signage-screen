import { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
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

/**
 * Round the speed to a whole number of device pixels per frame (at 60 Hz).
 * At e.g. 2.3 px per frame, text snaps alternately 2 and 3 pixels, which
 * looks like small irregular jerks; whole pixels per frame scroll evenly.
 */
export function pixelsPerSecond(cssPxPerSecond: number, dpr = window.devicePixelRatio || 1, hz = 60): number {
  const devicePerFrame = Math.max(1, Math.round((cssPxPerSecond * dpr) / hz));
  return (devicePerFrame * hz) / dpr;
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
function TickerView({ items, speed }: { items: TickerItem[]; speed: Speed }) {
  const sig = tickerSignature(items);
  const latest = useRef(items);
  latest.current = items;
  const [shown, setShown] = useState<Shown>(() => prepare(items));
  const shownSig = useRef(shown.sig);
  shownSig.current = shown.sig;
  const [moving, setMoving] = useState(false);
  const viewport = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const vp = viewport.current;
    const tr = track.current;
    if (!vp || !tr) return;
    const vw = vp.clientWidth;
    const tw = tr.scrollWidth;
    if (tw <= vw || typeof tr.animate !== "function") {
      setMoving(false);
      return;
    }
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    const ms = ((vw + tw) / pixelsPerSecond(SPEED_REM_PER_S[speed] * rem)) * 1000;
    // Only a transform with fixed pixel values: Chromium runs this on the
    // compositor, so work on the main thread (clock, data updates) can't
    // make the text stutter.
    const anim = tr.animate(
      [{ transform: `translate3d(${vw}px, 0, 0)` }, { transform: `translate3d(${-tw}px, 0, 0)` }],
      { duration: ms, easing: "linear" },
    );
    anim.onfinish = () => {
      // Swap in new content only between passes, so text never jumps.
      if (tickerSignature(latest.current) !== shownSig.current) setShown(prepare(latest.current));
      else anim.play();
    };
    setMoving(true);
    return () => {
      anim.onfinish = null;
      anim.cancel();
    };
  }, [shown.sig, speed]);

  // Standing still: show new content right away.
  useEffect(() => {
    if (sig !== shown.sig && !moving) setShown(prepare(items));
  }, [sig, shown.sig, moving, items]);

  const urgent = shown.items.some((i) => i.kind === "emergency");

  return (
    <div className={`ticker${urgent ? " urgent" : ""}`} role="marquee" aria-live="off">
      <div className="ticker-viewport" ref={viewport}>
        <div key={shown.sig} ref={track} className={`ticker-track${moving ? " moving" : ""}`}>
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

/**
 * The display re-renders every second (clock) and gets a fresh items array
 * every poll; skip those re-renders unless the content actually changed.
 */
export const Ticker = memo(
  TickerView,
  (a, b) => a.speed === b.speed && tickerSignature(a.items) === tickerSignature(b.items),
);
