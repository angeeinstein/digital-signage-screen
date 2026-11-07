#!/usr/bin/env bash
################################################################################
# Digital Signage (aviation dashboard) - install / update / repair / uninstall
#
#   curl -fsSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/install.sh | sudo bash
#
# Options (all optional):
#   --update | --repair | --uninstall   run that action without the menu
#   --branch NAME                       git branch to install (default: main; updates keep the installed one)
#   --user NAME                         user the service runs as
#   --port N                            HTTP port of the app (default: 8080)
#   --nginx | --no-nginx                put nginx on port 80 in front (asks if omitted)
#   --kiosk | --no-kiosk                set up the kiosk browser on this Pi's desktop (asks if omitted)
#   --kiosk-user NAME                   desktop user for the kiosk (default: detected)
#   --yes                               don't ask questions, use defaults
#
# Environment: SIGNAGE_REPO overrides the git URL (CI uses a local checkout),
# SIGNAGE_USER sets the service user.
#
# Runtime state (settings, password, caches) lives in $INSTALL_DIR/data, which
# git never touches, so updates cannot lose it.
################################################################################
set -euo pipefail

INSTALL_DIR="/opt/digital-signage"
DATA_DIR="$INSTALL_DIR/data"
VENV_DIR="$INSTALL_DIR/venv"
SERVICE_NAME="digital-signage"
REPO_URL="${SIGNAGE_REPO:-https://github.com/angeeinstein/digital-signage-screen.git}"
BRANCH="main"
BRANCH_SET=0
PORT="8080"
NODE_MAJOR_MIN=20      # Vite needs Node >= 20.19
NODE_SETUP_MAJOR=22    # LTS line installed from NodeSource when needed
ACTION=""
USE_NGINX=""
ASSUME_YES=0
SERVICE_USER="${SIGNAGE_USER:-}"
USE_KIOSK=""
KIOSK_USER=""
KIOSK_NEEDS_REBOOT=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
die()     { echo -e "${RED}[FAIL]${NC} $*" >&2; exit 1; }
header()  { echo -e "\n${GREEN}== $* ==${NC}"; }

ask() {  # ask "question" default -> echoes answer
    local q="$1" def="$2" ans=""
    if [[ $ASSUME_YES -eq 1 ]] || [[ ! -r /dev/tty ]]; then echo "$def"; return; fi
    read -r -p "$q " ans < /dev/tty || true
    echo "${ans:-$def}"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --update) ACTION="update" ;;
            --repair) ACTION="repair" ;;
            --uninstall) ACTION="uninstall" ;;
            --branch) BRANCH="$2"; BRANCH_SET=1; shift ;;
            --user) SERVICE_USER="$2"; shift ;;
            --port) PORT="$2"; shift ;;
            --nginx) USE_NGINX="yes" ;;
            --no-nginx) USE_NGINX="no" ;;
            --kiosk) USE_KIOSK="yes" ;;
            --no-kiosk) USE_KIOSK="no" ;;
            --kiosk-user) KIOSK_USER="$2"; shift ;;
            --yes|-y) ASSUME_YES=1 ;;
            -h|--help) echo "See the header of install.sh for options."; exit 0 ;;
            *) die "Unknown option: $1" ;;
        esac
        shift
    done
}

################################################################################
# Checks
################################################################################

require_root() {
    [[ $EUID -eq 0 ]] || die "Please run as root: sudo bash install.sh"
}

