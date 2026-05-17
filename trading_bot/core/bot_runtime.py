import os


def get_env_float(name, default):
    raw = os.environ.get(name)
    if raw in (None, ""):
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def get_target_capital(default):
    return max(0.0, get_env_float("BOT_CAPITAL", default))


def get_blocked_coins():
    raw = os.environ.get("BLOCKED_COINS", "")
    return {coin.strip().upper() for coin in raw.split(",") if coin.strip()}


def new_buys_disabled():
    return os.environ.get("BOT_DISABLE_NEW_BUYS", "0") == "1"


def get_available_budget(current_total_value, default_budget, target_capital):
    remaining_capacity = max(0.0, float(target_capital) - float(current_total_value))
    return max(0.0, min(float(default_budget), remaining_capacity))


def scale_trade_size(default_trade_size, target_capital, default_capital):
    if default_capital <= 0:
        return float(default_trade_size)
    scale = float(target_capital) / float(default_capital)
    scale = max(0.35, min(1.75, scale))
    return max(2.0, float(default_trade_size) * scale)
