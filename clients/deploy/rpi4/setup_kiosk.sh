#!/usr/bin/env bash
# One-time setup script for OmegaReader kiosk on RPi 4.
# Run this ON the RPi 4 (not from SSH — or SSH is fine for setup, just reboot after).
set -e

echo "=== OmegaReader Kiosk Setup ==="

# 1. Install X11 minimal + Chromium
echo "[1/3] Installing X11 kiosk packages..."
sudo apt update
sudo apt install -y xserver-xorg xinit x11-xserver-utils chromium-browser unclutter

# 2. Add user to required groups for display + input access
echo "[2/3] Adding $(whoami) to video, input, render, tty groups..."
sudo usermod -aG video,input,render,tty "$(whoami)"

# 3. Allow xinit from console without root
echo "[3/3] Configuring Xwrapper..."
sudo tee /etc/X11/Xwrapper.config > /dev/null << 'XWRAP'
allowed_users=anybody
needs_root_rights=yes
XWRAP

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
