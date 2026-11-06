# Changelog

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
