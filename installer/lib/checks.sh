#!/usr/bin/env bash
# FlowHub - Prerequisite checks
#
# Source this file from install.sh. Call run_prerequisite_checks().
# Prints PASS/FAIL for each check. Returns 1 if any check fails.
# No Docker execution. No network connections. Command availability only.

set -euo pipefail

CHECKS_FAILED=0

_check_pass() { printf "  [PASS] %s\n" "$1"; }
_check_fail() { printf "  [FAIL] %s\n  Fix: %s\n" "$1" "$2"; CHECKS_FAILED=1; }
_check_warn() { printf "  [WARN] %s\n" "$1"; }

_confirm_best_effort_os() {
    if [[ "${FLOWHUB_ASSUME_YES:-}" == "1" ]]; then
        return 0
    fi
    if [[ ! -t 0 ]]; then
        return 1
    fi
    local answer
    read -r -p "  Continue with best-effort unsupported OS install? [y/N]: " answer
    [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]]
}

check_os_support() {
    if [[ ! -f /etc/os-release ]]; then
        _check_fail "OS detection failed" "Use Ubuntu Server 24.04 LTS or 26.04 LTS."
        return
    fi
    # shellcheck source=/dev/null
    . /etc/os-release
    if [[ "${ID:-}" == "ubuntu-core" || "${NAME:-}" == *"Ubuntu Core"* ]]; then
        _check_fail "Ubuntu Core is not supported" "Use Ubuntu Server 24.04 LTS or 26.04 LTS."
        return
    fi
    if [[ "${ID:-}" == "ubuntu" && ( "${VERSION_ID:-}" == "24.04" || "${VERSION_ID:-}" == "26.04" ) ]]; then
        _check_pass "OS supported: ${PRETTY_NAME:-Ubuntu ${VERSION_ID}}"
        return
    fi
    if [[ "${ID:-}" == "ubuntu" || "${ID:-}" == "debian" || "${ID_LIKE:-}" == *"debian"* ]]; then
        _check_warn "OS best-effort only: ${PRETTY_NAME:-${ID:-unknown}}"
        if _confirm_best_effort_os; then
            _check_pass "Best-effort OS confirmation accepted"
        else
            _check_fail "Best-effort OS confirmation declined" "Use Ubuntu Server 24.04 LTS or 26.04 LTS."
        fi
        return
    fi
    _check_fail "Unsupported OS: ${PRETTY_NAME:-${ID:-unknown}}" "Use Ubuntu Server 24.04 LTS or 26.04 LTS."
}

check_apt_get_command() {
    if command -v apt-get &>/dev/null; then
        _check_pass "apt-get found: $(command -v apt-get)"
    else
        _check_fail "apt-get not found" "Use a Debian/Ubuntu server with apt-get available."
    fi
}

check_download_command() {
    if command -v curl &>/dev/null || command -v wget &>/dev/null; then
        local found=()
        command -v curl &>/dev/null && found+=("curl")
        command -v wget &>/dev/null && found+=("wget")
        _check_pass "download tool found: ${found[*]}"
    else
        _check_fail "curl or wget not found" "Install curl or wget with apt-get."
    fi
}

check_python_version() {
    local required_major=3 required_minor=10
    if ! command -v python3 &>/dev/null; then
        _check_fail "Python 3.10+ not found" "Install Python 3.10: https://www.python.org/downloads/"
        return
    fi
    local version
    version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local major minor
    IFS='.' read -r major minor <<< "$version"
    if [[ "$major" -gt "$required_major" ]] || \
       { [[ "$major" -eq "$required_major" ]] && [[ "$minor" -ge "$required_minor" ]]; }; then
        _check_pass "Python ${version} (>= ${required_major}.${required_minor} required)"
    else
        _check_fail "Python ${version} is too old" \
            "Install Python ${required_major}.${required_minor}+: https://www.python.org/downloads/"
    fi
}

check_docker_command() {
    if command -v docker &>/dev/null; then
        _check_pass "docker command found: $(command -v docker)"
    else
        _check_fail "docker not found in PATH" \
            "Install Docker: https://docs.docker.com/get-docker/"
    fi
}

check_docker_compose_command() {
    if command -v docker-compose &>/dev/null; then
        _check_pass "docker-compose found: $(command -v docker-compose)"
    elif command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
        _check_pass "docker compose plugin available"
    else
        _check_fail "docker compose not found" \
            "Install Docker Compose: https://docs.docker.com/compose/install/"
    fi
}

check_openssl_command() {
    if command -v openssl &>/dev/null; then
        _check_pass "openssl found: $(command -v openssl)"
    else
        _check_fail "openssl not found in PATH" \
            "Install openssl (Debian/Ubuntu: apt install openssl)"
    fi
}

check_system_requirements() {
    local install_dir="${1:-/}"
    local arch cpu_count mem_kb disk_kb
    arch="$(uname -m)"
    case "$arch" in
        x86_64) _check_pass "Architecture supported: ${arch}" ;;
        *) _check_fail "Unsupported architecture: ${arch}" "Use an x86_64/amd64 Linux host." ;;
    esac

    cpu_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 0)"
    if [[ "$cpu_count" -ge 2 ]]; then
        _check_pass "CPU cores: ${cpu_count}"
    else
        _check_fail "At least 2 CPU cores recommended" "Resize the server before installing FlowHub."
    fi

    mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
    if [[ "$mem_kb" -ge 3900000 ]]; then
        _check_pass "Memory: $((mem_kb / 1024)) MB"
    else
        _check_fail "At least 4 GB RAM recommended" "Resize the server before installing FlowHub."
    fi

    local disk_target="$install_dir"
    [[ -e "$disk_target" ]] || disk_target="$(dirname "$install_dir")"
    disk_kb="$(df -Pk "$disk_target" 2>/dev/null | awk 'NR==2 {print $4}')"
    if [[ "${disk_kb:-0}" -ge 20000000 ]]; then
        _check_pass "Free disk: $((disk_kb / 1024)) MB"
    else
        _check_fail "At least 20 GB free disk required" "Free disk space or use a larger server volume."
    fi
}

check_write_permission() {
    local target_dir="$1"
    local check_dir="$target_dir"
    if [[ ! -e "$target_dir" ]]; then
        check_dir="$(dirname "$target_dir")"
    fi
    if [[ -w "$check_dir" ]]; then
        _check_pass "Write permission: ${target_dir}"
    else
        _check_fail "No write permission: ${target_dir}" \
            "Run: chmod u+w $(dirname "$target_dir") or choose a different directory"
    fi
}

run_prerequisite_checks() {
    local install_dir="${1:-}"
    CHECKS_FAILED=0

    echo "========================================================"
    echo "  Prerequisite Checks"
    echo "========================================================"
    check_os_support
    check_apt_get_command
    check_download_command
    check_system_requirements "${install_dir:-/}"
    check_python_version
    check_docker_command
    check_docker_compose_command
    check_openssl_command
    if [[ -n "$install_dir" ]]; then
        check_write_permission "$install_dir"
    fi
    echo "========================================================"

    if [[ "$CHECKS_FAILED" -ne 0 ]]; then
        echo "  ERROR: One or more prerequisite checks failed."
        echo "  Resolve the issues above and re-run install.sh."
        return 1
    fi
    echo "  All prerequisite checks passed."
    return 0
}
