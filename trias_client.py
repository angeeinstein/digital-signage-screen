"""TRIAS API Client - handles all communication with the TRIAS public transit API"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from config import TRIAS_API_URL, DEFAULT_REQUESTOR_REF, NAMESPACES, STOP_CACHE_FILE, STOP_CACHE_TTL_HOURS, STOP_CACHE_ENABLED
import json
import os


class TriasClient:
    """Client for interacting with the TRIAS API"""
    
    def __init__(self, requestor_ref: str = DEFAULT_REQUESTOR_REF):
        self.api_url = TRIAS_API_URL
        self.requestor_ref = requestor_ref
        self.namespaces = NAMESPACES
        self.stop_cache = None
        self.cache_timestamp = None
        
        # Load cache on initialization
        if STOP_CACHE_ENABLED:
            self._load_stop_cache()
    
        # Load cache on initialization
        if STOP_CACHE_ENABLED:
            self._load_stop_cache()
    
    def _load_stop_cache(self):
        """Load stop cache from file if it exists and is fresh"""
        if os.path.exists(STOP_CACHE_FILE):
            try:
                with open(STOP_CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cache_time = datetime.fromisoformat(data['timestamp'])
                    
                    # Check if cache is still valid
                    if datetime.utcnow() - cache_time < timedelta(hours=STOP_CACHE_TTL_HOURS):
                        self.stop_cache = data['stops']
                        self.cache_timestamp = cache_time
                        print(f"[CACHE] Loaded {len(self.stop_cache)} stops from cache (age: {(datetime.utcnow() - cache_time).total_seconds() / 3600:.1f}h)")
                        return
                    else:
                        print(f"[CACHE] Cache expired")
            except Exception as e:
                print(f"[CACHE] Failed to load cache: {e}")
        
        # No valid cache - start with empty cache and let it build gradually
        print("[CACHE] No valid cache found, will build cache from searches")
        self.stop_cache = []
        self.cache_timestamp = datetime.utcnow()
    
    def _save_stop_cache(self):
        """Save stop cache to file"""
        if self.stop_cache:
            try:
                data = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'stops': self.stop_cache
                }
                with open(STOP_CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
                print(f"[CACHE] Saved {len(self.stop_cache)} stops to cache")
            except Exception as e:
                print(f"[CACHE] Failed to save cache: {e}")
    
    def _add_to_cache(self, stops: List[Dict[str, Any]]):
        """Add new stops to cache (avoids duplicates)"""
        if not STOP_CACHE_ENABLED or self.stop_cache is None:
            return
        
        existing_ids = {stop['stop_id'] for stop in self.stop_cache}
        new_stops = [stop for stop in stops if stop['stop_id'] not in existing_ids]
        
        if new_stops:
            self.stop_cache.extend(new_stops)
            # Save cache periodically (every 10 new stops)
            if len(new_stops) >= 10 or len(self.stop_cache) % 50 == 0:
                self._save_stop_cache()
    
    def _search_cache(self, query: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        """Search the cache for stops matching the query"""
        if not self.stop_cache:
            return None
        
        query_lower = query.lower()
        matches = []
        
        for stop in self.stop_cache:
            stop_name = stop.get('stop_name', '').lower()
            locality = stop.get('locality', '').lower()
            
            if query_lower in stop_name or query_lower in locality:
                matches.append(stop)
        
        # Sort by relevance (exact matches first, then contains)
        matches.sort(key=lambda s: (
            not s.get('stop_name', '').lower().startswith(query_lower),
            s.get('stop_name', '')
        ))
        
        return matches[:limit] if matches else None
    
    def _get_timestamp(self) -> str:
        """Generate current UTC timestamp in ISO-8601 format with Z suffix"""
        return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    def _create_base_request(self) -> ET.Element:
        """Create the base XML structure for TRIAS requests"""
        trias = ET.Element('Trias', {
            'xmlns': self.namespaces['trias'],
            'xmlns:siri': self.namespaces['siri'],
            'version': '1.2'
        })
        
        service_request = ET.SubElement(trias, 'ServiceRequest')
        
        # Add timestamp
        timestamp = ET.SubElement(service_request, '{%s}RequestTimestamp' % self.namespaces['siri'])
        timestamp.text = self._get_timestamp()
        
        # Add requestor ref
        requestor_ref = ET.SubElement(service_request, '{%s}RequestorRef' % self.namespaces['siri'])
        requestor_ref.text = self.requestor_ref
        
        # Add request payload container
        request_payload = ET.SubElement(service_request, 'RequestPayload')
        
        return trias, request_payload
    
    def _make_request(self, xml_body: str) -> ET.Element:
        """Make HTTP POST request to TRIAS API"""
        headers = {
            'Content-Type': 'text/xml',
            'Accept': 'text/xml'
        }
        
        try:
            response = requests.post(
                self.api_url,
                data=xml_body.encode('utf-8'),
                headers=headers,
                timeout=30
            )
            
            # Log first part of response if error
            if response.status_code >= 400:
                print(f"HTTP {response.status_code}: {response.text[:2000]}")
                response.raise_for_status()
            
            # Check for empty response
            if not response.content or len(response.content.strip()) == 0:
                raise Exception("API returned empty response")
            
            # Parse XML response
            try:
                return ET.fromstring(response.content)
            except ET.ParseError as e:
                print(f"XML Parse Error: {str(e)}")
                print(f"Response content (first 1000 chars): {response.content[:1000]}")
                raise Exception(f"Failed to parse XML response: {str(e)}")
            
        except requests.RequestException as e:
            raise Exception(f"API request failed: {str(e)}")
    
    def search_location_by_name(
        self, 
        location_name: str, 
        number_of_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for stops/locations by name (uses cache if available)
        
        Args:
            location_name: Name of the location to search for
            number_of_results: Maximum number of results to return
            
        Returns:
            List of location dictionaries with stop_id, stop_name, coordinates, etc.
        """
        # Try cache first if enabled
        if STOP_CACHE_ENABLED and self.stop_cache is not None:
            # Search cache
            cached_results = self._search_cache(location_name, number_of_results)
            if cached_results:
                print(f"[CACHE] Found {len(cached_results)} results in cache for '{location_name}'")
                return cached_results
        
        # Fetch from API
        print(f"[CACHE] Fetching '{location_name}' from API")
        results = self._fetch_location_by_name(location_name, number_of_results)
        
        # Add results to cache for future use
        if STOP_CACHE_ENABLED:
            self._add_to_cache(results)
        
        return results
    
    def _fetch_location_by_name(
        self, 
        location_name: str, 
        number_of_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch stops/locations by name from API (bypasses cache)
        
        Args:
            location_name: Name of the location to search for
            number_of_results: Maximum number of results to return
            
        Returns:
            List of location dictionaries with stop_id, stop_name, coordinates, etc.
        """
        trias, request_payload = self._create_base_request()
        
        # Build LocationInformationRequest
        loc_info_req = ET.SubElement(request_payload, 'LocationInformationRequest')
        
        initial_input = ET.SubElement(loc_info_req, 'InitialInput')
        location_name_elem = ET.SubElement(initial_input, 'LocationName')
        text = ET.SubElement(location_name_elem, 'Text')
        text.text = location_name
        language = ET.SubElement(location_name_elem, 'Language')
        language.text = 'de'
        
        restrictions = ET.SubElement(loc_info_req, 'Restrictions')
        type_elem = ET.SubElement(restrictions, 'Type')
        type_elem.text = 'stop'
        num_results = ET.SubElement(restrictions, 'NumberOfResults')
        num_results.text = str(number_of_results)
        
        # Convert to string and make request
        xml_string = ET.tostring(trias, encoding='utf-8', method='xml')
        xml_declaration = b'<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_body = xml_declaration + xml_string
        
        response_root = self._make_request(xml_body.decode('utf-8'))
        
        # Parse response
        return self._parse_location_results(response_root)
    
    def search_location_by_coordinates(
        self,
        longitude: float,
        latitude: float,
        radius: int = 500,
        number_of_results: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Search for stops near coordinates within a radius
        
        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            radius: Search radius in meters
            number_of_results: Maximum number of results
            
        Returns:
            List of location dictionaries
        """
        trias, request_payload = self._create_base_request()
        
        # Build LocationInformationRequest with InitialInput containing coordinates
        loc_info_req = ET.SubElement(request_payload, 'LocationInformationRequest')
        
        # Use InitialInput with GeoPosition (some TRIAS implementations require this)
        initial_input = ET.SubElement(loc_info_req, 'InitialInput')
        geo_position = ET.SubElement(initial_input, 'GeoPosition')
        lon_elem = ET.SubElement(geo_position, 'Longitude')
        lon_elem.text = str(longitude)
        lat_elem = ET.SubElement(geo_position, 'Latitude')
        lat_elem.text = str(latitude)
        
        # Add restrictions
        restrictions = ET.SubElement(loc_info_req, 'Restrictions')
        type_elem = ET.SubElement(restrictions, 'Type')
        type_elem.text = 'stop'
        num_results = ET.SubElement(restrictions, 'NumberOfResults')
        num_results.text = str(number_of_results)
        
        # Add PtModes to only get public transport stops
        pt_modes = ET.SubElement(restrictions, 'PtModes')
        include_all = ET.SubElement(pt_modes, 'IncludeAllModes')
        include_all.text = 'true'
        
        # Convert to string and make request
        xml_string = ET.tostring(trias, encoding='utf-8', method='xml')
        xml_declaration = b'<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_body = xml_declaration + xml_string
        
        response_root = self._make_request(xml_body.decode('utf-8'))
        
        # Parse response and filter by radius manually
        all_results = self._parse_location_results(response_root)
        
        # Filter results by distance from center point
        if all_results:
            import math
            filtered = []
            for result in all_results:
                if result.get('latitude') and result.get('longitude'):
                    # Haversine distance calculation for more accuracy
                    lat1, lon1 = math.radians(latitude), math.radians(longitude)
                    lat2, lon2 = math.radians(result['latitude']), math.radians(result['longitude'])
                    
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    
                    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                    c = 2 * math.asin(math.sqrt(a))
                    dist = 6371000 * c  # Earth radius in meters
                    
                    if dist <= radius:
                        result['distance'] = round(dist)
                        filtered.append(result)
            
            # Sort by distance
            filtered.sort(key=lambda x: x.get('distance', 999999))
            
            # Add to cache for future searches
            if STOP_CACHE_ENABLED and filtered:
                self._add_to_cache(filtered)
                print(f"[CACHE] Added {len(filtered)} nearby stops to cache")
            
            return filtered
        
        return all_results
    
    def get_departures(
        self,
        stop_id: str,
        number_of_results: int = 12,
        departure_window: int = 60,
        include_realtime: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get departure events for a stop
        
        Args:
            stop_id: StopPointRef ID (e.g., "at:46:7960")
            number_of_results: Maximum number of departures to return
            departure_window: Time window in minutes
            include_realtime: Whether to include realtime data
            
        Returns:
            List of departure dictionaries with times, line, destination, etc.
        """
        trias, request_payload = self._create_base_request()
        
        # Build StopEventRequest
        stop_event_req = ET.SubElement(request_payload, 'StopEventRequest')
        
        location = ET.SubElement(stop_event_req, 'Location')
        location_ref = ET.SubElement(location, 'LocationRef')
        stop_point_ref = ET.SubElement(location_ref, 'StopPointRef')
        stop_point_ref.text = stop_id
        
        params = ET.SubElement(stop_event_req, 'Params')
        num_results = ET.SubElement(params, 'NumberOfResults')
        num_results.text = str(number_of_results)
        stop_event_type = ET.SubElement(params, 'StopEventType')
        stop_event_type.text = 'departure'
        include_rt = ET.SubElement(params, 'IncludeRealtimeData')
        include_rt.text = 'true' if include_realtime else 'false'
        
        departure_window_elem = ET.SubElement(stop_event_req, 'DepartureWindow')
        departure_window_elem.text = str(departure_window)
        
        # Convert to string and make request
        xml_string = ET.tostring(trias, encoding='utf-8', method='xml')
        xml_declaration = b'<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_body = xml_declaration + xml_string
        
        response_root = self._make_request(xml_body.decode('utf-8'))
        
        # Parse response
        return self._parse_departure_results(response_root)
    
    def get_trip(
        self,
        origin: str,
        destination: str,
        number_of_results: int = 5,
        include_realtime: bool = True,
        departure_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get trip/route from origin to destination
        
        Args:
            origin: Origin location name or address
            destination: Destination location name or address
            number_of_results: Maximum number of trip options to return
            include_realtime: Whether to include realtime data
            departure_time: Departure time (defaults to now)
            
        Returns:
            Dictionary with origin, destination, and list of trips
        """
        # Resolve origin location
        origin_results = self.search_location_by_name(origin, 10)
        if not origin_results:
            raise Exception(f"Could not resolve origin: {origin}")
        origin_loc = origin_results[0]
        
        # Resolve destination location
        dest_results = self.search_location_by_name(destination, 10)
        if not dest_results:
            raise Exception(f"Could not resolve destination: {destination}")
        dest_loc = dest_results[0]
        
        # Build trip request
        trias, request_payload = self._create_base_request()
        
        trip_req = ET.SubElement(request_payload, 'TripRequest')
        
        # Origin
        origin_elem = ET.SubElement(trip_req, 'Origin')
        origin_ref = ET.SubElement(origin_elem, 'LocationRef')
        if origin_loc.get('stop_id'):
            stop_ref = ET.SubElement(origin_ref, 'StopPointRef')
            stop_ref.text = origin_loc['stop_id']
        elif origin_loc.get('latitude') and origin_loc.get('longitude'):
            geo_pos = ET.SubElement(origin_ref, 'GeoPosition')
            lon = ET.SubElement(geo_pos, 'Longitude')
            lon.text = str(origin_loc['longitude'])
            lat = ET.SubElement(geo_pos, 'Latitude')
            lat.text = str(origin_loc['latitude'])
        
        # Destination
        dest_elem = ET.SubElement(trip_req, 'Destination')
        dest_ref = ET.SubElement(dest_elem, 'LocationRef')
        if dest_loc.get('stop_id'):
            stop_ref = ET.SubElement(dest_ref, 'StopPointRef')
            stop_ref.text = dest_loc['stop_id']
        elif dest_loc.get('latitude') and dest_loc.get('longitude'):
            geo_pos = ET.SubElement(dest_ref, 'GeoPosition')
            lon = ET.SubElement(geo_pos, 'Longitude')
            lon.text = str(dest_loc['longitude'])
            lat = ET.SubElement(geo_pos, 'Latitude')
            lat.text = str(dest_loc['latitude'])
        
        # Departure time
        if departure_time is None:
            departure_time = datetime.utcnow()
        dep_time = ET.SubElement(trip_req, 'DepArrTime')
        dep_time.text = departure_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        # Parameters
        params = ET.SubElement(trip_req, 'Params')
        num_results = ET.SubElement(params, 'NumberOfResults')
        num_results.text = str(number_of_results)
        include_rt = ET.SubElement(params, 'IncludeRealtimeData')
        include_rt.text = 'true' if include_realtime else 'false'
        track_sections = ET.SubElement(params, 'IncludeTrackSections')
        track_sections.text = 'false'
        
        # Convert to string and make request
        xml_string = ET.tostring(trias, encoding='utf-8', method='xml')
        xml_declaration = b'<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_body = xml_declaration + xml_string
        
        response_root = self._make_request(xml_body.decode('utf-8'))
        
        # Parse response
        trips = self._parse_trip_results(response_root)
        
        return {
            'origin': {
                'name': origin_loc.get('stop_name') or origin,
                'stop_id': origin_loc.get('stop_id'),
                'latitude': origin_loc.get('latitude'),
                'longitude': origin_loc.get('longitude')
            },
            'destination': {
                'name': dest_loc.get('stop_name') or destination,
                'stop_id': dest_loc.get('stop_id'),
                'latitude': dest_loc.get('latitude'),
                'longitude': dest_loc.get('longitude')
            },
            'trips': trips
        }
    
    def _parse_location_results(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Parse LocationInformationResponse"""
        results = []
        
        # Find all LocationResult elements
        location_results = root.findall('.//trias:LocationResult', self.namespaces)
        
        for location_result in location_results:
            try:
                # Check if it's a StopPoint or StopPlace
                location = location_result.find('trias:Location', self.namespaces)
                if location is None:
                    continue
                
                # Try to find StopPoint first, then StopPlace
                stop_point = location.find('trias:StopPoint', self.namespaces)
                stop_place = location.find('trias:StopPlace', self.namespaces)
                
                stop_ref = None
                stop_name = None
                
                if stop_point is not None:
                    # This is a StopPoint (individual platform/stop)
                    stop_point_ref = stop_point.find('trias:StopPointRef', self.namespaces)
                    if stop_point_ref is None:
                        continue
                    stop_ref = stop_point_ref.text
                    stop_point_name = stop_point.find('trias:StopPointName/trias:Text', self.namespaces)
                    stop_name = stop_point_name.text if stop_point_name is not None else None
                    
                elif stop_place is not None:
                    # This is a StopPlace (stop area/group of platforms)
                    stop_place_ref = stop_place.find('trias:StopPlaceRef', self.namespaces)
                    if stop_place_ref is None:
                        continue
                    stop_ref = stop_place_ref.text
                    stop_place_name = stop_place.find('trias:StopPlaceName/trias:Text', self.namespaces)
                    stop_name = stop_place_name.text if stop_place_name is not None else None
                else:
                    # Skip addresses/POIs - we only want stops
                    continue
                
                if not stop_ref:
                    continue
                    
                # Get coordinates if available
                longitude_elem = location.find('.//trias:Longitude', self.namespaces)
                latitude_elem = location.find('.//trias:Latitude', self.namespaces)
                
                # Get locality name (city/area) if available
                locality_name = location.find('.//trias:LocationName/trias:Text', self.namespaces)
                
                result = {
                    'stop_id': stop_ref,
                    'stop_name': stop_name,
                    'locality': locality_name.text if locality_name is not None else None,
                    'longitude': float(longitude_elem.text) if longitude_elem is not None else None,
                    'latitude': float(latitude_elem.text) if latitude_elem is not None else None
                }
                
                results.append(result)
                
            except Exception as e:
                print(f"Error parsing location result: {e}")
                continue
        
        # Group by stop name and combine
        grouped = {}
        for result in results:
            stop_name = result['stop_name']
            if not stop_name:
                continue
                
            if stop_name not in grouped:
                # First occurrence - keep as is but prepare for multiple IDs
                grouped[stop_name] = {
                    'stop_id': [result['stop_id']],
                    'stop_name': stop_name,
                    'locality': result['locality'],
                    'longitude': result['longitude'],
                    'latitude': result['latitude'],
                    'platforms': 1
                }
            else:
                # Additional platform/variant - add ID and update coordinates if missing
                grouped[stop_name]['stop_id'].append(result['stop_id'])
                grouped[stop_name]['platforms'] += 1
                
                # Use first coordinates if current one is None
                if grouped[stop_name]['longitude'] is None and result['longitude'] is not None:
                    grouped[stop_name]['longitude'] = result['longitude']
                    grouped[stop_name]['latitude'] = result['latitude']
        
        # Convert grouped results back to list format
        combined_results = []
        for stop_name, data in grouped.items():
            # Use first stop_id as primary (for backward compatibility)
            # but include all IDs in the result
            result = {
                'stop_id': data['stop_id'][0],  # Primary ID
                'stop_ids': data['stop_id'],     # All IDs
                'stop_name': data['stop_name'],
                'locality': data['locality'],
                'longitude': data['longitude'],
                'latitude': data['latitude'],
                'platforms': data['platforms']
            }
            combined_results.append(result)
        
        return combined_results
    
    def _parse_departure_results(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Parse StopEventResponse"""
        results = []
        
        # Find all StopEventResult elements
        for stop_event_result in root.findall('.//trias:StopEventResult', self.namespaces):
            try:
                stop_event = stop_event_result.find('trias:StopEvent', self.namespaces)
                if stop_event is None:
                    continue
                
                # Get times
                this_call = stop_event.find('.//trias:ThisCall', self.namespaces)
                call_at_stop = this_call.find('.//trias:CallAtStop', self.namespaces)
                service_departure = call_at_stop.find('.//trias:ServiceDeparture', self.namespaces)
                
                timetabled_time = service_departure.find('trias:TimetabledTime', self.namespaces)
                estimated_time = service_departure.find('trias:EstimatedTime', self.namespaces)
                
                # Get line info
                service = stop_event.find('.//trias:Service', self.namespaces)
                published_line = service.find('.//trias:PublishedLineName/trias:Text', self.namespaces)
                
                # Get destination
                destination = service.find('.//trias:DestinationText/trias:Text', self.namespaces)
                
                # Get mode (bus, tram, etc.)
                mode = service.find('.//trias:Mode/trias:PtMode', self.namespaces)
                
                # Calculate actual time and delay
                planned_time_str = timetabled_time.text if timetabled_time is not None else None
                estimated_time_str = estimated_time.text if estimated_time is not None else None
                actual_time_str = estimated_time_str if estimated_time_str else planned_time_str
                
                delay_minutes = None
                delay_seconds = None
                if planned_time_str and estimated_time_str:
                    try:
                        planned = datetime.fromisoformat(planned_time_str.replace('Z', '+00:00'))
                        estimated = datetime.fromisoformat(estimated_time_str.replace('Z', '+00:00'))
                        delay_seconds = int((estimated - planned).total_seconds())
                        delay_minutes = round(delay_seconds / 60)
                    except:
                        pass
                
                result = {
                    'line': published_line.text if published_line is not None else None,
                    'destination': destination.text if destination is not None else None,
                    'mode': mode.text if mode is not None else None,
                    'planned_time': planned_time_str,
                    'estimated_time': estimated_time_str,
                    'actual_time': actual_time_str,
                    'delay_minutes': delay_minutes,
                    'delay_seconds': delay_seconds,
                    'has_realtime': estimated_time_str is not None,
                    'current_time': datetime.utcnow().isoformat() + 'Z'
                }
                
                results.append(result)
                
            except Exception as e:
                print(f"Error parsing departure result: {e}")
                continue
        
        return results
    
    def _parse_trip_results(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Parse TripResponse"""
        trips = []
        
        for trip_result in root.findall('.//trias:TripResult', self.namespaces):
            try:
                trip = trip_result.find('trias:Trip', self.namespaces)
                if trip is None:
                    continue
                
                # Get overall trip times
                start_time = trip.findtext('trias:StartTime', default=None, namespaces=self.namespaces)
                end_time = trip.findtext('trias:EndTime', default=None, namespaces=self.namespaces)
                duration = trip.findtext('trias:Duration', default=None, namespaces=self.namespaces)
                
                # Parse legs
                legs = []
                for leg_elem in trip.findall('trias:TripLeg', self.namespaces):
                    leg_data = self._parse_trip_leg(leg_elem)
                    if leg_data:
                        legs.append(leg_data)
                
                trip_data = {
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': duration,
                    'legs': legs
                }
                
                trips.append(trip_data)
                
            except Exception as e:
                print(f"Error parsing trip result: {e}")
                continue
        
        return trips
    
    def _parse_trip_leg(self, leg_elem: ET.Element) -> Optional[Dict[str, Any]]:
        """Parse a single trip leg (TimedLeg or ContinuousLeg)"""
        
        # Check for ContinuousLeg (walk, etc.)
        cont_leg = leg_elem.find('trias:ContinuousLeg', self.namespaces)
        if cont_leg is not None:
            return self._parse_continuous_leg(cont_leg)
        
        # Check for TimedLeg (public transport)
        timed_leg = leg_elem.find('trias:TimedLeg', self.namespaces)
        if timed_leg is not None:
            return self._parse_timed_leg(timed_leg)
        
        return None
    
    def _parse_continuous_leg(self, leg: ET.Element) -> Dict[str, Any]:
        """Parse ContinuousLeg (walking, etc.)"""
        
        # Get start point
        start_elem = leg.find('.//trias:LegStart', self.namespaces)
        start_name = None
        start_time = None
        if start_elem is not None:
            start_name = start_elem.findtext('.//trias:StopPointName/trias:Text', default=None, namespaces=self.namespaces)
            if not start_name:
                start_name = start_elem.findtext('.//trias:LocationName/trias:Text', default=None, namespaces=self.namespaces)
            start_time = start_elem.findtext('trias:Time', default=None, namespaces=self.namespaces)
            if not start_time:
                start_time = start_elem.findtext('trias:EstimatedTime', default=None, namespaces=self.namespaces)
        
        # Get end point
        end_elem = leg.find('.//trias:LegEnd', self.namespaces)
        end_name = None
        end_time = None
        if end_elem is not None:
            end_name = end_elem.findtext('.//trias:StopPointName/trias:Text', default=None, namespaces=self.namespaces)
            if not end_name:
                end_name = end_elem.findtext('.//trias:LocationName/trias:Text', default=None, namespaces=self.namespaces)
            end_time = end_elem.findtext('trias:Time', default=None, namespaces=self.namespaces)
            if not end_time:
                end_time = end_elem.findtext('trias:EstimatedTime', default=None, namespaces=self.namespaces)
        
        # Get duration
        duration = leg.findtext('trias:Duration', default=None, namespaces=self.namespaces)
        
        return {
            'type': 'continuous',
            'mode': 'walk',
            'from': start_name or 'Unknown',
            'to': end_name or 'Unknown',
            'departure_time': start_time,
            'arrival_time': end_time,
            'duration': duration
        }
    
    def _parse_timed_leg(self, leg: ET.Element) -> Dict[str, Any]:
        """Parse TimedLeg (public transport)"""
        
        # Get boarding point
        board_elem = leg.find('.//trias:LegBoard', self.namespaces)
        board_name = None
        board_time = None
        board_time_planned = None
        if board_elem is not None:
            board_name = board_elem.findtext('.//trias:StopPointName/trias:Text', default=None, namespaces=self.namespaces)
            board_time = board_elem.findtext('.//trias:ServiceDeparture/trias:EstimatedTime', default=None, namespaces=self.namespaces)
            board_time_planned = board_elem.findtext('.//trias:ServiceDeparture/trias:TimetabledTime', default=None, namespaces=self.namespaces)
            if not board_time:
                board_time = board_time_planned
        
        # Get alighting point
        alight_elem = leg.find('.//trias:LegAlight', self.namespaces)
        alight_name = None
        alight_time = None
        alight_time_planned = None
        if alight_elem is not None:
            alight_name = alight_elem.findtext('.//trias:StopPointName/trias:Text', default=None, namespaces=self.namespaces)
            alight_time = alight_elem.findtext('.//trias:ServiceArrival/trias:EstimatedTime', default=None, namespaces=self.namespaces)
            alight_time_planned = alight_elem.findtext('.//trias:ServiceArrival/trias:TimetabledTime', default=None, namespaces=self.namespaces)
            if not alight_time:
                alight_time = alight_time_planned
        
        # Get service info
        service = leg.find('.//trias:Service', self.namespaces)
        line = None
        mode = None
        destination = None
        if service is not None:
            line = service.findtext('.//trias:PublishedLineName/trias:Text', default=None, namespaces=self.namespaces)
            mode = service.findtext('.//trias:Mode/trias:PtMode', default=None, namespaces=self.namespaces)
            destination = service.findtext('.//trias:DestinationText/trias:Text', default=None, namespaces=self.namespaces)
        
        # Get duration
        duration = leg.findtext('trias:Duration', default=None, namespaces=self.namespaces)
        
        return {
            'type': 'timed',
            'mode': mode or 'unknown',
            'line': line or 'Unknown',
            'destination': destination,
            'from': board_name or 'Unknown',
            'to': alight_name or 'Unknown',
            'departure_time': board_time,
            'departure_time_planned': board_time_planned,
            'arrival_time': alight_time,
            'arrival_time_planned': alight_time_planned,
            'duration': duration
        }
