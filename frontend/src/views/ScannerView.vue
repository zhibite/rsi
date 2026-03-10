<template>
  <div class="scanner">
    <van-nav-bar title="RSI 扫描仪">
      <template #right>
        <van-badge :content="connected ? '' : '离线'" :color="connected ? '#22c55e' : '#ef4444'" />
      </template>
    </van-nav-bar>

    <div class="chips">
      <span class="chip red">超卖 {{ counts.oversold }}</span>
      <span class="chip orange">近超卖 {{ counts.nearOversold }}</span>
      <span class="chip gray">中性 {{ counts.neutral }}</span>
      <span class="chip green">超买 {{ counts.overbought }}</span>
    </div>

    <div class="toolbar">
      <van-search v-model="search" placeholder="搜索币种" background="#0f172a" />
      <div class="filter-btns">
        <button v-for="f in filters" :key="f.key" @click="activeFilter = f.key" :class="['filter-btn', activeFilter === f.key && 'active']">{{ f.label }}</button>
      </div>
    </div>

    <div class="rsi-grid">
      <div v-for="item in displayList" :key="item.symbol" class="rsi-item" :class="rsiClass(item.rsi)">
        <div class="rsi-symbol">{{ item.symbol.replace('/USDT', '') }}</div>
        <div class="rsi-value">{{ item.rsi.toFixed(1) }}</div>
        <div class="rsi-price">{{ item.price.toFixed(4) }}</div>
        <div class="rsi-bar-wrap"><div class="rsi-bar" :style="{ width: item.rsi + '%', background: rsiColor(item.rsi) }"></div></div>
      </div>
    </div>

    <div v-if="displayList.length === 0" class="empty-tip">{{ connected ? '加载中...' : '正在连接...' }}</div>
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
const rsiColor = (rsi) => rsi < 30 ? '#ef4444' : rsi > 70 ? '#22c55e' : '#3b82f6'

const { connected, connect } = usePublicRsi((snapshot) => { items.value = snapshot })
onMounted(connect)
</script>

<style scoped>
.scanner { background: #0f172a; min-height: 100vh; }
.chips { display: flex; gap: 8px; padding: 10px 12px; flex-wrap: wrap; }
.chip { font-size: 12px; padding: 4px 10px; border-radius: 20px; font-weight: 600; }
.chip.red    { background: #7f1d1d; color: #fca5a5; }
.chip.orange { background: #78350f; color: #fcd34d; }
.chip.gray   { background: #1e293b; color: #94a3b8; }
.chip.green  { background: #14532d; color: #86efac; }
.toolbar { padding: 0 12px 8px; }
.filter-btns { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.filter-btn { padding: 4px 12px; border-radius: 20px; border: 1px solid #334155; background: transparent; color: #94a3b8; font-size: 12px; cursor: pointer; }
.filter-btn.active { background: #3b82f6; border-color: #3b82f6; color: #fff; }
.rsi-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 0 12px 12px; }
.rsi-item { background: #1e293b; border-radius: 8px; padding: 10px; border: 1px solid #334155; }
.rsi-item.rsi-oversold   { border-color: #ef4444; }
.rsi-item.rsi-overbought { border-color: #22c55e; }
.rsi-symbol { font-size: 13px; font-weight: 700; color: #e2e8f0; }
.rsi-value  { font-size: 22px; font-weight: 800; color: #e2e8f0; margin: 2px 0; }
.rsi-price  { font-size: 11px; color: #64748b; margin-bottom: 6px; }
.rsi-bar-wrap { height: 3px; background: #334155; border-radius: 2px; overflow: hidden; }
.rsi-bar { height: 100%; border-radius: 2px; transition: width 0.3s; }
.empty-tip { text-align: center; color: #475569; padding: 60px 0; }
</style>
