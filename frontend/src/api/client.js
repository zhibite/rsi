import router from '../router'

const BASE = import.meta.env.VITE_API_BASE || ''

export async function request(path, options = {}) {
  const token = localStorage.getItem('token')
  const res = await fetch(BASE + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (res.status === 401) {
    localStorage.removeItem('token')
    router.push('/login')
    return null
  }
  if (res.status === 204) return null
  return res.json()
}

export const get  = (path) => request(path)
export const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) })
export const put  = (path, body) => request(path, { method: 'PUT',  body: JSON.stringify(body) })
export const del  = (path)       => request(path, { method: 'DELETE' })
