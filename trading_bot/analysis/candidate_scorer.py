#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_bot.core.state_store import load_json_path, save_json_path
from trading_bot.dashboards.data_store import load_research_items, sync_all_if_needed

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
CONFIG_FILE = REPO_ROOT / "config.json"
MANAGER_FILE = REPO_ROOT / "manager_state.json"
OUTPUT_FILE = DATA_DIR / "candidate_scores.json"

BOT_WATCHLISTS = {
    "dca": ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT", "MATIC", "NEAR", "ARB", "OP", "ATOM", "INJ", "RNDR", "FET", "GRT", "IMX"],
    "trend": ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "ADA", "AVAX", "DOT", "NEAR"],
    "grid": ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK"],
    "momentum": ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "ADA", "AVAX", "DOT", "NEAR", "ARB", "OP"],
    "deep_mr": ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT", "NEAR", "GRT", "IMX"],
}

POSITIVE_TERMS = {
    "outperform", "breakout", "bullish", "uptrend", "rotation", "accumulate", "strength", "momentum", "reversal", "oversold", "support",
}
NEGATIVE_TERMS = {
    "risk", "rug", "bearish", "breakdown", "overheated", "distribution", "avoid", "warn", "weakness", "downgrade",
}


def _load_json(path: Path, default: Any) -> Any:
    return load_json_path(path, default)


