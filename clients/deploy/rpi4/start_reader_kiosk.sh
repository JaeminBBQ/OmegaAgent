#!/usr/bin/env bash
# Launch OmegaReader in fullscreen kiosk mode on the RPi 4.
# Uses xinit + X11 on TTY (best touchscreen support), or existing desktop if available.
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

# Remove any .asoundrc that conflicts with PipeWire
rm -f "$HOME/.asoundrc"

# Set EMEET as default mic/speaker via PipeWire (pactl)
if command -v pactl >/dev/null 2>&1; then
    EMEET_SOURCE=$(pactl list sources short 2>/dev/null | grep -i "emeet" | grep -v monitor | head -1 | awk '{print $2}')
    if [ -n "$EMEET_SOURCE" ]; then
        pactl set-default-source "$EMEET_SOURCE" 2>/dev/null
        echo "[reader] Default mic → $EMEET_SOURCE"
    else
        echo "[reader] EMEET mic not found in PipeWire sources:"
        pactl list sources short 2>/dev/null || true
    fi
    EMEET_SINK=$(pactl list sinks short 2>/dev/null | grep -i "emeet" | head -1 | awk '{print $2}')
    if [ -n "$EMEET_SINK" ]; then
        pactl set-default-sink "$EMEET_SINK" 2>/dev/null
        echo "[reader] Default speaker → $EMEET_SINK"
    fi
else
    echo "[reader] pactl not found — Chromium may not detect EMEET mic"
fi

# Chromium flags (no keyring, kiosk, autoplay audio, touch)
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
    --touch-events=enabled
    --use-fake-ui-for-media-stream
    --unsafely-treat-insecure-origin-as-secure="http://${OMEGA_HOST}:8080"
    --enable-features=WebRTCPipeWireCapturer
)

# Kill any existing kiosk instances
pkill -f "chromium.*kiosk" 2>/dev/null || true
sleep 1

# Detect display environment
SESSION="${XDG_SESSION_TYPE:-tty}"
echo "[reader] Session type: $SESSION"

if [ "$SESSION" = "x11" ] || [ -n "$DISPLAY" ]; then
    # Already inside an X11 session (desktop or xinit)
    export DISPLAY="${DISPLAY:-:0}"
    xset s off 2>/dev/null || true
    xset -dpms 2>/dev/null || true
    xset s noblank 2>/dev/null || true
    command -v unclutter >/dev/null 2>&1 && unclutter -idle 3 -root &
    echo "[reader] Launching Chromium on X11 (DISPLAY=$DISPLAY)..."
    exec chromium-browser "${CHROMIUM_FLAGS[@]}" "${READER_URL}"

elif [ "$SESSION" = "wayland" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    echo "[reader] Launching Chromium on Wayland..."
    exec chromium-browser "${CHROMIUM_FLAGS[@]}" \
        --enable-features=UseOzonePlatform --ozone-platform=wayland \
        "${READER_URL}"

else
    # TTY — no display server. Start a minimal X11 session with xinit.
    if [ -n "$SSH_CONNECTION" ] || [ -n "$SSH_TTY" ]; then
        echo "[reader] ERROR: Cannot start X from SSH."
        echo "[reader] This runs automatically from .bash_profile on the physical console."
        echo "[reader] Or reboot to trigger autologin on tty1."
        exit 1
    fi

    if ! command -v xinit >/dev/null 2>&1; then
        echo "[reader] ERROR: xinit not found."
        echo "[reader] Install: sudo apt install xserver-xorg xinit x11-xserver-utils unclutter"
        exit 1
    fi

    echo "[reader] Starting X11 kiosk via xinit on $(tty)..."

    # Create a temporary .xinitrc that launches Chromium directly
    XINITRC=$(mktemp /tmp/omega-xinitrc.XXXXXX)
    cat > "$XINITRC" << XINIT_EOF
#!/bin/sh
# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Hide cursor after idle
unclutter -idle 3 -root &

# Launch Chromium kiosk
exec chromium-browser \\
    --kiosk \\
    --noerrdialogs \\
    --disable-infobars \\
    --disable-session-crashed-bubble \\
    --disable-restore-session-state \\
    --disable-translate \\
    --no-first-run \\
    --start-fullscreen \\
    --password-store=basic \\
    --disable-features=LockProfileCookieDatabase \\
    --autoplay-policy=no-user-gesture-required \\
    --check-for-update-interval=31536000 \\
    --touch-events=enabled \\
    --use-fake-ui-for-media-stream \\
    --unsafely-treat-insecure-origin-as-secure="http://${OMEGA_HOST}:8080" \\
    --enable-features=WebRTCPipeWireCapturer \\
    "${READER_URL}"
XINIT_EOF
    chmod +x "$XINITRC"

    # xinit starts X server + runs our script — touchscreen works natively
    exec xinit "$XINITRC" -- :0 vt$(tty | grep -o '[0-9]*')
fi
