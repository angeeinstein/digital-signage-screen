import os
import sys
import time
from pathlib import Path

import pytest
from conftest import FakeResponse, FakeSession, H

from signage.kiosk import KioskHub, send_heartbeat

LOCAL = {"REMOTE_ADDR": "127.0.0.1"}


@pytest.fixture(autouse=True)
def no_waiting(app):
    app.extensions["signage.kiosk"].poll_timeout = 0


# --- hub ---------------------------------------------------------------------------------

def test_commands_reach_agent_once_and_expire():
    hub = KioskHub()
    hub.poll_timeout = 0
    r = hub.agent_poll(0, {"version": "1"})
    assert r["commands"] == [] and hub.agent_online()
    hub.queue("screenshot")
    r = hub.agent_poll(r["seq"], {})
    assert r["commands"] == ["screenshot"]
    assert hub.agent_poll(r["seq"], {})["commands"] == []
    # stale commands (agent was away) are dropped
    hub.commands.put({"command": "reboot", "at": time.time() - 300})
    assert hub.agent_poll(r["seq"], {})["commands"] == []
    with pytest.raises(ValueError):
        hub.queue("rm -rf")


def test_heartbeat_reports_failure_when_display_is_frozen():
    hub = KioskHub()
    hub.started -= 600  # past the start-up grace period
    calls = []
    session = FakeSession(lambda m, url, **kw: calls.append(url) or FakeResponse(200))
    cfg = {"heartbeat_url": "https://hc-ping.com/abc", "require_display": True}
    assert send_heartbeat(session, cfg, hub) == {"healthy": False}
    hub.display_seen = time.time()
    assert send_heartbeat(session, cfg, hub) == {"healthy": True}
    assert calls == ["https://hc-ping.com/abc/fail", "https://hc-ping.com/abc"]
    hub.display_seen = 0
    send_heartbeat(session, {**cfg, "require_display": False}, hub)
    assert calls[-1] == "https://hc-ping.com/abc"
    with pytest.raises(RuntimeError):
        send_heartbeat(FakeSession(lambda *a, **k: FakeResponse(404)), cfg, hub)


# --- HTTP ----------------------------------------------------------------------------------

def test_display_poll_marks_screen_alive_only_locally(client, app):
    hub = app.extensions["signage.kiosk"]
    client.get("/api/display", headers={"Cf-Connecting-Ip": "1.2.3.4"})
    assert hub.display_seen == 0
    client.get("/api/display")
    assert hub.display_alive()


def test_reload_changes_build_id(admin):
    build = admin.get("/api/display").json["build"]
    assert admin.post("/api/admin/kiosk/reload", headers=H).status_code == 200
    assert admin.get("/api/display").json["build"] != build


def test_agent_endpoints_are_local_only(client):
    assert client.get("/api/kiosk/agent/commands", headers={"Cf-Ray": "x"}).status_code == 403
    assert client.get("/api/kiosk/agent/commands", environ_base={"REMOTE_ADDR": "10.0.0.7"}).status_code == 403
    assert client.post("/api/kiosk/agent/screenshot", headers={**H, "X-Forwarded-For": "8.8.8.8"},
                       data=b"x").status_code == 403


def test_admin_commands_and_screenshot(admin):
    # Without a running agent, commands are refused with a helpful message.
    r = admin.post("/api/admin/kiosk/restart-browser", headers=H)
    assert r.status_code == 409 and "helper" in r.json["error"]
    assert admin.get("/api/admin/kiosk").json["agent_online"] is False

    # Agent connects ...
    seq = admin.get("/api/kiosk/agent/commands?since=0&info_version=1").json["seq"]
    assert admin.get("/api/admin/kiosk").json["agent"] == {"version": "1"}
    assert admin.post("/api/admin/kiosk/screenshot", headers=H).status_code == 200
    assert admin.get("/api/admin/kiosk").json["screenshot_pending"] is True
    r = admin.get(f"/api/kiosk/agent/commands?since={seq}").json
    assert r["commands"] == ["screenshot"]
    # ... and uploads the picture
    assert admin.post("/api/kiosk/agent/screenshot", headers={**H, "Content-Type": "image/jpeg"},
                      data=b"\xff\xd8\xffjpeg").status_code == 200
    shot = admin.get("/api/admin/kiosk/screenshot")
    assert shot.status_code == 200 and shot.data.startswith(b"\xff\xd8") and shot.mimetype == "image/jpeg"
    assert admin.get("/api/admin/kiosk").json["screenshot_pending"] is False
    assert admin.post("/api/admin/kiosk/format-disk", headers=H).status_code == 404

    # A failed screenshot is reported back to the admin page.
    admin.post("/api/admin/kiosk/screenshot", headers=H)
    admin.post("/api/kiosk/agent/screenshot-error", headers=H, json={"error": "grim failed: no output"})
    st = admin.get("/api/admin/kiosk").json
    assert st["screenshot_error"] == "grim failed: no output" and st["screenshot_pending"] is False


