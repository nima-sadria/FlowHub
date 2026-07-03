#!/usr/bin/env bash
# FlowHub - Main installer entry point
#
# One-command install (clean server, run as root):
#   bash <(curl -Ls https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh)
#
# From a cloned repo:
#   bash installer/install.sh [--install-dir <path>] [--dry-run] [--non-interactive]
#
# Idempotent: detects existing installations and offers upgrade/repair/reinstall/exit.
# Never overwrites an existing .env without explicit confirmation.
#

set -euo pipefail

# -- Bootstrap -----------------------------------------------------------------
# When invoked via  bash <(curl ...)  the script streams through a file
# descriptor (/dev/fd/N).  dirname of that path does not contain lib/.
# We detect this and enter bootstrap mode: install system deps, clone the
# repo into INSTALL_DIR, then re-exec from there.

_FLOWHUB_CANONICAL_INSTALL_DIR="/opt/FlowHub"
_FLOWHUB_LEGACY_INSTALL_DIR="/opt/flowhub" # Legacy Compatibility
_FLOWHUB_INSTALL_DIR="${FLOWHUB_INSTALL_DIR:-${_FLOWHUB_CANONICAL_INSTALL_DIR}}"
_FLOWHUB_REPO_URL="https://github.com/nima-sadria/FlowHub.git"
_FLOWHUB_BRANCH="main"

if [[ "$_FLOWHUB_INSTALL_DIR" == "$_FLOWHUB_LEGACY_INSTALL_DIR" ]]; then
    echo "  Legacy install directory requested; using canonical path ${_FLOWHUB_CANONICAL_INSTALL_DIR}."
    _FLOWHUB_INSTALL_DIR="$_FLOWHUB_CANONICAL_INSTALL_DIR"
elif [[ "$_FLOWHUB_INSTALL_DIR" != "$_FLOWHUB_CANONICAL_INSTALL_DIR" ]]; then
    echo "ERROR: FlowHub first release installs only to ${_FLOWHUB_CANONICAL_INSTALL_DIR}." >&2
    exit 1
fi

_bs_confirm_legacy_migration() {
    if [[ "${FLOWHUB_ASSUME_YES:-}" == "1" ]]; then
        return 0
    fi
    if [[ ! -t 0 ]]; then
        echo "  Non-interactive bootstrap detected; migrating legacy install automatically."
        return 0
    fi
    local answer
    read -r -p "  Migrate legacy installation to ${_FLOWHUB_CANONICAL_INSTALL_DIR}? [Y/n]: " answer
    answer="${answer:-y}"
    [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]]
}

_bs_stop_legacy_stack() {
    local legacy_dir="${_FLOWHUB_LEGACY_INSTALL_DIR}"
    local compose_file="${legacy_dir}/docker-compose.yml"
    local env_file="${legacy_dir}/.env"
    if [[ ! -f "$compose_file" && -f "${legacy_dir}/docker-compose.beta.yml" ]]; then
        compose_file="${legacy_dir}/docker-compose.beta.yml"
    fi
    if [[ ! -f "$env_file" && -f "${legacy_dir}/.env.beta" ]]; then
        env_file="${legacy_dir}/.env.beta"
    fi
    [[ -f "$compose_file" ]] || return 0
    if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
        echo "  Stopping legacy stack before migration..."
        docker compose --project-directory "$legacy_dir" -f "$compose_file" \
            --env-file "$env_file" down --remove-orphans 2>/dev/null || true
    fi
}

_bs_normalize_legacy_release_files() {
    local dir="${1:-$_FLOWHUB_CANONICAL_INSTALL_DIR}"
    [[ -d "$dir" ]] || return 0

    if [[ ! -f "${dir}/.env" && -f "${dir}/.env.beta" ]]; then
        echo "  Legacy Compatibility: migrating .env.beta to .env"
        mv "${dir}/.env.beta" "${dir}/.env"
        chown root:root "${dir}/.env" 2>/dev/null || true
        chmod 600 "${dir}/.env" 2>/dev/null || true
    fi

    if [[ ! -f "${dir}/docker-compose.yml" && -f "${dir}/docker-compose.beta.yml" ]]; then
        echo "  Legacy Compatibility: migrating docker-compose.beta.yml to docker-compose.yml"
        mv "${dir}/docker-compose.beta.yml" "${dir}/docker-compose.yml"
    fi
}

_bs_rewrite_legacy_paths() {
    local file
    for file in \
        "${_FLOWHUB_CANONICAL_INSTALL_DIR}/.env" \
        "${_FLOWHUB_CANONICAL_INSTALL_DIR}/storage/config/flowhub.toml" \
        "${_FLOWHUB_CANONICAL_INSTALL_DIR}/storage/config/flowhub.toml"; do
        if [[ -f "$file" ]]; then
            sed -i "s|${_FLOWHUB_LEGACY_INSTALL_DIR}|${_FLOWHUB_CANONICAL_INSTALL_DIR}|g" "$file"
        fi
    done
}

