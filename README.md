# OmegaAgent

Self-hosted modular AI platform running on a home network. The PN64 runs all backend services (FastAPI, agents, scheduling, cloud APIs). The desktop handles GPU-accelerated workloads only (STT, TTS). RPi 400 client consumes the API over LAN.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  PN64 (primary server)                               │
│  Linux · i7 · 64GB DDR5                              │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │ FastAPI   │ │ Agents   │ │ Scheduler│             │
│  │ :8080     │ │ weather  │ │ APSched  │             │
│  │           │ │ jobs     │ │          │             │
│  └──────────┘ │ snow ... │ └──────────┘             │
│               └──────────┘                           │
│  Cloud APIs: Anthropic · Supabase · Serper           │
└───────────────────┬──────────────────────────────────┘
                    │ LAN
                    │
      ┌─────────────┼─────────────┐
      │             │             │
  ┌───▼────┐  ┌────▼──────┐
  │RPi 400 │  │  Desktop  │
  │Keyboard│  │  GPU Box  │
  │ + TTS  │  │ RTX 3060Ti│
  │ Work   │  │           │
  │ Assist │  │ Whisper   │
  └────────┘  │ Fish TTS  │
              └───────────┘
```

### What lives where

| Machine | Role | Runs |
|---|---|---|
| **PN64** | Primary server | FastAPI backend, all agents, APScheduler, Playwright, cloud API calls (Anthropic, Supabase, Serper) |
| **Desktop** | GPU services | Whisper Large v3 Turbo (STT), Fish Speech S1-mini (TTS), future local models |
| **RPi 400** | Keyboard + TTS client | Obsidian note capture, work assistant, TTS playback |

### Failover

RPi 400 client hits `/status` on the PN64 first (2s timeout). If the PN64 is down, it can fall back to the desktop running the same FastAPI image. The active host is cached for 30 seconds.

```python
PRIMARY = "http://172.16.0.200:8080"    # PN64
FALLBACK = "http://172.16.0.94:8080"   # Desktop

async def get_active_host():
    try:
        r = await httpx.get(f"{PRIMARY}/status", timeout=2.0)
        if r.json()["status"] == "ok":
            return PRIMARY
    except:
        pass
    return FALLBACK
```

---

## Quick Start (Development — Mac/Linux)

```bash
# 1. Clone
git clone <your-repo-url> OmegaAgent
cd OmegaAgent

# 2. Create venv
python3 -m venv venv
source venv/bin/activate

# 3. Install deps
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY

# 5. Run
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

Test it:
```bash
curl http://172.16.0.200:8080/status
curl -X POST http://172.16.0.200:8080/agents/weather/run
```

---

## PN64 Deployment (Primary Server)

The PN64 runs all backend services. No GPU required.

### Prerequisites
- Docker + Docker Compose

### Steps

```bash
# 1. Clone the repo
git clone <your-repo-url> ~/OmegaAgent
cd ~/OmegaAgent

# 2. Configure environment
cp .env.example .env
nano .env
# Fill in ALL keys — see "API Keys" section below

# 3. Start
docker compose up -d --build

# 4. Verify
curl http://localhost:8080/status
```

### Updating
```bash
cd ~/OmegaAgent
git pull
docker compose up -d --build
```

---

## Desktop GPU Server

The desktop only runs GPU-accelerated model services. It does NOT run the FastAPI backend or agents in normal operation.

### Services (`172.16.0.94`)
| Service | Port | Model | Purpose |
|---|---|---|---|
| Whisper STT | `:8000` | Large v3 Turbo | Speech-to-text transcription |
| Fish Speech TTS | `:8080` | S1-mini | High-quality TTS with voice cloning (~2-3s) |
| Kokoro TTS | `:8081` | 82M | Fast lightweight TTS (~instant) |

Health checks: `GET http://172.16.0.94:{port}/v1/health`

The PN64 proxies STT/TTS requests to the desktop via `WHISPER_URL`, `FISH_TTS_URL`, `KOKORO_TTS_URL` in `.env`. See `API_REFERENCE.md` for full endpoint documentation.

> Desktop can also run the full OmegaAgent stack as a fallback if the PN64 goes down. Just clone the repo, configure `.env`, and `docker compose up -d --build`.

---

## RPi Client

### RPi 400 (Keyboard + TTS Work Assistant)

The RPi 400 is a keyboard-only work assistant tied to the Obsidian vault. No screen.

