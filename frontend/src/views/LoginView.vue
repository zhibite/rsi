<template>
  <div class="login-page">
    <!-- Background decoration -->
    <div class="bg-orb bg-orb-1"></div>
    <div class="bg-orb bg-orb-2"></div>

    <div class="login-inner">
      <!-- Logo block -->
      <div class="logo-block">
        <div class="logo-circle">
          <span class="logo-letter">B</span>
        </div>
        <div class="logo-text">
          <h1 class="brand">BQuant</h1>
          <p class="subtitle">RSI 马丁交易系统</p>
        </div>
      </div>

      <!-- Card -->
      <div class="auth-card">
        <!-- Custom tab switcher -->
        <div class="tab-switcher">
          <button :class="['tab-pill', tab === 0 && 'active']" @click="tab = 0">登录</button>
          <button :class="['tab-pill', tab === 1 && 'active']" @click="tab = 1">注册</button>
        </div>

        <!-- Login form -->
        <div v-if="tab === 0" class="form-body">
          <div class="field-wrap">
            <label class="field-label">用户名</label>
            <input
              v-model="loginForm.username"
              class="field-input"
              placeholder="请输入用户名"
              autocomplete="username"
            />
          </div>
          <div class="field-wrap">
            <label class="field-label">密码</label>
            <input
              v-model="loginForm.password"
              class="field-input"
              type="password"
              placeholder="请输入密码"
              autocomplete="current-password"
              @keyup.enter="doLogin"
            />
          </div>
          <button class="submit-btn" :class="{ loading }" @click="doLogin" :disabled="loading">
            <span v-if="!loading">登 录</span>
            <span v-else class="btn-spinner"></span>
          </button>
        </div>

        <!-- Register form -->
        <div v-if="tab === 1" class="form-body">
          <div class="field-wrap">
            <label class="field-label">用户名</label>
            <input
              v-model="regForm.username"
              class="field-input"
              placeholder="请输入用户名"
              autocomplete="username"
            />
          </div>
          <div class="field-wrap">
            <label class="field-label">邮箱</label>
            <input
              v-model="regForm.email"
              class="field-input"
              type="email"
              placeholder="请输入邮箱地址"
              autocomplete="email"
            />
          </div>
          <div class="field-wrap">
            <label class="field-label">密码</label>
            <input
              v-model="regForm.password"
              class="field-input"
              type="password"
              placeholder="至少 6 位"
              autocomplete="new-password"
              @keyup.enter="doRegister"
            />
          </div>
          <button class="submit-btn" :class="{ loading }" @click="doRegister" :disabled="loading">
            <span v-if="!loading">创建账户</span>
            <span v-else class="btn-spinner"></span>
          </button>
        </div>
      </div>

      <p class="footer-note">安全加密 · 数据隔离 · 实盘 / 模拟交易</p>
    </div>
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
/* ── Page ── */
.login-page {
  min-height: 100vh;
  background: radial-gradient(ellipse at 50% 0%, #0d1f3c 0%, #080e1a 65%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 20px;
  overflow: hidden;
  position: relative;
}

/* Background ambient orbs */
.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  pointer-events: none;
  opacity: 0.15;
}
.bg-orb-1 {
  width: 320px; height: 320px;
  background: #3b82f6;
  top: -80px; left: -80px;
}
.bg-orb-2 {
  width: 260px; height: 260px;
  background: #6366f1;
  bottom: -60px; right: -60px;
}

.login-inner {
  width: 100%;
  max-width: 390px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 32px;
  position: relative;
  z-index: 1;
}

/* ── Logo ── */
.logo-block {
  display: flex;
  align-items: center;
  gap: 16px;
}
.logo-circle {
  width: 60px;
  height: 60px;
  border-radius: 18px;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4);
  flex-shrink: 0;
}
.logo-letter {
  font-size: 28px;
  font-weight: 900;
  color: #fff;
  font-family: system-ui, sans-serif;
  line-height: 1;
}
.logo-text { display: flex; flex-direction: column; gap: 2px; }
.brand {
  font-size: 26px;
  font-weight: 800;
  background: linear-gradient(90deg, #f0f4ff, #a5b4fc);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1.1;
}
.subtitle {
  font-size: 12px;
  color: #8899b4;
  letter-spacing: 0.04em;
}

/* ── Auth Card ── */
.auth-card {
  width: 100%;
  background: #111827;
  border: 1px solid #1e2d45;
  border-radius: 20px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  overflow: hidden;
}

/* ── Tab switcher ── */
.tab-switcher {
  display: flex;
  padding: 16px 16px 0;
  gap: 8px;
  background: #111827;
}
.tab-pill {
  flex: 1;
  height: 40px;
  border-radius: 10px;
  border: 1px solid #1e2d45;
  background: transparent;
  color: #8899b4;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.tab-pill.active {
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 2px 12px rgba(99, 102, 241, 0.35);
}

/* ── Form body ── */
.form-body {
  padding: 20px 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  font-size: 12px;
  font-weight: 600;
  color: #8899b4;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}
.field-input {
  width: 100%;
  height: 48px;
  background: #1a2540;
  border: 1px solid #1e2d45;
  border-radius: 10px;
  color: #f0f4ff;
  font-size: 15px;
  padding: 0 14px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  -webkit-appearance: none;
}
.field-input::placeholder { color: #4a6080; }
.field-input:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.18);
}

/* ── Submit button ── */
.submit-btn {
  width: 100%;
  height: 50px;
  border-radius: 25px;
  border: none;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.06em;
  cursor: pointer;
  margin-top: 4px;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4);
  transition: opacity 0.2s, transform 0.1s;
  display: flex;
  align-items: center;
  justify-content: center;
}
.submit-btn:active { transform: scale(0.98); opacity: 0.9; }
.submit-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* Loading spinner inside button */
.btn-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Footer note ── */
.footer-note {
  font-size: 11px;
  color: #4a6080;
  text-align: center;
  letter-spacing: 0.04em;
}
</style>
