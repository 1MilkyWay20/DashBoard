<template>
  <el-tooltip :content="ui.sidebarCollapsed ? '展开侧栏' : '隐藏侧栏'" placement="bottom">
    <el-button class="toggle-btn" text @click="ui.toggleSidebar()">
      <el-icon :size="18">
        <Expand v-if="ui.sidebarCollapsed" />
        <Fold v-else />
      </el-icon>
    </el-button>
  </el-tooltip>
</template>

<script setup>
import { Fold, Expand } from '@element-plus/icons-vue'
import { useUiStore } from '../store/ui'

const ui = useUiStore()
</script>

<style scoped>
.toggle-btn {
  padding: 8px;
  color: var(--dv-text-secondary);
  margin-right: 4px;
}
.toggle-btn:hover {
  color: var(--dv-primary);
}
</style>
