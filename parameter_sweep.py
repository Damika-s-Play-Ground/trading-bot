#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""Compatibility wrapper for reorganized package layout."""
import runpy

if __name__ == "__main__":
    runpy.run_module("trading_bot.analysis.parameter_sweep", run_name="__main__")
