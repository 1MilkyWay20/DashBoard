<template>
  <el-card shadow="never" class="kpi-card">
    <div class="kpi-label">{{ label }}</div>
    <div class="kpi-value">{{ value }}</div>
    <div v-if="delta" class="kpi-delta" :class="deltaType">
      {{ deltaType === 'up' ? '▲' : deltaType === 'down' ? '▼' : '—' }} {{ delta }}
      <span class="kpi-delta-base">较上期</span>
    </div>
  </el-card>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: String, required: true },
  // delta: 预格式化好的变化文本；deltaType: up=变好(绿) / down=变差(红) / flat
  delta: { type: String, default: '' },
  deltaType: { type: String, default: 'flat' },
})
</script>

<style scoped>
.kpi-card {
  text-align: left;
  border: 1px solid var(--dv-border) !important;
  border-radius: var(--dv-radius) !important;
  box-shadow: var(--dv-shadow) !important;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
  overflow: hidden;
}

.kpi-card:hover {
  box-shadow: var(--dv-shadow-hover) !important;
  transform: translateY(-1px);
}

.kpi-card :deep(.el-card__body) {
  padding: 16px 18px 14px;
  position: relative;
}

.kpi-card :deep(.el-card__body)::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--dv-primary), #2dd4bf);
  opacity: 0.85;
}

.kpi-label {
  color: var(--dv-text-muted);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.01em;
}

.kpi-value {
  font-size: 26px;
  font-weight: 700;
  margin: 8px 0 6px;
  color: var(--dv-text);
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
}

.kpi-delta {
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.kpi-delta.up {
  color: var(--dv-up);
}

.kpi-delta.down {
  color: var(--dv-down);
}

.kpi-delta.flat {
  color: var(--dv-text-muted);
}

.kpi-delta-base {
  color: var(--dv-text-muted);
  font-weight: 400;
  margin-left: 4px;
}
</style>
