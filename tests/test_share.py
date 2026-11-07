import threading

import pytest
from conftest import H

from signage.share import RelayBuffer, ShareError, ShareHub, is_local_screen

LOCAL = {"REMOTE_ADDR": "127.0.0.1"}


# --- who counts as "the screen" ---------------------------------------------------

@pytest.mark.parametrize("environ, headers, expected", [
    (LOCAL, {}, True),                                              # kiosk -> gunicorn directly
    (LOCAL, {"X-Forwarded-For": "127.0.0.1"}, True),                # kiosk -> nginx -> gunicorn
    ({"REMOTE_ADDR": "::1"}, {}, True),
    ({"REMOTE_ADDR": "192.168.1.20"}, {}, False),                    # LAN client
    (LOCAL, {"X-Forwarded-For": "192.168.1.20"}, False),            # LAN client via nginx
    (LOCAL, {"X-Forwarded-For": "1.2.3.4, 127.0.0.1"}, False),
    (LOCAL, {"Cf-Connecting-Ip": "1.2.3.4"}, False),                # through the tunnel
    (LOCAL, {"Cf-Ray": "abc"}, False),
    ({"REMOTE_ADDR": "127.0.0.1", "werkzeug.proxy_fix.orig": {"REMOTE_ADDR": "10.0.0.5"}}, {}, False),
])
def test_is_local_screen(environ, headers, expected):
    assert is_local_screen(environ, headers) is expected


# --- hub ---------------------------------------------------------------------------

def online_hub():
    hub = ShareHub()
    hub.poll_timeout = 0
    hub.screen_seen = 10**12  # far future: screen counts as online
    return hub


def test_code_flow_and_replacement():
    hub = online_hub()
    r = hub.request("Anna", "1.1.1.1", now=1000)
    state = hub.state()
    code = state["pending"]["code"]
    assert len(code) == 4 and state["pending"]["name"] == "Anna"

    with pytest.raises(ShareError, match="Enter the code"):
        hub.sender_signal(r["token"], {"type": "offer", "sdp": "x"}, now=1001)
    with pytest.raises(ShareError, match="Wrong code"):
        hub.verify(r["token"], "xxxx", now=1001)
    hub.verify(r["token"], code, now=1002)
    assert hub.state()["active"]["name"] == "Anna" and hub.state()["pending"] is None

    hub.sender_signal(r["token"], {"type": "offer", "sdp": "x"}, now=1003)
    events, _ = hub.screen.get(0, 0)
    assert any(e.get("type") == "offer" for e in events)

    # Someone else takes over with a new code; Anna is told.
    r2 = hub.request("Ben", "2.2.2.2", now=1010)
    hub.verify(r2["token"], hub.state()["pending"]["code"], now=1011)
    assert hub.state()["active"]["name"] == "Ben"
    assert r["token"] not in hub._senders


def test_wrong_code_limit():
    hub = online_hub()
    r = hub.request("", "1.1.1.1", now=1000)
    for _ in range(4):
        with pytest.raises(ShareError):
            hub.verify(r["token"], "nope", now=1001)
    with pytest.raises(ShareError, match="too many"):
        hub.verify(r["token"], "nope", now=1001)
    with pytest.raises(ShareError) as e:
        hub.verify(r["token"], "0000", now=1001)
    assert e.value.status == 410


def test_code_expires_and_rate_limit():
    hub = online_hub()
    r = hub.request("", "1.1.1.1", now=1000)
    hub.request("", "9.9.9.9", now=1000 + 61)  # triggers cleanup
    assert r["token"] not in hub._senders
    for i in range(4):
        hub.request("", "5.5.5.5", now=2000 + i)
    with pytest.raises(ShareError) as e:
        hub.request("", "5.5.5.5", now=2005)
    assert e.value.status == 429


def test_request_needs_screen():
    hub = ShareHub()
    with pytest.raises(ShareError) as e:
        hub.request("", "1.1.1.1")
    assert e.value.status == 503


