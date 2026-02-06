#!/usr/bin/env python3
"""
Digital Signage Display Application
A Flask-based digital signage solution for Raspberry Pi
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from datetime import datetime
import os
import json
import logging
import requests
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'digital-signage-secret-key-change-in-production')

# Configuration
BASE_DIR = Path(__file__).resolve().parent
CONTENT_DIR = BASE_DIR / 'content'
DASHBOARD_CONFIG_FILE = BASE_DIR / 'dashboard_config.json'

# Ensure directories exist
CONTENT_DIR.mkdir(exist_ok=True)

# Default dashboard configuration
DEFAULT_DASHBOARD_CONFIG = {
    'location': {
        'lat': 50.0,
        'lon': 8.0,
        'name': 'Default Location'
    },
    'weather': {
        'api_key': '',  # OpenWeatherMap API key
        'enabled': True
    },
    'transport': {
        'enabled': False,
        'api_url': '',
        'stop_id': ''
    },
    'timetable': {
        'enabled': True,
        'use_api': False,  # Set to True when using external API
        'api_url': '',  # URL for timetable API endpoint
        'api_key': '',  # API key if required
        'lectures': [
            {
                'year': 'Year 1',
                'time': '09:00',
                'name': 'Flight Principles',
                'room': 'A101'
            },
            {
                'year': 'Year 2',
                'time': '10:30',
                'name': 'Navigation',
                'room': 'A203'
            }
        ]
    }
}


def load_dashboard_config():
    """Load dashboard configuration from file or create default"""
    if DASHBOARD_CONFIG_FILE.exists():
        try:
            with open(DASHBOARD_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading dashboard config: {e}")
    return DEFAULT_DASHBOARD_CONFIG.copy()


def save_dashboard_config(config):
    """Save dashboard configuration to file"""
    try:
        with open(DASHBOARD_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving dashboard config: {e}")
        return False


@app.route('/')
def index():
    """Main aviation dashboard display"""
    return render_template('display.html')


@app.route('/admin')
def admin():
    """Dashboard configuration admin"""
    return render_template('admin.html')


@app.route('/api/dashboard/config', methods=['GET'])
def get_dashboard_config():
    """Get dashboard configuration"""
    config = load_dashboard_config()
    return jsonify({'success': True, 'config': config})


@app.route('/api/dashboard/config', methods=['POST'])
def update_dashboard_config():
    """Update dashboard configuration"""
    try:
        new_config = request.json
        if save_dashboard_config(new_config):
            return jsonify({'success': True, 'message': 'Dashboard configuration updated'})
        else:
            return jsonify({'success': False, 'message': 'Failed to save configuration'}), 500
    except Exception as e:
        logger.error(f"Error updating dashboard config: {e}")
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/dashboard/weather')
def get_weather():
    """Get weather data from OpenWeatherMap"""
    try:
        config = load_dashboard_config()
        api_key = config.get('weather', {}).get('api_key', '')
        
        if not api_key:
            return jsonify({
                'success': True,
                'weather': {
                    'temp': 20,
                    'description': 'No API key configured',
                    'wind': 0,
                    'humidity': 0,
                    'pressure': 1013,
                    'visibility': 10,
                    'icon': '01d'
                }
            })
        
        lat = config.get('location', {}).get('lat', 50.0)
        lon = config.get('location', {}).get('lon', 8.0)
        
        # Try One Call API 3.0 first (newer)
        url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={api_key}&units=metric&exclude=minutely,hourly,daily,alerts"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            current = data.get('current', {})
            weather = {
                'temp': current.get('temp', 0),
                'description': current.get('weather', [{}])[0].get('description', 'N/A').capitalize(),
                'wind': round(current.get('wind_speed', 0) * 3.6, 1),  # Convert m/s to km/h
                'humidity': current.get('humidity', 0),
                'pressure': current.get('pressure', 1013),
                'visibility': round(current.get('visibility', 10000) / 1000, 1),  # Convert m to km
                'icon': current.get('weather', [{}])[0].get('icon', '01d')
            }
            return jsonify({'success': True, 'weather': weather})
        elif response.status_code == 401:
            # If One Call API fails, try the free Current Weather API
            logger.info("One Call API 3.0 failed, trying Current Weather Data API")
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                weather = {
                    'temp': data['main']['temp'],
                    'description': data['weather'][0]['description'].capitalize(),
                    'wind': round(data['wind']['speed'] * 3.6, 1),  # Convert m/s to km/h
                    'humidity': data['main']['humidity'],
                    'pressure': data['main']['pressure'],
                    'visibility': round(data.get('visibility', 10000) / 1000, 1),  # Convert m to km
                    'icon': data['weather'][0]['icon']
                }
                return jsonify({'success': True, 'weather': weather})
        
        return jsonify({'success': False, 'message': 'Weather API error'}), 500
            
    except Exception as e:
        logger.error(f"Error fetching weather: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/dashboard/transport')
def get_transport():
    """Get public transport departures"""
    try:
        config = load_dashboard_config()
        transport_config = config.get('transport', {})
        
        if not transport_config.get('enabled', False):
            return jsonify({'success': True, 'departures': []})
        
        # This will be customized based on the specific API you provide
        # For now, returning mock data
        departures = [
            {'line': '3', 'destination': 'Airport', 'time': '5 min', 'color': '#E53935'},
            {'line': '12', 'destination': 'Main Station', 'time': '8 min', 'color': '#1E88E5'},
            {'line': '45', 'destination': 'University', 'time': '12 min', 'color': '#43A047'},
        ]
        
        return jsonify({'success': True, 'departures': departures})
        
    except Exception as e:
        logger.error(f"Error fetching transport: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/dashboard/nearest-flights')
def get_nearest_flights():
    """Get nearest flights from ADS-B Exchange"""
    try:
        config = load_dashboard_config()
        lat = config.get('location', {}).get('lat', 50.0)
        lon = config.get('location', {}).get('lon', 8.0)
        
        # ADS-B Exchange API - using public API
        # Note: This is a simplified version. For production, consider API rate limits
        url = f"https://globe.adsbexchange.com/api/aircraft.php"
        
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                aircraft_list = data.get('aircraft', [])
                
                # Calculate distance and filter nearby aircraft
                import math
                nearby_flights = []
                
                for aircraft in aircraft_list:
                    if 'lat' not in aircraft or 'lon' not in aircraft:
                        continue
                    
                    # Calculate distance using Haversine formula
                    lat1, lon1 = math.radians(lat), math.radians(lon)
                    lat2, lon2 = math.radians(aircraft['lat']), math.radians(aircraft['lon'])
                    
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    
                    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                    c = 2 * math.asin(math.sqrt(a))
                    distance = 6371 * c  # Earth radius in km
                    
                    if distance < 150:  # Within 150km
                        nearby_flights.append({
                            'callsign': aircraft.get('flight', '').strip() or aircraft.get('r', 'Unknown'),
                            'hex': aircraft.get('hex', ''),
                            'altitude': aircraft.get('alt_baro', 0),
                            'speed': aircraft.get('gs', 0),
                            'distance': round(distance, 1)
                        })
                
                # Sort by distance and get nearest 2
                nearby_flights.sort(key=lambda x: x['distance'])
                nearest_two = nearby_flights[:2]
                
                return jsonify({'success': True, 'flights': nearest_two})
        except:
            pass
        
        # Fallback to empty list if API fails
        return jsonify({'success': True, 'flights': []})
        
    except Exception as e:
        logger.error(f"Error fetching nearest flights: {e}")
        return jsonify({'success': True, 'flights': []})


@app.route('/api/dashboard/timetable')
def get_timetable():
    """Get lecture timetable"""
    try:
        config = load_dashboard_config()
        timetable_config = config.get('timetable', {})
        
        if not timetable_config.get('enabled', True):
            return jsonify({'success': True, 'lectures': []})
        
        # Check if using external API
        if timetable_config.get('use_api', False):
            api_url = timetable_config.get('api_url', '').strip()
            api_key = timetable_config.get('api_key', '').strip()
            
            if not api_url:
                return jsonify({'success': False, 'message': 'Timetable API URL not configured'}), 400
            
            # Fetch from external API
            headers = {}
            if api_key:
                # Adjust header key based on your API's requirements
                headers['Authorization'] = f'Bearer {api_key}'
            
            response = requests.get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            api_data = response.json()
            
            # Assuming API returns lectures in format: {'lectures': [...]}
            # Adjust this based on your actual API response structure
            lectures = api_data.get('lectures', api_data if isinstance(api_data, list) else [])
            
            return jsonify({'success': True, 'lectures': lectures})
        
        # Use local/manual timetable
        # Get current day of week
        now = datetime.now()
        weekday = now.strftime('%A')
        
        # Filter lectures for today and get next ones
        lectures = timetable_config.get('lectures', [])
        current_time = now.hour * 60 + now.minute
        
        # Filter lectures that are today or coming soon
        upcoming_lectures = []
        for lecture in lectures:
            # Check if lecture has a day field, if not assume it's for all days
            if 'day' in lecture and lecture['day'] != weekday:
                continue
                
            time_parts = lecture['time'].split(':')
            lecture_time = int(time_parts[0]) * 60 + int(time_parts[1])
            
            # Show lectures that are within the next 2 hours or currently happening
            if lecture_time >= current_time - 30 and lecture_time <= current_time + 120:
                upcoming_lectures.append(lecture)
        
        # Sort by time
        upcoming_lectures.sort(key=lambda x: x['time'])
        
        # Limit to next 8 lectures
        upcoming_lectures = upcoming_lectures[:8]
        
        return jsonify({'success': True, 'lectures': upcoming_lectures})
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching timetable from API: {e}")
        return jsonify({'success': False, 'message': f'API request failed: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error fetching timetable: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/test/weather')
def test_weather_api():
    """Test weather API with provided key"""
    try:
        api_key = request.args.get('api_key', '').strip()
        lat = float(request.args.get('lat', 50.0))
        lon = float(request.args.get('lon', 8.0))
        
        if not api_key:
            return jsonify({'success': False, 'message': 'No API key provided'}), 400
        
        # Log for debugging
        logger.info(f"Testing weather API with key length: {len(api_key)}, lat: {lat}, lon: {lon}")
        
        # Try One Call API 3.0 first
        url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={api_key}&units=metric&exclude=minutely,hourly,daily,alerts"
        response = requests.get(url, timeout=10)
        
        logger.info(f"One Call API 3.0 response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            current = data.get('current', {})
            return jsonify({
                'success': True,
                'temp': round(current.get('temp', 0), 1),
                'description': current.get('weather', [{}])[0].get('description', 'N/A').capitalize(),
                'location': 'One Call API 3.0'
            })
        
        # If One Call API fails, try Current Weather Data API
        logger.info("Trying Current Weather Data API")
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
        response = requests.get(url, timeout=10)
        
        logger.info(f"Current Weather API response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                'success': True,
                'temp': round(data['main']['temp'], 1),
                'description': data['weather'][0]['description'].capitalize(),
                'location': data.get('name', 'Unknown')
            })
        elif response.status_code == 401:
            try:
                error_data = response.json()
                error_msg = error_data.get('message', 'Invalid API key')
                return jsonify({
                    'success': False, 
                    'message': f'API key error: {error_msg}. If you just created the key, wait 10-15 minutes.'
                }), 401
            except:
                return jsonify({
                    'success': False, 
                    'message': 'Invalid API key. Wait 10-15 minutes if just created.'
                }), 401
        elif response.status_code == 429:
            return jsonify({'success': False, 'message': 'API rate limit exceeded. Wait a minute and try again'}), 429
        else:
            try:
                error_data = response.json()
                error_msg = error_data.get('message', f'HTTP {response.status_code}')
            except:
                error_msg = f'HTTP {response.status_code}'
            return jsonify({'success': False, 'message': f'API Error: {error_msg}'}), response.status_code
            
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': 'Request timeout. Check your internet connection'}), 500
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': 'Connection error. Check your internet connection'}), 500
    except Exception as e:
        logger.error(f"Error testing weather API: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@app.route('/api/test/transport')
def test_transport_api():
    """Test transport API"""
    try:
        api_url = request.args.get('api_url', '')
        stop_id = request.args.get('stop_id', '')
        
        if not api_url:
            return jsonify({'success': False, 'message': 'No API URL provided'}), 400
        
        # This is a placeholder - will need to be customized based on actual API
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'API accessible'})
        else:
            return jsonify({'success': False, 'message': f'HTTP {response.status_code}'}), response.status_code
            
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': 'Request timeout'}), 500
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': 'Connection error'}), 500
    except Exception as e:
        logger.error(f"Error testing transport API: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/test/timetable')
def test_timetable_api():
    """Test timetable API"""
    try:
        api_url = request.args.get('api_url', '').strip()
        api_key = request.args.get('api_key', '').strip()
        
        if not api_url:
            return jsonify({'success': False, 'message': 'No API URL provided'}), 400
        
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Try to extract lecture count from response
            lectures = data.get('lectures', data if isinstance(data, list) else [])
            lectures_count = len(lectures) if isinstance(lectures, list) else 'unknown'
            return jsonify({
                'success': True, 
                'lectures_count': lectures_count
            })
        else:
            error_msg = 'Unknown error'
            try:
                error_data = response.json()
                error_msg = error_data.get('message', error_msg)
            except:
                error_msg = f'HTTP {response.status_code}'
            return jsonify({'success': False, 'message': f'API Error: {error_msg}'}), response.status_code
            
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': 'Request timeout'}), 500
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': 'Connection error'}), 500
    except Exception as e:
        logger.error(f"Error testing timetable API: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal error: {error}")
    return render_template('500.html'), 500


if __name__ == '__main__':
    # Development server
    app.run(host='0.0.0.0', port=5000, debug=True)
