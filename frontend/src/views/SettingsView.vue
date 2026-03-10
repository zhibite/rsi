<template>
  <div class="settings">
    <van-nav-bar title="配置" />
    <van-tabs v-model:active="tab" sticky>
      <van-tab title="API密钥">
        <div class="tab-body">
          <div v-for="cfg in apiConfigs" :key="cfg.id" class="cfg-card">
            <div class="cfg-row">
              <span class="cfg-label">{{ cfg.label }}</span>
              <van-tag :type="cfg.is_active ? 'success' : 'default'" size="small">{{ cfg.is_active ? '已激活' : '未激活' }}</van-tag>
              <van-tag :type="cfg.is_test_mode ? 'warning' : 'danger'" size="small" style="margin-left:4px">{{ cfg.is_test_mode ? '模拟' : '实盘' }}</van-tag>
            </div>
            <div class="cfg-key">{{ cfg.api_key.slice(0, 8) }}****</div>
            <div class="cfg-actions">
              <van-button v-if="!cfg.is_active" size="mini" type="primary" @click="activateCfg(cfg.id)">激活</van-button>
              <van-button size="mini" type="danger" plain @click="deleteCfg(cfg.id)" style="margin-left:8px">删除</van-button>
            </div>
          </div>
          <van-button block type="primary" plain @click="showAddApi = true" style="margin-top:12px">+ 添加 API 配置</van-button>

          <van-dialog v-model:show="showAddApi" title="添加 API" :before-close="onAddApi" show-cancel-button>
            <div class="dialog-form">
              <van-field v-model="apiForm.label" label="标签" placeholder="如 Main" :border="false" />
              <van-field v-model="apiForm.api_key" label="API Key" placeholder="" :border="false" />
              <van-field v-model="apiForm.api_secret" label="Secret" type="password" placeholder="" :border="false" />
              <van-field v-model="apiForm.api_passphrase" label="Passphrase" type="password" placeholder="" :border="false" />
              <van-cell title="交易模式">
                <template #right-icon>
                  <van-switch v-model="apiForm.is_test_mode" size="20px" />
                </template>
                <template #label>{{ apiForm.is_test_mode ? '模拟盘' : '实盘' }}</template>
              </van-cell>
            </div>
          </van-dialog>
        </div>
      </van-tab>

      <van-tab title="交易对">
        <div class="tab-body">
          <div class="pair-toolbar">
            <van-button size="small" type="primary" @click="addTopPairs" :loading="addingTop">批量 TOP50</van-button>
            <van-button size="small" plain @click="syncPrec" :loading="syncing" style="margin-left:8px">同步精度</van-button>
            <van-button size="small" plain @click="showAddPair = true" style="margin-left:8px">+ 添加</van-button>
          </div>
          <div v-for="p in pairs" :key="p.id" class="pair-row">
            <span class="pair-sym">{{ p.symbol }}</span>
            <span class="pair-meta">首单:{{ p.first_order_amount }}U M{{ p.max_martin_levels }}</span>
            <van-switch :model-value="p.is_enabled" @update:model-value="togglePair(p)" size="18px" />
            <van-button size="mini" icon="delete-o" plain type="danger" @click="doDeletePair(p.id)" style="margin-left:6px" />
          </div>
          <div v-if="pairs.length === 0" class="empty-tip">暂无交易对</div>

          <van-dialog v-model:show="showAddPair" title="添加交易对" :before-close="onAddPair" show-cancel-button>
            <div class="dialog-form">
              <van-field v-model="pairForm.symbol" label="交易对" placeholder="如 BTC/USDT" :border="false" />
            </div>
          </van-dialog>
        </div>
      </van-tab>

      <van-tab title="策略">
        <div class="tab-body">
          <div class="section-title">RSI 参数</div>
          <div class="field-grid">
            <div class="field-item">
              <div class="field-label">RSI 超卖阈值</div>
              <input class="field-input" v-model.number="strat.rsi_oversold" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">RSI 超买阈值</div>
              <input class="field-input" v-model.number="strat.rsi_overbought" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">RSI 周期</div>
              <input class="field-input" v-model.number="strat.rsi_period" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">扫描间隔 (秒)</div>
              <input class="field-input" v-model.number="strat.scan_interval" type="number" />
            </div>
          </div>

          <div class="section-title">马丁策略</div>
          <div class="field-grid">
            <div class="field-item">
              <div class="field-label">最大持仓数</div>
              <input class="field-input" v-model.number="strat.max_open_positions" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">首单金额 (U)</div>
              <input class="field-input" v-model.number="strat.first_order_amount" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">马丁倍数</div>
              <input class="field-input" v-model.number="strat.martin_multiplier" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">最大补仓层数</div>
              <input class="field-input" v-model.number="strat.max_martin_levels" type="number" />
            </div>
          </div>

          <div class="section-title">止盈止损</div>
          <div class="field-grid">
            <div class="field-item">
              <div class="field-label">止盈启动 (%)</div>
              <input class="field-input" v-model.number="strat.take_profit_pct" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">追踪回撤 (%)</div>
              <input class="field-input" v-model.number="strat.trailing_stop_pct" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">补仓回撤 (%)</div>
              <input class="field-input" v-model.number="strat.replenishment_retracement_pct" type="number" />
            </div>
          </div>

          <div class="section-title">超买止盈</div>
          <div class="field-grid">
            <div class="field-item">
              <div class="field-label">超买 RSI 步长</div>
              <input class="field-input" v-model.number="strat.overbought_rsi_step" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">最低利润 (%)</div>
              <input class="field-input" v-model.number="strat.overbought_min_profit_pct" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">利润步长 (%)</div>
              <input class="field-input" v-model.number="strat.overbought_profit_step" type="number" />
            </div>
          </div>

          <div class="save-row">
            <van-button block type="primary" :loading="savingStrat" @click="saveStrat" class="save-btn">保存策略</van-button>
          </div>
        </div>
      </van-tab>

      <van-tab title="风控">
        <div class="tab-body">
          <div class="section-title">止损保护</div>
          <div class="field-grid">
            <div class="field-item">
              <div class="field-label">硬止损浮亏 (%)<span class="field-hint">0=关闭</span></div>
              <input class="field-input" v-model.number="strat.max_loss_pct" type="number" placeholder="0" />
            </div>
            <div class="field-item">
              <div class="field-label">补仓冷却 (秒)<span class="field-hint">0=关闭</span></div>
              <input class="field-input" v-model.number="strat.martin_cooldown_seconds" type="number" placeholder="0" />
            </div>
          </div>

          <div class="section-title">BTC 熔断</div>
          <div class="field-grid">
            <div class="field-item">
              <div class="field-label">熔断跌幅 (%)<span class="field-hint">0=关闭</span></div>
              <input class="field-input" v-model.number="strat.btc_drop_pct" type="number" placeholder="0" />
            </div>
            <div class="field-item">
              <div class="field-label">监测窗口 (分钟)</div>
              <input class="field-input" v-model.number="strat.btc_drop_minutes" type="number" />
            </div>
            <div class="field-item">
              <div class="field-label">暂停时长 (分钟)</div>
              <input class="field-input" v-model.number="strat.btc_pause_minutes" type="number" />
            </div>
          </div>

          <div class="save-row">
            <van-button block type="primary" :loading="savingStrat" @click="saveStrat" class="save-btn">保存风控</van-button>
          </div>
          <div class="risk-note">硬止损和 BTC 熔断实时生效，无需重启 Bot。熔断期间已有持仓正常管理，仅暂停新开仓。</div>
        </div>
      </van-tab>
    </van-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import { getApiConfigs, createApiCfg, updateApiCfg, deleteApiCfg, getPairs, createPair, updatePair, deletePair, syncPrecision, batchAddTop, getStrategy, updateStrategy } from '../api/trading'

