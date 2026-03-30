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
curl http://172.16.0.200:8080/status
# Should return JSON with status: "ok" or "degraded"

curl -X POST http://172.16.0.200:8080/agents/weather/run | jq
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

## Phase 2: Verify Desktop GPU Services

The Desktop (`172.16.0.94`) runs 3 GPU-accelerated services. These should already be running.

### Health checks

From the PN64 (or any machine on the LAN):
```bash
curl http://172.16.0.94:8000/v1/health   # Whisper STT
curl http://172.16.0.94:8080/v1/health   # Fish Speech TTS
curl http://172.16.0.94:8081/v1/health   # Kokoro TTS
# All should return: {"status": "ok"}
```

### Test STT (Whisper)
```bash
# Record a short clip (or use any .wav file)
curl http://172.16.0.94:8000/v1/audio/transcriptions \
  -F "file=@test_audio.wav"
# Returns: {"text": "Your transcribed text here."}
```

### Test TTS (Kokoro — fast)
```bash
curl -X POST http://172.16.0.94:8081/v1/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from OmegaAgent.", "voice": "af_heart"}' \
  --output test_kokoro.wav
# Should produce a playable WAV file
```

### Test TTS (Fish Speech — quality)
```bash
curl -X POST http://172.16.0.94:8080/v1/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from OmegaAgent."}' \
  --output test_fish.wav
```

See `API_REFERENCE.md` for full endpoint documentation.

---

## Phase 3: Test PN64 ↔ Desktop Communication

From the PN64 host, verify the OmegaAgent container can reach the desktop GPU services:

```bash
# From the PN64 host directly
curl http://172.16.0.94:8000/v1/health
curl http://172.16.0.94:8080/v1/health
curl http://172.16.0.94:8081/v1/health

# From inside the omega-agent container
docker exec omega-agent curl http://172.16.0.94:8000/v1/health
docker exec omega-agent curl http://172.16.0.94:8080/v1/health
docker exec omega-agent curl http://172.16.0.94:8081/v1/health
```

The `/status` endpoint also reports GPU service health:
```bash
curl http://172.16.0.200:8080/status | jq '.services[] | select(.name | startswith("whisper") or startswith("fish") or startswith("kokoro"))'
```

If this fails, check:
1. Desktop firewall allows ports 8000, 8080, 8081
2. Both machines are on the same VLAN/subnet
3. GPU services are running on the desktop (`docker ps` on desktop)

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

PRIMARY = "http://172.16.0.200:8080"    # PN64
FALLBACK = "http://172.16.0.94:8080"   # Desktop (fallback)

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
