<template>
  <el-dialog
    :model-value="modelValue"
    title="更换资质"
    width="560px"
    destroy-on-close
    append-to-body
    class="qual-dialog"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="onClosed"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" label-position="right">
      <el-form-item label="证件图片" prop="licenseFile">
        <el-upload
          class="license-upload"
          drag
          accept="image/jpeg,image/png,image/webp,image/bmp"
          :auto-upload="false"
          :show-file-list="false"
          :on-change="onLicenseChange"
        >
          <img v-if="previewUrl" :src="previewUrl" class="license-preview" alt="证件预览" />
          <div v-else class="license-placeholder">
            <el-icon :size="28"><UploadFilled /></el-icon>
            <div class="license-tip">点击或拖拽上传证件图片</div>
            <div class="license-hint">支持 jpg / png / webp，不超过 8MB</div>
          </div>
        </el-upload>
        <el-button v-if="previewUrl" link type="danger" class="clear-img" @click="clearLicense">
          清除图片
        </el-button>
      </el-form-item>

      <el-form-item label="美团门店ID" prop="mtStoreId">
        <el-input v-model="form.mtStoreId" clearable placeholder="请输入美团门店ID" />
      </el-form-item>

      <el-form-item label="饿了么门店ID" prop="elmStoreId">
        <el-input v-model="form.elmStoreId" clearable placeholder="请输入饿了么门店ID" />
      </el-form-item>

      <el-form-item label="京东门店ID" prop="jdStoreId">
        <el-input v-model="form.jdStoreId" clearable placeholder="请输入京东门店ID" />
      </el-form-item>

      <el-form-item label="团购门店ID" prop="tgStoreId">
        <el-input v-model="form.tgStoreId" clearable placeholder="请输入团购门店ID" />
      </el-form-item>

      <el-form-item label="经营者名称" prop="operatorName">
        <el-input v-model="form.operatorName" clearable placeholder="请输入经营者名称" />
      </el-form-item>

      <el-form-item label="社会信用代码" prop="creditCode">
        <el-input v-model="form.creditCode" clearable placeholder="请输入统一社会信用代码" />
      </el-form-item>

      <el-form-item label="法人" prop="legalPerson">
        <el-input v-model="form.legalPerson" clearable placeholder="请输入法人姓名" />
      </el-form-item>

      <el-form-item label="经营场所" prop="address">
        <el-input
          v-model="form.address"
          type="textarea"
          :rows="2"
          maxlength="200"
          show-word-limit
          placeholder="请输入经营场所"
        />
      </el-form-item>

      <el-form-item label="主业形态" prop="mainBusinessType">
        <el-input v-model="form.mainBusinessType" clearable placeholder="请输入主业形态" />
      </el-form-item>

      <el-form-item label="经营范围" prop="businessScope">
        <el-input
          v-model="form.businessScope"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="请输入经营范围"
        />
      </el-form-item>

      <el-form-item label="有效期至" prop="validUntil">
        <el-date-picker
          v-model="form.validUntil"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择有效期至"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="有效期编号" prop="licenseNo">
        <el-input v-model="form.licenseNo" clearable placeholder="请输入有效期编号" />
      </el-form-item>

      <el-form-item label="核准日期" prop="approvedAt">
        <el-date-picker
          v-model="form.approvedAt"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择核准日期"
          style="width: 100%"
        />
      </el-form-item>
    </el-form>

    <p v-if="jobHint" class="job-hint">{{ jobHint }}</p>

    <template #footer>
      <el-button :disabled="submitting" @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        {{ submitting ? '处理中…' : '提交' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const MAX_SIZE = 8 * 1024 * 1024
const POLL_MS = 3000
const POLL_MAX_MS = 5 * 60 * 1000

const formRef = ref(null)
const submitting = ref(false)
const previewUrl = ref('')
const licenseFile = ref(null)
const jobHint = ref('')
let pollTimer = null

const form = reactive({
  licenseFile: null,
  mtStoreId: '',
  elmStoreId: '',
  jdStoreId: '',
  tgStoreId: '',
  operatorName: '',
  creditCode: '',
  legalPerson: '',
  address: '',
  mainBusinessType: '',
  businessScope: '',
  validUntil: '',
  licenseNo: '',
  approvedAt: '',
})

/** 至少填一个平台门店 ID */
function validateAnyStoreId(_rule, _value, callback) {
  const ids = [form.mtStoreId, form.elmStoreId, form.jdStoreId, form.tgStoreId]
  if (ids.some((v) => String(v || '').trim())) {
    callback()
    return
  }
  callback(new Error('请至少填写一个平台门店ID'))
}

const rules = {
  licenseFile: [{ required: true, message: '请上传证件图片', trigger: 'change' }],
  mtStoreId: [{ validator: validateAnyStoreId, trigger: 'blur' }],
  elmStoreId: [{ validator: validateAnyStoreId, trigger: 'blur' }],
  jdStoreId: [{ validator: validateAnyStoreId, trigger: 'blur' }],
  tgStoreId: [{ validator: validateAnyStoreId, trigger: 'blur' }],
  operatorName: [{ required: true, message: '请输入经营者名称', trigger: 'blur' }],
  creditCode: [{ required: true, message: '请输入社会信用代码', trigger: 'blur' }],
  legalPerson: [{ required: true, message: '请输入法人', trigger: 'blur' }],
  address: [{ required: true, message: '请输入经营场所', trigger: 'blur' }],
  mainBusinessType: [{ required: true, message: '请输入主业形态', trigger: 'blur' }],
  businessScope: [{ required: true, message: '请输入经营范围', trigger: 'blur' }],
  validUntil: [{ required: true, message: '请选择有效期至', trigger: 'change' }],
  licenseNo: [{ required: true, message: '请输入有效期编号', trigger: 'blur' }],
  approvedAt: [{ required: true, message: '请选择核准日期', trigger: 'change' }],
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      stopPoll()
      jobHint.value = ''
    }
  },
)

