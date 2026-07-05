#!/usr/bin/env bash
# FlowHub - Installer wizard
#
# Source from install.sh. Call run_wizard before generating runtime defaults.
# The installer does not create administrator accounts. First-admin creation
# happens only in the web Setup Wizard after the application is running.

set -euo pipefail

_section() {
    echo ""
    echo "========================================================"
    echo "  $1"
    echo "========================================================"
}

wizard_section_confirm() {
    _section "Confirm Installation"
    echo ""
    echo "  FlowHub will be installed with runtime defaults."
    echo "  No administrator account will be created by the installer."
    echo "  Create the first administrator in the web Setup Wizard."
    echo ""
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
    echo "========================================================"
    echo "  FlowHub - Installer"
    echo "  First public release"
    echo "  Press Ctrl+C at any time to abort. No files will be written until"
    echo "  you confirm at the end."
    echo "========================================================"

    wizard_section_confirm
}
