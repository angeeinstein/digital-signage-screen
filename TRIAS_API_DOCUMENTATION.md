# TRIAS API Documentation (Direct Access)

## Overview

This guide explains how to directly query the **TRIAS API** (Austrian public transit data source) to get stop information and departures.

**API Endpoint:** `http://ogdtrias.verbundlinie.at:8183/stv/trias`

**Protocol:** XML/SOAP-based requests with POST method

**Namespace:** `http://www.vdv.de/trias`

## Authentication

No authentication required - the API is publicly accessible.

## Step 1: Finding Stops (LocationInformationRequest)

To get departure information, you first need a **Stop ID** (StopPointRef). Use the LocationInformationRequest to search for stops by name.

### Request Structure

**Endpoint:** `POST http://ogdtrias.verbundlinie.at:8183/stv/trias`

**Headers:**
```
Content-Type: text/xml
Accept: text/xml
```

**XML Request Body:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Trias xmlns="http://www.vdv.de/trias" xmlns:siri="http://www.siri.org.uk/siri" version="1.2">
    <ServiceRequest>
        <siri:RequestTimestamp>2026-02-06T12:00:00Z</siri:RequestTimestamp>
        <siri:RequestorRef>your_app_name</siri:RequestorRef>
        <RequestPayload>
            <LocationInformationRequest>
                <InitialInput>
                    <LocationName>
                        <Text>Jakominiplatz</Text>
                        <Language>de</Language>
                    </LocationName>
                </InitialInput>
                <Restrictions>
                    <Type>stop</Type>
                    <NumberOfResults>10</NumberOfResults>
                </Restrictions>
            </LocationInformationRequest>
        </RequestPayload>
    </ServiceRequest>
</Trias>
```

**Key Elements:**
- `RequestTimestamp`: Current UTC timestamp (ISO 8601 format with Z suffix)
- `RequestorRef`: Your application identifier (any string)
- `LocationName/Text`: Search query (e.g., "Jakominiplatz", "Hauptbahnhof")
- `Language`: Language code (use "de" for German)
- `Type`: Set to "stop" to search for stops/stations
- `NumberOfResults`: Maximum number of results to return

### Response Example

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Trias xmlns="http://www.vdv.de/trias" version="1.2">
    <ServiceDelivery>
        <ResponseTimestamp>2026-02-06T12:00:01Z</ResponseTimestamp>
        <DeliveryPayload>
            <LocationInformationResponse>
                <Location>
                    <Location>
                        <StopPoint>
                            <StopPointRef>AT:47:1234:1:1</StopPointRef>
                            <StopPointName>
                                <Text>Graz Jakominiplatz</Text>
                            </StopPointName>
                            <LocalityRef>Graz</LocalityRef>
                        </StopPoint>
                        <GeoPosition>
                            <Longitude>15.4395</Longitude>
                            <Latitude>47.0707</Latitude>
                        </GeoPosition>
                    </Location>
                </Location>
                <Location>
                    <Location>
                        <StopPoint>
                            <StopPointRef>AT:47:1234:1:2</StopPointRef>
                            <StopPointName>
                                <Text>Graz Jakominiplatz/Ost</Text>
                            </StopPointName>
                            <LocalityRef>Graz</LocalityRef>
                        </StopPoint>
                        <GeoPosition>
                            <Longitude>15.4400</Longitude>
                            <Latitude>47.0710</Latitude>
                        </GeoPosition>
                    </Location>
                </Location>
            </LocationInformationResponse>
        </DeliveryPayload>
    </ServiceDelivery>
</Trias>
```

**Extract the Stop ID:**
The `StopPointRef` element contains the Stop ID you need (e.g., `AT:47:1234:1:1`).

### Alternative: Search by Coordinates

To search for nearby stops using coordinates:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Trias xmlns="http://www.vdv.de/trias" xmlns:siri="http://www.siri.org.uk/siri" version="1.2">
    <ServiceRequest>
        <siri:RequestTimestamp>2026-02-06T12:00:00Z</siri:RequestTimestamp>
        <siri:RequestorRef>your_app_name</siri:RequestorRef>
        <RequestPayload>
            <LocationInformationRequest>
                <InitialInput>
                    <GeoPosition>
                        <Longitude>15.4395</Longitude>
                        <Latitude>47.0707</Latitude>
                    </GeoPosition>
                </InitialInput>
                <Restrictions>
                    <Type>stop</Type>
                    <NumberOfResults>20</NumberOfResults>
                </Restrictions>
            </LocationInformationRequest>
        </RequestPayload>
    </ServiceRequest>
