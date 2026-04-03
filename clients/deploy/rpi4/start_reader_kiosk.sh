#!/usr/bin/env bash
# Launch OmegaReader in fullscreen kiosk mode on the RPi 4.
# This script is called by the omega-reader.desktop autostart entry.
set -e

OMEGA_HOST="${OMEGA_HOST:-172.16.0.200}"
READER_URL="http://${OMEGA_HOST}:8080/reading/ui"

# Wait for network + OmegaAgent to be reachable
echo "[reader] Waiting for OmegaAgent at ${OMEGA_HOST}..."
for i in $(seq 1 60); do
    if curl -sf "http://${OMEGA_HOST}:8080/ping" >/dev/null 2>&1; then
        echo "[reader] Server is up."
        break
    fi
    sleep 2
done

# Disable screen blanking / power management
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true
xset s noblank 2>/dev/null || true

# Hide cursor after 3 seconds of inactivity (requires unclutter)
if command -v unclutter >/dev/null 2>&1; then
    unclutter -idle 3 -root &
fi

# Kill any existing Chromium instances
pkill -f "chromium.*kiosk" 2>/dev/null || true
sleep 1

# Launch Chromium in kiosk mode
exec chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --disable-translate \
    --no-first-run \
    --start-fullscreen \
    --autoplay-policy=no-user-gesture-required \
    --check-for-update-interval=31536000 \
    "${READER_URL}"
