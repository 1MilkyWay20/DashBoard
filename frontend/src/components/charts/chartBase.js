import { axisMoney, fmtInt, fmtMoney } from '../../utils/format'

/** 看板图表主色（与主题青绿一致） */
export const CHART_COLORS = ['#0d9488', '#0ea5e9', '#f59e0b', '#8b5cf6', '#ef4444', '#64748b']

/** 图表公共骨架：containLabel 防轴标签裁切，图例放顶部不占绘图区 */
export const CHART_BASE = {
  color: CHART_COLORS,
  legend: {
    top: 0,
    itemWidth: 16,
    itemHeight: 10,
    textStyle: { fontSize: 12, color: '#64748b' },
  },
  grid: { left: 8, right: 16, top: 42, bottom: 4, containLabel: true },
  textStyle: { fontSize: 12, color: '#64748b' },
}

/** 双轴（营业额 + 订单数）通用 tooltip */
export function axisTooltip(params) {
  const lines = params.map(
    (p) =>
      `${p.marker}${p.seriesName}　<b>${p.seriesName === '订单数' ? fmtInt(p.value) : fmtMoney(p.value)}</b>`,
  )
  return `${params[0].axisValueLabel || params[0].axisValue}<br/>${lines.join('<br/>')}`
}

export { axisMoney, fmtInt, fmtMoney, fmtPct } from '../../utils/format'
