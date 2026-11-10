<template>
  <div ref="el" :style="{ width: '100%', height }"></div>
</template>

<script setup>
// ECharts 薄包装：传入 option 即渲染，容器尺寸变化自动重绘
import { initChart } from '../utils/echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  option: { type: Object, default: null },
  height: { type: String, default: '320px' },
})

const el = ref()
let chart = null
let resizeObserver = null

function render() {
  if (chart && props.option) chart.setOption(props.option, true)
}

function onResize() {
  chart?.resize()
}

onMounted(() => {
  chart = initChart(el.value)
  render()
  // 监听外层容器。ECharts 会改自己根节点的像素高度，监听自身会形成重绘 → 变高 → 再重绘。
  const target = el.value.parentElement || el.value
  resizeObserver = new ResizeObserver(onResize)
  resizeObserver.observe(target)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})

watch(() => props.option, render, { deep: true })
</script>
