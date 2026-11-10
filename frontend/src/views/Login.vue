<template>
  <div class="login-page">
    <div class="login-bg" aria-hidden="true" />
    <div class="login-panel">
      <div class="brand">
        <span class="brand-mark" />
        <h1 class="brand-title">销售数据看板</h1>
        <p class="brand-desc">按品牌查看门店销售与经营指标</p>
      </div>
      <el-form class="login-form" :model="form" label-position="top" @keyup.enter="submit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" size="large" autofocus />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            size="large"
            placeholder="请输入密码"
          />
        </el-form-item>
        <el-button type="primary" class="submit" size="large" :loading="loading" @click="submit">
          登 录
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../store/auth'
import api from '../api'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    // 登录后：只有一个授权品牌就直接进看板，否则去品牌选择页
    const brands = await api.get('/meta/brands')
    if (brands.length === 1) router.push(`/dashboard/${brands[0].key}`)
    else router.push('/home')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  position: relative;
  overflow: hidden;
}

.login-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 20% 20%, rgba(45, 212, 191, 0.18), transparent 55%),
    radial-gradient(ellipse 70% 50% at 85% 75%, rgba(14, 165, 233, 0.12), transparent 50%),
    linear-gradient(160deg, #0f172a 0%, #1e293b 45%, #0f172a 100%);
}

.login-bg::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(148, 163, 184, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.06) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse 70% 70% at 50% 50%, black, transparent);
}

.login-panel {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 400px;
  padding: 36px 36px 32px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.7);
  border-radius: 16px;
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.35);
  backdrop-filter: blur(12px);
}

.brand {
  text-align: center;
  margin-bottom: 28px;
}

.brand-mark {
  display: inline-block;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(145deg, #2dd4bf, #0d9488);
  box-shadow: 0 8px 20px rgba(13, 148, 136, 0.35);
  margin-bottom: 14px;
}

.brand-title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 700;
  color: var(--dv-text);
  letter-spacing: -0.02em;
}

.brand-desc {
  margin: 0;
  font-size: 13px;
  color: var(--dv-text-muted);
}

.login-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: var(--dv-text-secondary);
}

.submit {
  width: 100%;
  margin-top: 4px;
  font-weight: 600;
  letter-spacing: 0.08em;
}
</style>
