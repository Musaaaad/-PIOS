def test_health_and_readiness(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "pios-mvp-backend", "version": "1.4.0"}
    assert health.headers.get("x-trace-id")

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "reachable"
