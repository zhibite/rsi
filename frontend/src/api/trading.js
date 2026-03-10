import { get, post, put, del } from './client'

// Bot
export const botStatus = ()  => get('/api/trading/bot/status')
export const startBot  = ()  => post('/api/trading/bot/start')
export const stopBot   = ()  => post('/api/trading/bot/stop')
export const getBalance = () => get('/api/trading/balance')

// Positions
export const getPositions = ()        => get('/api/trading/positions')
export const getHistory   = (p = 0)   => get(`/api/trading/positions/history?limit=50&offset=${p * 50}`)
export const getOrders    = (params)  => get('/api/trading/orders?' + new URLSearchParams(params).toString())
export const manualSell   = (id, pct) => post(`/api/trading/positions/${id}/manual-sell`, { pct })
export const manualBuy    = (id, amt) => post(`/api/trading/positions/${id}/manual-buy`, { amount_usdt: amt })

// Strategy
export const getStrategy    = ()     => get('/api/trading/strategy')
export const updateStrategy = (body) => put('/api/trading/strategy', body)

// Pairs
export const getPairs       = ()       => get('/api/trading/pairs')
export const createPair     = (body)   => post('/api/trading/pairs', body)
export const updatePair     = (id, b)  => put(`/api/trading/pairs/${id}`, b)
export const deletePair     = (id)     => del(`/api/trading/pairs/${id}`)
export const syncPrecision  = ()       => post('/api/trading/pairs/sync-precision')
export const batchAddTop    = (n = 50) => post(`/api/trading/pairs/batch-add-top?top_n=${n}`)

// API Config
export const getApiConfigs  = ()       => get('/api/trading/api-config')
export const createApiCfg   = (body)   => post('/api/trading/api-config', body)
export const updateApiCfg   = (id, b)  => put(`/api/trading/api-config/${id}`, b)
export const deleteApiCfg   = (id)     => del(`/api/trading/api-config/${id}`)

// Logs
export const getLogs = (limit = 100) => get(`/api/trading/logs?limit=${limit}`)
