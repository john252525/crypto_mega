"""CLI entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@click.group()
def main():
    """CryptoMega — Massive crypto trading signal system."""
    pass


@main.command()
@click.option("--host", default=None, help="API host")
@click.option("--port", default=None, type=int, help="API port")
def serve(host: str | None, port: int | None):
    """Start the API server."""
    import os
    import uvicorn
    h = host or os.getenv("HOST", "0.0.0.0")
    p = port or int(os.getenv("PORT", "8000"))
    uvicorn.run("crypto_mega.api.app:app", host=h, port=p, reload=True)


@main.command()
@click.option("--strategy-dir", default="strategies_user", help="Directory with strategy files")
@click.option("--symbols", default="BTC/USDT,ETH/USDT", help="Comma-separated trading pairs")
@click.option("--interval", default=60.0, help="Signal generation interval (seconds)")
def run(strategy_dir: str, symbols: str, interval: float):
    """Run the signal engine with all loaded strategies."""
    from crypto_mega.engine.orchestrator import Orchestrator

    symbol_list = [s.strip() for s in symbols.split(",")]
    orchestrator = Orchestrator(strategy_dir=strategy_dir, symbols=symbol_list)
    asyncio.run(orchestrator.start(interval=interval))


@main.command()
@click.argument("strategy_name")
@click.option("--symbols", default="BTC/USDT", help="Comma-separated trading pairs")
@click.option("--timeframe", default="1h", help="Timeframe")
@click.option("--grid/--no-grid", default=False, help="Run grid search")
@click.option("--capital", default=10000.0, help="Initial capital")
@click.option("--max-combos", default=None, type=int, help="Max grid search combinations")
def backtest(strategy_name: str, symbols: str, timeframe: str, grid: bool, capital: float, max_combos: int | None):
    """Backtest a strategy."""
    asyncio.run(_run_backtest(strategy_name, symbols, timeframe, grid, capital, max_combos))


async def _run_backtest(name: str, symbols: str, tf: str, grid: bool, capital: float, max_combos: int | None):
    from rich.console import Console
    from rich.table import Table

    from crypto_mega.backtester.backtester import Backtester
    from crypto_mega.data.provider import DataProvider
    from crypto_mega.strategies.loader import strategy_loader
    from crypto_mega.utils.types import StrategyConfig, TimeFrame

    console = Console()

    # Load strategies
    strategy_loader.load_directory("strategies_user")
    cls = strategy_loader.get(name)
    if not cls:
        console.print(f"[red]Strategy not found: {name}[/red]")
        console.print(f"Available: {list(strategy_loader.list_all().keys())}")
        return

    symbol_list = [s.strip() for s in symbols.split(",")]
    cfg = StrategyConfig(name=name, symbols=symbol_list, timeframes=[TimeFrame(tf)])

    # Fetch data
    dp = DataProvider()
    await dp.init_exchange("binance", {"enableRateLimit": True})
    console.print(f"[cyan]Fetching data for {symbol_list}...[/cyan]")
    data = await dp.fetch_multi(symbol_list, [tf], limit=500)
    await dp.close()

    bt = Backtester(initial_capital=capital)

    if grid:
        console.print(f"[cyan]Running grid search...[/cyan]")
        results = bt.grid_search(cls, data, cfg, max_combinations=max_combos)

        table = Table(title=f"Grid Search Results — {name}")
        table.add_column("Rank", style="cyan")
        table.add_column("Parameters")
        table.add_column("PnL", style="green")
        table.add_column("PnL %", style="green")
        table.add_column("Trades")
        table.add_column("Win Rate")
        table.add_column("Sharpe")
        table.add_column("Max DD")
        table.add_column("PF")

        for i, r in enumerate(results[:20]):
            table.add_row(
                str(i + 1),
                str(r.parameters),
                f"${r.total_pnl:.2f}",
                f"{r.total_pnl_pct:.1f}%",
                str(r.total_trades),
                f"{r.win_rate:.1f}%",
                f"{r.sharpe_ratio:.2f}",
                f"{r.max_drawdown:.1f}%",
                f"{r.profit_factor:.2f}",
            )
        console.print(table)
    else:
        strategy = cls(cfg)
        result = bt.run(strategy, data, cfg)
        console.print(f"\n[bold]Backtest: {name}[/bold]")
        console.print(f"  PnL: ${result.total_pnl:.2f} ({result.total_pnl_pct:.1f}%)")
        console.print(f"  Trades: {result.total_trades} (Win: {result.winning_trades}, Loss: {result.losing_trades})")
        console.print(f"  Win Rate: {result.win_rate:.1f}%")
        console.print(f"  Sharpe: {result.sharpe_ratio:.2f}")
        console.print(f"  Max Drawdown: {result.max_drawdown:.1f}%")
        console.print(f"  Profit Factor: {result.profit_factor:.2f}")
        console.print(f"  Runtime: {result.run_time_sec:.3f}s")


@main.command()
def strategies():
    """List available strategies."""
    from rich.console import Console
    from rich.table import Table

    from crypto_mega.strategies.loader import strategy_loader

    strategy_loader.load_directory("strategies_user")

    console = Console()
    table = Table(title="Available Strategies")
    table.add_column("Name", style="cyan")
    table.add_column("Class")

    for name, cls in strategy_loader.list_all().items():
        table.add_row(name, f"{cls.__module__}.{cls.__name__}")
    console.print(table)


if __name__ == "__main__":
    main()
