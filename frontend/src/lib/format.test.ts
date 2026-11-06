import { countdown, dayLabel, formatAltitude, windText } from "./format";

const TZ = "Europe/Vienna";

test("countdown", () => {
  const now = new Date("2026-11-06T10:00:00Z");
  expect(countdown("2026-11-06T09:59:00Z", now)).toBe("now");
  expect(countdown("2026-11-06T10:05:30Z", now)).toBe("5 min");
  expect(countdown("2026-11-06T11:07:00Z", now)).toBe("1 h 07");
});

test("windText rounds to 10 degrees and shows significant gusts only", () => {
  expect(windText(327, 12, 14)).toBe("330° 12 kt");
  expect(windText(4, 12, 25)).toBe("360° 12 kt G25");
  expect(windText(null, 5, null)).toBe("VRB° 5 kt");
  expect(windText(200, 0, null)).toBe("Calm");
});

test("dayLabel uses the configured time zone", () => {
  // 23:30 UTC is already the next day in Vienna (UTC+1)
  const now = new Date("2026-11-06T12:00:00Z");
  expect(dayLabel("2026-11-06T23:30:00Z", now, TZ)).toBe("Tomorrow");
  expect(dayLabel("2026-11-06T20:00:00Z", now, TZ)).toBe("Today");
});

test("formatAltitude", () => {
  expect(formatAltitude(null, true)).toBe("Ground");
  expect(formatAltitude(36000, false)).toBe("36,000 ft");
});
