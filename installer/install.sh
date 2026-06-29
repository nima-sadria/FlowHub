#!/usr/bin/env bash
# FlowHub Beta — Main installer entry point
#
# One-command install (clean server, run as root):
#   bash <(curl -Ls https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh)
#
# From a cloned repo:
#   bash installer/install.sh [--install-dir <path>] [--dry-run] [--non-interactive]
#
# Idempotent: detects existing installations and offers upgrade/repair/reconfigure/exit.
# Never overwrites an existing .env.beta without explicit confirmation.
#
# [BETA ENVIRONMENT — NOT PRODUCTION]

set -euo pipefail

# ── Bootstrap ─────────────────────────────────────────────────────────────────
# When invoked via  bash <(curl ...)  the script streams through a file
# descriptor (/dev/fd/N).  dirname of that path does not contain lib/.
# We detect this and enter bootstrap mode: install system deps, clone the
# repo into INSTALL_DIR, then re-exec from there.

_FLOWHUB_INSTALL_DIR="${FLOWHUB_INSTALL_DIR:-/opt/flowhub}"
_FLOWHUB_REPO_URL="https://github.com/nima-sadria/FlowHub.git"
_FLOWHUB_BRANCH="main"

_bs_require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        echo "ERROR: Bootstrap must run as root." >&2
        echo "  Run:  sudo bash <(curl -Ls <url>)" >&2
        exit 1
    fi
}

_bs_os_check() {
    [[ -f /etc/os-release ]] || {
        echo "ERROR: Cannot detect OS. Only Ubuntu and Debian are supported." >&2
        exit 1
    }
    # shellcheck source=/dev/null
    . /etc/os-release
    case "${ID:-}" in
        ubuntu|debian)
            echo "  OS:   ${PRETTY_NAME:-${ID}}"
            ;;
        *)
            echo "ERROR: Unsupported OS '${ID:-unknown}'. Only Ubuntu and Debian are supported." >&2
            exit 1
            ;;
    esac
}

_bs_arch_check() {
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64)  echo "  Arch: amd64" ;;
        aarch64) echo "  Arch: arm64" ;;
        *)
            echo "ERROR: Unsupported architecture '${arch}'. Only amd64 and arm64 are supported." >&2
            exit 1
            ;;
    esac
}

_bs_install_system_deps() {
    echo "  Installing system packages..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends \
        git curl ca-certificates gnupg lsb-release openssl python3 python3-pip
    echo "  System packages installed."
}

# ── Docker installation helpers ───────────────────────────────────────────────
# Defined before the bootstrap detection so both paths can use them.

# Method 1: official Docker apt repository.
# Downloads the GPG key to a temp file and validates it before touching apt.
# Returns 1 on any failure so callers can try the fallback.
_docker_install_via_apt() {
    # shellcheck source=/dev/null
    . /etc/os-release
    echo "  Trying Docker apt repository (download.docker.com)..."
    local tmpkey
    tmpkey="$(mktemp)"
    local http_status
    http_status=$(curl --connect-timeout 15 --max-time 30 \
        -s -w "%{http_code}" \
        -o "$tmpkey" \
        "https://download.docker.com/linux/${ID}/gpg" 2>/dev/null || echo "000")
    if [[ "$http_status" != "200" ]]; then
        rm -f "$tmpkey"
        echo "  Docker GPG key download failed (HTTP ${http_status})" >&2
        return 1
    fi
    if [[ ! -s "$tmpkey" ]]; then
        rm -f "$tmpkey"
        echo "  Docker GPG key response was empty" >&2
        return 1
    fi
    install -m 0755 -d /etc/apt/keyrings
    if ! gpg --dearmor < "$tmpkey" > /etc/apt/keyrings/docker.gpg 2>/dev/null; then
        rm -f "$tmpkey" /etc/apt/keyrings/docker.gpg
        echo "  Docker GPG key contained no valid OpenPGP data" >&2
        return 1
    fi
    rm -f "$tmpkey"
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${ID} $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y --no-install-recommends \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    echo "  Docker: installed and started (apt repository)"
}

