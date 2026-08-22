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
    assert 'VITE_HANDSONTABLE_LICENSE_KEY: "${VITE_HANDSONTABLE_LICENSE_KEY:-}"' in frontend
    assert "image: flowhub-frontend-build:latest" in frontend

    app = src[src.index("  app:") : src.index("  order-sync-runner:")]
    assert 'VITE_HANDSONTABLE_LICENSE_KEY: "${VITE_HANDSONTABLE_LICENSE_KEY:-}"' in app


def test_dockerfile_exposes_license_only_to_frontend_build_stage():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    frontend, runtime = dockerfile.split("# -- Stage 2: Python application", maxsplit=1)
    assert "ARG VITE_HANDSONTABLE_LICENSE_KEY" in frontend
    assert "VITE_HANDSONTABLE_LICENSE_KEY" not in runtime


def test_frontend_docker_stage_includes_raw_channel_document_imports():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    frontend, _runtime = dockerfile.split("# -- Stage 2: Python application", maxsplit=1)

    # ChannelDocs.tsx imports the repository contracts through
    # ../../../docs/reference/channel-api/*.md?raw.  The Docker stage runs from
    # /frontend, so the build context must create that sibling directory.
    assert "COPY docs/reference/channel-api/*.md /docs/reference/channel-api/" in frontend
