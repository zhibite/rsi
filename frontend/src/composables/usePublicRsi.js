import { ref, onUnmounted } from 'vue'

export function usePublicRsi(onSnapshot) {
  const connected = ref(false)
  let ws = null
  let pingTimer = null
  let reconnectTimer = null

  function connect() {
    const token = localStorage.getItem('token')
    if (!token) return

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws/rsi?token=${token}`)

    ws.onopen = () => {
      connected.value = true
      pingTimer = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25000)
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'public_rsi_snapshot') onSnapshot(msg.items || [])
      } catch {}
    }

    ws.onclose = () => {
      connected.value = false
      clearInterval(pingTimer)
      reconnectTimer = setTimeout(connect, 5000)
    }

    ws.onerror = () => ws.close()
  }

  function disconnect() {
    clearInterval(pingTimer)
    clearTimeout(reconnectTimer)
    ws?.close()
  }

  onUnmounted(disconnect)

  return { connected, connect, disconnect }
}
