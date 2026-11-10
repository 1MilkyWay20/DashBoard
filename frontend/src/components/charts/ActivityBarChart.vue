<template>
  <el-card shadow="never">
    <template #header>
      <div class="card-header">
        <div class="title-group">
          <span class="card-title">营销活动分析</span>
          <el-radio-group
            :model-value="platform"
            size="small"
            @change="$emit('update:platform', $event)"
          >
            <el-radio-button v-for="p in platforms" :key="p" :value="p">{{ p }}</el-radio-button>
          </el-radio-group>
        </div>
        <el-radio-group v-model="metric">
          <el-radio-button v-for="m in METRICS" :key="m.key" :value="m.key">
            {{ m.label }}
          </el-radio-button>
        </el-radio-group>
      </div>
    </template>
    <el-empty v-if="!data.length && !stores.length" description="暂无活动数据" :image-size="72" />
    <template v-else>
      <div class="scope-line">
        <span>{{ selectedStore || '全部门店' }}</span>
        <el-button v-if="selectedStore" link type="primary" @click="selectedStore = ''">
          查看全部门店
        </el-button>
      </div>
      <EChart :option="option" height="360px" />
      <el-table
        :data="pagedCategories"
        stripe
        border
        class="activity-table dv-resizable"
        :default-sort="{ prop: 'revenue', order: 'descending' }"
        @sort-change="(e) => onSort('category', e)"
      >
        <el-table-column prop="category" label="活动类型" min-width="140" sortable="custom" />
        <el-table-column prop="revenue" label="活动营业额" align="right" sortable="custom" min-width="140">
          <template #default="{ row }">{{ fmtMoney(row.revenue) }}</template>
        </el-table-column>
        <el-table-column prop="orders" label="活动订单数" align="right" sortable="custom" min-width="120">
          <template #default="{ row }">{{ fmtInt(row.orders) }}</template>
        </el-table-column>
        <el-table-column prop="merchant_spend" label="商家补贴金额" align="right" sortable="custom" min-width="150">
          <template #default="{ row }">{{ fmtMoney(row.merchant_spend) }}</template>
        </el-table-column>
        <el-table-column prop="roi" label="投入产出比" align="right" sortable="custom" min-width="120">
          <template #default="{ row }">{{ fmtDecimal(row.roi) }}</template>
        </el-table-column>
      </el-table>
      <div v-if="sortedCategories.length > PAGE_SIZE" class="pager">
        <el-pagination
          v-model:current-page="categoryPage"
          :page-size="PAGE_SIZE"
          :total="sortedCategories.length"
          layout="total, prev, pager, next"
          background
        />
      </div>

      <div class="store-title">门店活动</div>
      <el-table
        :data="pagedStores"
        stripe
        border
        highlight-current-row
        class="store-table dv-resizable"
        :row-class-name="storeRowClass"
        :default-sort="{ prop: 'revenue', order: 'descending' }"
        @row-click="onStoreClick"
        @sort-change="(e) => onSort('store', e)"
      >
        <el-table-column prop="store_name" label="门店" min-width="240" sortable="custom" show-overflow-tooltip />
        <el-table-column prop="revenue" label="活动营业额" align="right" sortable="custom" min-width="140">
          <template #default="{ row }">{{ fmtMoney(row.revenue) }}</template>
        </el-table-column>
        <el-table-column prop="orders" label="活动订单数" align="right" sortable="custom" min-width="120">
          <template #default="{ row }">{{ fmtInt(row.orders) }}</template>
        </el-table-column>
        <el-table-column prop="merchant_spend" label="商家补贴金额" align="right" sortable="custom" min-width="150">
          <template #default="{ row }">{{ fmtMoney(row.merchant_spend) }}</template>
        </el-table-column>
        <el-table-column prop="roi" label="投入产出比" align="right" sortable="custom" min-width="120">
          <template #default="{ row }">{{ fmtDecimal(row.roi) }}</template>
        </el-table-column>
      </el-table>
      <div v-if="sortedStores.length > PAGE_SIZE" class="pager">
        <el-pagination
          v-model:current-page="storePage"
          :page-size="PAGE_SIZE"
          :total="sortedStores.length"
          layout="total, prev, pager, next"
          background
        />
      </div>
    </template>
  </el-card>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import EChart from '../EChart.vue'
import { CHART_COLORS } from './chartBase'
import { axisMoney, fmtDecimal, fmtInt, fmtMoney } from '../../utils/format'

const METRICS = [
  { key: 'merchant_spend', label: '商家补贴金额', kind: 'money' },
  { key: 'revenue', label: '活动营业额', kind: 'money' },
  { key: 'orders', label: '活动订单数', kind: 'int' },
  { key: 'roi', label: '投入产出比', kind: 'ratio' },
]

const PAGE_SIZE = 6 // 活动类型表、门店表每页条数

