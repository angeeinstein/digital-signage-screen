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
import math
import time
from pathlib import Path
import xml.etree.ElementTree as ET

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
FLIGHT_ROUTES_CACHE_FILE = BASE_DIR / 'flight_routes_cache.json'

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
    'airlabs': {
        'api_key': '',  # AirLabs API key
        'enabled': True,
        'api_provider': 'airplaneslive',  # 'airlabs' or 'airplaneslive'
        'radius_km': 75  # Radius for nearby flights in km
    },
    'opensky': {
        'client_id': '',  # OpenSky API Client ID (optional, increases rate limit)
        'client_secret': '',  # OpenSky API Client Secret
        'enabled': True,  # Enable automatic route lookup
        'cache_days': 7  # Days to cache route data before refresh
    },
    'transport': {
        'enabled': True,
        'api_type': 'trias',  # 'trias' for Austrian public transit
        'stop_id': '',  # TRIAS Stop ID (e.g., AT:47:1234:1:1)
        'stop_name': ''  # Display name of the stop
    },
    'timetable': {
        'enabled': True,
        'use_api': True,  # Always use API
        'api_url': '',  # URL for timetable API endpoint
        'api_key': '',  # API key if required
        'lectures': []  # Not used anymore - API only
    }
}


def get_aircraft_category(aircraft_type):
    """Map ICAO aircraft type code to icon filename (specific or category-based)"""
    if not aircraft_type:
        return 'adsb_icons/a0'
    
    aircraft_type = aircraft_type.upper().strip()
    
    # Specific aircraft type icons (exact matches from adsb_icons)
    specific_icons = {
        # Airbus
        'A320': 'a320', 'A19N': 'a320', 'A20N': 'a320', 'A21N': 'a320',
        'A318': 'a320', 'A319': 'a320', 'A321': 'a320',
        'A330': 'a330', 'A332': 'a330', 'A333': 'a330', 'A338': 'a330', 'A339': 'a330',
        'A340': 'a340', 'A342': 'a340', 'A343': 'a340', 'A345': 'a340', 'A346': 'a340',
        'A380': 'a380', 'A388': 'a380',
        # Boeing
        'B737': 'b737', 'B738': 'b737', 'B739': 'b737', 'B37M': 'b737', 'B38M': 'b737',
        'B731': 'b737', 'B732': 'b737', 'B733': 'b737', 'B734': 'b737', 'B735': 'b737',
        'B736': 'b737', 'B39M': 'b737', 'B3XM': 'b737',
        'B747': 'b747', 'B741': 'b747', 'B742': 'b747', 'B743': 'b747', 'B744': 'b747',
        'B748': 'b747', 'B74R': 'b747', 'B74S': 'b747',
        'B767': 'b767', 'B762': 'b767', 'B763': 'b767', 'B764': 'b767',
        'B777': 'b777', 'B772': 'b777', 'B773': 'b777', 'B77L': 'b777', 'B77W': 'b777',
        'B787': 'b787', 'B788': 'b787', 'B789': 'b787', 'B78X': 'b787',
        # Business jets
        'LJ24': 'learjet', 'LJ25': 'learjet', 'LJ31': 'learjet', 'LJ35': 'learjet',
        'LJ40': 'learjet', 'LJ45': 'learjet', 'LJ55': 'learjet', 'LJ60': 'learjet',
        'GLF4': 'glf5', 'GLF5': 'glf5', 'GLF6': 'glf5', 'GLEX': 'glf5',
        'G150': 'glf5', 'G200': 'glf5', 'G250': 'glf5', 'G280': 'glf5',
        'G450': 'glf5', 'G500': 'glf5', 'G550': 'glf5', 'G650': 'glf5',
        'FA7X': 'fa7x', 'FA8X': 'fa7x', 'FA10': 'fa7x', 'FA20': 'fa7x', 'FA50': 'fa7x',
        # Regional jets
        'CRJ1': 'crjx', 'CRJ2': 'crjx', 'CRJ7': 'crjx', 'CRJ9': 'crjx', 'CRJX': 'crjx',
        'E170': 'erj', 'E175': 'erj', 'E75L': 'erj', 'E75S': 'erj',
        'E190': 'e195', 'E195': 'e195', 'E19X': 'e195', 'E290': 'e195', 'E295': 'e195',
        # Turboprops
        'DH8A': 'dh8a', 'DH8B': 'dh8a', 'DH8C': 'dh8a', 'DH8D': 'dh8a',
        'DHC6': 'dh8a', 'DHC7': 'dh8a', 'DHC8': 'dh8a',
        'Q100': 'dh8a', 'Q200': 'dh8a', 'Q300': 'dh8a', 'Q400': 'dh8a',
        # Other
        'MD11': 'md11', 'DC10': 'md11',
        'F100': 'f100', 'F70': 'f100',
        'C130': 'c130',
        'C152': 'cessna', 'C162': 'cessna', 'C172': 'cessna', 'C182': 'cessna',
        'C206': 'cessna', 'C208': 'cessna', 'C210': 'cessna',
        # Fighters (generic military icons)
        'F5': 'f5', 'F11': 'f11', 'F15': 'f15',
    }
    
    if aircraft_type in specific_icons:
        return f"adsb_icons/{specific_icons[aircraft_type]}"
    
    # Category-based fallback icons
    # Helicopter
    if aircraft_type in ['H25B', 'H25C', 'H60', 'EC35', 'EC45', 'AS50', 'AS55', 'AS65', 'B06', 'B407', 'B412', 'B429', 'B505', 'R22', 'R44', 'R66', 'S76', 'EC30', 'EC55', 'EC75', 'H135', 'H145', 'H175', 'AW09', 'AW39', 'AW69', 'AW89', 'AW19', 'MD50', 'MD60', 'MD90']:
        return 'adsb_icons/c0'  # Helicopter category
    
    # Widebody jets (twin-aisle)
    if aircraft_type in ['A350', 'A359', 'A35K', 'A3ST', 'B752', 'B753', 'IL96', 'L101', 'AN124', 'AN225']:
        return 'adsb_icons/a6'  # Widebody category
    
    # Turboprop
    if aircraft_type in ['AT43', 'AT44', 'AT45', 'AT46', 'AT72', 'AT73', 'AT75', 'AT76', 'E120', 'SF34', 'SH33', 'SH36', 'IL18', 'AN12', 'AN24', 'AN26', 'P3', 'BE20', 'PC12', 'TBM7', 'TBM8', 'TBM9']:
        return 'adsb_icons/a1'  # Turboprop category
    
    # Business jets
    if aircraft_type in ['C25A', 'C25B', 'C25C', 'C25M', 'C500', 'C510', 'C525', 'C550', 'C551', 'C56X', 'C650', 'C680', 'C700', 'C750', 'CL30', 'CL35', 'CL60', 'E35L', 'E50P', 'E55P', 'E545', 'E550', 'F2TH', 'F900', 'H25A', 'PC24', 'PRM1', 'BE40', 'BE9L']:
        return 'adsb_icons/a2'  # Business jet category
    
    # Piston / General Aviation
    if aircraft_type in ['P28A', 'P28B', 'P28R', 'P28T', 'PA28', 'PA31', 'PA34', 'PA44', 'PA46', 'SR20', 'SR22', 'BE58', 'BE36', 'BE95', 'C340', 'C402', 'C414', 'C421', 'P68', 'DA40', 'DA42', 'DA62', 'PA18', 'PA22', 'ULAC']:
        return 'adsb_icons/cessna'  # GA category
    
    # Regional jets not matched above
    if aircraft_type in ['RJ70', 'RJ85', 'RJ1H']:
        return 'adsb_icons/a3'  # Regional jet category
    
    # Military jets
    if aircraft_type.startswith('F') or aircraft_type.startswith('MIG') or aircraft_type.startswith('SU'):
        return 'adsb_icons/b4'  # Military category
    
    # Narrowbody jets (default for commercial aircraft)
    if aircraft_type.startswith('A') or aircraft_type.startswith('B') or aircraft_type.startswith('E') or 'MD8' in aircraft_type or 'DC9' in aircraft_type or 'C919' in aircraft_type or 'SU95' in aircraft_type:
        return 'adsb_icons/a5'  # Narrowbody category
    
    # Default fallback
    return 'adsb_icons/a0'


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


