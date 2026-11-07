# Changelog

## 2.3.0 – 2026-11-07

### Added
- **Kiosk helper** (`kiosk/agent.py`), set up by the installer on Pis with a desktop:
  starts Chromium on the dashboard, restarts it when it crashes or the page freezes.
- **Screen** section in admin: status of the TV and the helper, buttons to reload the
  display, restart the browser, restart the Pi, and take a screenshot of the TV.
- **Monitoring**: optional check-ins to healthchecks.io (or similar); reports a failure
  when the dashboard on the TV stops updating, with a grace period after boot.
- **Updates** section in admin: check for a newer version and update with one click,
  with the installer's output shown live. A root path unit runs the update; the app
  only requests it.
- Pause/resume button and "Fill the screen" poster layout for announcements.

### Fixed
- `install.sh --update` without `--branch` switched to `main`; it now keeps the
  installed branch and remote.
- The kiosk helper reports failed screenshots, finds the Wayland display itself, and
  restarts itself after an update.

### Changed
- The mouse pointer is hidden on the display.

## 2.2.0 – 2026-11-07

### Added
- **Screen sharing** (off by default): a laptop opens `/share`, enters the code the TV
  shows, and its screen appears on the TV. Video goes directly over the local network
  (WebRTC), with automatic fallback to streaming through the server, e.g. via the
  Cloudflare tunnel. Only the Pi's own browser can receive. Admin switch, live status,
  and "Stop sharing".
- The public address is detected from requests that come through Cloudflare.
- Installer sets a Chromium policy so the kiosk can share its real IP address with
  laptops (needed where mDNS is blocked) and play shared sound.
- Time limit for screen sharing (default 2 hours, 0 = none). 5 minutes before the end
  the laptop can extend once, by half the limit; the TV shows a countdown. A forgotten
  laptop can no longer block the TV all day.

### Changed
- The admin page is grouped into sections with a side menu (a row of tabs on phones).
  Sections with unsaved changes are marked.
- gunicorn uses 16 threads (screen sharing keeps a few requests open).

### Fixed
- The ticker stuttered on the Pi: the whole dashboard re-rendered every second and on every poll, and the scroll speed wasn't a whole number of pixels per frame. Now only the clock ticks every second, panels re-render only when their data changes, and the speed is rounded to whole pixels per frame.
- Login throttling behind the Cloudflare tunnel: all visitors appeared to come from
  localhost, so failed logins from anyone locked everyone out. The visitor's address
  from Cloudflare is used now.

## 2.1.0 – 2026-11-07

### Added
- **Announcements**: event invitations and notices with an optional poster image, a start and
  end date, shown as full-screen slides every few minutes and/or in the ticker. "Show now"
  button to check one on the TV. Slides never cover the dashboard more than half of the time.
- **News ticker** (off by default): emergencies and rare or military aircraft from the live
  ADS-B data, aviation headlines from RSS feeds filtered by keywords, and announcements.
  It disappears when there is nothing to show; the dashboard takes the space back.
- "News (ticker)" in the admin status overview, and a test button for the feeds.

### Changed
- Medical flights ("lifeguard") are no longer highlighted as emergencies.
- nginx accepts uploads up to 12 MB (was 1 MB).

## 2.0.0 – 2026-11-06

Complete rewrite. The v1 knowledge (API quirks, timetable parsing, aircraft icons) was kept; the code and UI are new.

### Fixed
- **Admin access could be forged**: v1 signed sessions with a hard-coded secret key. A random key is now generated on first start.
- **API keys were public**: `/api/dashboard/config` returned all secrets to anyone. The public endpoint now strips them; the admin UI masks them.
- **Updates reset the admin password** to `admin/admin` (the updater's `git stash -u` swallowed `admin_auth.json`). The installer now recovers that file from the stash if possible.
- **Flight list often empty**: airplanes.live now answers 403 to unregistered clients; adsb.lol and adsb.fi are used first, with automatic failover.
- **Distances were wrong**: the API's `dst` is nautical miles, but v1 showed it as km.
- **Wrong routes**: v1 took routes from OpenSky flight history that was 2–3 days old. Routes now come from adsbdb by callsign, with a plausibility check.
- **Rows cut off** when lists got longer: the display now shows only rows that fit completely.
- Ongoing lectures disappeared at their start time; they are now shown with a progress bar.
- Route lookups blocked the flights request and spent API quota on aircraft that weren't displayed.
- The weather panel showed a fake 20 °C when no API key was set. The default is now Open-Meteo, which needs no key.
- The nginx option proxied to the wrong port.

### Changed
- Backend split into the `signage/` package. Data is fetched by background pollers; a failing source shows its last data marked as stale.
- New React + TypeScript frontend (display and admin), scaled to the screen size (720p to 4K, portrait).
- Passwords use salted hashes (Werkzeug); old hashes are upgraded at the next login. Logins are throttled and requests are CSRF-protected.
- All runtime state lives in `data/` (git-ignored). v1 files are migrated automatically.
- One gunicorn worker with threads, so there is one shared set of caches.
- Installer rewritten: detects the service user, installs a recent Node.js, builds the frontend, backs up settings, checks health after starting.
- Tests (pytest, vitest) and CI that runs the real installer.

### Removed
- `trias_client.py` (unused, imported a module that didn't exist), the unused seed and template files, and outdated docs.

## 1.0.0 – 2026-02-06
- Initial version (Flask templates, OpenSky/AirLabs routes, OpenWeatherMap).
