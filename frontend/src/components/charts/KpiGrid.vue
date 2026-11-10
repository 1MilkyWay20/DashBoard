<template>
  <el-row v-if="items.length" :gutter="12" class="kpi-row">
    <el-col v-for="k in items" :key="k.label" :xs="12" :sm="8" :md="6" :lg="6">
      <KpiCard :label="k.label" :value="k.value" :delta="k.delta" :delta-type="k.deltaType" />
    </el-col>
  </el-row>
  <el-empty v-else-if="!loading" description="暂无数据" />
</template>

<script setup>
import { computed } from 'vue'
import KpiCard from '../KpiCard.vue'
import { fmtInt, fmtMoney, fmtPct, fmtDecimal } from '../../utils/format'

const props = defineProps({
  /** /dashboard/summary 返回体：{ current, previous } */
  summary: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const RATIO_KEYS = new Set(['实收率', '佣金占比', '商补占比'])

function kpiItem(label, cur, prev, fmt) {
  let delta = ''
  let deltaType = 'flat'
  if (prev !== undefined && prev !== null && prev !== 0) {
    if (RATIO_KEYS.has(label)) {
      const pts = (cur - prev) * 100
      delta = `${pts >= 0 ? '+' : ''}${fmtDecimal(pts)}pp`
    } else {
      const pct = ((cur - prev) / prev) * 100
      delta = `${pct >= 0 ? '+' : ''}${fmtDecimal(pct)}%`
    }
    deltaType = cur >= prev ? 'up' : 'down'
  }
  return { label, value: fmt(cur), delta, deltaType }
}

const items = computed(() => {
  const c = props.summary?.current
  const p = props.summary?.previous
  if (!c) return []
  return [
    kpiItem('销售额', c.revenue, p.revenue, fmtMoney),
    kpiItem('订单数', c.orders, p.orders, fmtInt),
    kpiItem('收入', c.income, p.income, fmtMoney),
    kpiItem('平台佣金', c.commission, p.commission, fmtMoney),
    kpiItem('商家补贴', c.subsidy, p.subsidy, fmtMoney),
    kpiItem('客单价', c.avg_order_value, p.avg_order_value, fmtDecimal),
    kpiItem('实收率', c.income_rate, p.income_rate, fmtPct),
    kpiItem('佣金占比', c.commission_rate, p.commission_rate, fmtPct),
    kpiItem('商补占比', c.subsidy_rate, p.subsidy_rate, fmtPct),
  ]
})
</script>

<style scoped>
.kpi-row {
  margin-bottom: 12px;
}
.kpi-row .el-col {
  margin-bottom: 12px;
}
</style>
