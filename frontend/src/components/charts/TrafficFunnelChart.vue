<template>
  <el-card shadow="never" class="fill-card">
    <template #header>
      <span class="card-title">转化漏斗</span>
    </template>
    <EChart :option="option" height="100%" />
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '../EChart.vue'
import { fmtInt, fmtPct } from '../../utils/format'

const props = defineProps({
  /** { exposure, visitors, orderers, visit_rate, order_rate } */
  data: { type: Object, default: null },
})

const STEPS = [
  { key: 'exposure', label: '曝光人数' },
  { key: 'visitors', label: '入店人数' },
  { key: 'orderers', label: '下单人数' },
]

const option = computed(() => {
  const d = props.data || {}
  const values = STEPS.map((s) => Number(d[s.key] ?? 0))
  const max = Math.max(...values, 1)

  return {
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        const idx = p.dataIndex
        const label = STEPS[idx].label
        const val = values[idx]
        let extra = ''
        if (idx === 1) extra = `<br/>入店转化率　<b>${fmtPct(d.visit_rate)}</b>`
        if (idx === 2) extra = `<br/>下单转化率　<b>${fmtPct(d.order_rate)}</b>`
        return `${p.marker}${label}　<b>${fmtInt(val)}</b>${extra}`
      },
    },
    series: [
      {
        type: 'funnel',
        left: '8%',
        right: '8%',
        top: 24,
        bottom: 24,
        min: 0,
        max,
        minSize: '18%',
        maxSize: '100%',
        sort: 'none', // 固定从上到下：曝光 → 入店 → 下单
        gap: 6,
        label: {
          show: true,
          position: 'inside',
          formatter: (p) => {
            const idx = p.dataIndex
            const lines = [`${STEPS[idx].label}`, fmtInt(values[idx])]
            if (idx === 1) lines.push(fmtPct(d.visit_rate))
            if (idx === 2) lines.push(fmtPct(d.order_rate))
            return lines.join('\n')
          },
          fontSize: 13,
          color: '#fff',
          lineHeight: 20,
        },
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        data: STEPS.map((s, i) => ({
          name: s.label,
          value: values[i],
        })),
      },
    ],
  }
})
</script>

<style scoped>
.card-title {
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
