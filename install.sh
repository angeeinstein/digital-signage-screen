#!/bin/bash

################################################################################
# Digital Signage Display - Comprehensive Installation Script
# For Raspberry Pi 5 with automatic installation, updates, and configuration
################################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/digital-signage"
SERVICE_NAME="digital-signage"
SERVICE_FILE="${SERVICE_NAME}.service"
LOG_DIR="/var/log/digital-signage"
RUN_DIR="/var/run/digital-signage"
VENV_DIR="${INSTALL_DIR}/venv"
USER="pi"
GROUP="pi"

# GitHub Configuration
GITHUB_USER="angeeinstein"
GITHUB_REPO="digital-signage-screen"
GITHUB_URL="https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git"
GITHUB_BRANCH="main"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

################################################################################
# Utility Functions
################################################################################

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  $1${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
    echo ""
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_os() {
    if [[ ! -f /etc/os-release ]]; then
        print_error "Cannot detect operating system"
        exit 1
    fi
    
    source /etc/os-release
    print_info "Detected OS: $PRETTY_NAME"
    
    if [[ "$ID" != "raspbian" ]] && [[ "$ID" != "debian" ]] && [[ "$ID" != "ubuntu" ]]; then
        print_warning "This script is optimized for Raspberry Pi OS, but will attempt to continue"
    fi
}

check_user_exists() {
    if ! id "$USER" &>/dev/null; then
        print_warning "User $USER does not exist. Creating user..."
        useradd -m -s /bin/bash "$USER" || true
        print_success "User $USER created"
    fi
}

detect_installation() {
    if [[ -d "$INSTALL_DIR" ]] && [[ -f "$INSTALL_DIR/app.py" ]]; then
        return 0  # Installation exists
    else
        return 1  # No installation
    fi
}

get_installed_version() {
    if [[ -f "$INSTALL_DIR/.version" ]]; then
        cat "$INSTALL_DIR/.version"
    else
        echo "unknown"
    fi
}

get_current_version() {
    if [[ -f "$SCRIPT_DIR/.version" ]]; then
        cat "$SCRIPT_DIR/.version"
    else
        echo "1.0.0"
    fi
}

################################################################################
# Installation Functions
################################################################################

install_system_packages() {
    print_header "Installing System Packages"
    
    print_info "Updating package lists..."
    apt-get update -qq || {
        print_error "Failed to update package lists"
        exit 1
    }
    
    print_info "Installing required packages..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        build-essential \
        git \
        curl \
        || {
        print_error "Failed to install system packages"
        exit 1
    }
    
    print_success "System packages installed"
}

setup_directories() {
    print_header "Setting Up Directories"
    
    # Create log directory (even though we use journald now, keep for compatibility)
    print_info "Creating log directory: $LOG_DIR"
    mkdir -p "$LOG_DIR"
    
    # Create run directory (not needed anymore but keep for compatibility)
    print_info "Creating run directory: $RUN_DIR"
    mkdir -p "$RUN_DIR"
    
    # Ensure content directory exists (already in repo but ensure it's there)
    print_info "Ensuring content directory exists: $INSTALL_DIR/content"
    mkdir -p "$INSTALL_DIR/content"
    
    # Ensure templates directory exists
    mkdir -p "$INSTALL_DIR/templates"
    
    # Ensure static directory exists
    mkdir -p "$INSTALL_DIR/static"
    
    # Create a default config if it doesn't exist
    if [[ ! -f "$INSTALL_DIR/config.json" ]]; then
        print_info "Creating default configuration..."
        cat > "$INSTALL_DIR/config.json" << 'EOF'
{
  "refresh_interval": 30,
  "rotation_enabled": true,
  "content_items": [],
  "display_name": "Digital Signage Display"
}
EOF
    fi
    
    print_success "Directories configured"
}

