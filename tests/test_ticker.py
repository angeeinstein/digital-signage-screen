import io
import time
from datetime import date, datetime, timezone

import pytest
from conftest import FakeResponse, FakeSession, H, fixture_bytes

from signage.announcements import AnnouncementError, AnnouncementStore, image_type, is_active, validate
from signage.providers import news
from signage.ticker import AircraftEvents, aircraft_event, compass

NOW = datetime(2026, 11, 6, 20, 0, tzinfo=timezone.utc)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# --- news ---------------------------------------------------------------------

def test_parse_rss_feed():
    items = news.parse_feed(fixture_bytes("news_rss.xml"), "https://www.austrianwings.info/feed.rss")
    assert len(items) == 4
    first = items[0]
    assert first["source"] == "Austrian Wings"
    assert first["title"].startswith("Notlandung in Wien")
    assert first["link"] == "https://www.austrianwings.info/2026/11/notlandung/"
    assert first["published"] == "2026-11-06T13:08:00+00:00"
    assert items[1]["title"] == "Neue Strecke Graz – Hamburg ab Sommer"  # double-escaped entity
    assert items[3]["published"] is None


def test_parse_atom_feed():
    atom = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom"><title>Example Aviation | News</title>
      <entry><title type="html">Crash &lt;b&gt;landing&lt;/b&gt;</title><id>urn:1</id>
        <link rel="alternate" href="https://example.org/1"/><updated>2026-11-06T18:00:00Z</updated></entry>
    </feed>"""
    [item] = news.parse_feed(atom, "https://example.org/feed")
    assert item == {"id": item["id"], "title": "Crash landing", "link": "https://example.org/1",
                    "source": "Example Aviation", "published": "2026-11-06T18:00:00+00:00"}


def test_parse_feed_rejects_html():
    with pytest.raises(ValueError):
        news.parse_feed(b"<html><body>Not a feed</body></html>", "https://example.org")


def test_select_headlines_filters_by_keyword_age_and_duplicates():
    items = news.parse_feed(fixture_bytes("news_rss.xml"), "https://x")
    items.append({**items[0], "id": "dup", "source": "Other"})
    picked = news.select_headlines(items, "notlandung, absturz", max_age_hours=24, limit=5, now=NOW)
    # "absturz" would match "Flugzeugabsturz", but that item is 4 days old; undated items are skipped.
    assert [i["title"][:10] for i in picked] == ["Notlandung"]
    assert len(news.select_headlines(items, "", 24, 5, now=NOW)) == 2  # empty filter = all recent
    assert len(news.select_headlines(items, "absturz", 24 * 7, 5, now=NOW)) == 1


def test_fetch_news_tolerates_one_broken_feed():
    def handler(method, url, **kw):
        if "broken" in url:
            return FakeResponse(404)
        return FakeResponse(200, content=fixture_bytes("news_rss.xml"))

    cfg = {"news_feeds": "https://broken.example/feed\nhttps://ok.example/feed", "news_keywords": "",
           "news_max_age_hours": 24 * 30, "news_max_items": 2}
    headlines, meta = news.fetch_news(FakeSession(handler), cfg)
    assert len(headlines) == 2 and meta["failed"] and meta["feeds"] == 2

    with pytest.raises(RuntimeError):
        news.fetch_news(FakeSession(lambda *a, **k: FakeResponse(500)), cfg)


# --- aircraft events ------------------------------------------------------------

def flight(**kw):
    base = {"id": "abc", "hex": "abc", "callsign": "TEST1", "registration": "", "type": "A20N", "type_name": "",
            "distance_km": 40.2, "bearing_deg": 44, "altitude_ft": 38000, "on_ground": False,
            "squawk": "1000", "emergency": False, "emergency_kind": None, "military": False}
    return {**base, **kw}


def test_aircraft_events():
    e = aircraft_event(flight(squawk="7700", emergency=True, emergency_kind="emergency"), True, True)
    assert e["kind"] == "emergency"
    assert e["text"] == "TEST1 (A20N): emergency, squawk 7700 · 40 km NE · 38,000 ft"
    assert aircraft_event(flight(type="A388"), True, True)["text"].startswith("Rare visitor: Airbus A380 TEST1")
    assert aircraft_event(flight(military=True, type_name="Lockheed C-130J Hercules"), True, True)["text"] \
        .startswith("Military: Lockheed C-130J Hercules")
    assert aircraft_event(flight(), True, True) is None
    assert aircraft_event(flight(type="A388"), True, False) is None
    assert compass(350) == "N" and compass(200) == "S"


def test_emergency_detection_ignores_lifeguard():
    from signage.providers.flights import emergency_of

    assert emergency_of({"squawk": "7600"}) == "radio failure"
    assert emergency_of({"emergency": "minfuel"}) == "minimum fuel"
    assert emergency_of({"emergency": "lifeguard", "squawk": "2000"}) is None


def test_aircraft_events_linger_then_expire():
    ev = AircraftEvents()
    ev.update([flight(type="A388")], True, True, now=1000)
    assert len(ev.items(now=1000)) == 1
    ev.update([], True, True, now=1200)  # aircraft gone, still shown for a while
    assert len(ev.items(now=1200)) == 1
    assert ev.items(now=1000 + 5 * 60 + 1) == []


# --- announcements ---------------------------------------------------------------

def test_announcement_validation():
    a = validate({"title": " Open day ", "end_date": "2026-11-20"})
    assert a["title"] == "Open day" and a["in_ticker"] and a["as_slide"]
    with pytest.raises(AnnouncementError):
        validate({"text": "no title, no image"})
    with pytest.raises(AnnouncementError):
        validate({"title": "x", "start_date": "2026-11-20", "end_date": "2026-11-01"})
    with pytest.raises(AnnouncementError):
        validate({"title": "x", "image": "../../etc/passwd"})
    with pytest.raises(AnnouncementError):
        validate({"title": "x", "in_ticker": False, "as_slide": False})
    with pytest.raises(AnnouncementError, match="ticker shows text only"):
        validate({"image": "0" * 32 + ".png", "in_ticker": True, "as_slide": False})
    assert validate({"image": "0" * 32 + ".png"})["as_slide"]  # poster without title: slide is fine
    assert validate({"title": "x"})["image_fit"] == "contain"
    assert validate({"title": "x", "image_fit": "cover"})["image_fit"] == "cover"
    with pytest.raises(AnnouncementError):
        validate({"title": "x", "image_fit": "stretch"})
    assert is_active(a, date(2026, 11, 20)) and not is_active(a, date(2026, 11, 21))
    assert not is_active({**a, "enabled": False}, date(2026, 11, 1))


def test_image_type_by_content():
    assert image_type(PNG[:16]) == "png"
    assert image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert image_type(b"<svg xmlns=") is None


def test_store_images(tmp_path):
    store = AnnouncementStore(tmp_path / "a.json", tmp_path / "media")
    name = store.save_image(io.BytesIO(PNG))
    assert (tmp_path / "media" / name).is_file()
    with pytest.raises(AnnouncementError):
        store.save_image(io.BytesIO(b"<svg onload=alert(1)>"))
    a = store.create({"title": "Poster", "image": name})
    with pytest.raises(AnnouncementError):
        store.create({"title": "Missing", "image": "0" * 32 + ".png"})
    # Reloads from disk
    assert AnnouncementStore(tmp_path / "a.json", tmp_path / "media").get(a["id"])["image"] == name


# --- API ---------------------------------------------------------------------------

def test_announcement_api_and_display(admin, app):
    r = admin.post("/api/admin/media", data={"file": (io.BytesIO(PNG), "poster.png")}, headers=H,
                   content_type="multipart/form-data")
    assert r.status_code == 200, r.json
    image = r.json["image"]
    assert admin.get(f"/media/{image}").status_code == 200

    r = admin.post("/api/admin/announcements", headers=H,
                   json={"title": "Aviation night", "text": "Thursday 18:00, room 1.01", "image": image})
    assert r.status_code == 200 and r.json["announcement"]["active"]
    ann_id = r.json["announcement"]["id"]

    d = admin.get("/api/display").json
    assert d["slides"]["items"][0]["image"] == f"/media/{image}"
    assert d["ticker"]["items"] == []  # ticker is off by default

    admin.put("/api/admin/config", headers=H, json={"config": {"ticker": {"enabled": True, "news_enabled": False}}})
    items = admin.get("/api/display").json["ticker"]["items"]
    assert items == [{"id": f"a:{ann_id}", "kind": "announcement",
                      "text": "Aviation night – Thursday 18:00, room 1.01"}]

    assert admin.post(f"/api/admin/announcements/{ann_id}/preview", headers=H).status_code == 200
    assert admin.get("/api/display").json["slides"]["preview"]["id"] == ann_id

    r = admin.put(f"/api/admin/announcements/{ann_id}", headers=H, json={"in_ticker": False})
    assert r.status_code == 200
    assert admin.get("/api/display").json["ticker"]["items"] == []

    assert admin.delete(f"/api/admin/announcements/{ann_id}", headers=H).status_code == 200
    assert admin.get("/api/display").json["slides"]["items"] == []


def test_announcement_api_requires_login_and_valid_names(client):
    assert client.get("/api/admin/announcements").status_code == 401
    r = client.post("/api/admin/media", data={"file": (io.BytesIO(PNG), "x.png")}, headers=H,
                    content_type="multipart/form-data")
    assert r.status_code == 401
    assert client.get("/media/..%2Fconfig.json").status_code == 404
    assert client.get("/media/config.json").status_code == 404


def test_upload_rejects_large_and_non_images(admin, monkeypatch):
    import signage.announcements as ann

    r = admin.post("/api/admin/media", data={"file": (io.BytesIO(b"GIF89a" + b"x" * 100), "a.gif")}, headers=H,
                   content_type="multipart/form-data")
    assert r.status_code == 200
    r = admin.post("/api/admin/media", data={"file": (io.BytesIO(b"%PDF-1.4"), "a.pdf")}, headers=H,
                   content_type="multipart/form-data")
    assert r.status_code == 422
    monkeypatch.setattr(ann, "MAX_IMAGE_BYTES", 1000)
    r = admin.post("/api/admin/media", data={"file": (io.BytesIO(PNG + b"x" * 5000), "big.png")}, headers=H,
                   content_type="multipart/form-data")
    assert r.status_code in (413, 422)


def test_ticker_config_validation(admin):
    r = admin.put("/api/admin/config", headers=H, json={"config": {"ticker": {"news_feeds": "ftp://x"}}})
    assert r.status_code == 422
    r = admin.put("/api/admin/config", headers=H,
                  json={"config": {"ticker": {"news_feeds": " https://a.example/feed \n\nhttps://b.example/rss "}}})
    assert r.json["config"]["ticker"]["news_feeds"] == "https://a.example/feed\nhttps://b.example/rss"


def test_display_ticker_with_aircraft_event(admin, app):
    svc = app.extensions["signage.services"]
    admin.put("/api/admin/config", headers=H, json={"config": {"ticker": {"enabled": True}}})
    svc.aircraft_events.update([flight(squawk="7700", emergency=True, emergency_kind="emergency")], True, True,
                               now=time.time())
    items = admin.get("/api/display").json["ticker"]["items"]
    assert items[0]["kind"] == "emergency"
    admin.put("/api/admin/config", headers=H, json={"config": {"ticker": {"emergencies": False}}})
    assert admin.get("/api/display").json["ticker"]["items"] == []
