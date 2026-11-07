import time
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import FakeResponse, FakeSession, fixture_bytes, fixture_json

from signage.aircraft import aircraft_icon, airline_from_callsign
from signage.providers import flights, timetable, transport, weather
from signage.providers.routes import RouteResolver, is_plausible, looks_like_flight_callsign

GRAZ = (47.07, 15.44)
VIENNA = ZoneInfo("Europe/Vienna")


# --- flights ------------------------------------------------------------------------

def test_normalize_computes_km_and_sorts():
    raw = fixture_json("adsb_point.json")["ac"]
    out = flights.normalize(raw, *GRAZ, radius_km=150)
    assert out, "fixture should contain aircraft"
    assert [f["distance_km"] for f in out] == sorted(f["distance_km"] for f in out)
    # API 'dst' is nautical miles; our km value must be ~1.852x larger
    by_hex = {a["hex"]: a for a in raw}
    f = out[0]
    assert f["distance_km"] == pytest.approx(by_hex[f["hex"]]["dst"] * 1.852, rel=0.05)


def test_normalize_filters_ground_radius_and_dupes():
    raw = [
        {"hex": "a", "flight": "DLH1  ", "lat": 47.08, "lon": 15.44, "alt_baro": "ground"},
        {"hex": "b", "flight": "AUA2", "lat": 47.10, "lon": 15.44, "alt_baro": 3000, "t": "A320"},
        {"hex": "b", "flight": "AUA2", "lat": 47.20, "lon": 15.44, "alt_baro": 3000, "t": "A320"},
        {"hex": "c", "lat": 49.0, "lon": 15.44, "alt_baro": 3000},  # ~215 km away
        {"hex": "d", "lat": None, "lon": None},
        {"hex": "e", "flight": "C12", "lat": 47.09, "lon": 15.45, "alt_baro": 1500},
    ]
    out = flights.normalize(raw, *GRAZ, radius_km=100)
    assert [f["hex"] for f in out] == ["e", "b"]
    assert out[0]["icon"] == "c0" and out[0]["type"] == "H135"  # Christophorus
    assert out[1]["icon"] == "a320" and out[1]["distance_km"] < 5
    with_ground = flights.normalize(raw, *GRAZ, radius_km=100, include_ground=True)
    assert with_ground[0]["on_ground"] and with_ground[0]["altitude_ft"] is None


def test_provider_failover():
    def handler(method, url, **kw):
        if "adsb.lol" in url:
            return FakeResponse(403, {"error": "contact us"})
        return FakeResponse(200, {"aircraft": [{"hex": "x"}]})

    ac, provider = flights.fetch_aircraft(FakeSession(handler), ["adsb.lol", "adsb.fi"], *GRAZ, 75)
    assert provider == "adsb.fi" and ac == [{"hex": "x"}]


def test_provider_all_fail():
    with pytest.raises(flights.ProviderError, match="adsb.lol: HTTP 500"):
        flights.fetch_aircraft(FakeSession(lambda *a, **k: FakeResponse(500)), ["adsb.lol"], *GRAZ, 75)


def test_aircraft_icons_and_airlines():
    assert aircraft_icon("A20N") == "a320"
    assert aircraft_icon("AT76") == "a1"
    assert aircraft_icon("ZZZZ", "A7") == "c0"
    assert aircraft_icon("") == "a0"
    assert airline_from_callsign("DLH4AB") == ("DLH", "Lufthansa")
    assert airline_from_callsign("OEABC") == ("", "")


# --- routes ------------------------------------------------------------------------------

def test_plausibility():
    route = fixture_json("adsbdb_dlh400.json")["response"]["flightroute"]
    r = {"origin": {"lat": route["origin"]["latitude"], "lon": route["origin"]["longitude"]},
         "destination": {"lat": route["destination"]["latitude"], "lon": route["destination"]["longitude"]}}
    assert is_plausible(r, 51.5, 0.0)      # over London on the way FRA -> JFK
    assert is_plausible(r, 50.1, 8.7)      # near Frankfurt
    assert not is_plausible(r, 41.0, 29.0)  # over Istanbul: wrong


def test_callsign_filter():
    assert looks_like_flight_callsign("DLH400")
    assert not looks_like_flight_callsign("OEABC")
    assert not looks_like_flight_callsign("C12")


