#!/usr/bin/env python3
"""
Digital Signage Display Application
A Flask-based digital signage solution for Raspberry Pi
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from datetime import datetime
import os
import json
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'digital-signage-secret-key-change-in-production')

# Configuration
BASE_DIR = Path(__file__).resolve().parent
CONTENT_DIR = BASE_DIR / 'content'
CONFIG_FILE = BASE_DIR / 'config.json'

# Ensure directories exist
CONTENT_DIR.mkdir(exist_ok=True)

# Default configuration
DEFAULT_CONFIG = {
    'refresh_interval': 30,  # seconds
    'rotation_enabled': True,
    'content_items': [],
    'display_name': 'Digital Signage Display'
}


def load_config():
    """Load configuration from file or create default"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    return DEFAULT_CONFIG.copy()


def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False


@app.route('/')
def index():
    """Main display page"""
    config = load_config()
    return render_template('display.html', config=config)


@app.route('/admin')
def admin():
    """Admin panel for managing content"""
    config = load_config()
    return render_template('admin.html', config=config)


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    config = load_config()
    return jsonify(config)


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration"""
    try:
        new_config = request.json
        if save_config(new_config):
            return jsonify({'success': True, 'message': 'Configuration updated'})
        else:
            return jsonify({'success': False, 'message': 'Failed to save configuration'}), 500
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/content', methods=['GET'])
def list_content():
    """List all content files"""
    try:
        files = []
        for item in CONTENT_DIR.iterdir():
            if item.is_file() and item.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.webm']:
                files.append({
                    'name': item.name,
                    'size': item.stat().st_size,
                    'modified': item.stat().st_mtime
                })
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        logger.error(f"Error listing content: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/content/<filename>', methods=['DELETE'])
def delete_content(filename):
    """Delete a content file"""
    try:
        file_path = CONTENT_DIR / filename
        if file_path.exists() and file_path.parent == CONTENT_DIR:
            file_path.unlink()
            return jsonify({'success': True, 'message': f'Deleted {filename}'})
        else:
            return jsonify({'success': False, 'message': 'File not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting content: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/content/<path:filename>')
def serve_content(filename):
    """Serve content files"""
    return send_from_directory(CONTENT_DIR, filename)


@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal error: {error}")
    return render_template('500.html'), 500


if __name__ == '__main__':
    # Development server
    app.run(host='0.0.0.0', port=5000, debug=True)
