const { createApp } = Vue;
const DASHBOARD_CACHE_KEY = 'dashboard_payload_v5';

createApp({
  data() {
    return {
      loading: true,
      error: '',
      payload: null,
      activeBotKey: null,
      refreshBusy: false,
      refreshStatus: 'Live polling every 30s',
      allocationHover: null,
      activityHover: null,
      equityHover: null,
      equityRangeStart: '',
      equityRangeEnd: '',
      equityRangePreset: 'today',
      pollHandle: null,
    };
  },
  computed: {
    summary() { return this.payload?.summary || {}; },
    analytics() { return this.payload?.analytics || {}; },
    bots() { return this.payload?.bots || []; },
    activeBot() {
      return this.bots.find(bot => bot.key === this.activeBotKey) || null;
    },
    recentTrades() { return this.payload?.recent_trades || []; },
    botAttributionRows() { return this.analytics?.bot_contribution || []; },
    tradeAttributionRows() { return this.analytics?.trade_attribution || []; },
    regimeReview() { return this.analytics?.regime_review || {}; },
    cronJobs() { return this.payload?.cron || []; },
    todoStats() { return this.payload?.todo?.stats || {}; },
    allocationSegments() { return this.payload?.charts?.allocation || []; },
    activityRows() { return this.payload?.charts?.activity || []; },
    allEquityPoints() { return this.payload?.charts?.equity || []; },
    totalAllocation() {
      return this.allocationSegments.reduce((sum, item) => sum + Number(item.value || 0), 0);
    },
    activityMax() {
      return Math.max(1, ...this.activityRows.map(item => Number(item.value || 0)));
    },
    botTableRows() {
      return [...this.bots].sort((a, b) => Number(b.value || 0) - Number(a.value || 0));
    },
    filteredEquityPoints() {
      const startTs = this.dateStartTimestamp(this.equityRangeStart);
      const endTs = this.dateEndTimestamp(this.equityRangeEnd);
      return this.allEquityPoints.filter(point => {
        const ts = new Date(point.timestamp || point.label || '').getTime();
        if (!Number.isFinite(ts)) return true;
        if (startTs != null && ts < startTs) return false;
        if (endTs != null && ts > endTs) return false;
        return true;
      });
    },
    visibleEquityPoints() {
      return this.filteredEquityPoints;
    },
    equityChart() {
      const points = this.visibleEquityPoints;
      const width = 920;
      const height = 320;
      const left = 64;
      const right = 22;
      const top = 22;
      const bottom = 42;
      if (!points.length) {
        return {
          width, height, left, right, top, bottom,
          points: [], polyline: '', area: '', ticks: [], labels: [],
          min: 0, max: 0, delta: 0, percentDelta: 0,
          startValue: 0, endValue: 0, highValue: 0, lowValue: 0,
          startLabel: '', endLabel: '',
        };
      }
      const values = points.map(item => Number(item.value || 0));
      const min = Math.min(...values);
      const max = Math.max(...values);
      const span = Math.max(max - min, Math.max(Math.abs(max), 1) * 0.02, 1);
      const axisMin = min - span * 0.16;
      const axisMax = max + span * 0.16;
      const usableW = width - left - right;
      const usableH = height - top - bottom;
      const step = points.length > 1 ? usableW / (points.length - 1) : 0;
      const highValue = max;
      const lowValue = min;
      const mapped = points.map((item, idx) => {
        const value = Number(item.value || 0);
        const x = left + idx * step;
        const y = top + ((axisMax - value) / Math.max(axisMax - axisMin, 1e-6)) * usableH;
        const ts = new Date(item.timestamp || item.label || '').getTime();
        return { ...item, x, y, value, idx, ts };
      });
      const polyline = mapped.map(item => `${item.x.toFixed(2)},${item.y.toFixed(2)}`).join(' ');
      const area = mapped.length
        ? `${polyline} ${mapped[mapped.length - 1].x.toFixed(2)},${(top + usableH).toFixed(2)} ${left},${(top + usableH).toFixed(2)}`
        : '';
      const ticks = [0, 0.25, 0.5, 0.75, 1].map(frac => ({
        y: top + usableH * frac,
        value: axisMax - (axisMax - axisMin) * frac,
      }));
      const labelStep = Math.max(1, Math.floor(points.length / 6));
      const labels = mapped.filter(item => item.idx % labelStep === 0 || item.idx === mapped.length - 1);
      const startValue = values[0];
      const endValue = values[values.length - 1];
      const delta = endValue - startValue;
      const percentDelta = startValue ? (delta / startValue) * 100 : 0;
      return {
        width, height, left, right, top, bottom,
        points: mapped,
        polyline,
        area,
        ticks,
        labels,
        min,
        max,
        delta,
        percentDelta,
        startValue,
        endValue,
        highValue,
        lowValue,
        startLabel: mapped[0]?.display_label || mapped[0]?.label || '',
        endLabel: mapped[mapped.length - 1]?.display_label || mapped[mapped.length - 1]?.label || '',
      };
    },
    equityStats() {
      const chart = this.equityChart;
      return [
        { label: 'Visible points', value: String(chart.points.length || 0) },
        { label: 'Start', value: chart.points.length ? this.formatMoney(chart.startValue) : '—' },
        { label: 'End', value: chart.points.length ? this.formatMoney(chart.endValue) : '—' },
        { label: 'High', value: chart.points.length ? this.formatMoney(chart.highValue) : '—' },
        { label: 'Low', value: chart.points.length ? this.formatMoney(chart.lowValue) : '—' },
        { label: 'Change', value: chart.points.length ? `${this.formatMoney(chart.delta)} · ${this.formatPct(chart.percentDelta)}` : '—' },
      ];
    },
    activeEquityPoint() {
      return this.equityHover || this.equityChart.points[this.equityChart.points.length - 1] || null;
    },
  },
  methods: {
    hydratePayload(nextPayload) {
      if (!nextPayload) return false;
      this.payload = nextPayload;
      this.initializeEquityControls();
      this.loading = false;
      return true;
    },
    isPayloadFreshEnough(payload) {
      return Boolean(payload?.analytics?.bot_contribution && payload?.analytics?.trade_attribution && payload?.charts?.equity);
    },
    restoreCachedPayload() {
      try {
        const cached = JSON.parse(window.localStorage.getItem(DASHBOARD_CACHE_KEY) || 'null');
        if (!cached || !this.isPayloadFreshEnough(cached.payload)) return false;
        return this.hydratePayload(cached.payload);
      } catch (error) {
        return false;
      }
    },
    restoreBootstrapPayload() {
      try {
        const bootstrapped = window.__DASHBOARD_BOOTSTRAP__;
        if (!this.isPayloadFreshEnough(bootstrapped)) return false;
        return this.hydratePayload(bootstrapped);
      } catch (error) {
        return false;
      }
    },
    initializeEquityControls() {
      if (!this.allEquityPoints.length) {
        this.equityRangeStart = '';
        this.equityRangeEnd = '';
        this.equityRangePreset = 'today';
        return;
      }
      const today = this.todayDateValue();
      if (!this.equityRangeStart) this.equityRangeStart = today;
      if (!this.equityRangeEnd) this.equityRangeEnd = today;
      if (!['today', 'all', 'custom'].includes(this.equityRangePreset)) this.equityRangePreset = 'today';
    },
    async loadDashboard(options = {}) {
      const showLoading = options.showLoading ?? !this.payload;
      if (showLoading) this.loading = true;
      this.error = '';
      try {
        const response = await fetch(`/api/dashboard-data?ts=${Date.now()}`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`dashboard data request failed (${response.status})`);
        this.hydratePayload(await response.json());
        window.localStorage.setItem(DASHBOARD_CACHE_KEY, JSON.stringify({ ts: Date.now(), payload: this.payload }));
      } catch (error) {
        console.error(error);
        this.error = error.message || 'Failed to load dashboard data';
      } finally {
        this.loading = false;
      }
    },
    async refreshPages() {
      this.refreshBusy = true;
      this.refreshStatus = 'Refreshing generated pages…';
      try {
        const response = await fetch('/api/refresh', { method: 'POST' });
        const payload = await response.json();
        this.refreshStatus = payload?.ok ? 'Generated pages refreshed' : 'Refresh failed';
        await this.loadDashboard();
      } catch (error) {
        console.error(error);
        this.refreshStatus = 'Refresh request failed';
      } finally {
        this.refreshBusy = false;
        setTimeout(() => {
          if (!this.refreshBusy) this.refreshStatus = 'Live polling every 30s';
        }, 3500);
      }
    },
    formatMoney(value, digits = 2) {
      const n = Number(value || 0);
      return `$${n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
    },
    formatPct(value, digits = 2) {
      const n = Number(value || 0);
      const sign = n > 0 ? '+' : '';
      return `${sign}${n.toFixed(digits)}%`;
    },
    shortPct(value, digits = 1) {
      return `${Number(value || 0).toFixed(digits)}%`;
    },
    formatQty(value) {
      const n = Number(value || 0);
      return n.toLocaleString(undefined, { maximumFractionDigits: 6 });
    },
    relativeTime(value) {
      if (!value) return '—';
      const ts = new Date(value).getTime();
      if (!Number.isFinite(ts)) return '—';
      const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
      if (diffSec < 60) return `${diffSec}s ago`;
      if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
      if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ${Math.floor((diffSec % 3600) / 60)}m ago`;
      return `${Math.floor(diffSec / 86400)}d ${Math.floor((diffSec % 86400) / 3600)}h ago`;
    },
    formatTime(value) {
      if (!value) return '—';
      const dt = new Date(value);
      if (Number.isNaN(dt.getTime())) return '—';
      return dt.toLocaleString();
    },
    humanizeToken(value) {
      return String(value || '—').replace(/_/g, ' ').replace(/\b\w/g, match => match.toUpperCase());
    },
    toDateTimeLocalValue(value) {
      if (!value) return '';
      const dt = new Date(value);
      if (Number.isNaN(dt.getTime())) return '';
      const pad = num => String(num).padStart(2, '0');
      const year = dt.getFullYear();
      const month = pad(dt.getMonth() + 1);
      const day = pad(dt.getDate());
      const hour = pad(dt.getHours());
      const minute = pad(dt.getMinutes());
      return `${year}-${month}-${day}T${hour}:${minute}`;
    },
    toDateValue(value) {
      if (!value) return '';
      const dt = new Date(value);
      if (Number.isNaN(dt.getTime())) return '';
      const pad = num => String(num).padStart(2, '0');
      return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
    },
    todayDateValue() {
      return this.toDateValue(new Date().toISOString());
    },
    dateStartTimestamp(value) {
      if (!value) return null;
      const ts = new Date(`${value}T00:00:00`).getTime();
      return Number.isFinite(ts) ? ts : null;
    },
    dateEndTimestamp(value) {
      if (!value) return null;
      const ts = new Date(`${value}T23:59:59.999`).getTime();
      return Number.isFinite(ts) ? ts : null;
    },
    openBotModal(key) {
      this.activeBotKey = key;
      document.body.style.overflow = 'hidden';
    },
    closeBotModal() {
      this.activeBotKey = null;
      document.body.style.overflow = '';
    },
    onKeydown(event) {
      if (event.key === 'Escape' && this.activeBotKey) this.closeBotModal();
    },
    donutDash(segment) {
      const circumference = 2 * Math.PI * 56;
      const dash = Math.max(circumference * ((Number(segment.value || 0)) / Math.max(this.totalAllocation, 1)), 0.001);
      return `${dash} ${Math.max(circumference - dash, 0)}`;
    },
    donutOffset(index) {
      const circumference = 2 * Math.PI * 56;
      let cursor = 0;
      for (let i = 0; i < index; i += 1) {
        cursor += circumference * ((Number(this.allocationSegments[i]?.value || 0)) / Math.max(this.totalAllocation, 1));
      }
      return -cursor;
    },
    setEquityPreset(preset) {
      this.equityRangePreset = preset;
      const points = this.allEquityPoints;
      if (!points.length) return;
      if (preset === 'all') {
        this.equityRangeStart = this.toDateValue(points[0].timestamp || points[0].label || '');
        this.equityRangeEnd = this.toDateValue(points[points.length - 1].timestamp || points[points.length - 1].label || '');
        return;
      }
      const today = this.todayDateValue();
      this.equityRangeStart = today;
      this.equityRangeEnd = today;
    },
    onEquityRangeChange() {
      this.equityRangePreset = 'custom';
      const startTs = this.dateStartTimestamp(this.equityRangeStart);
      const endTs = this.dateEndTimestamp(this.equityRangeEnd);
      if (startTs != null && endTs != null && startTs > endTs) {
        this.equityRangeEnd = this.equityRangeStart;
      }
    },
    resetEquityView() {
      this.setEquityPreset('today');
    },
    equityHoverPoint(point) {
      this.equityHover = point;
    },
    clearEquityHover() {
      this.equityHover = null;
    },
    activityWidth(item) {
      return `${(Number(item.value || 0) / this.activityMax) * 100}%`;
    },
    tradeActionClass(action) {
      return /BUY|LONG/.test(action || '') ? 'buy' : 'sell';
    },
    indicatorTone(value, direction = 'high') {
      const n = Number(value || 0);
      if (direction === 'rsi') {
        if (n <= 30) return 'green';
        if (n >= 70) return 'red';
        return 'yellow';
      }
      if (direction === 'macd') return n >= 0 ? 'green' : 'red';
      if (direction === 'vol') return n >= 1 ? 'green' : 'yellow';
      return n >= 0 ? 'green' : 'red';
    },
    contributionForPosition(bot, position) {
      const total = Number(this.summary.portfolio_total || 0);
      return total > 0 ? (Number(position.value || 0) / total) * 100 : 0;
    },
    positionPnlClass(value) {
      return Number(value || 0) >= 0 ? 'pnl-pos' : 'pnl-neg';
    },
    cronSeverityClass(level) {
      return `sev-${level || 'warning'}`;
    },
    chartInsight() {
      const active = this.activeEquityPoint;
      const points = this.equityChart.points;
      if (!active || !points.length) return 'Waiting for more journal history';
      const regime = active.regime ? ` · ${String(active.regime).toUpperCase()}` : '';
      const unrealized = active.unrealized_pnl != null ? ` · Unrealized ${this.formatMoney(active.unrealized_pnl)}` : '';
      return `${active.display_label || active.label || 'Latest'} · ${this.formatMoney(active.value)} · Δ ${this.formatMoney(this.equityChart.delta)} (${this.formatPct(this.equityChart.percentDelta)})${regime}${unrealized}`;
    },
    tradeSnapshotChips(trade) {
      if (!trade?.indicators) return [];
      return [
        { label: 'RSI', value: Number(trade.indicators.rsi).toFixed(1), tone: this.indicatorTone(trade.indicators.rsi, 'rsi') },
        { label: 'MACD', value: Number(trade.indicators.macd_hist).toFixed(4), tone: this.indicatorTone(trade.indicators.macd_hist, 'macd') },
        { label: 'MA20', value: this.formatMoney(trade.indicators.ma20, Number(trade.indicators.ma20) < 1 ? 5 : 2), tone: '' },
        { label: 'Vol', value: `${Number(trade.indicators.volume_ratio).toFixed(2)}x`, tone: this.indicatorTone(trade.indicators.volume_ratio, 'vol') },
      ];
    },
  },
  mounted() {
    this.restoreBootstrapPayload() || this.restoreCachedPayload();
    this.loadDashboard({ showLoading: !this.payload });
    this.pollHandle = window.setInterval(() => this.loadDashboard({ showLoading: false }), 30000);
    window.addEventListener('keydown', this.onKeydown);
  },
  beforeUnmount() {
    if (this.pollHandle) window.clearInterval(this.pollHandle);
    window.removeEventListener('keydown', this.onKeydown);
    document.body.style.overflow = '';
  },
  template: `
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">📊 Multi-Bot Trading Dashboard</h1>
        <p class="page-subtitle">Vue-powered Flask dashboard with live portfolio analytics, denser tables, richer bot drill-downs, and a simpler date-range equity explorer.</p>
      </div>
      <div class="header-actions">
        <button class="btn" @click="refreshPages" :disabled="refreshBusy">{{ refreshBusy ? 'Refreshing…' : 'Refresh generated pages' }}</button>
        <span class="status-note">{{ refreshStatus }}</span>
      </div>
    </div>

    <div class="nav">
      <a class="active" href="/dashboard">📊 Spot</a>
      <a href="/futures">🔵 Futures</a>
      <a href="/research">🔬 Research</a>
      <a href="/todo">🗒 Todo</a>
      <a href="/cron">⏱ Cron</a>
      <a href="/glossary">📖 Glossary</a>
    </div>

    <div v-if="loading" class="section-card">Loading dashboard…</div>
    <div v-else-if="error" class="section-card">{{ error }}</div>
    <template v-else>
      <div class="top-grid">
        <div class="stat-card">
          <div class="stat-label">Live portfolio</div>
          <div class="stat-value">{{ formatMoney(summary.portfolio_total) }}</div>
          <div class="stat-sub">Peak {{ formatMoney(summary.peak_total_value) }} · drawdown {{ shortPct(summary.portfolio_drawdown_pct) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Market regime</div>
          <div class="stat-value" style="font-size:24px">{{ payload.regime_label }}</div>
          <div class="stat-sub">{{ summary.positions_total }} open positions · {{ summary.trades_total }} logged trades</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Risk snapshot</div>
          <div class="stat-value" :class="summary.unrealized_pnl >= 0 ? 'green' : 'red'">{{ formatMoney(summary.unrealized_pnl) }}</div>
          <div class="stat-sub">Realized {{ formatMoney(summary.realized_pnl_recent) }} · combined loss {{ shortPct(summary.combined_loss_pct) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Roadmap sync</div>
          <div class="stat-value">{{ todoStats.open || 0 }}</div>
          <div class="stat-sub">open items · {{ todoStats.done || 0 }} done synced into dashboard store</div>
        </div>
      </div>

      <div class="analytics-grid">
        <div class="chart-card">
          <div class="chart-head">
            <div>
              <div class="chart-title">Portfolio allocation</div>
              <div class="chart-subtitle">Hover a slice or legend row to inspect the capital split</div>
            </div>
            <div class="chart-tooltip" v-if="allocationSegments.length">
              <span>{{ (allocationHover ?? allocationSegments[0]).label }}</span>
              <span>{{ formatMoney((allocationHover ?? allocationSegments[0]).value) }}</span>
              <span>{{ shortPct((allocationHover ?? allocationSegments[0]).share) }}</span>
            </div>
          </div>
          <div class="donut-layout">
            <div class="donut-wrap">
              <svg viewBox="0 0 160 160" style="width:180px;height:180px;overflow:visible;">
                <circle cx="80" cy="80" r="56" fill="none" stroke="#243244" stroke-width="18"></circle>
                <g v-for="(segment, idx) in allocationSegments" :key="segment.label" @mouseenter="allocationHover = segment" @mouseleave="allocationHover = null">
                  <circle
                    cx="80" cy="80" r="56" fill="none"
                    :stroke="segment.color"
                    :stroke-width="allocationHover && allocationHover.label === segment.label ? 22 : 18"
                    stroke-linecap="round"
                    :stroke-dasharray="donutDash(segment)"
                    :stroke-dashoffset="donutOffset(idx)"
                    transform="rotate(-90 80 80)"
                    :style="{ transition: 'all .18s ease', filter: allocationHover && allocationHover.label === segment.label ? 'drop-shadow(0 0 10px rgba(255,255,255,.18))' : 'none' }"
                  />
                </g>
              </svg>
              <div class="donut-center">
                <div class="donut-value">{{ formatMoney(summary.portfolio_total) }}</div>
                <div class="donut-label">live value</div>
              </div>
            </div>
            <div class="donut-legend">
              <div class="legend-row" v-for="segment in allocationSegments" :key="segment.label"
                :class="{ active: allocationHover && allocationHover.label === segment.label }"
                @mouseenter="allocationHover = segment" @mouseleave="allocationHover = null">
                <span class="legend-dot" :style="{ background: segment.color }"></span>
                <span>{{ segment.label }}</span>
                <span class="legend-meta">{{ formatMoney(segment.value) }} · {{ shortPct(segment.share) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="chart-card chart-card-wide">
          <div class="chart-head chart-head-stack">
            <div>
              <div class="chart-title">Equity curve explorer</div>
              <div class="chart-subtitle">Single date-range picker with today/all-history shortcuts and richer hover context from each performance snapshot</div>
            </div>
            <div class="chart-tooltip">{{ chartInsight() }}</div>
          </div>

          <div class="equity-toolbar">
            <div class="toolbar-group toolbar-group-range-single">
              <label class="input-stack input-stack-wide">
                <span>Date range</span>
                <div class="date-range-picker">
                  <input type="date" class="range-input" v-model="equityRangeStart" @change="onEquityRangeChange" />
                  <span class="range-separator">→</span>
                  <input type="date" class="range-input" v-model="equityRangeEnd" @change="onEquityRangeChange" />
                </div>
              </label>
              <button class="mini-btn" :class="{ active: equityRangePreset === 'today' }" @click="setEquityPreset('today')">Today</button>
              <button class="mini-btn" :class="{ active: equityRangePreset === 'all' }" @click="setEquityPreset('all')">All history</button>
              <button class="mini-btn" @click="resetEquityView">Reset</button>
            </div>
          </div>

          <div class="equity-stats-grid">
            <div class="mini-stat" v-for="stat in equityStats" :key="stat.label">
              <div class="mini-stat-label">{{ stat.label }}</div>
              <div class="mini-stat-value">{{ stat.value }}</div>
            </div>
          </div>

          <div v-if="!equityChart.points.length" class="empty-state">Not enough performance-journal data yet for the selected range.</div>
          <div v-else class="equity-chart-shell">
            <svg class="chart-svg chart-svg-tall" :viewBox="'0 0 ' + equityChart.width + ' ' + equityChart.height" preserveAspectRatio="none">
              <g v-for="tick in equityChart.ticks" :key="tick.y">
                <line class="chart-gridline" :x1="equityChart.left" :x2="equityChart.width - equityChart.right" :y1="tick.y" :y2="tick.y"></line>
                <text class="chart-axis" x="10" :y="tick.y + 4">{{ formatMoney(tick.value) }}</text>
              </g>
              <defs>
                <linearGradient id="equity-fill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stop-color="#60a5fa" stop-opacity="0.40"></stop>
                  <stop offset="100%" stop-color="#60a5fa" stop-opacity="0.03"></stop>
                </linearGradient>
              </defs>
              <polygon :points="equityChart.area" fill="url(#equity-fill)"></polygon>
              <polyline :points="equityChart.polyline" fill="none" stroke="#60a5fa" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"></polyline>
              <g v-for="point in equityChart.points" :key="point.idx" @mouseenter="equityHoverPoint(point)" @mouseleave="clearEquityHover">
                <line :x1="point.x" :x2="point.x" :y1="equityChart.top" :y2="equityChart.height - equityChart.bottom" stroke="#94a3b8" stroke-dasharray="4 5" :opacity="activeEquityPoint && activeEquityPoint.idx === point.idx ? 1 : 0"></line>
                <circle :cx="point.x" :cy="point.y" :r="activeEquityPoint && activeEquityPoint.idx === point.idx ? 6.6 : 4.5" fill="#60a5fa" stroke="#0f172a" stroke-width="2.4"></circle>
              </g>
              <g v-if="activeEquityPoint">
                <rect :x="Math.max(equityChart.left, Math.min(activeEquityPoint.x - 85, equityChart.width - 180))" :y="Math.max(10, activeEquityPoint.y - 62)" width="170" height="50" rx="12" fill="rgba(15,23,42,.96)" stroke="rgba(96,165,250,.48)"></rect>
                <text :x="Math.max(equityChart.left + 10, Math.min(activeEquityPoint.x - 75, equityChart.width - 170))" :y="Math.max(28, activeEquityPoint.y - 38)" fill="#cbd5e1" font-size="11" font-weight="700">{{ activeEquityPoint.display_label || activeEquityPoint.label }}</text>
                <text :x="Math.max(equityChart.left + 10, Math.min(activeEquityPoint.x - 75, equityChart.width - 170))" :y="Math.max(46, activeEquityPoint.y - 20)" fill="#eff6ff" font-size="12.5" font-weight="800">{{ formatMoney(activeEquityPoint.value) }}</text>
                <text :x="Math.max(equityChart.left + 10, Math.min(activeEquityPoint.x - 75, equityChart.width - 170))" :y="Math.max(62, activeEquityPoint.y - 4)" fill="#93c5fd" font-size="10.5">{{ activeEquityPoint.regime ? String(activeEquityPoint.regime).toUpperCase() : 'Portfolio snapshot' }}</text>
              </g>
              <text class="chart-axis" v-for="label in equityChart.labels" :key="label.idx" :x="label.x" :y="equityChart.height - 12" text-anchor="middle">{{ label.display_label || label.label }}</text>
            </svg>
          </div>
        </div>

        <div class="chart-card">
          <div class="chart-head">
            <div>
              <div class="chart-title">Bot activity</div>
              <div class="chart-subtitle">Hover each bar to compare trade volume and position footprint</div>
            </div>
            <div class="chart-tooltip" v-if="activityRows.length">
              <span>{{ (activityHover ?? activityRows[0]).label }}</span>
              <span>{{ (activityHover ?? activityRows[0]).value }} trades</span>
            </div>
          </div>
          <div class="bar-list">
            <div class="bar-row" v-for="row in activityRows" :key="row.label"
              :class="{ active: activityHover && activityHover.label === row.label }"
              @mouseenter="activityHover = row" @mouseleave="activityHover = null">
              <div class="bar-top">
                <span>{{ row.label }}</span>
                <strong>{{ row.value }}</strong>
              </div>
              <div class="bar-track"><div class="bar-fill" :style="{ width: activityWidth(row), background: row.color }"></div></div>
              <div class="bar-meta">{{ row.meta }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="section-card">
        <div class="section-head">
          <div>
            <h2>🧭 Attribution review</h2>
            <div class="section-note">Bot, trade, and regime attribution now render as visible review cards first so the section stays readable without horizontal scrolling.</div>
          </div>
          <div class="todo-strip">
            <span class="todo-pill">{{ botAttributionRows.length }} bot rows</span>
            <span class="todo-pill">{{ tradeAttributionRows.length }} trade rows</span>
            <span class="todo-pill">{{ regimeReview.samples || 0 }} regime samples</span>
          </div>
        </div>
        <div class="attribution-layout">
          <div class="attribution-column">
            <div class="mini-panel">
              <div class="mini-title">Bot contribution</div>
              <div v-if="botAttributionRows.length" class="attribution-card-list">
                <div class="attribution-card" v-for="row in botAttributionRows" :key="row.key">
                  <div class="attribution-row-top">
                    <div>
                      <div class="attribution-row-name">{{ row.name }}</div>
                      <div class="attribution-row-sub">{{ shortPct(row.portfolio_pct) }} of portfolio · {{ formatMoney(row.value) }}</div>
                    </div>
                    <span class="table-pill outline">{{ humanizeToken(row.optimizer_bias) }} · x{{ Number(row.combined_multiplier || 1).toFixed(2) }}</span>
                  </div>
                  <div class="attribution-chip-row">
                    <span class="attribution-chip">Unrealized <strong :class="row.unrealized_pnl >= 0 ? 'green' : 'red'">{{ formatMoney(row.unrealized_pnl) }}</strong></span>
                    <span class="attribution-chip">Realized <strong :class="row.realized_recent >= 0 ? 'green' : 'red'">{{ formatMoney(row.realized_recent) }}</strong></span>
                    <span class="attribution-chip">Drawdown {{ shortPct(row.drawdown_pct || 0, 2) }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="empty-state">No bot attribution rows available yet.</div>
            </div>

            <div class="mini-panel">
              <div class="mini-title">Recent trade attribution</div>
              <div v-if="tradeAttributionRows.length" class="attribution-card-list">
                <div class="attribution-card" v-for="row in tradeAttributionRows" :key="row.bot">
                  <div class="attribution-row-top">
                    <div>
                      <div class="attribution-row-name">{{ row.bot }}</div>
                      <div class="attribution-row-sub">{{ row.count }} recent trades · {{ formatMoney(row.notional) }} notional</div>
                    </div>
                    <div :class="row.pnl >= 0 ? 'green' : 'red'" style="font-weight:800;">{{ formatMoney(row.pnl) }}</div>
                  </div>
                  <div class="attribution-chip-row">
                    <span class="attribution-chip">Buys {{ row.buy_count }}</span>
                    <span class="attribution-chip">Sells {{ row.sell_count }}</span>
                    <span class="attribution-chip">Net PnL <strong :class="row.pnl >= 0 ? 'green' : 'red'">{{ formatMoney(row.pnl) }}</strong></span>
                  </div>
                </div>
              </div>
              <div v-else class="empty-state">No recent attributed trades in the current journal window.</div>
            </div>
          </div>

          <div class="mini-panel">
            <div class="mini-title">Regime changes</div>
            <div class="metric-grid">
              <div class="metric"><div class="k">Current</div><div class="v">{{ humanizeToken(regimeReview.current) }}</div></div>
              <div class="metric"><div class="k">Samples</div><div class="v">{{ regimeReview.samples || 0 }}</div></div>
              <div class="metric"><div class="k">Promotion</div><div class="v">{{ humanizeToken(regimeReview.latest_status) }}</div></div>
              <div class="metric"><div class="k">Failed gates</div><div class="v">{{ regimeReview.failed_gates ?? 0 }}</div></div>
            </div>
            <div class="todo-strip" v-if="regimeReview.counts">
              <span class="todo-pill" v-for="(count, regime) in regimeReview.counts" :key="regime">{{ humanizeToken(regime) }} {{ count }}</span>
            </div>
            <div class="reason-list" v-if="(regimeReview.transitions || []).length">
              <div class="reason-item" v-for="change in regimeReview.transitions" :key="change.timestamp + change.from + change.to">
                <div class="reason-top">
                  <strong>{{ humanizeToken(change.from) }} → {{ humanizeToken(change.to) }}</strong>
                  <span class="section-note">{{ relativeTime(change.timestamp) }}</span>
                </div>
                <div class="reason-text">{{ formatTime(change.timestamp) }}</div>
              </div>
            </div>
            <div v-else class="empty-state">No recent regime transitions inside the current journal window.</div>
          </div>
        </div>
      </div>

      <div class="section-card">
        <div class="section-head">
          <div>
            <h2>🤖 Bot drill-down table</h2>
            <div class="section-note">Each bot now stays in a compact table row. Click any row to open the full modal with signals, positions, and recent reasons.</div>
          </div>
        </div>
        <div class="table-shell">
          <table class="data-table bot-table">
            <thead>
              <tr>
                <th>Bot</th>
                <th>Signal</th>
                <th>Value</th>
                <th>Cash</th>
                <th>Positions</th>
                <th>Drift</th>
                <th>Trades</th>
                <th>Win rate</th>
                <th>Target</th>
                <th>Last trade</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="bot in botTableRows" :key="bot.key" class="clickable-row" @click="openBotModal(bot.key)">
                <td>
                  <div class="row-title-cell">
                    <span class="bot-icon">{{ bot.icon }}</span>
                    <div>
                      <div class="row-title">{{ bot.name }}</div>
                      <div class="row-sub">Portfolio {{ shortPct(bot.portfolio_pct) }} · Allocation {{ shortPct(bot.allocation_pct) }}</div>
                    </div>
                  </div>
                </td>
                <td>
                  <div class="cell-wrap">
                    <div class="signal-line">{{ bot.signal_hint }}</div>
                  </div>
                </td>
                <td>{{ formatMoney(bot.value) }}</td>
                <td>
                  <div>{{ formatMoney(bot.usdt) }}</div>
                  <div class="cell-sub">Pos {{ formatMoney(bot.positions_value) }}</div>
                </td>
                <td>{{ bot.positions_count }}</td>
                <td :class="bot.drift_pct <= 0 ? 'green' : 'red'">{{ formatPct(bot.drift_pct) }}</td>
                <td>
                  <div>{{ bot.trade_count }}</div>
                  <div class="cell-sub">24h {{ bot.last_run?.signals_found ?? '—' }} signals</div>
                </td>
                <td>{{ bot.win_rate == null ? '—' : shortPct(bot.win_rate) }}</td>
                <td>{{ formatMoney(bot.target_capital) }}</td>
                <td>
                  <div>{{ bot.last_trade.coin || '—' }} {{ bot.last_trade.action || '' }}</div>
                  <div class="cell-sub">{{ relativeTime(bot.last_trade.time) }} · click for details</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="section-card">
        <div class="section-head">
          <div>
            <h2>🔄 Recent trades details</h2>
            <div class="section-note">Converted into a denser table so rows scan faster while still showing reason and live indicator context.</div>
          </div>
        </div>
        <div class="table-shell">
          <table class="data-table trades-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Bot</th>
                <th>Side</th>
                <th>Coin</th>
                <th>Price</th>
                <th>Qty</th>
                <th>Notional</th>
                <th>PnL</th>
                <th>Reason</th>
                <th>Market snapshot</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="trade in recentTrades" :key="trade.time + trade.bot + trade.coin + trade.action">
                <td>
                  <div>{{ relativeTime(trade.time) }}</div>
                  <div class="cell-sub">{{ formatTime(trade.time) }}</div>
                </td>
                <td>
                  <span class="table-pill outline" :style="{ borderColor: trade.bot_color, color: '#e2e8f0' }">{{ trade.bot }}</span>
                </td>
                <td>
                  <span class="table-pill" :class="tradeActionClass(trade.action)">{{ trade.action }}</span>
                </td>
                <td><strong>{{ trade.coin }}</strong></td>
                <td>{{ formatMoney(trade.price, trade.price < 1 ? 5 : 2) }}</td>
                <td>{{ formatQty(trade.qty) }}</td>
                <td>{{ trade.usdt ? formatMoney(trade.usdt) : '—' }}</td>
                <td :class="trade.pnl == null ? '' : (trade.pnl >= 0 ? 'green' : 'red')">{{ trade.pnl == null ? '—' : formatMoney(trade.pnl) }}</td>
                <td>
                  <div class="reason-cell">{{ trade.reason }}</div>
                </td>
                <td>
                  <div v-if="trade.indicators" class="snapshot-grid">
                    <span v-for="chip in tradeSnapshotChips(trade)" :key="chip.label" class="snapshot-chip" :class="chip.tone">
                      <strong>{{ chip.label }}</strong>
                      <span>{{ chip.value }}</span>
                    </span>
                  </div>
                  <div v-else class="cell-sub">No indicator snapshot</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="activeBot" class="modal-backdrop" @click.self="closeBotModal">
        <div class="modal-shell" role="dialog" aria-modal="true" :aria-label="activeBot.name + ' details'">
          <div class="modal-header">
            <div>
              <div class="modal-kicker">🤖 Bot drill-down</div>
              <div class="modal-title-row">
                <span class="bot-icon">{{ activeBot.icon }}</span>
                <div>
                  <div class="modal-title">{{ activeBot.name }}</div>
                  <div class="section-note">Live allocation, positions, and signal context for this bot only.</div>
                </div>
              </div>
            </div>
            <button class="modal-close" @click="closeBotModal" aria-label="Close bot details">✕</button>
          </div>

          <div class="modal-summary-grid">
            <div class="metric">
              <div class="k">Portfolio value</div>
              <div class="v">{{ formatMoney(activeBot.total_value) }}</div>
            </div>
            <div class="metric">
              <div class="k">Portfolio share</div>
              <div class="v">{{ shortPct(activeBot.portfolio_share, 1) }}</div>
            </div>
            <div class="metric">
              <div class="k">Open positions</div>
              <div class="v">{{ activeBot.position_count }}</div>
            </div>
            <div class="metric">
              <div class="k">24h activity</div>
              <div class="v">{{ activeBot.trades_24h }} trades</div>
            </div>
          </div>

          <div class="bot-expand modal-expand">
            <div class="expand-grid modal-grid-top">
              <div class="mini-panel">
                <div class="mini-title">Deeper bot stats</div>
                <div class="metric-grid">
                  <div class="metric"><div class="k">Return</div><div class="v">{{ activeBot.total_return_pct == null ? '—' : formatPct(activeBot.total_return_pct) }}</div></div>
                  <div class="metric"><div class="k">Expectancy</div><div class="v">{{ activeBot.expectancy == null ? '—' : activeBot.expectancy }}</div></div>
                  <div class="metric"><div class="k">Drawdown</div><div class="v">{{ activeBot.drawdown_pct == null ? '—' : shortPct(activeBot.drawdown_pct) }}</div></div>
                  <div class="metric"><div class="k">Unrealized PnL</div><div class="v" :class="activeBot.unrealized_pnl >= 0 ? 'green' : 'red'">{{ formatMoney(activeBot.unrealized_pnl || 0) }}</div></div>
                  <div class="metric"><div class="k">Realized recent</div><div class="v" :class="activeBot.realized_pnl_recent >= 0 ? 'green' : 'red'">{{ formatMoney(activeBot.realized_pnl_recent || 0) }}</div></div>
                  <div class="metric"><div class="k">Last run</div><div class="v">{{ activeBot.last_run.time || '—' }}</div></div>
                </div>
                <div class="todo-strip" v-if="activeBot.last_run && Object.keys(activeBot.last_run).length">
                  <span class="todo-pill" v-if="activeBot.last_run.fng">F&G {{ activeBot.last_run.fng }}</span>
                  <span class="todo-pill" v-if="activeBot.last_run.buys">Buys {{ activeBot.last_run.buys }}</span>
                  <span class="todo-pill" v-if="activeBot.last_run.sold">Sold {{ activeBot.last_run.sold }}</span>
                  <span class="todo-pill" v-if="activeBot.last_run.signals_found !== undefined">Signals {{ activeBot.last_run.signals_found }}</span>
                </div>
              </div>

              <div class="mini-panel">
                <div class="mini-title">Recent trade reasons</div>
                <div class="reason-list" v-if="activeBot.recent_trade_reasons.length">
                  <div class="reason-item" v-for="reason in activeBot.recent_trade_reasons" :key="reason.time + reason.coin + reason.action">
                    <div class="reason-top">
                      <strong>{{ reason.coin || '—' }} {{ reason.action }}</strong>
                      <span class="section-note">{{ relativeTime(reason.time) }}</span>
                    </div>
                    <div class="reason-text">{{ reason.reason }}</div>
                  </div>
                </div>
                <div v-else class="empty-state">No recent trade reasons yet.</div>
              </div>
            </div>

            <div class="expand-grid">
              <div class="mini-panel">
                <div class="mini-title">Coin contribution to total portfolio</div>
                <div class="positions-table" v-if="activeBot.positions.length">
                  <div class="position-row" v-for="position in activeBot.positions" :key="position.coin">
                    <div>
                      <div class="position-head">
                        <span class="coin-pill">{{ position.coin }}</span>
                        <strong :class="positionPnlClass(position.pnl_pct)">{{ formatPct(position.pnl_pct) }}</strong>
                      </div>
                      <div class="position-meta">Avg {{ formatMoney(position.avg, 4) }} · Live {{ formatMoney(position.current, 4) }} · Qty {{ Number(position.qty).toFixed(4) }}</div>
                    </div>
                    <div class="position-value">
                      <div>{{ formatMoney(position.value) }}</div>
                      <div class="position-share">{{ shortPct(contributionForPosition(activeBot, position), 2) }} of total portfolio</div>
                    </div>
                  </div>
                </div>
                <div v-else class="empty-state">No open positions for this bot.</div>
              </div>

              <div class="mini-panel">
                <div class="mini-title">Signal snapshots</div>
                <div class="signal-grid" v-if="activeBot.signal_snapshots.length">
                  <div class="signal-item" v-for="signal in activeBot.signal_snapshots" :key="activeBot.key + signal.symbol">
                    <div class="signal-top">
                      <strong>{{ signal.symbol }}</strong>
                      <span class="section-note">Live {{ formatMoney(signal.price, signal.price < 1 ? 5 : 2) }}</span>
                    </div>
                    <div class="signal-text">RSI, MACD, moving averages, and volume context are shown here to explain what the bot is seeing now.</div>
                    <div class="signal-metrics">
                      <span class="pill" :class="indicatorTone(signal.rsi, 'rsi')">RSI {{ Number(signal.rsi).toFixed(1) }}</span>
                      <span class="pill" :class="indicatorTone(signal.macd_hist, 'macd')">MACD {{ Number(signal.macd_hist).toFixed(4) }}</span>
                      <span class="pill">MA20 {{ formatMoney(signal.ma20, signal.ma20 < 1 ? 5 : 2) }}</span>
                      <span class="pill">MA50 {{ formatMoney(signal.ma50, signal.ma50 < 1 ? 5 : 2) }}</span>
                      <span class="pill" :class="indicatorTone(signal.volume_ratio, 'vol')">Vol {{ Number(signal.volume_ratio).toFixed(2) }}x</span>
                    </div>
                  </div>
                </div>
                <div v-else class="empty-state">Live signal snapshots unavailable for this bot right now.</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
  `,
}).mount('#app');