</Trias>
```

## Step 2: Getting Departures (StopEventRequest)

Once you have a Stop ID, use the StopEventRequest to get real-time departure information.

### Request Structure

**XML Request Body:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Trias xmlns="http://www.vdv.de/trias" xmlns:siri="http://www.siri.org.uk/siri" version="1.2">
    <ServiceRequest>
        <siri:RequestTimestamp>2026-02-06T12:00:00Z</siri:RequestTimestamp>
        <siri:RequestorRef>your_app_name</siri:RequestorRef>
        <RequestPayload>
            <StopEventRequest>
                <Location>
                    <LocationRef>
                        <StopPointRef>AT:47:1234:1:1</StopPointRef>
                    </LocationRef>
                </Location>
                <Params>
                    <NumberOfResults>10</NumberOfResults>
                    <StopEventType>departure</StopEventType>
                    <IncludeRealtimeData>true</IncludeRealtimeData>
                </Params>
                <DepartureWindow>60</DepartureWindow>
            </StopEventRequest>
        </RequestPayload>
    </ServiceRequest>
</Trias>
```

**Key Elements:**
- `StopPointRef`: The Stop ID from the previous search
- `NumberOfResults`: Maximum number of departures to return
- `StopEventType`: Set to "departure" (or "arrival" for arrivals)
- `IncludeRealtimeData`: Set to "true" to include real-time predictions
- `DepartureWindow`: Time window in minutes (e.g., 60 = next hour)

### Response Example

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Trias xmlns="http://www.vdv.de/trias" version="1.2">
    <ServiceDelivery>
        <ResponseTimestamp>2026-02-06T12:00:01Z</ResponseTimestamp>
        <DeliveryPayload>
            <StopEventResponse>
                <StopEventResult>
                    <ResultId>1</ResultId>
                    <StopEvent>
                        <ThisCall>
                            <CallAtStop>
                                <ServiceDeparture>
                                    <TimetabledTime>2026-02-06T13:30:00</TimetabledTime>
                                    <EstimatedTime>2026-02-06T13:32:00</EstimatedTime>
                                </ServiceDeparture>
                            </CallAtStop>
                        </ThisCall>
                        <Service>
                            <OperatingDayRef>2026-02-06</OperatingDayRef>
                            <PublishedLineName>
                                <Text>1</Text>
                            </PublishedLineName>
                            <DestinationText>
                                <Text>Mariatrost</Text>
                            </DestinationText>
                        </Service>
                    </StopEvent>
                </StopEventResult>
                <StopEventResult>
                    <ResultId>2</ResultId>
                    <StopEvent>
                        <ThisCall>
                            <CallAtStop>
                                <ServiceDeparture>
                                    <TimetabledTime>2026-02-06T13:25:00</TimetabledTime>
                                </ServiceDeparture>
                            </CallAtStop>
                        </ThisCall>
                        <Service>
                            <PublishedLineName>
                                <Text>7</Text>
                            </PublishedLineName>
                            <DestinationText>
                                <Text>LKH/Med Uni</Text>
                            </DestinationText>
                        </Service>
                    </StopEvent>
                </StopEventResult>
            </StopEventResponse>
        </DeliveryPayload>
    </ServiceDelivery>
</Trias>
```

**Key Response Elements:**
- `TimetabledTime`: Scheduled departure time
- `EstimatedTime`: Real-time predicted departure (if available)
- `PublishedLineName/Text`: Line number (e.g., "1", "7", "S1")
- `DestinationText/Text`: Final destination

**Note:** If `EstimatedTime` is present, real-time data is available. If only `TimetabledTime` exists, it's schedule-based.

## Complete Workflow Examples

### Using cURL

**1. Search for a stop:**
```bash
curl -X POST http://ogdtrias.verbundlinie.at:8183/stv/trias \
  -H "Content-Type: text/xml" \
  -d '<?xml version="1.0" encoding="UTF-8"?>
