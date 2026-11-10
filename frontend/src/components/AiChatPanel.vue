<template>
  <el-drawer
    :model-value="modelValue"
    title="AI 经营分析"
    direction="rtl"
    size="420px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="ai-panel">
      <p class="ai-hint">
        基于当前看板筛选（品牌 / 日期 / 平台 / 门店）提问。聚合指标会发送至云端模型，请勿询问敏感订单明细。
      </p>

      <div class="ai-suggestions">
        <el-button
          v-for="q in suggestions"
          :key="q"
          size="small"
          round
          :disabled="sending"
          @click="ask(q)"
        >
          {{ q }}
        </el-button>
      </div>

      <div ref="listEl" class="ai-messages">
        <div v-if="!messages.length" class="ai-empty">试试上方建议问题，或直接输入你的问题。</div>
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="ai-msg"
          :class="m.role"
        >
          <div class="ai-role">{{ m.role === 'user' ? '我' : 'AI' }}</div>
          <div class="ai-bubble">
            <span class="ai-text">{{ m.content }}</span>
            <span v-if="m.streaming" class="ai-cursor">▍</span>
          </div>
          <div v-if="m.status" class="ai-status">{{ m.status }}</div>
        </div>
      </div>

      <div class="ai-input">
        <el-input
          v-model="draft"
          type="textarea"
          :rows="2"
          maxlength="2000"
          show-word-limit
          placeholder="例如：本期哪几家店拖后腿？"
          :disabled="sending"
          @keydown.enter.exact.prevent="submit"
        />
        <div class="ai-actions">
          <el-button link type="info" :disabled="sending || !messages.length" @click="clearChat">
            清空
          </el-button>
          <el-button type="primary" :loading="sending" :disabled="!canSend" @click="submit">
            发送
          </el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** 与看板 commonParams 一致：brand/start/end/platforms?/store_ids? */
  filterParams: { type: Object, required: true },
})

const emit = defineEmits(['update:modelValue'])

const suggestions = [
  '总结本期整体表现与环比变化',
  '哪几家店拖后腿？给出依据',
  '佣金占比是否异常？和平台对比',
]

const draft = ref('')
const sending = ref(false)
const messages = ref([])
const listEl = ref(null)
let abortCtrl = null

const canSend = computed(() => !!draft.value.trim() && !sending.value && !!props.filterParams?.brand)

watch(
  () => props.modelValue,
  (open) => {
    if (open) nextTick(scrollBottom)
  },
)

function clearChat() {
  if (sending.value) return
  messages.value = []
}

function ask(text) {
  draft.value = text
  submit()
}

async function scrollBottom() {
  await nextTick()
  const el = listEl.value
  if (el) el.scrollTop = el.scrollHeight
}

async function submit() {
  const text = draft.value.trim()
  if (!text || sending.value) return
  const p = props.filterParams
  if (!p?.brand || !p?.start || !p?.end) {
    ElMessage.warning('请先选择有效的日期范围')
    return
  }

  const hist = messages.value
    .filter((m) => !m.streaming && m.content && (m.role === 'user' || m.role === 'assistant'))
    .map((m) => ({ role: m.role, content: m.content }))

  messages.value.push({ role: 'user', content: text })
  draft.value = ''
  const assistant = { role: 'assistant', content: '', streaming: true, status: '思考中…' }
  messages.value.push(assistant)
  sending.value = true
  abortCtrl = new AbortController()
  await scrollBottom()

  const platforms = p.platforms
    ? String(p.platforms).split(',').map((s) => s.trim()).filter(Boolean)
    : undefined
  const store_ids = p.store_ids
    ? String(p.store_ids).split(',').map((s) => s.trim()).filter(Boolean)
    : undefined

  try {
    const token = localStorage.getItem('token')
    const res = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        brand: p.brand,
        start: p.start,
        end: p.end,
        platforms: platforms?.length ? platforms : undefined,
        store_ids: store_ids?.length ? store_ids : undefined,
        message: text,
        history: hist,
      }),
      signal: abortCtrl.signal,
    })

    if (!res.ok) {
      let detail = `请求失败 (${res.status})`
      try {
        const j = await res.json()
        detail = j.detail || detail
      } catch {
        /* ignore */
      }
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() || ''
      for (const part of parts) {
        const line = part.split('\n').find((l) => l.startsWith('data: '))
        if (!line) continue
        let ev
        try {
          ev = JSON.parse(line.slice(6))
        } catch {
          continue
        }
        if (ev.type === 'status') {
          assistant.status = ev.message || '查询中…'
        } else if (ev.type === 'token') {
          assistant.status = ''
          assistant.content += ev.text || ''
        } else if (ev.type === 'error') {
          assistant.status = ''
          assistant.streaming = false
          if (!assistant.content) assistant.content = ev.message || '分析失败'
          else assistant.content += `\n\n（${ev.message || '出错'}）`
          ElMessage.error(ev.message || '分析失败')
        } else if (ev.type === 'done') {
          assistant.status = ''
          assistant.streaming = false
        }
        await scrollBottom()
      }
    }
    assistant.streaming = false
    assistant.status = ''
    if (!assistant.content) assistant.content = '（无回复）'
  } catch (e) {
    if (e?.name === 'AbortError') {
      assistant.content = assistant.content || '（已取消）'
    } else {
      assistant.content = e?.message || '分析失败'
      ElMessage.error(assistant.content)
    }
    assistant.streaming = false
    assistant.status = ''
  } finally {
    sending.value = false
    abortCtrl = null
    await scrollBottom()
  }
}
</script>

<style scoped>
.ai-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 12px;
  margin: -8px 0 0;
}
.ai-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--dv-text-muted);
}
.ai-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ai-messages {
  flex: 1;
  min-height: 240px;
  overflow-y: auto;
  padding: 8px 4px;
  border: 1px solid var(--dv-border);
  border-radius: var(--dv-radius-sm);
  background: var(--dv-bg);
}
.ai-empty {
  padding: 24px 12px;
  text-align: center;
  color: var(--dv-text-muted);
  font-size: 13px;
}
.ai-msg {
  margin-bottom: 12px;
  padding: 0 8px;
}
.ai-msg.user .ai-bubble {
  background: var(--dv-primary-soft);
  margin-left: 24px;
}
.ai-msg.assistant .ai-bubble {
  background: var(--dv-surface);
  border: 1px solid var(--dv-border);
  margin-right: 24px;
}
.ai-role {
  font-size: 11px;
  color: var(--dv-text-muted);
  margin-bottom: 4px;
}
.ai-bubble {
  padding: 8px 10px;
  border-radius: var(--dv-radius-sm);
  font-size: 13px;
  line-height: 1.55;
  color: var(--dv-text);
  white-space: pre-wrap;
  word-break: break-word;
}
.ai-cursor {
  display: inline-block;
  margin-left: 1px;
  animation: blink 1s step-end infinite;
  color: var(--dv-primary);
}
.ai-status {
  margin-top: 4px;
  font-size: 12px;
  color: var(--dv-primary);
}
.ai-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ai-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
