import { useEffect } from "react";
import type { DisplayState, Slide } from "../lib/types";

type Slides = DisplayState["slides"];

export interface CurrentSlide {
  slide: Slide;
  /** Seconds this slide stays on screen in total, and how many are left. */
  seconds: number;
  remaining: number;
}

/**
 * Which announcement (if any) covers the dashboard right now.
 *
 * Every `every_minutes`, the slides are shown one after another for
 * `seconds` each. The schedule is derived from the clock, so it survives
 * page reloads. Slides never take more than half of each cycle: the
 * dashboard stays the main content. With more slides than fit, later
 * cycles continue where the previous one stopped.
 */
export function currentSlide(slides: Slides, now: Date): CurrentSlide | null {
  const t = now.getTime() / 1000;
  const p = slides.preview;
  if (p && p.until > t) {
    return { slide: p, seconds: slides.seconds, remaining: p.until - t };
  }
  const n = slides.items.length;
  if (!n) return null;
  const cycle = Math.max(60, slides.every_minutes * 60);
  const seconds = Math.min(slides.seconds, cycle / 2);
  const perCycle = Math.max(1, Math.min(n, Math.floor(cycle / 2 / seconds)));
  const pos = t % cycle;
  const idx = Math.floor(pos / seconds);
  if (idx >= perCycle) return null;
  const cycleNo = Math.floor(t / cycle);
  const slide = slides.items[(cycleNo * perCycle + idx) % n];
  if (!slide) return null;
  return {
    slide,
    seconds,
    remaining: seconds - (pos - idx * seconds),
  };
}

/** Load slide images ahead of time so they appear instantly. */
export function usePreloadSlides(slides: Slide[]) {
  const key = slides.map((s) => s.image ?? "").join("|");
  useEffect(() => {
    for (const s of slides) {
      if (s.image) new Image().src = s.image;
    }
  }, [key]);
}

export function SlideOverlay({ current }: { current: CurrentSlide }) {
  const { slide } = current;
  const hasCaption = !!(slide.title || slide.text);
  return (
    <div className="slide-overlay" key={slide.id} role="region" aria-label="Announcement">
      {slide.image && <div className="slide-bg" style={{ backgroundImage: `url("${slide.image}")` }} />}
      <div className={`slide${slide.image ? " has-image" : " text-only"}`}>
        {slide.image && <img className="slide-image" src={slide.image} alt={slide.title} />}
        {hasCaption && (
          <div className="slide-caption">
            {slide.title && <h1>{slide.title}</h1>}
            {slide.text && <p>{slide.text}</p>}
          </div>
        )}
      </div>
      <div
        className="slide-progress"
        style={{
          transform: `scaleX(${current.remaining / current.seconds})`,
        }}
      />
    </div>
  );
}
