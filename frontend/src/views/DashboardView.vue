<template>
  <div class="dashboard">
    <!-- Custom Header -->
    <div class="dash-header">
      <div class="dash-header-left">
        <div class="header-logo">B</div>
        <div>
          <div class="header-title">交易主页</div>
          <div class="header-sub">BQuant RSI Bot</div>
        </div>
      </div>
      <div class="avatar-btn" @click="logout">
        <span class="avatar-initials">{{ auth.user?.username?.charAt(0)?.toUpperCase() || 'U' }}</span>
      </div>
    </div>

    <!-- Stats 2x2 grid -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon">💰</div>
        <div class="stat-label">USDT 余额</div>
        <div class="stat-value mono accent-num">{{ balance ?? '--' }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">📈</div>
        <div class="stat-label">累计盈亏</div>
        <div class="stat-value mono" :class="pnlClass(summary?.total_pnl)">
          {{ summary?.total_pnl != null ? summary.total_pnl.toFixed(2) : '--' }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">📊</div>
        <div class="stat-label">持仓数</div>
        <div class="stat-value mono accent-num">{{ bot.positions.length }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">🎯</div>
        <div class="stat-label">胜率</div>
        <div class="stat-value mono">{{ summary?.win_rate != null ? summary.win_rate.toFixed(1) + '%' : '--' }}</div>
      </div>
    </div>

    <!-- Bot control button -->
    <div class="bot-section">
      <button
        class="bot-btn"
        :class="bot.running ? 'bot-running' : 'bot-stopped'"
        :disabled="botLoading"
        @click="toggleBot"
      >
        <span v-if="bot.running" class="pulse-dot"></span>
        <span v-if="botLoading" class="btn-spinner"></span>
        <span v-else>{{ bot.running ? '停止 Bot' : '启动 Bot' }}</span>
      </button>
    </div>

    <!-- Positions -->
    <div class="section-header">
      <span class="section-title">当前持仓</span>
      <span class="section-badge">{{ bot.positions.length }}</span>
    </div>

    <div v-if="bot.positions.length === 0" class="empty-tip">
      <div class="empty-icon">📭</div>
      <div>暂无持仓</div>
    </div>

    <div
      v-for="pos in bot.positions"
      :key="pos.id"
      class="pos-card"
      :class="pnlClass(pos.pnl_pct)"
      @click="showPosMenu(pos)"
    >
      <!-- Left accent bar -->
      <div class="pos-accent-bar" :class="pnlClass(pos.pnl_pct)"></div>

      <div class="pos-content">
        <div class="pos-top">
          <div class="pos-left">
            <span class="pos-symbol">{{ pos.symbol.replace('/USDT', '') }}</span>
            <span class="pos-usdt">/USDT</span>
            <span class="martin-badge" :class="pos.martin_level > 0 ? 'martin-warn' : 'martin-base'">
              L{{ pos.martin_level }}
            </span>
            <span v-if="pos.trailing_active" class="trailing-badge">追踪</span>
          </div>
          <div class="pos-pnl-block">
            <span class="pos-pnl mono" :class="pnlClass(pos.pnl_pct)">
              {{ pos.pnl_pct != null ? (pos.pnl_pct > 0 ? '+' : '') + pos.pnl_pct.toFixed(2) + '%' : '--' }}
            </span>
          </div>
        </div>

        <div class="pos-prices">
          <div class="price-item">
            <span class="price-label">均价</span>
            <span class="price-val mono">{{ pos.avg_price?.toFixed(4) ?? '--' }}</span>
          </div>
          <div class="price-divider"></div>
          <div class="price-item">
            <span class="price-label">现价</span>
            <span class="price-val mono">{{ pos.current_price?.toFixed(4) ?? '--' }}</span>
          </div>
          <div class="rsi-pill">
            RSI <span class="mono">{{ bot.rsi[pos.symbol] != null ? bot.rsi[pos.symbol].toFixed(1) : '--' }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Action sheet & dialogs (unchanged bindings) -->
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

    <!-- Logs -->
    <div class="section-header" style="margin-top: 16px;">
      <span class="section-title">运行日志</span>
    </div>
    <div class="log-box">
      <div v-for="log in bot.logs.slice(0, 60)" :key="log.id" class="log-item" :class="'log-' + log.level.toLowerCase()">
        <span class="log-time">{{ fmtTime(log.timestamp) }}</span>
        <span v-if="log.symbol" class="log-sym">{{ log.symbol }}</span>
        <span class="log-msg">{{ log.message }}</span>
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
.dashboard {
  background: var(--bg-page);
  min-height: 100vh;
  padding-bottom: 16px;
}

/* ── Header ── */
.dash-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 12px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-subtle);
}
.dash-header-left { display: flex; align-items: center; gap: 10px; }
.header-logo {
  width: 36px; height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  display: flex; align-items: center; justify-content: center;
  font-weight: 900; font-size: 16px; color: #fff;
  flex-shrink: 0;
}
.header-title { font-size: 16px; font-weight: 700; color: var(--text-primary); line-height: 1.2; }
.header-sub   { font-size: 11px; color: var(--text-muted); margin-top: 1px; }

.avatar-btn {
  width: 36px; height: 36px;
  border-radius: 50%;
  background: var(--bg-elevated);
  border: 1px solid var(--border-vis);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: border-color 0.2s;
}
.avatar-btn:active { border-color: var(--accent-from); }
.avatar-initials { font-size: 14px; font-weight: 700; color: var(--accent-from); }

/* ── Stats grid ── */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 14px 14px 0;
}
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  padding: 14px 14px 12px;
  box-shadow: var(--shadow-card);
  position: relative;
  overflow: hidden;
}
.stat-icon   { font-size: 16px; margin-bottom: 6px; }
.stat-label  { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; letter-spacing: 0.02em; }
.stat-value  { font-size: 22px; font-weight: 800; color: var(--text-primary); line-height: 1; }
.accent-num  { background: linear-gradient(90deg, #3b82f6, #6366f1); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.mono        { font-family: 'SF Mono', 'Fira Code', ui-monospace, monospace; }
.green       { color: var(--success) !important; }
.red         { color: var(--danger) !important; }

/* ── Bot button ── */
.bot-section { padding: 14px 14px 0; }
.bot-btn {
  width: 100%;
  height: 54px;
  border-radius: 27px;
  border: none;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.04em;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: opacity 0.2s, transform 0.1s;
}
.bot-btn:active  { transform: scale(0.98); }
.bot-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.bot-stopped {
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4);
}
.bot-running {
  background: linear-gradient(135deg, #dc2626, #ef4444);
  color: #fff;
  box-shadow: 0 4px 16px rgba(239, 68, 68, 0.35);
}

/* Pulsing green dot when running */
.pulse-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.5);
  animation: pulse-ring 1.4s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes pulse-ring {
  0%   { box-shadow: 0 0 0 0 rgba(16,185,129,0.5); }
  70%  { box-shadow: 0 0 0 8px rgba(16,185,129,0); }
  100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); }
}