clone_or_pull_from_github() {
    print_header "Getting Application from GitHub"
    
    local mode="$1"
    
    # Configure git safe.directory
    git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null || true
    
    if [[ "$mode" == "fresh" ]]; then
        print_info "Cloning from GitHub: ${GITHUB_URL}"
        
        # Remove install dir if doing fresh clone
        if [[ -d "$INSTALL_DIR" ]]; then
            print_info "Removing old installation directory..."
            rm -rf "$INSTALL_DIR"
        fi
        
        # Clone repository
        git clone -b "$GITHUB_BRANCH" "$GITHUB_URL" "$INSTALL_DIR" || {
            print_error "Failed to clone from GitHub"
            exit 1
        }
        
        print_success "Repository cloned successfully"
    else
        print_info "Pulling latest changes from GitHub..."
        
        cd "$INSTALL_DIR" || {
            print_error "Cannot access installation directory"
            exit 1
        }
        
        # Stash any local changes
        print_info "Stashing local changes..."
        git stash push -u -m "Auto-stash before update $(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
        
        # Pull latest changes
        git fetch origin || {
            print_error "Failed to fetch from GitHub"
            exit 1
        }
        
        git reset --hard "origin/$GITHUB_BRANCH" || {
            print_error "Failed to update from GitHub"
            exit 1
        }
        
        print_success "Repository updated successfully"
    fi
    
    # Preserve content and config
    if [[ "$mode" == "update" ]]; then
        print_info "Preserving user content and configuration..."
        # Content is already preserved by not being in git
    fi
}

setup_python_environment() {
    print_header "Setting Up Python Environment"
    
    # Remove old venv if doing clean install
    if [[ "$1" == "clean" ]] && [[ -d "$VENV_DIR" ]]; then
        print_info "Removing old virtual environment..."
        rm -rf "$VENV_DIR"
    fi
    
    # Create virtual environment
    print_info "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR" || {
        print_error "Failed to create virtual environment"
        exit 1
    }
    
    # Upgrade pip
    print_info "Upgrading pip..."
    "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel || {
        print_error "Failed to upgrade pip"
        exit 1
    }
    
    # Install Python packages
    print_info "Installing Python packages from requirements.txt..."
    "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" || {
        print_error "Failed to install Python packages"
        exit 1
    }
    
    print_success "Python environment configured"
}

setup_systemd_service() {
    print_header "Setting Up Systemd Service"
    
    # Copy service file from installation directory
    print_info "Installing systemd service file..."
    cp -f "$INSTALL_DIR/$SERVICE_FILE" "/etc/systemd/system/$SERVICE_FILE" || {
        print_error "Failed to copy service file"
        exit 1
    }
    
    # Reload systemd
    print_info "Reloading systemd daemon..."
    systemctl daemon-reload || {
        print_error "Failed to reload systemd"
        exit 1
    }
    
    # Enable service
    print_info "Enabling $SERVICE_NAME service..."
    systemctl enable "$SERVICE_NAME" || {
        print_error "Failed to enable service"
        exit 1
    }
    
    print_success "Systemd service configured"
}

configure_nginx() {
    print_header "Configuring Nginx (Optional)"
    
    # Check if nginx is already installed
    local nginx_installed=false
    if command -v nginx &> /dev/null; then
        nginx_installed=true
    fi
    
    # Ask user if they want nginx
    print_info "Nginx can act as a reverse proxy for additional features."
    if [[ "$nginx_installed" == true ]]; then
        print_info "Nginx is already installed on this system."
    fi
    echo "Do you want to use Nginx as a reverse proxy? (y/n)"
    read -p "Choice: " use_nginx < /dev/tty
    
    if [[ "$use_nginx" != "y" ]] && [[ "$use_nginx" != "Y" ]]; then
        print_info "Not using Nginx"
        
        # If nginx is installed, disable it or disable our site
        if [[ "$nginx_installed" == true ]]; then
            print_info "Disabling Digital Signage nginx configuration..."
            rm -f "/etc/nginx/sites-enabled/$SERVICE_NAME"
            rm -f "/etc/nginx/sites-enabled/default"
            
            # Stop nginx if it's running on port 80
            if systemctl is-active --quiet nginx; then
                print_info "Stopping nginx to free port 80..."
                systemctl stop nginx
                systemctl disable nginx
            fi
        fi
        
        # Ensure gunicorn uses port 8080 (default, no special permissions needed)
        sed -i 's/bind = "127.0.0.1:5000"/bind = "0.0.0.0:8080"/' "$INSTALL_DIR/gunicorn_config.py" 2>/dev/null || true
        sed -i 's/bind = "0.0.0.0:80"/bind = "0.0.0.0:8080"/' "$INSTALL_DIR/gunicorn_config.py" 2>/dev/null || true
        
        return
    fi
    
    # User wants nginx - install if needed
    if [[ "$nginx_installed" == false ]]; then
        print_info "Installing Nginx..."
        apt-get install -y nginx || {
            print_warning "Failed to install Nginx, skipping"
            return
        }
    fi
    
    # Remove default nginx site to avoid conflicts
    print_info "Removing default nginx configuration..."
    rm -f /etc/nginx/sites-enabled/default
    
    # Create nginx config for port 80 (main access)
    print_info "Creating nginx configuration..."
    cat > "/etc/nginx/sites-available/$SERVICE_NAME" << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
    
    # Update gunicorn to use port 5000 when nginx is enabled
    print_info "Configuring Gunicorn to use port 5000..."
    sed -i 's/bind = "0.0.0.0:80"/bind = "127.0.0.1:5000"/' "$INSTALL_DIR/gunicorn_config.py"
    
    # Enable site
    if [[ ! -L "/etc/nginx/sites-enabled/$SERVICE_NAME" ]]; then
        ln -s "/etc/nginx/sites-available/$SERVICE_NAME" "/etc/nginx/sites-enabled/$SERVICE_NAME"
    fi
    
    # Test nginx config
    print_info "Testing nginx configuration..."
    nginx -t &>/dev/null || {
        print_warning "Nginx configuration test failed, reverting"
        rm -f "/etc/nginx/sites-enabled/$SERVICE_NAME"
        sed -i 's/bind = "127.0.0.1:5000"/bind = "0.0.0.0:80"/' "$INSTALL_DIR/gunicorn_config.py"
        return
    }
    
    # Enable and start nginx
    systemctl enable nginx
    systemctl restart nginx || print_warning "Failed to restart nginx"
    
    print_success "Nginx configured (serving on port 80)"
}

