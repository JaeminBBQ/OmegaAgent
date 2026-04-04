FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download embedding model at build time
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-large-en-v1.5')"

# Download Kokoro TTS model at build time
RUN python -c "from kokoro import generate; print('Kokoro model loaded')"

# Copy service files
COPY embeddings_server.py .
COPY kokoro_server.py .
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8082 8081

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
