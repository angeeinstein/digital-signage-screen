# Digital Signage Display Solution

[![GitHub](https://img.shields.io/badge/GitHub-angeeinstein-blue?logo=github)](https://github.com/angeeinstein/digital-signage-screen)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue?logo=python)](https://www.python.org/)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-5-red?logo=raspberry-pi)](https://www.raspberrypi.com/)

A comprehensive digital signage solution built with Flask and Gunicorn, designed for Raspberry Pi 5. Features a fully automated installation and update system with GitHub integration.

## Features

- 🖥️ **Full-screen Display**: Clean, distraction-free content display
- 🔄 **Auto-rotation**: Automatic content cycling with configurable intervals
- 🎨 **Multi-format Support**: Images (JPG, PNG, GIF) and videos (MP4, WebM)
- ⚙️ **Web Admin Panel**: Easy content and configuration management
- 🚀 **Systemd Service**: Automatic startup and management
- 🔧 **Automated Installation**: Zero manual configuration required
- 📦 **Update Management**: Intelligent update system with backups
- 🔒 **Production Ready**: Runs on Gunicorn with proper permissions

## System Requirements

- Raspberry Pi 5 (or compatible Debian/Ubuntu system)
- Python 3.7+
- Root access (sudo)
- Internet connection for initial setup

## Quick Start

### One-Command Installation

Run this single command on your Raspberry Pi:
```bash
curl -sSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/install.sh | sudo bash
```

**Or clone and run locally:**
```bash
git clone https://github.com/angeeinstein/digital-signage-screen.git
cd digital-signage-screen
sudo bash install.sh
```

The script will:
- Install all required system packages
- Set up Python virtual environment
- Install Python dependencies
- Configure systemd service
- **Optionally** set up Nginx reverse proxy (asks during install)
- Configure permissions
- Start the service automatically

### Accessing the Display

Once installed, access your digital signage at:
- **Main Display**: `http://<raspberry-pi-ip>:8080/`
- **Admin Panel**: `http://<raspberry-pi-ip>:8080/admin`

**Note**: The installer will show you the exact IP address at the end. Default port is 8080 to avoid permission issues.

## Installation Script Features

The `install.sh` script handles everything automatically:

### First Installation
- Detects and installs missing packages
- Creates all necessary directories
- Sets up Python virtual environment
- Configures systemd service
- Fixes all permissions
- **Asks if you want Nginx** (optional reverse proxy)
- Handles port 80 binding without root

### Existing Installation Detected
When run on a system with existing installation, you get options:

1. **Update**: Preserves content and configuration
2. **Reinstall**: Clean install (removes all data)
3. **Repair**: Fixes permissions and service issues
4. **Uninstall**: Complete removal
5. **Cancel**: Exit without changes

### Update Features
- Automatic backup before updates (keeps last 5 backups)
- Zero downtime deployment
- Preserves all content and configuration
- Automatic rollback capability

## Adding Content

### Method 1: Admin Panel (Recommended)
1. Navigate to `http://<raspberry-pi-ip>/admin`
2. Upload images or videos
3. Configure display settings

### Method 2: Direct File Copy
Copy files to the content directory:
```bash
sudo cp /path/to/your/image.jpg /opt/digital-signage/content/
sudo chown pi:pi /opt/digital-signage/content/image.jpg
```

Supported formats:
- Images: `.jpg`, `.jpeg`, `.png`, `.gif`
- Videos: `.mp4`, `.webm`

## Configuration

### Display Settings
Configure via admin panel:
- **Display Name**: Custom name for your display
- **Refresh Interval**: Time between content changes (seconds)
- **Rotation Enabled**: Enable/disable automatic content rotation

Configuration is stored in `/opt/digital-signage/config.json`

### Service Management

```bash
# Start service
sudo systemctl start digital-signage

# Stop service
sudo systemctl stop digital-signage

# Restart service
sudo systemctl restart digital-signage

# View status
sudo systemctl status digital-signage

# View logs
sudo journalctl -u digital-signage -f
```

## File Locations

- **Installation**: `/opt/digital-signage/`
- **Content**: `/opt/digital-signage/content/`
- **Logs**: `/var/log/digital-signage/`
- **Service**: `/etc/systemd/system/digital-signage.service`
- **Backups**: `/opt/digital-signage-backup-*`

## Troubleshooting

### Quick Diagnostic

Run this to see what's wrong:
```bash
curl -sSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/diagnose.sh | sudo bash
```

### Service won't start

**Check service status and logs:**
```bash
sudo systemctl status digital-signage
sudo journalctl -u digital-signage -n 100 --no-pager
```

**Check what's using port 80:**
```bash
sudo lsof -i :80
# or
sudo netstat -tulpn | grep :80
```

**Common issues and fixes:**

1. **Port 80 permission denied / "Retrying in 1 second" error**
   
   This means something is blocking port 80. Fix it:
   
   ```bash
   # Stop nginx if it's running
   sudo systemctl stop nginx
   sudo systemctl disable nginx
   
   # Give Python permission to use port 80
   sudo setcap 'cap_net_bind_service=+ep' /opt/digital-signage/venv/bin/python3
   
   # Restart the service
   sudo systemctl restart digital-signage
   
   # Check if it's working
   sudo systemctl status digital-signage
   curl http://localhost/api/health
   ```
   
   **Alternative - Use port 8080 instead:**
   ```bash
   sudo nano /opt/digital-signage/gunicorn_config.py
   # Change line: bind = "0.0.0.0:8080"
   sudo systemctl restart digital-signage
   # Access at: http://YOUR_IP:8080
   ```

2. **Port 80 already in use**
   ```bash
   # Option 1: Set capabilities (done automatically by installer)
   sudo setcap 'cap_net_bind_service=+ep' /opt/digital-signage/venv/bin/python3
   
   # Option 2: Use port 8080 instead
   # Edit /opt/digital-signage/gunicorn_config.py
   # Change: bind = "0.0.0.0:8080"
   sudo systemctl restart digital-signage
   ```

2. **Missing Python packages**
   ```bash
   cd /opt/digital-signage
   source venv/bin/activate
   pip install -r requirements.txt
   sudo systemctl restart digital-signage
   ```

3. **Templates not found**
   ```bash
   # Ensure templates directory exists
   ls -la /opt/digital-signage/templates/
   
   # If missing, re-run installer
   curl -sSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/install.sh | sudo bash
   # Choose option 3 (Repair)
   ```

4. **Permission errors**
   ```bash
   sudo chown -R pi:pi /opt/digital-signage
   sudo chmod -R 755 /opt/digital-signage
   sudo systemctl restart digital-signage
   ```

**Run diagnostic test:**
```bash
curl -sSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/test-install.sh | sudo bash
```

### Service won't start
```bash
# Check service status
sudo systemctl status digital-signage

# View detailed logs
sudo journalctl -u digital-signage -n 100

# Repair installation
sudo bash install.sh
# Choose option 3 (Repair)
```

### Port 80 access issues
The script configures port 80 access automatically. If issues persist:
```bash
# Use alternative port 8080 (via Nginx)
http://<raspberry-pi-ip>:8080
```

### Permission issues
```bash
# Run repair
sudo bash install.sh
# Choose option 3 (Repair)
```

### Content not displaying
1. Check content directory: `ls -la /opt/digital-signage/content/`
2. Verify file permissions: `sudo chown -R pi:pi /opt/digital-signage/content/`
3. Check file formats (only supported formats will display)

## Auto-start on Boot

The service is automatically configured to start on boot. To verify:
```bash
sudo systemctl is-enabled digital-signage
```

## Updating

To update to a new version:

**Quick Update (Recommended):**
```bash
curl -sSL https://raw.githubusercontent.com/angeeinstein/digital-signage-screen/main/install.sh | sudo bash
```
Choose option 1 (Update) when prompted.

**Alternative: If already installed locally**
```bash
cd /opt/digital-signage
sudo bash install.sh
```
Choose option 1 (Update) when prompted.

The update process:
- Pulls latest code from GitHub
- Creates automatic backup of content and config
- Preserves all content and configuration
- Updates code and dependencies
- Restarts service
- Keeps last 5 backups for safety

## Uninstalling

To completely remove Digital Signage:
```bash
sudo bash install.sh
# Choose option 4 (Uninstall)
```

This removes:
- Service and systemd configuration
- Application files
- Log files
- Nginx configuration

## Security Notes

- Default setup runs on port 80 (requires sudo for install)
- Service runs as user 'pi' (not root)
- Admin panel has no authentication (add auth for public networks)
- Consider firewall rules for production use

## Customization
Using Nginx (Recommended for Production)

If you didn't enable Nginx during installation, you can add it later:

```bash
# Install nginx
sudo apt install -y nginx

# Create config
sudo nano /etc/nginx/sites-available/digital-signage
```

Add:
```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Enable and restart:
```bash
# Update gunicorn to use port 5000
sudo nano /opt/digital-signage/gunicorn_config.py
# Change: bind = "127.0.0.1:5000"

# Enable nginx site
sudo ln -s /etc/nginx/sites-available/digital-signage /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl restart digital-signage
```

### 
### Change Port
Edit `gunicorn_config.py`:
```python
bind = "0.0.0.0:8080"  # Change to desired port
```

### Adjust Workers
For different hardware, edit `gunicorn_config.py`:
```python
workers = 2  # Adjust based on CPU cores
```

### Custom Styling
Edit templates in `templates/` directory:
- `display.html` - Main display page
- `admin.html` - Admin panel
- `404.html` - Not found page
- `500.html` - Error page

## API Endpoints

- `GET /` - Main display page
- `GET /admin` - Admin panel
- `GET /api/config` - Get configuration
- `POST /api/config` - Update configuration
- `GET /api/content` - List content files
- `DELETE /api/content/<filename>` - Delete content
- `GET /api/health` - Health check
- `GET /content/<filename>` - Serve content file

## Development

To run in development mode:
```bash
cd /opt/digital-signage
source venv/bin/activate
python app.py
```

Access at: `http://localhost:5000`

## Support

For issues, questions, or contributions:
1. Check logs: `sudo journalctl -u digital-signage -f`
2. Run repair: `sudo bash install.sh` (option 3)
3. Check file permissions
4. Verify network connectivity
5. Open an issue on GitHub: https://github.com/angeeinstein/digital-signage-screen/issues

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Repository

GitHub: https://github.com/angeeinstein/digital-signage-screen

## License

MIT License - Feel free to use and modify for your needs.

## Version

Current Version: 1.0.0

## Author

Created by angeeinstein