def load_flight_routes_cache():
    """Load flight routes cache from file"""
    if FLIGHT_ROUTES_CACHE_FILE.exists():
        try:
            with open(FLIGHT_ROUTES_CACHE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading flight routes cache: {e}")
            return {}
    return {}


def save_flight_routes_cache(cache):
    """Save flight routes cache to file"""
    try:
        with open(FLIGHT_ROUTES_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving flight routes cache: {e}")
        return False


# TRIAS API Constants and Functions
TRIAS_API_URL = "http://ogdtrias.verbundlinie.at:8183/stv/trias"
TRIAS_NAMESPACES = {
    'trias': 'http://www.vdv.de/trias',
    'siri': 'http://www.siri.org.uk/siri'
}

def get_trias_timestamp():
    """Get current UTC timestamp in TRIAS format"""
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

def search_trias_stops(query, limit=20):
    """Search for transit stops using TRIAS API"""
    # Register namespace prefixes for proper output
    ET.register_namespace('', TRIAS_NAMESPACES['trias'])
    ET.register_namespace('siri', TRIAS_NAMESPACES['siri'])
    
    # Build XML using ElementTree for proper encoding
    trias = ET.Element('Trias', {
        'xmlns': TRIAS_NAMESPACES['trias'],
        'version': '1.2'
    })
    
    service_request = ET.SubElement(trias, 'ServiceRequest')
    
    timestamp = ET.SubElement(service_request, '{%s}RequestTimestamp' % TRIAS_NAMESPACES['siri'])
    timestamp.text = get_trias_timestamp()
    
    requestor_ref = ET.SubElement(service_request, '{%s}RequestorRef' % TRIAS_NAMESPACES['siri'])
    requestor_ref.text = 'digital_signage'
    
    request_payload = ET.SubElement(service_request, 'RequestPayload')
    loc_info_req = ET.SubElement(request_payload, 'LocationInformationRequest')
    
    initial_input = ET.SubElement(loc_info_req, 'InitialInput')
    location_name = ET.SubElement(initial_input, 'LocationName')
    text = ET.SubElement(location_name, 'Text')
    text.text = query
    language = ET.SubElement(location_name, 'Language')
    language.text = 'de'
    
    restrictions = ET.SubElement(loc_info_req, 'Restrictions')
    type_elem = ET.SubElement(restrictions, 'Type')
    type_elem.text = 'stop'
    num_results = ET.SubElement(restrictions, 'NumberOfResults')
    num_results.text = str(limit * 2)
    
    # Convert to string
    xml_string = ET.tostring(trias, encoding='utf-8', method='xml')
    xml_declaration = b'<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_request = (xml_declaration + xml_string).decode('utf-8')
    
    # Log the actual XML request being sent
    logger.info(f"TRIAS XML Request:\n{xml_request}")
    
    try:
        response = requests.post(
            TRIAS_API_URL,
            data=xml_request.encode('utf-8'),
            headers={'Content-Type': 'text/xml; charset=utf-8'},
            timeout=10
        )
        response.raise_for_status()
        
        # Log the raw response for debugging
        logger.info(f"TRIAS search for '{query}' - Response status: {response.status_code}")
        
        # Save response to file for debugging
        debug_file = f"/tmp/trias_response_{query.replace(' ', '_')}.xml"
        try:
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            logger.info(f"Response saved to {debug_file}")
        except:
            pass
        
        # Parse XML response
        root = ET.fromstring(response.content)
        stops_dict = {}  # Use dict to group by stop name
        
        # Count locations found
        locations = root.findall('.//trias:Location', TRIAS_NAMESPACES)
        logger.info(f"Found {len(locations)} Location elements in response")
        
        for location in root.findall('.//trias:Location', TRIAS_NAMESPACES):
            # Try to find StopPoint first, then StopPlace
            stop_point = location.find('trias:StopPoint', TRIAS_NAMESPACES)
            stop_place = location.find('trias:StopPlace', TRIAS_NAMESPACES)
            
            stop_ref = None
            stop_name = None
            
            if stop_point is not None:
                # This is a StopPoint (individual platform/stop)
                stop_point_ref = stop_point.find('trias:StopPointRef', TRIAS_NAMESPACES)
                if stop_point_ref is None:
                    continue
                stop_ref = stop_point_ref.text
                stop_point_name = stop_point.find('trias:StopPointName/trias:Text', TRIAS_NAMESPACES)
                stop_name = stop_point_name.text if stop_point_name is not None else None
                
            elif stop_place is not None:
                # This is a StopPlace (stop area/group of platforms)
                stop_place_ref = stop_place.find('trias:StopPlaceRef', TRIAS_NAMESPACES)
                if stop_place_ref is None:
                    continue
                stop_ref = stop_place_ref.text
                stop_place_name = stop_place.find('trias:StopPlaceName/trias:Text', TRIAS_NAMESPACES)
                stop_name = stop_place_name.text if stop_place_name is not None else None
            
            # Get coordinates
            geo_position = location.find('trias:GeoPosition', TRIAS_NAMESPACES)
            longitude = None
            latitude = None
            if geo_position is not None:
                lon_elem = geo_position.find('trias:Longitude', TRIAS_NAMESPACES)
                lat_elem = geo_position.find('trias:Latitude', TRIAS_NAMESPACES)
                longitude = float(lon_elem.text) if lon_elem is not None else None
                latitude = float(lat_elem.text) if lat_elem is not None else None
            
            if stop_ref is not None and stop_name is not None:
                logger.info(f"Found stop: {stop_name} (ID: {stop_ref})")
                # Group multiple platforms/variants of the same stop
                if stop_name in stops_dict:
                    # Add this stop_id to the list of IDs for this stop
                    if stop_ref not in stops_dict[stop_name]['stop_ids']:
                        stops_dict[stop_name]['stop_ids'].append(stop_ref)
                else:
                    stops_dict[stop_name] = {
                        'stop_id': stop_ref,  # Primary stop ID
                        'stop_ids': [stop_ref],  # All stop IDs (for multi-platform stops)
                        'stop_name': stop_name,
                        'longitude': longitude,
                        'latitude': latitude
                    }
        
        # Convert dict to list and limit results
        stops = []
        for stop_name, stop_data in list(stops_dict.items())[:limit]:
            # If multiple platforms, show count in name
            platform_count = len(stop_data['stop_ids'])
            if platform_count > 1:
                stop_data['stop_name'] = f"{stop_name} ({platform_count} platforms)"
            stops.append(stop_data)
        
        logger.info(f"Returning {len(stops)} stops after grouping")
        return stops
    except Exception as e:
        logger.error(f"Error searching TRIAS stops: {e}")
        return []

def get_trias_departures(stop_id, limit=10):
    """Get departures for a stop using TRIAS API"""
    xml_request = f'''<?xml version="1.0" encoding="UTF-8"?>
<Trias xmlns="http://www.vdv.de/trias" xmlns:siri="http://www.siri.org.uk/siri" version="1.2">
    <ServiceRequest>
        <siri:RequestTimestamp>{get_trias_timestamp()}</siri:RequestTimestamp>
        <siri:RequestorRef>digital_signage</siri:RequestorRef>
        <RequestPayload>
            <StopEventRequest>
                <Location>
                    <LocationRef>
                        <StopPointRef>{stop_id}</StopPointRef>
                    </LocationRef>
                </Location>
                <Params>
                    <NumberOfResults>{limit}</NumberOfResults>
                    <StopEventType>departure</StopEventType>
                    <IncludeRealtimeData>true</IncludeRealtimeData>
                </Params>
                <DepartureWindow>60</DepartureWindow>
            </StopEventRequest>
        </RequestPayload>
    </ServiceRequest>
</Trias>'''
    
    try:
        response = requests.post(
            TRIAS_API_URL,
            data=xml_request.encode('utf-8'),
            headers={'Content-Type': 'text/xml'},
            timeout=10
        )
        response.raise_for_status()
        
        # Parse XML response
        root = ET.fromstring(response.content)
        departures = []
        
        for stop_event in root.findall('.//trias:StopEvent', TRIAS_NAMESPACES):
            line_elem = stop_event.find('.//trias:PublishedLineName/trias:Text', TRIAS_NAMESPACES)
            dest_elem = stop_event.find('.//trias:DestinationText/trias:Text', TRIAS_NAMESPACES)
            timetabled_elem = stop_event.find('.//trias:TimetabledTime', TRIAS_NAMESPACES)
            estimated_elem = stop_event.find('.//trias:EstimatedTime', TRIAS_NAMESPACES)
            
            # Use estimated time if available, otherwise timetabled
            departure_time = estimated_elem.text if estimated_elem is not None else (timetabled_elem.text if timetabled_elem is not None else None)
            is_realtime = estimated_elem is not None
            
            if departure_time:
                # Parse ISO timestamp and format as HH:MM
                try:
                    dt = datetime.fromisoformat(departure_time.replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M')
                except:
                    time_str = departure_time
                
                departures.append({
                    'line': line_elem.text if line_elem is not None else 'N/A',
                    'direction': dest_elem.text if dest_elem is not None else 'N/A',
                    'time': time_str,
                    'is_realtime': is_realtime
                })
        
        return departures
    except Exception as e:
        logger.error(f"Error getting TRIAS departures: {e}")
        return []


def save_flight_routes_cache(cache):
    """Save flight routes cache to file"""
    try:
        with open(FLIGHT_ROUTES_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving flight routes cache: {e}")


def get_route_from_cache(callsign, cache, cache_days=7):
    """Get departure and arrival airports from cache for a callsign"""
    if not callsign:
        return '', '', False
    
    # Try exact match first
    if callsign in cache:
        route = cache[callsign]
        # Check if cache is still valid
        if 'last_seen' in route:
            try:
                last_seen = datetime.fromisoformat(route['last_seen'])
                age_days = (datetime.now() - last_seen).days
                if age_days < cache_days:
                    return route.get('from', ''), route.get('to', ''), True
                else:
                    return route.get('from', ''), route.get('to', ''), False  # Expired
            except:
                pass
        return route.get('from', ''), route.get('to', ''), True
    
    # Try without flight number (e.g., "UAL123" -> "UAL")
    airline_code = ''.join(filter(str.isalpha, callsign[:3]))
    if airline_code and airline_code in cache:
        route = cache[airline_code]
        if 'last_seen' in route:
            try:
                last_seen = datetime.fromisoformat(route['last_seen'])
                age_days = (datetime.now() - last_seen).days
                if age_days < cache_days:
                    return route.get('from', ''), route.get('to', ''), True
            except:
                pass
        return route.get('from', ''), route.get('to', ''), True
    
    return '', '', False


def update_route_cache(callsign, from_airport, to_airport, cache, not_found=False):
    """Update the route cache with new information"""
    if not callsign:
        return
    
    cache[callsign] = {
        'from': from_airport or '',
        'to': to_airport or '',
        'last_seen': datetime.now().isoformat(),
        'not_found': not_found  # Mark if route lookup failed (404)
    }
    save_flight_routes_cache(cache)


# OAuth2 token cache
_opensky_token_cache = {'token': None, 'expires_at': 0}

def get_opensky_token(client_id, client_secret):
    """Get OAuth2 access token for OpenSky API (cached for 30 minutes)"""
    global _opensky_token_cache
    
    # Check if cached token is still valid
    if _opensky_token_cache['token'] and time.time() < _opensky_token_cache['expires_at']:
        return _opensky_token_cache['token']
    
    try:
        token_url = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
        data = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret
        }
        
        response = requests.post(token_url, data=data, timeout=10)
        if response.status_code == 200:
            token_data = response.json()
            token = token_data.get('access_token')
            expires_in = token_data.get('expires_in', 1800)  # Default 30 minutes
            
            # Cache token (refresh 1 minute before expiry)
            _opensky_token_cache['token'] = token
            _opensky_token_cache['expires_at'] = time.time() + expires_in - 60
            
            logger.info("OpenSky: OAuth2 token obtained successfully")
            return token
        else:
            logger.error(f"OpenSky: Failed to get OAuth2 token: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"OpenSky: Error getting OAuth2 token: {e}")
        return None


def fetch_route_from_opensky(icao24, config):
    """Fetch flight route from OpenSky Network API"""
    try:
        opensky_config = config.get('opensky', {})
        if not opensky_config.get('enabled', True):
            return None, None
        
        client_id = opensky_config.get('client_id', '').strip()
        client_secret = opensky_config.get('client_secret', '').strip()
        
        # Query recent flights for this aircraft (1 day window)
        # OpenSky's flight database has a 2-day partition limit
        # We query 2-3 days ago to ensure data is available (batch processed)
        end_time = int(time.time()) - (2 * 24 * 3600)  # 2 days ago
        begin_time = end_time - (1 * 24 * 3600)  # 1 day window (total: 2-3 days ago)
        
        url = f"https://opensky-network.org/api/flights/aircraft?icao24={icao24.lower()}&begin={begin_time}&end={end_time}"
        
        # Prepare headers
        headers = {}
        if client_id and client_secret:
            # Use OAuth2 token for authenticated requests
            token = get_opensky_token(client_id, client_secret)
            if token:
                headers['Authorization'] = f'Bearer {token}'
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            flights = response.json()
            if flights and len(flights) > 0:
                # Get the most recent flight
                latest_flight = flights[-1]
                departure = latest_flight.get('estDepartureAirport', '')
                arrival = latest_flight.get('estArrivalAirport', '')
                
                if departure or arrival:
                    logger.info(f"OpenSky: Found route for {icao24}: {departure} → {arrival}")
                    return departure, arrival
            else:
                logger.debug(f"OpenSky: No flights found for {icao24} in database")
        elif response.status_code == 401:
            logger.warning("OpenSky API: Authentication failed. Check credentials.")
        elif response.status_code == 404:
            logger.debug(f"OpenSky: No data found for {icao24} (404)")
        elif response.status_code == 429:
            logger.warning("OpenSky API: Rate limit exceeded. Using cache only.")
        elif response.status_code == 400:
            # Log the actual error message from OpenSky
            try:
                error_data = response.json()
                logger.warning(f"OpenSky API 400 error for {icao24}: {error_data}")
            except:
                logger.warning(f"OpenSky API 400 error for {icao24}: {response.text}")
        else:
            logger.warning(f"OpenSky API returned {response.status_code} for {icao24}")
        
        return None, None
        
    except Exception as e:
        logger.error(f"Error fetching route from OpenSky for {icao24}: {e}")
        return None, None


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
        
        stop_id = transport_config.get('stop_id', '')
        if not stop_id:
            return jsonify({'success': True, 'departures': []})
        
        # Get departures from TRIAS API
        departures = get_trias_departures(stop_id, limit=5)
        
        return jsonify({'success': True, 'departures': departures})
        
    except Exception as e:
        logger.error(f"Error fetching transport: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/dashboard/nearest-flights')
def get_nearest_flights():
    """Get nearest flights from selected API provider"""
    try:
        config = load_dashboard_config()
        airlabs_config = config.get('airlabs', {})
        
        if not airlabs_config.get('enabled', True):
            return jsonify({'success': True, 'flights': []})
        
        api_provider = airlabs_config.get('api_provider', 'airplaneslive')
        
        if api_provider == 'airlabs':
            return get_flights_airlabs(config, airlabs_config)
        elif api_provider == 'airplaneslive':
            return get_flights_airplaneslive(config, airlabs_config)
        elif api_provider == 'opensky':
            return get_flights_opensky(config, airlabs_config)
        else:
            return jsonify({'success': False, 'message': 'Unknown API provider'}), 400
            
    except Exception as e:
        logger.error(f"Error fetching nearest flights: {e}")
        return jsonify({'success': False, 'flights': [], 'message': str(e)})


def get_flights_airplaneslive(config, flight_config):
    """Get flights from airplanes.live API with cached route enrichment"""
    try:
        # Load route cache
        route_cache = load_flight_routes_cache()
        
        # Get location
        lat = config.get('location', {}).get('lat', 50.0)
        lon = config.get('location', {}).get('lon', 8.0)
        radius_km = flight_config.get('radius_km', 75)
        
        # Convert km to nautical miles (1 km = 0.539957 nm)
        radius_nm = int(radius_km * 0.539957)
        
        # Call airplanes.live API
        url = f"http://api.airplanes.live/v2/point/{lat}/{lon}/{radius_nm}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        aircraft_list = data.get('ac', [])
        
        # Format flights
        nearby_flights = []
        for aircraft in aircraft_list:
            if not aircraft.get('lat') or not aircraft.get('lon'):
                continue
            
            # Get callsign and clean it
            callsign = (aircraft.get('flight') or '').strip()
            if not callsign:
                callsign = aircraft.get('r', 'Unknown')
            
            # Try to extract airline from callsign (first 2-3 letters)
            airline_code = ''
            airline_name = ''
            if len(callsign) >= 2:
                # Try 3-letter code first
                if len(callsign) >= 3 and callsign[:3].isalpha():
                    airline_code = callsign[:3]
                elif callsign[:2].isalpha():
                    airline_code = callsign[:2]
                
                # Map common airline codes
                airline_names = {
                    'AAL': 'American', 'DAL': 'Delta', 'UAL': 'United', 'SWA': 'Southwest',
                    'BAW': 'British Airways', 'DLH': 'Lufthansa', 'AFR': 'Air France', 'KLM': 'KLM',
                    'UAE': 'Emirates', 'QTR': 'Qatar', 'SIA': 'Singapore',
                    'SWR': 'Swiss', 'AUA': 'Austrian', 'BEL': 'Brussels', 'TAP': 'TAP',
                    'IBE': 'Iberia', 'AZA': 'ITA', 'SAS': 'SAS', 'FIN': 'Finnair',
                    'RYR': 'Ryanair', 'EZY': 'easyJet', 'WZZ': 'Wizz Air', 'VLG': 'Vueling',
                    'IGO': 'IndiGo', 'QFA': 'Qantas', 'ANZ': 'Air NZ', 'ACA': 'Air Canada',
                    'ANA': 'ANA', 'JAL': 'JAL', 'CPA': 'Cathay', 'THY': 'Turkish',
                    'ETH': 'Ethiopian', 'SAA': 'South African', 'ETD': 'Etihad', 'SVA': 'Saudia'
                }
                airline_name = airline_names.get(airline_code, '')
            
            # Try to get route from cache
            opensky_config = config.get('opensky', {})
            cache_days = opensky_config.get('cache_days', 7)
            from_airport, to_airport, is_valid = get_route_from_cache(callsign, route_cache, cache_days)
            
            # Check if this aircraft was previously marked as not found
            skip_lookup = False
            if callsign in route_cache:
                cached = route_cache[callsign]
                if cached.get('not_found', False):
                    # Skip lookup if not_found was set within last 24 hours
                    try:
                        last_seen = datetime.fromisoformat(cached['last_seen'])
                        hours_since = (datetime.now() - last_seen).total_seconds() / 3600
                        if hours_since < 24:
                            skip_lookup = True
                            logger.debug(f"Skipping OpenSky lookup for {callsign} (not found {hours_since:.1f}h ago)")
                    except:
                        pass
            
            # If not in cache or expired, try to fetch from OpenSky
            icao24 = aircraft.get('hex', '').lower()
            if not skip_lookup and ((not from_airport and not to_airport) or not is_valid):
                if icao24 and opensky_config.get('enabled', True):
                    logger.info(f"Fetching route for {callsign} (ICAO24: {icao24}) from OpenSky...")
                    # Fetch from OpenSky in background (don't block)
                    opensky_from, opensky_to = fetch_route_from_opensky(icao24, config)
                    if opensky_from or opensky_to:
                        from_airport = opensky_from or from_airport
                        to_airport = opensky_to or to_airport
                        logger.info(f"Found route for {callsign}: {from_airport} → {to_airport}")
                        # Update cache with successful result
                        update_route_cache(callsign, from_airport, to_airport, route_cache, not_found=False)
                    else:
                        logger.info(f"No route found for {callsign} ({icao24}) in OpenSky database")
                        # Cache the negative result to avoid retrying
                        update_route_cache(callsign, '', '', route_cache, not_found=True)
                else:
                    logger.debug(f"OpenSky lookup disabled or no ICAO24 for {callsign}")
            
            aircraft_type_code = aircraft.get('t', '')
            nearby_flights.append({
                'callsign': callsign,
                'flight_number': callsign,
                'airline': airline_code,
                'airline_name': airline_name,
                'aircraft_type': aircraft_type_code,
                'aircraft_category': get_aircraft_category(aircraft_type_code),
                'hex': aircraft.get('hex', ''),
                'altitude': aircraft.get('alt_baro', 0) or 0,
                'speed': aircraft.get('gs', 0) or 0,
                'distance': round(aircraft.get('dst', 0), 1),  # Already in km
                'from': from_airport,  # From cache if available
                'to': to_airport  # From cache if available
            })
        
        # Sort by distance and get nearest 4
        nearby_flights.sort(key=lambda x: x['distance'])
        nearest = nearby_flights[:4]
        
        return jsonify({'success': True, 'flights': nearest})
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching flights from airplanes.live: {e}")
        return jsonify({'success': False, 'flights': [], 'message': str(e)})
    except Exception as e:
        logger.error(f"Error processing airplanes.live data: {e}")
        return jsonify({'success': False, 'flights': [], 'message': str(e)})


def get_flights_opensky(config, flight_config):
    """Get flights from OpenSky Network API (free, no authentication)"""
    try:
        # Get location
        lat = config.get('location', {}).get('lat', 50.0)
        lon = config.get('location', {}).get('lon', 8.0)
        radius_km = flight_config.get('radius_km', 75)
        
        # Calculate bounding box (approximately)
        # 1 degree latitude ≈ 111 km
        lat_offset = radius_km / 111.0
        # 1 degree longitude varies by latitude
        lon_offset = radius_km / (111.0 * math.cos(math.radians(lat)))
        
        lamin = lat - lat_offset
        lamax = lat + lat_offset
        lomin = lon - lon_offset
        lomax = lon + lon_offset
        
        # Call OpenSky API
        url = f"https://opensky-network.org/api/states/all?lamin={lamin}&lomin={lomin}&lamax={lamax}&lomax={lomax}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        states = data.get('states', [])
        
        if not states:
            return jsonify({'success': True, 'flights': []})
        
        # Format flights
        nearby_flights = []
        for state in states:
            # State vector format: [icao24, callsign, origin_country, time_position, last_contact,
            #                       longitude, latitude, baro_altitude, on_ground, velocity,
            #                       true_track, vertical_rate, sensors, geo_altitude, squawk, spi, position_source, category]
            
            if len(state) < 8 or not state[5] or not state[6]:  # Need lon/lat
                continue
            
            if state[8]:  # Skip if on ground
                continue
            
            icao24 = state[0] or ''
            callsign = (state[1] or '').strip()
            origin_country = state[2] or ''
            lon_aircraft = state[5]
            lat_aircraft = state[6]
            altitude_m = state[7]  # meters
            velocity_ms = state[9]  # m/s
            
            # Calculate distance using Haversine formula
            lat1, lon1 = math.radians(lat), math.radians(lon)
            lat2, lon2 = math.radians(lat_aircraft), math.radians(lon_aircraft)
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            distance_km = 6371 * c
            
            # Convert units
            altitude_ft = int(altitude_m * 3.28084) if altitude_m else 0  # meters to feet
            speed_kts = int(velocity_ms * 1.94384) if velocity_ms else 0  # m/s to knots
            
            # Extract airline from callsign
            airline_code = ''
            airline_name = ''
            if callsign and len(callsign) >= 2:
                if len(callsign) >= 3 and callsign[:3].isalpha():
                    airline_code = callsign[:3]
                elif callsign[:2].isalpha():
                    airline_code = callsign[:2]
                
                # Map common airline codes (3-letter ICAO)
                airline_names = {
                    'AAL': 'American', 'DAL': 'Delta', 'UAL': 'United', 'SWA': 'Southwest',
                    'BAW': 'British Airways', 'DLH': 'Lufthansa', 'AFR': 'Air France', 'KLM': 'KLM',
                    'UAE': 'Emirates', 'QTR': 'Qatar', 'SIA': 'Singapore',
                    'SWR': 'Swiss', 'AUA': 'Austrian', 'BEL': 'Brussels', 'TAP': 'TAP',
                    'IBE': 'Iberia', 'AZA': 'ITA', 'SAS': 'SAS', 'FIN': 'Finnair',
                    'RYR': 'Ryanair', 'EZY': 'easyJet', 'WZZ': 'Wizz Air', 'VLG': 'Vueling',
                    'IGO': 'IndiGo', 'QFA': 'Qantas', 'ANZ': 'Air NZ', 'ACA': 'Air Canada',
                    'ANA': 'ANA', 'JAL': 'JAL', 'CPA': 'Cathay', 'THY': 'Turkish',
                    'ETH': 'Ethiopian', 'SAA': 'South African', 'ETD': 'Etihad', 'SVA': 'Saudia'
                }
                airline_name = airline_names.get(airline_code, '')
            
            # Get aircraft category
            category = ''
            if len(state) > 17 and state[17]:
                cat_num = state[17]
                categories = {
                    2: 'Light', 3: 'Small', 4: 'Large', 5: 'Heavy', 6: 'Super Heavy',
                    7: 'High Perf', 8: 'Helicopter', 9: 'Glider', 14: 'UAV'
                }
                category = categories.get(cat_num, '')
            
            nearby_flights.append({
                'callsign': callsign if callsign else icao24.upper(),
                'flight_number': callsign if callsign else icao24.upper(),
                'airline': airline_code,
                'airline_name': airline_name,
                'aircraft_type': category,  # Use category since we don't have type
                'hex': icao24,
                'altitude': altitude_ft,
                'speed': speed_kts,
                'distance': round(distance_km, 1),
                'from': origin_country,  # Use origin country instead of departure airport
                'to': ''  # Not available
            })
        
        # Sort by distance and get nearest 5
        nearby_flights.sort(key=lambda x: x['distance'])
        nearest = nearby_flights[:5]
        
        return jsonify({'success': True, 'flights': nearest})
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching flights from OpenSky: {e}")
        return jsonify({'success': False, 'flights': [], 'message': str(e)})
    except Exception as e:
        logger.error(f"Error processing OpenSky data: {e}")
        return jsonify({'success': False, 'flights': [], 'message': str(e)})


def get_flights_airlabs(config, flight_config):
    """Get flights from AirLabs API"""
    try:
        api_key = flight_config.get('api_key', '').strip()
        if not api_key:
            return jsonify({'success': True, 'flights': [], 'message': 'AirLabs API key not configured'})
        
        # Get location
        lat = config.get('location', {}).get('lat', 50.0)
        lon = config.get('location', {}).get('lon', 8.0)
        radius_km = flight_config.get('radius_km', 75)
        
        # Calculate bounding box (approximately)
        # 1 degree latitude ≈ 111 km
        # 1 degree longitude ≈ 111 km * cos(latitude)
        import math
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))
        
        lat_min = lat - lat_delta
        lat_max = lat + lat_delta
        lon_min = lon - lon_delta
        lon_max = lon + lon_delta
        
        # Airline code to name mapping
        airline_names = {
            'AA': 'American Airlines', 'DL': 'Delta', 'UA': 'United', 'WN': 'Southwest',
            'BA': 'British Airways', 'LH': 'Lufthansa', 'AF': 'Air France', 'KL': 'KLM',
            'EK': 'Emirates', 'QR': 'Qatar Airways', 'SQ': 'Singapore Airlines',
            'LX': 'Swiss', 'OS': 'Austrian', 'SN': 'Brussels Airlines', 'TP': 'TAP Portugal',
            'IB': 'Iberia', 'AZ': 'ITA Airways', 'SK': 'SAS', 'AY': 'Finnair',
            'FR': 'Ryanair', 'U2': 'easyJet', 'W6': 'Wizz Air', 'VY': 'Vueling',
            '6E': 'IndiGo', 'QF': 'Qantas', 'NZ': 'Air New Zealand', 'AC': 'Air Canada',
            'NH': 'ANA', 'JL': 'JAL', 'CX': 'Cathay Pacific', 'TK': 'Turkish Airlines',
            'ET': 'Ethiopian', 'SA': 'South African', 'EY': 'Etihad', 'SV': 'Saudia',
            'AI': 'Air India', 'TG': 'Thai Airways', 'MH': 'Malaysia Airlines',
            'GA': 'Garuda', 'PR': 'Philippine Airlines', 'VN': 'Vietnam Airlines',
            'CA': 'Air China', 'MU': 'China Eastern', 'CZ': 'China Southern',
            'AM': 'Aeromexico', 'CM': 'Copa Airlines', 'LA': 'LATAM', 'AR': 'Aerolineas',
            'AV': 'Avianca', 'G3': 'Gol', 'JJ': 'LATAM Brasil'
        }
        
        # Call AirLabs API
        bbox = f"{lat_min:.2f},{lon_min:.2f},{lat_max:.2f},{lon_max:.2f}"
        url = f"https://airlabs.co/api/v9/flights?api_key={api_key}&bbox={bbox}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('error'):
            logger.error(f"AirLabs API error: {data.get('error', {}).get('message', 'Unknown error')}")
            return jsonify({'success': False, 'flights': [], 'message': data.get('error', {}).get('message', 'API error')})
        
        flights_data = data.get('response', [])
        
        # Calculate distance and format flights
        nearby_flights = []
        for flight in flights_data:
            if not flight.get('lat') or not flight.get('lng'):
                continue
            
            # Calculate distance using Haversine formula
            lat1, lon1 = math.radians(lat), math.radians(lon)
            lat2, lon2 = math.radians(flight['lat']), math.radians(flight['lng'])
            
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            distance = 6371 * c  # Earth radius in km
            
            airline_code = flight.get('airline_iata', '')
            airline_name = airline_names.get(airline_code, airline_code)
            
            nearby_flights.append({
                'callsign': flight.get('flight_icao') or flight.get('flight_iata') or flight.get('reg_number', 'Unknown'),
                'flight_number': flight.get('flight_iata', ''),
                'airline': airline_code,
                'airline_name': airline_name,
                'aircraft_type': flight.get('aircraft_icao', ''),
                'hex': flight.get('hex', ''),
                'altitude': int(flight.get('alt', 0) * 3.28084) if flight.get('alt') else 0,  # Convert m to ft
                'speed': int(flight.get('speed', 0) * 1.94384) if flight.get('speed') else 0,  # Convert km/h to kts
                'distance': round(distance, 1),
                'from': flight.get('dep_iata', ''),
                'to': flight.get('arr_iata', '')
            })
        
        # Sort by distance and get nearest 5
        nearby_flights.sort(key=lambda x: x['distance'])
        nearest = nearby_flights[:5]
        
        return jsonify({'success': True, 'flights': nearest})
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching flights from AirLabs: {e}")
        return jsonify({'success': False, 'flights': [], 'message': str(e)})
    except Exception as e:
        logger.error(f"Error fetching nearest flights: {e}")
        return jsonify({'success': False, 'flights': [], 'message': str(e)})


@app.route('/api/dashboard/timetable')
def get_timetable():
    """Get lecture timetable from external API"""
    try:
        config = load_dashboard_config()
        timetable_config = config.get('timetable', {})
        
        if not timetable_config.get('enabled', True):
            return jsonify({'success': True, 'lectures': []})
        
        api_url = timetable_config.get('api_url', '').strip()
        api_key = timetable_config.get('api_key', '').strip()
        
        if not api_url:
            return jsonify({'success': True, 'lectures': [], 'message': 'No API configured yet'}), 200
        
        # Fetch from external API
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        api_data = response.json()
        
        # Assuming API returns lectures in format: {'lectures': [...]}
        # Adjust this based on your actual API response structure
        lectures = api_data.get('lectures', api_data if isinstance(api_data, list) else [])
        
        return jsonify({'success': True, 'lectures': lectures})
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching timetable from API: {e}")
        return jsonify({'success': False, 'lectures': [], 'message': f'API error: {str(e)}'}), 200
    except Exception as e:
        logger.error(f"Error fetching timetable: {e}")
        return jsonify({'success': False, 'lectures': [], 'message': str(e)}), 200


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
    """Test TRIAS transport API"""
    try:
        stop_id = request.args.get('stop_id', '')
        
        if not stop_id:
            return jsonify({'success': False, 'message': 'No stop ID provided'}), 400
        
        # Test by getting departures
        departures = get_trias_departures(stop_id, limit=3)
        
        if departures:
            return jsonify({
                'success': True,
                'message': f'Found {len(departures)} departures',
                'departures': departures
            })
        else:
            return jsonify({'success': False, 'message': 'No departures found or API error'}), 500
            
    except Exception as e:
        logger.error(f"Error testing transport API: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/transport/search-stops')
def search_stops():
    """Search for transit stops by name"""
    try:
        query = request.args.get('query', '')
        
        if not query or len(query) < 2:
            return jsonify({'success': False, 'message': 'Query too short'}), 400
        
        stops = search_trias_stops(query, limit=15)
        
        return jsonify({'success': True, 'stops': stops})
        
    except Exception as e:
        logger.error(f"Error searching stops: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/test/opensky')
def test_opensky_api():
    """Test OpenSky API with provided credentials or anonymous"""
    try:
        client_id = request.args.get('client_id', '').strip()
        client_secret = request.args.get('client_secret', '').strip()
        
        # Test with a known aircraft (Lufthansa A380 example)
        test_icao24 = '3c6444'  # Lufthansa D-AIMC (A380)
        # OpenSky flights data is batch processed - query 2-3 days ago (1 day window)
        end_time = int(time.time()) - (2 * 24 * 3600)  # 2 days ago
        begin_time = end_time - (1 * 24 * 3600)  # 1 day window
        
        url = f"https://opensky-network.org/api/flights/aircraft?icao24={test_icao24}&begin={begin_time}&end={end_time}"
        
        headers = {}
        auth_type = "anonymous"
        
        if client_id and client_secret:
            # Try OAuth2 authentication
            token = get_opensky_token(client_id, client_secret)
            if not token:
                return jsonify({
                    'success': False, 
                    'message': 'Failed to obtain OAuth2 token. Check your Client ID and Client Secret.'
                }), 401
            
            headers['Authorization'] = f'Bearer {token}'
            auth_type = "authenticated"
        
        response = requests.get(url, headers=headers, timeout=10)
        
        logger.info(f"OpenSky test API - Status: {response.status_code}, URL: {url}")
        if response.status_code != 200:
            logger.error(f"OpenSky test API error response: {response.text}")
        
        if response.status_code == 200:
            flights = response.json()
            flight_count = len(flights) if flights else 0
            
            # Get rate limit info from headers
            credits_remaining = response.headers.get('X-Rate-Limit-Remaining', 'Unknown')
            
            if flight_count > 0:
                sample_flight = flights[0]
                departure = sample_flight.get('estDepartureAirport', 'N/A')
                arrival = sample_flight.get('estArrivalAirport', 'N/A')
                
                return jsonify({
                    'success': True,
                    'message': f'Connected successfully! Found {flight_count} recent flight(s) for test aircraft.',
                    'credits': f'{credits_remaining} remaining',
                    'auth_type': auth_type,
                    'sample_route': f'{departure} → {arrival}'
                })
            else:
                return jsonify({
                    'success': True,
                    'message': f'API connected ({auth_type}) but no recent flights found for test aircraft. Your credentials are valid!',
                    'credits': f'{credits_remaining} remaining',
                    'auth_type': auth_type
                })
        
        elif response.status_code == 401:
            return jsonify({
                'success': False,
                'message': 'Authentication failed. Check your Client ID and Client Secret, or try anonymous access (leave empty).'
            }), 401
        
        elif response.status_code == 429:
            return jsonify({
                'success': False,
                'message': 'Rate limit exceeded. Anonymous users: 400 credits/day. With credentials: 4,000-8,000/day.'
            }), 429
        
        elif response.status_code == 400:
            try:
                error_data = response.json()
                error_msg = error_data.get('message', str(error_data))
            except:
                error_msg = response.text
            return jsonify({
                'success': False,
                'message': f'API returned 400 Bad Request: {error_msg}. This usually means the time range is invalid (OpenSky requires begin < end, and end must be at least 1 day ago).'
            }), 400
        
        else:
            return jsonify({
                'success': False,
                'message': f'API returned status {response.status_code}. Check OpenSky Network status.'
            }), response.status_code
            
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': 'Request timeout. Check your internet connection.'}), 500
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': 'Connection error. Check your internet connection.'}), 500
    except Exception as e:
        logger.error(f"Error testing OpenSky API: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@app.route('/api/flight-routes/add', methods=['POST'])
def add_flight_route():
    """Manually add a flight route to the cache"""
    try:
        data = request.get_json()
        callsign = data.get('callsign', '').strip().upper()
        from_airport = data.get('from', '').strip().upper()
        to_airport = data.get('to', '').strip().upper()
        
        if not callsign:
            return jsonify({'success': False, 'message': 'Callsign is required'}), 400
        
        if not from_airport and not to_airport:
            return jsonify({'success': False, 'message': 'At least one airport (from or to) is required'}), 400
        
        # Load cache
        cache = load_flight_routes_cache()
        
        # Update cache
        update_route_cache(callsign, from_airport, to_airport, cache)
        
        return jsonify({
            'success': True, 
            'message': f'Route added: {callsign} {from_airport} → {to_airport}',
            'cache_size': len(cache)
        })
        
    except Exception as e:
        logger.error(f"Error adding flight route: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/flight-routes/list')
def list_flight_routes():
    """Get all cached flight routes"""
    try:
        cache = load_flight_routes_cache()
        return jsonify({
            'success': True,
            'routes': cache,
            'count': len(cache)
        })
    except Exception as e:
        logger.error(f"Error listing flight routes: {e}")
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


@app.route('/api/test/airlabs')
def test_airlabs_api():
    """Test AirLabs API"""
    try:
        api_key = request.args.get('api_key', '').strip()
        lat = float(request.args.get('lat', 50.0))
        lon = float(request.args.get('lon', 8.0))
        
        if not api_key:
            return jsonify({'success': False, 'message': 'No API key provided'}), 400
        
        # Calculate small bounding box for testing
        import math
        radius_km = 50  # Small test radius
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))
        
        lat_min = lat - lat_delta
        lat_max = lat + lat_delta
        lon_min = lon - lon_delta
        lon_max = lon + lon_delta
        
        bbox = f"{lat_min:.2f},{lon_min:.2f},{lat_max:.2f},{lon_max:.2f}"
        url = f"https://airlabs.co/api/v9/flights?api_key={api_key}&bbox={bbox}"
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('error'):
                return jsonify({
                    'success': False, 
                    'message': data.get('error', {}).get('message', 'API error')
                }), 400
            
            flights = data.get('response', [])
            return jsonify({
                'success': True,
                'flights_count': len(flights)
            })
        else:
            return jsonify({'success': False, 'message': f'HTTP {response.status_code}'}), response.status_code
            
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': 'Request timeout'}), 500
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': 'Connection error'}), 500
    except Exception as e:
        logger.error(f"Error testing AirLabs API: {e}")
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
