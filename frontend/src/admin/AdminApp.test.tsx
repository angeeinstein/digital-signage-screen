import { act, fireEvent, render, screen } from "@testing-library/react";
import AdminApp from "./AdminApp";
import type { Config } from "../lib/types";

const config: Config = {
  location: { name: "Graz", lat: 47.07, lon: 15.44, timezone: "Europe/Vienna" },
  display: { font_scale: 1, map_enabled: true, map_zoom: 8.5 },
  weather: { enabled: true, provider: "open-meteo", openweathermap_api_key: "", refresh_seconds: 600 },
  flights: { enabled: true, providers: ["adsb.lol", "adsb.fi"], radius_km: 75, max_items: 6, include_ground: false, refresh_seconds: 15 },
  routes: { enabled: true, cache_days: 14, airlabs_enabled: false, airlabs_api_key: "", airlabs_daily_limit: 30 },
  transport: { enabled: true, stop_id: "at:46:4227", stop_name: "Alte Poststraße", max_items: 8, refresh_seconds: 60 },
  timetable: { enabled: true, cohorts: "", max_items: 8, time_window_hours: 24, show_ongoing: true, refresh_seconds: 300 },
};

function mockFetch(loggedIn: boolean) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const json = (body: unknown, status = 200) =>
    Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (url === "/api/auth/session") return json({ ok: true, logged_in: loggedIn, username: "admin", must_change: false });
    if (url === "/api/admin/config" && (!init || init.method === "GET"))
      return json({ ok: true, config, revision: 3 });
    if (url === "/api/admin/config" && init?.method === "PUT") {
      const body = JSON.parse(String(init.body));
      return json({ ok: true, config: body.config, revision: 4 });
    }
    if (url === "/api/admin/status") return json({ ok: true, sources: {} });
    return json({ ok: false, error: "unexpected" }, 404);
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

test("shows login when not authenticated", async () => {
  mockFetch(false);
  render(<AdminApp />);
  expect(await screen.findByRole("button", { name: "Sign in" })).toBeTruthy();
});

test("loads config, edits a value and saves only after Save", async () => {
  const calls = mockFetch(true);
  render(<AdminApp />);
  const radius = (await screen.findByLabelText("Radius (km)")) as HTMLInputElement;
  expect(radius.value).toBe("75");
  expect(screen.getByText("All changes saved")).toBeTruthy();

  fireEvent.change(radius, { target: { value: "40" } });
  expect(screen.getByText("You have unsaved changes")).toBeTruthy();

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /Save/ }));
  });
  const put = calls.find((c) => c.init?.method === "PUT");
  expect(put).toBeTruthy();
  expect(JSON.parse(String(put!.init!.body)).config.flights.radius_km).toBe(40);
  expect((put!.init!.headers as Record<string, string>)["X-Requested-With"]).toBe("signage");
  expect(await screen.findByText("All changes saved")).toBeTruthy();
});
