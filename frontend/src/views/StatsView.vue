<template>
  <div class="stats">
    <!-- Header -->
    <div class="stats-header">
      <div>
        <div class="stats-title">盈利统计</div>
        <div class="stats-sub">总体收益概览</div>
      </div>
    </div>

    <!-- Hero PnL card -->
    <div class="hero-card">
      <div class="hero-label">累计盈亏 (USDT)</div>
      <div class="hero-value mono" :class="pnlClass(summary?.total_pnl)">
        {{ summary?.total_pnl != null ? (summary.total_pnl >= 0 ? '+' : '') + summary.total_pnl.toFixed(4) : '--' }}
      </div>
      <div class="hero-sub" v-if="summary?.total_pnl != null">
        {{ summary.total_pnl >= 0 ? '盈利中' : '亏损中' }}
      </div>
    </div>

    <!-- 3 smaller stat cards -->
    <div class="mini-grid">
      <div class="mini-card">
        <div class="mini-icon">🔄</div>
        <div class="mini-label">总交易次数</div>
        <div class="mini-value mono">{{ summary?.total_trades ?? '--' }}</div>
      </div>
      <div class="mini-card">
        <div class="mini-icon">🎯</div>
        <div class="mini-label">胜率</div>
        <div class="mini-value mono accent-num">{{ summary?.win_rate != null ? summary.win_rate.toFixed(1) + '%' : '--' }}</div>
      </div>
      <div class="mini-card">
        <div class="mini-icon">📐</div>
        <div class="mini-label">笔均盈亏</div>
        <div class="mini-value mono" :class="pnlClass(summary?.avg_pnl_per_trade)">
          {{ summary?.avg_pnl_per_trade != null ? summary.avg_pnl_per_trade.toFixed(4) : '--' }}
        </div>
      </div>
    </div>

    <!-- Fees notice -->
    <div v-if="summary?.total_fees != null" class="fees-row">
      <span class="fees-label">累计手续费</span>
      <span class="fees-val mono">-{{ summary.total_fees.toFixed(4) }} USDT</span>
    </div>

    <!-- Chart section -->
    <div class="chart-section">
      <div class="chart-header">
        <span class="section-title">每日盈亏</span>
        <div class="days-pills">
          <button
            v-for="d in [7, 30, 90]"
            :key="d"
            class="day-pill"
            :class="days === d && 'active'"
            @click="setDays(d)"
          >{{ d }}天</button>
        </div>
      </div>
      <div class="chart-wrap">
        <Bar v-if="chartData" :data="chartData" :options="chartOptions" />
        <div v-else class="empty-tip">
          <div class="empty-icon">📊</div>
          <div>暂无数据</div>
        </div>
      </div>
    </div>

    <!-- Symbol PnL list -->
    <div class="section-header">
      <span class="section-title">各币种盈亏</span>
    </div>

    <div class="sym-list">
      <div v-for="item in symbolPnl" :key="item.symbol" class="sym-row">
        <div class="sym-left">
          <div class="sym-name">{{ item.symbol.replace('/USDT', '') }}</div>
          <div class="sym-meta">
            <span class="sym-trades">{{ item.trades }} 笔</span>
            <div class="wr-bar-wrap">
              <div class="wr-bar" :style="{ width: (item.win_rate || 0) + '%' }"></div>
            </div>
            <span class="sym-wr">{{ item.win_rate?.toFixed(1) }}%</span>
          </div>
        </div>
        <div class="sym-pnl mono" :class="pnlClass(item.pnl)">
          {{ item.pnl >= 0 ? '+' : '' }}{{ item.pnl?.toFixed(4) }}
        </div>
      </div>
    </div>

    <div v-if="symbolPnl.length === 0" class="empty-tip">
      <div class="empty-icon">📭</div>
      <div>暂无交易记录</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, BarElement, CategoryScale, LinearScale, Tooltip } from 'chart.js'
import { getSummary, getDailyPnl, getSymbolPnl } from '../api/stats'

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip)

const summary   = ref(null)
const symbolPnl = ref([])
const dailyPnl  = ref([])
const days      = ref(30)

const pnlClass = (v) => v == null ? '' : v > 0 ? 'green' : v < 0 ? 'red' : ''

const chartData = computed(() => {
  if (!dailyPnl.value.length) return null
  return {
    labels: dailyPnl.value.map(d => d.date.slice(5)),
    datasets: [{
      data: dailyPnl.value.map(d => d.pnl),
      backgroundColor: dailyPnl.value.map(d => d.pnl >= 0 ? '#10b981' : '#ef4444'),
      borderRadius: 3,
    }]
  }
})