<Trias xmlns="http://www.vdv.de/trias" xmlns:siri="http://www.siri.org.uk/siri" version="1.2">
    <ServiceRequest>
        <siri:RequestTimestamp>2026-02-06T12:00:00Z</siri:RequestTimestamp>
        <siri:RequestorRef>my_app</siri:RequestorRef>
        <RequestPayload>
            <LocationInformationRequest>
                <InitialInput>
                    <LocationName>
                        <Text>Hauptbahnhof</Text>
                        <Language>de</Language>
                    </LocationName>
                </InitialInput>
                <Restrictions>
                    <Type>stop</Type>
                    <NumberOfResults>5</NumberOfResults>
                </Restrictions>
            </LocationInformationRequest>
        </RequestPayload>
    </ServiceRequest>
</Trias>'
```

**2. Extract the StopPointRef from the XML response**

**3. Get departures:**
```bash
curl -X POST http://ogdtrias.verbundlinie.at:8183/stv/trias \
  -H "Content-Type: text/xml" \
  -d '<?xml version="1.0" encoding="UTF-8"?>
<Trias xmlns="http://www.vdv.de/trias" xmlns:siri="http://www.siri.org.uk/siri" version="1.2">
    <ServiceRequest>
        <siri:RequestTimestamp>2026-02-06T12:00:00Z</siri:RequestTimestamp>
        <siri:RequestorRef>my_app</siri:RequestorRef>
        <RequestPayload>
            <StopEventRequest>
                <Location>
                    <LocationRef>
                        <StopPointRef>AT:47:9999:1:1</StopPointRef>
                    </LocationRef>
                </Location>
                <Params>
                    <NumberOfResults>15</NumberOfResults>
                    <StopEventType>departure</StopEventType>
                    <IncludeRealtimeData>true</IncludeRealtimeData>
                </Params>
                <DepartureWindow>60</DepartureWindow>
            </StopEventRequest>
        </RequestPayload>
    </ServiceRequest>
</Trias>'
```

### Using Python

```python
import requests
from datetime import datetime
import xml.etree.ElementTree as ET

API_URL = "http://ogdtrias.verbundlinie.at:8183/stv/trias"
NAMESPACES = {
    'trias': 'http://www.vdv.de/trias',
    'siri': 'http://www.siri.org.uk/siri'
}

def get_current_timestamp():
    """Get current UTC timestamp in TRIAS format"""
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

def search_stops(query):
    """Search for stops by name"""
    xml_request = f'''<?xml version="1.0" encoding="UTF-8"?>
<Trias xmlns="http://www.vdv.de/trias" xmlns:siri="http://www.siri.org.uk/siri" version="1.2">
    <ServiceRequest>
        <siri:RequestTimestamp>{get_current_timestamp()}</siri:RequestTimestamp>
        <siri:RequestorRef>python_client</siri:RequestorRef>
        <RequestPayload>
            <LocationInformationRequest>
                <InitialInput>
                    <LocationName>
                        <Text>{query}</Text>
                        <Language>de</Language>
                    </LocationName>
                </InitialInput>
                <Restrictions>
                    <Type>stop</Type>
                    <NumberOfResults>10</NumberOfResults>
                </Restrictions>
            </LocationInformationRequest>
        </RequestPayload>
    </ServiceRequest>
</Trias>'''
    
    response = requests.post(
        API_URL,
        data=xml_request.encode('utf-8'),
        headers={'Content-Type': 'text/xml'}
    )
    
    # Parse XML response
    root = ET.fromstring(response.content)
    stops = []
    
    # Extract stop information
    for location in root.findall('.//trias:Location', NAMESPACES):
        stop_ref_elem = location.find('.//trias:StopPointRef', NAMESPACES)
        stop_name_elem = location.find('.//trias:StopPointName/trias:Text', NAMESPACES)
        lon_elem = location.find('.//trias:Longitude', NAMESPACES)
        lat_elem = location.find('.//trias:Latitude', NAMESPACES)
        
        if stop_ref_elem is not None and stop_name_elem is not None:
            stops.append({
                'stop_id': stop_ref_elem.text,
                'stop_name': stop_name_elem.text,
                'longitude': float(lon_elem.text) if lon_elem is not None else None,
                'latitude': float(lat_elem.text) if lat_elem is not None else None
            })
    
    return stops

