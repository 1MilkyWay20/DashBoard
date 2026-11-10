<template>
  <el-card shadow="never">
    <template #header>
      <div class="trend-header">
        <span class="trend-title">趋势</span>
        <el-radio-group v-model="metric">
          <el-radio-button v-for="m in METRICS" :key="m.key" :value="m.key">
            {{ m.label }}
          </el-radio-button>
        </el-radio-group>
      </div>
    </template>
    <EChart :option="option" height="360px" />
  </el-card>
</template>

<script setup>
import { computed, ref } from 'vue'
import EChart from '../EChart.vue'
import { CHART_COLORS } from './chartBase'
import { axisMoney, axisPct, fmtInt, fmtMoney, fmtPct } from '../../utils/format'

const METRICS = [
  { key: 'revenue', label: '营业额', kind: 'money' },
  { key: 'orders', label: '订单数', kind: 'int' },
  { key: 'income', label: '收入', kind: 'money' },
  { key: 'income_rate', label: '实收率', kind: 'pct' },
  { key: 'subsidy_rate', label: '商补占比', kind: 'pct' },
  { key: 'commission_rate', label: '佣金占比', kind: 'pct' },
]

const props = defineProps({
  /** [{ date, revenue, orders, income, income_rate, subsidy_rate, commission_rate }, ...] */
  data: { type: Array, default: () => [] },
})

const metric = ref('revenue')

const current = computed(() => METRICS.find((m) => m.key === metric.value) || METRICS[0])

function formatValue(v, kind) {
  if (kind === 'pct') return fmtPct(v)
  if (kind === 'int') return fmtInt(v)
  return fmtMoney(v)
}

function axisFormatter(v) {
  if (current.value.kind === 'pct') return axisPct(v)
  if (current.value.kind === 'int') return fmtInt(v)
  return axisMoney(v)
}

const option = computed(() => {
  const { key, label, kind } = current.value
  return {
    color: CHART_COLORS,
    legend: { show: false },
    grid: { left: 8, right: 16, top: 16, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const p = params[0]
        return `${p.axisValueLabel || p.axisValue}<br/>${p.marker}${label}　<b>${formatValue(p.value, kind)}</b>`
      },
    },
    textStyle: { fontSize: 12, color: '#64748b' },
    xAxis: {
      type: 'category',
      data: props.data.map((r) => r.date.slice(5)),
      axisLabel: { hideOverlap: true, fontSize: 12 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
    },
    yAxis: {
      type: 'value',
      // 比率轴从 0 起，便于看占比变化幅度
      scale: kind !== 'pct',
      axisLabel: { formatter: axisFormatter, fontSize: 12 },
      splitLine: { lineStyle: { type: 'dashed', color: '#e2e8f0' } },
    },
    series: [
      {
        name: label,
        type: 'line',
        smooth: true,
        showSymbol: props.data.length <= 14,
        symbolSize: 6,
        lineStyle: { width: 2.5 },
        areaStyle: { opacity: 0.12 },
        emphasis: { focus: 'series' },
        data: props.data.map((r) => r[key] ?? 0),
      },
    ],
  }
})
</script>

<style scoped>
.trend-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.trend-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
</style>