const chartOptions = {
  responsive: true,
  plugins: { legend: { display: false } },
  scales: {
    x: { ticks: { color: '#4a6080', font: { size: 10 } }, grid: { color: '#1e2d45' } },
    y: { ticks: { color: '#4a6080', font: { size: 10 } }, grid: { color: '#1e2d45' } },
  }
}

async function setDays(d) {
  days.value = d
  const res = await getDailyPnl(d)
  if (res) dailyPnl.value = res
}

onMounted(async () => {
  const [s, sp, dp] = await Promise.all([getSummary(), getSymbolPnl(), getDailyPnl(days.value)])
  if (s)  summary.value   = s
  if (sp) symbolPnl.value = sp.sort((a, b) => b.pnl - a.pnl)
  if (dp) dailyPnl.value  = dp
})
</script>

<style scoped>
.stats {
  background: var(--bg-page);
  min-height: 100vh;
  padding-bottom: 20px;
}

/* ── Header ── */
.stats-header {
  padding: 16px 16px 12px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-subtle);
}
.stats-title { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.stats-sub   { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

/* ── Hero PnL card ── */
.hero-card {
  margin: 14px 14px 0;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  padding: 20px 20px 18px;
  text-align: center;
  position: relative;
  overflow: hidden;
}
.hero-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, #3b82f6, #6366f1);
}
.hero-label { font-size: 12px; color: var(--text-muted); letter-spacing: 0.04em; margin-bottom: 8px; }
.hero-value {
  font-size: 36px;
  font-weight: 900;
  line-height: 1;
  margin-bottom: 6px;
}
.hero-sub { font-size: 12px; color: var(--text-muted); }

.mono { font-family: 'SF Mono', 'Fira Code', ui-monospace, monospace; }
.green { color: var(--success); }
.red   { color: var(--danger); }

/* Gradient text for hero when positive */
.hero-value.green {
  background: linear-gradient(90deg, #10b981, #34d399);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.hero-value.red {
  background: linear-gradient(90deg, #ef4444, #f87171);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* ── Mini stats grid ── */
.mini-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
  padding: 10px 14px 0;
}
.mini-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  padding: 12px 10px;
  text-align: center;
  box-shadow: var(--shadow-card);
}
.mini-icon   { font-size: 16px; margin-bottom: 4px; }
.mini-label  { font-size: 10px; color: var(--text-muted); margin-bottom: 4px; }
.mini-value  { font-size: 16px; font-weight: 800; color: var(--text-primary); }
.accent-num  { color: var(--accent-from); }

/* ── Fees row ── */
.fees-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 10px 14px 0;
  padding: 10px 14px;
  background: rgba(239,68,68,0.06);
  border: 1px solid rgba(239,68,68,0.15);
  border-radius: 10px;
}
.fees-label { font-size: 12px; color: var(--text-muted); }
.fees-val   { font-size: 13px; font-weight: 700; color: var(--danger); }

/* ── Chart section ── */
.chart-section {
  margin: 12px 14px 0;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  padding: 14px;
  box-shadow: var(--shadow-card);
}
.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.days-pills {
  display: flex;
  gap: 6px;
}
.day-pill {
  padding: 4px 12px;
  border-radius: 20px;
  border: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-sec);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s;
}
.day-pill.active {
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 2px 8px rgba(99,102,241,0.3);
}
.chart-wrap { min-height: 160px; }

/* ── Section header ── */
.section-header {
  padding: 16px 16px 6px;
}
.section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* ── Symbol list ── */
.sym-list {
  margin: 0 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}
.sym-row {
  display: flex;
  align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle);
  gap: 12px;
}
.sym-row:last-child { border-bottom: none; }

.sym-left { flex: 1; min-width: 0; }
.sym-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 5px;
}
.sym-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sym-trades {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}
.wr-bar-wrap {
  flex: 1;
  height: 4px;
  background: var(--bg-elevated);
  border-radius: 2px;
  overflow: hidden;
  max-width: 60px;
}
.wr-bar {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #6366f1);
  border-radius: 2px;
  transition: width 0.4s;
}
.sym-wr {
  font-size: 11px;
  color: var(--text-sec);
  white-space: nowrap;
}

.sym-pnl {
  font-size: 14px;
  font-weight: 800;
  flex-shrink: 0;
}

/* ── Empty ── */
.empty-tip {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 40px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.empty-icon { font-size: 28px; }
</style>
