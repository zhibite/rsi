<template>
  <div class="trades">
    <van-nav-bar title="交易记录" />

    <div class="filters">
      <van-field v-model="symFilter" placeholder="搜索币种" clearable :border="false" class="filter-field" />
      <van-dropdown-menu active-color="#3b82f6">
        <van-dropdown-item v-model="sideFilter" :options="sideOptions" />
      </van-dropdown-menu>
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <van-list v-model:loading="loading" :finished="finished" finished-text="没有更多了" @load="loadMore">
        <div v-for="order in orders" :key="order.id" class="order-card">
          <div class="order-top">
            <span class="order-symbol">{{ order.symbol }}</span>
            <van-tag :type="order.side === 'buy' ? 'primary' : 'danger'" size="mini">{{ order.side === 'buy' ? '买入' : '卖出' }}</van-tag>
            <span v-if="order.realized_pnl != null" class="order-pnl" :class="order.realized_pnl >= 0 ? 'green' : 'red'">
              {{ order.realized_pnl >= 0 ? '+' : '' }}{{ order.realized_pnl.toFixed(4) }}
            </span>
          </div>
          <div class="order-row">
            <span>{{ order.price?.toFixed(6) }}</span>
            <span>{{ order.quantity?.toFixed(6) }}</span>
            <span>{{ order.amount_usdt?.toFixed(2) }} U</span>
          </div>
          <div class="order-row">
            <van-tag plain size="mini" type="default">{{ noteLabel(order.note) }}</van-tag>
            <span class="order-time">{{ fmtTime(order.timestamp) }}</span>
          </div>
        </div>
      </van-list>
    </van-pull-refresh>
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

const orders     = ref([])
const loading    = ref(false)
const finished   = ref(false)
const refreshing = ref(false)
let offset = 0

const noteMap = { seed: '首单', ladder_1: 'M1', ladder_2: 'M2', ladder_3: 'M3', ladder_4: 'M4', ladder_5: 'M5', trailing_stop: '追踪止盈', overbought_sell: '超买止盈', stop_loss: '止损', manual_sell: '手动卖' }
const noteLabel = (n) => noteMap[n] || n || '--'
const fmtTime   = (ts) => ts ? new Date(ts + 'Z').toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''

async function loadMore() {
  const params = { limit: 50, offset }
  if (symFilter.value) params.symbol = symFilter.value
  if (sideFilter.value !== 'all') params.side = sideFilter.value
  const res = await getOrders(params)
  if (!res || res.length === 0) { finished.value = true; loading.value = false; return }
  orders.value.push(...res)
  offset += 50
  if (res.length < 50) finished.value = true
  loading.value = false
}

async function onRefresh() {
  orders.value = []; offset = 0; finished.value = false
  await loadMore()
  refreshing.value = false
}

watch([symFilter, sideFilter], onRefresh)
onMounted(onRefresh)
</script>

<style scoped>
.trades  { background: #0f172a; min-height: 100vh; }
.filters { display: flex; align-items: center; padding: 8px 12px; gap: 8px; background: #1e293b; }
.filter-field { flex: 1; background: #0f172a; border-radius: 8px; }
.order-card { margin: 8px 12px 0; background: #1e293b; border-radius: 10px; padding: 12px; }
.order-top  { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.order-symbol { font-size: 14px; font-weight: 700; color: #e2e8f0; flex: 1; }
.order-pnl   { font-size: 14px; font-weight: 700; }
.green { color: #22c55e; } .red { color: #ef4444; }
.order-row  { display: flex; justify-content: space-between; font-size: 12px; color: #64748b; margin-top: 4px; }
.order-time { font-size: 11px; color: #475569; }
</style>