def test_screen_messages_only_reach_active_sender():
    hub = online_hub()
    r = hub.request("", "1.1.1.1", now=1000)
    sid = hub.verify(r["token"], hub.state()["pending"]["code"], now=1001)["id"]
    hub.screen_signal("someone-else", {"type": "answer", "sdp": "y"})
    hub.screen_signal(sid, {"type": "answer", "sdp": "y"})
    events, _ = hub._senders[r["token"]].mailbox.get(0, 0)
    assert [e["type"] for e in events] == ["deadline", "answer"]
    with pytest.raises(ShareError):
        hub.screen_signal(sid, {"type": "evil"})


def test_relay_buffer_order_gap_and_longpoll():
    buf = RelayBuffer()
    buf.reset("s1", "video/webm")
    with pytest.raises(ShareError):
        buf.put("s1", 1, b"x")  # must start at 0
    buf.put("s1", 0, b"init")
    buf.put("s1", 1, b"a")
    assert buf.get("s1", -1, 0) == ("chunk", 1, b"inita")
    assert buf.get("s1", 1, 0)[0] == "wait"
    assert buf.get("other", 1, 0)[0] == "gone"
    for i in range(2, 300):
        buf.put("s1", i, b"z")
    assert buf.get("s1", 0, 0)[0] == "gap"

    result = {}
    t = threading.Thread(target=lambda: result.update(r=buf.get("s1", 299, 5)))
    t.start()
    buf.put("s1", 300, b"late")
    t.join(2)
    assert result["r"] == ("chunk", 300, b"late")


# --- HTTP ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_waiting(app):
    app.extensions["signage.share"].poll_timeout = 0


def enable(admin, **kw):
    r = admin.put("/api/admin/config", headers=H, json={"config": {"share": {"enabled": True, **kw}}})
    assert r.status_code == 200


def test_share_disabled_by_default(client):
    assert client.get("/api/share/info").json["enabled"] is False
    assert client.post("/api/share/request", headers=H, json={}).status_code == 404


def test_share_http_flow(admin, app):
    enable(admin)
    # The screen (local request) polls; that marks it online.
    r = admin.get("/api/share/screen/events?since=0")
    assert r.status_code == 200
    seq = r.json["seq"]

    r = admin.post("/api/share/request", headers=H, json={"name": "Anna"})
    assert r.status_code == 200
    token = r.json["token"]
    ev = admin.get(f"/api/share/screen/events?since={seq}").json
    code = ev["state"]["pending"]["code"]

    assert admin.post("/api/share/verify", headers=H, json={"token": token, "code": "x"}).status_code == 403
    r = admin.post("/api/share/verify", headers=H, json={"token": token, "code": code})
    assert r.status_code == 200 and r.json["relay"] is True
    sender_id = r.json["id"]

    assert admin.post("/api/share/signal", headers=H,
                      json={"token": token, "message": {"type": "relay", "session": "abc", "mime": "video/webm"}}
                      ).status_code == 200
    assert admin.post(f"/api/share/relay?token={token}&session=abc&seq=0", headers=H, data=b"init").status_code == 200
    r = admin.get("/api/share/screen/relay?session=abc&after=-1")
    assert r.status_code == 200 and r.data == b"init" and r.headers["X-Seq"] == "0"

    assert admin.post("/api/share/screen/signal", headers=H,
                      json={"to": sender_id, "message": {"type": "resync"}}).status_code == 200
    ev = admin.get(f"/api/share/events?token={token}&since=0").json
    assert ev["events"][-1]["type"] == "resync"

    st = admin.get("/api/admin/share").json
    assert st["state"]["active"]["name"] == "Anna" and st["state"]["active"]["mode"] == "relay"
    assert admin.post("/api/admin/share/stop", headers=H).status_code == 200
    assert admin.get("/api/admin/share").json["state"]["active"] is None


def test_screen_endpoints_reject_remote_and_tunnel(admin):
    enable(admin)
    assert admin.get("/api/share/screen/events", headers={"Cf-Connecting-Ip": "1.2.3.4"}).status_code == 403
    assert admin.get("/api/share/screen/events", environ_base={"REMOTE_ADDR": "192.168.0.9"}).status_code == 403


def test_relay_can_be_turned_off(admin):
    enable(admin, relay_enabled=False)
    admin.get("/api/share/screen/events?since=999999")  # mark the screen online
    token = admin.post("/api/share/request", headers=H, json={}).json["token"]
    code = admin.get("/api/admin/share").json["state"]["pending"]["code"]
    assert admin.post("/api/share/verify", headers=H, json={"token": token, "code": code}).json["relay"] is False
    r = admin.post("/api/share/signal", headers=H, json={"token": token, "message": {"type": "relay", "session": "a"}})
    assert r.status_code == 403


