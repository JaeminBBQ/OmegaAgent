# RPi 4 Voice Assistant — Setup

## Prerequisites
```bash
sudo apt install portaudio19-dev tmux
```

## Install
```bash
cd ~/Projects/OmegaAgent/clients
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure
Create `~/Projects/OmegaAgent/clients/.env`:
```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
WAKE_WORD_MODEL=hey_jarvis
WAKE_WORD_THRESHOLD=0.5
AUDIO_DEVICE=EMEET
```

## Manual Run
```bash
cd ~/Projects/OmegaAgent/clients
set -a && source .env && set +a && python3 rpi4_assistant.py
```

## Autostart (systemd — headless, runs on boot)
```bash
# Copy service file
sudo cp ~/Projects/OmegaAgent/clients/deploy/rpi4/omega-voice.service /etc/systemd/system/

# Make start script executable
chmod +x ~/Projects/OmegaAgent/clients/deploy/rpi4/start_omega_voice.sh

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable omega-voice
sudo systemctl start omega-voice

# Check status / logs
sudo systemctl status omega-voice
journalctl -u omega-voice -f
```

## Autostart (tmux — interactive, attach to see output)
Add to crontab (`crontab -e`):
```
@reboot sleep 10 && /home/jaeminbbq/Projects/OmegaAgent/clients/deploy/rpi4/start_omega_voice.sh
```

Then attach to see it: `tmux attach -t omega-voice`

---

## OmegaReader — Kiosk Mode (fullscreen reading UI)

### Prerequisites
```bash
sudo apt install chromium-browser unclutter
```

### Setup
```bash
# Make kiosk script executable
chmod +x ~/Projects/OmegaAgent/clients/deploy/rpi4/start_reader_kiosk.sh

# Copy desktop autostart file
mkdir -p ~/.config/autostart
cp ~/Projects/OmegaAgent/clients/deploy/rpi4/omega-reader.desktop ~/.config/autostart/
```

### Manual Launch
```bash
OMEGA_HOST=172.16.0.200 bash ~/Projects/OmegaAgent/clients/deploy/rpi4/start_reader_kiosk.sh
```

### What It Does
- Waits for OmegaAgent server to be reachable
- Disables screen blanking and power management
- Hides cursor after 3 seconds of inactivity
- Launches Chromium in fullscreen kiosk mode at `http://172.16.0.200:8080/reading/ui`
- Autoplay policy allows TTS audio without user gesture

### Exit Kiosk
Press `Alt+F4` to close Chromium, or SSH in and run:
```bash
pkill -f "chromium.*kiosk"
```

### Upload Books
From any computer on the network, navigate to:
```
http://172.16.0.200:8080/reading/ui
```
Or use curl:
```bash
curl -F "file=@mybook.epub" http://172.16.0.200:8080/reading/upload
```

---

## Troubleshooting
- **No audio device**: Check `python3 -c "import sounddevice as sd; print(sd.query_devices())"`
- **Wake word not loading**: Run `python3 -c "import openwakeword; openwakeword.utils.download_models()"`
- **Can't connect to server**: Verify PN64 is running: `curl http://172.16.0.200:8080/status`
- **TTS not working**: GPU desktop must be on for speech services
