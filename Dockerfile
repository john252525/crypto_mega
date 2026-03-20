FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy everything first (need package for setup)
COPY . .

# Install package + deps
RUN pip install --no-cache-dir -e .

# Railway injects $PORT at runtime; Procfile overrides CMD per service
CMD ["sh", "-c", "uvicorn crypto_mega.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