_bs_migrate_legacy_install() {
    [[ "$_FLOWHUB_INSTALL_DIR" == "$_FLOWHUB_CANONICAL_INSTALL_DIR" ]] || return 0
    [[ -d "$_FLOWHUB_LEGACY_INSTALL_DIR" ]] || return 0

    echo ""
    echo "  Legacy Compatibility: FlowHub installation detected at ${_FLOWHUB_LEGACY_INSTALL_DIR}"
    echo "  Canonical installation path is:       ${_FLOWHUB_CANONICAL_INSTALL_DIR}"

    if ! _bs_confirm_legacy_migration; then
        echo "  Migration skipped. Re-run the installer to migrate before first release."
        return 0
    fi

    _bs_stop_legacy_stack
    mkdir -p "$(dirname "$_FLOWHUB_CANONICAL_INSTALL_DIR")"

    if [[ ! -d "$_FLOWHUB_CANONICAL_INSTALL_DIR" ]]; then
        echo "  Moving legacy installation to canonical path..."
        mv "$_FLOWHUB_LEGACY_INSTALL_DIR" "$_FLOWHUB_CANONICAL_INSTALL_DIR"
    else
        echo "  Canonical path already exists; copying missing preserved files from legacy path..."
        local item
        for item in .env .env.beta docker-compose.yml docker-compose.beta.yml storage backups logs; do
            if [[ -e "${_FLOWHUB_LEGACY_INSTALL_DIR}/${item}" && ! -e "${_FLOWHUB_CANONICAL_INSTALL_DIR}/${item}" ]]; then
                cp -a "${_FLOWHUB_LEGACY_INSTALL_DIR}/${item}" "${_FLOWHUB_CANONICAL_INSTALL_DIR}/${item}"
            fi
        done
        rm -rf "$_FLOWHUB_LEGACY_INSTALL_DIR"
    fi

    _bs_normalize_legacy_release_files "$_FLOWHUB_CANONICAL_INSTALL_DIR"
    _bs_rewrite_legacy_paths
    echo "  Legacy installation migrated successfully."
}

_bs_require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        echo "ERROR: Bootstrap must run as root." >&2
        echo "  Run:  sudo bash <(curl -Ls <url>)" >&2
        exit 1
    fi
}

_bs_os_check() {
    [[ -f /etc/os-release ]] || {
        echo "ERROR: Cannot detect OS. Use Ubuntu Server 24.04 LTS or 26.04 LTS." >&2
        exit 1
    }
    # shellcheck source=/dev/null
    . /etc/os-release
    if [[ "${ID:-}" == "ubuntu-core" || "${NAME:-}" == *"Ubuntu Core"* ]]; then
        echo "ERROR: Ubuntu Core is not supported. Use Ubuntu Server 24.04 LTS or 26.04 LTS." >&2
        exit 1
    fi
    if [[ "${ID:-}" == "ubuntu" && ( "${VERSION_ID:-}" == "24.04" || "${VERSION_ID:-}" == "26.04" ) ]]; then
        echo "  OS:   ${PRETTY_NAME:-Ubuntu ${VERSION_ID}} (supported)"
        return 0
    fi
    if [[ "${ID:-}" == "ubuntu" || "${ID:-}" == "debian" || "${ID_LIKE:-}" == *"debian"* ]]; then
        echo "  OS:   ${PRETTY_NAME:-${ID}} (best-effort)"
        if [[ "${FLOWHUB_ASSUME_YES:-}" == "1" ]]; then
            return 0
        fi
        if [[ ! -t 0 ]]; then
            echo "ERROR: Best-effort OS requires interactive confirmation." >&2
            exit 1
        fi
        local answer
        read -r -p "  Continue with best-effort unsupported OS install? [y/N]: " answer
        [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]] || exit 1
        return 0
    fi
    echo "ERROR: Unsupported OS '${ID:-unknown}'. Use Ubuntu Server 24.04 LTS or 26.04 LTS." >&2
    exit 1
}

_bs_arch_check() {
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64)  echo "  Arch: amd64" ;;
        *)
            echo "ERROR: Unsupported architecture '${arch}'. Only amd64/x86_64 is supported." >&2
            exit 1
            ;;
    esac
}

_bs_tool_check() {
    if ! command -v apt-get &>/dev/null; then
        echo "ERROR: apt-get is required. Use Ubuntu Server 24.04 LTS or 26.04 LTS." >&2
        exit 1
    fi
    if ! command -v curl &>/dev/null && ! command -v wget &>/dev/null; then
        echo "ERROR: curl or wget is required for installation." >&2
        exit 1
    fi
}

_bs_install_system_deps() {
    echo "  Installing system packages..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends \
        git curl wget ca-certificates gnupg lsb-release openssl python3 python3-pip
    echo "  System packages installed."
}

# -- Docker installation helpers -----------------------------------------------
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

