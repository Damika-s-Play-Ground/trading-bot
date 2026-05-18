#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
from __future__ import annotations

import json
from collections import defaultdict

from trading_bot.core.state_store import load_json_path, save_json_path
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PERFORMANCE_JOURNAL_FILE = REPO_ROOT / "performance_journal.json"
OUTPUT_FILE = REPO_ROOT / "data" / "allocation_optimizer_snapshot.json"
BOT_SEQUENCE = ["dca", "trend", "grid", "momentum", "deep_mr"]


def _load_json(path: Path, default: Any) -> Any:
    return load_json_path(path, default)


def _save_json(path: Path, payload: Any) -> None:
    save_json_path(path, payload)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def build_snapshot(window: int = 48) -> dict[str, Any]:
    journal = _load_json(PERFORMANCE_JOURNAL_FILE, {"runs": []})
    runs = journal.get("runs", []) if isinstance(journal, dict) else []
    recent = runs[-window:]
    aggregates: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    latest_regime = recent[-1].get("regime") if recent else None

    for run in recent:
        bots = run.get("bots", {}) if isinstance(run.get("bots"), dict) else {}
        for bot_key in BOT_SEQUENCE:
            bot = bots.get(bot_key, {}) if isinstance(bots.get(bot_key), dict) else {}
            aggregates[bot_key]["allocation_pct"].append(_safe_float(bot.get("allocation_pct")))
            aggregates[bot_key]["drawdown_pct"].append(_safe_float(bot.get("drawdown_pct")))
            aggregates[bot_key]["drift_pct"].append(abs(_safe_float(bot.get("drift_pct"))))
            aggregates[bot_key]["win_rate"].append(_safe_float(bot.get("win_rate"), 50.0))
            aggregates[bot_key]["expectancy"].append(_safe_float(bot.get("expectancy")))
            aggregates[bot_key]["profit_factor"].append(_safe_float(bot.get("profit_factor"), 1.0))
            aggregates[bot_key]["current_total"].append(_safe_float(bot.get("current_total")))
            aggregates[bot_key]["target_capital"].append(_safe_float(bot.get("target_capital")))

    recommendations: dict[str, Any] = {}
    for bot_key in BOT_SEQUENCE:
        bucket = aggregates.get(bot_key, {})
        count = max(len(bucket.get("allocation_pct", [])), 1)
        avg_drawdown = sum(bucket.get("drawdown_pct", [0.0])) / count
        avg_drift = sum(bucket.get("drift_pct", [0.0])) / count
        avg_win_rate = sum(bucket.get("win_rate", [50.0])) / count
        avg_expectancy = sum(bucket.get("expectancy", [0.0])) / count
        avg_profit_factor = sum(bucket.get("profit_factor", [1.0])) / count
        avg_current = sum(bucket.get("current_total", [0.0])) / count
        avg_target = sum(bucket.get("target_capital", [0.0])) / count
        deployment_score = (
            (avg_win_rate - 50.0) * 0.012
            + avg_expectancy * 1.35
            + (avg_profit_factor - 1.0) * 0.22
            - avg_drawdown * 0.02
            - avg_drift * 0.004
        )
        multiplier = max(0.82, min(1.18, 1.0 + deployment_score))
        bias = "boost" if multiplier > 1.02 else ("trim" if multiplier < 0.98 else "hold")
        recommendations[bot_key] = {
            "multiplier": round(multiplier, 3),
            "bias": bias,
            "confidence": round(min(100.0, 35.0 + count * 1.2 + abs(avg_expectancy) * 30.0 + abs(avg_profit_factor - 1.0) * 25.0), 1),
            "inputs": {
                "sample_runs": count,
                "avg_drawdown_pct": round(avg_drawdown, 2),
                "avg_drift_pct": round(avg_drift, 2),
                "avg_win_rate": round(avg_win_rate, 2),
                "avg_expectancy": round(avg_expectancy, 4),
                "avg_profit_factor": round(avg_profit_factor, 3),
                "avg_current_total": round(avg_current, 2),
                "avg_target_capital": round(avg_target, 2),
            },
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": window,
        "latest_regime": latest_regime,
        "recommendations": recommendations,
    }
    _save_json(OUTPUT_FILE, payload)
    return payload


def load_snapshot() -> dict[str, Any]:
    return _load_json(OUTPUT_FILE, {})


def main() -> None:
    payload = build_snapshot()
    print("Allocation optimizer snapshot complete")
    print(f"Saved: {OUTPUT_FILE}")
    for bot_key in BOT_SEQUENCE:
        rec = payload.get("recommendations", {}).get(bot_key, {})
        print(f"{bot_key:<9} multiplier={rec.get('multiplier', 1.0):>4} bias={rec.get('bias', 'hold'):<4} confidence={rec.get('confidence', 0):>5}")


if __name__ == "__main__":
    main()
