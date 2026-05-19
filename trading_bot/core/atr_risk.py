from __future__ import annotations

from typing import Any

DEFAULT_SETTINGS = {
    "enabled": True,
    "period": 14,
    "risk_per_trade_pct": 1.0,
    "stop_atr_multiple": 2.0,
    "take_profit_atr_multiple": 3.0,
    "trailing_activation_atr_multiple": 1.5,
    "trailing_distance_atr_multiple": 1.0,
    "min_stop_loss_pct": 2.0,
    "max_stop_loss_pct": 12.0,
    "min_take_profit_pct": 4.0,
    "max_take_profit_pct": 20.0,
    "min_trailing_activation_pct": 2.0,
    "max_trailing_activation_pct": 12.0,
    "min_trailing_distance_pct": 1.0,
    "max_trailing_distance_pct": 8.0,
    "min_position_multiplier": 0.5,
    "max_position_multiplier": 2.0,
}


def merged_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    if isinstance(settings, dict):
        merged.update(settings)
    return merged


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(float(lower), min(float(upper), float(value)))


def _to_candle_values(candle: Any) -> tuple[float, float, float] | None:
    if isinstance(candle, dict):
        try:
            return float(candle["high"]), float(candle["low"]), float(candle["close"])
        except Exception:
            return None
    if isinstance(candle, (list, tuple)) and len(candle) >= 4:
        try:
            return float(candle[1]), float(candle[2]), float(candle[3])
        except Exception:
            return None
    return None


def calculate_atr(candles: list[Any], period: int = 14) -> float:
    if not candles:
        return 0.0
    normalized: list[tuple[float, float, float]] = []
    for candle in candles:
        values = _to_candle_values(candle)
        if values is not None:
            normalized.append(values)
    if not normalized:
        return 0.0
    window_size = max(1, int(period))
    start_idx = max(0, len(normalized) - window_size)
    window = normalized[start_idx:]
    prev_close: float | None = normalized[start_idx - 1][2] if start_idx > 0 else None
    true_ranges: list[float] = []
    for high, low, close in window:
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(max(0.0, tr))
        prev_close = close
    return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0


def atr_percent(atr_value: float, price: float) -> float:
    if price <= 0:
        return 0.0
    return max(0.0, float(atr_value) / float(price) * 100.0)


def resolve_atr_exit_profile(
    price: float,
    atr_value: float,
    settings: dict[str, Any] | None = None,
    *,
    fixed_stop_loss_pct: float | None = None,
    fixed_take_profit_pct: float | None = None,
    fixed_trailing_activation_pct: float | None = None,
    fixed_trailing_distance_pct: float | None = None,
) -> dict[str, float]:
    cfg = merged_settings(settings)
    atr_pct_value = atr_percent(atr_value, price)

    stop_floor = _clamp(
        atr_pct_value * float(cfg["stop_atr_multiple"]),
        float(cfg["min_stop_loss_pct"]),
        float(cfg["max_stop_loss_pct"]),
    )
    take_profit_floor = _clamp(
        atr_pct_value * float(cfg["take_profit_atr_multiple"]),
        float(cfg["min_take_profit_pct"]),
        float(cfg["max_take_profit_pct"]),
    )
    trailing_activation_floor = _clamp(
        atr_pct_value * float(cfg["trailing_activation_atr_multiple"]),
        float(cfg["min_trailing_activation_pct"]),
        float(cfg["max_trailing_activation_pct"]),
    )
    trailing_distance_floor = _clamp(
        atr_pct_value * float(cfg["trailing_distance_atr_multiple"]),
        float(cfg["min_trailing_distance_pct"]),
        float(cfg["max_trailing_distance_pct"]),
    )

    fixed_stop_abs = abs(float(fixed_stop_loss_pct)) if fixed_stop_loss_pct is not None else stop_floor
    fixed_take_profit = float(fixed_take_profit_pct) if fixed_take_profit_pct is not None else take_profit_floor
    fixed_trailing_activation = (
        float(fixed_trailing_activation_pct) if fixed_trailing_activation_pct is not None else trailing_activation_floor
    )
    fixed_trailing_distance = (
        float(fixed_trailing_distance_pct) if fixed_trailing_distance_pct is not None else trailing_distance_floor
    )

    stop_loss_pct = -max(fixed_stop_abs, stop_floor)
    take_profit_pct = max(fixed_take_profit, take_profit_floor)
    trailing_activation_pct = max(fixed_trailing_activation, trailing_activation_floor)
    trailing_distance_pct = max(fixed_trailing_distance, trailing_distance_floor)

    return {
        "atr_value": round(float(atr_value), 8),
        "atr_pct": round(atr_pct_value, 4),
        "stop_loss_pct": round(stop_loss_pct, 4),
        "take_profit_pct": round(take_profit_pct, 4),
        "trailing_activation_pct": round(trailing_activation_pct, 4),
        "trailing_distance_pct": round(trailing_distance_pct, 4),
    }


def normalize_position_size(
    *,
    target_capital: float,
    base_notional: float,
    atr_pct_value: float,
    settings: dict[str, Any] | None = None,
) -> float:
    cfg = merged_settings(settings)
    if base_notional <= 0:
        return 0.0
    stop_width_pct = _clamp(
        max(0.0, float(atr_pct_value)) * float(cfg["stop_atr_multiple"]),
        float(cfg["min_stop_loss_pct"]),
        float(cfg["max_stop_loss_pct"]),
    )
    if stop_width_pct <= 0:
        return float(base_notional)
    risk_budget = max(0.0, float(target_capital)) * float(cfg["risk_per_trade_pct"]) / 100.0
    if risk_budget <= 0:
        return float(base_notional)
    risk_based_notional = risk_budget / (stop_width_pct / 100.0)
    lower = float(base_notional) * float(cfg["min_position_multiplier"])
    if stop_width_pct <= float(cfg["min_stop_loss_pct"]):
        upper = float(base_notional) * float(cfg["max_position_multiplier"])
    else:
        upper = float(base_notional)
    return round(_clamp(risk_based_notional, lower, upper), 6)
