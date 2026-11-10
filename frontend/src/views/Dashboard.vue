<template>
  <el-container class="layout">
    <AppSidebar />

    <el-container direction="vertical">
      <el-header class="dv-topbar" height="56px">
        <SidebarToggle />
        <span class="dv-topbar-title">销售看板</span>
        <el-button
          v-if="aiEnabled"
          type="primary"
          plain
          size="small"
          class="ai-entry"
          @click="aiOpen = true"
        >
          AI 分析
        </el-button>
        <span class="dv-username">{{ auth.user?.username }}</span>
        <el-button link type="danger" @click="logout">退出</el-button>
      </el-header>

      <AiChatPanel v-model="aiOpen" :filter-params="commonParams()" />

      <BrandFloatingToolbar
        v-if="isXj"
        :items="xjToolbarItems"
        @select="onXjToolbarSelect"
      />
      <QualificationFormDialog v-if="isXj" v-model="qualOpen" />

      <el-main ref="mainEl" class="main dv-panel">
        <!-- 筛选栏 -->
        <div class="filter-bar dv-toolbar">
          <el-radio-group v-model="rangeMode">
            <el-radio-button value="1d">昨天</el-radio-button>
            <el-radio-button value="7d">近 7 天</el-radio-button>
            <el-radio-button value="30d">近 30 天</el-radio-button>
            <el-radio-button value="custom">自定义</el-radio-button>
          </el-radio-group>
          <el-date-picker
            v-if="rangeMode === 'custom'"
            v-model="customRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            :clearable="false"
            style="width: 260px"
          />
          <el-radio-group v-model="selectedPlatform">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button v-for="p in platformOptions" :key="p" :value="p">
              {{ p }}
            </el-radio-button>
          </el-radio-group>
          <el-tree-select
            v-model="selectedStores"
            :data="storeTree"
            multiple
            show-checkbox
            check-strictly
            collapse-tags
            collapse-tags-tooltip
            clearable
            filterable
            placeholder="区域 / 门店（全部）"
            style="width: 300px"
            :render-after-expand="false"
          />
        </div>

        <KpiGrid :summary="summary" :loading="loading" />

        <el-row v-if="summary?.current" :gutter="14" class="chart-row">

          <el-col :span="24">
            <TrendChart :data="trendRows" />
          </el-col>
          <el-col :md="12" :xs="24">
            <PlatformChart :data="platformRows" />
          </el-col>
          <el-col :md="12" :xs="24">
            <MealPieChart :data="mealRows" />
          </el-col>
          <el-col :span="24">
            <ProductTopChart
              :data="productRows"
              :filter-params="productFilterParams"
              :default-start="startDate"
              :default-end="endDate"
            />
          </el-col>
          <!-- 流量分析：漏斗 + 按日趋势（多平台合并），放在商品分析下方 -->
          <el-col :md="10" :xs="24" class="stretch-col">
            <TrafficFunnelChart :data="funnelData" />
          </el-col>
          <el-col :md="14" :xs="24" class="stretch-col">
            <TrafficTrendChart :data="trafficTrendRows" />
          </el-col>
          <el-col v-if="isKp" :span="24">
            <ActivityBarChart
              v-model:platform="activityPlatform"
              :platforms="activityPlatformOptions"
              :data="activityRows"
              :stores="activityStores"
              :store-categories="activityStoreCategories"
            />
          </el-col>
          <el-col :span="24">
            <StoreRankTable :data="storeRows" />
          </el-col>
          <el-col v-if="isXj" :span="24" id="xj-abnormal-section">
            <AbnormalOrderTable
              v-model:platform="abnormalPlatform"
              :platforms="abnormalPlatformOptions"
              :data="abnormalData"
            />
          </el-col>
        </el-row>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppSidebar from '../components/AppSidebar.vue'
