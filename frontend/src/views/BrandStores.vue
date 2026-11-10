<template>
  <el-container class="layout">
    <AppSidebar />
    <el-container direction="vertical">
      <el-header class="dv-topbar" height="56px">
        <SidebarToggle />
        <span class="dv-topbar-title">{{ brandLabel }} · 门店管理</span>
        <span class="dv-username">{{ auth.user?.username }}</span>
        <el-button link type="danger" @click="logout">退出</el-button>
      </el-header>

      <el-main class="main dv-panel">
        <div class="toolbar dv-toolbar">
          <el-input
            v-model="keyword"
            clearable
            placeholder="搜索门店名称 / 区域 / 门店 ID"
            style="width: 280px"
          />
          <el-radio-group v-model="statusFilter">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="on">已启用</el-radio-button>
            <el-radio-button value="off">已停用</el-radio-button>
          </el-radio-group>
          <el-button :loading="syncing" @click="doSync">补全平台 ID</el-button>
        </div>

        <el-table v-loading="loading" :data="filtered" stripe border class="store-table dv-resizable">

          <el-table-column prop="store_name" label="门店名称" min-width="200" />
          <el-table-column prop="region" label="区域" width="120" />
          <el-table-column prop="mt_id" label="美团门店ID" min-width="120" />
          <el-table-column prop="elm_id" label="饿了么门店ID" min-width="130" />
          <el-table-column prop="jd_id" label="京东门店ID" min-width="120" />
          <el-table-column label="启用" width="90" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="row.enabled"
                :loading="togglingId === row.id"
                @change="(v) => toggleEnabled(row, v)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="footer-hint">
          共 {{ filtered.length }} 家门店（名单来自门店表「门店名称」；停用后不参与看板统计与筛选）
        </div>
      </el-main>
    </el-container>

    <el-dialog v-model="dialogVisible" title="编辑门店" width="480px" destroy-on-close>
      <el-form :model="form" label-width="110px">
        <el-form-item label="门店名称">
          <el-input v-model="form.store_name" />
        </el-form-item>
        <el-form-item label="区域">
          <el-input v-model="form.region" placeholder="城市 / 战区 / 大区" />
        </el-form-item>
        <el-form-item label="美团门店ID">
          <el-input v-model="form.mt_id" clearable />
        </el-form-item>
        <el-form-item label="饿了么门店ID">
          <el-input v-model="form.elm_id" clearable />
        </el-form-item>
        <el-form-item label="京东门店ID">
          <el-input v-model="form.jd_id" clearable />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppSidebar from '../components/AppSidebar.vue'
import SidebarToggle from '../components/SidebarToggle.vue'
import { useAuthStore } from '../store/auth'
import api from '../api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const brandLabels = ref({})
const rows = ref([])
const loading = ref(true)
const syncing = ref(false)
const keyword = ref('')
const statusFilter = ref('all')
const togglingId = ref(null)

const dialogVisible = ref(false)
const editingId = ref(null)
const saving = ref(false)
const form = reactive({
  store_name: '',
  region: '',
  mt_id: '',
  elm_id: '',
  jd_id: '',
  enabled: true,
  remark: '',
})

const brandLabel = computed(
  () => brandLabels.value[route.params.brand] || route.params.brand,
)

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (statusFilter.value === 'on' && !r.enabled) return false
    if (statusFilter.value === 'off' && r.enabled) return false
    if (!kw) return true
    const blob = [r.store_name, r.region, r.mt_id, r.elm_id, r.jd_id, r.remark]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return blob.includes(kw)
  })
})

onMounted(async () => {
  const brands = await api.get('/meta/brands')
  brandLabels.value = Object.fromEntries(brands.map((b) => [b.key, b.label]))
  await load()
})

watch(() => route.params.brand, load)

function logout() {
  auth.logout()
  router.push('/login')
}

async function load() {
  if (!route.params.brand) return
  loading.value = true
  try {
    rows.value = await api.get('/stores', { params: { brand: route.params.brand, sync: true } })
  } finally {
    loading.value = false
  }
}

async function doSync() {
  syncing.value = true
  try {
    const res = await api.post('/stores/sync', null, { params: { brand: route.params.brand } })
    rows.value = res.stores
    ElMessage.success(res.added ? `已补全，并新增 ${res.added} 家` : '已按销售表补全空缺平台 ID')
  } finally {
    syncing.value = false
  }
}

async function toggleEnabled(row, enabled) {
  togglingId.value = row.id
  try {
    const updated = await api.put(`/stores/${row.id}`, { enabled })
    Object.assign(row, updated)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  } finally {
    togglingId.value = null
  }
}

function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, {
    store_name: row.store_name || '',
    region: row.region || '',
    mt_id: row.mt_id || '',
    elm_id: row.elm_id || '',
    jd_id: row.jd_id || '',
    enabled: !!row.enabled,
    remark: row.remark || '',
  })
  dialogVisible.value = true
}

async function save() {
  if (!form.store_name.trim()) {
    ElMessage.warning('门店名称不能为空')
    return
  }
  saving.value = true
  try {
    const updated = await api.put(`/stores/${editingId.value}`, {
      store_name: form.store_name.trim(),
      region: form.region,
      mt_id: form.mt_id,
      elm_id: form.elm_id,
      jd_id: form.jd_id,
      enabled: form.enabled,
      remark: form.remark,
    })
    const idx = rows.value.findIndex((r) => r.id === editingId.value)
    if (idx >= 0) rows.value[idx] = updated
    dialogVisible.value = false
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
  overflow: hidden;
  font-size: 14px;
  background: var(--dv-bg);
}
.main {
  padding: 18px 20px 24px;
  overflow-y: auto;
  background: var(--dv-bg);
}
.toolbar {
  margin-bottom: 14px;
}
.store-table {
  border-radius: var(--dv-radius);
  overflow: hidden;
  border: 1px solid var(--dv-border);
  box-shadow: var(--dv-shadow);
}
.footer-hint {
  margin-top: 12px;
  color: var(--dv-text-muted);
  font-size: 13px;
}
</style>
