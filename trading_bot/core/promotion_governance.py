#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
from __future__ import annotations

import json
from datetime import datetime, timezone

from trading_bot.core.state_store import load_json_path, save_json_path
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = REPO_ROOT / "config.json"
MANAGER_STATE_FILE = REPO_ROOT / "manager_state.json"
PERFORMANCE_JOURNAL_FILE = REPO_ROOT / "performance_journal.json"
OUTPUT_FILE = REPO_ROOT / "data" / "live_promotion_report.json"
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


def _gate(name: str, passed: bool, value: Any, requirement: str, note: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "value": value,
        "requirement": requirement,
        "note": note,
    }


def build_promotion_report(manager_state: dict[str, Any] | None = None) -> dict[str, Any]:
    config = _load_json(CONFIG_FILE, {})
    state = manager_state or _load_json(MANAGER_STATE_FILE, {})
    journal = _load_json(PERFORMANCE_JOURNAL_FILE, {"runs": []})
    runs = journal.get("runs", []) if isinstance(journal, dict) else []
    recent_runs = runs[-24:]
    portfolio_risk = state.get("portfolio_risk", {}) if isinstance(state.get("portfolio_risk"), dict) else {}
    perf = state.get("performance", {}) if isinstance(state.get("performance"), dict) else {}

    active_bots = 0
    for bot_key in BOT_SEQUENCE:
        bot = perf.get(bot_key, {}) if isinstance(perf.get(bot_key), dict) else {}
        if _safe_float(bot.get("sell_count")) > 0 or _safe_float(bot.get("current_total")) > 0:
            active_bots += 1

    avg_total = sum(_safe_float(run.get("portfolio_total")) for run in recent_runs) / max(len(recent_runs), 1)
    recent_drawdown = _safe_float(state.get("portfolio_drawdown_pct"))
    stress_loss = _safe_float(portfolio_risk.get("combined_loss_pct"))
    drawdown_breaker = bool(portfolio_risk.get("drawdown_breaker"))
    stress_breaker = bool(portfolio_risk.get("stress_breaker"))
    snapshot = state.get("allocation_optimizer", {}) if isinstance(state.get("allocation_optimizer"), dict) else {}
    mode = str(config.get("mode") or ("paper" if config.get("paper_trading") else "live"))

    gates = [
        _gate("mode_is_paper", mode == "paper", mode, "paper"),
        _gate("paper_run_history", len(runs) >= 30, len(runs), ">= 30 manager journal runs", "Need enough stable paper evidence before any live promotion."),
        _gate("recent_average_equity", avg_total >= 1150.0, round(avg_total, 2), ">= 1150.0 USDT"),
        _gate("portfolio_drawdown", recent_drawdown <= 5.0, round(recent_drawdown, 2), "<= 5.0%"),
        _gate("stress_loss", stress_loss <= 4.0, round(stress_loss, 2), "<= 4.0%"),
        _gate("risk_breakers_clear", not drawdown_breaker and not stress_breaker, {"drawdown_breaker": drawdown_breaker, "stress_breaker": stress_breaker}, "both false"),
        _gate("bot_coverage", active_bots >= 3, active_bots, ">= 3 active bots"),
        _gate("optimizer_snapshot_present", bool(snapshot.get("recommendations")), bool(snapshot.get("recommendations")), "true"),
    ]

    passed = [gate for gate in gates if gate["passed"]]
    failed = [gate for gate in gates if not gate["passed"]]
    status = "controlled_live_ready" if len(failed) == 0 else ("shadow_live_only" if len(failed) <= 2 else "paper_only")
    next_actions = [
        f"Resolve gate: {gate['name']} ({gate['value']} vs {gate['requirement']})"
        for gate in failed[:4]
    ]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "summary": {
            "passed_gates": len(passed),
            "failed_gates": len(failed),
            "mode": mode,
            "active_bots": active_bots,
            "journal_runs": len(runs),
        },
        "gates": gates,
        "next_actions": next_actions,
    }
    _save_json(OUTPUT_FILE, report)
    return report


def main() -> None:
    report = build_promotion_report()
    print("Promotion governance report complete")
    print(f"Saved: {OUTPUT_FILE}")
    print(f"Status: {report['status']}")
    for gate in report["gates"]:
        flag = "PASS" if gate["passed"] else "FAIL"
        print(f"{flag:<4} {gate['name']}: {gate['value']} (need {gate['requirement']})")


if __name__ == "__main__":
    main()
