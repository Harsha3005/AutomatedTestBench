#!/bin/bash
# ==============================================================
# IIITB Water Meter Test Bench - Kiosk Setup Script
# Run on the Bench RPi5 as root: sudo bash kiosk-setup.sh
# Sets up auto-login, Chromium kiosk, systemd services.
# ==============================================================

set -euo pipefail

BENCH_USER="harshavardhan"
BENCH_DIR="/home/$BENCH_USER/I.R.A.S/Water Flow Meter Calibration System/Bench System/Bench Controller"

echo "=== IIITB Test Bench Kiosk Setup ==="
echo "Bench directory: $BENCH_DIR"
echo ""

# --- 1. Install required packages ---
echo "[1/6] Installing packages..."
apt-get update -qq
apt-get install -y -qq openbox xorg lightdm chromium-browser unclutter redis-server

# --- 2. Configure auto-login via LightDM ---
echo "[2/6] Configuring auto-login..."
mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-autologin.conf << 'LIGHTDM'
[Seat:*]
autologin-user=harshavardhan
autologin-user-timeout=0
user-session=openbox
LIGHTDM

# --- 3. Configure Openbox autostart ---
echo "[3/6] Setting up Openbox..."
OPENBOX_DIR="/home/$BENCH_USER/.config/openbox"
mkdir -p "$OPENBOX_DIR"
cat > "$OPENBOX_DIR/autostart" << 'AUTOSTART'
# IIITB Test Bench - Openbox autostart
# Disable screen blanking and DPMS
xset s off
xset -dpms
xset s noblank

# Hide cursor after 3 seconds of inactivity
unclutter -idle 3 -root &

# Chromium kiosk is managed by systemd (bench-kiosk.service)
AUTOSTART
chown -R "$BENCH_USER:$BENCH_USER" "/home/$BENCH_USER/.config"

# --- 4. Install systemd services + udev rules ---
echo "[4/6] Installing systemd services and udev rules..."
cp "$BENCH_DIR/scripts/bench-django.service" /etc/systemd/system/
cp "$BENCH_DIR/scripts/bench-kiosk.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable bench-django.service
systemctl enable bench-kiosk.service
systemctl enable redis-server

# Install udev rules for USB-serial port mapping
if [ -f "$BENCH_DIR/scripts/99-bench-serial.rules" ]; then
    cp "$BENCH_DIR/scripts/99-bench-serial.rules" /etc/udev/rules.d/
    udevadm control --reload-rules
    udevadm trigger
    echo "  Udev rules installed."
fi

# --- 5. Collect static files ---
echo "[5/6] Collecting static files..."
cd "$BENCH_DIR"
sudo -u "$BENCH_USER" bash -c "source venv/bin/activate && DJANGO_SETTINGS_MODULE=config.settings_bench python manage.py collectstatic --noinput"

# --- 6. Run migrations ---
echo "[6/6] Running migrations..."
sudo -u "$BENCH_USER" bash -c "source venv/bin/activate && DJANGO_SETTINGS_MODULE=config.settings_bench python manage.py migrate --noinput"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "The system will boot into kiosk mode on next restart."
echo ""
echo "  Django:   http://127.0.0.1:8000/ (Daphne ASGI)"
echo "  Kiosk:    Chromium fullscreen on :0"
echo "  Redis:    localhost:6379"
echo ""
echo "To test without rebooting:"
echo "  sudo systemctl start bench-django"
echo "  sudo systemctl start bench-kiosk"
echo ""
echo "To exit kiosk mode:"
echo "  Ctrl+Alt+F2 for TTY, then:"
echo "  sudo systemctl stop bench-kiosk"
echo ""
