#!/usr/bin/env bash
# FlowHub Beta — Installer wizard
#
# Source from install.sh. Call run_wizard to populate admin credential variables.
# Asks only what the installer cannot default: admin username, email, password.
# All other settings (domain, port, DB, secrets, storage) use safe defaults and
# can be changed later from the web Setup Wizard.

set -euo pipefail

_prompt_plain() {
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

_prompt_password() {
    local var_name="$1" description="$2"
    local value
    read -r -s -p "  ${description}: " value
    echo ""
    printf -v "$var_name" '%s' "$value"
}

_section() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

wizard_section_admin() {
    _section "Admin Account"
    echo "  Create the administrator account you will use to sign in."
    echo ""

    _prompt_plain BETA_ADMIN_USERNAME "Admin username" "admin"

    while true; do
        local raw_email
        read -r -p "  Admin email: " raw_email
        raw_email="${raw_email// /}"
        if [[ -z "$raw_email" ]]; then
            echo "  ERROR: Email is required." >&2
            continue
        fi
        BETA_ADMIN_EMAIL="$raw_email"
        break
    done

    while true; do
        _prompt_password BETA_ADMIN_PASSWORD "Admin password (min 8 characters)"
        if [[ ${#BETA_ADMIN_PASSWORD} -lt 8 ]]; then
            echo "  ERROR: Password must be at least 8 characters." >&2
            continue
        fi
        local confirm_pass
        _prompt_password confirm_pass "Confirm password"
        if [[ "$BETA_ADMIN_PASSWORD" != "$confirm_pass" ]]; then
            echo "  ERROR: Passwords do not match. Try again." >&2
            continue
        fi
        break
    done
}

wizard_section_confirm() {
    _section "Confirm Installation"
    echo ""
    echo "  The following admin account will be created:"
    echo "    Username : ${BETA_ADMIN_USERNAME}"
    echo "    Email    : ${BETA_ADMIN_EMAIL}"
    echo "    Password : ●●●●●●●●"
    echo ""
    echo "  All other settings use defaults and can be changed in the web Setup Wizard."
    echo "    Install directory : ${INSTALL_DIR:-/opt/FlowHub}"
    echo "    Port              : 8085"
    echo "    Database name     : flowhub"
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
    echo "  FlowHub Beta — Installer"
    echo "  [BETA ENVIRONMENT — NOT PRODUCTION]"
    echo "  Press Ctrl+C at any time to abort. No files will be written until"
    echo "  you confirm at the end."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    wizard_section_admin
    wizard_section_confirm
}