# Method 2: get.docker.com convenience script.
# Used when the apt repository is unreachable or returns errors.
_docker_install_via_get_script() {
    echo "  Falling back to get.docker.com install script..."
    local tmpscript
    tmpscript="$(mktemp)"
    if ! curl -fsSL --connect-timeout 15 --max-time 120 \
            -o "$tmpscript" "https://get.docker.com" 2>/dev/null; then
        rm -f "$tmpscript"
        echo "  get.docker.com download failed" >&2
        return 1
    fi
    if [[ ! -s "$tmpscript" ]]; then
        rm -f "$tmpscript"
        echo "  get.docker.com script was empty" >&2
        return 1
    fi
    sh "$tmpscript"
    rm -f "$tmpscript"
    systemctl enable docker
    systemctl start docker
    echo "  Docker: installed and started (get.docker.com)"
}

# Final failure reporter — called when both methods fail.
_docker_install_report_failure() {
    echo "" >&2
    echo "  ── Docker Installation Failed ──────────────────────────────────────" >&2
    echo "  Both installation methods failed. Likely causes:" >&2
    echo "    • download.docker.com returned HTTP 403/404 (CDN or geo block)" >&2
    echo "    • Outbound HTTPS blocked by firewall or proxy" >&2
    echo "    • OS codename not yet listed in Docker apt repository" >&2
    echo "  Resolve connectivity, then manually install Docker:" >&2
    echo "    curl -fsSL https://get.docker.com | sh" >&2
    echo "    systemctl enable docker && systemctl start docker" >&2
    echo "  Then re-run: bash installer/install.sh" >&2
    echo "  ────────────────────────────────────────────────────────────────────" >&2
    return 1
}

_bs_install_docker() {
    if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
        echo "  Docker: already installed"
        return 0
    fi
    echo "  Installing Docker Engine + Compose plugin..."
    _docker_install_via_apt && return 0
    _docker_install_via_get_script && return 0
    _docker_install_report_failure
}

_bs_clone_or_pull() {
    if [[ -d "${_FLOWHUB_INSTALL_DIR}/.git" ]]; then
        echo "  Updating ${_FLOWHUB_INSTALL_DIR}..."
        git -C "$_FLOWHUB_INSTALL_DIR" fetch --quiet origin
        git -C "$_FLOWHUB_INSTALL_DIR" reset --hard "origin/${_FLOWHUB_BRANCH}"
        echo "  Repo updated."
    else
        echo "  Cloning FlowHub into ${_FLOWHUB_INSTALL_DIR}..."
        mkdir -p "$(dirname "$_FLOWHUB_INSTALL_DIR")"
        git clone --branch "$_FLOWHUB_BRANCH" --depth 1 \
            "$_FLOWHUB_REPO_URL" "$_FLOWHUB_INSTALL_DIR"
        echo "  Clone complete."
    fi
}

# Bootstrap detection: when piped via bash <(curl ...), BASH_SOURCE[0] is
# /dev/fd/N — its parent directory has no lib/checks.sh.
if [[ ! -f "$(dirname "${BASH_SOURCE[0]:-NONE}")/lib/checks.sh" ]]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  FlowHub Beta — Bootstrap (one-command install)"
    echo "  Install directory: ${_FLOWHUB_INSTALL_DIR}"
    echo "  [BETA ENVIRONMENT — NOT PRODUCTION]"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    _bs_require_root
    _bs_os_check
    _bs_arch_check
    _bs_install_system_deps
    _bs_install_docker
    _bs_clone_or_pull
    echo ""
    echo "  Handing off to full installer at ${_FLOWHUB_INSTALL_DIR}..."
    echo ""
    exec bash "${_FLOWHUB_INSTALL_DIR}/installer/install.sh" \
        --install-dir "${_FLOWHUB_INSTALL_DIR}" "$@"
fi

