<template>
  <div class="app-container">
    <router-view v-if="isLogin" />
    <template v-else>
      <div class="page-content">
        <router-view />
      </div>
      <van-tabbar v-model="active" route fixed safe-area-inset-bottom active-color="#3b82f6" inactive-color="#64748b">
        <van-tabbar-item to="/" icon="home-o">主页</van-tabbar-item>
        <van-tabbar-item to="/scan" icon="search">扫描</van-tabbar-item>
        <van-tabbar-item to="/trades" icon="records-o">记录</van-tabbar-item>
        <van-tabbar-item to="/stats" icon="chart-trending-o">统计</van-tabbar-item>
        <van-tabbar-item to="/settings" icon="setting-o">设置</van-tabbar-item>
      </van-tabbar>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'

const route  = useRoute()
const auth   = useAuthStore()
const active = ref(0)
const isLogin = computed(() => route.path === '/login')

onMounted(() => auth.fetchMe())
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0f172a;
  color: #e2e8f0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  -webkit-tap-highlight-color: transparent;
}
.app-container { min-height: 100vh; display: flex; flex-direction: column; }
.page-content  { flex: 1; overflow-y: auto; padding-bottom: 60px; }
.van-tabbar    { background: #1e293b !important; border-top: 1px solid #334155 !important; }
/* 全局 Vant 深色覆盖 */
.van-nav-bar   { background: #1e293b !important; }
.van-nav-bar__title, .van-nav-bar__text { color: #e2e8f0 !important; }
.van-cell      { background: #1e293b !important; color: #e2e8f0 !important; }
.van-cell__label { color: #94a3b8 !important; }
.van-field__control { color: #e2e8f0 !important; background: transparent !important; }
.van-field     { background: #1e293b !important; }
.van-popup     { background: #1e293b !important; }
.van-tab       { color: #94a3b8 !important; }
.van-tab--active { color: #3b82f6 !important; }
.van-tabs__line { background: #3b82f6 !important; }
.van-tabs__nav { background: #1e293b !important; }
</style>
