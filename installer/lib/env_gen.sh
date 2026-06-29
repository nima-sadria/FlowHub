#!/usr/bin/env bash
# FlowHub Beta — .env.beta file generation (BU4)
#
# Source from install.sh. Call generate_env_file ENV_PATH.
# Writes only bootstrap BETA_* variables to ENV_PATH with mode 600.
#
# Bootstrap variables are the minimum required for Docker and the database
# to start. All other configuration (WooCommerce, Nextcloud, timezone,
# currency, administrator credentials) is stored in the database by the
# web Setup Wizard and is NOT written to this file.

set -euo pipefail

generate_env_file() {
    local env_path="$1"
    local created_at
    created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    cat > "$env_path" <<ENVFILE
# FlowHub Beta — bootstrap environment file
# Created: ${created_at}
# DO NOT COMMIT THIS FILE
#
# This file contains only bootstrap values required for Docker and PostgreSQL
# to start. All other runtime configuration is stored in the database and
# managed through the web Setup Wizard (https://<domain>/setup) and Settings UI.

BETA_ENV=beta
BETA_DOMAIN=${BETA_DOMAIN}
BETA_PORT=${BETA_PORT}
BETA_SSL_MODE=${BETA_SSL_MODE}
BETA_DATABASE_URL=postgresql://${BETA_POSTGRES_USER}:${BETA_POSTGRES_PASSWORD}@postgres:5432/${BETA_POSTGRES_DB}
BETA_POSTGRES_DB=${BETA_POSTGRES_DB}
BETA_POSTGRES_USER=${BETA_POSTGRES_USER}
BETA_POSTGRES_PASSWORD=${BETA_POSTGRES_PASSWORD}
BETA_JWT_SECRET=${BETA_JWT_SECRET}
BETA_REST_API_SECRET=${BETA_REST_API_SECRET}
BETA_STORAGE_PATH=${BETA_STORAGE_PATH}
BETA_BACKUP_PATH=${BETA_BACKUP_PATH}
ENVFILE

    chmod 600 "$env_path"
    echo "  .env.beta written: ${env_path} (mode 600)"
}

validate_env_file() {
    local env_path="$1"
    echo "  Validating bootstrap configuration..."
    python3 - <<PYEOF
import sys
sys.path.insert(0, "$(dirname "$(dirname "$(readlink -f "$0")")")")
from app.beta.config import ConfigurationManager
from pathlib import Path

mgr = ConfigurationManager(env_file=Path("${env_path}"), check_paths=False)
mgr.load()
result = mgr.validate()
if not result.is_valid:
    print("  Configuration validation FAILED:")
    print(result.format_errors())
    sys.exit(1)
print("  Bootstrap configuration: VALID")
PYEOF
}