def _save_json(path: Path, payload: Any) -> None:
    save_json_path(path, payload)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _calc_sma(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return values[-1]
    return sum(values[-period:]) / period


def _calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = 0.0
    losses = 0.0
    for idx in range(-period, 0):
        diff = closes[idx] - closes[idx - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _calc_macd_hist(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float:
    if len(closes) < slow + signal:
        return 0.0
    fast_mult = 2 / (fast + 1)
    slow_mult = 2 / (slow + 1)
    signal_mult = 2 / (signal + 1)
    fast_ema = closes[0]
    slow_ema = closes[0]
    signal_ema = 0.0
    macd = 0.0
    first = True
    for close in closes:
        fast_ema = (close - fast_ema) * fast_mult + fast_ema
        slow_ema = (close - slow_ema) * slow_mult + slow_ema
        macd = fast_ema - slow_ema
        if first:
            signal_ema = macd
            first = False
        else:
            signal_ema = (macd - signal_ema) * signal_mult + signal_ema
    return macd - signal_ema


def _fetch_klines(symbol: str, interval: str = "1h", limit: int = 120) -> list[dict[str, float]]:
    qs = urllib.parse.urlencode({"symbol": f"{symbol}USDT", "interval": interval, "limit": limit})
    url = f"https://api.binance.com/api/v3/klines?{qs}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=12) as response:
        payload = json.loads(response.read())
    return [
        {
            "close": _safe_float(row[4]),
            "volume": _safe_float(row[7]),
        }
        for row in payload
    ]


def _indicator_snapshot(symbol: str) -> dict[str, Any]:
    try:
        rows = _fetch_klines(symbol)
        closes = [row["close"] for row in rows if row.get("close")]
        vols = [row["volume"] for row in rows if row.get("volume") is not None]
        if not closes:
            raise ValueError("missing closes")
        price = closes[-1]
        sma20 = _calc_sma(closes, 20)
        sma50 = _calc_sma(closes, 50)
        rsi = _calc_rsi(closes)
        hist = _calc_macd_hist(closes)
        recent_vol = vols[-1] if vols else 0.0
        avg_vol = sum(vols[-20:]) / max(len(vols[-20:]), 1)
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 0.0
        return {
            "price": round(price, 6),
            "rsi": round(rsi, 2),
            "macd_hist": round(hist, 6),
            "ma20": round(sma20, 6),
            "ma50": round(sma50, 6),
            "volume_ratio": round(vol_ratio, 2),
            "trend": "above-ma20" if price >= sma20 else "below-ma20",
        }
    except Exception as exc:
        return {"error": str(exc)}


def _extract_symbols(text: str, universe: set[str]) -> set[str]:
    tokens = set(re.findall(r"\b[A-Z0-9]{2,10}\b", text.upper()))
    return {token for token in tokens if token in universe}


def _active_symbols_from_manager(manager_state: dict[str, Any]) -> set[str]:
    output: set[str] = set()
    exposure = manager_state.get("coin_exposure_pct", {})
    if isinstance(exposure, dict):
        output.update(str(key).upper() for key in exposure.keys())
    return output


def _symbol_universe(config: dict[str, Any], manager_state: dict[str, Any]) -> list[str]:
    coins = set(str(item).upper() for item in config.get("coins", []) if item)
    coins.update(_active_symbols_from_manager(manager_state))
    for watchlist in BOT_WATCHLISTS.values():
        coins.update(watchlist)
    return sorted(coins)


def build_candidate_scores() -> dict[str, Any]:
    sync_all_if_needed(force=True, min_interval=0.0)
    config = _load_json(CONFIG_FILE, {})
    manager_state = _load_json(MANAGER_FILE, {})
    research_items = load_research_items(limit=300)
    universe = _symbol_universe(config, manager_state)
    universe_set = set(universe)

    mention_counts: Counter[str] = Counter()
    positive_hits: Counter[str] = Counter()
    negative_hits: Counter[str] = Counter()
    research_reasons: dict[str, list[str]] = defaultdict(list)

    for item in research_items:
        blob = " ".join(
            str(item.get(key, ""))
            for key in ("title", "strategy", "results", "takeaway", "raw")
        )
        upper_blob = blob.upper()
        lower_blob = blob.lower()
        matched_symbols = _extract_symbols(upper_blob, universe_set)
        if not matched_symbols:
            continue
        pos = sum(1 for term in POSITIVE_TERMS if term in lower_blob)
        neg = sum(1 for term in NEGATIVE_TERMS if term in lower_blob)
        title = str(item.get("title", "Research mention")).strip()
        for symbol in matched_symbols:
            mention_counts[symbol] += 1
            positive_hits[symbol] += pos
            negative_hits[symbol] += neg
            if len(research_reasons[symbol]) < 3:
                research_reasons[symbol].append(title)

    active_symbols = _active_symbols_from_manager(manager_state)
    exposure_pct = manager_state.get("coin_exposure_pct", {}) if isinstance(manager_state.get("coin_exposure_pct", {}), dict) else {}
    current_regime = str(manager_state.get("regime", "sideways"))

    candidates: list[dict[str, Any]] = []
    for symbol in universe:
        indicators = _indicator_snapshot(symbol)
        mention_score = mention_counts[symbol] * 6.0 + positive_hits[symbol] * 1.4 - negative_hits[symbol] * 2.0
        rsi = _safe_float(indicators.get("rsi", 50.0), 50.0)
        macd_hist = _safe_float(indicators.get("macd_hist", 0.0), 0.0)
        vol_ratio = _safe_float(indicators.get("volume_ratio", 0.0), 0.0)
        price = _safe_float(indicators.get("price", 0.0), 0.0)
        ma20 = _safe_float(indicators.get("ma20", 0.0), 0.0)
        ma50 = _safe_float(indicators.get("ma50", 0.0), 0.0)

        mean_reversion_score = max(0.0, 48.0 - rsi) * 0.85
        momentum_score = max(0.0, rsi - 52.0) * 0.5
        macd_score = max(-6.0, min(6.0, macd_hist * 600.0))
        volume_score = max(-2.0, min(5.0, (vol_ratio - 1.0) * 4.0))
        trend_score = 4.0 if price >= ma20 >= max(ma50, 0.000001) else (-2.5 if price < ma20 else 0.0)
        active_bonus = 3.0 if symbol in active_symbols else 0.0
        exposure_penalty = max(0.0, _safe_float(exposure_pct.get(symbol, 0.0)) - 6.0) * 1.3
        regime_bonus = 0.0
        if current_regime == "volatile" and rsi <= 38:
            regime_bonus += 3.0
        if current_regime == "bull" and price >= ma20 and macd_hist > 0:
            regime_bonus += 2.5
        if current_regime == "bear" and rsi < 30:
            regime_bonus += 1.5

        bot_affinity = {
            bot_key: (6.0 if symbol in watchlist else 0.0)
            + (3.0 if symbol in active_symbols and symbol in watchlist else 0.0)
            for bot_key, watchlist in BOT_WATCHLISTS.items()
        }
        strongest_bot = max(bot_affinity.items(), key=lambda item: item[1])[0]
        strongest_affinity = bot_affinity[strongest_bot]

        total_score = mention_score + mean_reversion_score + momentum_score + macd_score + volume_score + trend_score + active_bonus + regime_bonus + strongest_affinity - exposure_penalty
        confidence = max(0.0, min(100.0, 35.0 + mention_counts[symbol] * 8.0 + vol_ratio * 10.0 + abs(macd_hist) * 2200.0))

        candidates.append(
            {
                "symbol": symbol,
                "score": round(total_score, 2),
                "confidence": round(confidence, 1),
                "preferred_bot": strongest_bot,
                "breakdown": {
                    "research_mentions": mention_counts[symbol],
                    "research_score": round(mention_score, 2),
                    "mean_reversion_score": round(mean_reversion_score, 2),
                    "momentum_score": round(momentum_score, 2),
                    "macd_score": round(macd_score, 2),
                    "volume_score": round(volume_score, 2),
                    "trend_score": round(trend_score, 2),
                    "regime_bonus": round(regime_bonus, 2),
                    "active_bonus": round(active_bonus, 2),
                    "exposure_penalty": round(exposure_penalty, 2),
                    "bot_affinity": {bot: round(score, 2) for bot, score in bot_affinity.items()},
                },
                "research_examples": research_reasons[symbol],
                "indicators": indicators,
                "portfolio_exposure_pct": round(_safe_float(exposure_pct.get(symbol, 0.0)), 2),
            }
        )

    candidates.sort(key=lambda item: (item["score"], item["confidence"]), reverse=True)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regime": current_regime,
        "source_counts": {
            "research_items": len(research_items),
            "tracked_symbols": len(universe),
            "active_symbols": len(active_symbols),
        },
        "top_candidates": candidates[:12],
    }
    _save_json(OUTPUT_FILE, summary)
    return summary


def main() -> None:
    payload = build_candidate_scores()
    top = payload.get("top_candidates", [])
    print("Candidate scorer complete")
    print(f"Saved: {OUTPUT_FILE}")
    print(f"Regime: {payload.get('regime')}")
    for idx, item in enumerate(top[:5], 1):
        print(
            f"{idx:>2}. {item['symbol']:<6} score={item['score']:>6.2f} conf={item['confidence']:>5.1f}% bot={item['preferred_bot']} mentions={item['breakdown']['research_mentions']}"
        )


if __name__ == "__main__":
    main()
