<template>
  <div class="login-page">
    <div class="login-header">
      <div class="logo">📊</div>
      <h1>RSI Bot</h1>
      <p>量化马丁交易系统</p>
    </div>

    <van-tabs v-model:active="tab" color="#3b82f6" title-inactive-color="#94a3b8" title-active-color="#3b82f6" background="#1e293b">
      <van-tab title="登录">
        <div class="form-box">
          <van-field v-model="loginForm.username" label="用户名" placeholder="请输入用户名" :border="false" />
          <van-field v-model="loginForm.password" label="密码" type="password" placeholder="请输入密码" :border="false" />
          <van-button block type="primary" :loading="loading" @click="doLogin" class="submit-btn">登录</van-button>
        </div>
      </van-tab>
      <van-tab title="注册">
        <div class="form-box">
          <van-field v-model="regForm.username"  label="用户名" placeholder="请输入用户名" :border="false" />
          <van-field v-model="regForm.email"     label="邮箱"   placeholder="请输入邮箱" :border="false" />
          <van-field v-model="regForm.password"  label="密码"   type="password" placeholder="至少6位" :border="false" />
          <van-button block type="primary" :loading="loading" @click="doRegister" class="submit-btn">注册</van-button>
        </div>
      </van-tab>
    </van-tabs>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { useAuthStore } from '../stores/auth'
import { register } from '../api/auth'

const router  = useRouter()
const auth    = useAuthStore()
const tab     = ref(0)
const loading = ref(false)

const loginForm = reactive({ username: '', password: '' })
const regForm   = reactive({ username: '', email: '', password: '' })

async function doLogin() {
  if (!loginForm.username || !loginForm.password) { showToast('请填写完整'); return }
  loading.value = true
  const ok = await auth.login(loginForm)
  loading.value = false
  if (ok) { router.push('/') } else { showToast('用户名或密码错误') }
}

async function doRegister() {
  if (!regForm.username || !regForm.email || !regForm.password) { showToast('请填写完整'); return }
  loading.value = true
  const res = await register(regForm)
  loading.value = false
  if (res?.id) {
    showToast('注册成功，请登录')
    tab.value = 0
    loginForm.username = regForm.username
    loginForm.password = regForm.password
  } else {
    showToast(res?.detail || '注册失败')
  }
}
</script>

<style scoped>
.login-page  { min-height: 100vh; background: #0f172a; padding-top: 60px; }
.login-header { text-align: center; margin-bottom: 40px; }
.logo  { font-size: 56px; margin-bottom: 12px; }
h1     { font-size: 24px; font-weight: 700; color: #e2e8f0; }
p      { color: #94a3b8; margin-top: 6px; }
.form-box { padding: 24px 20px; display: flex; flex-direction: column; gap: 12px; }
.van-field { border-radius: 8px; margin-bottom: 4px; }
.submit-btn { margin-top: 12px; border-radius: 8px; height: 48px; background: #3b82f6; border: none; font-size: 16px; }
</style>
