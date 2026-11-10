<template>
  <el-card shadow="never">
    <template #header>
      <div class="card-header">
        <span>商品分析</span>
        <el-radio-group v-model="metric">
          <el-radio-button value="amount">销售额</el-radio-button>
          <el-radio-button value="qty">销量</el-radio-button>
        </el-radio-group>
      </div>
    </template>

    <el-row :gutter="16">
      <!-- 左侧：排行表 -->
      <el-col :md="8" :xs="24">
        <el-table
          :data="pagedData"
          stripe
          class="product-table"
          highlight-current-row
          :row-class-name="rowClassName"
          @row-click="onRowClick"
        >
          <el-table-column prop="name" label="商品名称" min-width="100" show-overflow-tooltip />
          <el-table-column :label="metricLabel" align="right" min-width="128">
            <template #default="{ row }">
              {{ metric === 'amount' ? fmtMoney(row.amount) : fmtInt(row.qty) }}
            </template>
          </el-table-column>
        </el-table>
        <div v-if="sortedData.length > PAGE_SIZE" class="pager">
          <el-pagination
            v-model:current-page="page"
            :page-size="PAGE_SIZE"
            :total="sortedData.length"
            layout="prev, pager, next"
            background
          />
        </div>
      </el-col>

      <!-- 右侧：搜索 + 日期 + 折线图 -->
      <el-col :md="16" :xs="24">
        <div class="trend-toolbar">
          <el-select
            v-model="productName"
            filterable
            clearable
            placeholder="搜索 / 选择商品"
            style="width: 240px"
          >
            <el-option v-for="n in productNames" :key="n" :label="n" :value="n" />
          </el-select>
          <el-date-picker
            v-model="chartRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            :clearable="false"
            style="width: 280px"
          />
        </div>
        <el-empty v-if="!productName" description="请选择或搜索商品查看趋势" :image-size="72" />
        <EChart v-else :option="chartOption" height="340px" />
      </el-col>
    </el-row>
  </el-card>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import EChart from '../EChart.vue'
import api from '../../api'
import { axisMoney, fmtInt, fmtMoney } from '../../utils/format'

const PAGE_SIZE = 10  // 商品排行每页条数

const props = defineProps({
  /** [{ name, amount, qty }, ...] */
  data: { type: Array, default: () => [] },
  /** 与看板一致的筛选上下文，用于拉商品趋势 */
  filterParams: { type: Object, default: () => ({}) },
  /** 看板当前日期，用作趋势图默认区间 */
  defaultStart: { type: String, default: '' },
  defaultEnd: { type: String, default: '' },
})

const page = ref(1)
const metric = ref('amount')  // amount=销售额 | qty=销量
const productName = ref('')
const chartRange = ref(null)
const trendRows = ref([])
const trendLoading = ref(false)

const metricLabel = computed(() => (metric.value === 'amount' ? '销售额' : '销量'))

const sortedData = computed(() => {
  const key = metric.value
  return [...props.data].sort((a, b) => Number(b[key] ?? 0) - Number(a[key] ?? 0))
})

const pagedData = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return sortedData.value.slice(start, start + PAGE_SIZE)
})

const productNames = computed(() => sortedData.value.map((r) => r.name).filter(Boolean))

function rowClassName({ row }) {
  return row.name === productName.value ? 'is-active-row' : ''
}

function onRowClick(row) {
  productName.value = row.name
}

function syncDefaultRange() {
  if (props.defaultStart && props.defaultEnd) {
    chartRange.value = [props.defaultStart, props.defaultEnd]
  }
}

async function loadTrend() {
  if (!productName.value || !chartRange.value?.[0] || !chartRange.value?.[1]) {
    trendRows.value = []
    return
  }
  if (!props.filterParams?.brand) return
  trendLoading.value = true
  try {
    trendRows.value = await api.get('/dashboard/product-trend', {
      params: {
        ...props.filterParams,
        start: chartRange.value[0],
        end: chartRange.value[1],
        name: productName.value,
      },
    })
  } finally {
    trendLoading.value = false
  }
}

const chartOption = computed(() => {
  const rows = trendRows.value
  const isAmount = metric.value === 'amount'
  const label = metricLabel.value
  return {
    legend: { show: false },
    grid: { left: 8, right: 16, top: 16, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const p = params[0]
        if (!p) return ''
        const text = isAmount ? fmtMoney(p.value) : fmtInt(p.value)
        return `${p.axisValueLabel || p.axisValue}<br/>${p.marker}${label}　<b>${text}</b>`
      },
    },
    xAxis: {
      type: 'category',
      data: rows.map((r) => r.date.slice(5)),
      axisLabel: { hideOverlap: true, fontSize: 13 },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: isAmount ? axisMoney : (v) => fmtInt(v), fontSize: 13 },
      splitLine: { lineStyle: { type: 'dashed' } },
    },
    series: [
      {
        name: label,
        type: 'line',
        smooth: true,
        showSymbol: rows.length <= 14,
        symbolSize: 6,
        lineStyle: { width: 2.5 },
        areaStyle: { opacity: 0.1 },
        data: rows.map((r) => (isAmount ? r.amount : r.qty)),
      },
    ],
  }
})

watch(metric, () => {
  page.value = 1
})

// 打开或筛选后：当前商品不在榜上时，默认选当前指标的第一名并画趋势
watch(
  () => props.data,
  (rows) => {
    page.value = 1
    const ranked = [...(rows || [])].sort(
      (a, b) => Number(b[metric.value] ?? 0) - Number(a[metric.value] ?? 0),
    )
    if (!ranked.length) {
      productName.value = ''
      return
    }
    if (!productName.value || !ranked.some((r) => r.name === productName.value)) {
      productName.value = ranked[0].name
    }
  },
  { immediate: true },
)

// 看板日期变化时同步趋势图默认区间
watch(
  () => [props.defaultStart, props.defaultEnd],
  () => {
    syncDefaultRange()
  },
  { immediate: true },
)

watch([productName, chartRange, () => props.filterParams], loadTrend, { deep: true, immediate: true })
</script>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 16px;
  font-weight: 600;
}
.product-table {
  font-size: 15px;
}
.product-table :deep(.el-table__header th) {
  font-size: 15px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.trend-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
:deep(.is-active-row) > td {
  background: var(--dv-primary-soft) !important;
}
</style>
