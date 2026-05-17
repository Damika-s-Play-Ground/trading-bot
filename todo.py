#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""Compatibility wrapper for the roadmap / TODO dashboard."""
import runpy

if __name__ == "__main__":
    runpy.run_module("trading_bot.dashboards.todo_page", run_name="__main__")
