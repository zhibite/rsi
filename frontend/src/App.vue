<template>
  <div class="app-container">
    <router-view v-if="isLogin" />
    <template v-else>
      <div class="page-content">
        <router-view />
      </div>
      <van-tabbar v-model="active" route fixed safe-area-inset-bottom active-color="#3b82f6" inactive-color="#4a6080">
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
:root {
  --bg-deepest:    #080e1a;
  --bg-page:       #0d1424;
  --bg-card:       #111827;
  --bg-elevated:   #1a2540;
  --border-subtle: #1e2d45;
  --border-vis:    #253352;
  --accent-from:   #3b82f6;
  --accent-to:     #6366f1;
  --accent-grad:   linear-gradient(135deg, #3b82f6, #6366f1);
  --success:       #10b981;
  --danger:        #ef4444;
  --warning:       #f59e0b;
  --text-primary:  #f0f4ff;
  --text-sec:      #8899b4;
  --text-muted:    #4a6080;
  --radius-card:   14px;
  --shadow-card:   0 2px 12px rgba(0,0,0,0.3);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg-page);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  -webkit-tap-highlight-color: transparent;
  overscroll-behavior: none;
}

.app-container { min-height: 100vh; display: flex; flex-direction: column; background: var(--bg-page); }
.page-content  { flex: 1; overflow-y: auto; padding-bottom: 70px; }

/* ── Tabbar ── */
.van-tabbar {
  height: 58px !important;
  background: var(--bg-card) !important;
  border-top: 1px solid var(--border-subtle) !important;
  box-shadow: 0 -4px 24px rgba(0,0,0,0.45) !important;
}
.van-tabbar-item {
  font-size: 11px !important;
  color: var(--text-muted) !important;
  position: relative !important;
}
.van-tabbar-item--active {
  color: var(--accent-from) !important;
}
.van-tabbar-item__icon {
  font-size: 22px !important;
  margin-bottom: 3px !important;
}
.van-tabbar-item--active::before {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 30px;
  height: 2px;
  border-radius: 0 0 3px 3px;
  background: linear-gradient(90deg, var(--accent-from), var(--accent-to));
}

/* ── Nav Bar ── */
.van-nav-bar {
  background: var(--bg-card) !important;
  border-bottom: 1px solid var(--border-subtle) !important;
  height: 52px !important;
}
.van-nav-bar__title {
  color: var(--text-primary) !important;
  font-size: 16px !important;
  font-weight: 700 !important;
}
.van-nav-bar__text { color: var(--accent-from) !important; }
.van-nav-bar .van-icon { color: var(--text-sec) !important; }

/* ── Cells & Fields ── */
.van-cell {
  background: var(--bg-card) !important;
  color: var(--text-primary) !important;
}
.van-cell__label  { color: var(--text-muted) !important; }
.van-cell::after  { border-color: var(--border-subtle) !important; }

.van-field { background: var(--bg-card) !important; }
.van-field__control {
  color: var(--text-primary) !important;
  background: transparent !important;
  caret-color: var(--accent-from);
}
.van-field__control::placeholder { color: var(--text-muted) !important; }
.van-field__label { color: var(--text-sec) !important; }

/* ── Popup / Dialog ── */
.van-popup { background: var(--bg-elevated) !important; }
.van-dialog {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-vis) !important;
  border-radius: var(--radius-card) !important;
}
.van-dialog__header {
  color: var(--text-primary) !important;
  font-weight: 700 !important;
  padding-top: 20px !important;
}
.van-dialog__confirm { color: var(--accent-from) !important; font-weight: 700 !important; }
.van-dialog__cancel  { color: var(--text-sec) !important; }
.van-hair-line--top::after { border-color: var(--border-subtle) !important; }

/* ── Tabs ── */
.van-tab        { color: var(--text-sec) !important; }
.van-tab--active { color: var(--accent-from) !important; }
.van-tabs__line  { background: linear-gradient(90deg, var(--accent-from), var(--accent-to)) !important; }
.van-tabs__nav   { background: var(--bg-card) !important; }
.van-tabs__wrap  { border-bottom: 1px solid var(--border-subtle) !important; }

/* ── Action Sheet ── */
.van-action-sheet {
  background: var(--bg-elevated) !important;
  border-radius: 20px 20px 0 0 !important;
}
.van-action-sheet__header {
  color: var(--text-primary) !important;
  font-weight: 700 !important;
  border-bottom: 1px solid var(--border-subtle) !important;
}
.van-action-sheet__item  { color: var(--text-primary) !important; background: transparent !important; }
.van-action-sheet__cancel { color: var(--text-sec) !important; background: var(--bg-card) !important; margin-top: 6px !important; }
.van-action-sheet__gap   { background: var(--border-subtle) !important; }

/* ── Dropdown ── */
.van-dropdown-menu__bar  { background: transparent !important; box-shadow: none !important; }
.van-dropdown-menu__title { color: var(--text-sec) !important; font-size: 13px !important; }
.van-dropdown-item__content { background: var(--bg-elevated) !important; }
.van-cell.van-dropdown-item__option { background: var(--bg-elevated) !important; }
.van-dropdown-item__option--active .van-cell__title { color: var(--accent-from) !important; }

/* ── Pull Refresh & List ── */
.van-pull-refresh { background: transparent !important; }
.van-list__finished-text { color: var(--text-muted) !important; font-size: 12px !important; }
.van-list__loading { color: var(--text-muted) !important; }

/* ── Radio ── */
.van-radio__label { color: var(--text-primary) !important; }
.van-radio__icon--checked .van-icon {
  background: var(--accent-from) !important;
  border-color: var(--accent-from) !important;
}

/* ── Search ── */
.van-search { background: transparent !important; padding: 0 !important; }
.van-search__content {
  background: var(--bg-elevated) !important;
  border-radius: 10px !important;
  border: 1px solid var(--border-subtle) !important;
}
.van-search__content .van-field__control { color: var(--text-primary) !important; }
.van-field__left-icon .van-icon { color: var(--text-muted) !important; }

/* ── Utility ── */
.green { color: var(--success) !important; }
.red   { color: var(--danger) !important; }
</style>
