import { get, post } from './client'

export const login    = (body) => post('/api/auth/login', body)
export const register = (body) => post('/api/auth/register', body)
export const me       = ()     => get('/api/auth/me')
