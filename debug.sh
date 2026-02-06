#!/bin/bash
# Get detailed error information

echo "=== Full Service Logs ==="
sudo journalctl -u digital-signage -n 50 --no-pager

echo ""
echo "=== Test App Directly ==="
cd /opt/digital-signage
source venv/bin/activate
python3 -c "import app; print('App imports OK')" 2>&1

echo ""
echo "=== Test Gunicorn Directly ==="
cd /opt/digital-signage
sudo -u pi /opt/digital-signage/venv/bin/gunicorn --bind 0.0.0.0:8080 --timeout 10 app:app &
GUNICORN_PID=$!
sleep 3
if ps -p $GUNICORN_PID > /dev/null; then
    echo "Gunicorn started successfully on port 8080"
    curl -s http://localhost:8080/api/health || echo "Failed to reach app"
    kill $GUNICORN_PID
else
    echo "Gunicorn failed to start"
fi