def test_admin_kiosk_requires_login(client):
    assert client.get("/api/admin/kiosk").status_code == 401
    assert client.post("/api/admin/kiosk/reboot", headers=H).status_code == 401
    assert client.get("/api/admin/kiosk/screenshot").status_code == 401


def test_heartbeat_url_is_secret(admin):
    admin.put("/api/admin/config", headers=H,
              json={"config": {"monitoring": {"heartbeat_url": "https://hc-ping.com/secret-uuid"}}})
    assert "secret-uuid" not in admin.get("/api/admin/config").get_data(as_text=True)
    assert "secret-uuid" not in admin.get("/api/display").get_data(as_text=True)
    assert admin.get("/api/admin/kiosk").json["heartbeat"]["status"] in ("pending", "ok", "error")


# --- the agent itself (Linux only: it uses fcntl and process groups) --------------------------

linux_only = pytest.mark.skipif(os.name != "posix", reason="kiosk agent runs on Linux")


@pytest.fixture
def fake_browser(tmp_path, monkeypatch):
    """A 'chromium' that just sleeps, first on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "chromium"
    script.write_text("#!/bin/sh\nexec sleep 300\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "kiosk"))
    if os.name != "posix":
        import types

        sys.modules.setdefault("fcntl", types.ModuleType("fcntl"))  # only used for the lock file
    import agent

    yield agent
    sys.path.pop(0)


@linux_only
def test_agent_starts_and_restarts_browser(fake_browser, tmp_path):
    agent = fake_browser
    b = agent.Browser("http://localhost:8080", tmp_path / "profile")
    b.ensure_running()
    first = b.proc
    assert first.poll() is None
    b.restart("test")
    assert first.poll() is not None
    b.ensure_running()  # requested restart: no crash back-off
    assert b.proc is not first and b.proc.poll() is None and b.crashes == 0
    b.restart("cleanup")


def test_agent_runs_commands_and_detects_frozen_page(fake_browser, tmp_path, monkeypatch):
    agent = fake_browser
    b = agent.Browser("http://localhost:8080", tmp_path / "profile")
    a = agent.Agent("http://localhost:8080", b)
    restarts, reboots = [], []
    monkeypatch.setattr(b, "restart", lambda reason: restarts.append(reason))
    monkeypatch.setattr(agent, "reboot", lambda: reboots.append(1))
    monkeypatch.setattr(b, "uptime", lambda: 1000)
    replies = iter([
        {"commands": ["restart-browser", "reboot"], "seq": 2, "display_age": 5},
        {"commands": [], "seq": 2, "display_age": 500},
    ])
    monkeypatch.setattr(a, "request", lambda *args, **kw: next(replies))
    a.poll_once()
    assert restarts == ["requested from the admin page"] and reboots == [1] and a.since == 2
    a.poll_once()
    assert "hasn't updated" in restarts[-1]


def test_agent_marks_clean_exit(fake_browser, tmp_path):
    agent = fake_browser
    prefs = tmp_path / "profile" / "Default" / "Preferences"
    prefs.parent.mkdir(parents=True)
    prefs.write_text('{"profile": {"exit_type": "Crashed", "exited_cleanly": false}}')
    agent.mark_clean_exit(tmp_path / "profile")
    assert '"exit_type": "Normal"' in prefs.read_text()


def test_heartbeat_no_false_alarm_right_after_boot():
    hub = KioskHub()  # just started, display not seen yet
    calls = []
    session = FakeSession(lambda m, url, **kw: calls.append(url) or FakeResponse(200))
    cfg = {"heartbeat_url": "https://hc-ping.com/abc", "require_display": True}
    assert send_heartbeat(session, cfg, hub)["healthy"]
    assert calls == ["https://hc-ping.com/abc"]