const tab = ref(0)

// API Config
const apiConfigs = ref([])
const showAddApi = ref(false)
const apiForm = reactive({ label: 'Main', api_key: '', api_secret: '', api_passphrase: '', is_test_mode: true })

async function loadApiConfigs() { const r = await getApiConfigs(); if (r) apiConfigs.value = r }
async function activateCfg(id) { await updateApiCfg(id, { is_active: true }); await loadApiConfigs() }
async function deleteCfg(id) {
  await showConfirmDialog({ title: '确认删除？' })
  await deleteApiCfg(id); await loadApiConfigs()
}
async function onAddApi(action) {
  if (action !== 'confirm') return true
  const res = await createApiCfg({ ...apiForm })
  if (res?.id) { showToast('添加成功'); await loadApiConfigs() }
  return true
}

// Pairs
const pairs = ref([])
const showAddPair = ref(false)
const pairForm = reactive({ symbol: '' })
const addingTop = ref(false)
const syncing   = ref(false)

async function loadPairs() { const r = await getPairs(); if (r) pairs.value = r }
async function togglePair(p) { await updatePair(p.id, { is_enabled: !p.is_enabled }); await loadPairs() }
async function doDeletePair(id) {
  await showConfirmDialog({ title: '确认删除？' })
  await deletePair(id); await loadPairs()
}
async function onAddPair(action) {
  if (action !== 'confirm') return true
  const res = await createPair({ symbol: pairForm.symbol.toUpperCase() })
  if (res?.id) { showToast('添加成功'); pairForm.symbol = ''; await loadPairs() }
  return true
}
async function addTopPairs() {
  addingTop.value = true
  const res = await batchAddTop(50)
  addingTop.value = false
  if (res) { showToast(`已添加 ${res.added} 个，跳过 ${res.skipped} 个`); await loadPairs() }
}
async function syncPrec() {
  syncing.value = true
  const res = await syncPrecision()
  syncing.value = false
  if (res) showToast(`已同步 ${res.updated} 个交易对精度`)
}

