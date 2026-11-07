import { render, screen } from "@testing-library/react";
import { currentSlide } from "./Slides";
import { pixelsPerSecond, Ticker } from "./Ticker";
import type { DisplayState, Slide, TickerItem } from "../lib/types";

const slide = (id: string): Slide => ({ id, title: `Slide ${id}`, text: "", image: null });
const slides = (items: Slide[], over: Partial<DisplayState["slides"]> = {}): DisplayState["slides"] => ({
  items,
  every_minutes: 5,
  seconds: 15,
  preview: null,
  ...over,
});
// 300 s cycle starting at t = 3000 s (a multiple of 300)
const at = (s: number) => new Date((3000 + s) * 1000);

describe("currentSlide", () => {
  it("shows nothing without announcements", () => {
    expect(currentSlide(slides([]), at(0))).toBeNull();
  });

  it("shows each slide for its time at the start of every cycle, then the dashboard", () => {
    const s = slides([slide("a"), slide("b")]);
    expect(currentSlide(s, at(0))?.slide.id).toBe("a");
    expect(currentSlide(s, at(14))?.remaining).toBeCloseTo(1);
    expect(currentSlide(s, at(15))?.slide.id).toBe("b");
    expect(currentSlide(s, at(30))).toBeNull();
    expect(currentSlide(s, at(299))).toBeNull();
    expect(currentSlide(s, at(300))?.slide.id).toBe("a");
  });

  it("never covers more than half of the cycle and rotates the rest into later cycles", () => {
    const many = slides(Array.from({ length: 30 }, (_, i) => slide(String(i))), { every_minutes: 1, seconds: 15 });
    // 60 s cycle -> at most 30 s of slides -> 2 slides per cycle
    const first = Number(currentSlide(many, at(0))?.slide.id);
    expect(currentSlide(many, at(15))?.slide.id).toBe(String((first + 1) % 30));
    expect(currentSlide(many, at(30))).toBeNull();
    expect(currentSlide(many, at(60))?.slide.id).toBe(String((first + 2) % 30));
  });

  it("clamps very long slides to half the cycle", () => {
    const s = slides([slide("a")], { every_minutes: 1, seconds: 120 });
    expect(currentSlide(s, at(29))?.slide.id).toBe("a");
    expect(currentSlide(s, at(31))).toBeNull();
  });

  it("shows a preview immediately", () => {
    const s = slides([], { preview: { ...slide("p"), until: 3000 + 10 } });
    expect(currentSlide(s, at(5))?.slide.id).toBe("p");
    expect(currentSlide(s, at(11))).toBeNull();
  });
});

describe("Ticker", () => {
  it("renders all items with their source", () => {
    const items: TickerItem[] = [
      { id: "e", kind: "emergency", text: "TEST1 squawking 7700" },
      { id: "n", kind: "news", text: "Headline", source: "FlightGlobal", published: new Date().toISOString() },
    ];
    const { container } = render(<Ticker items={items} speed="normal" />);
    expect(screen.getByText("TEST1 squawking 7700")).toBeTruthy();
    expect(screen.getByText("FlightGlobal · just now")).toBeTruthy();
    expect(container.querySelector(".ticker.urgent")).toBeTruthy();
  });

  it("updates right away when the text stands still", () => {
    const { rerender } = render(<Ticker items={[{ id: "1", kind: "announcement", text: "Old" }]} speed="slow" />);
    rerender(<Ticker items={[{ id: "1", kind: "announcement", text: "New" }]} speed="slow" />);
    expect(screen.getByText("New")).toBeTruthy();
  });
});

describe("pixelsPerSecond", () => {
  it("rounds to whole device pixels per 60 Hz frame", () => {
    // 136 px/s = 2.27 px per frame -> 2 px per frame
    expect(pixelsPerSecond(136, 1)).toBe(120);
    expect(pixelsPerSecond(200, 1)).toBe(180);
    // 1.5x scaling: 136 css px/s = 3.4 device px per frame -> 3 device px = 2 css px
    expect(pixelsPerSecond(136, 1.5)).toBe(120);
    expect(pixelsPerSecond(5, 1)).toBe(60); // never slower than 1 px per frame
  });
});
