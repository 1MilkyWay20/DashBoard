<template>
  <el-container class="layout">
    <AppSidebar />
    <el-container direction="vertical">
      <el-header class="dv-topbar" height="56px">
        <SidebarToggle />
        <span class="dv-topbar-title">用户管理</span>
        <span class="dv-username">{{ auth.user?.username }}</span>
        <el-button link type="danger" @click="logout">退出</el-button>
      </el-header>

      <el-main class="main dv-panel">
        <div class="page-head">
          <p class="page-desc">创建用户、分配可见品牌、启停账号</p>
          <el-button type="primary" @click="openCreate">新建用户</el-button>
        </div>

        <el-card shadow="never" class="table-card">
          <el-table :data="users" stripe>
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="username" label="用户名" min-width="120" />
            <el-table-column label="角色" width="100">
              <template #default="{ row }">
                <el-tag :type="row.is_admin ? 'warning' : 'info'">
                  {{ row.is_admin ? '管理员' : '普通用户' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'danger'">
                  {{ row.enabled ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="可见品牌" min-width="160">
              <template #default="{ row }">
                <el-tag v-for="b in row.brands" :key="b" size="small" class="brand-tag">
                  {{ brandLabel(b) }}
                </el-tag>
                <span v-if="row.is_admin" class="hint">管理员可见全部</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
                <el-button link type="danger" :disabled="row.id === auth.user?.id" @click="remove(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 新建/编辑弹窗 -->
        <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户' : '新建用户'" width="460px">
          <el-form :model="form" label-width="90px">
            <el-form-item label="用户名">
              <el-input v-model="form.username" :disabled="editing" placeholder="2-50 个字符" />
            </el-form-item>
            <el-form-item :label="editing ? '新密码' : '密码'">
              <el-input
                v-model="form.password"
                type="password"
                show-password
                :placeholder="editing ? '留空表示不修改密码' : '至少 6 位'"
              />
            </el-form-item>
            <el-form-item label="管理员">
              <el-switch v-model="form.is_admin" />
              <span class="hint">管理员可进入用户管理和登录记录，且可见全部品牌</span>
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="form.enabled" />
            </el-form-item>
            <el-form-item label="可见品牌">
              <el-checkbox-group v-model="form.brands" :disabled="form.is_admin">
                <el-checkbox v-for="b in brandList" :key="b.key" :value="b.key">
                  {{ b.label }}
                </el-checkbox>
              </el-checkbox-group>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="dialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          </template>
        </el-dialog>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppSidebar from '../components/AppSidebar.vue'
import SidebarToggle from '../components/SidebarToggle.vue'
import { useAuthStore } from '../store/auth'
import api from '../api'

const router = useRouter()
const auth = useAuthStore()

const users = ref([])
const brandList = ref([])
const dialogVisible = ref(false)
const editing = ref(null) // 编辑中的用户 id，null 表示新建
const saving = ref(false)

const form = reactive({ username: '', password: '', is_admin: false, enabled: true, brands: [] })

onMounted(async () => {
  brandList.value = await api.get('/admin/brands')
  await loadUsers()
})

function logout() {
  auth.logout()
  router.push('/login')
}

async function loadUsers() {
  users.value = await api.get('/admin/users')
}

function brandLabel(key) {
  return brandList.value.find((b) => b.key === key)?.label || key
}

function openCreate() {
  editing.value = null
  Object.assign(form, { username: '', password: '', is_admin: false, enabled: true, brands: [] })
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row.id
  Object.assign(form, {
    username: row.username,
    password: '',
    is_admin: row.is_admin,
    enabled: row.enabled,
    brands: [...row.brands],
  })
  dialogVisible.value = true
}

async function save() {
  if (!editing.value && (form.username.length < 2 || form.password.length < 6)) {
    ElMessage.warning('用户名至少 2 个字符，密码至少 6 位')
    return
  }
  if (editing.value && form.password && form.password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      const body = { is_admin: form.is_admin, enabled: form.enabled, brands: form.brands }
      if (form.password) body.password = form.password
      await api.put(`/admin/users/${editing.value}`, body)
    } else {
      await api.post('/admin/users', { ...form })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await loadUsers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除用户「${row.username}」？该操作不可恢复。`, '删除确认', {
    type: 'warning',
  })
  await api.delete(`/admin/users/${row.id}`)
  ElMessage.success('已删除')
  await loadUsers()
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
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  gap: 12px;
}
.page-desc {
  margin: 0;
  color: var(--dv-text-muted);
  font-size: 13px;
}
.table-card {
  border-radius: var(--dv-radius);
}
.brand-tag {
  margin-right: 6px;
}
.hint {
  color: var(--dv-text-muted);
  font-size: 12px;
  margin-left: 8px;
}
</style>