detect_user() {
    if [[ -n "$SERVICE_USER" ]]; then :
    elif [[ -f /etc/systemd/system/$SERVICE_NAME.service ]] \
        && grep -q '^User=' "/etc/systemd/system/$SERVICE_NAME.service"; then
        SERVICE_USER="$(sed -n 's/^User=//p' "/etc/systemd/system/$SERVICE_NAME.service" | head -1)"
    elif [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
        SERVICE_USER="$SUDO_USER"
    elif id pi &>/dev/null; then
        SERVICE_USER="pi"
    else
        SERVICE_USER="signage"
    fi
    if ! id "$SERVICE_USER" &>/dev/null; then
        info "Creating system user '$SERVICE_USER'"
        useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    fi
    SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
    info "Service will run as $SERVICE_USER:$SERVICE_GROUP"
}

is_installed() { [[ -d "$INSTALL_DIR/.git" ]]; }

################################################################################
# Steps
################################################################################

install_packages() {
    header "System packages"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-pip git curl ca-certificates >/dev/null
    ok "Python and git installed ($(python3 --version))"
    install_node
}

node_major() { command -v node >/dev/null && node -v | sed 's/^v\([0-9]*\).*/\1/' || echo 0; }

install_node() {
    if [[ "$(node_major)" -ge $NODE_MAJOR_MIN ]] && command -v npm >/dev/null; then
        ok "Node.js $(node -v) already installed"
        return
    fi
    info "Trying Node.js from the distribution..."
    apt-get install -y -qq nodejs npm >/dev/null 2>&1 || true
    if [[ "$(node_major)" -ge $NODE_MAJOR_MIN ]] && command -v npm >/dev/null; then
        ok "Node.js $(node -v) installed"
        return
    fi
    info "Distribution Node.js is too old ($(node -v 2>/dev/null || echo none)); installing Node.js $NODE_SETUP_MAJOR LTS from NodeSource"
    apt-get remove -y -qq nodejs npm >/dev/null 2>&1 || true
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_SETUP_MAJOR}.x" | bash - >/dev/null
    apt-get install -y -qq nodejs >/dev/null
    [[ "$(node_major)" -ge $NODE_MAJOR_MIN ]] || die "Could not install Node.js >= $NODE_MAJOR_MIN"
    ok "Node.js $(node -v) installed"
}

# Move v1 runtime files (next to app.py) into data/legacy so the app can migrate
# them, and recover credentials that the old updater stashed away by mistake.
preserve_legacy_state() {
    mkdir -p "$DATA_DIR/legacy"
    local f
    for f in dashboard_config.json admin_auth.json flight_routes_cache.json; do
        if [[ -f "$INSTALL_DIR/$f" && ! -f "$DATA_DIR/legacy/$f" ]]; then
            cp -p "$INSTALL_DIR/$f" "$DATA_DIR/legacy/$f"
            info "Preserved legacy $f"
        fi
    done
    if [[ ! -f "$DATA_DIR/auth.json" && ! -f "$DATA_DIR/legacy/admin_auth.json" && -d "$INSTALL_DIR/.git" ]]; then
        # v1's updater ran `git stash -u`, which swallowed admin_auth.json.
        local ref
        for ref in $(git -C "$INSTALL_DIR" stash list --format='%gd' 2>/dev/null); do
            if git -C "$INSTALL_DIR" show "${ref}^3:admin_auth.json" > "$DATA_DIR/legacy/admin_auth.json" 2>/dev/null; then
                ok "Recovered admin credentials from $ref (lost by an earlier update)"
                break
            fi
            rm -f "$DATA_DIR/legacy/admin_auth.json"
        done
    fi
}

