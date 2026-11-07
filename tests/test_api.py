import json

from conftest import H


def test_display_is_public_and_has_no_secrets(client, app):
    app.extensions["signage.config"].update({"weather": {"openweathermap_api_key": "topsecret"},
                                             "routes": {"airlabs_api_key": "alsosecret"},
                                             "monitoring": {"heartbeat_url": "https://hc-ping.com/secret-uuid"}})
    r = client.get("/api/display")
    assert r.status_code == 200
    body = r.get_json()
    assert set(body["sources"]) == {"flights", "weather", "transport", "timetable"}
    assert "topsecret" not in r.get_data(as_text=True) and "alsosecret" not in r.get_data(as_text=True)
    assert "secret-uuid" not in r.get_data(as_text=True)
    assert body["revision"] >= 2


def test_health(client):
    r = client.get("/api/health").get_json()
    assert r["ok"] and r["sources"]["weather"]["status"] == "pending"


def test_admin_requires_login(client):
    for method, url in [("get", "/api/admin/config"), ("put", "/api/admin/config"), ("get", "/api/admin/stops"),
                        ("get", "/api/admin/routes"), ("post", "/api/admin/test/weather")]:
        r = getattr(client, method)(url, headers=H, json={})
        assert r.status_code == 401, url


def test_csrf_header_required(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 403


def test_login_flow_and_throttle(client):
    assert client.get("/api/auth/session").get_json()["logged_in"] is False
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "x"}, headers=H).status_code == 401
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"}, headers=H)
    assert r.status_code == 429


def test_login_bad_body_does_not_crash(client):
    r = client.post("/api/auth/login", data="not json", headers={**H, "Content-Type": "text/plain"})
    assert r.status_code == 401


def test_config_roundtrip_masks_secret(admin):
    r = admin.put("/api/admin/config", json={"config": {"weather": {"openweathermap_api_key": "k1"}}}, headers=H)
    assert r.status_code == 200
    cfg = admin.get("/api/admin/config").get_json()["config"]
    assert cfg["weather"]["openweathermap_api_key"] == "••••••••"
    cfg["flights"]["radius_km"] = 40
    admin.put("/api/admin/config", json={"config": cfg}, headers=H)
    store = admin.application.extensions["signage.config"]
    assert store.get()["weather"]["openweathermap_api_key"] == "k1"
    assert store.get()["flights"]["radius_km"] == 40


def test_config_validation_error(admin):
    r = admin.put("/api/admin/config", json={"config": {"flights": {"radius_km": -1}}}, headers=H)
    assert r.status_code == 422 and "flights.radius_km" in r.get_json()["error"]


def test_password_change(admin):
    r = admin.post("/api/auth/password", json={"current_password": "admin", "new_password": "short"}, headers=H)
    assert r.status_code == 400
    r = admin.post("/api/auth/password", json={"current_password": "admin", "new_password": "correct horse"},
                   headers=H)
    assert r.status_code == 200
    admin.post("/api/auth/logout", headers=H)
    r = admin.post("/api/auth/login", json={"username": "admin", "password": "correct horse"}, headers=H)
    assert r.status_code == 200 and r.get_json()["must_change"] is False


def test_manual_routes(admin):
    r = admin.post("/api/admin/routes", json={"callsign": "aua123", "origin": "vie", "destination": "LOWG"},
                   headers=H)
    assert r.status_code == 200
    routes = admin.get("/api/admin/routes").get_json()["routes"]
    assert routes[0]["callsign"] == "AUA123" and routes[0]["destination"]["icao"] == "LOWG"
    assert admin.post("/api/admin/routes", json={"callsign": "X", "origin": "toolong", "destination": "A"},
                      headers=H).status_code == 400
    assert admin.delete("/api/admin/routes/AUA123", headers=H).status_code == 200
    assert admin.get("/api/admin/routes").get_json()["routes"] == []


def test_legacy_files_are_migrated(tmp_path, monkeypatch):
    import signage
    from signage import create_app

    legacy_dir = tmp_path / "data" / "legacy"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "dashboard_config.json").write_text(json.dumps(
        {"location": {"lat": 47.07, "lon": 15.44, "name": "Graz"}, "transport": {"stop_id": "at:46:4227"}}))
    monkeypatch.setattr(signage, "BASE_DIR", tmp_path / "nowhere")
    app = create_app(data_dir=tmp_path / "data", start_pollers=False)
    cfg = app.extensions["signage.config"].get()
    assert cfg["location"]["name"] == "Graz" and cfg["transport"]["stop_id"] == "at:46:4227"


def test_spa_routes_without_build(client, monkeypatch, tmp_path):
    import signage

    monkeypatch.setattr(signage, "FRONTEND_DIST", tmp_path / "missing")
    # FRONTEND_DIST is read at request time through the module global
    r = client.get("/")
    assert r.status_code in (200, 503)