def get_departures(stop_id, limit=10):
    """Get departures for a stop"""
    xml_request = f'''<?xml version="1.0" encoding="UTF-8"?>
<Trias xmlns="http://www.vdv.de/trias" xmlns:siri="http://www.siri.org.uk/siri" version="1.2">
    <ServiceRequest>
        <siri:RequestTimestamp>{get_current_timestamp()}</siri:RequestTimestamp>
        <siri:RequestorRef>python_client</siri:RequestorRef>
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
    
    response = requests.post(
        API_URL,
        data=xml_request.encode('utf-8'),
        headers={'Content-Type': 'text/xml'}
    )
    
    # Parse XML response
    root = ET.fromstring(response.content)
    departures = []
    
    for stop_event in root.findall('.//trias:StopEvent', NAMESPACES):
        line_elem = stop_event.find('.//trias:PublishedLineName/trias:Text', NAMESPACES)
        dest_elem = stop_event.find('.//trias:DestinationText/trias:Text', NAMESPACES)
        timetabled_elem = stop_event.find('.//trias:TimetabledTime', NAMESPACES)
        estimated_elem = stop_event.find('.//trias:EstimatedTime', NAMESPACES)
        
        departures.append({
            'line': line_elem.text if line_elem is not None else 'N/A',
            'direction': dest_elem.text if dest_elem is not None else 'N/A',
            'planned_time': timetabled_elem.text if timetabled_elem is not None else None,
            'estimated_time': estimated_elem.text if estimated_elem is not None else None,
            'is_realtime': estimated_elem is not None
        })
    
    return departures

# Example usage:
if __name__ == '__main__':
    # Search for stops
    print("Searching for 'Hauptbahnhof'...")
    stops = search_stops('Hauptbahnhof')
    
    if stops:
        print(f"\nFound {len(stops)} stops:")
        for stop in stops:
            print(f"  - {stop['stop_name']} (ID: {stop['stop_id']})")
        
        # Get departures for first stop
        stop_id = stops[0]['stop_id']
        print(f"\nGetting departures for {stops[0]['stop_name']}...")
        departures = get_departures(stop_id, limit=5)
        
        print(f"\nNext {len(departures)} departures:")
        for dep in departures:
            time = dep['estimated_time'] if dep['is_realtime'] else dep['planned_time']
            status = "🔴 Live" if dep['is_realtime'] else "📅 Scheduled"
            print(f"  Line {dep['line']} → {dep['direction']}: {time} ({status})")
    else:
        print("No stops found")
```

## XML Namespaces

When parsing responses, use these namespaces:

```python
NAMESPACES = {
    'trias': 'http://www.vdv.de/trias',
    'siri': 'http://www.siri.org.uk/siri'
}
```

## Important Notes

1. **Stop ID Format**: Stop IDs follow the format `AT:{region}:{stop}:{platform}:{variant}`
   - Example: `AT:47:1234:1:1`

2. **Timestamps**: Always use UTC time in ISO 8601 format with `Z` suffix
   - Example: `2026-02-06T12:00:00Z`

3. **Real-time Data**: 
   - If `EstimatedTime` exists → Real-time data available
   - If only `TimetabledTime` exists → Scheduled data only

4. **StopPlace vs StopPoint**:
   - Coordinate searches may return `StopPlace` elements instead of `StopPoint`
   - Both contain `StopPointRef` which is the Stop ID you need

5. **Rate Limiting**: The API has no official rate limits, but be respectful:
   - Don't make excessive concurrent requests
   - Cache stop information locally
   - Use appropriate time windows to minimize requests

6. **Language**: Use `de` for German (primary language in Austria)

7. **Error Handling**: The API returns XML error messages in the response body with HTTP 200, so always check the response content for error elements.

## Additional Request Types

### Trip/Route Planning (TripRequest)

For journey planning between two locations, use TripRequest (see separate documentation or source code for details).

## Support

For issues with the TRIAS API itself, contact:
- **Provider**: Verbund Linie (Austrian Public Transit Network)
- **API Documentation**: Limited official documentation available
- **Data Source**: Open Government Data (OGD) Austria

## License

The TRIAS API data is provided under Open Government Data Austria terms. Check the official OGD portal for current license information.
