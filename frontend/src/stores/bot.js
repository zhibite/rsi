import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '../api/trading'

export const useBotStore = defineStore('bot', () => {
  const running   = ref(false)
  const balance   = ref(null)
  const positions = ref([])
  const logs      = ref([])
  const rsi       = ref({})

  async function refresh() {
    const [status, pos, bal] = await Promise.all([
      api.botStatus(),
      api.getPositions(),
      api.getBalance(),
    ])
    if (status)  running.value   = status.running
    if (pos)     positions.value = pos
    if (bal)     balance.value   = bal.balance_usdt
  }

  async function loadLogs() {
    const data = await api.getLogs(100)
    if (data) logs.value = data
  }

  function applyWsMessage(msg) {
    if (msg.type === 'rsi_snapshot') {
      rsi.value = msg.data || {}
    } else if (msg.type === 'rsi_update') {
      rsi.value = { ...rsi.value, [msg.data.symbol]: msg.data.rsi }
    } else if (msg.type === 'position_opened') {
      refresh()
    } else if (msg.type === 'martin_buy') {
      refresh()
    } else if (msg.type === 'position_closed') {
      positions.value = positions.value.filter(p => p.symbol !== msg.data.symbol)
      running.value = running.value  // no-op, just keep ref
      refresh()
    } else if (msg.type === 'position_partial_sell') {
      refresh()
    }
  }

  return { running, balance, positions, logs, rsi, refresh, loadLogs, applyWsMessage }
})