def test_resolver_caches_and_limits(tmp_path):
    body = fixture_json("adsbdb_dlh400.json")

    def handler(method, url, **kw):
        if url.endswith("DLH400"):
            return FakeResponse(200, body)
        return FakeResponse(200, {"response": "unknown callsign"})

    sess = FakeSession(handler)
    res = RouteResolver(tmp_path / "routes.json", sess)
    fl = [{"callsign": "DLH400", "lat": 50.1, "lon": 8.7}, {"callsign": "XYZ123", "lat": 50.1, "lon": 8.7},
          {"callsign": "OEABC", "lat": 50.1, "lon": 8.7}]
    res.annotate(fl, {"enabled": True, "cache_days": 14})
    assert fl[0]["route"]["destination"]["iata"] == "JFK"
    assert fl[0]["airline"] == "Lufthansa"
    assert "route" not in fl[1] or fl[1]["route"] is None
    assert len(sess.calls) == 2  # registration not looked up
    res.annotate([dict(f) for f in fl], {"enabled": True, "cache_days": 14})
    assert len(sess.calls) == 2  # both cached (positive and negative)
    res.flush()
    res2 = RouteResolver(tmp_path / "routes.json", sess)
    assert {r["callsign"] for r in res2.list()} == {"DLH400", "XYZ123"}


def test_resolver_error_retries_later_and_manual_wins(tmp_path):
    sess = FakeSession(lambda *a, **k: FakeResponse(503))
    res = RouteResolver(tmp_path / "r.json", sess)
    fl = [{"callsign": "AUA123", "lat": 47, "lon": 15}]
    res.annotate(fl, {"enabled": True})
    entry = res.list()[0]
    assert entry["error"] and not entry["found"]
    res.set_manual("AUA123", "VIE", "GRZ")
    fl = [{"callsign": "AUA123", "lat": 47, "lon": 15}]
    res.annotate(fl, {"enabled": True})
    assert fl[0]["route"]["origin"]["iata"] == "VIE"


def test_resolver_lookup_budget(tmp_path):
    sess = FakeSession(lambda *a, **k: FakeResponse(200, {"response": "unknown callsign"}))
    res = RouteResolver(tmp_path / "r.json", sess)
    res.annotate([{"callsign": f"DLH{i}00", "lat": 47, "lon": 15} for i in range(10)], {"enabled": True})
    assert len(sess.calls) == 4


def test_old_route_cache_is_discarded(tmp_path):
    p = tmp_path / "r.json"
    p.write_text('{"DLH1": {"from": "EDDF", "to": "LOWW", "last_seen": "2026-01-01T00:00:00"}}')
    assert RouteResolver(p, FakeSession(lambda *a, **k: None)).list() == []


# --- weather -------------------------------------------------------------------------------

def test_open_meteo_parse():
    w = weather.parse_open_meteo(fixture_json("openmeteo_current.json"))
    assert w["provider"] == "open-meteo" and w["icon"] == "cloudy"
    assert w["visibility_km"] == 32.6 and w["pressure_hpa"] == 1028 and w["wind_dir_deg"] == 330


def test_owm_parse():
    w = weather.parse_owm_current({
        "weather": [{"description": "light rain", "icon": "10n"}],
        "main": {"temp": 10, "humidity": 80, "pressure": 1012, "feels_like": 9},
        "wind": {"speed": 5, "deg": 200}, "visibility": 10000, "clouds": {"all": 90},
    })
    assert w["icon"] == "rain" and not w["is_day"] and w["wind_kt"] == 10 and w["dew_point_c"] == 6.0


# --- transport ------------------------------------------------------------------------------

def test_parse_departures_fixture():
    root = ET.fromstring(fixture_bytes("trias_departures.xml"))
    deps = transport.parse_departures(root, VIENNA)
    assert deps and deps[0]["line"] == "552" and deps[0]["mode"] == "bus"
    assert deps[0]["planned"].endswith("+01:00")  # converted from UTC to Vienna (winter)
    assert deps == sorted(deps, key=lambda d: d["expected"])


def test_parse_departures_realtime_and_cancelled():
    xml = b"""<trias:Trias xmlns:trias="http://www.vdv.de/trias"><trias:StopEvent>
      <trias:ThisCall><trias:CallAtStop><trias:ServiceDeparture>
        <trias:TimetabledTime>2026-11-06T10:00:00Z</trias:TimetabledTime>
        <trias:EstimatedTime>2026-11-06T10:03:00Z</trias:EstimatedTime>
      </trias:ServiceDeparture></trias:CallAtStop></trias:ThisCall>
      <trias:Service><trias:ServiceSection><trias:Mode><trias:PtMode>tram</trias:PtMode></trias:Mode>
        <trias:PublishedLineName><trias:Text>7</trias:Text></trias:PublishedLineName></trias:ServiceSection>
        <trias:Cancelled>true</trias:Cancelled>
        <trias:DestinationText><trias:Text>Wetzelsdorf</trias:Text></trias:DestinationText></trias:Service>
    </trias:StopEvent></trias:Trias>"""
    d = transport.parse_departures(ET.fromstring(xml), VIENNA)[0]
    assert d["realtime"] and d["delay_min"] == 3 and d["cancelled"] and d["mode"] == "tram"
    assert d["expected"] == "2026-11-06T11:03:00+01:00"


