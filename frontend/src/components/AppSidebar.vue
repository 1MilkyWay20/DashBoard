<template>
  <el-aside :width="asideWidth" class="aside" :class="{ collapsed: ui.sidebarCollapsed }">
    <div class="aside-inner">
      <div class="logo">
        <span class="logo-mark" />
        <div class="logo-text">
          <div class="logo-title">销售看板</div>
        </div>
      </div>
      <el-menu
        :key="route.path"
        :default-active="active"
        :default-openeds="openBrandMenus"
        router
        class="menu"
        background-color="transparent"
        text-color="#94a3b8"
        active-text-color="#f8fafc"
      >
        <template v-for="b in brands" :key="b.key">
          <!-- 超管：品牌下挂销售看板 + 门店管理 -->
          <el-sub-menu v-if="auth.isAdmin" :index="b.key">
            <template #title>
              <span class="menu-label">{{ b.label }}</span>
            </template>
            <el-menu-item :index="`/dashboard/${b.key}`">销售看板</el-menu-item>
            <el-menu-item :index="`/dashboard/${b.key}/stores`">门店管理</el-menu-item>
          </el-sub-menu>
          <!-- 普通用户：只进销售看板 -->
          <el-menu-item v-else :index="`/dashboard/${b.key}`">
            {{ b.label }}
          </el-menu-item>
        </template>
        <el-menu-item v-if="auth.isAdmin" index="/admin/users">
          <el-icon><Setting /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/admin/login-logs">
          <el-icon><Clock /></el-icon>
          <span>登录记录</span>
        </el-menu-item>
      </el-menu>
    </div>
  </el-aside>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Clock, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '../store/auth'
import { useUiStore } from '../store/ui'
import api from '../api'

const route = useRoute()
const auth = useAuthStore()
const ui = useUiStore()
const brands = ref([])

const asideWidth = computed(() => (ui.sidebarCollapsed ? '0px' : '232px'))
const active = computed(() => route.path)
const openBrandMenus = computed(() =>
  auth.isAdmin ? [route.params.brand].filter(Boolean) : [],
)

onMounted(async () => {
  brands.value = await api.get('/meta/brands')
})
</script>

<style scoped>
.aside {
  background: var(--dv-sidebar-bg);
  overflow: hidden;
  border-right: 1px solid var(--dv-sidebar-border);
  transition: width 0.22s ease;
  flex-shrink: 0;
}

.aside.collapsed {
  border-right: none;
}

/* 内层固定宽度，避免收起时菜单按 0 宽布局导致展开后文字空白 */
.aside-inner {
  width: 232px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 22px 20px 18px;
  border-bottom: 1px solid var(--dv-sidebar-border);
  min-height: 72px;
  white-space: nowrap;
}

.logo-mark {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: linear-gradient(145deg, #2dd4bf 0%, #0d9488 55%, #0f766e 100%);
  box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.25), 0 8px 20px rgba(13, 148, 136, 0.35);
  flex-shrink: 0;
}

.logo-text {
  flex: 1;
  min-width: 0;
}

.logo-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--dv-sidebar-text-strong);
  letter-spacing: 0.02em;
  line-height: 1.2;
}

.logo-sub {
  font-size: 11px;
  color: var(--dv-sidebar-text);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-top: 2px;
}

.menu {
  border-right: none;
  flex: 1;
  padding: 12px 10px;
  font-size: 14px;
  background: transparent !important;
  overflow-y: auto;
  overflow-x: hidden;
}

.menu :deep(.el-menu-item),
.menu :deep(.el-sub-menu__title) {
  height: 42px;
  line-height: 42px;
  margin: 2px 0;
  border-radius: 8px;
  color: var(--dv-sidebar-text) !important;
}

.menu :deep(.el-menu-item:hover),
.menu :deep(.el-sub-menu__title:hover) {
  background: var(--dv-sidebar-hover) !important;
  color: var(--dv-sidebar-text-strong) !important;
}

.menu :deep(.el-menu-item.is-active) {
  background: var(--dv-sidebar-active) !important;
  color: var(--dv-sidebar-text-strong) !important;
  font-weight: 600;
  box-shadow: inset 3px 0 0 var(--dv-sidebar-accent);
}

.menu :deep(.el-sub-menu .el-menu) {
  background: transparent !important;
}

.menu :deep(.el-sub-menu .el-menu-item) {
  padding-left: 44px !important;
  min-width: auto;
}

.menu :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
  color: var(--dv-sidebar-text-strong) !important;
}

.menu :deep(.el-icon) {
  color: inherit;
}

.menu-label {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
