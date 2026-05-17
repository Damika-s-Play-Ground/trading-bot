#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""Shared UI helpers for the generated dashboards."""
from __future__ import annotations

from hashlib import sha1
from html import escape
from math import ceil, pi
from typing import Iterable


def _clean_label(label: str) -> str:
    return escape(str(label), quote=True)


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "||".join(str(part) for part in parts)
    digest = sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _fmt_axis_value(value: float, span: float) -> str:
    if span >= 1000:
        return f"{value:,.0f}"
    if span >= 100:
        return f"{value:,.1f}"
    return f"{value:,.2f}"


def _fmt_delta(value: float) -> str:
    return f"{value:+,.2f}"


def build_line_chart_svg(
    values: Iterable[float],
    *,
    labels: Iterable[str] | None = None,
    title: str = "",
    subtitle: str = "",
    color: str = "#3b82f6",
    fill: bool = True,
    height: int = 230,
) -> str:
    values = [float(v) for v in values if v is not None]
    if len(values) < 2:
        return f'<div class="chart-card"><div class="chart-head"><div><strong>{_clean_label(title)}</strong><div class="mini-note">{_clean_label(subtitle)}</div></div></div><div class="empty-box" style="padding:28px 18px;">Not enough data to draw a chart yet.</div></div>'

    labels = list(labels) if labels is not None else [str(i + 1) for i in range(len(values))]
    min_v = min(values)
    max_v = max(values)
    min_idx = values.index(min_v)
    max_idx = values.index(max_v)
    raw_span = max(max_v - min_v, 1e-9)
    pad = max(raw_span * 0.14, max(abs(max_v), abs(min_v), 1.0) * 0.0008)
    axis_min = min_v - pad
    axis_max = max_v + pad
    axis_span = max(axis_max - axis_min, 1e-9)

    width = 760
    left_pad = 54
    right_pad = 18
    top_pad = 18
    bottom_pad = 38
    chart_w = width - left_pad - right_pad
    chart_h = height - top_pad - bottom_pad
    step = chart_w / max(len(values) - 1, 1)

    coords = []
    point_nodes = []
    for idx, value in enumerate(values):
        x = left_pad + idx * step
        y = top_pad + (axis_max - value) / axis_span * chart_h
        coords.append((x, y, value))
        label = labels[idx] if idx < len(labels) else f"Point {idx + 1}"
        tooltip = f"{_clean_label(label)} · Equity {_fmt_axis_value(value, raw_span)}"
        latest_class = " chart-point-latest" if idx == len(values) - 1 else ""
        extreme_class = " chart-point-extreme" if idx in {min_idx, max_idx} else ""
        point_nodes.append(
            f"<g class='chart-point-group' tabindex='0' title='{tooltip}' data-tooltip='{tooltip}'>"
            f"<line class='chart-guide' x1='{x:.1f}' y1='{top_pad:.1f}' x2='{x:.1f}' y2='{top_pad + chart_h:.1f}' />"
            f"<circle class='chart-point{latest_class}{extreme_class}' cx='{x:.1f}' cy='{y:.1f}' r='4.8' fill='{color}' stroke='#0f172a' stroke-width='2' />"
            f"</g>"
        )

    points = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in coords)
    last_x, last_y, latest_value = coords[-1]
    base_y = top_pad + chart_h
    gradient_id = _stable_id(
        "grad",
        title,
        color,
        *(round(v, 4) for v in values),
    )
    fill_path = ""
    if fill:
        fill_points = f"{points} {last_x:.1f},{base_y:.1f} {left_pad:.1f},{base_y:.1f}"
        fill_path = f"<polygon class='chart-area' points='{fill_points}' fill='url(#{gradient_id})' stroke='none' />"

    y_ticks = []
    for frac in [0, 0.25, 0.5, 0.75, 1.0]:
        value = axis_max - axis_span * frac
        y = top_pad + chart_h * frac
        y_ticks.append(
            f"<line class='chart-gridline' x1='{left_pad:.1f}' y1='{y:.1f}' x2='{width - right_pad:.1f}' y2='{y:.1f}' />"
            f"<text class='chart-axis-label' x='10' y='{y + 4:.1f}'>{_fmt_axis_value(value, raw_span)}</text>"
        )

    tick_step = max(1, ceil(len(labels) / 6))
    label_nodes = "".join(
        f"<text class='chart-axis-label' x='{left_pad + idx * step:.1f}' y='{height - 12}' text-anchor='middle'>{_clean_label(lbl)}</text>"
        for idx, lbl in enumerate(labels)
        if idx % tick_step == 0 or idx == len(labels) - 1
    )

    delta = latest_value - values[0]
    stats = (
        f"<div class='chart-stats'>"
        f"<span class='chart-stat'>Latest {_fmt_axis_value(latest_value, raw_span)}</span>"
        f"<span class='chart-stat'>High {_fmt_axis_value(max_v, raw_span)}</span>"
        f"<span class='chart-stat'>Low {_fmt_axis_value(min_v, raw_span)}</span>"
        f"<span class='chart-stat'>Δ {_fmt_delta(delta)}</span>"
        f"</div>"
    )

    latest_tag_w = 74
    latest_tag_x = min(width - right_pad - latest_tag_w, last_x + 10)
    latest_tag_y = max(top_pad + 6, min(base_y - 18, last_y - 18))

    chart = f"""
    <div class="chart-card">
        <div class="chart-head">
            <div>
                <strong>{_clean_label(title)}</strong>
                <div class="mini-note">{_clean_label(subtitle)}</div>
            </div>
            {stats}
        </div>
        <svg viewBox="0 0 {width} {height}" class="chart-svg" preserveAspectRatio="none" role="img" aria-label="{_clean_label(title)}">
            <defs>
                <linearGradient id="{gradient_id}" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stop-color="{color}" stop-opacity="0.42" />
                    <stop offset="100%" stop-color="{color}" stop-opacity="0.02" />
                </linearGradient>
            </defs>
            {''.join(y_ticks)}
            {fill_path}
            <polyline class="chart-line" points="{points}" fill="none" stroke="{color}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round" />
            {''.join(point_nodes)}
            <g class="chart-latest-tag">
                <rect x="{latest_tag_x:.1f}" y="{latest_tag_y:.1f}" width="{latest_tag_w}" height="22" rx="11" fill="#0f172a" stroke="{color}" stroke-opacity="0.55" />
                <text x="{latest_tag_x + latest_tag_w/2:.1f}" y="{latest_tag_y + 14:.1f}" text-anchor="middle" fill="#e2e8f0" font-size="10.5" font-weight="700">{_fmt_axis_value(latest_value, raw_span)}</text>
            </g>
            {label_nodes}
        </svg>
    </div>
    """
    return chart


