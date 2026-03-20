FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy app code
COPY . .

# Install the package itself
RUN pip install --no-cache-dir -e .

# Default command — overridden per service in railway.toml
CMD ["uvicorn", "crypto_mega.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
