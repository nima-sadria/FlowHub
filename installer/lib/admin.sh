#!/usr/bin/env bash
# FlowHub - initial admin account creation
#
# Source from install.sh. Requires:
#   - App container running and database migrated
#     (call after wait_for_postgres_ready + run_alembic_migrations)
#   - FLOWHUB_* env exported (call _load_env_for_docker first)
#
# Uses FLOWHUB_ADMIN_USERNAME, FLOWHUB_ADMIN_EMAIL, FLOWHUB_ADMIN_PASSWORD from the
# installer wizard. In non-interactive mode, the password is auto-generated
# and printed once. It is never persisted to disk.
#
# Idempotent: if the admin user already exists the CLI exits non-zero and this
# function reports that without failing the install.

set -euo pipefail

create_admin_account() {
    local install_dir="$1"
    local compose_file="${install_dir}/docker-compose.yml"
    local env_file="${install_dir}/.env"
    local username="${FLOWHUB_ADMIN_USERNAME:-admin}"
    local dc_cmd

    if docker compose version &>/dev/null 2>&1; then
        dc_cmd="docker compose"
    elif command -v docker-compose &>/dev/null; then
        dc_cmd="docker-compose"
    else
        echo "  ERROR: docker compose not available" >&2
        return 1
    fi

    # Use password from wizard if available; otherwise auto-generate.
    local password auto_generated=0
    if [[ -n "${FLOWHUB_ADMIN_PASSWORD:-}" ]]; then
        password="$FLOWHUB_ADMIN_PASSWORD"
    else
        password="$(openssl rand -hex 20 2>/dev/null \
            || python3 -c 'import secrets; print(secrets.token_hex(20))')"
        auto_generated=1
    fi

    echo "  Creating admin user '${username}'..."

    # The create-admin CLI reads FLOWHUB_DATABASE_URL from the container env.
    if ${dc_cmd} --project-directory "$install_dir" -f "$compose_file" --env-file "$env_file" \
            exec -T app python -m cli.main create-admin \
            --username "$username" --password "$password"; then

        if [[ "$auto_generated" -eq 1 ]]; then
            echo ""
            echo "  ===================================================================="
            echo "  Admin account created (auto-generated password)."
            echo "    Username: ${username}"
            echo "    Password: ${password}"
            echo "  Store this password now - it is shown only once."
            echo "  ===================================================================="
        else
            echo "  Admin account created."
            echo "    Username : ${username}"
            echo "    Email    : ${FLOWHUB_ADMIN_EMAIL:-}"
        fi
        return 0
    fi

    echo "" >&2
    echo "  NOTE: admin creation did not complete." >&2
    echo "  The user may already exist, or the app container is not ready." >&2
    echo "  Create manually with:" >&2
    echo "    ${dc_cmd} -f ${compose_file} exec app python -m cli.main create-admin" >&2
    return 0
}