def test_public_url_detected_from_cloudflare(admin, app, tmp_path):
    assert admin.get("/api/admin/share").json["public_url"] == ""
    admin.get("/api/health", headers={"Cf-Connecting-Ip": "1.2.3.4", "Host": "projektraum.example.at"})
    assert admin.get("/api/admin/share").json["public_url"] == "https://projektraum.example.at"
    assert (tmp_path / "public_url.json").exists()
    admin.put("/api/admin/config", headers=H, json={"config": {"share": {"public_url": "https://other.example/"}}})
    assert admin.get("/api/admin/share").json["public_url"] == "https://other.example"


def test_access_email_used_as_name(admin):
    enable(admin)
    admin.get("/api/share/screen/events?since=999999")
    admin.post("/api/share/request", headers={**H, "Cf-Access-Authenticated-User-Email": "anna@fh-joanneum.at"},
               json={})
    assert admin.get("/api/admin/share").json["state"]["pending"]["name"] == "anna@fh-joanneum.at"


def test_login_throttle_uses_cloudflare_client(client):
    for _ in range(5):
        client.post("/api/auth/login", headers={**H, "Cf-Connecting-Ip": "6.6.6.6"},
                    json={"username": "admin", "password": "wrong"})
    blocked = client.post("/api/auth/login", headers={**H, "Cf-Connecting-Ip": "6.6.6.6"},
                          json={"username": "admin", "password": "admin"})
    assert blocked.status_code == 429
    other = client.post("/api/auth/login", headers={**H, "Cf-Connecting-Ip": "7.7.7.7"},
                        json={"username": "admin", "password": "admin"})
    assert other.status_code == 200


# --- time limit -----------------------------------------------------------------------

def start_sharing(hub, now=1000, limit_s=3600):
    r = hub.request("Anna", "1.1.1.1", now=now)
    hub.verify(r["token"], hub.state()["pending"]["code"], now=now, limit_s=limit_s)
    return r["token"]


def test_sharing_ends_at_time_limit():
    hub = online_hub()
    token = start_sharing(hub, now=1000, limit_s=3600)
    assert hub.state()["active"]["ends_at"] == 4600
    msg = hub._senders[token].mailbox.get(0, 0)[0][0]
    assert msg == {"type": "deadline", "remaining": 3600, "can_extend": True, "extend_minutes": 30, "warning_s": 300}
    # Keep the sender "seen" so only the limit can end it.
    hub._senders[token].last_seen = 4600
    hub._cleanup(4599)
    assert hub.state()["active"] is not None
    hub._cleanup(4600)
    assert hub.state()["active"] is None


def test_extend_only_once_by_half():
    hub = online_hub()
    token = start_sharing(hub, now=1000, limit_s=3600)
    msg = hub.extend(token, now=4400)
    assert hub.state()["active"]["ends_at"] == 4600 + 1800
    assert msg["can_extend"] is False and msg["remaining"] == 2000
    with pytest.raises(ShareError, match="only be extended once"):
        hub.extend(token, now=6000)


def test_no_limit():
    hub = online_hub()
    token = start_sharing(hub, limit_s=0)
    assert hub.state()["active"]["ends_at"] is None
    with pytest.raises(ShareError):
        hub.extend(token)


def test_extend_http(admin):
    enable(admin, max_minutes=60)
    admin.get("/api/share/screen/events?since=999999")
    token = admin.post("/api/share/request", headers=H, json={}).json["token"]
    code = admin.get("/api/admin/share").json["state"]["pending"]["code"]
    admin.post("/api/share/verify", headers=H, json={"token": token, "code": code})
    r = admin.post("/api/share/extend", headers=H, json={"token": token})
    assert r.status_code == 200 and r.json["can_extend"] is False
    assert admin.post("/api/share/extend", headers=H, json={"token": token}).status_code == 409
    assert admin.put("/api/admin/config", headers=H,
                     json={"config": {"share": {"max_minutes": 9999}}}).status_code == 422