# Final failure reporter - called when both methods fail.
_docker_install_report_failure() {
    echo "" >&2
    echo "  -- Docker Installation Failed --------------------------------------" >&2
    echo "  Both installation methods failed. Likely causes:" >&2
    echo "    - download.docker.com returned HTTP 403/404 (CDN or geo block)" >&2
    echo "    - Outbound HTTPS blocked by firewall or proxy" >&2
    echo "    - OS codename not yet listed in Docker apt repository" >&2
    echo "  Resolve connectivity, then manually install Docker:" >&2
    echo "    curl -fsSL https://get.docker.com | sh" >&2
    echo "    systemctl enable docker && systemctl start docker" >&2
    echo "  Then re-run: bash installer/install.sh" >&2
    echo "  --------------------------------------------------------------------" >&2
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
    _bs_migrate_legacy_install
    if [[ -d "${_FLOWHUB_INSTALL_DIR}/.git" ]]; then
        echo "  Existing FlowHub repository detected at ${_FLOWHUB_INSTALL_DIR}."
        echo "  Handing off without changing files; the full installer will ask what to do."
    else
        echo "  Cloning FlowHub into ${_FLOWHUB_INSTALL_DIR}..."
        mkdir -p "$(dirname "$_FLOWHUB_INSTALL_DIR")"
        git clone --branch "$_FLOWHUB_BRANCH" --depth 1 \
            "$_FLOWHUB_REPO_URL" "$_FLOWHUB_INSTALL_DIR"
        echo "  Clone complete."
    fi
}

# Bootstrap detection: when piped via bash <(curl ...), BASH_SOURCE[0] is
# /dev/fd/N - its parent directory has no lib/checks.sh.
if [[ ! -f "$(dirname "${BASH_SOURCE[0]:-NONE}")/lib/checks.sh" ]]; then
    echo ""
    echo "========================================================"
    echo "  FlowHub - Bootstrap (one-command install)"
    echo "  Install directory: ${_FLOWHUB_INSTALL_DIR}"
    echo "========================================================"
    echo ""
    _bs_require_root
    _bs_os_check
    _bs_arch_check
    _bs_tool_check
    _bs_install_system_deps
    _bs_install_docker
    _bs_clone_or_pull
    echo ""
    echo "  Handing off to full installer at ${_FLOWHUB_INSTALL_DIR}..."
    echo ""
    exec bash "${_FLOWHUB_INSTALL_DIR}/installer/install.sh" \
        --install-dir "${_FLOWHUB_INSTALL_DIR}" "$@"
fi

# -- Running from a proper repo checkout ---------------------------------------

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

# -- Docker auto-install (non-bootstrap path) ----------------------------------
# Called by step_prerequisites() before run_prerequisite_checks().
# Installs Docker Engine + Compose plugin on Ubuntu/Debian when missing.
# No-op (with warning) if auto-install cannot run; hard-fails if both
# installation methods fail so the installer does not proceed without Docker.
_ensure_docker_installed() {
    if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
        return 0
    fi

    echo ""
    echo "  Docker not found - auto-installing Docker Engine + Compose plugin..."

    if [[ "$(id -u)" -ne 0 ]]; then
        echo "  WARNING: Not running as root - cannot auto-install Docker." >&2
        echo "  Install manually: https://docs.docker.com/engine/install/" >&2
        return 0  # let run_prerequisite_checks() report the [FAIL]
    fi

    if [[ ! -f /etc/os-release ]]; then
        echo "  WARNING: Cannot detect OS - skipping Docker auto-install." >&2
        return 0
    fi
    # shellcheck source=/dev/null
    . /etc/os-release
    if [[ "${ID:-}" == "ubuntu-core" || "${NAME:-}" == *"Ubuntu Core"* ]]; then
        echo "  ERROR: Ubuntu Core is not supported." >&2
        return 1
    fi
    if [[ "${ID:-}" == "ubuntu" && ( "${VERSION_ID:-}" == "24.04" || "${VERSION_ID:-}" == "26.04" ) ]]; then
        :
    elif [[ "${ID:-}" == "ubuntu" || "${ID:-}" == "debian" || "${ID_LIKE:-}" == *"debian"* ]]; then
        echo "  WARNING: OS '${PRETTY_NAME:-${ID:-unknown}}' is best-effort for Docker auto-install." >&2
    else
        echo "  WARNING: OS '${ID:-unknown}' not supported for auto-install - skipping." >&2
        return 0
    fi

    if ! command -v apt-get &>/dev/null; then
        echo "  WARNING: apt-get not found - skipping Docker auto-install." >&2
        return 0
    fi

    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends \
        curl wget ca-certificates gnupg lsb-release

    _docker_install_via_apt && return 0
    _docker_install_via_get_script && return 0
    _docker_install_report_failure
}

# ---- Defaults ----
CANONICAL_INSTALL_DIR="/opt/FlowHub"
LEGACY_INSTALL_DIR="/opt/flowhub" # Legacy Compatibility
INSTALL_DIR="${FLOWHUB_INSTALL_DIR:-${CANONICAL_INSTALL_DIR}}"
DRY_RUN=0
NON_INTERACTIVE=0
ACTION_UNINSTALL=0
ACTION_UPGRADE=0
ACTION_REPAIR=0
ACTION_REINSTALL=0
INSTALLER_ENV_FILE=""
INSTALLER_CREATED_FILES=""   # space-separated, for file rollback

# ---- Argument parsing ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)           DRY_RUN=1 ;;
        --non-interactive)   NON_INTERACTIVE=1 ;;
        --uninstall)         ACTION_UNINSTALL=1 ;;
        --upgrade)           ACTION_UPGRADE=1 ;;
        --repair)            ACTION_REPAIR=1 ;;
        --reinstall)         ACTION_REINSTALL=1 ;;
        --install-dir)       INSTALL_DIR="$2"; shift ;;
        --install-dir=*)     INSTALL_DIR="${1#*=}" ;;
        -h|--help)
            echo "Usage: bash installer/install.sh [--dry-run] [--install-dir DIR] [--non-interactive] [--upgrade] [--repair] [--reinstall] [--uninstall]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
    shift
