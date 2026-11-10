import { defineStore } from 'pinia'

const STORAGE_KEY = 'dv_sidebar_collapsed'

export const useUiStore = defineStore('ui', {
  state: () => ({
    // true = 侧栏隐藏，给内容区更多空间；刷新后记住上次选择
    sidebarCollapsed: localStorage.getItem(STORAGE_KEY) === '1',
  }),
  actions: {
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
      localStorage.setItem(STORAGE_KEY, this.sidebarCollapsed ? '1' : '0')
    },
    setSidebarCollapsed(v) {
      this.sidebarCollapsed = !!v
      localStorage.setItem(STORAGE_KEY, this.sidebarCollapsed ? '1' : '0')
    },
  },
})
