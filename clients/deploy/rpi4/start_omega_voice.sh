#!/bin/bash
# Auto-start script for OmegaAgent RPi 4 Voice Assistant
#
# Runs the always-listening voice assistant in a tmux session.
# Loads .env for DISCORD_WEBHOOK_URL, WAKE_WORD_MODEL, etc.

PROJECT_DIR="/home/jaeminbbq/Projects/OmegaAgent/clients"
VENV_DIR="$PROJECT_DIR/.venv"
SESSION_NAME="omega-voice"

cd "$PROJECT_DIR" || { echo "ERROR: $PROJECT_DIR not found"; exit 1; }

source "$VENV_DIR/bin/activate"

# Load environment variables
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Check if tmux session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session already exists. Attaching..."
    tmux attach -t "$SESSION_NAME"
else
    tmux new-session -s "$SESSION_NAME" \
        "cd $PROJECT_DIR && source .venv/bin/activate && set -a && source .env && set +a && python3 rpi4_assistant.py"
fi
