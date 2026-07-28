"""Create an isolated local FlowHub runtime without committing credentials."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_DIR = ROOT / ".local" / "dev"


def _write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        # Windows ACLs remain authoritative when POSIX mode bits are unavailable.
        pass


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _ensure_env(state_dir: Path) -> tuple[Path, dict[str, str]]:
    env_path = state_dir / "backend.env"
    if not env_path.exists():
        database_path = (state_dir / "flowhub.db").resolve().as_posix()
        values = {
            "FLOWHUB_DATABASE_URL": f"sqlite:///{database_path}",
            "FLOWHUB_ENV": "dev",
            "FLOWHUB_JWT_SECRET": secrets.token_urlsafe(64),
            "FLOWHUB_VERSION": "local-dev",
            "FLOWHUB_TIMEZONE": "UTC",
            "FLOWHUB_ORDER_SYNC_ENABLED": "false",
            "FLOWHUB_LOG_LEVEL": "DEBUG",
        }
        content = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
        _write_private(env_path, content)
    return env_path, _read_env(env_path)


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(ROOT / "alembic_flowhub.ini"))
    command.upgrade(config, "head")


def _ensure_owner(state_dir: Path) -> Path:
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.repository import create_user, get_user_by_username
    from app.flowhub.database import _get_engine
    from app.flowhub.setup.service import AppConfigService

    credentials_path = state_dir / "credentials.json"
    engine = _get_engine(os.environ["FLOWHUB_DATABASE_URL"])
    session = sessionmaker(bind=engine)()
    try:
        username = "local_owner"
        user = get_user_by_username(session, username)
        if user is None:
            password = secrets.token_urlsafe(24)
            create_user(
                session,
                username=username,
                hashed_password=hash_password(password),
                role="owner",
            )
            credentials = {
                "username": username,
                "password": password,
                "baseUrl": "http://127.0.0.1:5173",
            }
            _write_private(credentials_path, json.dumps(credentials, indent=2) + "\n")
        elif not credentials_path.exists():
            raise RuntimeError(
                "The local Owner exists but .local/dev/credentials.json is missing. "
                "Delete .local/dev/flowhub.db and rerun the bootstrap to regenerate both."
            )

        config = AppConfigService(session)
        if not config.is_setup_completed():
            config.mark_setup_complete(updated_by="local_dev_bootstrap")
    finally:
        session.close()
    return credentials_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    args = parser.parse_args()

    state_dir = args.state_dir.resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    env_path, values = _ensure_env(state_dir)
    os.environ.update(values)

    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    _run_migrations()
    credentials_path = _ensure_owner(state_dir)

    print(f"Local environment: {env_path}")
    print(f"Local credentials: {credentials_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
