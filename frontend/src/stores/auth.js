import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as authApi from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user  = ref(null)

  async function fetchMe() {
    if (!token.value) return
    const data = await authApi.me()
    if (data) user.value = data
  }

  async function login(body) {
    const data = await authApi.login(body)
    if (data?.access_token) {
      token.value = data.access_token
      localStorage.setItem('token', data.access_token)
      await fetchMe()
      return true
    }
    return false
  }

  function logout() {
    token.value = ''
    user.value  = null
    localStorage.removeItem('token')
  }

  return { token, user, login, logout, fetchMe }
})