# ── Running from a proper repo checkout ───────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/lib"
TEMPLATES_DIR="${SCRIPT_DIR}/templates"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Source lib modules
# shellcheck source=installer/lib/checks.sh
source "${LIB_DIR}/checks.sh"
# shellcheck source=installer/lib/secrets.sh
source "${LIB_DIR}/secrets.sh"
# shellcheck source=installer/lib/wizard.sh
source "${LIB_DIR}/wizard.sh"
# shellcheck source=installer/lib/env_gen.sh
source "${LIB_DIR}/env_gen.sh"
# shellcheck source=installer/lib/storage.sh
source "${LIB_DIR}/storage.sh"
# shellcheck source=installer/lib/docker_deploy.sh
source "${LIB_DIR}/docker_deploy.sh"
# shellcheck source=installer/lib/db_init.sh
source "${LIB_DIR}/db_init.sh"
# shellcheck source=installer/lib/admin.sh
source "${LIB_DIR}/admin.sh"
# shellcheck source=installer/lib/uninstall.sh
source "${LIB_DIR}/uninstall.sh"

# ── Docker auto-install (non-bootstrap path) ──────────────────────────────────
# Called by step_prerequisites() before run_prerequisite_checks().
# Installs Docker Engine + Compose plugin on Ubuntu/Debian when missing.
# No-op (with warning) if auto-install cannot run; hard-fails if both
# installation methods fail so the installer does not proceed without Docker.
_ensure_docker_installed() {
    if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
        return 0
    fi

    echo ""
    echo "  Docker not found — auto-installing Docker Engine + Compose plugin..."

    if [[ "$(id -u)" -ne 0 ]]; then
        echo "  WARNING: Not running as root — cannot auto-install Docker." >&2
        echo "  Install manually: https://docs.docker.com/engine/install/" >&2
        return 0  # let run_prerequisite_checks() report the [FAIL]
    fi

    if [[ ! -f /etc/os-release ]]; then
        echo "  WARNING: Cannot detect OS — skipping Docker auto-install." >&2
        return 0
    fi
    # shellcheck source=/dev/null
    . /etc/os-release
    case "${ID:-}" in
        ubuntu|debian) ;;
        *)
            echo "  WARNING: OS '${ID:-unknown}' not supported for auto-install — skipping." >&2
            return 0
            ;;
    esac

    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg lsb-release

    _docker_install_via_apt && return 0
    _docker_install_via_get_script && return 0
    _docker_install_report_failure
}

# ---- Defaults ----
INSTALL_DIR="/opt/flowhub"
DRY_RUN=0
NON_INTERACTIVE=0
ACTION_UNINSTALL=0
INSTALLER_ENV_FILE=""
INSTALLER_CREATED_FILES=""   # space-separated, for file rollback

# ---- Argument parsing ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)           DRY_RUN=1 ;;
        --non-interactive)   NON_INTERACTIVE=1 ;;
        --uninstall)         ACTION_UNINSTALL=1 ;;
        --install-dir)       INSTALL_DIR="$2"; shift ;;
        --install-dir=*)     INSTALL_DIR="${1#*=}" ;;
        -h|--help)
            echo "Usage: bash installer/install.sh [--dry-run] [--install-dir DIR] [--non-interactive] [--uninstall]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
    shift
done

INSTALLER_ENV_FILE="${INSTALL_DIR}/.env.beta"

# When invoked without an interactive terminal (e.g. piped through
# `bash <(curl ...)` in an automated context, CI, or a provisioning script),
# there is no TTY to drive the wizard prompts. Fall back to non-interactive
# mode with sane defaults instead of blocking forever on `read`.
if [[ "$NON_INTERACTIVE" -eq 0 && ! -t 0 ]]; then
    echo "  No interactive terminal detected — running non-interactively with defaults."
    NON_INTERACTIVE=1
fi