set_permissions() {
    print_header "Setting Permissions"
    
    print_info "Setting ownership to $USER:$GROUP..."
    chown -R "$USER:$GROUP" "$INSTALL_DIR"
    chown -R "$USER:$GROUP" "$LOG_DIR" 2>/dev/null || true
    chown -R "$USER:$GROUP" "$RUN_DIR" 2>/dev/null || true
    
    print_info "Setting file permissions..."
    chmod 755 "$INSTALL_DIR"
    chmod 755 "$LOG_DIR" 2>/dev/null || true
    chmod 755 "$RUN_DIR" 2>/dev/null || true
    chmod -R 644 "$INSTALL_DIR"/*.py 2>/dev/null || true
    chmod -R 755 "$INSTALL_DIR/content" 2>/dev/null || true
    chmod 644 "$INSTALL_DIR/config.json" 2>/dev/null || true
    
    # Allow binding to port 80 without root
    print_info "Configuring port binding capabilities..."
    if command -v setcap &> /dev/null; then
        setcap 'cap_net_bind_service=+ep' "$VENV_DIR/bin/python3" 2>/dev/null || {
            print_warning "Failed to set capabilities. You may need to run on port > 1024 or use nginx"
        }
    else
        print_warning "setcap not available. Service may need to run on port > 1024"
    fi
    
    print_success "Permissions configured"
}

start_service() {
    print_header "Starting Service"
    
    # Stop service if running
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_info "Stopping existing service..."
        systemctl stop "$SERVICE_NAME"
    fi
    
    # Reload systemd to ensure latest service file is loaded
    print_info "Reloading systemd daemon..."
    systemctl daemon-reload
    
    # Start service
    print_info "Starting $SERVICE_NAME service..."
    systemctl start "$SERVICE_NAME" || {
        print_error "Failed to start service"
        print_info "Recent service logs:"
        journalctl -u "$SERVICE_NAME" -n 50 --no-pager || true
        print_info ""
        print_info "Checking Python environment..."
        "$VENV_DIR/bin/python3" --version || print_error "Python not found in venv"
        print_info "Checking Flask installation..."
        "$VENV_DIR/bin/python3" -c "import flask; print(f'Flask {flask.__version__}')" || print_error "Flask not installed"
        print_info "Checking Gunicorn installation..."
        "$VENV_DIR/bin/gunicorn" --version || print_error "Gunicorn not found"
        exit 1
    }
    
    # Wait a moment and check status
    sleep 3
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service started successfully"
    else
        print_error "Service failed to start"
        print_info "Service status:"
        systemctl status "$SERVICE_NAME" --no-pager --lines=20 || true
        print_info ""
        print_info "Recent logs:"
        journalctl -u "$SERVICE_NAME" -n 100 --no-pager
        exit 1
    fi
}

################################################################################
# Update Functions
################################################################################

backup_installation() {
    print_header "Creating Backup"
    
    local backup_dir="/opt/digital-signage-backup-$(date +%Y%m%d_%H%M%S)"
    
    print_info "Backing up content and configuration to: $backup_dir"
    mkdir -p "$backup_dir"
    
    # Backup content directory
    if [[ -d "$INSTALL_DIR/content" ]]; then
        cp -r "$INSTALL_DIR/content" "$backup_dir/" || true
    fi
    
    # Backup config files
    if [[ -f "$INSTALL_DIR/config.json" ]]; then
        cp "$INSTALL_DIR/config.json" "$backup_dir/" || true
    fi
    
    if [[ -f "$INSTALL_DIR/dashboard_config.json" ]]; then
        cp "$INSTALL_DIR/dashboard_config.json" "$backup_dir/" || true
    fi
    
    if [[ -f "$INSTALL_DIR/flight_routes_cache.json" ]]; then
        cp "$INSTALL_DIR/flight_routes_cache.json" "$backup_dir/" || true
    fi
    
    # Keep only last 5 backups
    print_info "Cleaning old backups..."
    ls -dt /opt/digital-signage-backup-* 2>/dev/null | tail -n +6 | xargs rm -rf 2>/dev/null || true
    
    print_success "Backup created: $backup_dir"
    
    # Store backup dir for restore
    LAST_BACKUP_DIR="$backup_dir"
}

restore_from_backup() {
    if [[ -z "$LAST_BACKUP_DIR" ]] || [[ ! -d "$LAST_BACKUP_DIR" ]]; then
        print_info "No backup to restore"
        return
    fi
    
    print_info "Restoring content and configuration from backup..."
    
    # Restore content
    if [[ -d "$LAST_BACKUP_DIR/content" ]]; then
        mkdir -p "$INSTALL_DIR/content"
        cp -r "$LAST_BACKUP_DIR/content/"* "$INSTALL_DIR/content/" 2>/dev/null || true
    fi
    
    # Restore config files
    if [[ -f "$LAST_BACKUP_DIR/config.json" ]]; then
        cp "$LAST_BACKUP_DIR/config.json" "$INSTALL_DIR/" || true
    fi
    
    if [[ -f "$LAST_BACKUP_DIR/dashboard_config.json" ]]; then
        cp "$LAST_BACKUP_DIR/dashboard_config.json" "$INSTALL_DIR/" || true
    fi
    
    if [[ -f "$LAST_BACKUP_DIR/flight_routes_cache.json" ]]; then
        cp "$LAST_BACKUP_DIR/flight_routes_cache.json" "$INSTALL_DIR/" || true
    fi
    
    print_success "Content and configuration restored"
}

update_installation() {
    print_header "Updating Installation"
    
    backup_installation
    
    # Stop service
    print_info "Stopping service..."
    systemctl stop "$SERVICE_NAME" || true
    
    # Pull latest from GitHub
    clone_or_pull_from_github "update"
    
    # Restore content and config if backed up
    restore_from_backup
    
    # Update Python environment
    setup_python_environment "update"
    
    # Update service file
    print_info "Updating service configuration..."
    cp -f "$INSTALL_DIR/$SERVICE_FILE" "/etc/systemd/system/$SERVICE_FILE" 2>/dev/null || true
    systemctl daemon-reload
    
    # Set permissions
    set_permissions
    
    # Start service
    start_service
    
    print_success "Update completed"
}

################################################################################
# Interactive Menu Functions
################################################################################

show_menu() {
    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo "  Digital Signage - Installation/Update Menu"
    echo "═══════════════════════════════════════════════════════"
    echo ""
    echo "Existing installation detected:"
    echo "  Location: $INSTALL_DIR"
    echo "  Version: $(get_installed_version)"
    echo "  New version: $(get_current_version)"
    echo ""
    echo "What would you like to do?"
    echo ""
    echo "  1) Update (preserve content and config)"
    echo "  2) Reinstall (clean install, remove all data)"
    echo "  3) Repair (fix permissions and service)"
    echo "  4) Uninstall"
    echo "  5) Cancel"
    echo ""
}

handle_menu_choice() {
    local choice="$1"
    
    case $choice in
        1)
            print_info "Starting update..."
            update_installation
            ;;
        2)
            print_warning "This will remove all existing data!"
            read -p "Are you sure? (yes/no): " confirm < /dev/tty
            if [[ "$confirm" == "yes" ]]; then
                print_info "Starting clean installation..."
                systemctl stop "$SERVICE_NAME" 2>/dev/null || true
                systemctl disable "$SERVICE_NAME" 2>/dev/null || true
                rm -rf "$INSTALL_DIR"
                rm -rf "$LOG_DIR"
                rm -rf "$RUN_DIR"
                perform_installation
            else
                print_info "Cancelled"
                exit 0
            fi
            ;;
        3)
            print_info "Repairing installation..."
            set_permissions
            setup_systemd_service
            systemctl daemon-reload
            systemctl restart "$SERVICE_NAME"
            print_success "Repair completed"
            ;;
        4)
            print_warning "This will completely remove Digital Signage!"
            read -p "Are you sure? (yes/no): " confirm < /dev/tty
            if [[ "$confirm" == "yes" ]]; then
                uninstall
            else
                print_info "Cancelled"
                exit 0
            fi
            ;;
        5)
            print_info "Installation cancelled"
            exit 0
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac
}

uninstall() {
    print_header "Uninstalling Digital Signage"
    
    # Stop and disable service
    print_info "Stopping and disabling service..."
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    
    # Remove service file
    print_info "Removing service file..."
    rm -f "/etc/systemd/system/$SERVICE_FILE"
    systemctl daemon-reload
    
    # Remove nginx config
    print_info "Removing nginx configuration..."
    rm -f "/etc/nginx/sites-enabled/$SERVICE_NAME"
    rm -f "/etc/nginx/sites-available/$SERVICE_NAME"
    systemctl reload nginx 2>/dev/null || true
    
    # Remove directories
    print_info "Removing installation directory..."
    rm -rf "$INSTALL_DIR"
    
    print_info "Removing log directory..."
    rm -rf "$LOG_DIR"
    
    print_info "Removing run directory..."
    rm -rf "$RUN_DIR"
    
    print_success "Digital Signage has been uninstalled"
}

################################################################################
# Main Installation Flow
################################################################################

perform_installation() {
    check_user_exists
    install_system_packages
    clone_or_pull_from_github "fresh"
    setup_directories
    setup_python_environment "clean"
    setup_systemd_service
    configure_nginx
    set_permissions
    start_service
    
    print_header "Installation Complete!"
    echo ""
    print_success "Digital Signage is now running!"
    echo ""
    
    # Detect which port is configured
    local port=8080
    if grep -q "bind = \"0.0.0.0:8080\"" "$INSTALL_DIR/gunicorn_config.py" 2>/dev/null; then
        port=8080
    elif grep -q "bind = \"0.0.0.0:80\"" "$INSTALL_DIR/gunicorn_config.py" 2>/dev/null; then
        port=80
    elif grep -q "bind = \"127.0.0.1:5000\"" "$INSTALL_DIR/gunicorn_config.py" 2>/dev/null; then
        port=80
        echo "Using Nginx on port 80 (proxying to internal port 5000)"
    fi
    
    local ip=$(hostname -I | awk '{print $1}')
    echo "Access the display at:"
    if [[ "$port" == "80" ]]; then
        echo "  - http://${ip}"
        echo "  - http://${ip}:80"
    else
        echo "  - http://${ip}:${port}"
    fi
    echo ""
    echo "Admin panel at:"
    if [[ "$port" == "80" ]]; then
        echo "  - http://${ip}/admin"
    else
        echo "  - http://${ip}:${port}/admin"
    fi
    echo ""
    echo "Service management:"
    echo "  - Start:   sudo systemctl start $SERVICE_NAME"
    echo "  - Stop:    sudo systemctl stop $SERVICE_NAME"
    echo "  - Restart: sudo systemctl restart $SERVICE_NAME"
    echo "  - Status:  sudo systemctl status $SERVICE_NAME"
    echo "  - Logs:    sudo journalctl -u $SERVICE_NAME -f"
    echo ""
}

################################################################################
# Main Script Entry Point
################################################################################

main() {
    print_header "Digital Signage Display - Installation Script"
    
    # Root check
    check_root
    
    # OS check
    check_os
    
    # Check for existing installation
    if detect_installation; then
        show_menu
        read -p "Enter your choice (1-5): " choice < /dev/tty
        handle_menu_choice "$choice"
    else
        print_info "No existing installation detected"
        print_info "Starting fresh installation..."
        perform_installation
    fi
}

# Run main function
main "$@"
