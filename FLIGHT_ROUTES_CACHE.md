# Flight Route Cache System

## Overview

The aviation dashboard uses a **persistent route cache** to store flight callsign-to-airport mappings. This allows the system to display departure and arrival airports even when using APIs that don't provide this information (like airplanes.live).

## How It Works

1. **Primary Data Source**: airplanes.live API (unlimited, real-time aircraft positions)
2. **Route Cache**: Local JSON file (`flight_routes_cache.json`) stores callsign → airport mappings
3. **Learning System**: Cache grows automatically over time as you add routes
4. **Persistent Storage**: Cache survives updates and restarts

## Adding Routes

### Via Admin Interface

1. Open the admin page: `http://your-ip:8080/admin`
2. Scroll to "Route Cache Management"
3. Enter flight details:
   - **Flight**: Callsign (e.g., `DLH123`, `BAW456`)
   - **From**: Departure airport ICAO code (e.g., `FRA`, `LHR`)
   - **To**: Arrival airport ICAO code (e.g., `JFK`, `LAX`)
4. Click "Add Route"

### Via API

```bash
curl -X POST http://localhost:8080/api/flight-routes/add \
  -H "Content-Type: application/json" \
  -d '{"callsign": "DLH123", "from": "FRA", "to": "JFK"}'
```

### Batch Import

You can manually edit `flight_routes_cache.json`:

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

## Airport Code Resources

- **ICAO Codes**: 4-letter international codes (FRA, EDDF, KJFK)
- **IATA Codes**: 3-letter codes (FRA, JFK, LAX) - also work

### Lookup Tools:
- https://www.world-airport-codes.com/
- https://airportcodes.aero/
- https://www.iata.org/en/publications/directories/code-search/

## Common Routes Examples

### European Hubs
```
DLH = Frankfurt (FRA) hub
BAW = London Heathrow (LHR) hub
AFR = Paris CDG (CDG) hub
KLM = Amsterdam (AMS) hub
SWR = Zurich (ZRH) hub
AUA = Vienna (VIE) hub
```

### North American Carriers
```
AAL = American Airlines (Dallas/DFW, Charlotte/CLT hubs)
DAL = Delta (Atlanta/ATL, Detroit/DTW hubs)
UAL = United (Chicago/ORD, Houston/IAH hubs)
SWA = Southwest (Dallas/DAL, Baltimore/BWI hubs)
```

### Middle East & Asia
```
UAE = Emirates (Dubai/DXB hub)
QTR = Qatar (Doha/DOH hub)
ETD = Etihad (Abu Dhabi/AUH hub)
SIA = Singapore (Singapore/SIN hub)
THY = Turkish (Istanbul/IST hub)
```

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

## Tips for Building Your Cache

1. **Start with common routes** in your area
2. **Observe the display** - note which flights appear regularly
3. **Add routes gradually** as you see repeated callsigns
4. **Use airline prefixes** for generic hub info (e.g., "DLH" = Lufthansa/FRA)
5. **Share cache files** with others in your region

## Troubleshooting

**Routes not showing:**
- Ensure callsign matches exactly (case-insensitive)
- Check JSON syntax in cache file
- Verify file permissions (should be readable by `digital-signage` user)

**Cache not persisting:**
- Check disk space
- Verify write permissions to application directory
- Check logs: `sudo journalctl -u digital-signage -f`

## Future Enhancements

Potential improvements:
- [ ] Web scraping for automatic route discovery
- [ ] Integration with FlightAware/FlightRadar24 APIs
- [ ] Community-shared cache database
- [ ] Machine learning for route prediction
- [ ] Historical data analysis for common patterns

## API Comparison

| Feature | AirLabs | Airplanes.live + Cache |
|---------|---------|------------------------|
| API Calls | 1,000/month (limited) | Unlimited |
| API Key | Required | None |
| Real-time | ✅ | ✅ |
| Airports | ✅ Built-in | ✅ Via cache |
| Setup | Immediate | Builds over time |
| Cost | Free tier limited | Free forever |

## Contributing

Have a large route cache? Share it with the community!
- Export your `flight_routes_cache.json`
- Submit as GitHub issue or pull request
- Help others bootstrap their displays
