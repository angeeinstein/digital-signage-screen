#!/bin/bash
# Quick test script to verify installation

echo "=== Digital Signage Installation Test ==="
echo ""

# Check if installation exists
if [[ ! -d "/opt/digital-signage" ]]; then
    echo "❌ Installation not found at /opt/digital-signage"
    exit 1
fi
echo "✅ Installation directory exists"

# Check Python venv
if [[ ! -f "/opt/digital-signage/venv/bin/python3" ]]; then
    echo "❌ Python virtual environment not found"
    exit 1
fi
echo "✅ Python virtual environment exists"

# Check Flask
if /opt/digital-signage/venv/bin/python3 -c "import flask" 2>/dev/null; then
    echo "✅ Flask is installed"
else
    echo "❌ Flask is not installed"
    exit 1
fi

# Check Gunicorn
if [[ -f "/opt/digital-signage/venv/bin/gunicorn" ]]; then
    echo "✅ Gunicorn is installed"
else
    echo "❌ Gunicorn is not installed"
    exit 1
fi

# Check service file
if [[ -f "/etc/systemd/system/digital-signage.service" ]]; then
    echo "✅ Systemd service file exists"
else
    echo "❌ Systemd service file not found"
    exit 1
fi

# Check service status
if systemctl is-active --quiet digital-signage; then
    echo "✅ Service is running"
else
    echo "⚠️  Service is not running"
    echo "   Run: sudo systemctl status digital-signage"
fi

# Check port 80
if nc -z localhost 80 2>/dev/null; then
    echo "✅ Port 80 is accessible"
else
    echo "⚠️  Port 80 is not accessible (may need capabilities)"
fi

# Test API
if curl -s http://localhost/api/health > /dev/null 2>&1; then
    echo "✅ API endpoint responding"
else
    echo "⚠️  API endpoint not responding"
fi

echo ""
echo "=== Test Complete ==="
