# Aviation Dashboard Setup Guide

This guide will help you configure the aviation student information dashboard.

## Quick Start

1. **Access the dashboard**: Navigate to `http://your-ip:8080/`
2. **Configure settings**: Go to `http://your-ip:8080/admin`

## Features

### 🕐 Time & Date
Automatically displays current time and date - no configuration needed!

### ✈️ Flight Radar
Shows live aircraft in your area using ADS-B Exchange. The map automatically centers on your configured location.

**Configuration:**
- Set your latitude and longitude in the dashboard admin panel
- Default view shows aircraft within ~150km radius

### 🌤️ Weather
Displays real-time weather conditions including temperature, wind, humidity, pressure, and visibility.

**Setup:**
1. Get a free API key from [OpenWeatherMap](https://openweathermap.org/api)
2. Sign up for a free account
3. Navigate to API keys section
4. Copy your API key
5. Paste it in Dashboard Admin → Weather Settings → API Key
6. Save configuration

### 🚌 Public Transport Departures
Shows next departures for bus/tram at your nearest stop.

**Setup:**
Once you provide the API details for your local transport system, I'll integrate it. For now:
1. Go to Dashboard Admin → Public Transport Settings
2. Enter your API URL and Stop ID when available
3. Enable the transport display

### 📅 Lecture Timetable
Displays upcoming lectures for different year groups.

**Setup:**
1. Go to Dashboard Admin → Lecture Timetable
2. Click "Add Lecture" to create new entries
3. Fill in:
   - **Year Group**: e.g., "Year 1", "Year 2", etc.
   - **Day**: Select day of the week
   - **Time**: Lecture start time (24-hour format)
   - **Lecture Name**: e.g., "Flight Principles"
   - **Room**: e.g., "A101"
4. Click "Save Configuration"

The dashboard automatically:
- Shows only lectures for the current day
- Highlights lectures happening now or within 30 minutes
- Displays the next 8 upcoming lectures
- Updates every minute

## Location Configuration

Set your location in Dashboard Admin:
- **Location Name**: Display name (e.g., "Frankfurt")
- **Latitude**: Used for weather and flight tracking
- **Longitude**: Used for weather and flight tracking

Example coordinates:
- Frankfurt: 50.1109, 8.6821
- London: 51.5074, -0.1278
- Paris: 48.8566, 2.3522

## Auto-Refresh

The dashboard automatically refreshes:
- Time: Every second
- Weather: Every 5 minutes
- Transport: Every minute
- Timetable: Every minute

## Full Screen Mode

For the best experience:
1. Open the dashboard in a browser
2. Press F11 (or browser's fullscreen option)
3. The display will automatically scale to fit

## Customization

### Flight Radar Options

You can customize the flight radar view by editing the URL in [dashboard.html](templates/dashboard.html):

Current: ADS-B Exchange (free, no account needed)
- Shows all aircraft with ADS-B transponders
- Real-time data
- No API key required

Alternative: FlightRadar24 (requires subscription for embedding)

### Adding More Content

The dashboard is modular. You can add more widgets by:
1. Editing [dashboard.html](templates/dashboard.html)
2. Adding new grid sections
3. Creating corresponding API endpoints in [app.py](app.py)

## Troubleshooting

**Weather not showing:**
- Verify your OpenWeatherMap API key is correct
- Check that you've saved the configuration
- API keys can take a few minutes to activate after creation

**Flight radar not loading:**
- Check your internet connection
- Verify the ADS-B Exchange website is accessible
- Try refreshing the page

**Timetable not showing lectures:**
- Ensure lectures are configured for the current day
- Check that lecture times are in 24-hour format (HH:MM)
- Verify "Enable Timetable Display" is checked

**Transport departures showing "Loading...":**
- This feature requires API integration
- Contact admin to configure the transport API

## API Endpoints

For developers:

- `GET /api/dashboard/config` - Get dashboard configuration
- `POST /api/dashboard/config` - Update configuration
- `GET /api/dashboard/weather` - Get weather data
- `GET /api/dashboard/transport` - Get transport departures
- `GET /api/dashboard/timetable` - Get lecture timetable

## Example Transport API Integration

When you provide your transport API details, I'll integrate it. Most transport APIs follow this pattern:

```python
response = requests.get(
    f"{api_url}/departures/{stop_id}",
    headers={"Authorization": f"Bearer {api_key}"}
)
```

Common transport APIs:
- Germany: VRR, RMV, Deutsche Bahn
- UK: TfL (Transport for London)
- Others: Let me know your location!
