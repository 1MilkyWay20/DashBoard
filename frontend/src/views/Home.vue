<template>
  <div class="home-page">
    <header class="home-header">
      <div class="brand-block">
        <span class="brand-mark" />
        <div>
          <h1 class="home-title">选择品牌</h1>
          <p class="home-sub">进入对应品牌的销售数据看板</p>
        </div>
      </div>
      <div class="user">
        <span class="dv-username">{{ auth.user?.username }}</span>
        <el-button v-if="auth.isAdmin" link type="primary" @click="router.push('/admin/users')">
          用户管理
        </el-button>
        <el-button v-if="auth.isAdmin" link type="primary" @click="router.push('/admin/login-logs')">
          登录记录
        </el-button>
        <el-button link type="danger" @click="logout">退出</el-button>
      </div>
    </header>

    <el-empty v-if="!brands.length && !loading" description="没有可见品牌，请联系管理员分配" />
    <div v-loading="loading" class="brand-grid">
      <article
        v-for="b in brands"
        :key="b.key"
        class="brand-card"
        @click="router.push(`/dashboard/${b.key}`)"
      >
        <div class="brand-name">{{ b.label }}</div>
        <div v-if="b.stats" class="brand-date">数据日期 {{ b.stats.date }}</div>
        <div class="stat-grid">
          <div v-for="s in cardStats(b)" :key="s.label" class="stat">
            <span class="stat-label">{{ s.label }}</span>
            <span class="stat-value">{{ s.value }}</span>
            <span v-if="s.delta" class="stat-delta" :class="s.deltaType">
              {{ s.deltaType === 'up' ? '▲' : '▼' }} {{ s.delta }}
            </span>
          </div>
        </div>
        <div class="brand-tip">进入数据看板 →</div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../store/auth'
import api from '../api'
import { fmtDecimal, fmtInt, fmtMoney, fmtPct } from '../utils/format'

const router = useRouter()
const auth = useAuthStore()
const brands = ref([])
const loading = ref(true)

// 品牌卡片固定展示的四项概览指标（数据取该品牌销售表最近一天）
const STAT_LABELS = ['营业额', '收入', '订单数', '实收率']

onMounted(async () => {
  try {
    brands.value = await api.get('/meta/brands/summary')
  } finally {
    loading.value = false
  }
})

function logout() {
  auth.logout()
  router.push('/login')
}

// 单项指标：当前值 + 较前一天的涨跌（比率类用百分点差）
function statItem(label, cur, prev, fmt, isRatio = false) {
  let delta = ''
  let deltaType = 'flat'
  if (prev !== undefined && prev !== null && prev !== 0) {
    if (isRatio) {
      const pts = (cur - prev) * 100
      delta = `${pts >= 0 ? '+' : ''}${fmtDecimal(pts)}pp`
    } else {
      const pct = ((cur - prev) / prev) * 100
      delta = `${pct >= 0 ? '+' : ''}${fmtDecimal(pct)}%`
    }
    deltaType = cur >= prev ? 'up' : 'down'
  }
  return { label, value: fmt(cur), delta, deltaType }
}

function cardStats(b) {
  const c = b.stats?.current
  const p = b.stats?.previous
  if (!c) {
    // 查不到数据（表异常/无数据）：按约定显示"--"，卡片仍可点击进入看板
    return STAT_LABELS.map((label) => ({ label, value: '--', delta: '', deltaType: 'flat' }))
  }
  return [
    statItem('营业额', c.revenue, p?.revenue, fmtMoney),
    statItem('收入', c.income, p?.income, fmtMoney),
    statItem('订单数', c.orders, p?.orders, fmtInt),
    statItem('实收率', c.income_rate, p?.income_rate, fmtPct, true),
  ]
}
</script>

<style scoped>
.home-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 48px 24px 64px;
  min-height: 100vh;
  background:
    radial-gradient(ellipse 60% 40% at 10% 0%, rgba(45, 212, 191, 0.12), transparent 55%),
    var(--dv-bg);
}

.home-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 28px;
  flex-wrap: wrap;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-mark {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  background: linear-gradient(145deg, #2dd4bf, #0d9488);
  box-shadow: 0 8px 18px rgba(13, 148, 136, 0.28);
  flex-shrink: 0;
}

.home-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--dv-text);
}

.home-sub {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--dv-text-muted);
}

.user {
  display: flex;
  align-items: center;
  gap: 4px;
}

.brand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  min-height: 120px;
}

.brand-card {
  background: var(--dv-surface);
  border: 1px solid var(--dv-border);
  border-radius: var(--dv-radius);
  box-shadow: var(--dv-shadow);
  padding: 20px 18px 16px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.brand-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--dv-shadow-hover);
  border-color: #99f6e4;
}

.brand-name {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 4px;
  color: var(--dv-text);
}

.brand-date {
  color: var(--dv-text-muted);
  font-size: 12px;
  margin-bottom: 14px;
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 14px;
  margin-bottom: 14px;
}

.stat {
  display: flex;
  flex-direction: column;
}

.stat-label {
  color: var(--dv-text-muted);
  font-size: 12px;
}

.stat-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--dv-text);
  font-variant-numeric: tabular-nums;
}

.stat-delta {
  font-size: 11px;
  font-weight: 600;
}

.stat-delta.up {
  color: var(--dv-up);
}

.stat-delta.down {
  color: var(--dv-down);
}

.brand-tip {
  color: var(--dv-primary);
  font-size: 13px;
  font-weight: 600;
  text-align: right;
}
</style>
