#!/bin/bash
# Diagnostic script for Digital Signage

echo "=== Digital Signage Diagnostics ==="
echo ""

echo "1. Checking what's using port 80:"
sudo lsof -i :80 || sudo netstat -tulpn | grep :80
echo ""

echo "2. Checking nginx status:"
sudo systemctl status nginx --no-pager | head -5
echo ""

echo "3. Checking digital-signage service:"
sudo systemctl status digital-signage --no-pager | head -10
echo ""

echo "4. Recent service logs:"
sudo journalctl -u digital-signage -n 20 --no-pager
echo ""

echo "5. Gunicorn config:"
grep "bind =" /opt/digital-signage/gunicorn_config.py
echo ""

echo "6. Python capabilities:"
getcap /opt/digital-signage/venv/bin/python3
echo ""

echo "=== Suggested Fix ==="
echo "Run one of these:"
echo ""
echo "Option 1 - Stop nginx and use direct port 80:"
echo "  sudo systemctl stop nginx"
echo "  sudo systemctl disable nginx"
echo "  sudo setcap 'cap_net_bind_service=+ep' /opt/digital-signage/venv/bin/python3"
echo "  sudo systemctl restart digital-signage"
echo ""
echo "Option 2 - Use port 8080 instead:"
echo "  sudo sed -i 's/bind = \"0.0.0.0:80\"/bind = \"0.0.0.0:8080\"/' /opt/digital-signage/gunicorn_config.py"
echo "  sudo systemctl restart digital-signage"
echo "  # Then access at http://YOUR_IP:8080"
