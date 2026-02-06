# Changelog

All notable changes to Digital Signage Display will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-06

### Added
- Initial release of Digital Signage Display
- Flask web application with Gunicorn server
- Full-screen display with content rotation
- Support for images (JPG, PNG, GIF) and videos (MP4, WebM)
- Web-based admin panel for configuration
- Systemd service for automatic startup
- Nginx reverse proxy configuration
- Comprehensive automated installation script
- GitHub-based installation and updates
- Automatic backup system (keeps last 5 backups)
- Health check endpoint
- Content management API
- Configurable refresh intervals
- Clock display on main screen
- Error handling and logging
- Documentation (README, CONTRIBUTING)
- CI/CD workflow with GitHub Actions

### Features
- Zero-configuration installation
- Intelligent update detection
- Automatic permission handling
- Port 80 binding without root
- Repair functionality for broken installations
- Complete uninstall option
- Preservation of content during updates

### Installation Methods
- One-line curl installation
- Manual git clone installation
- Quick installer script

### Technical Details
- Optimized for Raspberry Pi 5
- Python 3.7+ support
- Runs as non-root user (pi)
- Production-ready with Gunicorn
- Systemd integration
- Automatic log rotation

## [Unreleased]

### Planned
- File upload via web interface
- User authentication for admin panel
- Multiple display layouts
- Scheduled content rotation
- Remote management API
- Mobile-responsive admin panel
- Content preview in admin panel
- Playlist management
- Weather widget integration
- RSS feed support

---

## Version History

- 1.0.0 - Initial Release (February 6, 2026)