// Strategy
const strat = reactive({})
const savingStrat = ref(false)
async function loadStrat() {
  const r = await getStrategy()
  if (r) Object.assign(strat, r)
}
async function saveStrat() {
  savingStrat.value = true
  const res = await updateStrategy({ ...strat, pairs: [] })
  savingStrat.value = false
  if (res?.id) showToast('保存成功')
  else showToast('保存失败')
}

onMounted(async () => {
  await Promise.all([loadApiConfigs(), loadPairs(), loadStrat()])
})
</script>

<style scoped>
.settings { background: #0f172a; min-height: 100vh; }
.tab-body { padding: 14px; }

/* section 标题 */
.section-title {
  font-size: 12px;
  font-weight: 600;
  color: #38bdf8;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin: 18px 0 10px;
  padding-left: 2px;
}
.section-title:first-child { margin-top: 4px; }

/* 两列网格表单 */
.field-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.field-item {
  background: #1e293b;
  border-radius: 10px;
  padding: 10px 12px 12px;
}
.field-label {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.field-hint {
  font-size: 10px;
  color: #475569;
  background: #0f172a;
  border-radius: 4px;
  padding: 1px 4px;
}
.field-input {
  width: 100%;
  box-sizing: border-box;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #e2e8f0;
  font-size: 16px;
  font-weight: 600;
  padding: 6px 8px;
  outline: none;
  -webkit-appearance: none;
}
.field-input:focus { border-color: #38bdf8; }

/* API 配置卡片 */
.cfg-card { background: #1e293b; border-radius: 10px; padding: 14px; margin-bottom: 10px; }
.cfg-row  { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.cfg-label { font-size: 14px; font-weight: 700; color: #e2e8f0; flex: 1; }
.cfg-key   { font-size: 12px; color: #64748b; margin-bottom: 8px; font-family: monospace; }
.cfg-actions { display: flex; }

/* 交易对 */
.pair-toolbar { display: flex; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.pair-row { display: flex; align-items: center; padding: 10px 0; border-bottom: 1px solid #1e293b; gap: 8px; }
.pair-sym { font-size: 14px; color: #e2e8f0; flex: 1; }
.pair-meta { font-size: 11px; color: #64748b; }

/* 保存按钮 */
.save-row { margin-top: 20px; }
.save-btn { border-radius: 10px; height: 48px; font-size: 16px; }

/* 风控说明 */
.risk-note { margin-top: 12px; font-size: 12px; color: #64748b; line-height: 1.6; padding: 10px 12px; background: #1e293b; border-radius: 8px; }

.empty-tip { text-align: center; color: #475569; padding: 40px; }
.dialog-form { padding: 12px 0; }
</style>
