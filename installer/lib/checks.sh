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
        x86_64|aarch64) _check_pass "Architecture supported: ${arch}" ;;
        *) _check_fail "Unsupported architecture: ${arch}" "Use an amd64 or arm64 Linux host." ;;
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
