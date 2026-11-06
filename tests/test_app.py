from __future__ import annotations

from fastapi.testclient import TestClient

from kite_starter.app import create_app


def test_health():
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
