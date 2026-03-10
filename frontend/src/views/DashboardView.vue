<template>
  <div class="dashboard">
    <van-nav-bar title="交易主页" :right-text="auth.user?.username" @click-right="logout" />

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">USDT 余额</div>
        <div class="stat-value">{{ balance ?? '--' }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">累计盈亏</div>
        <div class="stat-value" :class="pnlClass(summary?.total_pnl)">
          {{ summary?.total_pnl != null ? summary.total_pnl.toFixed(2) : '--' }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">持仓数</div>
        <div class="stat-value">{{ bot.positions.length }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">胜率</div>
        <div class="stat-value">{{ summary?.win_rate != null ? summary.win_rate.toFixed(1) + '%' : '--' }}</div>
      </div>
    </div>

    <div class="section">
      <van-button block :type="bot.running ? 'danger' : 'primary'" :loading="botLoading" @click="toggleBot" class="bot-btn">
        {{ bot.running ? '停止 Bot' : '启动 Bot' }}
      </van-button>
    </div>

    <div class="section-title">当前持仓 ({{ bot.positions.length }})</div>
    <div v-if="bot.positions.length === 0" class="empty-tip">暂无持仓</div>
    <div v-for="pos in bot.positions" :key="pos.id" class="pos-card" @click="showPosMenu(pos)">
      <div class="pos-top">
        <span class="pos-symbol">{{ pos.symbol }}</span>
        <span class="pos-pnl" :class="pnlClass(pos.pnl_pct)">
          {{ pos.pnl_pct != null ? (pos.pnl_pct > 0 ? '+' : '') + pos.pnl_pct.toFixed(2) + '%' : '--' }}
        </span>
      </div>
      <div class="pos-row">
        <span class="pos-meta">均价 {{ pos.avg_price?.toFixed(4) }}</span>
        <span class="pos-meta">现价 {{ pos.current_price?.toFixed(4) ?? '--' }}</span>
      </div>
      <div class="pos-row">
        <van-tag :type="pos.martin_level > 0 ? 'warning' : 'primary'" size="mini">L{{ pos.martin_level }}</van-tag>
        <van-tag v-if="pos.trailing_active" type="success" size="mini" style="margin-left:4px">追踪中</van-tag>
        <span class="pos-meta" style="margin-left:auto">RSI {{ bot.rsi[pos.symbol] != null ? bot.rsi[pos.symbol].toFixed(1) : '--' }}</span>
      </div>
    </div>

    <van-action-sheet v-model:show="menuShow" :title="menuPos?.symbol" :actions="menuActions" @select="onMenuAction" cancel-text="取消" />

    <van-dialog v-model:show="sellShow" title="手动卖出" :before-close="onSellConfirm" show-cancel-button>
      <div class="dialog-body">
        <van-radio-group v-model="sellPct" direction="horizontal">
          <van-radio :name="25">25%</van-radio>
          <van-radio :name="50">50%</van-radio>
          <van-radio :name="100">100%</van-radio>
        </van-radio-group>
      </div>
    </van-dialog>

    <van-dialog v-model:show="buyShow" title="手动补仓" :before-close="onBuyConfirm" show-cancel-button>
      <div class="dialog-body">
        <van-field v-model="buyAmt" type="number" label="金额 (USDT)" placeholder="如 40" :border="false" />
      </div>
    </van-dialog>

    <div class="section-title">运行日志</div>
    <div class="log-box">
      <div v-for="log in bot.logs.slice(0, 60)" :key="log.id" class="log-item" :class="'log-' + log.level.toLowerCase()">
        <span class="log-time">{{ fmtTime(log.timestamp) }}</span>
        <span v-if="log.symbol" class="log-sym">[{{ log.symbol }}]</span>
        <span>{{ log.message }}</span>
      </div>
      <div v-if="bot.logs.length === 0" class="empty-tip">暂无日志</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import { useAuthStore } from '../stores/auth'
import { useBotStore } from '../stores/bot'
import { useWebSocket } from '../composables/useWebSocket'
import { startBot, stopBot, manualSell, manualBuy } from '../api/trading'
import { getSummary } from '../api/stats'
import router from '../router'

const auth       = useAuthStore()
const bot        = useBotStore()
const botLoading = ref(false)
const balance    = ref(null)
const summary    = ref(null)
const menuShow   = ref(false)
const menuPos    = ref(null)
const sellShow   = ref(false)
const sellPct    = ref(100)
const buyShow    = ref(false)
const buyAmt     = ref('')

const menuActions = [{ name: '手动卖出', color: '#ef4444' }, { name: '手动补仓', color: '#3b82f6' }]

const pnlClass = (v) => v == null ? '' : v > 0 ? 'green' : v < 0 ? 'red' : ''
const fmtTime  = (ts) => ts ? new Date(ts + 'Z').toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''

async function toggleBot() {
  botLoading.value = true
  const res = await (bot.running ? stopBot() : startBot())
  if (res) bot.running = res.running
  botLoading.value = false
  await bot.refresh()
}

function showPosMenu(pos) { menuPos.value = pos; menuShow.value = true }
function onMenuAction(action) {
  if (action.name === '手动卖出') { sellPct.value = 100; sellShow.value = true }
  else { buyAmt.value = ''; buyShow.value = true }
}
async function onSellConfirm(action) {
  if (action !== 'confirm') return true
  const res = await manualSell(menuPos.value.id, sellPct.value)
  if (res) { showToast('卖出完成 PnL: ' + res.pnl?.toFixed(4) + ' USDT'); await bot.refresh() }
  return true
}
async function onBuyConfirm(action) {
  if (action !== 'confirm') return true
  const amt = parseFloat(buyAmt.value)
  if (!amt) { showToast('请输入有效金额'); return false }
  const res = await manualBuy(menuPos.value.id, amt)
  if (res) { showToast('补仓完成 均价: ' + res.new_avg_price?.toFixed(6)); await bot.refresh() }
  return true
}

const { connect, disconnect } = useWebSocket('/ws', (msg) => {
  bot.applyWsMessage(msg)
  if (['position_opened', 'martin_buy', 'position_closed', 'position_partial_sell'].includes(msg.type)) bot.loadLogs()
})

let timer = null
onMounted(async () => {
  await bot.refresh()
  await bot.loadLogs()
  summary.value = await getSummary()
  balance.value = bot.balance
  connect()
  timer = setInterval(async () => { await bot.refresh(); summary.value = await getSummary(); balance.value = bot.balance }, 30000)
})
onUnmounted(() => { clearInterval(timer); disconnect() })

function logout() {
  showConfirmDialog({ title: '确认退出？' }).then(() => { auth.logout(); router.push('/login') })
}
</script>

<style scoped>
.dashboard { background: #0f172a; min-height: 100vh; }
.stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 12px; }
.stat-card  { background: #1e293b; border-radius: 10px; padding: 14px; }
.stat-label { font-size: 11px; color: #64748b; margin-bottom: 6px; }
.stat-value { font-size: 20px; font-weight: 700; color: #e2e8f0; }
.green { color: #22c55e; } .red { color: #ef4444; }
.section { padding: 0 12px 12px; }
.bot-btn { border-radius: 10px; height: 50px; font-size: 16px; font-weight: 600; }
.section-title { padding: 8px 12px 4px; font-size: 12px; font-weight: 600; color: #64748b; letter-spacing: 0.05em; }
.pos-card { margin: 0 12px 10px; background: #1e293b; border-radius: 10px; padding: 14px; cursor: pointer; }
.pos-top  { display: flex; justify-content: space-between; margin-bottom: 8px; }
.pos-symbol { font-size: 15px; font-weight: 700; color: #e2e8f0; }
.pos-pnl   { font-size: 16px; font-weight: 700; }
.pos-row   { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.pos-meta  { font-size: 12px; color: #64748b; }
.empty-tip { text-align: center; color: #475569; font-size: 13px; padding: 24px; }
.log-box   { margin: 0 12px 16px; background: #0f172a; border: 1px solid #1e293b; border-radius: 10px; padding: 10px; max-height: 280px; overflow-y: auto; }
.log-item  { font-size: 11px; padding: 3px 0; border-bottom: 1px solid #1e293b; color: #94a3b8; line-height: 1.5; }
.log-warning { color: #f59e0b; } .log-error { color: #ef4444; }
.log-time  { color: #475569; margin-right: 6px; }
.log-sym   { color: #60a5fa; margin-right: 4px; }
.dialog-body { padding: 20px; }
</style>
