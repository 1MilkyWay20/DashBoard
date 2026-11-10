<template>
  <el-container class="layout">
    <AppSidebar />
    <el-container direction="vertical">
      <el-header class="dv-topbar" height="56px">
        <SidebarToggle />
        <span class="dv-topbar-title">登录记录</span>
        <span class="dv-username">{{ auth.user?.username }}</span>
        <el-button link type="danger" @click="logout">退出</el-button>
      </el-header>

      <el-main class="main dv-panel">
        <p class="page-desc">查看各账号的登录时间、结果和 IP。成功和失败都会留下记录。</p>

        <div class="dv-toolbar filters">
          <el-input
            v-model="username"
            clearable
            placeholder="按用户名筛选"
            style="width: 200px"
            @keyup.enter="search"
            @clear="search"
          />
          <el-select v-model="successFilter" clearable placeholder="全部结果" style="width: 140px" @change="search">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="fail" />
          </el-select>
          <el-button type="primary" @click="search">查询</el-button>
        </div>

        <el-card shadow="never" class="table-card">
          <el-table v-loading="loading" :data="items" stripe>
            <el-table-column prop="created_at" label="时间" width="180" />
            <el-table-column prop="username" label="用户名" min-width="120" />
            <el-table-column label="结果" width="90">
              <template #default="{ row }">
                <el-tag :type="row.success ? 'success' : 'danger'">
                  {{ row.success ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="说明" min-width="140" />
            <el-table-column prop="ip" label="IP" min-width="140" />
          </el-table>
          <div class="pager">
            <el-pagination
              v-model:current-page="page"
              v-model:page-size="pageSize"
              :total="total"
              :page-sizes="[20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              background
              @current-change="load"
              @size-change="onSizeChange"
            />
          </div>
        </el-card>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppSidebar from '../components/AppSidebar.vue'
import SidebarToggle from '../components/SidebarToggle.vue'
import { useAuthStore } from '../store/auth'
import api from '../api'

const router = useRouter()
const auth = useAuthStore()

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const username = ref('')
const successFilter = ref('')
const loading = ref(false)

onMounted(load)

function logout() {
  auth.logout()
  router.push('/login')
}

function search() {
  page.value = 1
  load()
}

function onSizeChange() {
  page.value = 1
  load()
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    const keyword = username.value.trim()
    if (keyword) params.username = keyword
    if (successFilter.value === 'success') params.success = true
    if (successFilter.value === 'fail') params.success = false
    const data = await api.get('/admin/login-logs', { params })
    items.value = data.items
    total.value = data.total
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载登录记录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
  overflow: hidden;
  background: var(--dv-bg);
}
.main {
  padding: 18px 20px 24px;
  overflow-y: auto;
  background: var(--dv-bg);
}
.page-desc {
  margin: 0 0 14px;
  color: var(--dv-text-muted);
  font-size: 13px;
}
.filters {
  margin-bottom: 14px;
}
.table-card {
  border-radius: var(--dv-radius);
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
