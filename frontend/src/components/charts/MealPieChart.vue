<template>
  <el-card shadow="never" header="三餐时段订单占比">
    <EChart :option="option" height="340px" />
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '../EChart.vue'
import { CHART_COLORS, fmtInt } from './chartBase'
import { fmtDecimal } from '../../utils/format'

const props = defineProps({
  /** [{ meal_type, order_count }, ...] */
  data: { type: Array, default: () => [] },
})

const total = computed(() => props.data.reduce((s, r) => s + (r.order_count || 0), 0))

const option = computed(() => {
  // 环形图：环内标总单量、图例带单量；完整信息在 tooltip
  const legendFormatter = (name) => {
    const r = props.data.find((x) => (x.meal_type || '未知') === name)
    return `${name}　${fmtInt(r?.order_count ?? 0)} 单`
  }
  return {
    color: CHART_COLORS,
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.marker}${p.name}　<b>${fmtInt(p.value)}</b> 单（${fmtDecimal(p.percent)}%）`,
    },
    title: {
      text: fmtInt(total.value),
      subtext: '总订单',
      left: 'center',
      top: '32%',
      textStyle: { fontSize: 24, fontWeight: 600, color: '#0f172a' },
      subtextStyle: { fontSize: 13, color: '#94a3b8' },
    },
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 12,
      itemHeight: 12,
      formatter: legendFormatter,
      textStyle: { fontSize: 13 },
    },
    series: [
      {
        type: 'pie',
        radius: ['44%', '66%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
        // 环外只标占比；名称和单量在底部图例
        label: { position: 'outside', formatter: (p) => `${fmtDecimal(p.percent)}%`, fontSize: 13, color: '#606266' },
        labelLine: { length: 10, length2: 8 },
        data: props.data.map((r) => ({ name: r.meal_type || '未知', value: r.order_count })),
      },
    ],
  }
})
</script>
