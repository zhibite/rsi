<template>
  <div class="trades">
    <!-- Header -->
    <div class="trades-header">
      <div>
        <div class="trades-title">交易记录</div>
        <div class="trades-sub">历史成交明细</div>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input
          v-model="symFilter"
          class="search-input"
          placeholder="搜索币种…"
          autocomplete="off"
        />
        <button v-if="symFilter" class="clear-btn" @click="symFilter = ''">✕</button>
      </div>
      <van-dropdown-menu active-color="#3b82f6" class="side-dropdown">
        <van-dropdown-item v-model="sideFilter" :options="sideOptions" />
      </van-dropdown-menu>
    </div>

    <!-- List -->
    <div class="order-list">
      <div v-if="loading" class="loading-tip">加载中…</div>

      <template v-else>
        <div v-for="order in orders" :key="order.id" class="order-card">
          <div class="order-side-bar" :class="order.side === 'buy' ? 'bar-buy' : (order.realized_pnl != null && order.realized_pnl < 0 ? 'bar-loss' : 'bar-sell')"></div>

          <div class="order-body">
            <div class="order-top">
              <span class="order-symbol">{{ order.symbol.replace('/USDT', '') }}</span>
              <span class="order-usdt">/USDT</span>
              <span class="side-badge" :class="order.side === 'buy' ? 'badge-buy' : 'badge-sell'">
                {{ order.side === 'buy' ? '买入' : '卖出' }}
              </span>
              <span v-if="order.realized_pnl != null" class="order-pnl mono" :class="order.realized_pnl >= 0 ? 'pnl-pos' : 'pnl-neg'">
                {{ order.realized_pnl >= 0 ? '+' : '' }}{{ order.realized_pnl.toFixed(4) }}
              </span>
            </div>

            <div class="order-metrics">
              <div class="metric">
                <span class="metric-label">价格</span>
                <span class="metric-val mono">{{ order.price?.toFixed(6) ?? '--' }}</span>
              </div>
              <div class="metric-sep"></div>
              <div class="metric">
                <span class="metric-label">数量</span>
                <span class="metric-val mono">{{ order.quantity?.toFixed(6) ?? '--' }}</span>
              </div>
              <div class="metric-sep"></div>
              <div class="metric">
                <span class="metric-label">金额</span>
                <span class="metric-val mono">{{ order.amount_usdt?.toFixed(2) ?? '--' }} U</span>
              </div>
            </div>

            <div class="order-footer">
              <span class="note-badge" :class="noteBadgeClass(order.note)">{{ noteLabel(order.note) }}</span>
              <span class="order-time">{{ fmtTime(order.timestamp) }}</span>
            </div>
          </div>
        </div>

        <div v-if="orders.length === 0" class="empty-tip">暂无记录</div>
      </template>
    </div>

    <!-- Pagination -->
    <div class="pagination">
      <button class="page-btn" :disabled="currentPage === 1" @click="goPage(currentPage - 1)">← 上一页</button>
      <span class="page-info">第 {{ currentPage }} 页</span>
      <button class="page-btn" :disabled="!hasMore" @click="goPage(currentPage + 1)">下一页 →</button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { getOrders } from '../api/trading'

const symFilter  = ref('')
const sideFilter = ref('all')
const sideOptions = [
  { text: '全部方向', value: 'all' },
  { text: '买入', value: 'buy' },
  { text: '卖出', value: 'sell' },
]

const PAGE_SIZE = 10
const orders      = ref([])
const loading     = ref(false)
const currentPage = ref(1)
const hasMore     = ref(false)

const noteMap = { seed: '首单', ladder_1: 'M1', ladder_2: 'M2', ladder_3: 'M3', ladder_4: 'M4', ladder_5: 'M5', trailing_stop: '追踪止盈', overbought_sell: '超买止盈', stop_loss: '止损', manual_sell: '手动卖' }
const noteLabel = (n) => noteMap[n] || n || '--'
const fmtTime   = (ts) => ts ? new Date(ts + 'Z').toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''
const noteBadgeClass = (n) => {
  if (!n) return 'note-default'
  if (n === 'seed') return 'note-badge note-seed'
  if (n.startsWith('ladder_') || n.startsWith('M')) return 'note-badge note-martin'
  if (n === 'trailing_stop' || n === 'overbought_sell') return 'note-badge note-trailing'
  if (n === 'stop_loss') return 'note-badge note-loss'
  return 'note-badge note-default'
}

async function fetchPage(page) {
  loading.value = true
  const params = { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }
  if (symFilter.value) params.symbol = symFilter.value
  if (sideFilter.value !== 'all') params.side = sideFilter.value
  const res = await getOrders(params)
  loading.value = false
  orders.value = res || []
  hasMore.value = (res?.length ?? 0) === PAGE_SIZE
}

