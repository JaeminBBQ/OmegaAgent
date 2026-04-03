#!/usr/bin/env bash
# Launch OmegaReader in fullscreen kiosk mode on the RPi 4.
# Works on TTY-only (no desktop) using cage, or with an existing X11/Wayland desktop.
set -e

OMEGA_HOST="${OMEGA_HOST:-172.16.0.200}"
READER_URL="http://${OMEGA_HOST}:8080/reading/ui"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
mkdir -p "$XDG_RUNTIME_DIR" 2>/dev/null || true

# Wait for network + OmegaAgent to be reachable
echo "[reader] Waiting for OmegaAgent at ${OMEGA_HOST}..."
for i in $(seq 1 60); do
    if curl -sf "http://${OMEGA_HOST}:8080/ping" >/dev/null 2>&1; then
        echo "[reader] Server is up."
        break
    fi
    sleep 2
done

# Common Chromium flags (no keyring prompt, kiosk, autoplay audio)
CHROMIUM_FLAGS=(
    --kiosk
    --noerrdialogs
    --disable-infobars
    --disable-session-crashed-bubble
    --disable-restore-session-state
    --disable-translate
    --no-first-run
    --start-fullscreen
    --password-store=basic
    --disable-features=LockProfileCookieDatabase
    --autoplay-policy=no-user-gesture-required
    --check-for-update-interval=31536000
    --enable-features=UseOzonePlatform
    --ozone-platform=wayland
)

# Kill any existing kiosk instances
pkill -f "chromium.*kiosk" 2>/dev/null || true
sleep 1

# Detect display environment
SESSION="${XDG_SESSION_TYPE:-tty}"
echo "[reader] Session type: $SESSION"

if [ "$SESSION" = "x11" ]; then
    # Running inside an X11 desktop — use X directly
    export DISPLAY="${DISPLAY:-:0}"
    export XAUTHORITY="${XAUTHORITY:-/home/jaeminbbq/.Xauthority}"
    xset s off 2>/dev/null || true
    xset -dpms 2>/dev/null || true
    command -v unclutter >/dev/null 2>&1 && unclutter -idle 3 -root &
    echo "[reader] Launching Chromium on X11..."
    # Remove ozone flags for X11
    exec chromium-browser \
        --kiosk --noerrdialogs --disable-infobars \
        --disable-session-crashed-bubble --disable-restore-session-state \
        --disable-translate --no-first-run --start-fullscreen \
        --password-store=basic --disable-features=LockProfileCookieDatabase \
        --autoplay-policy=no-user-gesture-required \
        --check-for-update-interval=31536000 \
        "${READER_URL}"

elif [ "$SESSION" = "wayland" ]; then
    # Running inside an existing Wayland desktop
    echo "[reader] Launching Chromium on Wayland..."
    exec chromium-browser "${CHROMIUM_FLAGS[@]}" "${READER_URL}"

else
    # TTY / no desktop — use cage as a minimal Wayland compositor
    if ! command -v cage >/dev/null 2>&1; then
        echo "[reader] ERROR: No display server and 'cage' is not installed."
        echo "[reader] Install it with:  sudo apt install cage"
        exit 1
    fi
    echo "[reader] No desktop detected — launching cage kiosk compositor..."
    # cage runs a single app fullscreen with no decorations
    exec cage -- chromium-browser "${CHROMIUM_FLAGS[@]}" "${READER_URL}"
fi
