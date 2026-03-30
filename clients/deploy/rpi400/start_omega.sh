#!/bin/bash
# Auto-start script for OmegaAgent RPi 400 Assistant in tmux
#
# Replaces: note-assistant/start_voice.sh
# Key difference: No local AI, no venv, no API keys — just httpx → PN64

PROJECT_DIR="/home/jaeminbbq/Projects/OmegaAgent/clients"
VENV_DIR="$PROJECT_DIR/.venv"
SESSION_NAME="omega"

# Change to project directory
cd "$PROJECT_DIR" || { echo "ERROR: $PROJECT_DIR not found"; exit 1; }

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Try to raise window to top in background (for desktop autostart)
(
    sleep 2
    if command -v wmctrl &> /dev/null; then
        wmctrl -a "OmegaAgent" 2>/dev/null || true
    fi
    if command -v xdotool &> /dev/null; then
        WID=$(xdotool search --name "OmegaAgent" | head -1)
        if [ -n "$WID" ]; then
            xdotool windowactivate "$WID" 2>/dev/null || true
        fi
    fi
) &

# Check if tmux session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session already exists. Attaching..."
    tmux attach -t "$SESSION_NAME"
else
    # Create new tmux session and run the assistant
    tmux new-session -s "$SESSION_NAME" "cd $PROJECT_DIR && source .venv/bin/activate && python3 rpi400_assistant.py"
fi
