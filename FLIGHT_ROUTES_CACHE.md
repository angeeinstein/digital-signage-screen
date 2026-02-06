# Flight Route Cache System

## Overview

The aviation dashboard uses **automatic route discovery** powered by OpenSky Network's historical flight data API. Routes are cached locally for efficiency, requiring minimal API calls while providing accurate, real-time airport information.

## How It Works

1. **Primary Data Source**: airplanes.live API (unlimited, real-time aircraft positions)
2. **Route Discovery**: OpenSky Network API (historical flight data for airports)
3. **Smart Caching**: Local JSON file stores callsign → airport mappings with 7-day expiry
4. **Automatic Refresh**: Expired cache entries are automatically refreshed from OpenSky

### Data Flow

```
┌─────────────────────┐
│ Airplanes.live API  │ (Unlimited calls)
│ Real-time positions │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Check Local Cache   │
│ Is route cached?    │
│ Is cache fresh?     │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │ YES         │ NO
    ▼             ▼
┌────────┐    ┌────────────────┐
│ Use    │    │ OpenSky API    │
│ Cache  │    │ Fetch route    │
└────────┘    │ Update cache   │
              └────────────────┘
```

## Setup

### Anonymous Access (Default)
- **No credentials needed**
- 400 API credits/day
- 10-second data resolution
- Perfect for most users

### With Free Account (Recommended)
1. Sign up at https://opensky-network.org/register
2. Go to admin panel: `http://your-ip:8080/admin`
3. Enter username and password
4. Benefits:
   - **8,000 API credits/day** (vs 400 anonymous)
   - Historical data access
   - 5-second data resolution

## Configuration

### Via Admin Interface

1. Open `http://your-ip:8080/admin`
2. Scroll to "OpenSky Network - Automatic Route Discovery"
3. Configure:
   - ✅ **Enable automatic route lookup** (checked by default)
   - **Username** (optional - for higher limits)
   - **Password** (optional)
   - **Cache Expiry**: 7 days (default, adjustable 1-90 days)

## How Cache Works

### Automatic Discovery Process

1. **Flight detected** by airplanes.live
2. **Cache lookup**: Check if route is cached and fresh
3. **If not cached**: Query OpenSky for recent flights by this aircraft
4. **Cache update**: Store departure/arrival airports with timestamp
5. **Display**: Show complete flight info with airports

### Cache Efficiency

With default 7-day expiry:
- **Day 1**: 20 flights detected → 20 OpenSky API calls
- **Day 2-7**: Same flights → 0 API calls (all cached)
- **Day 8**: Cache expires → 20 API calls to refresh
- **Result**: ~3 API calls per flight per month

## Manual Route Override (Optional)

You can still manually add specific routes if needed:

### Via Admin Interface

1. Go to `http://your-ip:8080/admin`
2. Scroll to "Manual Route Override"
3. Enter flight details and click "Add Route"

### Via API

```bash
curl -X POST http://localhost:8080/api/flight-routes/add \
  -H "Content-Type: application/json" \
  -d '{"callsign": "DLH123", "from": "FRA", "to": "JFK"}'
```

```json
{
  "DLH123": {
    "from": "FRA",
    "to": "JFK",
    "last_seen": "2026-02-06T12:00:00"
  },
  "BAW456": {
    "from": "LHR",
    "to": "LAX",
    "last_seen": "2026-02-06T12:30:00"
  }
}
```

## Cache File Structure

Location: `flight_routes_cache.json`

```json
{
  "DLH123": {
    "from": "FRA",
    "to": "JFK",
    "last_seen": "2026-02-06T12:00:00"
  },
  "BAW456": {
    "from": "LHR",
    "to": "LAX",
    "last_seen": "2026-02-06T12:30:00"
  }
}
```

- **Automatic entries**: Added by OpenSky lookup
- **Manual entries**: Added via admin UI or API
- **last_seen**: ISO 8601 timestamp for cache expiry
- **Expiry**: Refreshed after configured days (default: 7)

## OpenSky API Details

### Rate Limits

| User Type | Daily Credits | Resolution | Cost per Request |
|-----------|---------------|------------|------------------|
| Anonymous | 400 | 10 seconds | 1-4 credits* |
| Registered | 4,000 | 5 seconds | 1-4 credits* |
| Contributing | 8,000 | 5 seconds | 1-4 credits* |

*Credits depend on query complexity (bounding box size, time range)

### API Endpoint Used

```
GET /api/flights/aircraft?icao24={hex}&begin={timestamp}&end={timestamp}
```

- **icao24**: Aircraft transponder hex code (from airplanes.live)
- **begin/end**: 7-day time window
- **Response**: Array of historical flights with airports

### Authentication

Optional HTTP Basic Auth:
- Username: OpenSky account username
- Password: OpenSky account password

## Airport Code Resources

- **ICAO Codes**: 4-letter international codes (FRA, EDDF, KJFK)
- **IATA Codes**: 3-letter codes (FRA, JFK, LAX) - also work

### Lookup Tools:
- https://www.world-airport-codes.com/
- https://airportcodes.aero/
- https://www.iata.org/en/publications/directories/code-search/

## Benefits Over Manual Entry

| Feature | Manual Entry | Automatic Discovery |
|---------|-------------|---------------------|
| **Setup** | Add each route | Configure once |
| **Accuracy** | Depends on user | Real flight data |
| **Maintenance** | Update manually | Auto-refreshes |
| **Coverage** | Limited to entries | Discovers all flights |
| **Effort** | High | Zero |

## Troubleshooting

### Routes Not Appearing

**Check OpenSky is enabled:**
- Go to admin panel
- Verify "Enable automatic route lookup" is checked

**Check credentials (if using):**
- Test login at https://opensky-network.org/
- Verify username/password in admin panel
- Check logs: `sudo journalctl -u digital-signage -f`

**Check rate limits:**
- Anonymous: 400 credits/day
- With account: 4,000-8,000 credits/day
- Wait until next day if limit reached

### Aircraft Not in OpenSky Database

Some aircraft may not have recent flight history:
- Private/general aviation
- Military aircraft
- New aircraft
- Flights outside OpenSky coverage

**Solution**: Add routes manually for these specific flights

### Cache Not Persisting

- Check disk space: `df -h`
- Verify write permissions: `ls -la /opt/digital-signage/`
- Check logs: `sudo journalctl -u digital-signage -f`

## Cache File Location

- **Linux/Raspberry Pi**: `/opt/digital-signage/flight_routes_cache.json`
- **Development**: `./flight_routes_cache.json`

## Backup & Restore

The route cache is automatically backed up when running:
```bash
sudo ./install.sh
```

Backup location: `/opt/digital-signage-backup-YYYYMMDD_HHMMSS/`

## Cache Statistics

View cache contents via API:
```bash
curl http://localhost:8080/api/flight-routes/list
```

## Future Enhancements

- [ ] Background worker for proactive cache warming
- [ ] Integration with FlightRadar24 for supplemental data
- [ ] Community-shared cache database
- [ ] Historical pattern analysis
- [ ] Route prediction based on time of day

## API Comparison

| Feature | Manual Cache | Automatic (OpenSky) |
|---------|-------------|---------------------|
| API Calls | 0 | 1-4 per unknown flight |
| Setup Time | Hours | Minutes |
| Accuracy | User-dependent | Real data |
| Maintenance | Manual updates | Auto-refresh |
| Coverage | Limited | Comprehensive |
| **Recommended** | Supplement | **Primary** |

## Contributing

Have suggestions for improving automatic discovery?
- Report issues on GitHub
- Share optimization tips
- Contribute code improvements
