# Digital Signage – Aviation Student Dashboard

A full-screen information display for aviation students at FH JOANNEUM Graz,
built for a Raspberry Pi driving a TV. It shows:

- **Live air traffic**: an ADS-B Exchange map, plus the nearest aircraft with
  airline, route, type, altitude, speed and distance
- **Weather** in aviation units: wind (°/kt, gusts), QNH, visibility, dew point
- **Public transport departures** from a configurable stop, with real-time delays and cancellations
- **Upcoming lectures** from the FH JOANNEUM timetable, including lectures in progress and exams

Everything is configured in a browser at `/admin`.

## Install on a Raspberry Pi

```bash
curl -sSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/install.sh | sudo bash
```

The installer:

- installs Python, git and Node.js (from NodeSource if the system's version is too old)
- clones the app to `/opt/digital-signage`
- builds the frontend
- sets up a systemd service

It can optionally put nginx in front, so the dashboard is reachable on port 80.

Then open `http://<pi-address>:8080/admin`, log in with **admin / admin** and
set a new password (you will be asked to). Set the location, pick your stop,
and save. The display at `http://<pi-address>:8080/` picks up changes within a
few seconds.

Running `install.sh` again on an installed system offers **Update**, **Repair** and
**Uninstall**. The same actions are available without the menu:

```bash
sudo bash /opt/digital-signage/install.sh --update
sudo bash /opt/digital-signage/install.sh --repair
sudo bash /opt/digital-signage/install.sh --help    # all options (port, nginx, user, branch)
```

Updates never touch your settings. Everything the app writes lives in
`/opt/digital-signage/data/`, which git ignores, and every update first backs
it up to `/var/backups/digital-signage/`. Upgrading from v1 migrates the old
`dashboard_config.json` and `admin_auth.json` automatically.

### Showing it full-screen (kiosk)

Raspberry Pi OS (Bookworm or later, Wayland/labwc desktop), logged in automatically as the desktop user:

```bash
sudo raspi-config nonint do_blanking 1          # disable screen blanking
mkdir -p ~/.config/labwc
cat >> ~/.config/labwc/autostart <<'EOF'
chromium-browser --kiosk --noerrdialogs --disable-infobars --no-first-run \
  --disable-session-crashed-bubble --check-for-update-interval=31536000 \
  http://localhost:8080/ &
EOF
```

On Debian Trixie–based images the browser binary is called `chromium`. The
display reconnects on its own if the server restarts, and it reloads itself
after an update.

## How it works

```
 Browser (React)                     Flask app (one gunicorn process)
 ───────────────                     ───────────────────────────────────────────────
 /            display  ── polls ──▶  /api/display ◀── snapshots ── background pollers
 /admin       settings               /api/admin/*                   ├─ flights   (15 s)
                                                                    ├─ weather   (10 min)
                                                                    ├─ transport (1 min)
                                                                    └─ timetable (5 min)
```

The backend fetches every data source on its own background thread. HTTP
requests only read the latest snapshot, so a slow or failing upstream API
can't stall the screen. When a fetch fails, the last good data stays up with
an "updated x min ago" marker, rather than the panel going blank.

| Panel | Source | Key needed |
|---|---|---|
| Aircraft | adsb.lol, adsb.fi, airplanes.live (tried in order) | no |
| Routes | adsbdb.com by callsign; AirLabs as an optional fallback | AirLabs only |
| Weather | Open-Meteo, or OpenWeatherMap | OWM only |
| Departures | TRIAS API of Verbund Linie (Austria) | no |
| Lectures | `almaty.fh-joanneum.at` timetable JSON | no |

### Lessons learned (why v2 looks the way it does)

- **airplanes.live returns HTTP 403** to API clients that haven't registered
  with them. This was the main reason the v1 flight list was often empty.
  It's now only the last fallback.
- **`dst` in readsb APIs is nautical miles**, not km. Distances are now
  computed from the coordinates.
- **OpenSky's flight history is 2–3 days old**, so routes taken from it were
  often wrong. Routes now come from adsbdb by callsign. A route is hidden if
  the aircraft's position isn't plausibly on the way between the two airports.
- **TRIAS stop search** works much better with the town name ("Graz Alte
  Poststraße"). The admin search adds it automatically and ranks nearby stops first.
- **Lecture titles** follow a fixed pattern. Parsing is covered by tests in
  `tests/test_providers.py` using real responses.
- **List overflow:** the display measures each list and only shows rows that
  fit completely ("6 of 9"). Every cell truncates with "…" instead of
  overflowing.

## Development

You need Python ≥ 3.9 and Node.js ≥ 20.19.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd frontend && npm ci && cd ..

python app.py                      # backend on http://127.0.0.1:5000
cd frontend && npm run dev         # frontend on http://localhost:5173 (proxies /api)
```

Set `SIGNAGE_DATA_DIR` to keep development settings away from the repo (the
default is `./data`).

Checks (CI runs the same):

```bash
ruff check . && pytest -q                       # backend
cd frontend && npx tsc -b && npx vitest run     # frontend
```

CI also runs `install.sh` on a fresh Ubuntu machine, and checks that the
service comes up and that an update keeps the settings.

### Layout

```
signage/            Flask backend
  api.py            HTTP endpoints (/api/display public, /api/admin/* login required)
  config.py         settings schema, validation, v1 migration
  auth.py           password hashing, login throttling, CSRF guard
  poller.py         background refresh with stale/error tracking
  services.py       wires settings → data sources → pollers
  providers/        one module per external API
frontend/src/
  display/          the TV screen (AutoFitList, panels)
  admin/            settings UI
tests/              pytest suite + recorded API responses
docs/trias-api.md   notes on the TRIAS API
```

## Credits

Aircraft silhouettes: `static/icons/adsb_icons` (see the attribution file in
that folder). Flight data: the adsb.lol, adsb.fi and airplanes.live
communities; routes from adsbdb.com. Weather: Open-Meteo.com (CC BY 4.0).
Transport: Verbund Linie TRIAS open data.
