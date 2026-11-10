/** 展示小数位数约定：凡涉及小数，默认保留 2 位（见 AGENTS.md） */
export const DECIMAL_DIGITS = 2

/** 金额：千分位；digits 默认 2 */
export function fmtMoney(v, digits = DECIMAL_DIGITS) {
  return Number(v ?? 0).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** 整数：千分位（订单数等，不带小数） */
export function fmtInt(v) {
  return Number(v ?? 0).toLocaleString('zh-CN')
}

/** 比率：0.1234 → 12.34%；digits 默认 2 */
export function fmtPct(v, digits = DECIMAL_DIGITS) {
  return `${((v ?? 0) * 100).toFixed(digits)}%`
}

/** 客单价等普通小数 */
export function fmtDecimal(v, digits = DECIMAL_DIGITS) {
  return Number(v ?? 0).toFixed(digits)
}

/** 坐标轴金额缩写（万），完整数值放 tooltip */
export function axisMoney(v) {
  const n = Number(v)
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(DECIMAL_DIGITS)}万`
  return n.toLocaleString('zh-CN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: DECIMAL_DIGITS,
  })
}

/** 坐标轴比率：0.1234 → 12.34% */
export function axisPct(v) {
  return `${(Number(v ?? 0) * 100).toFixed(DECIMAL_DIGITS)}%`
}
