# Kokoro TTS - Native Setup

Kokoro TTS runs natively on Windows/Ubuntu for best performance. Use the existing `kokoro_server.py` from the main OmegaAgent repo.

## Windows Setup

### 1. Install Python 3.11+
Download from [python.org](https://www.python.org/downloads/)

### 2. Install Dependencies
```powershell
# Open PowerShell as Administrator
cd C:\path\to\OmegaAgent

# Create virtual environment
python -m venv venv-kokoro
.\venv-kokoro\Scripts\activate

# Install dependencies
pip install fastapi uvicorn[standard] kokoro-onnx numpy scipy
```

### 3. Run Kokoro Server
```powershell
# Activate venv
.\venv-kokoro\Scripts\activate

# Run server (port 8081)
python services\kokoro\kokoro_server.py
```

### 4. Auto-start on Boot (Optional)
Create a scheduled task:
1. Open Task Scheduler
2. Create Basic Task → "Kokoro TTS"
3. Trigger: At startup
4. Action: Start a program
   - Program: `C:\path\to\OmegaAgent\venv-kokoro\Scripts\python.exe`
   - Arguments: `C:\path\to\OmegaAgent\services\kokoro\kokoro_server.py`
   - Start in: `C:\path\to\OmegaAgent`

---

## Ubuntu Setup

### 1. Install Python 3.11+
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
```

### 2. Install Dependencies
```bash
cd ~/OmegaAgent

# Create virtual environment
python3.11 -m venv venv-kokoro
source venv-kokoro/bin/activate

# Install dependencies
pip install fastapi uvicorn[standard] kokoro-onnx numpy scipy
```

### 3. Run Kokoro Server
```bash
# Activate venv
source ~/OmegaAgent/venv-kokoro/bin/activate

# Run server (port 8081)
python services/kokoro/kokoro_server.py
```

### 4. Auto-start on Boot (systemd)
Create a systemd service:

```bash
sudo nano /etc/systemd/system/kokoro-tts.service
```

Add:
```ini
[Unit]
Description=Kokoro TTS Service
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/OmegaAgent
Environment="PATH=/home/YOUR_USERNAME/OmegaAgent/venv-kokoro/bin"
ExecStart=/home/YOUR_USERNAME/OmegaAgent/venv-kokoro/bin/python services/kokoro/kokoro_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable kokoro-tts
sudo systemctl start kokoro-tts

# Check status
sudo systemctl status kokoro-tts

# View logs
journalctl -u kokoro-tts -f
```

---

## Test

```bash
# Check health
curl http://localhost:8081/v1/health

# Generate speech
curl -X POST http://localhost:8081/v1/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from Kokoro", "voice": "af_bella"}' \
  --output test.wav
```

## Network Access

If you need to access Kokoro from other machines (like the PN64):

**Windows Firewall:**
```powershell
New-NetFirewallRule -DisplayName "Kokoro TTS" -Direction Inbound -LocalPort 8081 -Protocol TCP -Action Allow
```

**Ubuntu Firewall:**
```bash
sudo ufw allow 8081/tcp
```

Then update OmegaAgent's `.env` on the PN64:
```bash
KOKORO_TTS_URL=http://172.16.0.94:8081
```
