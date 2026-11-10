<template>
  <el-card shadow="never" class="fill-card">
    <template #header>
      <div class="trend-header">
        <span class="trend-title">流量趋势</span>
        <el-radio-group v-model="metric">
          <el-radio-button v-for="m in METRICS" :key="m.key" :value="m.key">
            {{ m.label }}
          </el-radio-button>
        </el-radio-group>
      </div>
    </template>
    <EChart :option="option" height="100%" />
  </el-card>
</template>

<script setup>
import { computed, ref } from 'vue'
import EChart from '../EChart.vue'
import { CHART_BASE } from './chartBase'
import { axisPct, fmtInt, fmtPct } from '../../utils/format'

const METRICS = [
  { key: 'exposure', label: '曝光人数', kind: 'int' },
  { key: 'visitors', label: '入店人数', kind: 'int' },
  { key: 'orderers', label: '下单人数', kind: 'int' },
  { key: 'visit_rate', label: '入店转化率', kind: 'pct' },
  { key: 'order_rate', label: '下单转化率', kind: 'pct' },
]

const props = defineProps({
  /** [{ date, platform, exposure, visitors, orderers, visit_rate, order_rate }, ...] */
  data: { type: Array, default: () => [] },
})

const metric = ref('exposure') // 默认曝光人数

const current = computed(() => METRICS.find((m) => m.key === metric.value) || METRICS[0])

/** 日期轴（去重保序） */
const dates = computed(() => [...new Set(props.data.map((r) => r.date))])

/** 平台列表（去重保序） */
const platforms = computed(() => [...new Set(props.data.map((r) => r.platform || '未知'))])

function formatValue(v, kind) {
  return kind === 'pct' ? fmtPct(v) : fmtInt(v)
}

function axisFormatter(v) {
  return current.value.kind === 'pct' ? axisPct(v) : fmtInt(v)
}

const option = computed(() => {
  const { key, label, kind } = current.value
  const dateList = dates.value
  const plats = platforms.value
  // date -> platform -> row，便于按平台对齐日期轴
  const byDatePlat = new Map()
  for (const r of props.data) {
    byDatePlat.set(`${r.date}\0${r.platform || '未知'}`, r)
  }

  return {
    ...CHART_BASE,
    legend: {
      ...CHART_BASE.legend,
      data: plats,
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const lines = params.map(
          (p) =>
            `${p.marker}${p.seriesName}　<b>${formatValue(p.value, kind)}</b>`,
        )
        return `${params[0].axisValueLabel || params[0].axisValue}<br/>${label}<br/>${lines.join('<br/>')}`
      },
    },
    xAxis: {
      type: 'category',
      data: dateList.map((d) => d.slice(5)),
      axisLabel: { hideOverlap: true, fontSize: 13 },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: kind !== 'pct',
      min: kind === 'pct' ? 0 : undefined,
      axisLabel: { formatter: axisFormatter, fontSize: 13 },
      splitLine: { lineStyle: { type: 'dashed' } },
    },
    series: plats.map((plat) => ({
      name: plat,
      type: 'line',
      smooth: true,
      showSymbol: dateList.length <= 14,
      symbolSize: 6,
      lineStyle: { width: 2.5 },
      emphasis: { focus: 'series' },
      data: dateList.map((d) => {
        const row = byDatePlat.get(`${d}\0${plat}`)
        return row ? (row[key] ?? 0) : null
      }),
    })),
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
.fill-card {
  display: flex;
  flex-direction: column;
  width: 100%;
  /* 与商品分析卡片同高，固定高度避免图表重绘把容器越撑越高 */
  height: 590px;
  box-sizing: border-box;
}
.fill-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}
.fill-card :deep(.el-card__body > div) {
  flex: 1;
  height: auto !important;
  min-height: 0;
}
</style>
