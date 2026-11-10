<template>
  <el-card shadow="never">
    <template #header>
      <div class="card-header">
        <span class="card-title">平台对比</span>
        <el-radio-group v-model="metric">
          <el-radio-button value="revenue">营业额</el-radio-button>
          <el-radio-button value="orders">订单量</el-radio-button>
        </el-radio-group>
      </div>
    </template>
    <EChart :option="option" height="340px" />
  </el-card>
</template>

<script setup>
import { computed, ref } from 'vue'
import EChart from '../EChart.vue'
import { CHART_COLORS } from './chartBase'
import { fmtInt, fmtMoney, fmtDecimal } from '../../utils/format'

const props = defineProps({
  /** [{ platform, revenue, orders }, ...] */
  data: { type: Array, default: () => [] },
})

const metric = ref('revenue') // 默认营业额

const isRevenue = computed(() => metric.value === 'revenue')

const total = computed(() =>
  props.data.reduce((s, r) => s + Number((isRevenue.value ? r.revenue : r.orders) ?? 0), 0),
)

const option = computed(() => {
  const rows = props.data
  const valueKey = isRevenue.value ? 'revenue' : 'orders'
  const subtext = isRevenue.value ? '总营业额' : '总订单'

  const legendFormatter = (name) => {
    const r = rows.find((x) => (x.platform || '未知') === name)
    const v = Number(r?.[valueKey] ?? 0)
    const text = isRevenue.value ? fmtMoney(v) : fmtInt(v)
    return `${name}　${text}${isRevenue.value ? '' : ' 单'}`
  }

  const formatValue = (v) => (isRevenue.value ? `${fmtMoney(v)} 元` : `${fmtInt(v)} 单`)

  return {
    color: CHART_COLORS,
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.marker}${p.name}　<b>${formatValue(p.value)}</b>（${fmtDecimal(p.percent)}%）`,
    },
    title: {
      text: isRevenue.value ? fmtMoney(total.value) : fmtInt(total.value),
      subtext,
      left: 'center',
      top: '32%',
      textStyle: { fontSize: 22, fontWeight: 600, color: '#0f172a' },
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
        label: { position: 'outside', formatter: (p) => `${fmtDecimal(p.percent)}%`, fontSize: 13, color: '#606266' },
        labelLine: { length: 10, length2: 8 },
        data: rows.map((r) => ({
          name: r.platform || '未知',
          value: Number(r[valueKey] ?? 0),
        })),
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
  gap: 8px;
}
.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
</style>