done

if [[ "$INSTALL_DIR" == "$LEGACY_INSTALL_DIR" ]]; then
    echo "  Legacy install directory requested; using canonical path ${CANONICAL_INSTALL_DIR}."
    INSTALL_DIR="$CANONICAL_INSTALL_DIR"
elif [[ "$INSTALL_DIR" != "$CANONICAL_INSTALL_DIR" ]]; then
    echo "ERROR: FlowHub first release installs only to ${CANONICAL_INSTALL_DIR}." >&2
    exit 1
fi

INSTALLER_ENV_FILE="${INSTALL_DIR}/.env"

# When invoked without an interactive terminal (e.g. piped through
# `bash <(curl ...)` in an automated context, CI, or a provisioning script),
# there is no TTY to drive the wizard prompts. Fall back to non-interactive
# mode with sane defaults instead of blocking forever on `read`.
if [[ "$NON_INTERACTIVE" -eq 0 && ! -t 0 ]]; then
    echo "  No interactive terminal detected - running non-interactively with defaults."
    NON_INTERACTIVE=1
fi

_confirm_legacy_migration() {
    if [[ "$NON_INTERACTIVE" -eq 1 || "${FLOWHUB_ASSUME_YES:-}" == "1" ]]; then
        return 0
    fi
    local answer
    read -r -p "  Migrate legacy installation to ${CANONICAL_INSTALL_DIR}? [Y/n]: " answer
    answer="${answer:-y}"
    [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]]
}

_stop_stack_at_path() {
    local path="$1"
    local compose_file="${path}/docker-compose.yml"
    local env_file="${path}/.env"
    if [[ ! -f "$compose_file" && -f "${path}/docker-compose.beta.yml" ]]; then
        compose_file="${path}/docker-compose.beta.yml"
    fi
    if [[ ! -f "$env_file" && -f "${path}/.env.beta" ]]; then
        env_file="${path}/.env.beta"
    fi
    [[ -f "$compose_file" ]] || return 0
    if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
        echo "  Stopping stack at ${path} before migration..."
        docker compose --project-directory "$path" -f "$compose_file" \
            --env-file "$env_file" down --remove-orphans 2>/dev/null || true
    fi
}

normalize_legacy_release_files() {
    local dir="${1:-$INSTALL_DIR}"
    [[ -d "$dir" ]] || return 0

    if [[ ! -f "${dir}/.env" && -f "${dir}/.env.beta" ]]; then
        echo "  Legacy Compatibility: migrating .env.beta to .env"
        mv "${dir}/.env.beta" "${dir}/.env"
        chown root:root "${dir}/.env" 2>/dev/null || true
        chmod 600 "${dir}/.env" 2>/dev/null || true
    fi

    if [[ ! -f "${dir}/docker-compose.yml" && -f "${dir}/docker-compose.beta.yml" ]]; then
        echo "  Legacy Compatibility: migrating docker-compose.beta.yml to docker-compose.yml"
        mv "${dir}/docker-compose.beta.yml" "${dir}/docker-compose.yml"
    fi
}

_rewrite_legacy_paths() {
    local file
    for file in \
        "${CANONICAL_INSTALL_DIR}/.env" \
        "${CANONICAL_INSTALL_DIR}/storage/config/flowhub.toml" \
        "${CANONICAL_INSTALL_DIR}/storage/config/flowhub.toml"; do
        if [[ -f "$file" ]]; then
            sed -i "s|${LEGACY_INSTALL_DIR}|${CANONICAL_INSTALL_DIR}|g" "$file"
        fi
    done
}

migrate_legacy_installation_if_needed() {
    [[ "$INSTALL_DIR" == "$CANONICAL_INSTALL_DIR" ]] || return 0
    [[ -d "$LEGACY_INSTALL_DIR" ]] || return 0

    echo ""
    echo "  Legacy FlowHub installation detected: ${LEGACY_INSTALL_DIR}"
    echo "  Canonical installation path is:       ${CANONICAL_INSTALL_DIR}"
    echo "  The migration preserves .env, database volumes, uploads, generated secrets, and configuration."

    if ! _confirm_legacy_migration; then
        echo "  Migration skipped. The installer will continue only with ${CANONICAL_INSTALL_DIR}."
        return 0
    fi

    _stop_stack_at_path "$LEGACY_INSTALL_DIR"
    mkdir -p "$(dirname "$CANONICAL_INSTALL_DIR")"

    if [[ ! -d "$CANONICAL_INSTALL_DIR" ]]; then
        echo "  Moving legacy installation to canonical path..."
        mv "$LEGACY_INSTALL_DIR" "$CANONICAL_INSTALL_DIR"
    else
        echo "  Canonical path already exists; copying missing preserved files from legacy path..."
        local item
        for item in .env .env.beta docker-compose.yml docker-compose.beta.yml storage backups logs; do
            if [[ -e "${LEGACY_INSTALL_DIR}/${item}" && ! -e "${CANONICAL_INSTALL_DIR}/${item}" ]]; then
                cp -a "${LEGACY_INSTALL_DIR}/${item}" "${CANONICAL_INSTALL_DIR}/${item}"
            fi
        done
        rm -rf "$LEGACY_INSTALL_DIR"
    fi

    normalize_legacy_release_files "$CANONICAL_INSTALL_DIR"
    _rewrite_legacy_paths
    INSTALL_DIR="$CANONICAL_INSTALL_DIR"
    INSTALLER_ENV_FILE="${INSTALL_DIR}/.env"
    REPO_DIR="$CANONICAL_INSTALL_DIR"
    echo "  Legacy installation migrated successfully."
}

