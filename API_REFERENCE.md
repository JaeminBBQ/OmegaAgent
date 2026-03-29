# AI Stack API Reference

**Host**: `172.16.0.94`

| Service | Base URL | Purpose |
|---------|----------|---------|
| Fish Speech TTS | `http://172.16.0.94:8080` | Voice cloning, high quality TTS |
| Kokoro TTS | `http://172.16.0.94:8081` | Fast lightweight TTS |
| Whisper STT | `http://172.16.0.94:8000` | Speech-to-text transcription |

---

## Health Checks

```
GET http://172.16.0.94:8080/v1/health   → {"status": "ok"}
GET http://172.16.0.94:8081/v1/health   → {"status": "ok"}
GET http://172.16.0.94:8000/v1/health   → {"status": "ok"}
```

---

## Endpoints

### 1. Fish Speech TTS — `POST http://172.16.0.94:8080/v1/tts`

High-quality TTS with optional voice cloning. ~2-3s latency.

**Content-Type**: `application/json` or `application/msgpack`

**Request body (JSON)**:
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | string | *required* | Text to synthesize |
| `format` | string | `"wav"` | Output format: `wav`, `mp3`, `pcm` |
| `max_new_tokens` | int | `1024` | Max generation tokens |
| `top_p` | float | `0.8` | Top-p sampling (0.1–1.0) |
| `temperature` | float | `0.8` | Sampling temperature (0.1–1.0) |
| `repetition_penalty` | float | `1.1` | Repetition penalty (0.9–2.0) |
| `chunk_length` | int | `200` | Chunk length (100–300) |
| `streaming` | bool | `false` | Stream WAV chunks |

**Response**: Audio file (`audio/wav` by default)

**Example**:
```bash
curl -X POST "http://172.16.0.94:8080/v1/tts" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from Fish Speech."}' \
  --output speech.wav
```

**Interactive docs**: http://172.16.0.94:8080/docs

---

### 2. Kokoro TTS — `POST http://172.16.0.94:8081/v1/tts`

Fast, lightweight TTS (82M params). Instant response, no voice cloning.

**Content-Type**: `application/json`

**Request body**:
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | string | *required* | Text to synthesize |
| `voice` | string | `"af_heart"` | Voice ID (see below) |

**Available voices** (English):
`af_heart`, `af_bella`, `af_nicole`, `af_sarah`, `af_sky`, `am_adam`, `am_michael`, `bf_emma`, `bf_isabella`, `bm_george`, `bm_lewis`

Full list: https://huggingface.co/hexgrad/Kokoro-82M

**Response**: Audio file (`audio/wav`, 24kHz mono)

**Example**:
```bash
curl -X POST "http://172.16.0.94:8081/v1/tts" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from Kokoro.", "voice": "af_bella"}' \
  --output speech.wav
```

---

### 3. Whisper STT — `POST http://172.16.0.94:8000/v1/audio/transcriptions`

OpenAI-compatible speech-to-text endpoint.

**Content-Type**: `multipart/form-data`

**Form fields**:
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file` | file | *required* | Audio file (WAV, MP3, etc.) |
| `model` | string | — | Model name (ignored, uses server default) |
| `language` | string | `null` | Language hint (e.g. `"en"`) |
| `response_format` | string | `"json"` | `json` or `verbose_json` |

**Response** (`json`):
```json
{"text": "Transcribed text here."}
```

**Response** (`verbose_json`):
```json
{"text": "Transcribed text.", "language": "en", "duration": 3.5}
```

**Example**:
```bash
curl http://172.16.0.94:8000/v1/audio/transcriptions \
  -F "file=@audio.wav"
```

---

## Python Client Examples

### TTS with Kokoro (fast)

```python
import requests

def speak(text: str, voice: str = "af_heart") -> bytes:
    """Generate speech using Kokoro TTS. Returns WAV bytes."""
    resp = requests.post(
        "http://172.16.0.94:8081/v1/tts",
        json={"text": text, "voice": voice},
    )
    resp.raise_for_status()
    return resp.content  # WAV audio bytes
```

### TTS with Fish Speech (quality)

```python
import requests

def speak_hq(text: str) -> bytes:
    """Generate speech using Fish Speech TTS. Returns WAV bytes."""
    resp = requests.post(
        "http://172.16.0.94:8080/v1/tts",
        json={"text": text},
    )
    resp.raise_for_status()
    return resp.content  # WAV audio bytes
```

### STT with Whisper

```python
import requests

def transcribe(audio_path: str) -> str:
    """Transcribe audio file to text using Whisper."""
    with open(audio_path, "rb") as f:
        resp = requests.post(
            "http://172.16.0.94:8000/v1/audio/transcriptions",
            files={"file": ("audio.wav", f, "audio/wav")},
        )
    resp.raise_for_status()
    return resp.json()["text"]
```

### Full pipeline: STT → LLM → TTS

```python
import requests

AI_HOST = "http://172.16.0.94"

def transcribe(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        resp = requests.post(
            f"{AI_HOST}:8000/v1/audio/transcriptions",
            files={"file": ("audio.wav", f, "audio/wav")},
        )
    resp.raise_for_status()
    return resp.json()["text"]

def ask_llm(prompt: str) -> str:
    """Replace with your Haiku/Claude API call."""
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

def speak(text: str) -> bytes:
    """Use Kokoro for fast response, Fish Speech for quality."""
    resp = requests.post(
        f"{AI_HOST}:8081/v1/tts",
        json={"text": text},
    )
    resp.raise_for_status()
    return resp.content

# Pipeline
user_text = transcribe("recording.wav")
llm_response = ask_llm(user_text)
audio = speak(llm_response)

with open("response.wav", "wb") as f:
    f.write(audio)
```

---

## Notes

- All endpoints are **unauthenticated** — secure with firewall rules if exposed beyond LAN.
- Fish Speech supports **streaming** (`"streaming": true`) for chunked WAV output.
- Kokoro is ~10x faster than Fish Speech for simple TTS without cloning.
- Max concurrent requests: services are single-worker, requests queue sequentially.
