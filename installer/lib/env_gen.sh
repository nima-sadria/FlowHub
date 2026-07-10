#!/usr/bin/env bash
# FlowHub - .env file generation
#
# Source from install.sh. Call generate_env_file ENV_PATH.
# Writes all FLOWHUB_* variables to ENV_PATH with mode 600.
# Validates the generated config using B3 ConfigValidator via Python.
# Never commits the .env file - ensure .gitignore excludes it.

set -euo pipefail

generate_env_file() {
    local env_path="$1"
    local created_at
    created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    cat > "$env_path" <<ENVFILE
# FlowHub - generated environment file
# Created: ${created_at}
# DO NOT COMMIT THIS FILE

FLOWHUB_ENV=production
FLOWHUB_DOMAIN=${FLOWHUB_DOMAIN}
FLOWHUB_PORT=${FLOWHUB_PORT}
FLOWHUB_DATABASE_URL=postgresql://${FLOWHUB_POSTGRES_USER}:${FLOWHUB_POSTGRES_PASSWORD}@postgres:5432/${FLOWHUB_POSTGRES_DB}
FLOWHUB_POSTGRES_DB=${FLOWHUB_POSTGRES_DB}
FLOWHUB_POSTGRES_USER=${FLOWHUB_POSTGRES_USER}
FLOWHUB_POSTGRES_PASSWORD=${FLOWHUB_POSTGRES_PASSWORD}
FLOWHUB_JWT_SECRET=${FLOWHUB_JWT_SECRET}
FLOWHUB_REST_API_SECRET=${FLOWHUB_REST_API_SECRET}
FLOWHUB_TRUSTED_PROXY_NETWORKS=${FLOWHUB_TRUSTED_PROXY_NETWORKS:-}
FLOWHUB_NEXTCLOUD_URL=${FLOWHUB_NEXTCLOUD_URL}
FLOWHUB_NEXTCLOUD_FILE_PATH=${FLOWHUB_NEXTCLOUD_FILE_PATH}
FLOWHUB_NEXTCLOUD_USERNAME=${FLOWHUB_NEXTCLOUD_USERNAME}
FLOWHUB_NEXTCLOUD_PASSWORD=${FLOWHUB_NEXTCLOUD_PASSWORD}
FLOWHUB_WOOCOMMERCE_URL=${FLOWHUB_WOOCOMMERCE_URL}
FLOWHUB_WOOCOMMERCE_KEY=${FLOWHUB_WOOCOMMERCE_KEY}
FLOWHUB_WOOCOMMERCE_SECRET=${FLOWHUB_WOOCOMMERCE_SECRET}
FLOWHUB_TIMEZONE=${FLOWHUB_TIMEZONE}
FLOWHUB_CURRENCY=${FLOWHUB_CURRENCY}
FLOWHUB_ADMIN_USERNAME=${FLOWHUB_ADMIN_USERNAME}
FLOWHUB_ADMIN_EMAIL=${FLOWHUB_ADMIN_EMAIL}
FLOWHUB_STORAGE_PATH=${FLOWHUB_STORAGE_PATH}
FLOWHUB_BACKUP_PATH=${FLOWHUB_BACKUP_PATH}
FLOWHUB_SSL_MODE=${FLOWHUB_SSL_MODE}
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
    # dependencies on the host - those live inside the Docker image. When the
    # app package can't be imported here, skip host-side validation gracefully;
    # the same configuration is validated by the app at runtime. A genuine
    # validation failure (importable app + invalid config) still aborts install.
    python3 - "${env_path}" "${repo_dir}" <<'PYEOF'
import sys
from pathlib import Path

env_path = sys.argv[1]
sys.path.insert(0, sys.argv[2])

try:
    from app.flowhub.config import ConfigurationManager
except Exception as exc:  # noqa: BLE001 - app deps absent on host is expected
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
