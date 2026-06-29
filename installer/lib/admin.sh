#!/usr/bin/env bash
# FlowHub Beta — initial admin account creation
#
# Source from install.sh. Requires:
#   - App container running and database migrated
#     (call after wait_for_postgres_ready + run_alembic_migrations)
#   - BETA_* env exported (call _load_env_for_docker first)
#
# Creates the initial admin user by invoking the create-admin CLI inside the
# running app container. The password is auto-generated, printed once to the
# terminal, and written to logs/admin-credentials.txt (mode 600).
#
# Idempotent: if the admin user already exists the CLI exits non-zero and this
# function reports that without failing the install.

set -euo pipefail

create_admin_account() {
    local install_dir="$1"
    local compose_file="${install_dir}/docker-compose.beta.yml"
    local env_file="${install_dir}/.env.beta"
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

    # Generate a strong, shell-safe random password (160-bit hex).
    local password
    password="$(openssl rand -hex 20 2>/dev/null \
        || python3 -c 'import secrets; print(secrets.token_hex(20))')"

    echo "  Creating initial admin user '${username}'..."

    # The create-admin CLI reads BETA_DATABASE_URL from the container env.
    if ${dc_cmd} --project-directory "$install_dir" -f "$compose_file" --env-file "$env_file" \
            exec -T app python -m cli.main create-admin \
            --username "$username" --password "$password"; then
        echo ""
        echo "  ===================================================================="
        echo "  Admin account created."
        echo "    Username: ${username}"
        echo "    Password: ${password}"
        echo "  Store this password now — it is shown only once."
        echo "  ===================================================================="

        # Best-effort: persist credentials to a 0600 file for the operator.
        local logf="${install_dir}/logs/admin-credentials.txt"
        if printf 'username=%s\npassword=%s\n' "$username" "$password" > "$logf" 2>/dev/null; then
            chmod 600 "$logf" 2>/dev/null || true
            echo "  Saved to: ${logf} (mode 600)"
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
