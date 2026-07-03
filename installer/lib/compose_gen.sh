#!/usr/bin/env bash
# FlowHub Docker Compose file generation.
#
# Generates docker-compose.yml by substituting FLOWHUB_* template_variables in
# installer/templates/docker-compose.template.yml using envsubst.
# Does not start Docker services; launch is handled by docker_deploy.sh.

set -euo pipefail

generate_compose_file() {
    local template_path="$1"
    local output_path="$2"

    if [[ ! -f "$template_path" ]]; then
        echo "  ERROR: Compose template not found: ${template_path}" >&2
        return 1
    fi

    if ! command -v envsubst &>/dev/null; then
        echo "  ERROR: envsubst not found (install gettext package)" >&2
        return 1
    fi

    # Substitute only FLOWHUB_* variables from environment.
    # shellcheck disable=SC2016
    envsubst '${FLOWHUB_ENV} ${FLOWHUB_DOMAIN} ${FLOWHUB_PORT} ${FLOWHUB_DATABASE_URL}
              ${FLOWHUB_POSTGRES_DB} ${FLOWHUB_POSTGRES_USER} ${FLOWHUB_POSTGRES_PASSWORD}
              ${FLOWHUB_JWT_SECRET} ${FLOWHUB_REST_API_SECRET}' \
        < "$template_path" > "$output_path"

    echo "  Docker Compose file generated: ${output_path}"
    echo "  NOTE: Docker stack launch is handled by docker_deploy.sh."
    echo "  To launch manually: docker compose -f ${output_path} up -d"
}
