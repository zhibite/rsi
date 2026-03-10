<template>
  <div class="stats">
    <van-nav-bar title="盈利统计" />

    <div class="stats-grid">
      <div class="stat-card full">
        <div class="stat-label">累计盈亏 (USDT)</div>
        <div class="stat-value big" :class="pnlClass(summary?.total_pnl)">
          {{ summary?.total_pnl != null ? (summary.total_pnl >= 0 ? '+' : '') + summary.total_pnl.toFixed(4) : '--' }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">总交易次数</div>
        <div class="stat-value">{{ summary?.total_trades ?? '--' }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">胜率</div>
        <div class="stat-value">{{ summary?.win_rate != null ? summary.win_rate.toFixed(1) + '%' : '--' }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">笔均盈亏</div>
        <div class="stat-value" :class="pnlClass(summary?.avg_pnl_per_trade)">
          {{ summary?.avg_pnl_per_trade != null ? summary.avg_pnl_per_trade.toFixed(4) : '--' }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">累计手续费</div>
        <div class="stat-value red">{{ summary?.total_fees != null ? '-' + summary.total_fees.toFixed(4) : '--' }}</div>
      </div>
    </div>

    <div class="chart-section">
      <div class="days-btns">
        <button v-for="d in [7, 30, 90]" :key="d" @click="setDays(d)" :class="['day-btn', days === d && 'active']">{{ d }}天</button>
      </div>
      <div class="chart-wrap">
        <Bar v-if="chartData" :data="chartData" :options="chartOptions" />
        <div v-else class="empty-tip">暂无数据</div>
      </div>
    </div>

    <div class="section-title">各币种盈亏</div>
    <div v-for="item in symbolPnl" :key="item.symbol" class="sym-row">
      <div class="sym-name">{{ item.symbol }}</div>
      <div class="sym-stats">
        <span class="sym-trades">{{ item.trades }}笔</span>
        <span class="sym-wr">{{ item.win_rate?.toFixed(1) }}%</span>
        <span :class="['sym-pnl', pnlClass(item.pnl)]">{{ item.pnl >= 0 ? '+' : '' }}{{ item.pnl?.toFixed(4) }}</span>
      </div>
    </div>
    <div v-if="symbolPnl.length === 0" class="empty-tip">暂无交易记录</div>
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
      backgroundColor: dailyPnl.value.map(d => d.pnl >= 0 ? '#22c55e' : '#ef4444'),
      borderRadius: 3,
    }]
  }
})

const chartOptions = {
  responsive: true,
  plugins: { legend: { display: false } },
  scales: {
    x: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: '#1e293b' } },
    y: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: '#1e293b' } },
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
.stats { background: #0f172a; min-height: 100vh; }
.stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 12px; }
.stat-card { background: #1e293b; border-radius: 10px; padding: 14px; }
.stat-card.full { grid-column: span 2; }
.stat-label { font-size: 11px; color: #64748b; margin-bottom: 6px; }
.stat-value { font-size: 20px; font-weight: 700; color: #e2e8f0; }
.stat-value.big { font-size: 28px; }
.green { color: #22c55e; } .red { color: #ef4444; }
.chart-section { margin: 0 12px 12px; background: #1e293b; border-radius: 10px; padding: 14px; }
.days-btns { display: flex; gap: 8px; margin-bottom: 12px; }
.day-btn { padding: 4px 14px; border-radius: 20px; border: 1px solid #334155; background: transparent; color: #94a3b8; font-size: 12px; cursor: pointer; }
.day-btn.active { background: #3b82f6; border-color: #3b82f6; color: #fff; }
.chart-wrap { min-height: 160px; }
.section-title { padding: 8px 12px 4px; font-size: 12px; font-weight: 600; color: #64748b; }
.sym-row  { display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid #1e293b; }
.sym-name { font-size: 14px; color: #e2e8f0; flex: 1; }
.sym-stats { display: flex; gap: 12px; align-items: center; }
.sym-trades { font-size: 12px; color: #64748b; }
.sym-wr    { font-size: 12px; color: #94a3b8; }
.sym-pnl   { font-size: 14px; font-weight: 700; }
.empty-tip { text-align: center; color: #475569; padding: 40px; }
</style>