backup_data() {
    [[ -d "$DATA_DIR" ]] || return 0
    local dest
    dest="/var/backups/digital-signage/$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$dest"
    cp -a "$DATA_DIR/." "$dest/"
    chmod 700 "$(dirname "$dest")"
    # keep the 5 newest backups (names are timestamps, so ls is safe)
    # shellcheck disable=SC2012
    ls -1dt /var/backups/digital-signage/*/ 2>/dev/null | tail -n +6 | xargs -r rm -rf
    ok "Backed up settings to $dest"
}

fetch_code() {
    git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null || true
    if is_installed; then
        # Stay on the installed branch and remote unless told otherwise.
        if [[ $BRANCH_SET -eq 0 ]]; then
            BRANCH="$(git -C "$INSTALL_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
        fi
        if [[ -z "${SIGNAGE_REPO:-}" ]]; then
            REPO_URL="$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null || echo "$REPO_URL")"
        fi
    fi
    header "Application code ($BRANCH)"
    if is_installed; then
        preserve_legacy_state
        backup_data
        git -C "$INSTALL_DIR" remote set-url origin "$REPO_URL"
        git -C "$INSTALL_DIR" fetch --quiet origin "$BRANCH"
        # --force: v1 tracked runtime files (dashboard_config.json, content/)
        # that were edited in place. They are already in data/legacy and the
        # backup above, so local changes to tracked files can be discarded.
        git -C "$INSTALL_DIR" checkout --quiet --force -B "$BRANCH" "origin/$BRANCH"
        git -C "$INSTALL_DIR" reset --quiet --hard "origin/$BRANCH"
        ok "Updated to $(git -C "$INSTALL_DIR" log -1 --format='%h %s')"
    else
        if [[ -d "$INSTALL_DIR" ]] && [[ -n "$(ls -A "$INSTALL_DIR")" ]]; then
            die "$INSTALL_DIR exists but is not a git checkout. Move it away first."
        fi
        git clone --quiet --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
        ok "Cloned $(git -C "$INSTALL_DIR" log -1 --format='%h %s')"
    fi
    mkdir -p "$DATA_DIR"
}

setup_python() {
    header "Python environment"
    [[ -x "$VENV_DIR/bin/python" ]] || python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
    ok "Python packages installed"
}

build_frontend() {
    header "Frontend build"
    local fe="$INSTALL_DIR/frontend"
    # Build next to the served frontend and swap it in at once: the running
    # dashboard keeps serving the old one meanwhile.
    rm -rf "$fe/dist.new" "$fe/dist.old"
    (cd "$fe" && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent -- --outDir dist.new) \
        || die "Frontend build failed (see output above)"
    [[ -f "$fe/dist.new/index.html" ]] || die "Frontend build produced no index.html"
    if [[ -d "$fe/dist" ]]; then mv "$fe/dist" "$fe/dist.old"; fi
    mv "$fe/dist.new" "$fe/dist"
    rm -rf "$fe/dist.old"
    rm -rf "$fe/node_modules/.cache"
    ok "Frontend built"
}

choose_nginx() {
    if [[ -z "$USE_NGINX" ]]; then
        if [[ -f /etc/nginx/sites-enabled/$SERVICE_NAME ]]; then
            USE_NGINX="yes"
        else
            local a
            a="$(ask "Serve the dashboard on port 80 via nginx? [y/N]" n)"
            [[ "$a" =~ ^[Yy] ]] && USE_NGINX="yes" || USE_NGINX="no"
        fi
    fi
}

setup_nginx() {
    if [[ "$USE_NGINX" != "yes" ]]; then
        if [[ -f /etc/nginx/sites-enabled/$SERVICE_NAME ]]; then
            rm -f "/etc/nginx/sites-enabled/$SERVICE_NAME"
            systemctl reload nginx 2>/dev/null || true
            info "Removed nginx site"
        fi
        return
    fi
    header "nginx"
    apt-get install -y -qq nginx >/dev/null
    cat > "/etc/nginx/sites-available/$SERVICE_NAME" <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    client_max_body_size 12m;  # announcement images, up to 10 MB
    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }
}
EOF
    ln -sf "/etc/nginx/sites-available/$SERVICE_NAME" "/etc/nginx/sites-enabled/$SERVICE_NAME"
    rm -f /etc/nginx/sites-enabled/default
    nginx -t >/dev/null 2>&1 || die "nginx configuration test failed (run: nginx -t)"
    systemctl enable --quiet nginx
    systemctl restart nginx
    ok "nginx serves port 80 -> 127.0.0.1:$PORT"
}

install_service() {
    header "systemd service"
    local bind="0.0.0.0:$PORT" proxied=0
    if [[ "$USE_NGINX" == "yes" ]]; then bind="127.0.0.1:$PORT"; proxied=1; fi
    sed -e "s|@USER@|$SERVICE_USER|g" \
        -e "s|@GROUP@|$SERVICE_GROUP|g" \
        -e "s|@INSTALL_DIR@|$INSTALL_DIR|g" \
        -e "s|@DATA_DIR@|$DATA_DIR|g" \
        -e "s|@BIND@|$bind|g" \
        -e "s|@PROXIED@|$proxied|g" \
        "$INSTALL_DIR/digital-signage.service" > "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    systemctl enable --quiet "$SERVICE_NAME"
    ok "Service installed (listening on $bind)"
}

set_permissions() {
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    chmod 750 "$DATA_DIR"
    find "$DATA_DIR" -type f -exec chmod 640 {} +
    [[ -f "$DATA_DIR/auth.json" ]] && chmod 600 "$DATA_DIR/auth.json"
    [[ -f "$DATA_DIR/secret_key" ]] && chmod 600 "$DATA_DIR/secret_key"
    return 0
}

start_and_check() {
    header "Starting"
    systemctl restart "$SERVICE_NAME"
    local _
    for _ in $(seq 1 30); do
        if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
            ok "Dashboard is up"
            return 0
        fi
        sleep 1
    done
    journalctl -u "$SERVICE_NAME" -n 60 --no-pager || true
    die "The service did not become healthy. Logs are shown above."
}

summary() {
    local ip url
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    if [[ "$USE_NGINX" == "yes" ]]; then url="http://${ip}"; else url="http://${ip}:$PORT"; fi
    echo
    echo -e "${GREEN}Digital Signage is running.${NC}"
    echo "  Display:  $url/"
    echo "  Admin:    $url/admin"
    if [[ ! -f "$DATA_DIR/auth.json" ]] || grep -q '"must_change": true' "$DATA_DIR/auth.json" 2>/dev/null; then
        echo -e "  ${YELLOW}Login with admin / admin and change the password right away.${NC}"
    fi
    echo
    echo "  Logs:     sudo journalctl -u $SERVICE_NAME -f"
    echo "  Restart:  sudo systemctl restart $SERVICE_NAME"
    echo "  Update:   sudo bash $INSTALL_DIR/install.sh --update"
    if [[ $KIOSK_NEEDS_REBOOT -eq 1 ]]; then
        echo
        echo -e "  ${YELLOW}Reboot to start the kiosk helper: sudo reboot${NC}"
    fi
    echo
}

################################################################################
# Actions
################################################################################

# Chromium policy for the kiosk browser on this machine (only affects pages on
# localhost, i.e. the dashboard itself):
# - WebRtcLocalIpsAllowedUrls: screen sharing connects laptops directly to the
#   Pi. Browsers normally hide their local IP behind an mDNS name, which can't
#   be resolved on networks that block mDNS; the dashboard may show the real IP.
# - AutoplayAllowed: shared screens with sound start without a click.
CHROMIUM_POLICY_DIRS=(/etc/chromium/policies/managed /etc/chromium-browser/policies/managed)

install_browser_policy() {
    local dir
    for dir in "${CHROMIUM_POLICY_DIRS[@]}"; do
        mkdir -p "$dir"
        cat > "$dir/$SERVICE_NAME.json" <<'EOF'
{
  "WebRtcLocalIpsAllowedUrls": ["http://localhost", "http://localhost:*", "http://127.0.0.1", "http://127.0.0.1:*"],
  "AutoplayAllowed": true
}
EOF
        chmod 644 "$dir/$SERVICE_NAME.json"
    done
    ok "Browser policy for screen sharing installed (restart the kiosk browser to apply)"
}

remove_browser_policy() {
    local dir
    for dir in "${CHROMIUM_POLICY_DIRS[@]}"; do
        rm -f "$dir/$SERVICE_NAME.json"
    done
}

################################################################################
# Kiosk: browser autostart + helper (crash recovery, remote control)
################################################################################

KIOSK_SUDOERS="/etc/sudoers.d/$SERVICE_NAME-kiosk"
KIOSK_DESKTOP_NAME="$SERVICE_NAME-kiosk.desktop"
KIOSK_MARK="# digital-signage kiosk helper"

kiosk_home() { getent passwd "$1" | cut -d: -f6; }

detect_kiosk_user() {
    # The user running the desktop session (not necessarily the service user).
    [[ -n "$KIOSK_USER" ]] && return 0
    KIOSK_USER="$(ps -o user= -C labwc,wayfire,lxsession,openbox 2>/dev/null | head -1 | tr -d ' ')" || true
    if [[ -z "$KIOSK_USER" && -f "$KIOSK_SUDOERS" ]]; then
        KIOSK_USER="$(awk '{print $1; exit}' "$KIOSK_SUDOERS")"
    fi
}

choose_kiosk() {
    detect_kiosk_user
    if [[ -z "$USE_KIOSK" ]]; then
        if [[ -f "$KIOSK_SUDOERS" ]]; then
            USE_KIOSK="yes"   # set up before: keep it up to date
        elif [[ -z "$KIOSK_USER" ]]; then
            USE_KIOSK="no"    # no desktop session (headless or CI)
        else
            local a
            a="$(ask "Set up the kiosk browser for '$KIOSK_USER' (autostart, crash recovery, remote control from admin)? [Y/n]" y)"
            if [[ "$a" =~ ^[Nn] ]]; then USE_KIOSK="no"; else USE_KIOSK="yes"; fi
        fi
    fi
    if [[ "$USE_KIOSK" == "yes" && -z "$KIOSK_USER" ]]; then
        warn "No desktop user found; use --kiosk-user NAME. Skipping kiosk setup."
        USE_KIOSK="no"
    fi
}

# Comment out autostart lines that start Chromium on the dashboard, so the
# browser doesn't run twice. Each changed file is backed up once.
disable_old_kiosk() {
    local home="$1" f
    for f in "$home/.config/labwc/autostart" "$home/.config/wayfire.ini" \
             "$home/.config/lxsession/LXDE-pi/autostart" \
             /etc/xdg/labwc/autostart /etc/xdg/lxsession/LXDE-pi/autostart; do
        [[ -f "$f" ]] || continue
        if grep -vE '^[[:space:]]*#' "$f" | grep -iE 'chrom' | grep -qE 'localhost|127\.0\.0\.1'; then
            [[ -f "$f.before-signage-kiosk" ]] || cp -p "$f" "$f.before-signage-kiosk"
            sed -i -E '/^[[:space:]]*#/! { /[Cc]hrom/ { /localhost|127\.0\.0\.1/ { /kiosk\/agent\.py/! s/^/# disabled by digital-signage (the kiosk helper starts the browser now): / } } }' "$f"
            info "Disabled the old browser autostart in $f (backup: $f.before-signage-kiosk)"
        fi
    done
    for f in "$home"/.config/autostart/*.desktop /etc/xdg/autostart/*.desktop; do
        [[ -f "$f" && "$(basename "$f")" != "$KIOSK_DESKTOP_NAME" ]] || continue
        if grep -iE '^Exec=.*chrom' "$f" | grep -qE 'localhost|127\.0\.0\.1'; then
            mv "$f" "$f.disabled-by-signage"
            info "Disabled the old autostart entry $f"
        fi
    done
    for f in "$home"/.config/systemd/user/*.service; do
        [[ -f "$f" ]] || continue
        if grep -iE '^ExecStart=.*chrom' "$f" | grep -qE 'localhost|127\.0\.0\.1'; then
            warn "$f also starts the browser. Disable it, or the browser may run twice."
        fi
    done
    return 0
}

setup_kiosk() {
    header "Kiosk"
    local home cmd tmp
    home="$(kiosk_home "$KIOSK_USER")"
    [[ -n "$home" && -d "$home" ]] || { warn "Home of '$KIOSK_USER' not found; skipping kiosk setup"; return 0; }
    command -v grim >/dev/null || apt-get install -y -qq grim >/dev/null 2>&1 \
        || warn "Could not install grim (needed for screenshots in admin)"
    disable_old_kiosk "$home"

    cmd="/usr/bin/python3 $INSTALL_DIR/kiosk/agent.py --url http://localhost:$PORT"
    # XDG autostart (Raspberry Pi OS desktop with labwc or LXDE) ...
    sudo -u "$KIOSK_USER" mkdir -p "$home/.config/autostart"
    cat > "$home/.config/autostart/$KIOSK_DESKTOP_NAME" <<EOF
[Desktop Entry]
Type=Application
Name=Digital Signage kiosk
Comment=Starts the dashboard in Chromium and keeps it running
Exec=$cmd
X-GNOME-Autostart-enabled=true
EOF
    chown "$KIOSK_USER:" "$home/.config/autostart/$KIOSK_DESKTOP_NAME"
    # ... and a user labwc autostart, which replaces the system one when it exists.
    # The helper allows only one instance, so starting it twice is harmless.
    if [[ -f "$home/.config/labwc/autostart" ]]; then
        sed -i "/kiosk\/agent\.py/d" "$home/.config/labwc/autostart"
        printf '%s &  %s\n' "$cmd" "$KIOSK_MARK" >> "$home/.config/labwc/autostart"
    fi

    # Let the helper reboot the Pi (admin page button), and nothing else.
    tmp="$(mktemp)"
    echo "$KIOSK_USER ALL=(root) NOPASSWD: /usr/bin/systemctl reboot" > "$tmp"
    if visudo -cf "$tmp" >/dev/null; then
        install -m 440 "$tmp" "$KIOSK_SUDOERS"
    else
        warn "Could not set up the reboot permission"
    fi
    rm -f "$tmp"

    if pgrep -u "$KIOSK_USER" -f kiosk/agent.py >/dev/null; then
        ok "Kiosk helper updated for '$KIOSK_USER' (takes effect after the next reboot)"
    else
        ok "Kiosk helper set up for '$KIOSK_USER'"
        KIOSK_NEEDS_REBOOT=1
    fi
}

remove_kiosk() {
    detect_kiosk_user
    [[ -n "$KIOSK_USER" ]] || return 0
    local home
    home="$(kiosk_home "$KIOSK_USER")"
    rm -f "$home/.config/autostart/$KIOSK_DESKTOP_NAME" "$KIOSK_SUDOERS"
    [[ -f "$home/.config/labwc/autostart" ]] && sed -i "/kiosk\/agent\.py/d" "$home/.config/labwc/autostart"
    pkill -u "$KIOSK_USER" -f kiosk/agent.py 2>/dev/null || true
    info "Kiosk helper removed. Your previous autostart files were kept as *.before-signage-kiosk / *.disabled-by-signage."
}

################################################################################
# Updates from the admin page
################################################################################
# The app can't run this installer (it runs unprivileged). It creates
# data/update-request; a path unit sees the file and starts the update
# service as root, which runs the newest installer and logs to UPDATE_LOG.

UPDATE_SCRIPT="/usr/local/lib/$SERVICE_NAME/self-update.sh"
UPDATE_LOG_DIR="/var/log/$SERVICE_NAME"

install_update_service() {
    mkdir -p "$(dirname "$UPDATE_SCRIPT")" "$UPDATE_LOG_DIR"
    chmod 755 "$UPDATE_LOG_DIR"
    # This runs during an update started by that very script: write a new file
    # and rename it over the old one, so the running bash keeps reading the
    # old file (bash reads scripts while executing them).
    local tmp="$UPDATE_SCRIPT.new"
    cat > "$tmp" <<'EOF'
#!/bin/bash
# Started by digital-signage-update.service (admin page -> "Update now").
# Everything is inside main(), so bash has read the whole script before it
# runs any of it.
set -uo pipefail
main() {
    local DIR="@INSTALL_DIR@" LOG="@LOG_DIR@/update.log" SCRIPT="/run/@SERVICE_NAME@-install.sh" BRANCH rc
    rm -f "@DATA_DIR@/update-request"
    exec >"$LOG" 2>&1
    chmod 644 "$LOG"
    echo "Update started $(date '+%Y-%m-%d %H:%M:%S')"
    git_() { git -c safe.directory="$DIR" -C "$DIR" "$@"; }
    BRANCH="$(git_ rev-parse --abbrev-ref HEAD)"
    # Run a copy of the newest installer: the update replaces install.sh while it runs.
    if git_ fetch --quiet origin "$BRANCH" && git_ show "origin/$BRANCH:install.sh" > "$SCRIPT"; then
        echo "Using the newest installer from branch $BRANCH"
    else
        echo "Could not fetch the newest installer; using the installed one"
        cp "$DIR/install.sh" "$SCRIPT"
    fi
    bash "$SCRIPT" --update --yes --branch "$BRANCH" --port "@PORT@"
    rc=$?
    rm -f "$SCRIPT"
    echo "@@RESULT $rc $(date +%s)"
    exit "$rc"
}
main "$@"
EOF
    sed -i -e "s|@INSTALL_DIR@|$INSTALL_DIR|g" -e "s|@DATA_DIR@|$DATA_DIR|g" -e "s|@LOG_DIR@|$UPDATE_LOG_DIR|g" \
        -e "s|@SERVICE_NAME@|$SERVICE_NAME|g" -e "s|@PORT@|$PORT|g" "$tmp"
    chmod 755 "$tmp"
    mv -f "$tmp" "$UPDATE_SCRIPT"

    cat > "/etc/systemd/system/$SERVICE_NAME-update.service" <<EOF
[Unit]
Description=Digital Signage update (requested from the admin page)

[Service]
Type=oneshot
ExecStart=$UPDATE_SCRIPT
TimeoutStartSec=30min
EOF
    # PathExists, and the script deletes the request first: one update per request.
    cat > "/etc/systemd/system/$SERVICE_NAME-update.path" <<EOF
[Unit]
Description=Watch for update requests from the Digital Signage admin page

[Path]
PathExists=$DATA_DIR/update-request
Unit=$SERVICE_NAME-update.service

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --quiet "$SERVICE_NAME-update.path"
    systemctl start "$SERVICE_NAME-update.path" 2>/dev/null || true
    ok "Updates from the admin page enabled"
}

remove_update_service() {
    systemctl disable --now "$SERVICE_NAME-update.path" 2>/dev/null || true
    rm -f "/etc/systemd/system/$SERVICE_NAME-update.path" "/etc/systemd/system/$SERVICE_NAME-update.service" \
        "$UPDATE_SCRIPT"
    systemctl daemon-reload
}

do_install() {
    detect_user
    install_packages
    fetch_code
    setup_python
    build_frontend
    choose_nginx
    install_service
    install_update_service
    setup_nginx
    install_browser_policy
    choose_kiosk
    [[ "$USE_KIOSK" == "yes" ]] && setup_kiosk
    set_permissions
    start_and_check
    summary
}

do_update() {
    detect_user
    install_node
    # v2 keeps running (on the code it has loaded) until start_and_check
    # restarts it, so the admin page can show the update's progress. Only v1,
    # which writes its settings into the checkout, is stopped first.
    if [[ ! -d "$INSTALL_DIR/signage" ]]; then systemctl stop "$SERVICE_NAME" 2>/dev/null || true; fi
    fetch_code
    setup_python
    build_frontend
    choose_nginx
    install_service
    install_update_service
    setup_nginx
    install_browser_policy
    choose_kiosk
    [[ "$USE_KIOSK" == "yes" ]] && setup_kiosk
    set_permissions
    start_and_check
    summary
}

do_repair() {
    detect_user
    setup_python
    [[ -f "$INSTALL_DIR/frontend/dist/index.html" ]] || build_frontend
    choose_nginx
    install_service
    install_update_service
    setup_nginx
    install_browser_policy
    choose_kiosk
    [[ "$USE_KIOSK" == "yes" ]] && setup_kiosk
    set_permissions
    start_and_check
    summary
}

do_uninstall() {
    local a
    a="$(ask "Remove Digital Signage including all settings? Type 'yes' to confirm:" no)"
    [[ "$a" == "yes" ]] || { info "Cancelled"; exit 0; }
    backup_data || true
    systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    if [[ -f /etc/nginx/sites-enabled/$SERVICE_NAME ]]; then
        rm -f "/etc/nginx/sites-enabled/$SERVICE_NAME" "/etc/nginx/sites-available/$SERVICE_NAME"
        systemctl reload nginx 2>/dev/null || true
    fi
    remove_browser_policy
    remove_kiosk
    remove_update_service
    rm -rf "$INSTALL_DIR"
    ok "Uninstalled. A backup of your settings is in /var/backups/digital-signage/"
}

menu() {
    echo
    echo "Existing installation found in $INSTALL_DIR"
    echo "  ($(git -C "$INSTALL_DIR" log -1 --format='%h, %cd' --date=short 2>/dev/null || echo unknown version))"
    echo
    echo "  1) Update (keeps settings)"
    echo "  2) Repair (reinstall service, permissions, dependencies)"
    echo "  3) Uninstall"
    echo "  4) Cancel"
    case "$(ask "Choice [1]:" 1)" in
        1) ACTION="update" ;;
        2) ACTION="repair" ;;
        3) ACTION="uninstall" ;;
        *) info "Cancelled"; exit 0 ;;
    esac
}

main() {
    parse_args "$@"
    require_root
    if [[ -z "$ACTION" ]]; then
        if is_installed; then menu; else ACTION="install"; fi
    fi
    case "$ACTION" in
        install) if is_installed; then do_update; else do_install; fi ;;
        update) is_installed || die "Not installed yet - run without --update"; do_update ;;
        repair) is_installed || die "Not installed"; do_repair ;;
        uninstall) do_uninstall ;;
    esac
}

main "$@"
