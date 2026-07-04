from __future__ import annotations

from pathlib import Path


COMPOSE = Path("docker-compose.yml")


def test_frontend_build_service_targets_frontend_stage_only():
    src = COMPOSE.read_text(encoding="utf-8")
    frontend = src[src.index("  frontend:") : src.index("  app:")]
    assert "profiles:" in frontend
    assert "- build" in frontend
    assert "dockerfile: Dockerfile" in frontend
    assert "target: frontend-build" in frontend
    assert "image: flowhub-frontend-build:latest" in frontend
