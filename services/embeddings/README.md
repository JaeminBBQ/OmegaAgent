# Self-Hosted Embedding Service

Sentence-transformers embedding service for OmegaAgent RAG pipeline.

## Model

**bge-large-en-v1.5** (BAAI)
- 1024 dimensions
- Optimized for retrieval tasks
- SOTA performance on academic papers
- ~1.3GB VRAM

## Deployment (GPU Server)

```bash
# On 172.16.0.94 (3060 Ti)
cd ~/Projects/OmegaAgent/services/embeddings
docker compose up -d --build

# Check health
curl http://172.16.0.94:8082/v1/health

# Test embedding
curl -X POST http://172.16.0.94:8082/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"texts": ["Hello world", "Test embedding"]}'
```

## API

### POST /v1/embeddings

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

### GET /v1/health

Health check.

**Response:**
```json
{
  "status": "ok",
  "model": "BAAI/bge-large-en-v1.5",
  "device": "cuda",
  "dimensions": 1024
}
```

## Performance

- **Throughput**: ~1000 chunks/sec on 3060 Ti
- **Latency**: ~10ms per text (single), ~100ms for batch of 100
- **VRAM**: ~1.3GB

## Integration

OmegaAgent uses `core/embeddings.py` client to communicate with this service.
