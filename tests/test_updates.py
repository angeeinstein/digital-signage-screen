import pytest
from conftest import H

from signage.updates import Updater


@pytest.fixture
def updater(tmp_path):
    unit = tmp_path / "update.path"
    unit.write_text("[Path]")
    return Updater(tmp_path / "data", log_path=tmp_path / "update.log", unit_path=unit)


def test_status_idle_running_and_result(updater, tmp_path):
    (tmp_path / "data").mkdir()
    assert updater.status()["state"] == "idle" and updater.status()["log"] == ""

    updater.request()
    assert (tmp_path / "data" / "update-request").exists()
    assert updater.status()["state"] == "starting"
    with pytest.raises(RuntimeError, match="already running"):
        updater.request()

    # the service removes the request and starts logging (with installer colours)
    (tmp_path / "data" / "update-request").unlink()
    updater.log_path.write_text("Update started\n\x1b[0;32m[ OK ]\x1b[0m Python packages installed\n")
    st = updater.status()
    assert st["state"] == "running" and "[ OK ] Python packages installed" in st["log"] and "\x1b" not in st["log"]

    updater.log_path.write_text(updater.log_path.read_text() + "done\n@@RESULT 0 1762480000\n")
    st = updater.status()
    assert st["state"] == "idle" and st["result"] == {"code": 0, "finished": 1762480000}
    assert "@@RESULT" not in st["log"]


def test_request_needs_update_service(tmp_path):
    u = Updater(tmp_path, log_path=tmp_path / "log", unit_path=tmp_path / "missing.path")
    assert u.status()["supported"] is False
    with pytest.raises(RuntimeError, match="update service"):
        u.request()


def test_update_api(admin, app, tmp_path, monkeypatch):
    unit = tmp_path / "update.path"
    unit.write_text("[Path]")
    app.extensions["signage.updater"] = Updater(tmp_path, log_path=tmp_path / "update.log", unit_path=unit)
    st = admin.get("/api/admin/update").json
    assert st["supported"] and st["state"] == "idle" and "version" in st and "current" in st
    assert admin.post("/api/admin/update/start", headers=H).status_code == 200
    assert admin.post("/api/admin/update/start", headers=H).status_code == 409

    import signage.updates as updates

    monkeypatch.setattr(updates, "check_remote", lambda: {"remote": "abc", "remote_short": "abc", "available": True})
    assert admin.post("/api/admin/update/check", headers=H).json["available"] is True

    def offline():
        raise RuntimeError("could not resolve host")

    monkeypatch.setattr(updates, "check_remote", offline)
    r = admin.post("/api/admin/update/check", headers=H)
    assert r.status_code == 502 and "could not resolve host" in r.json["error"]


def test_update_api_requires_login(client):
    assert client.get("/api/admin/update").status_code == 401
    assert client.post("/api/admin/update/start", headers=H).status_code == 401