def build_bar_chart(
    items: Iterable[dict],
    *,
    title: str,
    subtitle: str = "",
    value_suffix: str = "",
) -> str:
    items = list(items)
    if not items:
        return f'<div class="chart-card"><div class="chart-head"><div><strong>{_clean_label(title)}</strong><div class="mini-note">{_clean_label(subtitle)}</div></div></div><div class="empty-box" style="padding:28px 18px;">No data available.</div></div>'

    max_value = max(float(item.get("value", 0) or 0) for item in items) or 1
    rows = []
    for item in items:
        value = float(item.get("value", 0) or 0)
        pct = (value / max_value) * 100 if max_value else 0
        color = item.get("color", "#3b82f6")
        label = _clean_label(str(item.get("label", "")))
        meta = _clean_label(str(item.get("meta", "")))
        tooltip = f"{label} · {value:,.1f}{value_suffix} · {meta}" if meta else f"{label} · {value:,.1f}{value_suffix}"
        rows.append(
            f"""
            <div class="bar-row" tabindex="0" title="{tooltip}" data-tooltip="{tooltip}">
                <div class="bar-row-head">
                    <span>{label}</span>
                    <span class="bar-value">{value:,.1f}{value_suffix}</span>
                </div>
                <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;background:{color};"></div></div>
                <div class="bar-meta">{meta}</div>
            </div>
            """
        )
    return f"""
    <div class="chart-card">
        <div class="chart-head">
            <div>
                <strong>{_clean_label(title)}</strong>
                <div class="mini-note">{_clean_label(subtitle)}</div>
            </div>
        </div>
        <div class="bar-chart">{''.join(rows)}</div>
    </div>
    """


def build_donut_chart(
    segments: Iterable[dict],
    *,
    title: str,
    center_value: str,
    center_label: str = "",
    subtitle: str = "",
) -> str:
    segments = [seg for seg in segments if float(seg.get("value", 0) or 0) >= 0]
    total = sum(float(seg.get("value", 0) or 0) for seg in segments)
    if total <= 0:
        total = 1

    chart_id = _stable_id(
        "donut",
        title,
        *(str(seg.get("label", "")) for seg in segments),
        *(round(float(seg.get("value", 0) or 0), 4) for seg in segments),
    )
    circumference = 2 * pi * 56
    cursor = 0.0
    segment_nodes = []
    legend_rows = []
    for idx, seg in enumerate(segments):
        value = float(seg.get("value", 0) or 0)
        pct = value / total
        dash = max(circumference * pct, 0.0001)
        gap = max(circumference - dash, 0.0)
        color = seg.get("color", "#3b82f6")
        label = _clean_label(str(seg.get("label", "")))
        tooltip = f"{label} · {value:,.1f} · {pct*100:.1f}% of total"
        segment_nodes.append(
            f"<g class='donut-segment-group' tabindex='0' title='{tooltip}' data-chart='{chart_id}' data-segment='{idx}' data-tooltip='{tooltip}'>"
            f"<circle class='donut-segment' cx='80' cy='80' r='56' fill='none' stroke='{color}' stroke-width='18' stroke-linecap='round' stroke-dasharray='{dash:.3f} {gap:.3f}' stroke-dashoffset='{-cursor:.3f}' transform='rotate(-90 80 80)' />"
            f"</g>"
        )
        legend_rows.append(
            f"<div class='legend-row' tabindex='0' title='{tooltip}' data-chart='{chart_id}' data-segment='{idx}' data-tooltip='{tooltip}'>"
            f"<span class='legend-dot' style='background:{color}'></span>"
            f"<span>{label}</span>"
            f"<span class='legend-meta'><span class='legend-val'>{value:,.1f}</span><span class='legend-share'>{pct*100:.1f}%</span></span>"
            f"</div>"
        )
        cursor += dash

    return f"""
    <div class="chart-card donut-card" data-chart="{chart_id}">
        <div class="chart-head">
            <div>
                <strong>{_clean_label(title)}</strong>
                <div class="mini-note">{_clean_label(subtitle)}</div>
            </div>
        </div>
        <div class="donut-wrap">
            <div class="donut">
                <svg viewBox="0 0 160 160" class="donut-svg" role="img" aria-label="{_clean_label(title)}">
                    <circle cx="80" cy="80" r="56" fill="none" stroke="#243244" stroke-width="18" />
                    {''.join(segment_nodes)}
                </svg>
                <div class="donut-inner">
                    <div class="donut-value">{_clean_label(center_value)}</div>
                    <div class="donut-label">{_clean_label(center_label)}</div>
                </div>
            </div>
            <div class="donut-legend">{''.join(legend_rows)}</div>
        </div>
    </div>
    """
