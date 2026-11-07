# Digital Signage – Aviation Student Dashboard

A full-screen information display for aviation students at FH JOANNEUM Graz,
built for a Raspberry Pi driving a TV. It shows:

- **Live air traffic**: an ADS-B Exchange map, plus the nearest aircraft with
  airline, route, type, altitude, speed and distance
- **Weather** in aviation units: wind (°/kt, gusts), QNH, visibility, dew point
- **Public transport departures** from a configurable stop, with real-time delays and cancellations
- **Upcoming lectures** from the FH JOANNEUM timetable, including lectures in progress and exams
- **Announcements** (optional): event invitations and notices, with a poster image, shown as
  a full-screen slide every few minutes and/or in the ticker, between a start and end date
- **News ticker** (optional): a line at the bottom with emergencies (squawk 7700/7600/7500) and
  rare or military aircraft nearby, aviation news headlines and announcements. It only
  appears while there is something to show
- **Screen sharing** (optional): show a laptop's screen on the TV from the browser, after
  entering a code shown on the TV. No cable, no app, no switching TV inputs

Everything is configured in a browser at `/admin`.

## Install on a Raspberry Pi

```bash
curl -fsSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/install.sh | sudo bash
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

### Screen sharing

Turn it on under "Screen sharing" in the admin page. Then:

1. On a laptop, open `https://<public address>/share`. The admin page shows the address.
2. Click "Show a code on the TV" and type the 4-digit code that appears on the TV.
3. Choose a window, a browser tab or the whole screen. The TV shows it until you stop,
   or until someone else enters a new code.

The setup goes through the app (and the Cloudflare tunnel, if you use one). The video
itself goes directly from the laptop to the Pi over the local network (WebRTC). If no
direct connection comes up within 6 seconds, it streams through the server instead,
with 1–2 s delay. That can be turned off in admin.

Only the browser on the Pi itself receives shared screens; visitors of the public
dashboard never do. Phones can't share: their browsers don't support screen capture.

**Networks that block mDNS:** browsers hide their local IP address behind a
`….local` name, which can't be resolved there. The installer therefore sets a
Chromium policy (`/etc/chromium/policies/managed/digital-signage.json`) that lets
the dashboard on `localhost` use the Pi's real address. Restart the kiosk browser
(or reboot) after installing or updating.

**Public address:** not configured anywhere. The app remembers the host name of
the first request that arrives through Cloudflare, and shows it in admin and on
the TV while someone is sharing. You can override it in admin.

**Cloudflare Access:** protecting `/share` with an Access policy works well on top
of the code. The application must cover both `/share` and `/api/share/` (the page's
requests go there), and must *not* cover `/api/share/screen/`; that's only used
by the Pi itself over localhost, so it never passes through Cloudflare anyway.
When Access logs someone in, the app uses their e-mail address as the name on the TV.

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
| Ticker news | RSS/Atom feeds (default: Austrian Wings, FlightGlobal) | no |

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
- **News feeds:** The Aviation Herald has no public feed, and Aviation Safety
  Network blocks automated clients, so the ticker uses feeds that are openly
  published, filtered by keywords such as "crash" or "Notlandung".
- **Slides** never cover the dashboard more than half of the time. Their
  schedule follows the clock, so it survives reloads.

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
  ticker.py         aircraft events (emergencies, rare types) for the ticker
  announcements.py  announcements and uploaded images (data/media/)
  share.py          screen sharing: codes, signaling, fallback stream
  providers/        one module per external API
frontend/src/
  display/          the TV screen (AutoFitList, panels, ticker, slides, shared screen)
  admin/            settings UI
  share/            the /share page for laptops
tests/              pytest suite + recorded API responses
docs/trias-api.md   notes on the TRIAS API
```

## Credits

Aircraft silhouettes: `static/icons/adsb_icons` (see the attribution file in
that folder). Flight data: the adsb.lol, adsb.fi and airplanes.live
communities; routes from adsbdb.com. Weather: Open-Meteo.com (CC BY 4.0).
Transport: Verbund Linie TRIAS open data.