# Defaults applied when running non-interactively (wizard skipped). Secrets are
# generated separately by generate_all_secrets. Only sets vars not already set,
# so explicit FLOWHUB_*/BETA_* environment overrides are respected.
apply_noninteractive_defaults() {
    : "${BETA_DOMAIN:=localhost}"
    : "${BETA_PORT:=8085}"
    : "${BETA_SSL_MODE:=off}"
    : "${BETA_POSTGRES_DB:=wooprice_beta}"
    : "${BETA_POSTGRES_USER:=wooprice_beta}"
    : "${BETA_NEXTCLOUD_URL:=}"
    : "${BETA_NEXTCLOUD_FILE_PATH:=}"
    : "${BETA_NEXTCLOUD_USERNAME:=}"
    : "${BETA_NEXTCLOUD_PASSWORD:=}"
    : "${BETA_WOOCOMMERCE_URL:=}"
    : "${BETA_WOOCOMMERCE_KEY:=}"
    : "${BETA_WOOCOMMERCE_SECRET:=}"
    : "${BETA_TIMEZONE:=UTC}"
    : "${BETA_CURRENCY:=USD}"
    : "${BETA_ADMIN_EMAIL:=admin@example.com}"
    : "${BETA_STORAGE_PATH:=${INSTALL_DIR}/storage}"
    : "${BETA_BACKUP_PATH:=${INSTALL_DIR}/backups}"
    export BETA_DOMAIN BETA_PORT BETA_SSL_MODE BETA_POSTGRES_DB BETA_POSTGRES_USER \
        BETA_NEXTCLOUD_URL BETA_NEXTCLOUD_FILE_PATH BETA_NEXTCLOUD_USERNAME BETA_NEXTCLOUD_PASSWORD \
        BETA_WOOCOMMERCE_URL BETA_WOOCOMMERCE_KEY BETA_WOOCOMMERCE_SECRET \
        BETA_TIMEZONE BETA_CURRENCY BETA_ADMIN_EMAIL BETA_STORAGE_PATH BETA_BACKUP_PATH
    echo "  Non-interactive defaults applied (domain=${BETA_DOMAIN}, port=${BETA_PORT}, db=${BETA_POSTGRES_DB})."
}

# ---- Rollback ----
_track_file() { INSTALLER_CREATED_FILES="${INSTALLER_CREATED_FILES} $1"; }

rollback_all() {
    echo ""
    echo "  !! Rolling back installation (removing only files/dirs created by this run)..."
    rollback_storage 2>/dev/null || true
    for f in $INSTALLER_CREATED_FILES; do
        if [[ -f "$f" ]]; then
            rm -f "$f"
            echo "  Removed file: ${f}"
        fi
    done
    echo "  Rollback complete."
}

# ---- Error handler ----
on_error() {
    local exit_code=$?
    local line_no="${1:-?}"
    echo ""
    echo "  !! Installation failed at line ${line_no} (exit code: ${exit_code})"
    if [[ "$DRY_RUN" -eq 0 ]]; then
        rollback_all
    fi
    echo ""
    echo "  To diagnose: docker compose -f ${INSTALL_DIR}/docker-compose.beta.yml logs"
    echo "  To retry:    re-run install.sh"
    exit "$exit_code"
}
trap 'on_error $LINENO' ERR

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

print_banner() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  FlowHub Beta Installer  v1.0.0-bu1"
    echo "  [BETA ENVIRONMENT — NOT PRODUCTION]"
    echo ""
    echo "  This installer sets up a completely isolated Beta environment."
    echo "  It will NOT modify any Production WooPrice installation."
    echo ""
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  *** DRY-RUN MODE — No files will be written, no Docker started ***"
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ---------------------------------------------------------------------------
# Idempotency — detect existing installation
# ---------------------------------------------------------------------------

detect_existing_installation() {
    [[ -f "${INSTALLER_ENV_FILE}" ]]
}

