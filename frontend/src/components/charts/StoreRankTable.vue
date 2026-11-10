<template>
  <el-card shadow="never">
    <template #header>
      <div class="card-header">
        <span>门店排行</span>
        <el-button
          type="primary"
          link
          :disabled="!sortedData.length"
          :loading="exporting"
          @click="exportExcel"
        >
          导出 Excel
        </el-button>
      </div>
    </template>
    <el-table :data="pagedData" stripe border class="store-table dv-resizable" @sort-change="onSortChange">
      <el-table-column label="#" width="50">
        <template #default="{ $index }">{{ rankOf($index) }}</template>
      </el-table-column>
      <el-table-column prop="store_name" label="门店" min-width="200" show-overflow-tooltip />
      <el-table-column prop="revenue" label="营业额" align="right" sortable="custom" min-width="140">
        <template #default="{ row }">{{ fmtMoney(row.revenue) }}</template>
      </el-table-column>
      <el-table-column prop="orders" label="订单数" align="right" sortable="custom" min-width="110">
        <template #default="{ row }">{{ fmtInt(row.orders) }}</template>
      </el-table-column>
      <el-table-column prop="income" label="收入" align="right" sortable="custom" min-width="140">
        <template #default="{ row }">{{ fmtMoney(row.income) }}</template>
      </el-table-column>
      <!-- 鱇脯独有：利润紧跟收入后 -->
      <el-table-column
        v-if="showProfitCols"
        prop="profit"
        label="利润"
        align="right"
        sortable="custom"
        min-width="140"
      >
        <template #default="{ row }">{{ fmtMoney(row.profit) }}</template>
      </el-table-column>
      <el-table-column prop="income_rate" label="实收率" align="right" sortable="custom" min-width="110">
        <template #default="{ row }">{{ fmtPct(row.income_rate) }}</template>
      </el-table-column>
      <el-table-column prop="subsidy_rate" label="活动支出占比" align="right" sortable="custom" min-width="150">
        <template #default="{ row }">{{ fmtPct(row.subsidy_rate) }}</template>
      </el-table-column>
      <el-table-column prop="commission_rate" label="平台佣金占比" align="right" sortable="custom" min-width="150">
        <template #default="{ row }">{{ fmtPct(row.commission_rate) }}</template>
      </el-table-column>
      <el-table-column prop="avg_order_value" label="客单价" align="right" sortable="custom" min-width="110">
        <template #default="{ row }">{{ fmtDecimal(row.avg_order_value) }}</template>
      </el-table-column>
      <!-- 鱇脯独有：结算占比=收入/线下金额，利润率=利润/营业额 -->
      <el-table-column
        v-if="showProfitCols"
        prop="settlement_rate"
        label="结算占比"
        align="right"
        sortable="custom"
        min-width="120"
      >
        <template #default="{ row }">{{ fmtPct(row.settlement_rate) }}</template>
      </el-table-column>
      <el-table-column
        v-if="showProfitCols"
        prop="profit_rate"
        label="利润率"
        align="right"
        sortable="custom"
        min-width="110"
      >
        <template #default="{ row }">{{ fmtPct(row.profit_rate) }}</template>
      </el-table-column>
    </el-table>
    <div v-if="sortedData.length > PAGE_SIZE" class="pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="PAGE_SIZE"
        :total="sortedData.length"
        layout="total, prev, pager, next"
        background
      />
    </div>
  </el-card>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { fmtInt, fmtMoney, fmtPct, fmtDecimal, DECIMAL_DIGITS } from '../../utils/format'

const PAGE_SIZE = 10  // 门店排行每页条数

const props = defineProps({
  /** 门店行；鱇脯额外含 profit / settlement_rate / profit_rate */
  data: { type: Array, default: () => [] },
})

const page = ref(1)
const sortProp = ref(null)
const sortOrder = ref(null)  // 'ascending' | 'descending' | null
const exporting = ref(false)

/** 接口返回了利润字段才展示（仅鱇脯） */
const showProfitCols = computed(() => props.data.some((r) => Object.prototype.hasOwnProperty.call(r, 'profit')))

const sortedData = computed(() => {
  const rows = [...props.data]
  if (!sortProp.value || !sortOrder.value) return rows
  const key = sortProp.value
  const dir = sortOrder.value === 'ascending' ? 1 : -1
  rows.sort((a, b) => {
    const va = Number(a[key] ?? 0)
    const vb = Number(b[key] ?? 0)
    return (va - vb) * dir
  })
  return rows
})

const pagedData = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return sortedData.value.slice(start, start + PAGE_SIZE)
})

function rankOf(index) {
  return (page.value - 1) * PAGE_SIZE + index + 1
}

function onSortChange({ prop, order }) {
  sortProp.value = order ? prop : null
  sortOrder.value = order
  page.value = 1
}

/** 比率转百分数数值，便于 Excel 再计算 */
function pctNum(v) {
  return Number((((v ?? 0) * 100).toFixed(DECIMAL_DIGITS)))
}

function moneyNum(v) {
  return Number(Number(v ?? 0).toFixed(DECIMAL_DIGITS))
}

/** 导出当前筛选下的全部门店排行（含当前排序），与表格列一致 */
async function exportExcel() {
  if (!sortedData.value.length) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  exporting.value = true
  try {
    const XLSX = await import('xlsx')
    const withProfit = showProfitCols.value
    const rows = sortedData.value.map((r, i) => {
      const row = {
        '#': i + 1,
        门店: r.store_name ?? '',
        营业额: moneyNum(r.revenue),
        订单数: Number(r.orders ?? 0),
        收入: moneyNum(r.income),
      }
      if (withProfit) row['利润'] = moneyNum(r.profit)
      row['实收率(%)'] = pctNum(r.income_rate)
      row['活动支出占比(%)'] = pctNum(r.subsidy_rate)
      row['平台佣金占比(%)'] = pctNum(r.commission_rate)
      row['客单价'] = moneyNum(r.avg_order_value)
      if (withProfit) {
        row['结算占比(%)'] = pctNum(r.settlement_rate)
        row['利润率(%)'] = pctNum(r.profit_rate)
      }
      return row
    })

    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, '门店排行')
    const stamp = new Date()
    const y = stamp.getFullYear()
    const m = String(stamp.getMonth() + 1).padStart(2, '0')
    const d = String(stamp.getDate()).padStart(2, '0')
    XLSX.writeFile(wb, `门店排行_${y}${m}${d}.xlsx`)
  } catch {
    ElMessage.error('导出失败，请重试')
  } finally {
    exporting.value = false
  }
}

// 筛选变更导致数据重载时回到第一页
watch(
  () => props.data,
  () => {
    page.value = 1
  },
)
</script>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.store-table {
  font-size: 15px;
}
.store-table :deep(.el-table__header th) {
  font-size: 15px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
