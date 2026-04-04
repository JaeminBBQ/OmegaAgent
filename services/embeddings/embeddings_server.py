#!/usr/bin/env python3
"""Self-hosted embedding service using sentence-transformers.

Runs on GPU server (172.16.0.94) alongside Whisper/TTS.
Model: bge-large-en-v1.5 (1024 dims, optimized for retrieval)
"""

import logging
from typing import List

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="OmegaAgent Embeddings", version="1.0.0")

# Load model on startup
MODEL_NAME = "BAAI/bge-large-en-v1.5"
model = None


@app.on_event("startup")
async def load_model():
    global model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Loading {MODEL_NAME} on {device}...")
    model = SentenceTransformer(MODEL_NAME, device=device)
    logger.info(f"Model loaded. Embedding dim: {model.get_sentence_embedding_dimension()}")


class EmbedRequest(BaseModel):
    """Request body for embedding generation."""
    texts: List[str] = Field(..., description="List of texts to embed", max_length=100)
    normalize: bool = Field(True, description="Normalize embeddings to unit length")


class EmbedResponse(BaseModel):
    """Response with embeddings."""
    embeddings: List[List[float]] = Field(..., description="List of embedding vectors")
    model: str = Field(..., description="Model name used")
    dimensions: int = Field(..., description="Embedding dimensionality")


@app.post("/v1/embeddings", response_model=EmbedResponse)
async def create_embeddings(request: EmbedRequest):
    """Generate embeddings for a list of texts.
    
    Compatible with OpenAI embeddings API format but returns our model.
    """
    if not model:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    
    try:
        # Generate embeddings
        embeddings = model.encode(
            request.texts,
            normalize_embeddings=request.normalize,
            convert_to_numpy=True,
        )
        
        # Convert to list of lists
        embeddings_list = [emb.tolist() for emb in embeddings]
        
        return EmbedResponse(
            embeddings=embeddings_list,
            model=MODEL_NAME,
            dimensions=model.get_sentence_embedding_dimension(),
        )
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Embedding error: {e}")


@app.get("/v1/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "dimensions": model.get_sentence_embedding_dimension() if model else None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082, log_level="info")