if [[ "$DRY_RUN" -eq 0 ]]; then
    migrate_legacy_installation_if_needed
    normalize_legacy_release_files "$INSTALL_DIR"
fi

# Defaults applied when running non-interactively (wizard skipped). Secrets are
# generated separately by generate_all_secrets. Only sets vars not already set,
# so explicit FLOWHUB_*/FLOWHUB_* environment overrides are respected.
apply_noninteractive_defaults() {
    : "${FLOWHUB_DOMAIN:=localhost}"
    : "${FLOWHUB_PORT:=8085}"
    : "${FLOWHUB_SSL_MODE:=off}"
    : "${FLOWHUB_POSTGRES_DB:=flowhub}"
    : "${FLOWHUB_POSTGRES_USER:=flowhub}"
    : "${FLOWHUB_NEXTCLOUD_URL:=}"
    : "${FLOWHUB_NEXTCLOUD_FILE_PATH:=}"
    : "${FLOWHUB_NEXTCLOUD_USERNAME:=}"
    : "${FLOWHUB_NEXTCLOUD_PASSWORD:=}"
    : "${FLOWHUB_WOOCOMMERCE_URL:=}"
    : "${FLOWHUB_WOOCOMMERCE_KEY:=}"
    : "${FLOWHUB_WOOCOMMERCE_SECRET:=}"
    : "${FLOWHUB_TIMEZONE:=UTC}"
    : "${FLOWHUB_CURRENCY:=USD}"
    : "${FLOWHUB_ADMIN_USERNAME:=admin}"
    : "${FLOWHUB_ADMIN_EMAIL:=admin@example.com}"
    : "${FLOWHUB_STORAGE_PATH:=${INSTALL_DIR}/storage}"
    : "${FLOWHUB_BACKUP_PATH:=${INSTALL_DIR}/backups}"
    export FLOWHUB_DOMAIN FLOWHUB_PORT FLOWHUB_SSL_MODE FLOWHUB_POSTGRES_DB FLOWHUB_POSTGRES_USER \
        FLOWHUB_NEXTCLOUD_URL FLOWHUB_NEXTCLOUD_FILE_PATH FLOWHUB_NEXTCLOUD_USERNAME FLOWHUB_NEXTCLOUD_PASSWORD \
        FLOWHUB_WOOCOMMERCE_URL FLOWHUB_WOOCOMMERCE_KEY FLOWHUB_WOOCOMMERCE_SECRET \
        FLOWHUB_TIMEZONE FLOWHUB_CURRENCY FLOWHUB_ADMIN_USERNAME FLOWHUB_ADMIN_EMAIL \
        FLOWHUB_STORAGE_PATH FLOWHUB_BACKUP_PATH
    echo "  Non-interactive defaults applied (domain=${FLOWHUB_DOMAIN}, port=${FLOWHUB_PORT}, db=${FLOWHUB_POSTGRES_DB})."
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
    echo "  To diagnose: docker compose -f ${INSTALL_DIR}/docker-compose.yml logs"
    echo "  To retry:    re-run install.sh"
    exit "$exit_code"
}
trap 'on_error $LINENO' ERR

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

print_banner() {
    echo ""
    echo "========================================================"
    echo "  FlowHub Installer  v1.0.0-bu1"
    echo ""
    echo "  Runs in complete isolation - no other installations are affected."
    echo ""
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  *** DRY-RUN MODE - No files will be written, no Docker started ***"
    fi
    echo "========================================================"
}

# ---------------------------------------------------------------------------
# Idempotency - detect existing installation
# ---------------------------------------------------------------------------

detect_existing_installation() {
    [[ -f "${INSTALLER_ENV_FILE}" ]]
}

handle_existing_installation() {
    echo ""
    echo "  Existing FlowHub installation detected."
    echo "  Environment file: ${INSTALLER_ENV_FILE}"
    echo ""
    echo "  Select an action:"
    echo ""
    echo "  1. Upgrade    - rebuild images, run migrations, restart services"
    echo "  2. Repair     - re-run prerequisite checks, migrations, and health verification"
    echo "  3. Reinstall  - regenerate configuration, rebuild, migrate, and restart"
    echo "  4. Exit"
    echo ""
    local choice
    read -r -p "  Enter choice [1-4]: " choice
    case "${choice:-}" in
        1) step_upgrade ;;
        2) step_repair ;;
        3) step_reconfigure ;;
        4|"")
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

step_update_repository() {
    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        echo ""
        echo "  Updating repository..."
        git -C "$INSTALL_DIR" pull --ff-only origin main
    fi
}

