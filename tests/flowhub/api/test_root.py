"""Tests for the FlowHub root route GET /."""

from fastapi.testclient import TestClient

import app.flowhub.app as flowhub_app

client = TestClient(flowhub_app.app)


class TestRootRoute:
    def test_root_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_content_type_html(self):
        response = client.get("/")
        assert "text/html" in response.headers["content-type"]

    def test_root_serves_spa_index_when_built(self, monkeypatch, tmp_path):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<!doctype html><div id=\"root\"></div>", encoding="utf-8")
        monkeypatch.setattr(flowhub_app, "_FRONTEND_DIST", dist)

        response = client.get("/")
        assert response.status_code == 200
        assert '<div id="root"></div>' in response.text

    def test_root_fallback_only_when_spa_index_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(flowhub_app, "_FRONTEND_DIST", tmp_path / "missing")

        response = client.get("/")
        assert response.status_code == 200
        assert "Frontend assets are not available" in response.text

    def test_root_does_not_expose_secrets(self):
        response = client.get("/")
        text = response.text.upper()
        for secret_key in (
            "JWT_SECRET",
            "REST_API_SECRET",
            "POSTGRES_PASSWORD",
            "NEXTCLOUD_PASSWORD",
            "WOOCOMMERCE_SECRET",
        ):
            assert secret_key not in text

    def test_health_still_works(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["env"] == "production"
        assert data["version"] == "1.0.0"
