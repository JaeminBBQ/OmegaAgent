# Project Context — Personal AI Platform
*Provide this to Claude Opus in Windsurf at the start of every session*

---

## Who I Am
Junior DevOps engineer by title, ~4-5 years experience, Masters degree. Underutilized at current job, actively building toward SRE/Platform Engineer roles. Based in Reno, Nevada. Building this platform to upskill, automate personal workflows, and create career leverage. Home closing April 10.

---

## What This Project Is
A self-hosted modular AI platform running on a home network. It consists of always-on backend services running on a desktop GPU machine, with RPi clients consuming the API. The platform hosts local AI models and orchestrates cloud APIs through a unified FastAPI backend. Agents are modular — each one is a new Python module that plugs into shared core infrastructure.

---

## Hardware
- **Desktop (primary server)**: Ubuntu, i7, RTX 3060 Ti 12GB VRAM, 4TB storage. Always-on. Runs all models and the FastAPI backend.
- **PN64 (fallback server)**: Linux, i7, 64GB DDR5 RAM. Failover when desktop is unavailable.
- **RPi 4**: Touchscreen, conference speaker and mic. Voice + visual dashboard client.
- **RPi 400**: Keyboard only, no screen. Work assistant, Obsidian note capture, TTS output.

---

## Failover System
RPi clients hit `/status` on desktop first (2 second timeout), fall back to PN64 if unavailable. Status endpoint returns per-service health. Active host cached 30 seconds.

```python
PRIMARY = "http://desktop:8080"
FALLBACK = "http://pn64:8080"

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

## Model Stack
| Layer | Model | Location |
|---|---|---|
| STT | Whisper Large v3 Turbo | Local GPU |
| TTS | Fish Speech S1-mini (custom voice cloned) | Local GPU |
| Embeddings | nomic-embed-text via Ollama | Local GPU |
| LLM | Claude Haiku (default), Sonnet (complex tasks) | Anthropic API |

VRAM budget: Whisper ~3GB + Fish Speech ~2GB + nomic ~0.5GB = ~5.5GB peak simultaneous. 3060 Ti has 12GB so ~6.5GB free for on-demand models.

---

## Tech Stack
```
Backend:        FastAPI (Python)
Database:       Supabase + pgvector
RAG:            LlamaIndex
Scheduling:     APScheduler
Scraping:       Playwright (local, JavaScript capable)
Search:         Serper API
Config:         python-dotenv / Doppler
Containers:     Docker + NVIDIA Container Toolkit (Ubuntu)
```

---

## API Keys & Services
- **Anthropic** — Claude Haiku (primary LLM), Sonnet (complex reasoning)
- **Serper** — search API for agent broad context queries
- **Supabase** — pgvector + Postgres (RAG storage, structured agent data)
- **Voyage AI** — optional higher quality embeddings (pairs well with Claude)
- **Snow data API** — paid, TBD provider
- All keys managed via Doppler or .env — never hardcoded

---

## Project Structure
```
project/
├── core/
│   ├── llm.py              # Haiku/Sonnet wrapper
│   ├── embeddings.py       # nomic/voyage wrapper
│   ├── search.py           # Serper wrapper
│   ├── scraper.py          # Playwright wrapper
│   └── db.py               # pgvector/Supabase
│
├── agents/
│   ├── snow.py
│   ├── weather.py
│   ├── jobs.py
│   ├── experience_builder.py
│   ├── cert_tracker.py
│   ├── salary_intel.py
│   ├── closing_tracker.py
│   ├── home_maintenance.py
│   ├── budget.py
│   ├── reno_intel.py
│   └── incident_log.py
│
├── api/
│   └── routes/
│       ├── agents.py       # /agents/{name}/run
│       ├── status.py       # /status
│       └── voice.py        # STT/TTS endpoints
│
├── scheduler/
│   └── jobs.py
│
└── clients/
    ├── rpi_dashboard/
    ├── rpi400/
    └── web/
```

---

## Agent Pattern
Every agent follows this structure. Do not deviate from it:

```python
from core.llm import LLMClient
from core.db import DBClient
from core.search import SearchClient

class AgentName:
    def __init__(self, llm: LLMClient, db: DBClient, search: SearchClient):
        self.llm = llm
        self.db = db
        self.search = search

    async def run(self) -> dict:
        # 1. Fetch/scrape data
        # 2. Analyze with Haiku
        # 3. Store results in pgvector/Supabase
        # 4. Return structured result
        pass

    async def should_alert(self) -> bool:
        # Threshold/condition logic
        pass
```

---

## Coding Standards
- **Python 3.11+**
- **Async first** — use `async/await` throughout, httpx not requests
- **Type hints** on all functions
- **Pydantic models** for all API request/response schemas
- **Never hardcode** API keys, URLs, or thresholds — use config
- **Structured logging** — every agent logs what it fetched, what Haiku returned, what was stored
- **Docker-ready** — every service should have a Dockerfile
- Error handling on all external calls — network failures are expected

---

## Current Agent Status
| Agent | Status | Priority |
|---|---|---|
| Snow | Not started | Phase 1 |
| Weather | Not started | Phase 1 |
| Job Scraper | Not started | Phase 1 |
| Experience Builder | Not started | Phase 1 |
| Closing Tracker | Not started | 🔴 Urgent (Apr 10) |
| Cert Tracker | Not started | Phase 2 |
| Salary Intelligence | Not started | Phase 2 |
| Home Maintenance | Not started | Phase 3 |
| Budget Monitor | Not started | Phase 3 |
| Reno Intelligence | Not started | Phase 3 |
| Incident Log | Not started | Phase 3 |

---

## Obsidian Vault (RPi 400)
RAG pipeline for personal knowledge base:

```
vault/
├── Daily/YYYY-MM-DD.md     # daily logs
├── Projects/<name>.md      # project notes
├── Dev/snippets.md         # code snippets
├── Reminders.md            # checkbox items with dates
└── Work/incident-log.md    # work problems solved
```

Nightly job: ingest new notes → Haiku structures and tags → nomic embeddings → pgvector. Query via LlamaIndex semantic search from any device.

Haiku capture system prompt:
```
You are capturing a note. Always extract and return JSON:
{
  "type": "reminder|idea|task|reference|code|incident",
  "project": "project name or null",
  "content": "the actual note",
  "tags": ["relevant", "keywords"],
  "date": "YYYY-MM-DD",
  "priority": "high|medium|low or null"
}
Return only valid JSON, no preamble.
```

---

## Infrastructure Build Order
When starting from scratch, build in this order:
1. FastAPI skeleton + `/status` endpoint
2. pgvector + Supabase connection (db.py)
3. Haiku wrapper (llm.py)
4. Serper wrapper (search.py)
5. Playwright wrapper (scraper.py)
6. nomic embeddings via Ollama (embeddings.py)
7. APScheduler setup (scheduler/jobs.py)
8. Docker + NVIDIA Container Toolkit configuration
9. First agent end-to-end
10. RPi client after first agent works

---

## Important Context
- Desktop runs Ubuntu as primary OS — no WSL, native Docker + NVIDIA Container Toolkit
- PN64 is CPU only fallback — slower inference acceptable for fallback role
- Both desktop and PN64 expose identical API surface so failover is transparent
- RPi 4 is voice + touch client — context aware display, not button-per-agent
- RPi 400 is keyboard + TTS — work hours assistant tied to Obsidian vault
- Custom voice: Fish Speech S1-mini with cloned voice ID — consistent across all TTS calls
- Target job titles: SRE, Platform Engineer (pay better than DevOps junior)
- Home closing April 10 — closing tracker is time sensitive
