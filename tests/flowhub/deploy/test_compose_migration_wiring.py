"""Deployment wiring guard: the Compose stack must run FlowHub migrations
before the app and order-sync-runner start.

Regression context: the order-sync-runner crashed in staging with
`relation "ip_connector_events" does not exist` because docker-compose.yml
started the app and runner directly (uvicorn / `python -m app.flowhub.orders.runner`)
without ever applying the FlowHub Alembic head. The active app does not
auto-migrate on startup, so the schema is only created by an explicit
`alembic -c alembic_flowhub.ini upgrade head`. These tests fail if that
migration step is dropped, if it stops using the canonical alembic_flowhub
config, or if the app/runner no longer wait for it to complete.

The canonical database env var is FLOWHUB_DATABASE_URL (read by
app/flowhub/database.py and alembic_flowhub/env.py). DATABASE_URL belongs only
to the legacy app/config.py path and must not become the migration source.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
MIGRATE_SERVICE = "flowhub-migrate"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def _command_tokens(service: dict) -> list[str]:
    command = service.get("command", [])
    if isinstance(command, str):
        return command.split()
    return [str(token) for token in command]


def _depends_on(service: dict) -> dict:
    """Normalize depends_on to {service: condition} for the long form used here."""
    raw = service.get("depends_on", {})
    if isinstance(raw, list):
        return {name: None for name in raw}
    return {name: (spec or {}).get("condition") for name, spec in raw.items()}


def test_compose_defines_a_flowhub_migration_service():
    services = _compose()["services"]
    assert MIGRATE_SERVICE in services, (
        "docker-compose.yml must define a one-shot migration service so the "
        "schema exists before the app and order-sync-runner start."
    )
    tokens = _command_tokens(services[MIGRATE_SERVICE])
    # Must run the canonical FlowHub alembic config, not the legacy root one.
    assert tokens[:1] == ["alembic"], tokens
    assert "-c" in tokens and "alembic_flowhub.ini" in tokens, tokens
    assert tokens[-2:] == ["upgrade", "head"], tokens
    # Guard against accidentally pointing at the legacy alembic.ini.
    assert "alembic.ini" not in tokens, (
        "Migration must use alembic_flowhub.ini (FLOWHUB_DATABASE_URL), not the "
        "legacy alembic.ini which requires DATABASE_URL."
    )


def test_migration_service_waits_for_postgres_health():
    migrate = _compose()["services"][MIGRATE_SERVICE]
    assert _depends_on(migrate).get("postgres") == "service_healthy"
    # A one-shot job must not be restarted on successful exit.
    assert str(migrate.get("restart", "no")) == "no"


def test_app_and_runner_wait_for_migration_to_complete():
    services = _compose()["services"]
    for name in ("app", "order-sync-runner"):
        deps = _depends_on(services[name])
        assert deps.get(MIGRATE_SERVICE) == "service_completed_successfully", (
            f"{name} must wait for {MIGRATE_SERVICE} to finish so it never runs "
            "against an unmigrated database (e.g. missing ip_connector_events)."
        )
        # Postgres dependency must remain intact.
        assert deps.get("postgres") == "service_healthy"


def test_alembic_flowhub_env_uses_canonical_database_url():
    env_text = (REPO_ROOT / "alembic_flowhub" / "env.py").read_text(encoding="utf-8")
    assert "FLOWHUB_DATABASE_URL" in env_text, (
        "The active migration env must source the URL from FLOWHUB_DATABASE_URL."
    )
