#!/usr/bin/env bash
# WooPrice Beta — .env file generation (B4 Installer Foundation)
#
# Source from install.sh. Call generate_env_file ENV_PATH.
# Writes all BETA_* variables to ENV_PATH with mode 600.
# Validates the generated config using B3 ConfigValidator via Python.
# Never commits the .env file — ensure .gitignore excludes it.

set -euo pipefail

generate_env_file() {
    local env_path="$1"
    local created_at
    created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    cat > "$env_path" <<ENVFILE
# WooPrice Beta — generated environment file
# Created: ${created_at}
# DO NOT COMMIT THIS FILE

BETA_ENV=beta
BETA_DOMAIN=${BETA_DOMAIN}
BETA_PORT=${BETA_PORT}
BETA_DATABASE_URL=postgresql://${BETA_POSTGRES_USER}:${BETA_POSTGRES_PASSWORD}@postgres:5432/${BETA_POSTGRES_DB}
BETA_POSTGRES_DB=${BETA_POSTGRES_DB}
BETA_POSTGRES_USER=${BETA_POSTGRES_USER}
BETA_POSTGRES_PASSWORD=${BETA_POSTGRES_PASSWORD}
BETA_JWT_SECRET=${BETA_JWT_SECRET}
BETA_REST_API_SECRET=${BETA_REST_API_SECRET}
BETA_NEXTCLOUD_URL=${BETA_NEXTCLOUD_URL}
BETA_NEXTCLOUD_FILE_PATH=${BETA_NEXTCLOUD_FILE_PATH}
BETA_NEXTCLOUD_USERNAME=${BETA_NEXTCLOUD_USERNAME}
BETA_NEXTCLOUD_PASSWORD=${BETA_NEXTCLOUD_PASSWORD}
BETA_WOOCOMMERCE_URL=${BETA_WOOCOMMERCE_URL}
BETA_WOOCOMMERCE_KEY=${BETA_WOOCOMMERCE_KEY}
BETA_WOOCOMMERCE_SECRET=${BETA_WOOCOMMERCE_SECRET}
BETA_TIMEZONE=${BETA_TIMEZONE}
BETA_CURRENCY=${BETA_CURRENCY}
BETA_ADMIN_EMAIL=${BETA_ADMIN_EMAIL}
BETA_STORAGE_PATH=${BETA_STORAGE_PATH}
BETA_BACKUP_PATH=${BETA_BACKUP_PATH}
BETA_SSL_MODE=${BETA_SSL_MODE}
ENVFILE

    chmod 600 "$env_path"
    echo "  .env written: ${env_path} (mode 600)"
}

validate_env_file() {
    local env_path="$1"
    echo "  Validating configuration using B3 Configuration Core..."
    local repo_dir
    repo_dir="$(dirname "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")")"
    # The bootstrap installs python3 but NOT the application's Python
    # dependencies on the host — those live inside the Docker image. When the
    # app package can't be imported here, skip host-side validation gracefully;
    # the same configuration is validated by the app at runtime. A genuine
    # validation failure (importable app + invalid config) still aborts install.
    python3 - "${env_path}" "${repo_dir}" <<'PYEOF'
import sys
from pathlib import Path

env_path = sys.argv[1]
sys.path.insert(0, sys.argv[2])

try:
    from app.beta.config import ConfigurationManager
except Exception as exc:  # noqa: BLE001 — app deps absent on host is expected
    print(f"  NOTE: host-side config validation skipped ({type(exc).__name__}).")
    print("  Configuration is validated by the application at runtime.")
    sys.exit(0)

mgr = ConfigurationManager(env_file=Path(env_path), check_paths=False)
mgr.load()
result = mgr.validate()
if not result.is_valid:
    print("  Configuration validation FAILED:")
    print(result.format_errors())
    sys.exit(1)
print("  Configuration validation: PASS")
PYEOF
}
