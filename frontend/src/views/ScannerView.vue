<template>
  <div class="scanner">
    <!-- Header -->
    <div class="scan-header">
      <div class="scan-header-left">
        <div class="scan-title">RSI 扫描仪</div>
        <div class="scan-sub">实时多空信号监控</div>
      </div>
      <div class="connect-status" :class="connected ? 'conn-on' : 'conn-off'">
        <span class="conn-dot" :class="connected ? 'dot-on' : 'dot-off'"></span>
        <span>{{ connected ? '已连接' : '离线' }}</span>
      </div>
    </div>

    <!-- Stats chips horizontal scroll -->
    <div class="chips-scroll">
      <div class="chip chip-red">
        <span class="chip-label">超卖</span>
        <span class="chip-count">{{ counts.oversold }}</span>
      </div>
      <div class="chip chip-orange">
        <span class="chip-label">近超卖</span>
        <span class="chip-count">{{ counts.nearOversold }}</span>
      </div>
      <div class="chip chip-neutral">
        <span class="chip-label">中性</span>
        <span class="chip-count">{{ counts.neutral }}</span>
      </div>
      <div class="chip chip-green">
        <span class="chip-label">超买</span>
        <span class="chip-count">{{ counts.overbought }}</span>
      </div>
    </div>

    <!-- Search bar -->
    <div class="toolbar">
      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input
          v-model="search"
          class="search-input"
          placeholder="搜索币种…"
        />
      </div>
    </div>

    <!-- Filter pills -->
    <div class="filter-row">
      <button
        v-for="f in filters"
        :key="f.key"
        class="filter-pill"
        :class="activeFilter === f.key && 'active'"
        @click="activeFilter = f.key"
      >{{ f.label }}</button>
    </div>

    <!-- RSI grid -->
    <div class="rsi-grid">
      <div
        v-for="item in displayList"
        :key="item.symbol"
        class="rsi-card"
        :class="rsiClass(item.rsi)"
      >
        <div class="rsi-top">
          <span class="rsi-coin">{{ item.symbol.replace('/USDT', '') }}</span>
          <span class="rsi-val mono" :style="{ color: rsiColor(item.rsi) }">{{ item.rsi.toFixed(1) }}</span>
        </div>
        <div class="rsi-price mono">{{ item.price.toFixed(4) }}</div>
        <div class="rsi-bar-wrap">
          <div class="rsi-bar" :style="{ width: item.rsi + '%', background: rsiColor(item.rsi) }"></div>
        </div>
        <div class="rsi-zone-label" :style="{ color: rsiColor(item.rsi) }">
          {{ item.rsi < 30 ? '超卖' : item.rsi > 70 ? '超买' : '中性' }}
        </div>
      </div>
    </div>

    <div v-if="displayList.length === 0" class="empty-tip">
      <div class="empty-icon">{{ connected ? '⏳' : '📡' }}</div>
      <div>{{ connected ? '加载中...' : '正在连接...' }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { usePublicRsi } from '../composables/usePublicRsi'

const search      = ref('')
const activeFilter = ref('all')
const items       = ref([])

const filters = [
  { key: 'all', label: '全部' },
  { key: 'oversold', label: '超卖<30' },
  { key: 'near', label: '近超卖30-40' },
  { key: 'overbought', label: '超买>70' },
]

const counts = computed(() => ({
  oversold:     items.value.filter(i => i.rsi < 30).length,
  nearOversold: items.value.filter(i => i.rsi >= 30 && i.rsi < 40).length,
  neutral:      items.value.filter(i => i.rsi >= 40 && i.rsi <= 60).length,
  overbought:   items.value.filter(i => i.rsi > 70).length,
}))

const displayList = computed(() => {
  let list = [...items.value]
  if (activeFilter.value === 'oversold')   list = list.filter(i => i.rsi < 30)
  if (activeFilter.value === 'near')       list = list.filter(i => i.rsi >= 30 && i.rsi < 40)
  if (activeFilter.value === 'overbought') list = list.filter(i => i.rsi > 70)
  if (search.value) list = list.filter(i => i.symbol.toLowerCase().includes(search.value.toLowerCase()))
  return list.sort((a, b) => a.rsi - b.rsi)
})

const rsiClass = (rsi) => rsi < 30 ? 'rsi-oversold' : rsi > 70 ? 'rsi-overbought' : ''
const rsiColor = (rsi) => rsi < 30 ? '#ef4444' : rsi > 70 ? '#10b981' : '#3b82f6'

const { connected, connect } = usePublicRsi((snapshot) => { items.value = snapshot })
onMounted(connect)
</script>

<style scoped>
.scanner {
  background: var(--bg-page);
  min-height: 100vh;
  padding-bottom: 16px;
}

/* ── Header ── */
.scan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 12px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-subtle);
}
.scan-title { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.scan-sub   { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

.connect-status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  padding: 5px 10px;
  border-radius: 20px;
  border: 1px solid;
}
.conn-on  { color: var(--success); border-color: rgba(16,185,129,0.25); background: rgba(16,185,129,0.08); }
.conn-off { color: var(--danger);  border-color: rgba(239,68,68,0.25);  background: rgba(239,68,68,0.08); }

.conn-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-on {
  background: var(--success);
  box-shadow: 0 0 0 0 rgba(16,185,129,0.5);
  animation: pulse-conn 1.8s ease-in-out infinite;
}
.dot-off { background: var(--danger); }
@keyframes pulse-conn {
  0%   { box-shadow: 0 0 0 0 rgba(16,185,129,0.5); }
  70%  { box-shadow: 0 0 0 6px rgba(16,185,129,0); }
  100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); }
}

