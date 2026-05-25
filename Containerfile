# Containerfile — works with both Podman and Docker.
# Data, memory, and .env are volume-mounted at runtime — nothing sensitive is baked in.

FROM python:3.12-slim

WORKDIR /app

# libgomp1 is required by ONNX Runtime (ChromaDB bundled embeddings).
# Without it the semantic memory layer fails to initialize on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies as a separate layer so rebuilds after
# source-only changes don't re-download packages.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source. data/ and .env are excluded via .containerignore and
# mounted from the host at runtime so they survive image rebuilds.
COPY . .

EXPOSE 8080

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
