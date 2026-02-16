#!/bin/bash
# ==============================================================
# IIITB Water Meter Calibration Lab - Setup Script
# Run on the Lab PC as root: sudo bash lab-setup.sh
# Sets up systemd service, udev rules, static files, database.
# ==============================================================

set -euo pipefail

LAB_USER="harshavardhan"
LAB_DIR="/home/$LAB_USER/I.R.A.S/Water Flow Meter Calibration System/Bench System/Bench Controller"

echo "=== IIITB Calibration Lab Setup ==="
echo "Lab directory: $LAB_DIR"
echo ""

# --- 1. Install systemd service ---
echo "[1/4] Installing systemd service..."
cp "$LAB_DIR/scripts/lab-django.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable lab-django.service

# --- 2. Install udev rules ---
echo "[2/4] Installing udev rules..."
if [ -f "$LAB_DIR/scripts/99-lab-serial.rules" ]; then
    cp "$LAB_DIR/scripts/99-lab-serial.rules" /etc/udev/rules.d/
    udevadm control --reload-rules
    udevadm trigger
    echo "  Udev rules installed."
else
    echo "  No udev rules found (skipping — add after hardware connection)."
fi

# --- 3. Collect static files ---
echo "[3/4] Collecting static files..."
cd "$LAB_DIR"
sudo -u "$LAB_USER" bash -c "source venv/bin/activate && DJANGO_SETTINGS_MODULE=config.settings_lab python manage.py collectstatic --noinput"

# --- 4. Run migrations ---
echo "[4/4] Running migrations..."
sudo -u "$LAB_USER" bash -c "source venv/bin/activate && DJANGO_SETTINGS_MODULE=config.settings_lab python manage.py migrate --noinput"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "  Django:   http://0.0.0.0:8080/ (Gunicorn WSGI)"
echo ""
echo "To start the service:"
echo "  sudo systemctl start lab-django"
echo ""
echo "To check status:"
echo "  sudo systemctl status lab-django"
echo "  sudo journalctl -u lab-django -f"
echo ""
