# OmegaAgent Deployment Guide

Step-by-step instructions to deploy the full stack and test end-to-end.

---

## Prerequisites

### PN64 (Primary Server)
- Linux (Ubuntu 22.04+ recommended)
- Docker + Docker Compose installed
- Network access to Desktop and RPis
- Git installed

### Desktop (GPU Server)
- Ubuntu 22.04+ with NVIDIA drivers installed
- RTX 3060 Ti (12GB VRAM)
- Docker + Docker Compose + NVIDIA Container Toolkit
- Git installed

### RPi 4 & RPi 400
- Raspberry Pi OS (64-bit recommended)
- Python 3.11+
- Network access to PN64 and Desktop

---

## Phase 1: Deploy PN64 Backend

SSH into your PN64:

```bash
# 1. Clone the repo
cd ~
git clone git@github.com:JaeminBBQ/OmegaAgent.git
cd OmegaAgent

# 2. Configure environment
cp .env.example .env
nano .env
```

Edit `.env` and fill in:
```bash
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
SERPER_API_KEY=your-serper-key-if-you-have-one
GPU_SERVER_URL=http://desktop:5000  # or use desktop's LAN IP
DEFAULT_TIMEZONE=America/Los_Angeles
LOG_LEVEL=INFO
```

> **Note**: If you don't have Supabase or Serper keys yet, leave them blank. The weather agent will still work (it just won't persist results or do web searches).

```bash
# 3. Start the backend
docker compose up -d --build

# 4. Verify it's running
docker ps
# Should show: omega-agent container running

# 5. Test the API
curl http://localhost:8080/status
# Should return JSON with status: "ok" or "degraded"

curl -X POST http://localhost:8080/agents/weather/run | jq
# Should return weather data for Reno, NV with Haiku summary
```

### Troubleshooting PN64

```bash
# View logs
docker logs omega-agent -f

# Restart
docker compose restart

# Rebuild after code changes
docker compose up -d --build
```

---

## Phase 2: Deploy Desktop GPU Services

The Desktop will run Whisper STT and Fish Speech TTS. For now, let's set up a minimal test server to verify the PN64 can reach it.

SSH into your Desktop:

```bash
# 1. Create a test GPU service directory
mkdir -p ~/gpu-services
cd ~/gpu-services

# 2. Create a simple test server
cat > test_server.py << 'EOF'
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok", "service": "desktop-gpu-test"}

@app.post("/stt")
async def stt_placeholder(audio: bytes = None):
    return {"transcription": "Test STT response - Whisper not installed yet"}

@app.post("/tts")
async def tts_placeholder(text: str = ""):
    return {"audio_url": "test.wav", "message": "Test TTS response - Fish Speech not installed yet"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
EOF

# 3. Install FastAPI
python3 -m pip install fastapi uvicorn

# 4. Run the test server
python3 test_server.py
```

From the PN64, test connectivity:
```bash
curl http://desktop:5000/health
# Should return: {"status":"ok","service":"desktop-gpu-test"}
```

> **Later**: You'll replace this test server with actual Whisper + Fish Speech containers. For now, this proves the network path works.

---

## Phase 3: Test PN64 ↔ Desktop Communication

On the PN64, verify the GPU_SERVER_URL is reachable:

```bash
# From inside the omega-agent container
docker exec omega-agent curl http://desktop:5000/health

# Or test from PN64 host
curl http://desktop:5000/health
```

If this fails, check:
1. Desktop firewall allows port 5000
2. Both machines are on the same LAN
3. Hostname resolution works (try IP instead: `http://192.168.1.x:5000`)

---

## Phase 4: Deploy RPi Clients

The RPi clients are simple Python scripts that hit the PN64 API. Let's create a minimal test client.

### RPi 4 (or RPi 400) Setup

SSH into your RPi:

```bash
# 1. Clone the repo
cd ~
git clone git@github.com:JaeminBBQ/OmegaAgent.git
cd OmegaAgent

# 2. Create a test client
mkdir -p clients/test
cat > clients/test/test_client.py << 'EOF'
#!/usr/bin/env python3
"""
Minimal RPi test client.
Tests failover: PN64 primary, Desktop fallback.
"""
import asyncio
import httpx

PRIMARY = "http://pn64:8080"
FALLBACK = "http://desktop:8080"

async def get_active_host():
    """Discover which server is up."""
    print(f"Checking primary: {PRIMARY}")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{PRIMARY}/status")
            if r.status_code == 200 and r.json().get("status") in ["ok", "degraded"]:
                print(f"✓ Primary is up: {PRIMARY}")
                return PRIMARY
    except Exception as e:
        print(f"✗ Primary failed: {e}")
    
    print(f"Checking fallback: {FALLBACK}")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{FALLBACK}/status")
            if r.status_code == 200:
                print(f"✓ Fallback is up: {FALLBACK}")
                return FALLBACK
    except Exception as e:
        print(f"✗ Fallback failed: {e}")
    
    raise RuntimeError("No servers available")

async def test_weather():
    """Test the weather agent."""
    host = await get_active_host()
    print(f"\nCalling weather agent on {host}...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{host}/agents/weather/run")
        r.raise_for_status()
        data = r.json()
    
    print(f"\n{'='*60}")
    print(f"Location: {data['location']}")
    print(f"Current: {data['current']['temperature_f']}°F, {data['current']['weather_description']}")
    print(f"Alerts: {len(data['alerts'])}")
    print(f"\nSummary:\n{data['summary']}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    asyncio.run(test_weather())
EOF

chmod +x clients/test/test_client.py

# 3. Install dependencies
python3 -m pip install httpx

# 4. Run the test
python3 clients/test/test_client.py
```

