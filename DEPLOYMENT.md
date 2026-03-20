# Deployment Guide

## Railway (Production)

### Prerequisites
- Railway account (railway.app)
- Git repository

### One-Command Deploy

```bash
railway init          # Link to your repo
railway variables set EXCHANGE_API_KEY=your_key EXCHANGE_API_SECRET=your_secret
railway up
```

That's it. Here's what Railway does automatically:

1. **Reads Dockerfile** → builds image
2. **Reads Procfile** → creates 3 services:
   - `web`: FastAPI API server (public domain)
   - `engine`: Signal generation loop (background)
   - `worker`: Celery workers for backtesting (background)
3. **Injects env vars**:
   - `DATABASE_URL` (PostgreSQL)
   - `REDIS_URL` (Redis)
   - `PORT` (8000)
4. **Health checks** → monitors `/health` endpoint
5. **Auto-restart** → on failure, up to 3 retries

### Manual Setup (if needed)

If Railway doesn't auto-detect, configure in dashboard:

**Plugins:**
- PostgreSQL 15
- Redis 7

**Services** (create each):

| Name | Start Command | Port |
|------|---|---|
| api | `uvicorn crypto_mega.api.app:app --host 0.0.0.0 --port $PORT` | Public |
| engine | `python -m crypto_mega.cli run --symbols BTC/USDT,ETH/USDT --interval 60` | Private |
| worker | `celery -A crypto_mega.engine.tasks:celery_app worker --loglevel=info` | Private |

**Shared Variables:**
```
EXCHANGE_API_KEY=xxx
EXCHANGE_API_SECRET=xxx
EXCHANGE_SANDBOX=true       ← Keep true until you're ready
LOG_LEVEL=INFO
MAX_WORKERS=4
```

### Monitoring

```bash
railway logs api      # API service logs
railway logs engine   # Signal engine logs
railway logs worker   # Celery worker logs
```

### Database Migrations

Railway automatically creates tables on startup (SQLAlchemy creates schema). No manual migration needed.

### WebSocket

Railway's edge automatically handles WebSocket upgrades. Connect to:
- `wss://your-domain.railway.app/ws/signals` (real-time signals)
- `wss://your-domain.railway.app/ws/monitor` (live stats)

---

## Local Development

### Setup

```bash
# Install dependencies
pip install -e ".[dev]"

# Copy env template
cp .env.example .env
# Edit .env with your exchange API keys (keep EXCHANGE_SANDBOX=true)
```

### Run Services

Terminal 1 - Redis (or use `docker run -p 6379:6379 redis:7`):
```bash
redis-server
```

Terminal 2 - PostgreSQL (or use `docker run -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15`):
```bash
# Already have postgres running
```

Terminal 3 - Celery worker:
```bash
celery -A crypto_mega.engine.tasks:celery_app worker --loglevel=info
```

Terminal 4 - Signal engine:
```bash
python -m crypto_mega.cli run --symbols BTC/USDT,ETH/USDT --interval 60
```

Terminal 5 - API server:
```bash
python -m crypto_mega.cli serve
```

Open browser to `http://localhost:8000` → FastAPI docs
Connect WebSocket to `ws://localhost:8000/ws/signals`

### Run Tests

```bash
pytest tests/ -v
```

---

## Load Testing / Stress

If you want to handle tons of strategies/signals:

1. **Increase Celery concurrency**:
   ```
   railway variables set CELERY_CONCURRENCY=16
   ```
   And update Procfile worker line to use it.

2. **Increase max_workers**:
   ```
   railway variables set MAX_WORKERS=8
   ```

3. **Use Railway's horizontal scaling** (paid feature):
   Scale each service independently.

4. **Add caching** (Redis):
   Already set up for Celery task results.

---

## Troubleshooting

### WebSocket disconnects
- Railway edge keeps connections for 60s of inactivity max
- Client should auto-reconnect
- Check `/health` endpoint for service health

### Database pool exhausted
- Set `SQLALCHEMY_POOL_SIZE=20` (default is 10)
- Set `SQLALCHEMY_MAX_OVERFLOW=40`

### Celery tasks timing out
- Increase `task_time_limit` in `crypto_mega/engine/tasks.py` (currently 3600s)
- For grid search, set `max_combinations=100` to limit task size

### Out of memory
- Celery worker uses memory for task state
- Set `CELERYD_MAX_TASKS_PER_CHILD=100` to restart workers periodically

---

## Cost Estimate (Railway)

| Service | Memory | Price/month |
|---------|--------|------------|
| API | 512MB | ~$5 |
| Engine | 512MB | ~$5 |
| Worker | 512MB x 2-4 | ~$5-20 |
| PostgreSQL | 1GB | ~$10 |
| Redis | 256MB | ~$5 |
| **Total** | | **~$30-50** |

You get $5/month free credit from Railway.