/* Button spinner */
.btn-spinner {
  width: 18px; height: 18px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Section header ── */
.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 16px 6px;
}
.section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.section-badge {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-from);
  background: rgba(59,130,246,0.12);
  border-radius: 10px;
  padding: 2px 7px;
  min-width: 20px;
  text-align: center;
}

/* ── Empty tip ── */
.empty-tip {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 28px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.empty-icon { font-size: 28px; }

/* ── Position cards ── */
.pos-card {
  margin: 0 14px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  cursor: pointer;
  display: flex;
  overflow: hidden;
  transition: border-color 0.2s;
}
.pos-card:active { opacity: 0.85; }

.pos-accent-bar {
  width: 4px;
  flex-shrink: 0;
  background: var(--border-vis);
  border-radius: 0;
}
.pos-accent-bar.green { background: linear-gradient(180deg, #10b981, #059669) !important; }
.pos-accent-bar.red   { background: linear-gradient(180deg, #ef4444, #dc2626) !important; }

.pos-content { flex: 1; padding: 12px 12px 10px; min-width: 0; }

.pos-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
}
.pos-left { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.pos-symbol { font-size: 16px; font-weight: 800; color: var(--text-primary); }
.pos-usdt   { font-size: 12px; color: var(--text-muted); margin-right: 2px; }

.martin-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 6px;
  letter-spacing: 0.03em;
}
.martin-warn {
  background: rgba(245,158,11,0.18);
  color: var(--warning);
  border: 1px solid rgba(245,158,11,0.25);
}
.martin-base {
  background: rgba(59,130,246,0.15);
  color: var(--accent-from);
  border: 1px solid rgba(59,130,246,0.2);
}
.trailing-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 6px;
  background: rgba(16,185,129,0.15);
  color: var(--success);
  border: 1px solid rgba(16,185,129,0.2);
}

.pos-pnl-block { flex-shrink: 0; }
.pos-pnl {
  font-size: 17px;
  font-weight: 800;
  color: var(--text-primary);
}

.pos-prices {
  display: flex;
  align-items: center;
  gap: 10px;
}
.price-item  { display: flex; flex-direction: column; gap: 2px; }
.price-label { font-size: 10px; color: var(--text-muted); }
.price-val   { font-size: 13px; color: var(--text-sec); }
.price-divider {
  width: 1px; height: 28px;
  background: var(--border-subtle);
  flex-shrink: 0;
}
.rsi-pill {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 3px 8px;
  white-space: nowrap;
}
.rsi-pill .mono { color: var(--accent-from); font-weight: 700; }

/* ── Log box ── */
.log-box {
  margin: 0 14px 16px;
  background: var(--bg-deepest);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  padding: 10px;
  max-height: 260px;
  overflow-y: auto;
}
.log-item {
  font-size: 11px;
  font-family: 'SF Mono', 'Fira Code', ui-monospace, monospace;
  padding: 3px 0;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted);
  line-height: 1.6;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.log-item:last-child { border-bottom: none; }
.log-info    { color: #8899b4; }
.log-warning { color: var(--warning); }
.log-error   { color: var(--danger); }
.log-time    { color: #4a6080; flex-shrink: 0; }
.log-sym     { color: #60a5fa; flex-shrink: 0; font-weight: 600; }
.log-msg     { color: inherit; }

/* ── Dialog body ── */
.dialog-body { padding: 20px 20px 8px; }
</style>