/* ── Chips row ── */
.chips-scroll {
  display: flex;
  gap: 8px;
  padding: 12px 14px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.chips-scroll::-webkit-scrollbar { display: none; }

.chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  border: 1px solid;
  white-space: nowrap;
  flex-shrink: 0;
}
.chip-label { font-size: 12px; font-weight: 600; }
.chip-count {
  font-size: 13px;
  font-weight: 800;
  font-family: 'SF Mono', ui-monospace, monospace;
  min-width: 18px;
  text-align: center;
}

.chip-red     { background: rgba(239,68,68,0.1);    border-color: rgba(239,68,68,0.25);    color: #f87171; }
.chip-orange  { background: rgba(245,158,11,0.1);   border-color: rgba(245,158,11,0.25);   color: #fbbf24; }
.chip-neutral { background: rgba(139,148,160,0.1);  border-color: rgba(139,148,160,0.2);   color: var(--text-sec); }
.chip-green   { background: rgba(16,185,129,0.1);   border-color: rgba(16,185,129,0.25);   color: #34d399; }

/* ── Toolbar / search ── */
.toolbar { padding: 0 14px 10px; }
.search-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 11px;
  padding: 0 12px;
  height: 40px;
}
.search-icon { font-size: 14px; flex-shrink: 0; }
.search-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 14px;
  caret-color: var(--accent-from);
}
.search-input::placeholder { color: var(--text-muted); }

/* ── Filter pills ── */
.filter-row {
  display: flex;
  gap: 6px;
  padding: 0 14px 12px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  flex-wrap: nowrap;
}
.filter-row::-webkit-scrollbar { display: none; }

.filter-pill {
  padding: 5px 13px;
  border-radius: 20px;
  border: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-sec);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.18s;
}
.filter-pill.active {
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 2px 8px rgba(99,102,241,0.3);
}

/* ── RSI Grid ── */
.rsi-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 0 14px 12px;
}
@media (min-width: 480px) {
  .rsi-grid { grid-template-columns: 1fr 1fr 1fr; }
}

.rsi-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  padding: 12px;
  box-shadow: var(--shadow-card);
  transition: border-color 0.2s;
}
.rsi-card.rsi-oversold   { border-color: rgba(239,68,68,0.4); }
.rsi-card.rsi-overbought { border-color: rgba(16,185,129,0.4); }

.rsi-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 3px;
}
.rsi-coin {
  font-size: 14px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: 0.01em;
}
.rsi-val {
  font-size: 20px;
  font-weight: 900;
  line-height: 1;
}
.mono { font-family: 'SF Mono', 'Fira Code', ui-monospace, monospace; }

.rsi-price {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.rsi-bar-wrap {
  height: 5px;
  background: var(--bg-elevated);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 6px;
}
.rsi-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}

.rsi-zone-label {
  font-size: 10px;
  font-weight: 700;
  text-align: right;
  letter-spacing: 0.04em;
}

/* ── Empty ── */
.empty-tip {
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
  padding: 60px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.empty-icon { font-size: 32px; }
</style>
