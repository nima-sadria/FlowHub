#!/usr/bin/env bash
# FlowHub â€” Interactive uninstaller (lib/uninstall.sh)
#
# Source from install.sh. Provides:
#   run_uninstall INSTALL_DIR
#
# Interactive, safe, idempotent. Removes ONLY FlowHub resources.
# Never touches flowhub or unrelated Docker projects.
# Missing resources are silently skipped (not a fatal error).

set -euo pipefail

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Ask a yes/no question; prints "y" or "n".
# $1 = prompt text   $2 = default (y|n, default n)
_uninstall_ask_yn() {
    local prompt="$1"
    local default="${2:-n}"
    local hint
    [[ "$default" == "y" ]] && hint="[Y/n]" || hint="[y/N]"
    local ans
    read -r -p "    ${prompt} ${hint}: " ans
    case "${ans,,}" in
        y|yes) echo "y" ;;
        n|no)  echo "n" ;;
        "")    echo "$default" ;;
        *)     echo "n" ;;
    esac
}

# ---------------------------------------------------------------------------
# run_uninstall
# ---------------------------------------------------------------------------

run_uninstall() {
    local install_dir="${1:-/opt/FlowHub}"
    local env_file="${install_dir}/.env.beta"
    local compose_file="${install_dir}/docker-compose.beta.yml"
    local cli_path="/usr/local/bin/flowhub"
    local project_name
    project_name="flowhub"

    # â”€â”€ Step 1: Warning â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    echo ""
    echo "â”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پ"
    echo "  UNINSTALL â€” FlowHub"
    echo "â”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پ"
    echo ""
    echo "  WARNING: FlowHub and all selected resources will be removed."
    echo ""
    echo "  Scope: ONLY FlowHub resources"
    echo "    Docker project : ${project_name}"
    echo "    Install dir    : ${install_dir}"
    echo "    CLI            : ${cli_path}"
    echo ""
    echo "  flowhub and all other Docker projects are NOT affected."
    echo ""

    # â”€â”€ Step 2: Selection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    echo "  What should be removed? Answer y/N for each item."
    echo ""
    echo "  Docker resources:"
    local rm_containers rm_images rm_volumes rm_network
    rm_containers="$(_uninstall_ask_yn "Stop and remove Docker containers"                              "y")"
    rm_images="$(    _uninstall_ask_yn "Remove FlowHub Docker images"                                   "y")"
    rm_volumes="$(   _uninstall_ask_yn "Remove FlowHub Docker volumes  [database data will be lost]"    "y")"
    rm_network="$(   _uninstall_ask_yn "Remove FlowHub Docker network"                                  "y")"
    echo ""
    echo "  Files and directories:"
    local rm_project_dir rm_cli rm_systemd rm_config rm_logs rm_backups
    rm_project_dir="$(_uninstall_ask_yn "Remove project directory (${install_dir})"                     "y")"
    rm_cli="$(        _uninstall_ask_yn "Remove CLI (${cli_path})"                                      "y")"
    rm_systemd="$(    _uninstall_ask_yn "Remove systemd services (if any)"                              "y")"
    rm_config="$(     _uninstall_ask_yn "Remove generated configuration (.env.beta + TOML)"             "y")"
    rm_logs="$(       _uninstall_ask_yn "Remove logs (${install_dir}/logs)"                             "y")"
    rm_backups="$(    _uninstall_ask_yn "Remove backups  [OFF by default] (${install_dir}/backups)"     "n")"

    # At least one item must be selected
    local any_selected=0
    for _v in "$rm_containers" "$rm_images" "$rm_volumes" "$rm_network" \
              "$rm_project_dir" "$rm_cli" "$rm_systemd" "$rm_config" \
              "$rm_logs" "$rm_backups"; do
        [[ "$_v" == "y" ]] && any_selected=1 && break
    done
    if [[ "$any_selected" -eq 0 ]]; then
        echo ""
        echo "  Nothing selected â€” exiting without changes."
        return 0
    fi

    # â”€â”€ Step 3: Confirmation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    echo ""
    echo "  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€"
    echo "  The following will be permanently removed:"
    [[ "$rm_containers"  == "y" ]] && echo "    â€¢ Docker containers (project: ${project_name})"
    [[ "$rm_images"      == "y" ]] && echo "    â€¢ Docker images (project: ${project_name})"
    [[ "$rm_volumes"     == "y" ]] && echo "    â€¢ Docker volumes â€” ALL database data will be lost"
    [[ "$rm_network"     == "y" ]] && echo "    â€¢ Docker network (project: ${project_name})"
    [[ "$rm_project_dir" == "y" ]] && echo "    â€¢ Project directory: ${install_dir}"
    [[ "$rm_cli"         == "y" ]] && echo "    â€¢ CLI: ${cli_path}"
    [[ "$rm_systemd"     == "y" ]] && echo "    â€¢ Systemd services (flowhub*)"
    [[ "$rm_config"      == "y" ]] && echo "    â€¢ Configuration: .env.beta + TOML"
    [[ "$rm_logs"        == "y" ]] && echo "    â€¢ Logs: ${install_dir}/logs"
    [[ "$rm_backups"     == "y" ]] && echo "    â€¢ Backups: ${install_dir}/backups"
    echo "  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€"
    echo ""
    echo "  This action CANNOT be undone."
    echo "  To confirm, type exactly:  UNINSTALL"
    echo ""
    local confirm
    read -r -p "  > " confirm
    if [[ "$confirm" != "UNINSTALL" ]]; then
        echo ""
        echo "  Confirmation not received â€” uninstall cancelled."
        return 0
    fi

    # â”€â”€ Step 4: Execute â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    echo ""
    echo "â”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پ"
    echo "  Removing FlowHub resources..."
    echo "â”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پ"
    echo ""

    local -a removed=()
    local -a preserved=()

    # Resolve compose command
    local docker_ok=0
    local dc_cmd=""
    if command -v docker &>/dev/null; then
        docker_ok=1
        if docker compose version &>/dev/null 2>&1; then
            dc_cmd="docker compose"
        elif command -v docker-compose &>/dev/null; then
            dc_cmd="docker-compose"
        fi
    fi

    # â”€â”€ Containers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if [[ "$rm_containers" == "y" ]]; then
        printf "  Stopping and removing containers..."
        if [[ "$docker_ok" -eq 1 ]]; then
            if [[ -n "$dc_cmd" && -f "$compose_file" ]]; then
                ${dc_cmd} --project-directory "$install_dir" -f "$compose_file" \
                    down --remove-orphans 2>/dev/null || true
            else
                # Fallback: find containers by compose project label
                local _cids
                _cids="$(docker container ls -aq \
                    --filter "label=com.docker.compose.project=${project_name}" \
                    2>/dev/null || true)"
                if [[ -n "$_cids" ]]; then
                    # shellcheck disable=SC2086
                    docker container stop $_cids 2>/dev/null || true
                    # shellcheck disable=SC2086
                    docker container rm   $_cids 2>/dev/null || true
                fi
            fi
        fi
        removed+=("containers")
        echo " done"
    else
        # If containers are kept but volumes will be removed, stop the stack
        # first so the volumes are not in use (stop â‰  remove).
        if [[ "$rm_volumes" == "y" && "$docker_ok" -eq 1 && -n "$dc_cmd" && -f "$compose_file" ]]; then
            printf "  Stopping stack (needed before volume removal)..."
            ${dc_cmd} --project-directory "$install_dir" -f "$compose_file" \
                stop 2>/dev/null || true
            echo " done"
        fi
        # Track preserved containers only if any exist
        if [[ "$docker_ok" -eq 1 ]]; then
            local _running
            _running="$(docker container ls -aq \
                --filter "label=com.docker.compose.project=${project_name}" \
                2>/dev/null | grep -c . || true)"
            [[ "${_running:-0}" -gt 0 ]] && preserved+=("containers (still running)")
        fi
    fi

    # â”€â”€ Images â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if [[ "$rm_images" == "y" ]]; then
        printf "  Removing Docker images..."
        if [[ "$docker_ok" -eq 1 ]]; then
            local _img_ids=""
            # Primary: images reported by compose
            if [[ -n "$dc_cmd" && -f "$compose_file" ]]; then
                _img_ids="$(${dc_cmd} --project-directory "$install_dir" \
                    -f "$compose_file" images -q 2>/dev/null || true)"
            fi
            # Secondary: images bearing the project build label
            local _labeled
            _labeled="$(docker image ls -q \
                --filter "label=com.docker.compose.project=${project_name}" \
                2>/dev/null || true)"
            # Merge, deduplicate, remove blanks
            local _all_imgs
            _all_imgs="$(printf '%s\n%s\n' "$_img_ids" "$_labeled" \
                | sort -u | grep -v '^$' || true)"
            if [[ -n "$_all_imgs" ]]; then
                # shellcheck disable=SC2086
                docker image rm -f $_all_imgs 2>/dev/null || true
            fi
        fi
        removed+=("images")
        echo " done"
    fi

    # â”€â”€ Volumes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if [[ "$rm_volumes" == "y" ]]; then
        printf "  Removing Docker volumes..."
        if [[ "$docker_ok" -eq 1 ]]; then
            local _vols
            _vols="$(docker volume ls -q \
                --filter "label=com.docker.compose.project=${project_name}" \
                2>/dev/null || true)"
            if [[ -n "$_vols" ]]; then
                # shellcheck disable=SC2086
                docker volume rm $_vols 2>/dev/null || true
            fi
        fi
        removed+=("volumes")
        echo " done"
    fi

    # â”€â”€ Network â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if [[ "$rm_network" == "y" ]]; then
        printf "  Removing Docker network..."
        if [[ "$docker_ok" -eq 1 ]]; then
            local _nets
            _nets="$(docker network ls -q \
                --filter "label=com.docker.compose.project=${project_name}" \
                2>/dev/null || true)"
            if [[ -n "$_nets" ]]; then
                # shellcheck disable=SC2086
                docker network rm $_nets 2>/dev/null || true
            fi
        fi
        removed+=("network")
        echo " done"
    fi

    # â”€â”€ CLI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if [[ "$rm_cli" == "y" ]]; then
        if [[ -f "$cli_path" ]]; then
            printf "  Removing CLI (%s)..." "$cli_path"
            rm -f "$cli_path" 2>/dev/null || true
            removed+=("CLI (${cli_path})")
            echo " done"
        fi
    else
        [[ -f "$cli_path" ]] && preserved+=("CLI (${cli_path})")
    fi

    # â”€â”€ Systemd services â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if [[ "$rm_systemd" == "y" ]]; then
        local _found_svc=0
        local _svc
        for _svc in flowhub flowhub-beta flowhub-worker; do
            if systemctl list-unit-files 2>/dev/null \
                    | grep -q "^${_svc}\.service"; then
                printf "  Removing systemd service (%s)..." "$_svc"
                systemctl stop    "$_svc" 2>/dev/null || true
                systemctl disable "$_svc" 2>/dev/null || true
                rm -f "/etc/systemd/system/${_svc}.service" 2>/dev/null || true
                removed+=("systemd: ${_svc}.service")
                _found_svc=1
                echo " done"
            fi
        done
        [[ "$_found_svc" -eq 1 ]] && systemctl daemon-reload 2>/dev/null || true
    fi

    # â”€â”€ Generated configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if [[ "$rm_config" == "y" ]]; then
        printf "  Removing configuration..."
        rm -f "$env_file" 2>/dev/null || true
        rm -f "${install_dir}/storage/config/flowhub.toml" 2>/dev/null || true
        rm -f "${install_dir}/storage/config/flowhub-beta.toml" 2>/dev/null || true
        removed+=("configuration (.env.beta)")
        echo " done"
    else
        [[ -f "$env_file" ]] && preserved+=("configuration (${env_file})")
    fi

    # â”€â”€ Logs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if [[ "$rm_logs" == "y" ]]; then
        if [[ -d "${install_dir}/logs" ]]; then
            printf "  Removing logs..."
            rm -rf "${install_dir}/logs" 2>/dev/null || true
            removed+=("logs")
            echo " done"
        fi
    else
        [[ -d "${install_dir}/logs" ]] && preserved+=("logs (${install_dir}/logs)")
    fi

    # â”€â”€ Backups â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if [[ "$rm_backups" == "y" ]]; then
        if [[ -d "${install_dir}/backups" ]]; then
            printf "  Removing backups..."
            rm -rf "${install_dir}/backups" 2>/dev/null || true
            removed+=("backups")
            echo " done"
        fi
    else
        [[ -d "${install_dir}/backups" ]] && preserved+=("backups (${install_dir}/backups)")
    fi

    # â”€â”€ Project directory (last â€” compose file lives here) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if [[ "$rm_project_dir" == "y" ]]; then
        if [[ -d "$install_dir" ]]; then
            printf "  Removing project directory (%s)..." "$install_dir"
            rm -rf "$install_dir" 2>/dev/null || true
            removed+=("project directory (${install_dir})")
            echo " done"
        fi
    else
        [[ -d "$install_dir" ]] && preserved+=("project directory (${install_dir})")
    fi

    # â”€â”€ Step 5: Summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    echo ""
    echo "â”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پ"
    echo "  Uninstall Complete"
    echo "â”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پ"
    echo ""
    if [[ "${#removed[@]}" -gt 0 ]]; then
        echo "  Removed:"
        local _item
        for _item in "${removed[@]}"; do
            echo "    â€¢ ${_item}"
        done
    else
        echo "  Nothing was removed (resources were already absent)."
    fi
    if [[ "${#preserved[@]}" -gt 0 ]]; then
        echo ""
        echo "  Preserved:"
        for _item in "${preserved[@]}"; do
            echo "    â€¢ ${_item}"
        done
    fi
    echo ""
    echo "  To reinstall FlowHub:"
    echo "    bash installer/install.sh"
    echo "â”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پâ”پ"
}
