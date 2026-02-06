# Flight Route Cache Implementation Summary

## Changes Made

### 1. Removed Limited APIs
- ❌ **AirLabs** - Removed due to 1,000 API calls/month limit
- ❌ **OpenSky Network** - Removed (real-time API doesn't provide airports)
- ✅ **Airplanes.live** - Kept as primary (unlimited, free)

### 2. Added Persistent Route Caching System

#### New Files Created:
- `flight_routes_cache.json` - Persistent cache storing callsign → airport mappings
- `flight_routes_seed.json` - Seed data with common airline hubs
- `FLIGHT_ROUTES_CACHE.md` - Complete documentation

#### Backend Changes (`app.py`):
- Added `math` module import for distance calculations
- New constant: `FLIGHT_ROUTES_CACHE_FILE`
- New functions:
  - `load_flight_routes_cache()` - Load cache from JSON file
  - `save_flight_routes_cache(cache)` - Save cache to JSON file
  - `get_route_from_cache(callsign, cache)` - Lookup airports by callsign
  - `update_route_cache(callsign, from, to, cache)` - Add/update routes
- Modified `get_flights_airplaneslive()` - Now enriches data with cached routes
- New API endpoints:
  - `POST /api/flight-routes/add` - Manually add routes
  - `GET /api/flight-routes/list` - View all cached routes

#### Frontend Changes (`admin.html`):
- Removed AirLabs/OpenSky from dropdown
- Simplified to single provider (airplanes.live)
- Added "Route Cache Management" section with:
  - Input fields for callsign, departure, arrival
  - "Add Route" button
  - Status/result display
- New JavaScript function: `addRouteToCache()`
- Updated `toggleFlightApiSettings()` to handle single provider

#### Installation Script (`install.sh`):
- Updated `backup_installation()` to backup `flight_routes_cache.json`
- Updated `restore_from_backup()` to restore `flight_routes_cache.json`

### 3. How It Works

```
┌─────────────────────┐
│ Airplanes.live API  │ (Unlimited calls)
│ Real-time positions │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Flight Data         │
│ - Callsign          │
│ - Aircraft type     │
│ - Altitude/Speed    │
│ - Distance          │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Route Cache Lookup  │ (flight_routes_cache.json)
│ Callsign → Airports │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Enriched Display    │
│ DLH123              │
│ Lufthansa           │
│ FRA → JFK           │ ← From cache
│ B747-8              │
│ 38,000 ft           │
└─────────────────────┘
```

### 4. Benefits

| Feature | Before (AirLabs) | After (Airplanes.live + Cache) |
|---------|------------------|--------------------------------|
| **API Limit** | 1,000/month | ♾️ Unlimited |
| **API Key** | Required | ❌ None needed |
| **Real-time** | ✅ | ✅ |
| **Airports** | ✅ Immediate | ✅ Via cache (builds over time) |
| **Cost** | Free tier runs out | ✅ Free forever |
| **Setup** | API key required | Zero configuration |

### 5. Usage

#### Adding Routes via Admin UI:
1. Go to http://your-ip:8080/admin
2. Scroll to "Route Cache Management"
3. Enter flight details and click "Add Route"

#### Adding Routes via API:
```bash
curl -X POST http://localhost:8080/api/flight-routes/add \
  -H "Content-Type: application/json" \
  -d '{"callsign": "DLH123", "from": "FRA", "to": "JFK"}'
```

#### Manual Cache Editing:
Edit `flight_routes_cache.json` directly:
```json
{
  "DLH123": {
    "from": "FRA",
    "to": "JFK",
    "last_seen": "2026-02-06T12:00:00"
  }
}
```

### 6. Cache Building Strategy

**Quick Start:**
1. Watch your display for a few days
2. Note which flights appear regularly
3. Add those routes manually
4. System learns over time

**Common Routes:**
- `DLH` = Lufthansa (FRA hub)
- `BAW` = British Airways (LHR hub)
- `AFR` = Air France (CDG hub)
- `UAL` = United (ORD/IAH hubs)
- `DAL` = Delta (ATL/DTW hubs)

### 7. Files Modified

```
app.py                          (Backend logic + API endpoints)
templates/admin.html            (Admin UI + route management)
install.sh                      (Backup/restore cache file)
flight_routes_cache.json        (NEW - persistent cache)
flight_routes_seed.json         (NEW - seed data)
FLIGHT_ROUTES_CACHE.md          (NEW - documentation)
```

### 8. Testing

After deployment:
1. ✅ Check flights display on main page
2. ✅ Add a test route in admin
3. ✅ Verify route appears in flight display
4. ✅ Check cache file is created
5. ✅ Test backup/restore preserves cache

### 9. Deployment

No special steps needed:
```bash
cd /opt/digital-signage
sudo git pull origin main
sudo systemctl restart digital-signage
```

The cache file will be created automatically on first use.

## Migration Notes

**For existing users:**
- AirLabs configuration will be ignored
- API key is no longer needed
- No action required - system switches automatically
- Old config preserved for reference

## Future Enhancements

- [ ] Auto-populate cache from FlightRadar24 (web scraping)
- [ ] Community-shared cache database
- [ ] Import/export cache files
- [ ] Route statistics and analytics
- [ ] Automatic route discovery via pattern matching
