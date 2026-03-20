# CryptoMega — Massive Crypto Trading Signal System

Pluggable, scalable crypto trading system with dynamic strategy loading, resource management, backtesting, and auto-execution.

## ⚡ Deploy to Railway (2 min)

```bash
railway init
# Add PostgreSQL 15 and Redis 7 plugins in dashboard
railway variables set EXCHANGE_API_KEY=xxx EXCHANGE_API_SECRET=xxx EXCHANGE_SANDBOX=true
railway up
```

That's it! Railway auto-creates 3 services (api, engine, worker) from Procfile, injects DATABASE_URL/REDIS_URL, deploys, and watches health checks.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          API / Dashboard                              │
│                     (FastAPI REST + WebSocket)                        │
├──────────┬──────────┬──────────┬──────────┬──────────┬───────────────┤
│ Strategy │  Signal  │ Resource │Execution │ Monitor  │    Risk       │
│  Loader  │  Engine  │ Manager  │ Engine   │          │   Manager     │
│          │          │          │          │          │               │
│ .py file │ Run all  │ Priority │ Exchange │ Theo vs  │ Position size │
│ code str │ strats   │ based    │ API via  │ Real PnL │ Drawdown ctrl │
│ GPT code │ parallel │ compute  │ ccxt     │ Diverge  │ Kill switch   │
│ hot-load │ dispatch │ alloc    │ routing  │ alerts   │ Daily limits  │
├──────────┴──────────┼──────────┴──────────┼──────────┴───────────────┤
│    Data Provider     │    Backtester       │      Orchestrator        │
│   (ccxt + cache)     │ (grid/random search)│   (wires everything)     │
└──────────────────────┴─────────────────────┴─────────────────────────┘
```

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# List strategies
crypto-mega strategies

# Backtest a strategy
crypto-mega backtest SMACrossover --symbols BTC/USDT --timeframe 1h

# Grid search optimization
crypto-mega backtest SMACrossover --symbols BTC/USDT --grid --max-combos 50

# Start API server
crypto-mega serve

# Run signal engine
crypto-mega run --symbols BTC/USDT,ETH/USDT --interval 60
```

## Adding a Strategy

Drop a `.py` file into `strategies_user/` or POST code to the API:

```python
from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection

class MyStrategy(BaseStrategy):
    def generate_signals(self, data):
        signals = []
        for key, df in data.items():
            symbol = key.split("_")[0]
            # Your logic here
            if some_condition:
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=0.8,
                    price=df.iloc[-1]["close"],
                ))
        return signals

    def param_grid(self):
        return {"my_param": [1, 2, 3, 4, 5]}
```

Or via API:
```bash
curl -X POST http://localhost:8000/strategies/load-code \
  -H "Content-Type: application/json" \
  -d '{"code": "class X(BaseStrategy): ...", "symbols": ["BTC/USDT"]}'
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/strategies/load-code` | POST | Load strategy from code string |
| `/strategies/load-file` | POST | Load strategy from file |
| `/strategies` | GET | List all strategies |
| `/backtest` | POST | Run backtest / grid search |
| `/resources` | GET | Resource allocation status |
| `/resources/priority` | POST | Set strategy priority |
| `/resources/adjustments` | GET | Pending auto-adjustments |
| `/execution/pending` | GET | Signals awaiting approval |
| `/execution/approve` | POST | Approve signal for execution |
| `/monitor/stats` | GET | Performance stats + recommendations |
| `/monitor/alerts` | GET | Divergence alerts |
| `/risk` | GET | Risk/portfolio status |
| `/risk/kill-switch/activate` | POST | Emergency stop |
| `/status` | GET | Full system status |

## Resource Management Modes

- **Manual**: Admin sets priorities directly (0-100)
- **Auto**: System adjusts based on Sharpe ratio, win rate, PnL trend
- **Hybrid**: System proposes, admin approves
- **Random**: Equal distribution (exploration mode)

Higher priority = more compute cycles, more workers, faster update interval.

## Risk Controls

- Per-trade risk: max % of portfolio
- Max drawdown: auto-pause trading
- Position limits: max size, max count
- Daily limits: max trades, max loss
- Kill switch: emergency halt (manual or auto at threshold)
