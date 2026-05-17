const { createApp } = Vue;

createApp({
  data() {
    return {
      loading: true,
      error: '',
      payload: null,
      expandedBots: {},
      refreshBusy: false,
      refreshStatus: 'Live polling every 30s',
      allocationHover: null,
      activityHover: null,
      equityHover: null,
      pollHandle: null,
    };
  },
  computed: {
    summary() { return this.payload?.summary || {}; },
    bots() { return this.payload?.bots || []; },
    recentTrades() { return this.payload?.recent_trades || []; },
    cronJobs() { return this.payload?.cron || []; },
    todoStats() { return this.payload?.todo?.stats || {}; },
    allocationSegments() { return this.payload?.charts?.allocation || []; },
    activityRows() { return this.payload?.charts?.activity || []; },
    equityPoints() { return this.payload?.charts?.equity || []; },
    totalAllocation() {
      return this.allocationSegments.reduce((sum, item) => sum + Number(item.value || 0), 0);
    },
    activityMax() {
      return Math.max(1, ...this.activityRows.map(item => Number(item.value || 0)));
    },
    lineChart() {
      const points = this.equityPoints;
      const width = 760;
      const height = 250;
      const left = 50;
      const right = 18;
      const top = 20;
      const bottom = 32;
      if (!points.length) {
        return { width, height, points: [], area: '', ticks: [], labels: [], min: 0, max: 0, delta: 0 };
      }
      const values = points.map(item => Number(item.value || 0));
      const min = Math.min(...values);
      const max = Math.max(...values);
      const span = Math.max(max - min, 1);
      const axisMin = min - span * 0.14;
      const axisMax = max + span * 0.14;
      const usableW = width - left - right;
      const usableH = height - top - bottom;
      const step = points.length > 1 ? usableW / (points.length - 1) : 0;
      const mapped = points.map((item, idx) => {
        const value = Number(item.value || 0);
        const x = left + idx * step;
        const y = top + ((axisMax - value) / Math.max(axisMax - axisMin, 1e-6)) * usableH;
        return { ...item, x, y, value, idx };
      });
      const polyline = mapped.map(item => `${item.x.toFixed(2)},${item.y.toFixed(2)}`).join(' ');
      const area = mapped.length
        ? `${polyline} ${mapped[mapped.length - 1].x.toFixed(2)},${(top + usableH).toFixed(2)} ${left},${(top + usableH).toFixed(2)}`
        : '';
      const ticks = [0, 0.25, 0.5, 0.75, 1].map(frac => {
        const value = axisMax - (axisMax - axisMin) * frac;
        return {
          y: top + usableH * frac,
          value,
        };
      });
      const labelStep = Math.max(1, Math.floor(points.length / 6));
      const labels = mapped.filter(item => item.idx % labelStep === 0 || item.idx === mapped.length - 1);
      return { width, height, left, right, top, bottom, points: mapped, polyline, area, ticks, labels, min, max, delta: values[values.length - 1] - values[0] };
    },
  },
  methods: {
    async loadDashboard() {
      this.loading = true;
      this.error = '';
      try {
        const response = await fetch('/api/dashboard-data', { cache: 'no-store' });
        if (!response.ok) throw new Error(`dashboard data request failed (${response.status})`);
        this.payload = await response.json();
        if (!Object.keys(this.expandedBots).length && this.bots[0]) {
          this.expandedBots[this.bots[0].key] = true;
        }
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
    relativeTime(value) {
      if (!value) return '—';
      const ts = new Date(value).getTime();
      if (!Number.isFinite(ts)) return '—';
      const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
      if (diffSec < 60) return `${diffSec}s ago`;
      if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
      return `${Math.floor(diffSec / 3600)}h ${Math.floor((diffSec % 3600) / 60)}m ago`;
    },
    formatTime(value) {
      if (!value) return '—';
      const dt = new Date(value);
      if (Number.isNaN(dt.getTime())) return '—';
      return dt.toLocaleString();
    },
    toggleBot(key) {
      this.expandedBots[key] = !this.expandedBots[key];
    },
    isExpanded(key) {
      return !!this.expandedBots[key];
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
    equityHoverPoint(point) {
      this.equityHover = point;
    },
    clearEquityHover() {
      this.equityHover = null;
    },
    activeEquityPoint() {
      return this.equityHover || this.lineChart.points[this.lineChart.points.length - 1] || null;
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
      const active = this.activeEquityPoint();
      if (!active) return 'Waiting for more journal history';
      return `${active.label || 'Latest'} · ${this.formatMoney(active.value)} · Δ ${this.formatMoney(this.lineChart.delta)}`;
    },
  },
  mounted() {
    this.loadDashboard();
    this.pollHandle = window.setInterval(() => this.loadDashboard(), 30000);
  },
  beforeUnmount() {
    if (this.pollHandle) window.clearInterval(this.pollHandle);
  },
  template: `
  <div>
    <div class="page-header">
      <div>
        <h1 class="page-title">📊 Multi-Bot Trading Dashboard</h1>
        <p class="page-subtitle">Vue-powered Flask dashboard with live portfolio analytics, drill-down bot cards, synced TODO state, richer recent-trade snapshots, and stronger cron health checks.</p>
      </div>
      <div class="header-actions">
        <button class="btn" @click="refreshPages" :disabled="refreshBusy">{{ refreshBusy ? 'Refreshing…' : 'Refresh generated pages' }}</button>
        <span class="status-note">{{ refreshStatus }}</span>
      </div>
    </div>

    <div class="nav">
      <a class="active" href="/dashboard.html">📊 Spot</a>
      <a href="/futures.html">🔵 Futures</a>
      <a href="/research.html">🔬 Research</a>
      <a href="/todo.html">🗒 Todo</a>
      <a href="/cron.html">⏱ Cron</a>
      <a href="/glossary.html">📖 Glossary</a>
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

        <div class="chart-card">
          <div class="chart-head">
            <div>
              <div class="chart-title">Equity curve</div>
              <div class="chart-subtitle">Clearer history with gradient fill, axis guides, and point hover states</div>
            </div>
            <div class="chart-tooltip">{{ chartInsight() }}</div>
          </div>
          <div v-if="!lineChart.points.length" class="empty-state">Not enough performance-journal data yet.</div>
          <svg v-else class="chart-svg" :viewBox="'0 0 ' + lineChart.width + ' ' + lineChart.height" preserveAspectRatio="none">
            <g v-for="tick in lineChart.ticks" :key="tick.y">
              <line class="chart-gridline" :x1="lineChart.left" :x2="lineChart.width - lineChart.right" :y1="tick.y" :y2="tick.y"></line>
              <text class="chart-axis" x="8" :y="tick.y + 4">{{ formatMoney(tick.value) }}</text>
            </g>
            <defs>
              <linearGradient id="equity-fill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stop-color="#60a5fa" stop-opacity="0.42"></stop>
                <stop offset="100%" stop-color="#60a5fa" stop-opacity="0.03"></stop>
              </linearGradient>
            </defs>
            <polygon :points="lineChart.area" fill="url(#equity-fill)"></polygon>
            <polyline :points="lineChart.polyline" fill="none" stroke="#60a5fa" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"></polyline>
            <g v-for="point in lineChart.points" :key="point.idx" @mouseenter="equityHoverPoint(point)" @mouseleave="clearEquityHover">
              <line :x1="point.x" :x2="point.x" :y1="lineChart.top" :y2="lineChart.height - lineChart.bottom" stroke="#94a3b8" stroke-dasharray="4 5" :opacity="equityHover && equityHover.idx === point.idx ? 1 : 0"></line>
              <circle :cx="point.x" :cy="point.y" :r="equityHover && equityHover.idx === point.idx ? 6 : 4.6" fill="#60a5fa" stroke="#0f172a" stroke-width="2.2"></circle>
            </g>
            <text class="chart-axis" v-for="label in lineChart.labels" :key="label.idx" :x="label.x" :y="lineChart.height - 10" text-anchor="middle">{{ label.label }}</text>
          </svg>
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
            <h2>🤖 Bot cards with drill-downs</h2>
            <div class="section-note">Each card now shows its portfolio share up front, and expands into deeper stats, live signal snapshots, and recent trade reasons.</div>
          </div>
        </div>
        <div class="bots-grid">
          <div class="bot-card" v-for="bot in bots" :key="bot.key" :class="{ open: isExpanded(bot.key) }" :style="{ borderLeft: '4px solid ' + bot.color }" @click="toggleBot(bot.key)">
            <div class="bot-top">
              <div class="bot-name-wrap">
                <div class="bot-icon">{{ bot.icon }}</div>
                <div>
                  <div class="bot-name">{{ bot.name }}</div>
                  <div class="section-note">{{ bot.signal_hint }}</div>
                </div>
              </div>
              <div class="bot-badges">
                <span class="badge">Target {{ shortPct(bot.allocation_pct) }}</span>
                <span class="badge">Portfolio {{ shortPct(bot.portfolio_pct) }}</span>
              </div>
            </div>
            <div class="bot-stats">
              <div class="bot-stat">
                <div class="k">Value</div>
                <div class="v">{{ formatMoney(bot.value) }}</div>
                <div class="s">Contributes {{ shortPct(bot.portfolio_pct) }}</div>
              </div>
              <div class="bot-stat">
                <div class="k">Cash</div>
                <div class="v">{{ formatMoney(bot.usdt) }}</div>
                <div class="s">Positions {{ formatMoney(bot.positions_value) }}</div>
              </div>
              <div class="bot-stat">
                <div class="k">Drift</div>
                <div class="v" :class="bot.drift_pct <= 0 ? 'green' : 'red'">{{ formatPct(bot.drift_pct) }}</div>
                <div class="s">Target {{ formatMoney(bot.target_capital) }}</div>
              </div>
              <div class="bot-stat">
                <div class="k">Trades</div>
                <div class="v">{{ bot.trade_count }}</div>
                <div class="s">Open positions {{ bot.positions_count }}</div>
              </div>
              <div class="bot-stat">
                <div class="k">Win rate</div>
                <div class="v">{{ bot.win_rate == null ? '—' : shortPct(bot.win_rate) }}</div>
                <div class="s">Profit factor {{ bot.profit_factor ?? '—' }}</div>
              </div>
              <div class="bot-stat">
                <div class="k">Last trade</div>
                <div class="v">{{ bot.last_trade.coin || '—' }} {{ bot.last_trade.action || '' }}</div>
                <div class="s">{{ relativeTime(bot.last_trade.time) }}</div>
              </div>
            </div>

            <div v-if="isExpanded(bot.key)" class="bot-expand" @click.stop>
              <div class="expand-grid">
                <div class="mini-panel">
                  <div class="mini-title">Deeper bot stats</div>
                  <div class="metric-grid">
                    <div class="metric"><div class="k">Return</div><div class="v">{{ bot.total_return_pct == null ? '—' : formatPct(bot.total_return_pct) }}</div></div>
                    <div class="metric"><div class="k">Expectancy</div><div class="v">{{ bot.expectancy == null ? '—' : bot.expectancy }}</div></div>
                    <div class="metric"><div class="k">Drawdown</div><div class="v">{{ bot.drawdown_pct == null ? '—' : shortPct(bot.drawdown_pct) }}</div></div>
                    <div class="metric"><div class="k">Unrealized PnL</div><div class="v" :class="bot.unrealized_pnl >= 0 ? 'green' : 'red'">{{ formatMoney(bot.unrealized_pnl || 0) }}</div></div>
                    <div class="metric"><div class="k">Realized recent</div><div class="v" :class="bot.realized_pnl_recent >= 0 ? 'green' : 'red'">{{ formatMoney(bot.realized_pnl_recent || 0) }}</div></div>
                    <div class="metric"><div class="k">Last run</div><div class="v">{{ bot.last_run.time || '—' }}</div></div>
                  </div>
                  <div class="todo-strip" v-if="bot.last_run && Object.keys(bot.last_run).length">
                    <span class="todo-pill" v-if="bot.last_run.fng">F&G {{ bot.last_run.fng }}</span>
                    <span class="todo-pill" v-if="bot.last_run.buys">Buys {{ bot.last_run.buys }}</span>
                    <span class="todo-pill" v-if="bot.last_run.sold">Sold {{ bot.last_run.sold }}</span>
                    <span class="todo-pill" v-if="bot.last_run.signals_found !== undefined">Signals {{ bot.last_run.signals_found }}</span>
                  </div>
                </div>

                <div class="mini-panel">
                  <div class="mini-title">Recent trade reasons</div>
                  <div class="reason-list" v-if="bot.recent_trade_reasons.length">
                    <div class="reason-item" v-for="reason in bot.recent_trade_reasons" :key="reason.time + reason.coin + reason.action">
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
                  <div class="positions-table" v-if="bot.positions.length">
                    <div class="position-row" v-for="position in bot.positions" :key="position.coin">
                      <div>
                        <div class="position-head">
                          <span class="coin-pill">{{ position.coin }}</span>
                          <strong :class="positionPnlClass(position.pnl_pct)">{{ formatPct(position.pnl_pct) }}</strong>
                        </div>
                        <div class="position-meta">Avg {{ formatMoney(position.avg, 4) }} · Live {{ formatMoney(position.current, 4) }} · Qty {{ Number(position.qty).toFixed(4) }}</div>
                      </div>
                      <div class="position-value">
                        <div>{{ formatMoney(position.value) }}</div>
                        <div class="position-share">{{ shortPct(contributionForPosition(bot, position), 2) }} of total portfolio</div>
                      </div>
                    </div>
                  </div>
                  <div v-else class="empty-state">No open positions for this bot.</div>
                </div>

                <div class="mini-panel">
                  <div class="mini-title">Signal snapshots</div>
                  <div class="signal-grid" v-if="bot.signal_snapshots.length">
                    <div class="signal-item" v-for="signal in bot.signal_snapshots" :key="bot.key + signal.symbol">
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
      </div>

      <div class="section-card">
        <div class="section-head">
          <div>
            <h2>🔄 Recent trades</h2>
            <div class="section-note">Responsive cards now include the raw reason text plus richer RSI / MACD / MA / volume snapshots when available.</div>
          </div>
        </div>
        <div class="trade-grid">
          <div class="trade-card" v-for="trade in recentTrades" :key="trade.time + trade.bot + trade.coin + trade.action">
            <div class="trade-top">
              <div class="trade-main">
                <span class="trade-time">{{ relativeTime(trade.time) }}</span>
                <span class="trade-bot" :style="{ borderColor: trade.bot_color }">{{ trade.bot }}</span>
                <span class="trade-action" :class="tradeActionClass(trade.action)">{{ trade.action }}</span>
                <span class="trade-coin">{{ trade.coin }}</span>
              </div>
              <div class="trade-values">
                <span class="badge">@ {{ formatMoney(trade.price, trade.price < 1 ? 5 : 2) }}</span>
                <span class="badge" v-if="trade.usdt">{{ formatMoney(trade.usdt) }}</span>
                <span class="badge" v-if="trade.pnl !== null && trade.pnl !== undefined" :class="trade.pnl >= 0 ? 'green' : 'red'">PnL {{ formatMoney(trade.pnl) }}</span>
              </div>
            </div>
            <div class="trade-reason">{{ trade.reason }}</div>
            <div class="indicator-grid" v-if="trade.indicators">
              <div class="indicator-card">
                <div class="indicator-label">RSI</div>
                <div class="indicator-value">{{ Number(trade.indicators.rsi).toFixed(1) }}</div>
                <div class="indicator-sub">Momentum pressure</div>
              </div>
              <div class="indicator-card">
                <div class="indicator-label">MACD hist</div>
                <div class="indicator-value" :class="indicatorTone(trade.indicators.macd_hist, 'macd')">{{ Number(trade.indicators.macd_hist).toFixed(4) }}</div>
                <div class="indicator-sub">vs signal {{ Number(trade.indicators.macd_signal).toFixed(4) }}</div>
              </div>
              <div class="indicator-card">
                <div class="indicator-label">MA context</div>
                <div class="indicator-value">20 {{ formatMoney(trade.indicators.ma20, trade.indicators.ma20 < 1 ? 5 : 2) }}</div>
                <div class="indicator-sub">50 {{ formatMoney(trade.indicators.ma50, trade.indicators.ma50 < 1 ? 5 : 2) }}</div>
              </div>
              <div class="indicator-card">
                <div class="indicator-label">Volume</div>
                <div class="indicator-value" :class="indicatorTone(trade.indicators.volume_ratio, 'vol')">{{ Number(trade.indicators.volume_ratio).toFixed(2) }}x</div>
                <div class="indicator-sub">{{ formatMoney(trade.indicators.volume, 0) }} vs 20-bar avg</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="section-card">
        <div class="section-head">
          <div>
            <h2>⏱ Cron health</h2>
            <div class="section-note">Cadence-aware rules now flag jobs that miss their expected interval instead of only showing a stale badge.</div>
          </div>
        </div>
        <div class="cron-grid">
          <div class="cron-card" v-for="job in cronJobs" :key="job.job_key">
            <div class="cron-top">
              <div class="cron-name">{{ job.name }}</div>
              <span :class="cronSeverityClass(job.severity)">{{ job.severity }}</span>
            </div>
            <div class="section-note" style="margin-bottom:10px">{{ job.message }}</div>
            <div class="cron-meta">
              <div class="k">Schedule</div><div>{{ job.schedule }}</div>
              <div class="k">Expected cadence</div><div>{{ job.expected_minutes ? job.expected_minutes + 'm' : '—' }}</div>
              <div class="k">Missed runs</div><div>{{ job.missed_runs }}</div>
              <div class="k">Latest status</div><div>{{ job.latest_status }}</div>
              <div class="k">Last run</div><div>{{ relativeTime(job.last_run_at) }}</div>
              <div class="k">Details</div><div>{{ job.details }}</div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
  `,
}).mount('#app');
