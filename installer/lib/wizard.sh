#!/usr/bin/env bash
# FlowHub Beta — Bootstrap configuration wizard (BU4)
#
# Source from install.sh. Call run_wizard to populate bootstrap BETA_* variables.
# Collects only what Docker and the database need to start.
# All other configuration (integrations, timezone, currency, admin account)
# is completed through the web Setup Wizard at https://<domain>/setup.

set -euo pipefail

_prompt() {
    local var_name="$1" description="$2" default_val="${3:-}"
    local prompt_str
    if [[ -n "$default_val" ]]; then
        prompt_str="  ${description} [${default_val}]: "
    else
        prompt_str="  ${description}: "
    fi
    local value
    read -r -p "$prompt_str" value
    value="${value:-$default_val}"
    printf -v "$var_name" '%s' "$value"
}

_prompt_secret() {
    local var_name="$1" description="$2" offer_generate="${3:-y}"
    if [[ "$offer_generate" == "y" ]]; then
        echo "  ${description}"
        echo "  Press Enter to auto-generate (recommended), or type your own:"
        local value
        read -r -s -p "  > " value
        echo ""
        printf -v "$var_name" '%s' "$value"
    else
        local value
        read -r -s -p "  ${description}: " value
        echo ""
        printf -v "$var_name" '%s' "$value"
    fi
}

_section_header() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Section $1 — $2"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

wizard_section_network() {
    _section_header "1" "Network"
    _prompt BETA_DOMAIN \
        "Domain (e.g., flowhub.yourdomain.com or localhost)" ""
    _prompt BETA_PORT \
        "Port" "8085"
    echo "  SSL mode options: off / self-signed / letsencrypt / manual"
    _prompt BETA_SSL_MODE \
        "SSL mode" "off"
}

wizard_section_database() {
    _section_header "2" "Database"
    _prompt BETA_POSTGRES_DB   "PostgreSQL database name" "flowhub_beta"
    _prompt BETA_POSTGRES_USER "PostgreSQL username"      "flowhub_beta"
    echo "  PostgreSQL password — press Enter to auto-generate (recommended):"
    _prompt_secret BETA_POSTGRES_PASSWORD "PostgreSQL password" "y"
}

wizard_section_secrets() {
    _section_header "3" "Application Secrets"
    echo "  JWT signing key — press Enter to auto-generate (strongly recommended):"
    _prompt_secret BETA_JWT_SECRET "JWT secret (min 64 chars)" "y"
    echo "  REST API secret — press Enter to auto-generate (strongly recommended):"
    _prompt_secret BETA_REST_API_SECRET "REST API secret (min 32 chars)" "y"
}

wizard_section_storage() {
    _section_header "4" "Storage Paths"
    _prompt BETA_STORAGE_PATH "Storage base path" "/opt/flowhub/storage"
    _prompt BETA_BACKUP_PATH  "Backup path"       "/opt/flowhub/backups"
}

wizard_section_confirm() {
    _section_header "5" "Confirmation"

    local masked_jwt masked_rest masked_pg
    masked_jwt="********${BETA_JWT_SECRET: -4}"
    masked_rest="********${BETA_REST_API_SECRET: -4}"
    masked_pg="${BETA_POSTGRES_PASSWORD:+********${BETA_POSTGRES_PASSWORD: -4}}"
    masked_pg="${masked_pg:-[will be generated]}"

    local proto="http"
    [[ "${BETA_SSL_MODE:-off}" != "off" ]] && proto="https"

    echo ""
    echo "  Installation Summary:"
    echo "  Domain:        ${BETA_DOMAIN}:${BETA_PORT}"
    echo "  SSL mode:      ${BETA_SSL_MODE}"
    echo "  Postgres DB:   ${BETA_POSTGRES_DB}"
    echo "  Postgres user: ${BETA_POSTGRES_USER}"
    echo "  Postgres pass: ${masked_pg}"
    echo "  JWT secret:    ${masked_jwt:=[will be generated]}"
    echo "  REST secret:   ${masked_rest:=[will be generated]}"
    echo "  Storage path:  ${BETA_STORAGE_PATH}"
    echo "  Backup path:   ${BETA_BACKUP_PATH}"
    echo ""
    echo "  After installation, open your browser and complete setup:"
    echo "  ${proto}://${BETA_DOMAIN}:${BETA_PORT}/setup"
    echo ""

    local answer
    read -r -p "  Proceed with installation? [Y/n]: " answer
    answer="${answer:-y}"
    if [[ "${answer,,}" != "y" && "${answer,,}" != "yes" ]]; then
        echo "  Installation cancelled."
        exit 0
    fi
}

run_wizard() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  FlowHub Beta — Bootstrap Configuration"
    echo "  [BETA ENVIRONMENT — NOT PRODUCTION]"
    echo ""
    echo "  This wizard collects only what is needed to start Docker"
    echo "  and the database. Everything else (WooCommerce, Nextcloud,"
    echo "  timezone, currency, administrator account) is configured"
    echo "  through the web Setup Wizard after installation."
    echo ""
    echo "  Press Ctrl+C at any time to abort (no files will be written)."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    wizard_section_network
    wizard_section_database
    wizard_section_secrets
    wizard_section_storage
    wizard_section_confirm
}