# ---- Upgrade path (keeps existing .env) ----
step_upgrade() {
    echo ""
    echo "========================================================"
    echo "  Upgrade: rebuilding images and restarting services"
    echo "========================================================"
    step_update_repository
    _load_env_for_docker
    step_docker_launch
    step_database_init
    step_create_admin
    step_install_cli
    step_health_check
    step_completion_report
}

# ---- Repair path ----
step_repair() {
    echo ""
    echo "========================================================"
    echo "  Repair: re-checking prerequisites and health"
    echo "========================================================"
    _load_env_for_docker

    # Verify .env exists
    if [[ ! -f "${INSTALLER_ENV_FILE}" ]]; then
        echo "  ERROR: ${INSTALLER_ENV_FILE} not found. Cannot repair without environment file." >&2
        echo "  Run a fresh install instead: bash installer/install.sh" >&2
        return 1
    fi
    echo "  Environment file: ${INSTALLER_ENV_FILE} [OK]"

    step_prerequisites

    # Verify Docker Compose stack is reachable
    local compose_file="${INSTALL_DIR}/docker-compose.yml"
    if [[ -f "$compose_file" ]]; then
        local dc_cmd
        if docker compose version &>/dev/null 2>&1; then dc_cmd="docker compose"
        else dc_cmd="docker-compose"; fi
        echo ""
        echo "  Checking container status..."
        ${dc_cmd} --project-directory "$INSTALL_DIR" -f "$compose_file" --env-file "${INSTALLER_ENV_FILE}" ps 2>/dev/null || true
    fi

    step_database_init
    step_install_cli
    step_health_check

    echo ""
    _load_env_for_docker
    local port="${FLOWHUB_PORT:-8085}"
    local domain="${FLOWHUB_DOMAIN:-localhost}"
    local ssl_mode="${FLOWHUB_SSL_MODE:-off}"
    local public_url
    public_url="$(_build_public_url "$domain" "$port" "$ssl_mode")"
    echo "========================================================"
    echo "  Repair complete."
    echo ""
    echo "  FlowHub is available at: ${public_url}"
    echo "  Setup wizard:            ${public_url}/setup"
    echo "  Sign in:                 ${public_url}/login"
    echo "========================================================"
}

# ---- Reconfigure path ----
step_reconfigure() {
    echo ""
    echo "========================================================"
    echo "  Reconfigure: wizard will regenerate .env"
    echo "  EXISTING .env WILL BE OVERWRITTEN after confirmation."
    echo "========================================================"
    if [[ "$ACTION_REINSTALL" -ne 1 && "$NON_INTERACTIVE" -ne 1 && "${FLOWHUB_ASSUME_YES:-}" != "1" ]]; then
        local confirm
        read -r -p "  Continue? Secrets will be regenerated. [y/N]: " confirm
        if [[ "${confirm,,}" != "y" && "${confirm,,}" != "yes" ]]; then
            echo "  Reconfiguration cancelled."
            exit 0
        fi
    fi
    step_wizard
    step_secrets
    step_env_file
    step_storage
    step_docker_launch
    step_database_init
    step_create_admin
    step_install_cli
    step_health_check
    step_completion_report
}

