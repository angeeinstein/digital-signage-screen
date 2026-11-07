import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_json(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_bytes(name):
    return (FIXTURES / name).read_bytes()


class FakeResponse:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code = status
        self._body = body
        self.content = content

    def json(self):
        return self._body

    def iter_content(self, chunk_size=1):
        data = self.content
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]

    def close(self):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    """Routes GET/POST calls to a handler: handler(method, url, **kw) -> FakeResponse."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self.handler("GET", url, **kw)

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self.handler("POST", url, **kw)


@pytest.fixture
def app(tmp_path):
    from signage import create_app

    app = create_app(data_dir=tmp_path, start_pollers=False)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


H = {"X-Requested-With": "signage"}


@pytest.fixture
def admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin"}, headers=H)
    assert r.status_code == 200
    return client