def test_requests_escape_input():
    body = transport.location_request_by_name('<x>&"', 5)
    ET.fromstring(body)  # still well-formed XML
    assert b"&lt;x&gt;&amp;" in body


def test_parse_locations_fixture():
    stops = transport.parse_locations(ET.fromstring(fixture_bytes("trias_location.xml")))
    assert stops[0]["stop_id"] == "at:41:18415" and stops[0]["lat"] == pytest.approx(47.02944)


def test_stop_name_matching():
    assert transport._matches("alte poststraße", "Alte Poststraße (Remise)")
    assert transport._matches("Alte Poststrasse", "Alte Poststraße")
    assert not transport._matches("Hauptplatz", "Alte Poststraße")


# --- timetable --------------------------------------------------------------------------------

def test_parse_title_regular():
    t = timetable.parse_title("Sustainable Aviation Fuels (-114053) (Vorlesung (VO)), Kraft Gerhard, "
                              "Standardgruppe, ., AP149 AP149.02.201 (LAV 2024)")
    assert t["course"] == "Sustainable Aviation Fuels"
    assert t["kind"] == "VO" and t["room"] == "AP149.02.201" and t["cohort"] == "LAV24"
    assert t["lecturer"] == "Kraft Gerhard" and t["group"] == "" and not t["online"]


def test_parse_title_online_and_exam():
    t = timetable.parse_title("Flugmechanik und Drehflügler (-114060) (Integrierte Lehrveranstaltung (IL)), "
                              "Arnold Uwe T.P., Standardgruppe, Online (LAV 2024)")
    assert t["course"] == "Flugmechanik und Drehflügler" and t["kind"] == "IL" and t["online"]
    e = timetable.parse_title("Prüfungstermin: B22.0587404 25S 3SSt IL Kunst- und Faserverbundwerkstoffe  bei "
                              "Windbacher, -, AP149 AP149.02.212 (LAV 2023)")
    assert e["kind"] == "EXAM" and e["course"] == "Kunst- und Faserverbundwerkstoffe"
    assert e["room"] == "AP149.02.212"


def test_cohorts():
    oct_ = datetime(2026, 10, 5, tzinfo=VIENNA)
    sep = datetime(2026, 9, 5, tzinfo=VIENNA)
    assert timetable.default_cohorts(oct_)[:3] == ["LAV 2024", "LAV 2025", "LAV 2026"]
    assert timetable.default_cohorts(sep)[2] == "LAV 2025"
    assert timetable.parse_cohorts("lav23, MAV 2025", oct_) == ["LAV 2023", "MAV 2025"]
    assert timetable.parse_cohorts(" ", oct_) == timetable.default_cohorts(oct_)


def test_build_lectures_ongoing_window_and_dedupe():
    events = fixture_json("almaty_lav2024.json")
    now = datetime(2026, 11, 6, 10, 0, tzinfo=VIENNA)  # during the 09:00-12:15 lecture
    out = timetable.build_lectures(events + events, now, 24, True, VIENNA)
    assert out[0]["ongoing"] and out[0]["course"] == "Sustainable Aviation Fuels"
    assert len({(x["start"], x["course"]) for x in out}) == len(out)
    without = timetable.build_lectures(events, now, 24, False, VIENNA)
    assert all(not x["ongoing"] for x in without)
    narrow = timetable.build_lectures(events, now, 1, True, VIENNA)
    assert all(datetime.fromisoformat(x["start"]) <= datetime(2026, 11, 6, 11, 0, tzinfo=VIENNA) for x in narrow)


# --- poller -----------------------------------------------------------------------------------

def test_poller_keeps_last_data_on_error():
    from signage.poller import Poller, SourceDisabled

    state = {"fail": False, "disabled": False}

    def fetch():
        if state["disabled"]:
            raise SourceDisabled("off")
        if state["fail"]:
            raise RuntimeError("boom")
        return [1, 2], {"provider": "x"}

    p = Poller("t", fetch, lambda: 10)
    p.run_once()
    assert p.to_dict()["status"] == "ok" and p.to_dict()["meta"] == {"provider": "x"}
    state["fail"] = True
    p.run_once()
    d = p.to_dict()
    assert d["status"] == "error" and d["data"] == [1, 2] and d["stale"] and d["error"] == "boom"
    assert p._next_delay() == 10
    p.run_once()
    assert p._next_delay() == 20  # backoff
    state["disabled"] = True
    p.run_once()
    assert p.to_dict()["status"] == "disabled" and p.to_dict()["data"] is None


def test_poller_marks_old_data_stale():
    from signage.poller import Poller

    p = Poller("t", lambda: 1, lambda: 10)
    p.run_once()
    assert not p.to_dict()["stale"]
    p._snapshot.updated_at = time.time() - 3600
    assert p.to_dict()["stale"]
