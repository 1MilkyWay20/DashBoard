<template>
  <div class="float-toolbar" :class="{ collapsed: !open }" aria-label="快捷工具栏">
    <button
      type="button"
      class="toggle"
      :aria-expanded="open"
      :title="open ? '收起工具栏' : '展开工具栏'"
      @click="open = !open"
    >
      <el-icon class="toggle-icon" :size="14">
        <DArrowRight v-if="open" />
        <DArrowLeft v-else />
      </el-icon>
    </button>

    <nav class="panel" :aria-hidden="!open">
      <button
        v-for="item in items"
        :key="item.key"
        type="button"
        class="item"
        :disabled="item.disabled"
        @click="onItemClick(item)"
      >
        {{ item.label }}
      </button>
    </nav>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { DArrowLeft, DArrowRight } from '@element-plus/icons-vue'

defineProps({
  /** [{ key, label, disabled? }] */
  items: { type: Array, default: () => [] },
})

const emit = defineEmits(['select'])

/** 平时收起，只露左侧小把手 */
const open = ref(false)

function onItemClick(item) {
  if (item.disabled) return
  emit('select', item)
}
</script>

<style scoped>
.float-toolbar {
  position: fixed;
  right: 0;
  bottom: 96px;
  z-index: 1200;
  display: flex;
  align-items: stretch;
  transition: transform 0.28s ease;
}

/* 收起时把面板滑出屏外，只留把手贴右缘 */
.float-toolbar.collapsed {
  transform: translateX(calc(100% - 22px));
}

.toggle {
  flex-shrink: 0;
  align-self: center;
  width: 22px;
  height: 48px;
  margin: 0;
  padding: 0;
  border: none;
  border-radius: 10px 0 0 10px;
  background: #fff;
  box-shadow: -2px 0 10px rgba(15, 23, 42, 0.08);
  color: var(--dv-text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s ease, background 0.15s ease;
}

.toggle:hover {
  color: var(--dv-primary);
  background: var(--dv-primary-soft);
}

.toggle-icon {
  display: flex;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 112px;
  padding: 10px 0;
  background: #fff;
  border-radius: 14px 0 0 14px;
  box-shadow: -4px 4px 20px rgba(15, 23, 42, 0.1);
}

.item {
  appearance: none;
  border: none;
  background: transparent;
  margin: 0;
  padding: 14px 18px;
  font-size: 13px;
  line-height: 1.3;
  color: var(--dv-text-secondary);
  text-align: center;
  white-space: nowrap;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}

.item:hover:not(:disabled) {
  color: var(--dv-primary);
  background: var(--dv-primary-soft);
}

.item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.float-toolbar.collapsed .panel {
  pointer-events: none;
}
</style>