**What it does:**
- Captures quick notes/tasks via keyboard input
- Sends to Haiku for structuring and tagging
- Stores in Obsidian vault + Supabase via the API
- TTS output for confirmations and agent responses

---

## API Keys & Services

| Service | Key | Where it's used | Required for |
|---|---|---|---|
| **Anthropic** | `ANTHROPIC_API_KEY` | `core/llm.py` | All agents (Haiku summaries, analysis) |
| **Supabase** | `SUPABASE_URL`, `SUPABASE_KEY` | `core/db.py` | Persisting agent results, future RAG storage |
| **Serper** | `SERPER_API_KEY` | `core/search.py` | Agents needing web search (jobs, salary, reno intel) |
| **Whisper STT** | `WHISPER_URL` | `core/speech.py` | Speech-to-text via desktop GPU |
| **Fish TTS** | `FISH_TTS_URL` | `core/speech.py` | High-quality TTS via desktop GPU |
| **Kokoro TTS** | `KOKORO_TTS_URL` | `core/speech.py` | Fast TTS via desktop GPU |

### What works without keys

| Service | Without key |
|---|---|
| Anthropic | Agents fall back to simple text summaries (no LLM analysis) |
| Supabase | Agent results not persisted (returned in API response only) |
| Serper | Search-dependent agents won't function |
| GPU Services | STT/TTS unavailable (agents + text API still work fine) |

---

## Project Structure

```
OmegaAgent/
├── main.py                    # FastAPI entry point + lifecycle
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
│
├── core/                      # Shared infrastructure (do NOT put agent code here)
│   ├── config.py              # Env var loading
│   ├── llm.py                 # Claude Haiku/Sonnet wrapper
│   ├── db.py                  # Supabase client
│   ├── search.py              # Serper web search
│   ├── scraper.py             # Playwright browser scraping
│   ├── speech.py              # Whisper STT + Fish/Kokoro TTS wrapper
│   └── embeddings.py          # Embedding client (provider TBD)
│
├── agents/                    # Each agent is its own package
│   └── weather/
│       ├── api.py             # Open-Meteo async client
│       ├── models.py          # Pydantic schemas
│       └── agent.py           # WeatherAgent class
│
├── api/
│   ├── models.py              # Shared API response schemas
│   └── routes/
│       ├── status.py          # GET /status (health + failover)
│       └── agents.py          # POST /agents/{name}/run
│
├── scheduler/
│   └── jobs.py                # APScheduler setup
│
└── clients/                   # RPi client code (future)
    ├── rpi_dashboard/
    ├── rpi400/
    └── web/
```

### Adding a New Agent

Every agent follows the same pattern. Create `agents/<name>/`:

```
agents/new_agent/
├── __init__.py       # from .agent import NewAgent
├── api.py            # Domain-specific API client (if needed)
├── models.py         # Pydantic schemas
└── agent.py          # Agent class with run() and should_alert()
```

Agent class template:
```python
from core.llm import LLMClient
from core.db import DBClient
from core.search import SearchClient

class NewAgent:
    def __init__(self, llm: LLMClient, db: DBClient, search: SearchClient):
        self.llm = llm
        self.db = db
        self.search = search

    async def run(self) -> dict:
        # 1. Fetch/scrape data
        # 2. Analyze with Haiku
        # 3. Store results in Supabase
        # 4. Return structured result
        pass

    async def should_alert(self) -> bool:
        # Threshold/condition logic
        pass
```

Then register in `main.py` and `api/routes/agents.py`.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/status` | Platform health + per-service status (used for failover) |
| `POST` | `/agents/weather/run` | Run weather agent (optional lat/lon override) |
| `GET` | `/docs` | Auto-generated OpenAPI docs |

---

## Scheduled Jobs

| Job | Interval | Description |
|---|---|---|
| `weather_reno` | Every 2 hours | Fetch Reno weather + forecast, generate Haiku summary |

---

## Agent Status

| Agent | Status | Priority |
|---|---|---|
| Weather | ✅ Working | Phase 1 |
| Snow | Not started | Phase 1 |
| Job Scraper | Not started | Phase 1 |
| Experience Builder | Not started | Phase 1 |
| Closing Tracker | Not started | 🔴 Urgent (Apr 10) |
| Cert Tracker | Not started | Phase 2 |
| Salary Intelligence | Not started | Phase 2 |
| Home Maintenance | Not started | Phase 3 |
| Budget Monitor | Not started | Phase 3 |
| Reno Intelligence | Not started | Phase 3 |
| Incident Log | Not started | Phase 3 |