const props = defineProps({
  /** [{ category, revenue, merchant_spend, orders, roi }, ...] */
  data: { type: Array, default: () => [] },
  /** [{ store_name, revenue, merchant_spend, orders, roi }, ...] */
  stores: { type: Array, default: () => [] },
  /** [{ store_name, category, revenue, merchant_spend, orders, roi }, ...] */
  storeCategories: { type: Array, default: () => [] },
  /** 本卡片自己的平台，不跟页面顶部平台筛选联动 */
  platform: { type: String, default: '美团' },
  platforms: { type: Array, default: () => ['美团', '饿了么', '京东'] },
})

defineEmits(['update:platform'])

const metric = ref('merchant_spend')
const categoryPage = ref(1)
const storePage = ref(1)
const categorySort = ref({ prop: 'revenue', order: 'descending' })
const storeSort = ref({ prop: 'revenue', order: 'descending' })
const selectedStore = ref('')

const categorySource = computed(() => {
  if (!selectedStore.value) return props.data
  return props.storeCategories.filter((r) => r.store_name === selectedStore.value)
})

const current = computed(() => METRICS.find((m) => m.key === metric.value) || METRICS[0])

const rows = computed(() =>
  [...categorySource.value].sort((a, b) => Number(b[current.value.key] ?? 0) - Number(a[current.value.key] ?? 0)),
)

function compareRows(a, b, prop, order) {
  const dir = order === 'ascending' ? 1 : -1
  if (prop === 'category' || prop === 'store_name') {
    return dir * String(a[prop] || '').localeCompare(String(b[prop] || ''), 'zh')
  }
  return dir * (Number(a[prop] ?? 0) - Number(b[prop] ?? 0))
}

function sortedOf(list, sort) {
  const { prop, order } = sort
  return [...list].sort((a, b) => compareRows(a, b, prop || 'revenue', order || 'descending'))
}

const sortedCategories = computed(() => sortedOf(categorySource.value, categorySort.value))
const sortedStores = computed(() => sortedOf(props.stores, storeSort.value))

const pagedCategories = computed(() => {
  const start = (categoryPage.value - 1) * PAGE_SIZE
  return sortedCategories.value.slice(start, start + PAGE_SIZE)
})
const pagedStores = computed(() => {
  const start = (storePage.value - 1) * PAGE_SIZE
  return sortedStores.value.slice(start, start + PAGE_SIZE)
})

function onStoreClick(row) {
  selectedStore.value = selectedStore.value === row.store_name ? '' : row.store_name
}

function storeRowClass({ row }) {
  return row.store_name === selectedStore.value ? 'is-active-row' : ''
}

function onSort(which, { prop, order }) {
  const target = which === 'store' ? storeSort : categorySort
  const page = which === 'store' ? storePage : categoryPage
  target.value = { prop: prop || 'revenue', order: order || 'descending' }
  page.value = 1
}

watch(
  () => props.data,
  () => {
    categoryPage.value = 1
    selectedStore.value = ''
  },
)
watch(selectedStore, () => {
  categoryPage.value = 1
})
watch(
  () => props.stores,
  () => {
    storePage.value = 1
  },
)

function formatValue(v, kind) {
  if (kind === 'int') return fmtInt(v)
  if (kind === 'ratio') return fmtDecimal(v)
  return fmtMoney(v)
}

function axisFormatter(v) {
  if (current.value.kind === 'int') return fmtInt(v)
  if (current.value.kind === 'ratio') return fmtDecimal(v)
  return axisMoney(v)
}

const option = computed(() => {
  const { key, label, kind } = current.value
  const list = rows.value
  return {
    color: CHART_COLORS,
    legend: { show: false },
    grid: { left: 8, right: 16, top: 16, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const p = params[0]
        if (!p) return ''
        return `${p.axisValue}<br/>${p.marker}${label}　<b>${formatValue(p.value, kind)}</b>`
      },
    },
    xAxis: {
      type: 'category',
      data: list.map((r) => r.category),
      axisTick: { show: false },
      axisLabel: { interval: 0, rotate: 28, fontSize: 12, color: '#64748b' },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: axisFormatter, fontSize: 12, color: '#64748b' },
      splitLine: { lineStyle: { type: 'dashed', color: '#e2e8f0' } },
    },
    series: [
      {
        name: label,
        type: 'bar',
        barMaxWidth: 36,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        data: list.map((r) => Number(r[key] ?? 0)),
      },
    ],
  }
})
</script>

<style scoped>
.card-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.title-group {
  display: flex;
  align-items: center;
  gap: 12px;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--dv-text);
}
.scope-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--dv-text-secondary);
}
.activity-table {
  margin-top: 16px;
}
.store-table :deep(.el-table__row) {
  cursor: pointer;
}
.store-table :deep(.is-active-row) > td {
  background: var(--dv-primary-soft) !important;
}
.store-title {
  margin: 18px 0 10px;
  font-size: 15px;
  font-weight: 600;
  color: var(--dv-text);
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
