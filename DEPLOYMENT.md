# Deployment Guide

Complete guide for deploying Digital Signage Display on Raspberry Pi.

## Prerequisites

- Raspberry Pi 5 (or Pi 4 with modifications)
- MicroSD card (16GB+ recommended)
- Raspberry Pi OS (Bookworm or later)
- Display connected via HDMI
- Network connection (WiFi or Ethernet)
- SSH access or keyboard/mouse

## Step 1: Prepare Raspberry Pi

### Install Raspberry Pi OS
1. Download Raspberry Pi Imager
2. Flash Raspberry Pi OS Lite or Desktop
3. Enable SSH (add empty `ssh` file to boot partition)
4. Configure WiFi if needed (`wpa_supplicant.conf`)

### First Boot Setup
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Set timezone
sudo raspi-config
# Select: Localisation Options > Timezone

# (Optional) Set hostname
sudo raspi-config
# Select: System Options > Hostname
```

## Step 2: Install Digital Signage

### One-Command Installation
```bash
curl -sSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/install.sh | sudo bash
```

This single command will:
- Install all dependencies
- Clone from GitHub
- Configure services
- **Ask if you want Nginx** (optional)
- Start the application

**Or clone and run locally:**
```bash
git clone https://github.com/angeeinstein/digital-signage-screen.git
cd digital-signage-screen
sudo bash install.sh
```

## Step 3: Configure Display

### Add Content
```bash
# Copy images/videos to content directory
sudo cp /path/to/your/content/*.jpg /opt/digital-signage/content/
sudo chown -R pi:pi /opt/digital-signage/content/
```

### Configure Settings
1. Open browser: `http://<pi-ip>/admin`
2. Adjust refresh interval
3. Set display name
4. Enable/disable rotation

## Step 4: Configure Autostart (Chromium Kiosk)

### Install Chromium
```bash
sudo apt install -y chromium-browser unclutter
```

### Create Autostart Script
```bash
mkdir -p ~/.config/autostart
nano ~/.config/autostart/digital-signage.desktop
```

Add:
```ini
[Desktop Entry]
Type=Application
Name=Digital Signage Display
Exec=/home/pi/start-kiosk.sh
X-GNOME-Autostart-enabled=true
```

### Create Kiosk Script
```bash
nano ~/start-kiosk.sh
```

Add:
```bash
#!/bin/bash

# Wait for network
sleep 10

# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Hide cursor
unclutter -idle 0.1 &

# Start Chromium in kiosk mode
chromium-browser --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --no-first-run \
  --disable-features=Translate \
  --check-for-update-interval=31536000 \
  http://localhost
```

Make executable:
```bash
chmod +x ~/start-kiosk.sh
```

## Step 5: Disable Screen Blanking

Edit LXDE config:
```bash
nano ~/.config/lxsession/LXDE-pi/autostart
```

Add these lines:
```
@xset s off
@xset -dpms
@xset s noblank
```

## Step 6: Testing

### Test Service
```bash
# Check service status
sudo systemctl status digital-signage

# View logs
sudo journalctl -u digital-signage -f

# Test API
curl http://localhost/api/health
```

### Test Display
1. Open browser
2. Navigate to `http://<pi-ip>/`
3. Verify content displays

### Test Admin Panel
1. Navigate to `http://<pi-ip>/admin`
2. Upload content
3. Change settings

## Step 7: Security Hardening

### Change Default Password
```bash
passwd
```

### Configure Firewall
```bash
sudo apt install -y ufw
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 8080/tcp
sudo ufw enable
```

### Add Authentication (Optional)
Edit `app.py` to add basic auth:
```python
from flask_httpauth import HTTPBasicAuth
auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
    # Add your authentication logic
    pass
```

## Step 8: Updates

### Automatic Updates
```bash
# Pull latest from GitHub
curl -sSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/install.sh | sudo bash
```
Choose option 1 (Update)

### Manual Updates
```bash
cd /opt/digital-signage
sudo bash install.sh
```

## Troubleshooting

### Service Won't Start
```bash
# Check logs
sudo journalctl -u digital-signage -n 100 --no-pager

# Check permissions
sudo chown -R pi:pi /opt/digital-signage

# Repair installation
sudo bash /opt/digital-signage/install.sh
# Choose option 3 (Repair)
```

### Display Not Showing
```bash
# Check if service is running
sudo systemctl status digital-signage

# Test locally
curl http://localhost/

# Check content directory
ls -la /opt/digital-signage/content/
```

### Network Issues
```bash
# Check network
ip addr show
ping google.com

# Check firewall
sudo ufw status

# Test port binding
sudo netstat -tulpn | grep :80
```

### Performance Issues
Edit `gunicorn_config.py`:
```python
# Reduce workers for lower-end hardware
workers = 1

# Adjust timeout
timeout = 60
```

Then restart:
```bash
sudo systemctl restart digital-signage
```

## Advanced Configuration

### Custom Port
Edit `/opt/digital-signage/gunicorn_config.py`:
```python
bind = "0.0.0.0:8000"
```

### Custom Domain
Configure nginx:
```bash
sudo nano /etc/nginx/sites-available/digital-signage
```

Update server_name:
```nginx
server {
    listen 80;
    server_name yourdomain.com;
    # ... rest of config
}
```

### HTTPS Setup
```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d yourdomain.com
```

### Remote Management
Enable SSH tunneling for secure remote access:
```bash
ssh -L 8080:localhost:80 pi@raspberry-pi-ip
```
Then access via: `http://localhost:8080`

## Monitoring

### Check Service Status
```bash
sudo systemctl status digital-signage
```

### View Real-time Logs
```bash
sudo journalctl -u digital-signage -f
```

### Monitor Resources
```bash
# Install htop
sudo apt install htop

# View processes
htop
```

### Health Check Endpoint
```bash
curl http://localhost/api/health
```

## Backup and Restore

### Manual Backup
```bash
# Backup content and config
sudo tar -czf ~/digital-signage-backup.tar.gz \
  /opt/digital-signage/content \
  /opt/digital-signage/config.json
```

### Restore
```bash
# Extract backup
sudo tar -xzf ~/digital-signage-backup.tar.gz -C /
sudo chown -R pi:pi /opt/digital-signage
sudo systemctl restart digital-signage
```

## Production Checklist

- [ ] Raspberry Pi OS updated
- [ ] Digital Signage installed
- [ ] Content added
- [ ] Display configured
- [ ] Chromium kiosk enabled
- [ ] Screen blanking disabled
- [ ] Service starts on boot
- [ ] Firewall configured
- [ ] Default password changed
- [ ] Backups configured
- [ ] Updates scheduled
- [ ] Monitoring in place

## Support

- GitHub Issues: https://github.com/angeeinstein/digital-signage-screen/issues
- Documentation: README.md
- Logs: `sudo journalctl -u digital-signage -f`