handle_existing_installation() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Existing FlowHub Beta installation detected."
    echo "  Environment file: ${INSTALLER_ENV_FILE}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  Select an action:"
    echo ""
    echo "  1. Upgrade    — rebuild images and restart the stack (keeps .env.beta)"
    echo "  2. Repair     — re-run prerequisite checks and health verification"
    echo "  3. Reconfigure — re-run wizard, regenerate .env.beta, then upgrade"
    echo "  4. Uninstall  — remove FlowHub containers, images, volumes, and files"
    echo "  5. Exit"
    echo ""
    local choice
    read -r -p "  Enter choice [1-5]: " choice
    case "${choice:-}" in
        1) step_upgrade ;;
        2) step_repair ;;
        3) step_reconfigure ;;
        4) step_uninstall ;;
        5|"")
            echo "  Exiting without changes."
            exit 0
            ;;
        *)
            echo "  Invalid choice. Exiting."
            exit 1
            ;;
    esac
}

# ---- Uninstall path ----
step_uninstall() {
    run_uninstall "$INSTALL_DIR"
}

# ---- Upgrade path (keeps existing .env.beta) ----
step_upgrade() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Upgrade: rebuilding images and restarting services"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    _load_env_for_docker
    step_docker_launch
    step_database_init
    step_create_admin
    step_health_check
    step_completion_report
}

# ---- Repair path ----
step_repair() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Repair: re-checking prerequisites and health"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    _load_env_for_docker
    step_prerequisites
    step_storage
    step_health_check
    echo ""
    echo "  Repair complete."
}

# ---- Reconfigure path ----
step_reconfigure() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Reconfigure: wizard will regenerate .env.beta"
    echo "  EXISTING .env.beta WILL BE OVERWRITTEN after confirmation."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    local confirm
    read -r -p "  Continue? Secrets will be regenerated. [y/N]: " confirm
    if [[ "${confirm,,}" != "y" && "${confirm,,}" != "yes" ]]; then
        echo "  Reconfiguration cancelled."
        exit 0
    fi
    step_wizard
    step_secrets
    step_env_file
    step_storage
    step_docker_launch
    step_database_init
    step_create_admin
    step_health_check
    step_completion_report
}

