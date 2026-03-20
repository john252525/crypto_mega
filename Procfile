# Alternative to railway.toml — Heroku-compatible Procfile
# Railway also supports Procfile for defining services.
web: uvicorn crypto_mega.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
engine: python -m crypto_mega.cli run --symbols BTC/USDT,ETH/USDT,SOL/USDT --interval 60
worker: celery -A crypto_mega.engine.tasks:celery_app worker --loglevel=info --concurrency=${MAX_WORKERS:-4}
