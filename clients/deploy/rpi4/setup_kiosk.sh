#!/usr/bin/env bash
# One-time setup script for OmegaReader kiosk on RPi 4.
# Run this ON the RPi 4 (not from SSH — or SSH is fine for setup, just reboot after).
set -e

echo "=== OmegaReader Kiosk Setup ==="

# 1. Install cage + seatd
echo "[1/4] Installing cage and seatd..."
sudo apt update
sudo apt install -y cage seatd chromium-browser

# 2. Add user to required groups
echo "[2/4] Adding $(whoami) to video, input, render groups..."
sudo usermod -aG video,input,render "$(whoami)"

# 3. Enable seatd service
echo "[3/4] Enabling seatd..."
sudo systemctl enable seatd
sudo systemctl start seatd

# 4. Add auto-launch to .bash_profile (only on tty1)
KIOSK_SCRIPT="$HOME/Projects/OmegaAgent/clients/deploy/rpi4/start_reader_kiosk.sh"
MARKER="# >>> OmegaReader kiosk auto-launch >>>"

if grep -q "$MARKER" "$HOME/.bash_profile" 2>/dev/null; then
    echo "[4/4] .bash_profile already has kiosk hook — skipping."
else
    echo "[4/4] Adding kiosk auto-launch to .bash_profile..."
    cat >> "$HOME/.bash_profile" << EOF

$MARKER
# Auto-launch OmegaReader kiosk on physical console (tty1)
if [ "\$(tty)" = "/dev/tty1" ] && [ -z "\$SSH_CONNECTION" ]; then
    echo "Starting OmegaReader kiosk in 3 seconds... (Ctrl+C to cancel)"
    sleep 3
    exec bash "$KIOSK_SCRIPT"
fi
# <<< OmegaReader kiosk auto-launch <<<
EOF
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Enable console autologin:"
echo "     sudo raspi-config → 1 System Options → S5 Boot / Auto Login → B2 Console Autologin"
echo "  2. Reboot:  sudo reboot"
echo ""
echo "The RPi will boot → autologin on tty1 → launch cage → show OmegaReader fullscreen."
echo "To exit kiosk: press Ctrl+C within 3 seconds of boot, or SSH in and run: pkill cage"
