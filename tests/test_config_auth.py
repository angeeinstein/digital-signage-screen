import hashlib
import json

import pytest

from signage.auth import CredentialStore, LoginThrottle
from signage.config import DEFAULTS, MASK, ConfigError, ConfigStore, admin_view, migrate_v1, public_view, validate


def test_validate_merges_and_checks_ranges():
    new = validate({"flights": {"radius_km": "50"}}, DEFAULTS)
    assert new["flights"]["radius_km"] == 50
    assert new["weather"] == DEFAULTS["weather"]
    with pytest.raises(ConfigError, match="flights.radius_km"):
        validate({"flights": {"radius_km": 9999}}, DEFAULTS)
    with pytest.raises(ConfigError, match="location.timezone"):
        validate({"location": {"timezone": "Mars/Base"}}, DEFAULTS)
    with pytest.raises(ConfigError):
        validate({"flights": {"providers": ["evil.example"]}}, DEFAULTS)


def test_secrets_hidden_and_masked():
    cfg = validate({"weather": {"openweathermap_api_key": "abc"}}, DEFAULTS)
    assert "openweathermap_api_key" not in json.dumps(public_view(cfg))
    assert admin_view(cfg)["weather"]["openweathermap_api_key"] == MASK


def test_store_keeps_secret_when_mask_sent(tmp_path):
    store = ConfigStore(tmp_path / "c.json")
    store.update({"weather": {"openweathermap_api_key": "secret1"}})
    rev = store.revision
    store.update({"weather": {"openweathermap_api_key": MASK, "refresh_seconds": 120}})
    assert store.get()["weather"]["openweathermap_api_key"] == "secret1"
    assert store.get()["weather"]["refresh_seconds"] == 120
    assert store.revision == rev + 1
    # persisted and reloadable
    assert ConfigStore(tmp_path / "c.json").get()["weather"]["refresh_seconds"] == 120


def test_corrupt_stored_value_falls_back_to_default(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"revision": 3, "data": {"flights": {"radius_km": "lots"}}}))
    assert ConfigStore(p).get()["flights"]["radius_km"] == DEFAULTS["flights"]["radius_km"]


def test_migrate_v1():
    old = {
        "location": {"lat": 47.07, "lon": 15.44, "name": "Graz"},
        "weather": {"api_key": "k", "enabled": True},
        "airlabs": {"enabled": True, "radius_km": 60, "api_provider": "airplaneslive"},
        "airlabs_route": {"api_key": "a", "enabled": True},
        "transport": {"enabled": True, "stop_id": "at:46:4227", "stop_name": "Alte Poststraße"},
        "timetable": {"enabled": True, "cohort": "LAV2023", "max_items": 5, "time_window_hours": 48},
    }
    new = validate(migrate_v1(old), DEFAULTS)
    assert new["weather"]["provider"] == "openweathermap"
    assert new["flights"]["radius_km"] == 60
    assert new["routes"]["airlabs_api_key"] == "a" and new["routes"]["airlabs_enabled"]
    assert new["transport"]["stop_id"] == "at:46:4227"
    assert new["timetable"]["cohorts"] == "LAV2023"


def test_legacy_sha256_password_is_upgraded(tmp_path):
    legacy = tmp_path / "admin_auth.json"
    legacy.write_text(json.dumps({"username": "admin", "password": hashlib.sha256(b"hunter22").hexdigest()}))
    store = CredentialStore(tmp_path / "auth.json", legacy_path=legacy)
    assert not store.verify("admin", "wrong")
    assert store.verify("admin", "hunter22")
    stored = json.loads((tmp_path / "auth.json").read_text())["password_hash"]
    assert len(stored) != 64  # no longer bare sha256
    assert store.verify("admin", "hunter22")


def test_password_change_rules(tmp_path):
    store = CredentialStore(tmp_path / "auth.json")
    assert store.must_change
    with pytest.raises(PermissionError):
        store.change("nope", "longenough1")
    with pytest.raises(ValueError):
        store.change("admin", "short")
    store.change("admin", "longenough1")
    assert store.verify("admin", "longenough1") and not store.must_change


def test_login_throttle():
    t = LoginThrottle(max_failures=3, window_seconds=60)
    for _ in range(3):
        assert t.retry_after("ip") == 0
        t.fail("ip")
    assert t.retry_after("ip") > 0
    t.reset("ip")
    assert t.retry_after("ip") == 0



def test_non_ascii_username(tmp_path):
    from signage.auth import CredentialStore

    store = CredentialStore(tmp_path / "auth.json")
    store.change("admin", "a-long-password", new_username="Jörg")
    assert store.verify("Jörg", "a-long-password")
    assert not store.verify("Jorg", "a-long-password")
    store.change("a-long-password", "another-password")  # change() calls verify() with the stored name
    assert store.verify("Jörg", "another-password")


def test_redact_secrets():
    from signage.util import redact_secrets

    msg = ("500 Server Error for url: https://api.openweathermap.org/data/2.5/weather?lat=47&lon=15"
           "&appid=abc123SECRET&units=metric")
    assert "abc123SECRET" not in redact_secrets(msg) and "appid=***" in redact_secrets(msg)
    assert redact_secrets("airlabs?api_key=XYZ&flight_icao=DLH1") == "airlabs?api_key=***&flight_icao=DLH1"
    assert redact_secrets("nothing secret here") == "nothing secret here"