# Load .env into shell for use by Docker deploy functions
_load_env_for_docker() {
    if [[ -f "${INSTALLER_ENV_FILE}" ]]; then
        # Export only FLOWHUB_* vars; skip comments and blank lines
        while IFS='=' read -r key value; do
            [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
            [[ "$key" =~ ^FLOWHUB_ ]] && export "$key=$value"
        done < <(grep -E '^FLOWHUB_' "${INSTALLER_ENV_FILE}" 2>/dev/null || true)
    fi
}

# ---------------------------------------------------------------------------
# Installation steps
# ---------------------------------------------------------------------------

step_prerequisites() {
    echo ""
    echo "Step 1 - Prerequisite Checks"
    _ensure_docker_installed
    run_prerequisite_checks "$INSTALL_DIR"
}

step_wizard() {
    if [[ "$NON_INTERACTIVE" -eq 0 ]]; then
        echo ""
        echo "Step 2 - Admin Account Setup"
        run_wizard
        # Fill remaining FLOWHUB_* defaults not asked by the wizard
        apply_noninteractive_defaults
    else
        echo ""
        echo "Step 2 - Non-interactive configuration (applying defaults)"
        apply_noninteractive_defaults
    fi
}

step_secrets() {
    echo ""
    echo "Step 3 - Secret Generation"
    generate_all_secrets
}

step_env_file() {
    echo ""
    echo "Step 4 - Environment File Generation"
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
    echo "Step 5 - Storage Directory Setup"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would create:"
        echo "  ${FLOWHUB_STORAGE_PATH:-/opt/FlowHub/storage}/{logs,config,plugins,uploads,diagnostics}"
        echo "  ${FLOWHUB_BACKUP_PATH:-/opt/FlowHub/backups}"
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
    echo "Step 6 - Managed Configuration File"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would write: ${FLOWHUB_STORAGE_PATH:-/opt/FlowHub/storage}/config/flowhub.toml"
        return
    fi
    # installer_core imports app.flowhub.config which requires Python deps installed
    # on the host. Skip gracefully if not available - Docker stack uses .env.
    if ! python3 - <<PYEOF 2>/dev/null
import sys
sys.path.insert(0, "${REPO_DIR}")
from installer.installer_core import InstallerConfig, generate_toml_content, write_toml_config
from pathlib import Path

config = InstallerConfig(
    domain="${FLOWHUB_DOMAIN:-}",
    port=int("${FLOWHUB_PORT:-8085}"),
    ssl_mode="${FLOWHUB_SSL_MODE:-off}",
    postgres_db="${FLOWHUB_POSTGRES_DB:-flowhub}",
    postgres_user="${FLOWHUB_POSTGRES_USER:-flowhub}",
    storage_path="${FLOWHUB_STORAGE_PATH:-/opt/FlowHub/storage}",
    backup_path="${FLOWHUB_BACKUP_PATH:-/opt/FlowHub/backups}",
    log_level="INFO",
)
content = generate_toml_content(config)
config_dir = Path("${FLOWHUB_STORAGE_PATH:-/opt/FlowHub/storage}/config")
config_dir.mkdir(parents=True, exist_ok=True)
path = write_toml_config(content, config_dir)
print(f"  Managed config written: {path}")
PYEOF
    then
        echo "  NOTE: TOML config skipped (Python app dependencies not on host)."
        echo "  Docker stack reads .env directly - no impact on operation."
    fi
}

step_compose_verify() {
    echo ""
    echo "Step 7 - Docker Compose Verification"
    local compose_file="${INSTALL_DIR}/docker-compose.yml"
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
        echo "  ERROR: docker-compose.yml not found at ${INSTALL_DIR}" >&2
        echo "  Ensure the repository was cloned to ${INSTALL_DIR}" >&2
        return 1
    fi
}

step_docker_launch() {
    echo ""
    echo "Step 8 - Docker Stack Launch"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would run: docker compose up -d --build"
        return
    fi
    _load_env_for_docker
    build_and_start_services "$INSTALL_DIR"
}

step_database_init() {
    echo ""
    echo "Step 9 - Database Initialization"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would wait for PostgreSQL, then run: alembic -c alembic_flowhub.ini upgrade head"
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

detect_flowhub_operator_user() {
    local candidate="${FLOWHUB_OPERATOR_USER:-${SUDO_USER:-}}"
    if [[ -n "$candidate" && "$candidate" != "root" ]] && id "$candidate" >/dev/null 2>&1; then
        echo "$candidate"
        return 0
    fi

    if getent group flowhub >/dev/null 2>&1; then
        candidate="$(getent group flowhub | awk -F: '{ split($4, users, ","); print users[1] }')"
        if [[ -n "$candidate" && "$candidate" != "root" ]] && id "$candidate" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    fi

    for env_candidate in "${LOGNAME:-}" "${USER:-}"; do
        if [[ -n "$env_candidate" && "$env_candidate" != "root" ]] && id "$env_candidate" >/dev/null 2>&1; then
            echo "$env_candidate"
            return 0
        fi
    done

    candidate="$(awk -F: '$3 >= 1000 && $1 != "nobody" { print $1; exit }' /etc/passwd 2>/dev/null || true)"
    if [[ -n "$candidate" && "$candidate" != "root" ]] && id "$candidate" >/dev/null 2>&1; then
        echo "$candidate"
        return 0
    fi

    if [[ -t 0 ]]; then
        while true; do
            read -r -p "  Linux operator username for flowhub CLI access (blank to skip): " candidate
            candidate="${candidate:-}"
            if [[ -z "$candidate" ]]; then
                return 1
            fi
            if [[ -n "$candidate" && "$candidate" != "root" ]] && id "$candidate" >/dev/null 2>&1; then
                echo "$candidate"
                return 0
            fi
            echo "  '${candidate}' is not an existing non-root Linux user. Try: getent passwd <username>" >&2
        done
    fi

    return 1
}

step_install_cli() {
    echo ""
    echo "Step 10 - Install flowhub CLI"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would install: /usr/local/bin/flowhub"
        echo "  [DRY RUN] Would install: /usr/local/lib/flowhub/flowhub-helper"
        echo "  [DRY RUN] Would install: /etc/sudoers.d/flowhub"
        return
    fi
    local wrapper_src="${REPO_DIR}/scripts/flowhub"
    local helper_src="${REPO_DIR}/scripts/flowhub-helper"
    local wrapper_dst="/usr/local/bin/flowhub"
    local helper_dir="/usr/local/lib/flowhub"
    local helper_dst="${helper_dir}/flowhub-helper"
    local sudoers_dst="/etc/sudoers.d/flowhub"
    local operator_user=""
    local sudoers_tmp

    if [[ ! -f "$wrapper_src" || ! -f "$helper_src" ]]; then
        echo "  WARNING: CLI wrapper/helper not found in ${REPO_DIR}/scripts - skipping" >&2
        return
    fi

    if [[ "${EUID}" -ne 0 ]]; then
        echo "  WARNING: CLI privileged helper requires root installer access - skipping" >&2
        echo "  Re-run with: sudo ./installer/install.sh --repair" >&2
        return
    fi

    install -d -o root -g root -m 0755 "$helper_dir"
    install -o root -g root -m 0755 "$wrapper_src" "$wrapper_dst"
    install -o root -g root -m 0755 "$helper_src" "$helper_dst"

    if getent group flowhub >/dev/null 2>&1; then
        :
    else
        groupadd --system flowhub
    fi
    if operator_user="$(detect_flowhub_operator_user)"; then
        usermod -aG flowhub "$operator_user"
    else
        echo "  WARNING: Could not determine a non-root operator user for flowhub CLI access." >&2
        echo "  Set FLOWHUB_OPERATOR_USER=<username> and run: sudo ./installer/install.sh --repair" >&2
    fi

    if [[ -f "${REPO_DIR}/.env" ]]; then
        chown root:root "${REPO_DIR}/.env"
        chmod 600 "${REPO_DIR}/.env"
    fi

    sudoers_tmp="$(mktemp)"
    {
        echo "# FlowHub operator helper. Managed by installer/install.sh."
        echo "Cmnd_Alias FLOWHUB_HELPER = ${helper_dst}"
        echo "%flowhub ALL=(root) NOPASSWD: FLOWHUB_HELPER"
        if [[ -n "$operator_user" && "$operator_user" != "root" ]] && id "$operator_user" >/dev/null 2>&1; then
            echo "${operator_user} ALL=(root) NOPASSWD: FLOWHUB_HELPER"
        fi
    } > "$sudoers_tmp"
    chmod 0440 "$sudoers_tmp"
    if command -v visudo >/dev/null 2>&1; then
        visudo -cf "$sudoers_tmp" >/dev/null
    fi
    install -o root -g root -m 0440 "$sudoers_tmp" "$sudoers_dst"
    rm -f "$sudoers_tmp"

    echo "  CLI installed: ${wrapper_dst}"
    echo "  Privileged helper installed: ${helper_dst}"
    echo "  Sudoers allowlist installed: ${sudoers_dst}"
    if [[ -n "$operator_user" ]]; then
        echo "  Operator authorized: ${operator_user} (group: flowhub)"
    fi
    echo "  .env permissions: root:root 600"
    echo "  If group membership is not visible in an existing shell, open a new shell session."
    echo "  Test with: flowhub --help"
}

step_health_check() {
    echo ""
    echo "Step 11 - Health Verification"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [DRY RUN] Would verify: http://localhost:${FLOWHUB_PORT:-8085}/api/health"
        return
    fi
    _load_env_for_docker
    local port="${FLOWHUB_PORT:-8085}"
    wait_for_app_healthy "$port" 24
    verify_health_endpoint "$port"
}

# Build the user-facing public URL from domain, port, and SSL mode.
# First-release URL contract includes the configured panel port for all modes.
_build_public_url() {
    local domain="${1:-localhost}"
    local port="${2:-8085}"
    local ssl_mode="${3:-off}"
    case "$ssl_mode" in
        letsencrypt|manual)
            echo "https://${domain}:${port}"
            ;;
        self-signed)
            echo "https://${domain}:${port}"
            ;;
        off|*)
            echo "http://${domain}:${port}"
            ;;
    esac
}

