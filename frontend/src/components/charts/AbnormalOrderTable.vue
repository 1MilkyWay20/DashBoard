<template>
  <el-card shadow="never">
    <template #header>
      <div class="card-header">
        <span>异常订单</span>
        <div class="header-actions">
          <el-radio-group
            :model-value="platform"
            size="small"
            @change="$emit('update:platform', $event)"
          >
            <el-radio-button v-for="p in platforms" :key="p" :value="p">{{ p }}</el-radio-button>
          </el-radio-group>
          <el-button
            type="primary"
            link
            :disabled="!sortedRows.length"
            :loading="exporting"
            @click="exportExcel"
          >
          导出 Excel
        </el-button>
        </div>
      </div>
    </template>
    <el-table
      :data="pagedRows"
      stripe
      border
      show-summary
      :summary-method="summaryMethod"
      class="store-table dv-resizable"
      empty-text="暂无异常订单"
      @sort-change="onSortChange"
    >
      <el-table-column label="#" width="50">
        <template #default="{ $index }">{{ rankOf($index) }}</template>
      </el-table-column>
      <el-table-column
        prop="store_name"
        label="门店"
        min-width="200"
        sortable="custom"
        show-overflow-tooltip
      />
      <el-table-column
        v-for="issue in sortedIssues"
        :key="issue"
        :prop="issue"
        :label="issue"
        align="right"
        sortable="custom"
        min-width="140"
      >
        <template #default="{ row }">{{ cellText(row[issue]) }}</template>
      </el-table-column>
      <el-table-column prop="total" label="总计" align="right" sortable="custom" min-width="110">
        <template #default="{ row }">{{ fmtInt(row.total) }}</template>
      </el-table-column>
    </el-table>
    <div v-if="sortedRows.length > PAGE_SIZE" class="pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="PAGE_SIZE"
        :total="sortedRows.length"
        layout="total, prev, pager, next"
        background
      />
    </div>
  </el-card>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { fmtInt } from '../../utils/format'

const PAGE_SIZE = 9 // 每页门店数

const props = defineProps({
  /** { issues, rows, totals }；一单多问题已在入库时拆开分别计数 */
  data: { type: Object, default: null },
  /** 本表自己的平台，不跟页面顶部平台筛选联动 */
  platform: { type: String, default: '美团' },
  platforms: { type: Array, default: () => ['美团', '饿了么'] },
})

defineEmits(['update:platform'])

const page = ref(1)
const sortProp = ref(null)
const sortOrder = ref(null)
const exporting = ref(false)

function byZh(a, b) {
  return String(a).localeCompare(String(b), 'zh-CN')
}

const sortedIssues = computed(() => [...(props.data?.issues || [])].sort(byZh))

const sortedRows = computed(() => {
  const rows = [...(props.data?.rows || [])]
  if (!sortProp.value || !sortOrder.value) {
    rows.sort((a, b) => byZh(a.store_name, b.store_name))
    return rows
  }
  const key = sortProp.value
  const dir = sortOrder.value === 'ascending' ? 1 : -1
  rows.sort((a, b) => {
    if (key === 'store_name') return byZh(a.store_name, b.store_name) * dir
    return (Number(a[key] ?? 0) - Number(b[key] ?? 0)) * dir
  })
  return rows
})

const pagedRows = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return sortedRows.value.slice(start, start + PAGE_SIZE)
})

function rankOf(index) {
  return (page.value - 1) * PAGE_SIZE + index + 1
}

function onSortChange({ prop, order }) {
  sortProp.value = order ? prop : null
  sortOrder.value = order
  page.value = 1
}

function cellText(value) {
  const n = Number(value || 0)
  return n ? fmtInt(n) : ''
}

function summaryMethod({ columns }) {
  const totals = props.data?.totals || {}
  return columns.map((col) => {
    if (col.property === 'store_name') return '总计'
    if (col.property === 'total') return fmtInt(totals.total || 0)
    if (!col.property) return ''
    return cellText(totals[col.property])
  })
}

/** 导出当前筛选下的全部门店（含当前排序），并附总计行 */
async function exportExcel() {
  if (!sortedRows.value.length) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  exporting.value = true
  try {
    const XLSX = await import('xlsx')
    const issues = sortedIssues.value
    const totals = props.data?.totals || {}
    const rows = sortedRows.value.map((r, i) => {
      const row = { '#': i + 1, 门店: r.store_name ?? '' }
      for (const issue of issues) row[issue] = Number(r[issue] ?? 0)
      row['总计'] = Number(r.total ?? 0)
      return row
    })
    const totalRow = { '#': '', 门店: '总计' }
    for (const issue of issues) totalRow[issue] = Number(totals[issue] ?? 0)
    totalRow['总计'] = Number(totals.total ?? 0)
    rows.push(totalRow)

    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, '异常订单')
    const stamp = new Date()
    const y = stamp.getFullYear()
    const m = String(stamp.getMonth() + 1).padStart(2, '0')
    const d = String(stamp.getDate()).padStart(2, '0')
    XLSX.writeFile(wb, `异常订单_${props.platform}_${y}${m}${d}.xlsx`)
  } catch {
    ElMessage.error('导出失败，请重试')
  } finally {
    exporting.value = false
  }
}

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
  gap: 12px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.store-table {
  font-size: 15px;
}
.store-table :deep(.el-table__header th) {
  font-size: 15px;
}
.store-table :deep(.el-table__footer) {
  font-weight: 600;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
