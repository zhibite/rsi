import { get } from './client'

export const getSummary   = ()         => get('/api/stats/summary')
export const getDailyPnl  = (days = 30) => get(`/api/stats/daily-pnl?days=${days}`)
export const getSymbolPnl = ()          => get('/api/stats/symbol-pnl')