Expected output:
```
Checking primary: http://pn64:8080
✓ Primary is up: http://pn64:8080

Calling weather agent on http://pn64:8080...

============================================================
Location: Reno, NV
Current: 74.1°F, Overcast
Alerts: 0

Summary:
**Current Conditions:** Overcast and mild at 74°F...
============================================================
```

### Test Failover

1. Stop the PN64 backend:
   ```bash
   # On PN64
   docker compose down
   ```

2. Start the backend on Desktop (fallback):
   ```bash
   # On Desktop
   cd ~/OmegaAgent
   cp .env.example .env
   nano .env  # Fill in same keys as PN64
   docker compose up -d --build
   ```

3. Run the RPi test client again:
   ```bash
   # On RPi
   python3 clients/test/test_client.py
   ```

   Should now show:
   ```
   Checking primary: http://pn64:8080
   ✗ Primary failed: ...
   Checking fallback: http://desktop:8080
   ✓ Fallback is up: http://desktop:8080
   ```

4. Bring PN64 back up:
   ```bash
   # On PN64
   docker compose up -d
   ```

---

## Phase 5: End-to-End Test Checklist

Run through this checklist to verify everything works:

### PN64 Backend
- [ ] `docker ps` shows `omega-agent` running
- [ ] `curl http://localhost:8080/status` returns `{"status": "ok"}` or `{"status": "degraded"}`
- [ ] `curl -X POST http://localhost:8080/agents/weather/run` returns weather data with Haiku summary
- [ ] `docker logs omega-agent` shows scheduler started with 1 job (`weather_reno`)

### Desktop GPU Test Server
- [ ] `curl http://desktop:5000/health` returns `{"status": "ok"}`
- [ ] From PN64: `curl http://desktop:5000/health` works (network path verified)

### RPi Client
- [ ] Test client discovers PN64 as primary
- [ ] Test client successfully calls weather agent
- [ ] When PN64 is down, test client falls back to Desktop
- [ ] When PN64 comes back up, test client uses it again

### Scheduled Jobs
- [ ] Wait 2 hours (or change interval in `main.py` to 5 minutes for testing)
- [ ] Check logs: `docker logs omega-agent | grep weather`
- [ ] Should see automatic weather agent runs every 2 hours

---

## Next Steps After Testing

Once everything above works:

1. **Desktop GPU Services**: Replace the test server with actual Whisper + Fish Speech containers
2. **RPi Clients**: Build the full dashboard (touchscreen UI, mic input, speaker output)
3. **More Agents**: Add the next agent (closing tracker is urgent per your roadmap)
4. **Supabase Setup**: Configure Supabase to persist agent results
5. **Serper Integration**: Add web search to agents that need it

---

## Troubleshooting

### PN64 can't reach Desktop
```bash
# Check firewall on Desktop
sudo ufw status
sudo ufw allow 5000/tcp

# Test with IP instead of hostname
curl http://192.168.1.x:5000/health
```

### RPi can't reach PN64
```bash
# Check PN64 firewall
sudo ufw allow 8080/tcp

# Test with IP
curl http://192.168.1.y:8080/status
```

### Docker container won't start
```bash
# Check logs
docker logs omega-agent

# Common issues:
# - Port 8080 already in use: `sudo lsof -i :8080`
# - Missing .env file: `cp .env.example .env`
# - Bad API key: check .env values
```

### Weather agent returns fallback summary
- Check `ANTHROPIC_API_KEY` is set correctly in `.env`
- Verify model name is correct: `claude-haiku-4-5`
- Check logs: `docker logs omega-agent | grep -i anthropic`

---

## Quick Reference

### PN64 Commands
```bash
cd ~/OmegaAgent
docker compose up -d --build    # Start
docker compose down             # Stop
docker compose restart          # Restart
docker logs omega-agent -f      # View logs
git pull && docker compose up -d --build  # Update
```

### Desktop Commands
```bash
cd ~/gpu-services
python3 test_server.py          # Run test server
# Later: docker compose up -d   # Run Whisper + Fish
```

### RPi Commands
```bash
cd ~/OmegaAgent
python3 clients/test/test_client.py  # Test failover + weather agent
```