async function goPage(page) {
  currentPage.value = page
  await fetchPage(page)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function onRefresh() {
  currentPage.value = 1
  await fetchPage(1)
}

watch([symFilter, sideFilter], onRefresh)
onMounted(onRefresh)
</script>

<style scoped>
.trades {
  background: var(--bg-page);
  min-height: 100vh;
  padding-bottom: 16px;
}

/* ── Header ── */
.trades-header {
  padding: 16px 16px 12px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-subtle);
}
.trades-title { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.trades-sub   { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

/* ── Filter bar ── */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-subtle);
}
.search-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 7px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 0 10px;
  height: 38px;
}
.search-icon { font-size: 13px; flex-shrink: 0; }
.search-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 13px;
  caret-color: var(--accent-from);
}
.search-input::placeholder { color: var(--text-muted); }
.clear-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.side-dropdown { flex-shrink: 0; }

/* ── Order cards ── */
.order-card {
  margin: 8px 14px 0;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  display: flex;
  overflow: hidden;
}

.order-side-bar {
  width: 4px;
  flex-shrink: 0;
}
.bar-buy  { background: linear-gradient(180deg, #3b82f6, #6366f1); }
.bar-sell { background: linear-gradient(180deg, #10b981, #059669); }
.bar-loss { background: linear-gradient(180deg, #ef4444, #dc2626); }

.order-body {
  flex: 1;
  padding: 11px 12px 10px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Row 1 */
.order-top {
  display: flex;
  align-items: center;
  gap: 5px;
}
.order-symbol {
  font-size: 15px;
  font-weight: 800;
  color: var(--text-primary);
  flex-shrink: 0;
}
.order-usdt {
  font-size: 11px;
  color: var(--text-muted);
  margin-right: 3px;
}
.side-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 6px;
  flex-shrink: 0;
}
.badge-buy  { background: rgba(59,130,246,0.15); color: #60a5fa; border: 1px solid rgba(59,130,246,0.2); }
.badge-sell { background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.2); }

.order-pnl {
  margin-left: auto;
  font-size: 14px;
  font-weight: 800;
  flex-shrink: 0;
}
.pnl-pos { color: var(--success); }
.pnl-neg { color: var(--danger); }
.mono { font-family: 'SF Mono', 'Fira Code', ui-monospace, monospace; }

/* Row 2 */
.order-metrics {
  display: flex;
  align-items: center;
  gap: 8px;
}
.metric { display: flex; flex-direction: column; gap: 2px; }
.metric-label { font-size: 10px; color: var(--text-muted); }
.metric-val   { font-size: 12px; color: var(--text-sec); }
.metric-sep   { width: 1px; height: 24px; background: var(--border-subtle); flex-shrink: 0; }

/* Row 3 */
.order-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.note-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
  letter-spacing: 0.02em;
}

/* Note type colors */
.note-badge.note-seed     { background: rgba(59,130,246,0.15); color: #60a5fa;  border: 1px solid rgba(59,130,246,0.2); }
.note-badge.note-martin   { background: rgba(245,158,11,0.15); color: #fbbf24;  border: 1px solid rgba(245,158,11,0.2); }
.note-badge.note-trailing { background: rgba(16,185,129,0.15); color: #34d399;  border: 1px solid rgba(16,185,129,0.2); }
.note-badge.note-loss     { background: rgba(239,68,68,0.15);  color: #f87171;  border: 1px solid rgba(239,68,68,0.2); }
.note-badge.note-default  { background: var(--bg-elevated); color: var(--text-muted); border: 1px solid var(--border-subtle); }

.order-time { font-size: 11px; color: var(--text-muted); }

/* ── Pagination ── */
.order-list { padding-bottom: 4px; }

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 16px 14px 8px;
}
.page-btn {
  height: 36px;
  padding: 0 18px;
  border-radius: 18px;
  border: 1px solid var(--border-vis);
  background: var(--bg-card);
  color: var(--text-sec);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s;
  white-space: nowrap;
}
.page-btn:not(:disabled):hover { border-color: var(--accent-from); color: var(--accent-from); }
.page-btn:not(:disabled):active { transform: scale(0.96); }
.page-btn:disabled { opacity: 0.35; cursor: not-allowed; }

.page-info {
  font-size: 13px;
  color: var(--text-muted);
  min-width: 60px;
  text-align: center;
}

/* ── Loading / Empty ── */
.loading-tip {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 40px;
}
.empty-tip {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 40px;
}
</style>

