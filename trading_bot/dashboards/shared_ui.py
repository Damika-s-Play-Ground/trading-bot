#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""Shared UI helpers for the generated dashboards."""
from __future__ import annotations

from math import ceil
from typing import Iterable


def _clean_label(label: str) -> str:
    return str(label).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
    span = max(max_v - min_v, 1e-9)
    width = 760
    left_pad = 42
    right_pad = 18
    top_pad = 18
    bottom_pad = 34
    chart_w = width - left_pad - right_pad
    chart_h = height - top_pad - bottom_pad
    step = chart_w / max(len(values) - 1, 1)

    points = []
    point_nodes = []
    for idx, value in enumerate(values):
        x = left_pad + idx * step
        y = top_pad + (max_v - value) / span * chart_h
        points.append(f"{x:.1f},{y:.1f}")
        label = labels[idx] if idx < len(labels) else f"Point {idx + 1}"
        tooltip = f"{_clean_label(label)} | Value: {value:,.2f}"
        point_nodes.append(
            f"<g class='chart-point-group'><title>{tooltip}</title><circle class='chart-point' cx='{x:.1f}' cy='{y:.1f}' r='4.4' fill='{color}' stroke='#0f172a' stroke-width='2' /></g>"
        )

    last_x = left_pad + (len(values) - 1) * step
    base_y = top_pad + chart_h
    fill_path = ""
    if fill:
        fill_path = f"<polygon points='{points[0]} {' '.join(points[1:])} {last_x:.1f},{base_y:.1f} {left_pad:.1f},{base_y:.1f}' fill='{color}22' stroke='none' />"

    y_ticks = []
    for frac in [0, 0.25, 0.5, 0.75, 1.0]:
        value = max_v - span * frac
        y = top_pad + chart_h * frac
        y_ticks.append(
            f"<text x='8' y='{y + 4:.1f}' fill='#64748b' font-size='10'>{value:,.0f}</text>"
        )

    label_nodes = ""
    tick_step = max(1, ceil(len(labels) / 6))
    label_nodes = "".join(
        f"<text x='{left_pad + idx * step:.1f}' y='{height - 12}' text-anchor='middle' fill='#64748b' font-size='10'>{_clean_label(lbl)}</text>"
        for idx, lbl in enumerate(labels)
        if idx % tick_step == 0 or idx == len(labels) - 1
    )

    area = (
        f"<defs><linearGradient id='grad-{abs(hash(tuple(values))) % 10_000}' x1='0' x2='0' y1='0' y2='1'>"
        f"<stop offset='0%' stop-color='{color}' stop-opacity='0.25' />"
        f"<stop offset='100%' stop-color='{color}' stop-opacity='0.02' />"
        f"</linearGradient></defs>"
    )
    chart = f"""
    <div class="chart-card">
        <div class="chart-head">
            <div>
                <strong>{_clean_label(title)}</strong>
                <div class="mini-note">{_clean_label(subtitle)}</div>
            </div>
        </div>
        <svg viewBox="0 0 {width} {height}" class="chart-svg" preserveAspectRatio="none" role="img" aria-label="{_clean_label(title)}">
            {area}
            {fill_path}
            {''.join(y_ticks)}
            <polyline points="{' '.join(points)}" fill="none" stroke="{color}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" />
            {''.join(point_nodes)}
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
        tooltip = f"{label} | Value: {value:,.1f}{value_suffix}"
        rows.append(
            f"""
            <div class="bar-row" title="{tooltip}">
                <div class="bar-row-head">
                    <span>{label}</span>
                    <span class="bar-value">{value:,.1f}{value_suffix}</span>
                </div>
                <div class="bar-track"><div class="bar-fill" title="{tooltip}" style="width:{pct:.1f}%;background:{color};"></div></div>
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
    gradient_parts = []
    cursor = 0.0
    legend_rows = []
    for seg in segments:
        value = float(seg.get("value", 0) or 0)
        pct = value / total
        start = cursor * 360.0
        cursor += pct
        end = cursor * 360.0
        color = seg.get("color", "#3b82f6")
        label = _clean_label(str(seg.get("label", "")))
        gradient_parts.append(f"{color} {start:.2f}deg {end:.2f}deg")
        legend_rows.append(
            f"<div class='legend-row' title='{label} | Value: {value:,.1f} ({pct*100:.1f}%)'><span class='legend-dot' style='background:{color}'></span><span>{label}</span><span class='legend-val'>{value:,.1f}</span></div>"
        )
    gradient = ", ".join(gradient_parts)
    return f"""
    <div class="chart-card donut-card">
        <div class="chart-head">
            <div>
                <strong>{_clean_label(title)}</strong>
                <div class="mini-note">{_clean_label(subtitle)}</div>
            </div>
        </div>
        <div class="donut-wrap">
            <div class="donut" style="background:conic-gradient({gradient});">
                <div class="donut-inner">
                    <div class="donut-value">{_clean_label(center_value)}</div>
                    <div class="donut-label">{_clean_label(center_label)}</div>
                </div>
            </div>
            <div class="donut-legend">{''.join(legend_rows)}</div>
        </div>
    </div>
    """