function revokePreview() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function clearLicense() {
  revokePreview()
  licenseFile.value = null
  form.licenseFile = null
  formRef.value?.validateField('licenseFile')
}

function onLicenseChange(file) {
  const raw = file?.raw
  if (!raw) return
  if (!raw.type.startsWith('image/')) {
    ElMessage.warning('请上传图片文件')
    return
  }
  if (raw.size > MAX_SIZE) {
    ElMessage.warning('图片不能超过 8MB')
    return
  }
  revokePreview()
  licenseFile.value = raw
  form.licenseFile = raw
  previewUrl.value = URL.createObjectURL(raw)
  formRef.value?.validateField('licenseFile')
}

function reset() {
  stopPoll()
  revokePreview()
  licenseFile.value = null
  jobHint.value = ''
  Object.assign(form, {
    licenseFile: null,
    mtStoreId: '',
    elmStoreId: '',
    jdStoreId: '',
    tgStoreId: '',
    operatorName: '',
    creditCode: '',
    legalPerson: '',
    address: '',
    mainBusinessType: '',
    businessScope: '',
    validUntil: '',
    licenseNo: '',
    approvedAt: '',
  })
  formRef.value?.clearValidate()
}

function onClosed() {
  reset()
}

async function waitJobDone(jobId) {
  const started = Date.now()
  while (Date.now() - started < POLL_MAX_MS) {
    const job = await api.get(`/qualification/jobs/${jobId}`)
    if (job.status === 'success') {
      ElMessage.success(`任务 #${jobId} 已完成`)
      jobHint.value = `任务 #${jobId} 执行成功`
      return 'success'
    }
    if (job.status === 'failed') {
      const msg = job.error_message || '未知错误'
      ElMessage.error(`任务 #${jobId} 失败：${msg}`)
      jobHint.value = `任务 #${jobId} 失败：${msg}`
      return 'failed'
    }
    const label = job.status === 'running' ? '本机脚本执行中' : '等待本机 worker 领取'
    jobHint.value = `任务 #${jobId}：${label}…（请保持本机 worker 运行）`
    await new Promise((resolve) => {
      pollTimer = setTimeout(resolve, POLL_MS)
    })
  }
  ElMessage.warning(`任务 #${jobId} 仍在处理，可稍后在本机 worker 日志查看`)
  jobHint.value = `任务 #${jobId} 仍在排队或执行中`
  return 'pending'
}

async function submit() {
  const ok = await formRef.value?.validate().catch(() => false)
  if (!ok) return
  if (!licenseFile.value) {
    ElMessage.warning('请上传证件图片')
    return
  }

  submitting.value = true
  jobHint.value = ''
  try {
    const fd = new FormData()
    fd.append('license', licenseFile.value)
    fd.append('mt_store_id', form.mtStoreId.trim())
    fd.append('elm_store_id', form.elmStoreId.trim())
    fd.append('jd_store_id', form.jdStoreId.trim())
    fd.append('tg_store_id', form.tgStoreId.trim())
    fd.append('operator_name', form.operatorName.trim())
    fd.append('credit_code', form.creditCode.trim())
    fd.append('legal_person', form.legalPerson.trim())
    fd.append('address', form.address.trim())
    fd.append('main_business_type', form.mainBusinessType.trim())
    fd.append('business_scope', form.businessScope.trim())
    fd.append('valid_until', form.validUntil)
    fd.append('license_no', form.licenseNo.trim())
    fd.append('approved_at', form.approvedAt)

    const job = await api.post('/qualification/jobs', fd)
    ElMessage.success(`已创建任务 #${job.id}，等待本机 worker 执行`)
    jobHint.value = `任务 #${job.id}：等待本机 worker 领取…`
    const finalStatus = await waitJobDone(job.id)
    if (finalStatus === 'success') {
      emit('update:modelValue', false)
    }
  } catch (e) {
    const detail = e.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '提交失败，请稍后重试')
  } finally {
    submitting.value = false
    stopPoll()
  }
}
</script>

<style scoped>
.license-upload {
  width: 100%;
}

.license-upload :deep(.el-upload) {
  width: 100%;
}

.license-upload :deep(.el-upload-dragger) {
  width: 100%;
  padding: 16px;
  border-radius: var(--dv-radius-sm);
}

.license-preview {
  display: block;
  max-width: 100%;
  max-height: 220px;
  margin: 0 auto;
  object-fit: contain;
  border-radius: 6px;
}

.license-placeholder {
  color: var(--dv-text-muted);
  padding: 12px 0;
}

.license-tip {
  margin-top: 8px;
  font-size: 13px;
  color: var(--dv-text-secondary);
}

.license-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--dv-text-muted);
}

.clear-img {
  margin-top: 4px;
}

.job-hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--dv-text-secondary);
  line-height: 1.4;
}
</style>