step_completion_report() {
    echo ""
    echo "========================================================"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  FlowHub - Dry Run Complete"
        echo "  No files were written. No Docker was started."
        echo "  Review the output above for a preview of what would happen."
    else
        _load_env_for_docker
        local port="${FLOWHUB_PORT:-8085}"
        local domain="${FLOWHUB_DOMAIN:-localhost}"
        local ssl_mode="${FLOWHUB_SSL_MODE:-off}"
        local public_url
        public_url="$(_build_public_url "$domain" "$port" "$ssl_mode")"
        echo "  FlowHub - Installation Complete"
        echo ""
        echo "  +-----------------------------------------------------+"
        echo "  |  Open your browser and complete setup:              |"
        echo "  |                                                     |"
        echo "  |    ${public_url}/setup"
        echo "  |                                                     |"
        echo "  |  The web wizard will guide you through:             |"
        echo "  |    - Server profile (domain, timezone, currency)    |"
        echo "  |    - Database verification                          |"
        echo "  |    * Admin account and finish                       |"
        echo "  |                                                     |"
        echo "  |  Admin username: ${FLOWHUB_ADMIN_USERNAME:-admin}"
        echo "  |  Sign in at:     ${public_url}/login"
        echo "  +-----------------------------------------------------+"
        echo ""
        echo "  Public URL:           ${public_url}"
        echo "  Internal Docker Port: ${port}"
        echo "  Environment file:     ${INSTALLER_ENV_FILE}"
        echo "  Health check:         ${public_url}/api/health"
        echo ""
        echo "  Management:"
        echo "    flowhub              - interactive management menu"
        echo "    flowhub status       - configuration status"
        echo "    flowhub health       - local health checks"
        echo "    flowhub diagnostics run - full integration check"
        echo ""
        echo "  Docker:"
        echo "    docker compose -f ${INSTALL_DIR}/docker-compose.yml ps"
        echo "    docker compose -f ${INSTALL_DIR}/docker-compose.yml logs -f app"
    fi
    echo "========================================================"
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
    if [[ "$ACTION_UPGRADE" -eq 1 ]]; then
        step_upgrade
        return
    fi
    if [[ "$ACTION_REPAIR" -eq 1 ]]; then
        step_repair
        return
    fi
    if [[ "$ACTION_REINSTALL" -eq 1 ]]; then
        step_reconfigure
        return
    fi

    # Idempotency check - detect existing installation before starting.
    # Non-interactive mode with an existing .env defaults to upgrade to
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