import SidebarToggle from '../components/SidebarToggle.vue'
import KpiGrid from '../components/charts/KpiGrid.vue'
import TrendChart from '../components/charts/TrendChart.vue'
import PlatformChart from '../components/charts/PlatformChart.vue'
import MealPieChart from '../components/charts/MealPieChart.vue'
import ProductTopChart from '../components/charts/ProductTopChart.vue'
import StoreRankTable from '../components/charts/StoreRankTable.vue'
import TrafficFunnelChart from '../components/charts/TrafficFunnelChart.vue'
import TrafficTrendChart from '../components/charts/TrafficTrendChart.vue'
import ActivityBarChart from '../components/charts/ActivityBarChart.vue'
import AbnormalOrderTable from '../components/charts/AbnormalOrderTable.vue'
import AiChatPanel from '../components/AiChatPanel.vue'
import BrandFloatingToolbar from '../components/BrandFloatingToolbar.vue'
import QualificationFormDialog from '../components/QualificationFormDialog.vue'
import { useAuthStore } from '../store/auth'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const platformOptions = ref([])
const storeTree = ref([]) // 机构树：区 → 战区/城市 → 门店
const nodeStores = ref({}) // 节点 value -> 下属门店 id 列表
const selectedPlatform = ref('') // 空字符串 = 全部平台
const abnormalPlatform = ref('美团') // 异常订单表自己的平台，默认美团
const activityPlatform = ref('美团') // 营销活动分析自己的平台，默认美团
const selectedStores = ref([]) // 树节点 value：n:机构id / s:门店名 / r:区域
const rangeMode = ref('7d')
const customRange = ref(null)
const loading = ref(true)
const aiOpen = ref(false)
const aiEnabled = ref(false)
const qualOpen = ref(false)
const mainEl = ref(null)

/** 品牌 xj 右侧浮动工具栏入口；后续可继续往里加小工具 */
const xjToolbarItems = computed(() => [
  { key: 'top', label: '回到顶部' },
  { key: 'ai', label: 'AI 分析', disabled: !aiEnabled.value },
  { key: 'abnormal', label: '异常订单' },
  { key: 'qualification', label: '更换资质' },
  { key: 'feedback', label: '意见反馈' },
])

function mainScrollEl() {
  const el = mainEl.value
  return el?.$el || el || null
}

function onXjToolbarSelect(item) {
  if (item.key === 'top') {
    mainScrollEl()?.scrollTo({ top: 0, behavior: 'smooth' })
    return
  }
  if (item.key === 'ai') {
    if (!aiEnabled.value) {
      ElMessage.info('AI 分析未开启')
      return
    }
    aiOpen.value = true
    return
  }
  if (item.key === 'abnormal') {
    document.getElementById('xj-abnormal-section')?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
    return
  }
  if (item.key === 'qualification') {
    qualOpen.value = true
    return
  }
  if (item.key === 'feedback') {
    ElMessageBox.prompt('欢迎留下使用建议，我们会认真看', '意见反馈', {
      confirmButtonText: '提交',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '例如：希望多一个某某图表…',
      inputValidator: (v) => !!(v && v.trim()) || '请填写内容',
    })
      .then(() => ElMessage.success('已收到，谢谢反馈'))
      .catch(() => {})
  }
}

const summary = ref(null)
const trendRows = ref([])
const platformRows = ref([])
const storeRows = ref([])
const mealRows = ref([])
const productRows = ref([])
const funnelData = ref(null)
const trafficTrendRows = ref([])
const activityRows = ref([])
const activityStores = ref([])
const activityStoreCategories = ref([])
const abnormalData = ref(null)

const isKp = computed(() => route.params.brand === 'kp')
const isXj = computed(() => route.params.brand === 'xj')
const abnormalPlatformOptions = computed(() => {
  const list = (platformOptions.value.length ? [...platformOptions.value] : ['美团', '饿了么'])
    .filter((p) => p !== '京东')
  if (!list.includes('美团')) list.unshift('美团')
  return list
})
const activityPlatformOptions = computed(() => {
  const list = platformOptions.value.length ? [...platformOptions.value] : ['美团', '饿了么', '京东']
  if (!list.includes('美团')) list.unshift('美团')
  return list
})

/** 把选中的区域/门店节点展开成门店 id，供接口 store_ids 参数 */
function resolveStoreIds() {
  const ids = new Set()
  for (const v of selectedStores.value) {
    for (const id of nodeStores.value[v] || []) ids.add(id)
  }
  return [...ids]
}

// 筛选联动时挡住连带触发，避免同一轮操作打两次接口
let syncingFilters = false
let platformSeq = 0
let optionsSeq = 0
let listSeq = 0
let activitySeq = 0
let abnormalSeq = 0

onMounted(async () => {
  const seq = ++optionsSeq
  const [platforms, stores] = await Promise.all([fetchPlatformOptions(), fetchStoreOptions()])
  if (seq !== optionsSeq) return
  platformOptions.value = platforms
  applyStoreOptions(stores)
  loadAll()
  api
    .get('/ai/status')
    .then((s) => {
      aiEnabled.value = !!s?.enabled
    })
    .catch(() => {
      aiEnabled.value = false
    })
})

