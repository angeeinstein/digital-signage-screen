# Quick Start - Aviation Dashboard

## 🚀 Deploy to Raspberry Pi

```bash
# Update the installation
curl -sSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/install.sh | sudo bash
# Select option 1 (Update existing installation)
```

## 🔧 Configure Dashboard

1. **Open admin panel**: http://192.168.1.145:8080/admin

2. **Set your location**:
   - Location Name: Your city/campus name
   - Latitude & Longitude: [Get from Google Maps](https://www.google.com/maps) (right-click → coordinates)

3. **Get Weather API Key** (FREE):
   - Go to https://openweathermap.org/api
   - Click "Sign Up" → Create free account
   - Navigate to "API keys" → Copy your key
   - Paste in dashboard admin → Weather Settings

4. **Setup Lecture Timetable**:
   - Click "Add Lecture"
   - Fill in: Year Group, Day, Time, Name, Room
   - Repeat for all your lectures
   - Click "Save Configuration"

5. **View Dashboard**: http://192.168.1.145:8080/
   - Press F11 for fullscreen

## 📱 URLs

| Page | URL | Purpose |
|------|-----|---------|
| **Dashboard** | http://192.168.1.145:8080/ | Main information display |
| **Settings** | http://192.168.1.145:8080/admin | Configure dashboard |

## 🎯 What's Displayed

- ⏰ **Time & Date** - Large, always visible
- ✈️ **Live Flight Tracking** - Aircraft in your area
- 🌤️ **Weather** - Temp, wind, humidity, pressure, visibility
- 🚌 **Transport** - Next departures (configure API later)
- 📅 **Lecture Timetable** - Next classes for all years

## 🔄 Auto-Updates

- Time: Every 1 second
- Weather: Every 5 minutes  
- Timetable: Every 1 minute
- Transport: Every 1 minute

## 📍 Example Locations

Find your coordinates on [Google Maps](https://www.google.com/maps):
1. Right-click on your location
2. Click the coordinates to copy
3. Paste in dashboard admin

Common aviation schools:
- **Frankfurt** (example): 50.1109, 8.6821
- **London**: 51.5074, -0.1278
- **Paris**: 48.8566, 2.3522

## 🚌 Transport API (Todo)

When you have the API details, provide:
- API provider name
- API endpoint URL
- Stop/Station ID
- API key (if needed)

I'll integrate it for you!

## ⚙️ Troubleshooting

**Weather not showing?**
- Check API key is entered correctly
- Wait 5 minutes for first update
- New API keys can take 10 minutes to activate

**Timetable empty?**
- Make sure lectures are added for current day
- Check "Enable Timetable Display" is ON
- Save configuration after changes

**Flight radar blank?**
- Check internet connection
- Try refreshing the page
- ADS-B Exchange may take 30 seconds to load

## 💡 Tips

- Run on a large TV/monitor for best effect
- Use Chrome or Firefox in fullscreen (F11)
- Set browser to auto-start on boot
- Keep Raspberry Pi connected to ethernet for stable connection
- Add lectures for the whole week at once

## 📝 Sample Timetable Entry

```
Year Group: Year 1
Day: Monday
Time: 09:00
Lecture: Flight Principles & Aerodynamics
Room: A101
```

## Need Help?

Check [DASHBOARD_SETUP.md](DASHBOARD_SETUP.md) for detailed documentation!
