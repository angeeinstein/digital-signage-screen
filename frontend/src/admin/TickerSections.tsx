import { Megaphone, Newspaper } from "lucide-react";
import type { Config } from "../lib/types";
import { Card, NumberInput, Select, TestButton, TextArea, TextInput, Toggle } from "./fields";
import type { Setter } from "./Sections";

export function TickerCard({ draft, set }: { draft: Config; set: Setter }) {
  const t = draft.ticker;
  return (
    <Card title="News ticker" icon={<Newspaper className="icon" />}>
      <Toggle
        label="Show the ticker"
        checked={t.enabled}
        onChange={set("ticker", "enabled")}
        help="A scrolling line at the bottom of the screen. It only appears while there is something to show."
      />
      {t.enabled && (
        <>
          <Select
            label="Scroll speed"
            value={t.speed}
            options={[
              { value: "slow", label: "Slow" },
              { value: "normal", label: "Normal" },
              { value: "fast", label: "Fast" },
            ]}
            onChange={set("ticker", "speed")}
          />

          <h3>From the live aircraft data</h3>
          <Toggle
            label="Emergencies"
            checked={t.emergencies}
            onChange={set("ticker", "emergencies")}
            help="Aircraft in range squawking 7700 (emergency), 7600 (radio failure) or 7500 (hijack). Stays for 15 minutes after the aircraft leaves the area."
          />
          <Toggle
            label="Rare and military aircraft"
            checked={t.notable_aircraft}
            onChange={set("ticker", "notable_aircraft")}
            help="E.g. A380, An-124, Beluga, 747, C-17, and aircraft listed as military. Uses the radius from the Flights settings."
          />

          <h3>Aviation news</h3>
          <Toggle label="Show news headlines" checked={t.news_enabled} onChange={set("ticker", "news_enabled")} />
          {t.news_enabled && (
            <>
              <TextArea
                label="Feeds (RSS or Atom, one per line)"
                rows={3}
                value={t.news_feeds}
                onChange={set("ticker", "news_feeds")}
                help="Default: Austrian Wings and FlightGlobal. The Aviation Herald and Aviation Safety Network don't offer a feed that can be used."
              />
              <TextInput
                label="Only headlines containing"
                value={t.news_keywords}
                onChange={set("ticker", "news_keywords")}
                help="Comma separated, not case-sensitive, also matches inside words (absturz → Flugzeugabsturz). Leave empty to show all headlines."
              />
              <div className="grid-3">
                <NumberInput label="Max. age" unit="hours" value={t.news_max_age_hours} min={1} max={168} onChange={set("ticker", "news_max_age_hours")} />
                <NumberInput label="Max. headlines" value={t.news_max_items} min={1} max={20} onChange={set("ticker", "news_max_items")} />
                <NumberInput label="Check every" unit="seconds" value={t.refresh_seconds} min={300} max={3600} step={60} onChange={set("ticker", "refresh_seconds")} />
              </div>
              <TestButton source="news" draft={draft} label="Test feeds" />
            </>
          )}
          <p className="help">Announcements can also run in the ticker; see "Announcements" below.</p>
        </>
      )}
    </Card>
  );
}

export function SlidesCard({ draft, set }: { draft: Config; set: Setter }) {
  const a = draft.announcements;
  return (
    <Card title="Announcement slides" icon={<Megaphone className="icon" />}>
      <Toggle
        label="Show announcements as full-screen slides"
        checked={a.slides_enabled}
        onChange={set("announcements", "slides_enabled")}
        help="Slides cover the dashboard briefly, then it comes back. They never take more than half of the time."
      />
      <div className="grid-2">
        <NumberInput
          label="Show slides every"
          unit="minutes"
          value={a.slide_every_minutes}
          min={1}
          max={120}
          onChange={set("announcements", "slide_every_minutes")}
        />
        <NumberInput label="Each slide for" unit="seconds" value={a.slide_seconds} min={5} max={120} onChange={set("announcements", "slide_seconds")} />
      </div>
    </Card>
  );
}