# Load .env.beta into shell for use by Docker deploy functions
_load_env_for_docker() {
    if [[ -f "${INSTALLER_ENV_FILE}" ]]; then
        # Export only BETA_* vars; skip comments and blank lines
        while IFS='=' read -r key value; do
            [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
            [[ "$key" =~ ^BETA_ ]] && export "$key=$value"
        done < <(grep -E '^BETA_' "${INSTALLER_ENV_FILE}" 2>/dev/null || true)
    fi
}

# ---------------------------------------------------------------------------
# Installation steps
# ---------------------------------------------------------------------------

step_prerequisites() {
    echo ""
    echo "Step 1 — Prerequisite Checks"
    _ensure_docker_installed
    run_prerequisite_checks "$INSTALL_DIR"
}

step_wizard() {
    if [[ "$NON_INTERACTIVE" -eq 0 ]]; then
        echo ""
        echo "Step 2 — Interactive Configuration Wizard"
        run_wizard
    else
        echo ""
        echo "Step 2 — Non-interactive configuration (applying defaults)"
        apply_noninteractive_defaults
    fi
}

step_secrets() {
    echo ""
    echo "Step 3 — Secret Generation"
    generate_all_secrets
}

step_env_file() {
    echo ""
    echo "Step 4 — Environment File Generation"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would write: ${INSTALLER_ENV_FILE}"
        echo "  [DRY RUN] Would validate configuration using B3 ConfigValidator"
        return
    fi
    mkdir -p "$INSTALL_DIR"
    generate_env_file "$INSTALLER_ENV_FILE"
    _track_file "$INSTALLER_ENV_FILE"
    validate_env_file "$INSTALLER_ENV_FILE"
}

step_storage() {
    echo ""
    echo "Step 5 — Storage Directory Setup"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would create:"
        echo "  ${BETA_STORAGE_PATH:-/opt/flowhub/storage}/{logs,config,plugins,uploads,diagnostics}"
        echo "  ${BETA_BACKUP_PATH:-/opt/flowhub/backups}"
        echo "  ${INSTALL_DIR}/logs"
        return
    fi
    setup_storage_dirs
    # Ensure bind-mount directories exist in INSTALL_DIR
    mkdir -p "${INSTALL_DIR}/storage" "${INSTALL_DIR}/backups" "${INSTALL_DIR}/logs"
    echo "  Bind-mount directories ready: storage/ backups/ logs/"
}

step_toml_config() {
    echo ""
    echo "Step 6 — Managed Configuration File"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would write: ${BETA_STORAGE_PATH:-/opt/flowhub/storage}/config/flowhub-beta.toml"
        return
    fi
    # installer_core imports app.beta.config which requires Python deps installed
    # on the host. Skip gracefully if not available — Docker stack uses .env.beta.
    if ! python3 - <<PYEOF 2>/dev/null
import sys
sys.path.insert(0, "${REPO_DIR}")
from installer.installer_core import InstallerConfig, generate_toml_content, write_toml_config
from pathlib import Path

config = InstallerConfig(
    domain="${BETA_DOMAIN:-}",
    port=int("${BETA_PORT:-8085}"),
    ssl_mode="${BETA_SSL_MODE:-off}",
    postgres_db="${BETA_POSTGRES_DB:-wooprice_beta}",
    postgres_user="${BETA_POSTGRES_USER:-wooprice_beta}",
    storage_path="${BETA_STORAGE_PATH:-/opt/flowhub/storage}",
    backup_path="${BETA_BACKUP_PATH:-/opt/flowhub/backups}",
    log_level="INFO",
)
content = generate_toml_content(config)
config_dir = Path("${BETA_STORAGE_PATH:-/opt/flowhub/storage}/config")
config_dir.mkdir(parents=True, exist_ok=True)
path = write_toml_config(content, config_dir)
print(f"  Managed config written: {path}")
PYEOF
    then
        echo "  NOTE: TOML config skipped (Python app dependencies not on host)."
        echo "  Docker stack reads .env.beta directly — no impact on operation."
    fi
}

step_compose_verify() {
    echo ""
    echo "Step 7 — Docker Compose Verification"
    local compose_file="${INSTALL_DIR}/docker-compose.beta.yml"
    if [[ -f "$compose_file" ]]; then
        echo "  Compose file: ${compose_file}"
        local dc_cmd
        dc_cmd="$(docker_compose_cmd)"
        if [[ "$DRY_RUN" -eq 0 ]]; then
            ${dc_cmd} --project-directory "$INSTALL_DIR" -f "$compose_file" --env-file "${INSTALLER_ENV_FILE}" config --quiet \
                && echo "  Compose config: VALID" \
                || { echo "  ERROR: Compose config validation failed" >&2; return 1; }
        else
            echo "  [DRY RUN] Would validate: ${compose_file}"
        fi
    else
        echo "  ERROR: docker-compose.beta.yml not found at ${INSTALL_DIR}" >&2
        echo "  Ensure the repository was cloned to ${INSTALL_DIR}" >&2
        return 1
    fi
}

step_docker_launch() {
    echo ""
    echo "Step 8 — Docker Stack Launch"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would run: docker compose up -d --build"
        return
    fi
    _load_env_for_docker
    build_and_start_services "$INSTALL_DIR"
}

step_database_init() {
    echo ""
    echo "Step 9 — Database Initialization"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would wait for PostgreSQL, then run: alembic -c alembic_beta.ini upgrade head"
        return
    fi
    _load_env_for_docker
    wait_for_postgres_ready "$INSTALL_DIR" 90
    run_alembic_migrations "$INSTALL_DIR"
}

step_create_admin() {
    echo ""
    echo "Step 9b - Create Admin Account"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would run: python -m cli.main create-admin (auto-generated password)"
        return
    fi
    _load_env_for_docker
    create_admin_account "$INSTALL_DIR"
}

step_install_cli() {
    echo ""
    echo "Step 10 — Install flowhub CLI"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would install: /usr/local/bin/flowhub"
        return
    fi
    local wrapper_src="${REPO_DIR}/scripts/wooprice"
    local wrapper_dst="/usr/local/bin/flowhub"
    if [[ ! -f "$wrapper_src" ]]; then
        echo "  WARNING: CLI wrapper not found at ${wrapper_src} — skipping" >&2
        return
    fi
    if [[ -w "$(dirname "$wrapper_dst")" ]] || command -v sudo &>/dev/null; then
        if [[ -w "$(dirname "$wrapper_dst")" ]]; then
            cp "$wrapper_src" "$wrapper_dst"
            chmod +x "$wrapper_dst"
        else
            sudo cp "$wrapper_src" "$wrapper_dst"
            sudo chmod +x "$wrapper_dst"
        fi
        echo "  CLI installed: ${wrapper_dst}"
        echo "  Test with: flowhub --help"
    else
        echo "  WARNING: Cannot write to $(dirname "$wrapper_dst") (no sudo) — CLI not installed"
        echo "  Manual install: cp ${wrapper_src} ${wrapper_dst} && chmod +x ${wrapper_dst}"
    fi
}

step_health_check() {
    echo ""
    echo "Step 11 — Health Verification"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would verify: http://localhost:${BETA_PORT:-8085}/api/health"
        return
    fi
    _load_env_for_docker
    local port="${BETA_PORT:-8085}"
    wait_for_app_healthy "$port" 24
    verify_health_endpoint "$port"
}

step_completion_report() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  FlowHub Beta — Dry Run Complete"
        echo "  No files were written. No Docker was started."
        echo "  Review the output above for a preview of what would happen."
    else
        _load_env_for_docker
        local port="${BETA_PORT:-8085}"
        local domain="${BETA_DOMAIN:-localhost}"
        local proto="http"
        [[ "${BETA_SSL_MODE:-off}" != "off" ]] && proto="https"
        echo "  FlowHub Beta — Installation Complete"
        echo ""
        echo "  ┌─────────────────────────────────────────────────────┐"
        echo "  │  Open your browser and complete setup:              │"
        echo "  │                                                     │"
        echo "  │    ${proto}://${domain}:${port}/setup"
        echo "  │                                                     │"
        echo "  │  The web wizard will guide you through:             │"
        echo "  │    • Server profile (timezone, currency)            │"
        echo "  │    • Database verification                          │"
        echo "  │    • Administrator account creation                 │"
        echo "  │    • WooCommerce and Nextcloud connections          │"
        echo "  └─────────────────────────────────────────────────────┘"
        echo ""
        echo "  Environment file: ${INSTALLER_ENV_FILE}"
        echo "  Health check:     ${proto}://${domain}:${port}/api/health"
        echo ""
        echo "  Management:"
        echo "    flowhub              — interactive management menu"
        echo "    flowhub status       — configuration status"
        echo "    flowhub health       — local health checks"
        echo "    flowhub diagnostics run — full integration check"
        echo ""
        echo "  Docker:"
        echo "    docker compose -f ${INSTALL_DIR}/docker-compose.beta.yml ps"
        echo "    docker compose -f ${INSTALL_DIR}/docker-compose.beta.yml logs -f app"
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    print_banner

    # --uninstall flag: bypass the normal install flow regardless of state.
    if [[ "$ACTION_UNINSTALL" -eq 1 ]]; then
        step_uninstall
        return
    fi

    # Idempotency check — detect existing installation before starting.
    # Non-interactive mode with an existing .env.beta defaults to upgrade to
    # avoid silently overwriting secrets without confirmation.
    if detect_existing_installation && [[ "$DRY_RUN" -eq 0 ]]; then
        if [[ "$NON_INTERACTIVE" -eq 1 ]]; then
            echo "  Existing installation detected. Running upgrade (non-interactive mode)."
            step_upgrade
            return
        fi
        handle_existing_installation
        return
    fi

    step_prerequisites
    step_wizard
    step_secrets
    step_env_file
    step_storage
    step_toml_config
    step_compose_verify
    step_docker_launch
    step_database_init
    step_create_admin
    step_install_cli
    step_health_check
    step_completion_report
}

main "$@"
