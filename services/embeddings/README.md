# AI Services (GPU Server)

Combined Kokoro TTS + Embeddings service running on GPU for optimal performance.

## Services

### 1. Kokoro TTS (Port 8081)
**Model**: Kokoro-82M (ONNX optimized)
- Fast lightweight TTS
- 11 voices (English)
- ~200ms latency
- ~500MB VRAM

### 2. Embeddings (Port 8082)
**Model**: bge-large-en-v1.5 (BAAI)
- 1024 dimensions
- Optimized for retrieval tasks
- SOTA performance on academic papers
- ~1.3GB VRAM

**Total VRAM**: ~1.8GB (plenty of room on 3060 Ti)

## Deployment (GPU Server)

```bash
# On 172.16.0.94 (3060 Ti)
cd ~/Projects/OmegaAgent/services/embeddings
docker compose up -d --build

# Check health
curl http://172.16.0.94:8081/v1/health  # Kokoro
curl http://172.16.0.94:8082/v1/health  # Embeddings
```

## API Reference

### Kokoro TTS

**POST /v1/tts**

Generate speech from text.

**Request:**
```json
{
  "text": "Hello from Kokoro",
  "voice": "af_bella",
  "speed": 1.0
}
```

**Response**: WAV audio (24kHz mono)

**Available voices**: `af_heart`, `af_bella`, `af_nicole`, `af_sarah`, `af_sky`, `am_adam`, `am_michael`, `bf_emma`, `bf_isabella`, `bm_george`, `bm_lewis`

**GET /v1/voices** - List available voices

---

### Embeddings

**POST /v1/embeddings**

Generate embeddings for texts.

**Request:**
```json
{
  "texts": ["text1", "text2"],
  "normalize": true
}
```

**Response:**
```json
{
  "embeddings": [[0.1, 0.2, ...], [0.3, 0.4, ...]],
  "model": "BAAI/bge-large-en-v1.5",
  "dimensions": 1024
}
```

## Performance

**Kokoro TTS:**
- Latency: ~200ms per sentence
- Throughput: ~5 requests/sec

**Embeddings:**
- Throughput: ~1000 chunks/sec
- Latency: ~10ms per text (single), ~100ms for batch of 100

## Integration

- `core/speech.py` - Kokoro TTS client
- `core/embeddings.py` - Embeddings client