function logout() {
  auth.logout()
  router.push('/login')
}

// ---------- 筛选参数 ----------
function fmtDay(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const startDate = computed(() => {
  if (rangeMode.value === 'custom') return customRange.value?.[0] || null
  const d = new Date()
  if (rangeMode.value === '1d') {
    d.setDate(d.getDate() - 1)
  } else {
    d.setDate(d.getDate() - (rangeMode.value === '7d' ? 6 : 29))
  }
  return fmtDay(d)
})
const endDate = computed(() => {
  if (rangeMode.value === 'custom') return customRange.value?.[1] || null
  if (rangeMode.value === '1d') {
    const d = new Date()
    d.setDate(d.getDate() - 1)
    return fmtDay(d)
  }
  return fmtDay(new Date())
})

/** 营销活动只吃本卡片平台，日期和门店仍跟页面筛选 */
function activityParams() {
  const storeIds = resolveStoreIds()
  return {
    brand: route.params.brand,
    start: startDate.value,
    end: endDate.value,
    platforms: activityPlatform.value || '美团',
    store_ids: storeIds.length ? storeIds.join(',') : undefined,
  }
}

/** 异常订单只吃本表平台，日期和门店仍跟页面筛选 */
function abnormalParams() {
  const storeIds = resolveStoreIds()
  return {
    brand: route.params.brand,
    start: startDate.value,
    end: endDate.value,
    platforms: abnormalPlatform.value || '美团',
    store_ids: storeIds.length ? storeIds.join(',') : undefined,
  }
}

function commonParams() {
  const storeIds = resolveStoreIds()
  return {
    brand: route.params.brand,
    start: startDate.value,
    end: endDate.value,
    platforms: selectedPlatform.value || undefined,
    store_ids: storeIds.length ? storeIds.join(',') : undefined,
  }
}

/** 商品趋势图自带日期，这里只传品牌/平台/门店 */
const productFilterParams = computed(() => {
  const p = commonParams()
  return {
    brand: p.brand,
    platforms: p.platforms,
    store_ids: p.store_ids,
  }
})

/** 趋势图：筛到单天时拉近 7 天（含当天），便于看变化 */
function trendParams() {
  const params = commonParams()
  if (params.start && params.end && params.start === params.end) {
    const d = new Date(`${params.end}T00:00:00`)
    d.setDate(d.getDate() - 6)
    params.start = fmtDay(d)
  }
  return params
}

// 切到自定义时若还没选过日期，默认填近 7 天，避免空白无数据
watch(rangeMode, (mode) => {
  if (mode === 'custom' && !customRange.value) {
    const end = new Date()
    const start = new Date()
    start.setDate(start.getDate() - 6)
    customRange.value = [fmtDay(start), fmtDay(end)]
  }
})

// 平台变化先刷新门店树并清掉失效节点，再只拉一次看板
watch(selectedPlatform, async () => {
  if (syncingFilters) return
  const seq = ++platformSeq
  const optSeq = ++optionsSeq
  syncingFilters = true
  try {
    const stores = await fetchStoreOptions()
    if (seq !== platformSeq || optSeq !== optionsSeq) return
    applyStoreOptions(stores)
    const valid = new Set(Object.keys(nodeStores.value))
    const next = selectedStores.value.filter((v) => valid.has(v))
    const changed =
      next.length !== selectedStores.value.length || next.some((v, i) => v !== selectedStores.value[i])
    if (changed) selectedStores.value = next
    await nextTick()
  } catch {
    // 门店树失败时仍按当前平台刷新看板
  } finally {
    if (seq === platformSeq) syncingFilters = false
  }
  if (seq === platformSeq) loadAll()
})

// 切品牌时重拉平台/门店选项，并清空已选，避免跨品牌残留
watch(
  () => route.params.brand,
  async () => {
    platformSeq += 1
    const optSeq = ++optionsSeq
    syncingFilters = true
    selectedPlatform.value = ''
    abnormalPlatform.value = '美团'
    activityPlatform.value = '美团'
    selectedStores.value = []
    await nextTick()
    syncingFilters = false
    const [platforms, stores] = await Promise.all([fetchPlatformOptions(), fetchStoreOptions()])
    if (optSeq !== optionsSeq) return
    platformOptions.value = platforms
    applyStoreOptions(stores)
    loadAll()
  },
)

watch([startDate, endDate], () => {
  if (syncingFilters) return
  loadAll()
})

watch(selectedStores, () => {
  if (syncingFilters) return
  loadAll()
})

function fetchPlatformOptions() {
  return api.get('/meta/platforms', {
    params: { brand: route.params.brand },
  })
}

function fetchStoreOptions() {
  return api.get('/meta/stores', {
    params: {
      brand: route.params.brand,
      platform: selectedPlatform.value || undefined,
    },
  })
}

function applyStoreOptions(data) {
  storeTree.value = data?.tree || []
  nodeStores.value = data?.node_stores || {}
}

async function loadAll() {
  if (!startDate.value || !endDate.value) return
  const seq = ++listSeq
  const aSeq = ++activitySeq
  const bSeq = ++abnormalSeq
  loading.value = true
  const params = commonParams()
  const trend = trendParams()
  try {
    const requests = [
      api.get('/dashboard/summary', { params }),
      api.get('/dashboard/trend', { params: trend }),
      api.get('/dashboard/by-platform', { params }),
      api.get('/dashboard/stores', { params }),
      api.get('/dashboard/meal-type', { params }),
      api.get('/dashboard/products', { params }),
      api.get('/dashboard/exposure-funnel', { params }),
      api.get('/dashboard/exposure-trend', { params: trend }),
    ]
    const jobs = [Promise.all(requests)]
    if (isKp.value) {
      jobs.push(fetchActivities(aSeq).catch(() => {
        if (aSeq === activitySeq) clearActivities()
      }))
    } else clearActivities()
    if (isXj.value) {
      jobs.push(fetchAbnormal(bSeq).catch(() => {
        if (bSeq === abnormalSeq) abnormalData.value = null
      }))
    } else abnormalData.value = null
    const [results] = await Promise.all(jobs)
    if (seq !== listSeq) return
    const [s, t, p, st, m, pr, funnel, traffic] = results
    summary.value = s
    trendRows.value = t
    platformRows.value = p
    storeRows.value = st
    mealRows.value = m
    productRows.value = pr
    funnelData.value = funnel
    trafficTrendRows.value = traffic
  } finally {
    if (seq === listSeq) loading.value = false
  }
}

function clearActivities() {
  activityRows.value = []
  activityStores.value = []
  activityStoreCategories.value = []
}

async function fetchActivities(seq) {
  if (!isKp.value || !startDate.value || !endDate.value) {
    if (seq === activitySeq) clearActivities()
    return
  }
  const data = await api.get('/dashboard/activities', { params: activityParams() })
  if (seq !== activitySeq) return
  activityRows.value = data?.categories || []
  activityStores.value = data?.stores || []
  activityStoreCategories.value = data?.store_categories || []
}

async function fetchAbnormal(seq) {
  if (!isXj.value || !startDate.value || !endDate.value) {
    if (seq === abnormalSeq) abnormalData.value = null
    return
  }
  const data = await api.get('/dashboard/abnormal-orders', { params: abnormalParams() })
  if (seq !== abnormalSeq) return
  abnormalData.value = data
}

watch(abnormalPlatform, () => {
  if (syncingFilters || !isXj.value) return
  const seq = ++abnormalSeq
  fetchAbnormal(seq).catch(() => {
    if (seq === abnormalSeq) abnormalData.value = null
  })
})

watch(activityPlatform, () => {
  if (syncingFilters || !isKp.value) return
  const seq = ++activitySeq
  fetchActivities(seq).catch(() => {
    if (seq === activitySeq) clearActivities()
  })
})
</script>

<style scoped>
.layout {
  height: 100vh;
  overflow: hidden;
  font-size: 14px;
  background: var(--dv-bg);
}
.main {
  padding: 18px 20px 24px;
  overflow-y: auto;
  background: var(--dv-bg);
}
.filter-bar {
  position: sticky;
  top: 0;
  z-index: 20;
  margin-bottom: 16px;
}
.main :deep(.el-radio-button__inner),
.main :deep(.el-input__inner),
.main :deep(.el-select__placeholder),
.main :deep(.el-select__selected-item),
.main :deep(.el-tag) {
  font-size: 13px;
}
.chart-row :deep(.el-col) {
  margin-bottom: 14px;
}
.chart-row :deep(.stretch-col) {
  display: flex;
}
.chart-row :deep(.stretch-col > *) {
  flex: 1;
  width: 100%;
  min-width: 0;
}
.ai-entry {
  margin-right: 4px;
}
</style>
