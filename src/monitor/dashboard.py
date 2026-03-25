"""
Rich terminal dashboard.

Displays live P&L, signal heatmap, active positions, and agent activity.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

if TYPE_CHECKING:
    from src.risk.portfolio import PortfolioManager
    from src.fusion.bayesian import BayesianResult


console = Console()


def make_header(mode: str) -> Panel:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode_color = "red" if mode == "live" else "yellow"
    text = Text()
    text.append("POLYMARKET NEWS BOT ", style="bold cyan")
    text.append(f"[{mode.upper()}] ", style=f"bold {mode_color}")
    text.append(f"| {ts}", style="dim")
    return Panel(text, box=box.HEAVY)


def make_portfolio_panel(portfolio: "PortfolioManager") -> Panel:
    s = portfolio.state
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Key", style="dim", width=20)
    table.add_column("Value", style="bold")

    pnl_color = "green" if s.total_pnl >= 0 else "red"
    table.add_row("Portfolio Value", f"${s.total_value:.2f}")
    table.add_row("Total P&L", Text(f"{s.total_pnl:+.2f} ({s.total_pnl_pct:+.1%})", style=pnl_color))
    table.add_row("Cash", f"${s.current_cash:.2f}")
    table.add_row("Exposure", f"${s.total_exposure_usd:.2f} ({s.exposure_pct:.1%})")
    table.add_row("Trades", f"{s.total_trades} (Win: {s.win_rate:.0%})")
    table.add_row("Fees Paid", f"${s.total_fees_paid:.2f}")
    return Panel(table, title="Portfolio", border_style="green")


def make_positions_panel(portfolio: "PortfolioManager") -> Panel:
    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("Market", style="cyan", max_width=35)
    table.add_column("Dir", width=4)
    table.add_column("Size", width=8)
    table.add_column("Entry", width=7)
    table.add_column("Current", width=8)
    table.add_column("P&L", width=8)

    for market_id, pos in portfolio.state.positions.items():
        pnl = pos.unrealized_pnl
        pnl_color = "green" if pnl >= 0 else "red"
        dir_color = "green" if pos.direction == "YES" else "red"
        table.add_row(
            market_id[:35],
            Text(pos.direction, style=dir_color),
            f"${pos.size_usd:.2f}",
            f"{pos.entry_price:.3f}",
            f"{pos.current_price:.3f}",
            Text(f"{pnl:+.2f}", style=pnl_color),
        )

    if not portfolio.state.positions:
        table.add_row("No open positions", "", "", "", "", "")

    return Panel(table, title="Open Positions", border_style="blue")


def make_signals_panel(results: list["BayesianResult"]) -> Panel:
    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("Market", style="cyan", max_width=30)
    table.add_column("Prior", width=6)
    table.add_column("Post", width=6)
    table.add_column("Edge", width=7)
    table.add_column("Trade", width=6)
    table.add_column("Signals", width=6)

    for result in results[-8:]:   # show last 8
        edge_color = "green" if result.effective_edge > 0 else "red" if result.effective_edge < -0.03 else "dim"
        trade_color = "green" if result.trade_direction == "YES" else "red" if result.trade_direction == "NO" else "dim"
        table.add_row(
            result.market_id[:30],
            f"{result.prior_prob:.3f}",
            f"{result.posterior_prob:.3f}",
            Text(f"{result.effective_edge:+.3f}", style=edge_color),
            Text(result.trade_direction, style=trade_color),
            str(result.signal_count),
        )

    return Panel(table, title="Signal Analysis", border_style="yellow")


def make_activity_panel(log_lines: list[str]) -> Panel:
    text = Text()
    for line in log_lines[-15:]:
        if "ERROR" in line:
            text.append(f"{line}\n", style="red")
        elif "WARNING" in line:
            text.append(f"{line}\n", style="yellow")
        elif "FILL" in line or "TRADE" in line:
            text.append(f"{line}\n", style="bold green")
        else:
            text.append(f"{line}\n", style="dim")
    return Panel(text, title="Activity Log", border_style="dim")


class Dashboard:
    """Rich live dashboard for the trading agent."""

    def __init__(self, portfolio: "PortfolioManager", trading_mode: str = "paper") -> None:
        self._portfolio = portfolio
        self._trading_mode = trading_mode
        self._recent_results: list["BayesianResult"] = []
        self._log_lines: list[str] = []
        self._live: Live | None = None

    def add_result(self, result: "BayesianResult") -> None:
        self._recent_results.append(result)
        if len(self._recent_results) > 50:
            self._recent_results = self._recent_results[-50:]

    def log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_lines.append(f"[{ts}] {message}")
        if len(self._log_lines) > 200:
            self._log_lines = self._log_lines[-200:]

    def _build_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(make_header(self._trading_mode), size=3),
            Layout(name="main"),
            Layout(make_activity_panel(self._log_lines), size=18),
        )
        layout["main"].split_row(
            Layout(name="left"),
            Layout(make_signals_panel(self._recent_results)),
        )
        layout["left"].split_column(
            make_portfolio_panel(self._portfolio),
            make_positions_panel(self._portfolio),
        )
        return layout

    def start_live(self) -> None:
        self._live = Live(
            self._build_layout(),
            console=console,
            refresh_per_second=1,
            screen=True,
        )
        self._live.__enter__()

    def update(self) -> None:
        if self._live:
            self._live.update(self._build_layout())

    def stop(self) -> None:
        if self._live:
            self._live.__exit__(None, None, None)

    def print_static(self) -> None:
        """Print a static snapshot (for non-interactive use)."""
        console.print(make_header(self._trading_mode))
        console.print(make_portfolio_panel(self._portfolio))
        console.print(make_positions_panel(self._portfolio))
        if self._recent_results:
            console.print(make_signals_panel(self._recent_results))
