<script setup lang="ts">
import { computed, getCurrentInstance, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  listBatches,
  listFiles,
  loadBatch,
  loadSummary,
  pollPreview,
  repairBatch,
  retryBatch,
  runTask,
  startPreview,
  stopTask,
  type PluginApi,
} from '../config/api'
import type {
  ArchiveConfig,
  ArchiveFile,
  ArchiveTask,
  Batch,
  BatchPage,
  FilePage,
  PreviewData,
  SummaryPayload,
} from '../config/types'
import { cloneTask, createArchiveTask, normalizeArchiveConfig } from '../config/values'
import archiveLogo from '../assets/archive-logo.png'

type NoticeType = 'success' | 'warning' | 'error' | 'info'
type HostToast = ((message: string) => unknown) & Partial<Record<NoticeType, (message: string) => unknown>>
type HostConfirm = (options?: {
  type?: 'info' | 'warn' | 'error'
  title?: string
  content?: string
  confirmText?: string
  cancelText?: string
}) => Promise<boolean>

const props = defineProps<{
  /** 宿主传入的动态配置对象；进入页面前会被规范化为完整配置。 */
  initialConfig?: unknown
  /** 宿主注入的已认证插件 API 客户端。 */
  api?: PluginApi
}>()

const emit = defineEmits<{
  /** 请求宿主持久化完整配置对象。 */
  save: [ArchiveConfig]
  /** 请求宿主关闭插件配置。 */
  close: []
  /** 请求宿主提供适合表格和详情页的横向空间。 */
  layout: [{ maxWidth: string }]
}>()

emit('layout', { maxWidth: '68rem' })

type ViewKey = 'overview' | 'tasks' | 'batches' | 'files'

const instance = getCurrentInstance()
const locale = computed(() => String(instance?.appContext.config.globalProperties.$i18n?.locale ?? 'zh-CN'))
const hostToast = inject<HostToast | null>('moviepilot:toast', null)
const hostConfirm = inject<HostConfirm | null>('moviepilot:confirm', null)
const README_URL = 'https://github.com/InfinityPacer/MoviePilot-Plugins/blob/main/plugins.v3/archivemanager/README.md'
const draft = ref<ArchiveConfig>(normalizeArchiveConfig(props.initialConfig))
const original = ref<ArchiveConfig>(normalizeArchiveConfig(props.initialConfig))
const activeView = ref<ViewKey>('overview')
const activeTaskId = ref(draft.value.tasks[0]?.id ?? '')
const editorOpen = ref(false)
const editingTaskId = ref<string | null>(null)
const taskEditor = ref<ArchiveTask>(createArchiveTask())
const includePatternsText = ref('')
const excludePatternsText = ref('')
const minFreeGiB = ref(1)
const mobileNavOpen = ref(false)
const compatibilityOpen = ref(false)
const compatibilityReason = ref<'format' | 'encrypt_names'>('format')
const pendingFormat = ref<'7z' | 'zip' | null>(null)

const summary = ref<SummaryPayload | null>(null)
const summaryState = ref<'loading' | 'available' | 'unavailable'>('loading')
const notice = ref<{ type: NoticeType; text: string } | null>(null)
const operationBusy = ref(false)
const operationMessage = ref('')

const previewOpen = ref(false)
const previewJobId = ref('')
const previewState = ref<'idle' | 'running' | 'complete' | 'failed'>('idle')
const previewResult = ref<PreviewData | null>(null)
const previewMessage = ref('')

const batchTaskFilter = ref(activeTaskId.value)
const batchStatusFilter = ref('')
const batchPage = ref(1)
const batchPageSize = ref(30)
const batchData = ref<BatchPage>({ items: [], total: 0 })
const batchLoading = ref(false)
const batchDialogOpen = ref(false)
const selectedBatch = ref<Batch | null>(null)
const batchDetailLoading = ref(false)

const fileTaskFilter = ref(activeTaskId.value)
const fileDirectory = ref('')
const fileQuery = ref('')
const fileStatus = ref('')
const filePage = ref(1)
const filePageSize = ref(30)
const fileData = ref<FilePage>({ items: [], directories: [], total: 0 })
const fileLoading = ref(false)

let previewTimer: ReturnType<typeof setTimeout> | undefined
let operationTimer: ReturnType<typeof setInterval> | undefined
let summaryRequestToken = 0
let batchRequestToken = 0
let fileRequestToken = 0
let disposed = false

const tasksById = computed(() => new Map(draft.value.tasks.map(task => [task.id, task])))
const selectedTask = computed(() => tasksById.value.get(activeTaskId.value) ?? draft.value.tasks[0] ?? null)
const hasFileTaskSelection = computed(() => Boolean(fileTaskFilter.value && tasksById.value.has(fileTaskFilter.value)))
const isDirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(original.value))
const summaryValue = computed<SummaryPayload>(
  () =>
    summary.value ?? {
      archived_files: 0,
      archive_count: 0,
      source_bytes: 0,
      archive_bytes: 0,
      deleted_files: 0,
      failed_batches: 0,
      pending_files: 0,
      running: null,
      queued: [],
      config_error: '',
      last_error: null,
      tasks: [],
    },
)
const lastErrorMessage = computed(() => {
  const error = summaryValue.value.last_error
  return typeof error === 'string' ? error : error?.message || ''
})
const queuedTaskNames = computed(() =>
  summaryValue.value.queued.map(taskId => tasksById.value.get(taskId)?.name ?? taskId).filter(Boolean),
)
const batchPageCount = computed(() => Math.max(1, Math.ceil(batchData.value.total / batchPageSize.value)))
const filePageCount = computed(() => Math.max(1, Math.ceil(fileData.value.total / filePageSize.value)))
const breadcrumbs = computed(() => {
  const parts = fileDirectory.value.split('/').filter(Boolean)
  return [
    { title: '根目录', path: '' },
    ...parts.map((part, index) => ({ title: part, path: parts.slice(0, index + 1).join('/') })),
  ]
})
const taskEditorTitle = computed(() => (editingTaskId.value ? '编辑归档任务' : '新增归档任务'))
const taskEditorHasSavedPassword = computed(() => Boolean(taskEditor.value.password_set))
const namingExamples = computed(() => {
  const values = {
    task_name: taskEditor.value.name || '归档任务',
    date: '20260911',
    time: '040020',
    id: '7f3a9c',
    sequence: '0001',
  }
  const render = (template: string, fallback: string): string => {
    const source = template.trim() || fallback
    const rendered = source.replace(/\{([^{}]+)\}/g, (match, field: string) => {
      if (field.startsWith('%')) {
        return field.replace(
          /%Y|%y|%m|%d|%H|%I|%M|%S/g,
          token =>
            ({ '%Y': '2026', '%y': '26', '%m': '09', '%d': '11', '%H': '04', '%I': '04', '%M': '00', '%S': '20' })[
              token
            ] || token,
        )
      }
      return field in values ? values[field as keyof typeof values] : match
    })
    return rendered.trim() || fallback
  }
  const archiveStem = render(taskEditor.value.archive_name_template, values.id)
  return {
    batch: render(taskEditor.value.batch_name_template, `${values.date}_${values.sequence}`),
    archive: `${archiveStem}.${taskEditor.value.format}`,
  }
})

const viewLabels: Record<ViewKey, { title: string; icon: string; summary: string }> = {
  overview: { title: '概览', icon: 'mdi-view-dashboard-outline', summary: '任务、运行状态和归档策略' },
  tasks: { title: '任务', icon: 'mdi-format-list-checks', summary: '管理归档任务、命名和执行策略' },
  batches: { title: '批次', icon: 'mdi-package-variant-closed', summary: '查看归档批次、清理和校验结果' },
  files: { title: '文件', icon: 'mdi-file-search-outline', summary: '按目录和状态检索归档文件' },
}

const batchStatusOptions: Array<{ title: string; value: string }> = [
  { title: '全部状态', value: '' },
  { title: '构建中', value: 'building' },
  { title: '校验中', value: 'verifying' },
  { title: '发布中', value: 'publishing' },
  { title: '待补全清单', value: 'manifest_pending' },
  { title: '已完成', value: 'completed' },
  { title: '清理中', value: 'cleaning' },
  { title: '清理失败', value: 'cleanup_failed' },
  { title: '失败', value: 'failed' },
  { title: '已取消', value: 'cancelled' },
  { title: '已中断', value: 'interrupted' },
  { title: '已替代', value: 'superseded' },
]

const groupingOptions = [
  { title: '不分组', value: 'none' },
  { title: '按目录', value: 'directory' },
  { title: '按日期', value: 'date' },
  { title: '目录 + 日期', value: 'directory_date' },
]
const timeGrainOptions = [
  { title: '小时', value: 'hour' },
  { title: '天', value: 'day' },
  { title: '月', value: 'month' },
]
const formatOptions = [
  { title: '7z', value: '7z' },
  { title: 'ZIP', value: 'zip' },
]
const compressionOptions = [
  { title: '存储（不压缩）', value: 'store' },
  { title: '快速', value: 'fast' },
  { title: '标准', value: 'normal' },
  { title: '高压缩', value: 'high' },
]
const encryptionOptions = [
  { title: '不加密', value: 'none' },
  { title: 'AES-256', value: 'aes256' },
]
const notificationEventOptions = [
  { title: '归档成功', value: 'success' },
  { title: '归档失败', value: 'failure' },
  { title: '其他', value: 'other' },
]

function setNotice(text: string, type: NoticeType = 'info'): void {
  const notify = hostToast?.[type] ?? hostToast?.info ?? (typeof hostToast === 'function' ? hostToast : undefined)
  if (notify) {
    try {
      void notify(text)
      notice.value = null
      return
    } catch {
      // 宿主通知属于可选动态边界；组件内提示仍然保留。
    }
  }
  notice.value = { text, type }
}

function ensureSelection(): void {
  if (!draft.value.tasks.some(task => task.id === activeTaskId.value))
    activeTaskId.value = draft.value.tasks[0]?.id ?? ''
  if (!draft.value.tasks.some(task => task.id === batchTaskFilter.value)) batchTaskFilter.value = activeTaskId.value
  if (!draft.value.tasks.some(task => task.id === fileTaskFilter.value)) fileTaskFilter.value = activeTaskId.value
}

function selectTask(taskId: string): void {
  activeTaskId.value = taskId
  batchTaskFilter.value = taskId
  fileTaskFilter.value = taskId
}

function selectMobileView(view: ViewKey): void {
  activeView.value = view
  mobileNavOpen.value = false
}

function openTaskEditor(task?: ArchiveTask): void {
  const next = cloneTask(task ?? createArchiveTask())
  taskEditor.value = next
  editingTaskId.value = task?.id ?? null
  includePatternsText.value = next.include_patterns.join('\n')
  excludePatternsText.value = next.exclude_patterns.join('\n')
  minFreeGiB.value = Number((next.min_free_bytes / 1024 ** 3).toFixed(2))
  editorOpen.value = true
}

function parsePatterns(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map(pattern => pattern.trim())
    .filter(Boolean)
}

function prepareEditorTask(): ArchiveTask {
  const task = cloneTask(taskEditor.value)
  task.include_patterns = parsePatterns(includePatternsText.value)
  task.exclude_patterns = parsePatterns(excludePatternsText.value)
  task.min_free_bytes = Math.max(0, Number(minFreeGiB.value) || 0) * 1024 ** 3
  if (task.delete_source) task.verify = true
  if (task.format === 'zip') task.encrypt_names = false
  if (task.password.length > 0) task.password_set = true
  return task
}

function saveTaskEditor(): void {
  const task = prepareEditorTask()
  const index = draft.value.tasks.findIndex(item => item.id === task.id)
  if (index >= 0) draft.value.tasks.splice(index, 1, task)
  else draft.value.tasks.push(task)
  selectTask(task.id)
  editorOpen.value = false
  setNotice('任务已更新，保存配置后才会生效。', 'success')
}

function cancelTaskEditor(): void {
  editorOpen.value = false
}

async function removeTask(task: ArchiveTask): Promise<void> {
  let confirmed = false
  if (hostConfirm) {
    try {
      confirmed = await hostConfirm({
        type: 'error',
        title: '删除归档任务',
        content: `确定删除任务“${task.name}”吗？保存后该任务将不再执行。`,
        confirmText: '删除任务',
        cancelText: '取消',
      })
    } catch {
      confirmed = false
    }
  }
  if (!confirmed) return
  draft.value.tasks = draft.value.tasks.filter(item => item.id !== task.id)
  ensureSelection()
  setNotice('任务已从配置草稿移除。', 'success')
}

function handleDeleteSource(value: unknown): void {
  taskEditor.value.delete_source = value === true
  if (taskEditor.value.delete_source) {
    taskEditor.value.verify = true
    setNotice('删除源文件已启用，归档校验已强制开启。', 'warning')
  }
}

function handleVerify(value: unknown): void {
  if (taskEditor.value.delete_source && value !== true) {
    taskEditor.value.verify = true
    setNotice('删除源文件必须启用归档校验。', 'warning')
    return
  }
  taskEditor.value.verify = value === true
}

function requestFormat(value: unknown): void {
  const format = value === 'zip' ? 'zip' : '7z'
  if (format === 'zip' && taskEditor.value.encrypt_names) {
    pendingFormat.value = format
    compatibilityReason.value = 'format'
    compatibilityOpen.value = true
    return
  }
  taskEditor.value.format = format
}

function requestEncryptNames(value: unknown): void {
  if (value === true && taskEditor.value.format === 'zip') {
    compatibilityReason.value = 'encrypt_names'
    pendingFormat.value = null
    compatibilityOpen.value = true
    return
  }
  taskEditor.value.encrypt_names = value === true
}

function acceptCompatibilityChange(): void {
  if (compatibilityReason.value === 'format' && pendingFormat.value) {
    taskEditor.value.format = pendingFormat.value
    taskEditor.value.encrypt_names = false
  } else {
    taskEditor.value.format = '7z'
    taskEditor.value.encrypt_names = true
  }
  compatibilityOpen.value = false
  pendingFormat.value = null
}

function cancelCompatibilityChange(): void {
  compatibilityOpen.value = false
  pendingFormat.value = null
}

function handleEncryption(value: unknown): void {
  taskEditor.value.encryption = value === 'aes256' ? 'aes256' : 'none'
  if (taskEditor.value.encryption === 'aes256' && taskEditor.value.format === '7z' && !taskEditor.value.encrypt_names) {
    taskEditor.value.encrypt_names = true
  }
}

function saveConfig(): void {
  const payload = normalizeArchiveConfig(draft.value)
  draft.value = payload
  original.value = normalizeArchiveConfig(payload)
  emit('save', normalizeArchiveConfig(payload))
  setNotice('配置已提交给宿主保存。', 'success')
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat(locale.value.startsWith('en') ? 'en-US' : 'zh-CN').format(value || 0)
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

function formatDate(value: string): string {
  if (!value) return '-'
  const timestamp = new Date(value)
  return Number.isNaN(timestamp.getTime())
    ? value
    : timestamp.toLocaleString(locale.value.startsWith('en') ? 'en-US' : 'zh-CN')
}

function statusLabel(status?: string): string {
  const normalized = status || 'pending'
  return (
    batchStatusOptions.find(item => item.value === normalized)?.title ??
    ({
      pending: '待处理',
      archived: '已归档',
      retained: '已归档，源文件保留',
      deleting: '清理中',
      deleted: '已删除源文件',
      failed: '失败',
      missing: '源文件已缺失',
      changed: '源文件已变化',
      superseded: '已替代',
    }[normalized] ||
      normalized)
  )
}

function statusColor(status?: string): string {
  const normalized = status || 'pending'
  if (['completed', 'archived', 'retained', 'deleted'].includes(normalized)) return 'success'
  if (['failed', 'cleanup_failed', 'missing', 'changed'].includes(normalized)) return 'error'
  if (['cancelled', 'interrupted', 'superseded'].includes(normalized)) return 'warning'
  return 'primary'
}

function batchFileStatus(file: ArchiveFile, batch: Batch): string {
  const recordedStatus = file.status || batch.cleanup?.[file.relative_path]
  if (recordedStatus) return recordedStatus
  if (batch.status === 'completed') return 'archived'
  return batch.status || 'pending'
}

function phaseLabel(phase: string): string {
  return (
    {
      history: '历史队列',
      incremental: '新增文件',
      waiting_capacity: '等待空间',
      waiting_retry: '等待重试',
      idle: '空闲',
      stopped: '已停止',
    }[phase] || phase
  )
}

function progressLabel(progress: SummaryPayload['tasks'][number]): string {
  if (progress.phase === 'history') {
    return `历史 ${formatNumber(progress.history_archived)} / ${formatNumber(progress.history_total)}，剩余 ${formatNumber(progress.history_remaining)}`
  }
  if (progress.phase === 'waiting_capacity') return progress.reason || '等待外部工具移走归档成品'
  if (progress.phase === 'waiting_retry') return progress.reason || '存在失败批次，等待重试后继续'
  return (
    progress.reason || `积压 ${formatNumber(progress.pending_archives)} 批 · ${formatBytes(progress.pending_bytes)}`
  )
}

async function refreshSummary(): Promise<void> {
  const requestToken = ++summaryRequestToken
  const payload = await loadSummary(props.api)
  if (disposed || requestToken !== summaryRequestToken) return
  summary.value = payload
  summaryState.value = payload ? 'available' : 'unavailable'
}

function clearOperationPolling(): void {
  if (operationTimer) clearInterval(operationTimer)
  operationTimer = undefined
  operationBusy.value = false
  operationMessage.value = ''
}

function startOperationPolling(): void {
  clearOperationPolling()
  operationBusy.value = true
  let attempts = 0
  operationTimer = setInterval(() => {
    attempts += 1
    void refreshSummary()
    if (activeView.value === 'batches') void loadBatchPage()
    if (attempts >= 40 || (!summary.value?.running && (summary.value?.queued.length ?? 0) === 0))
      clearOperationPolling()
  }, 2500)
}

async function executeRun(taskId = activeTaskId.value): Promise<void> {
  if (!taskId) {
    setNotice('请先选择一个归档任务。', 'warning')
    return
  }
  operationMessage.value = '正在提交归档任务…'
  const result = await runTask(props.api, taskId)
  if (!result) {
    setNotice('归档任务提交失败，请检查插件状态。', 'error')
    operationMessage.value = ''
    return
  }
  setNotice(result.queued ? '归档任务已加入队列。' : '归档任务已启动。', 'success')
  operationMessage.value = '归档任务运行中…'
  await refreshSummary()
  startOperationPolling()
}

async function executeStop(): Promise<void> {
  operationMessage.value = '正在请求停止…'
  const result = await stopTask(props.api, summary.value?.running?.task_id)
  if (!result) {
    setNotice('停止请求失败，请稍后重试。', 'error')
    operationMessage.value = ''
    return
  }
  setNotice('已发送停止请求，正在等待运行状态收敛。', 'warning')
  await refreshSummary()
  startOperationPolling()
}

async function executeBatchAction(action: 'retry' | 'repair', batch: Batch): Promise<void> {
  operationMessage.value = action === 'retry' ? '正在重新构建批次…' : '正在补全清单…'
  const result = action === 'retry' ? await retryBatch(props.api, batch.id) : await repairBatch(props.api, batch.id)
  if (!result) {
    setNotice(action === 'retry' ? '批次重试失败。' : '清单补全失败。', 'error')
    operationMessage.value = ''
    return
  }
  setNotice(action === 'retry' ? '批次已加入重试队列。' : '清单补全已加入队列。', 'success')
  batchDialogOpen.value = false
  await refreshSummary()
  startOperationPolling()
}

async function startPreviewForTask(task: ArchiveTask): Promise<void> {
  previewOpen.value = true
  previewState.value = 'running'
  previewResult.value = null
  previewMessage.value = '正在扫描源目录…'
  const result = await startPreview(props.api, task)
  if (!result?.job_id) {
    previewState.value = 'failed'
    previewMessage.value = '预览任务提交失败，请检查目录和插件状态。'
    return
  }
  previewJobId.value = result.job_id
  await pollPreviewJob(result.job_id)
}

async function pollPreviewJob(jobId: string): Promise<void> {
  const startedAt = Date.now()
  const poll = async (): Promise<void> => {
    if (disposed || !previewOpen.value || Date.now() - startedAt > 120000) {
      if (!disposed && previewState.value === 'running') {
        previewState.value = 'failed'
        previewMessage.value = '预览等待超时，请稍后重试。'
      }
      return
    }
    const result = await pollPreview(props.api, jobId)
    if (result?.status === 'complete') {
      previewState.value = 'complete'
      previewResult.value = result.data
      previewMessage.value = result.message || '预览完成。'
      return
    }
    if (result?.status === 'failed') {
      previewState.value = 'failed'
      previewMessage.value = result.message || '预览失败。'
      return
    }
    previewMessage.value = result?.message || '正在扫描源目录…'
    previewTimer = setTimeout(() => void poll(), 1200)
  }
  await poll()
}

async function loadBatchPage(): Promise<void> {
  const requestToken = ++batchRequestToken
  batchLoading.value = true
  try {
    const result = await listBatches(props.api, {
      task_id: batchTaskFilter.value || undefined,
      page: batchPage.value,
      page_size: batchPageSize.value,
      status: batchStatusFilter.value || undefined,
    })
    if (!disposed && requestToken === batchRequestToken && activeView.value === 'batches') batchData.value = result
  } finally {
    if (requestToken === batchRequestToken) batchLoading.value = false
  }
}

async function openBatch(batch: Batch): Promise<void> {
  batchDialogOpen.value = true
  selectedBatch.value = batch
  batchDetailLoading.value = true
  selectedBatch.value = (await loadBatch(props.api, batch.id)) ?? batch
  batchDetailLoading.value = false
}

async function loadFilePage(): Promise<void> {
  const requestToken = ++fileRequestToken
  if (!hasFileTaskSelection.value) {
    fileData.value = { items: [], directories: [], total: 0 }
    fileLoading.value = false
    return
  }
  fileLoading.value = true
  try {
    const result = await listFiles(props.api, {
      task_id: fileTaskFilter.value || undefined,
      directory: fileDirectory.value,
      query: fileQuery.value.trim() || undefined,
      status: fileStatus.value || undefined,
      page: filePage.value,
      page_size: filePageSize.value,
    })
    if (!disposed && requestToken === fileRequestToken && activeView.value === 'files') fileData.value = result
  } finally {
    if (requestToken === fileRequestToken) fileLoading.value = false
  }
}

function submitFileSearch(): void {
  if (filePage.value !== 1) {
    filePage.value = 1
    return
  }
  void loadFilePage()
}

function navigateDirectory(path: string): void {
  fileDirectory.value = path
  filePage.value = 1
}

function closePreview(): void {
  previewOpen.value = false
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = undefined
}

watch(
  () => props.initialConfig,
  value => {
    const normalized = normalizeArchiveConfig(value)
    draft.value = normalized
    original.value = normalizeArchiveConfig(normalized)
    ensureSelection()
  },
  { deep: true },
)

watch([activeView, batchTaskFilter, batchStatusFilter, batchPage, batchPageSize], ([view]) => {
  if (view === 'batches') void loadBatchPage()
})

watch([activeView, fileTaskFilter, fileDirectory, fileStatus, filePage, filePageSize], ([view]) => {
  if (view === 'files') void loadFilePage()
})

watch(
  () => draft.value.tasks.map(task => task.id),
  () => ensureSelection(),
)

onMounted(() => {
  void refreshSummary()
})

onBeforeUnmount(() => {
  disposed = true
  if (previewTimer) clearTimeout(previewTimer)
  clearOperationPolling()
})
</script>

<template>
  <section class="archive-config">
    <form @submit.prevent="saveConfig">
      <header class="archive-header">
        <div class="archive-header__brand">
          <img :src="archiveLogo" alt="" class="archive-header__logo" />
          <div class="archive-header__identity">
            <div class="archive-header__crumbs">
              <span>MoviePilot</span>
              <VIcon icon="mdi-chevron-right" size="14" />
              <span>插件</span>
            </div>
            <div class="archive-header__title-row">
              <h1>压缩归档</h1>
              <VChip color="primary" size="x-small" variant="tonal">BETA</VChip>
            </div>
          </div>
        </div>
        <div class="archive-header__actions">
          <VBtn
            class="archive-header__run"
            :disabled="!activeTaskId || operationBusy"
            prepend-icon="mdi-play"
            type="button"
            variant="tonal"
            @click="executeRun()"
          >
            运行一次
          </VBtn>
          <VBtn
            class="archive-header__save"
            color="primary"
            :disabled="!isDirty"
            prepend-icon="mdi-content-save"
            type="submit"
          >
            保存修改
          </VBtn>
          <VBtn class="archive-header__close-action" prepend-icon="mdi-close" variant="outlined" @click="emit('close')">
            关闭
          </VBtn>
          <VBtn
            aria-label="关闭"
            class="archive-header__close-icon"
            icon
            size="small"
            variant="text"
            @click="emit('close')"
          >
            <VIcon icon="mdi-close" />
          </VBtn>
        </div>
      </header>

      <div class="archive-body">
        <VAlert
          v-if="notice"
          :type="notice.type"
          closable
          density="compact"
          variant="tonal"
          @click:close="notice = null"
        >
          {{ notice.text }}
        </VAlert>
        <VAlert v-if="summaryValue.config_error" class="archive-alert" type="error" variant="tonal">
          <strong>配置不可运行</strong>
          <span>{{ summaryValue.config_error }}</span>
        </VAlert>
        <VAlert v-if="lastErrorMessage" class="archive-alert" type="warning" variant="tonal">
          <strong>最近一次运行失败</strong>
          <span>{{ lastErrorMessage }}</span>
        </VAlert>
        <div class="archive-workspace">
          <aside class="archive-nav">
            <div class="archive-nav__heading">工作区</div>
            <VList class="archive-nav__list" density="compact" nav>
              <VListItem
                v-for="(view, key) in viewLabels"
                :key="key"
                :active="activeView === key"
                :prepend-icon="view.icon"
                :title="view.title"
                color="primary"
                rounded="lg"
                @click="activeView = key"
              />
            </VList>
            <section class="archive-nav__help">
              <strong class="archive-nav__help-title">关于插件</strong>
              <p>文件压缩归档，支持独立清单、校验和可选加密。</p>
              <VBtn
                :href="README_URL"
                append-icon="mdi-open-in-new"
                class="archive-nav__help-link"
                color="primary"
                rel="noopener noreferrer"
                size="small"
                target="_blank"
                variant="text"
              >
                查看文档
              </VBtn>
            </section>
          </aside>

          <main class="archive-main">
            <div class="archive-main__heading">
              <div>
                <div class="archive-main__title">
                  <VIcon :icon="viewLabels[activeView].icon" color="primary" size="21" />
                  <h2>{{ viewLabels[activeView].title }}</h2>
                </div>
                <p>{{ viewLabels[activeView].summary }}</p>
              </div>
              <div class="archive-main__heading-actions">
                <VBtn
                  aria-label="切换工作区"
                  class="archive-mobile-nav"
                  icon
                  size="small"
                  variant="tonal"
                  @click="mobileNavOpen = true"
                >
                  <VIcon icon="mdi-view-list-outline" />
                  <VTooltip activator="parent" text="切换工作区" />
                </VBtn>
                <VBtn
                  aria-label="刷新当前数据"
                  icon
                  size="small"
                  variant="text"
                  @click="
                    activeView === 'batches'
                      ? loadBatchPage()
                      : activeView === 'files'
                        ? loadFilePage()
                        : refreshSummary()
                  "
                >
                  <VIcon icon="mdi-refresh" />
                  <VTooltip activator="parent" text="刷新当前数据" />
                </VBtn>
              </div>
            </div>

            <section v-if="activeView === 'overview' || activeView === 'tasks'" class="archive-view archive-overview">
              <template v-if="activeView === 'overview'">
                <div class="archive-metrics" aria-label="归档统计">
                  <div class="archive-metric">
                    <VIcon icon="mdi-file-check-outline" />
                    <span>已归档文件</span>
                    <strong>{{ formatNumber(summaryValue.archived_files) }}</strong>
                  </div>
                  <div class="archive-metric">
                    <VIcon icon="mdi-package-variant-closed" />
                    <span>归档批次</span>
                    <strong>{{ formatNumber(summaryValue.archive_count) }}</strong>
                  </div>
                  <div class="archive-metric">
                    <VIcon icon="mdi-database-arrow-down-outline" />
                    <span>源文件体积</span>
                    <strong>{{ formatBytes(summaryValue.source_bytes) }}</strong>
                  </div>
                  <div class="archive-metric">
                    <VIcon icon="mdi-archive-arrow-down-outline" />
                    <span>归档体积</span>
                    <strong>{{ formatBytes(summaryValue.archive_bytes) }}</strong>
                  </div>
                  <div class="archive-metric">
                    <VIcon icon="mdi-delete-outline" />
                    <span>已删除源文件</span>
                    <strong>{{ formatNumber(summaryValue.deleted_files) }}</strong>
                  </div>
                  <div class="archive-metric" :class="{ 'archive-metric--warning': summaryValue.failed_batches > 0 }">
                    <VIcon icon="mdi-alert-circle-outline" />
                    <span>失败批次</span>
                    <strong>{{ formatNumber(summaryValue.failed_batches) }}</strong>
                  </div>
                </div>
                <div v-if="summaryState === 'loading'" class="archive-inline-state">
                  <VProgressCircular color="primary" indeterminate size="18" width="2" /> 正在读取运行概况…
                </div>
                <div
                  v-else-if="summaryState === 'unavailable'"
                  class="archive-inline-state archive-inline-state--error"
                >
                  <VIcon icon="mdi-cloud-alert-outline" />运行概况暂不可用，配置编辑仍可继续。
                </div>
                <div v-if="summaryValue.running || queuedTaskNames.length" class="archive-running">
                  <div class="archive-running__copy">
                    <VProgressCircular color="primary" indeterminate size="20" width="2" />
                    <div>
                      <strong>{{ operationMessage || '归档任务正在运行' }}</strong>
                      <span v-if="summaryValue.running"
                        >{{ tasksById.get(summaryValue.running.task_id)?.name || summaryValue.running.task_id }} ·
                        {{ summaryValue.running.phase }}</span
                      >
                      <span v-else>排队任务：{{ queuedTaskNames.join('、') }}</span>
                    </div>
                  </div>
                  <VBtn
                    color="warning"
                    :disabled="!summaryValue.running"
                    prepend-icon="mdi-stop"
                    variant="tonal"
                    @click="executeStop"
                    >停止</VBtn
                  >
                </div>
                <section v-if="summaryValue.tasks.length" class="archive-section archive-progress">
                  <div class="archive-section__header">
                    <div>
                      <h3>任务队列进度</h3>
                      <p>历史快照优先完成；空间不足时等待外部工具移走已发布成品。</p>
                    </div>
                    <VChip color="primary" size="small" variant="tonal"
                      >{{ summaryValue.tasks.filter(task => task.active).length }} 个活动任务</VChip
                    >
                  </div>
                  <div class="archive-progress__list">
                    <div v-for="progress in summaryValue.tasks" :key="progress.task_id" class="archive-progress__row">
                      <div class="archive-progress__identity">
                        <VIcon
                          :color="progress.active ? 'primary' : 'disabled'"
                          :icon="progress.active ? 'mdi-progress-clock' : 'mdi-check-circle-outline'"
                        /><strong>{{ tasksById.get(progress.task_id)?.name || progress.task_id }}</strong>
                      </div>
                      <VChip
                        :color="
                          progress.phase === 'waiting_capacity' || progress.phase === 'waiting_retry'
                            ? 'warning'
                            : progress.active
                              ? 'primary'
                              : 'default'
                        "
                        size="small"
                        variant="tonal"
                        >{{ phaseLabel(progress.phase) }}</VChip
                      ><span class="archive-progress__detail">{{ progressLabel(progress) }}</span
                      ><span class="archive-progress__capacity"
                        >积压 {{ formatNumber(progress.pending_archives) }} 批 · {{ formatBytes(progress.pending_bytes)
                        }}<br />可用空间 {{ formatBytes(progress.free_bytes) }}</span
                      >
                    </div>
                  </div>
                </section>
                <section class="archive-section archive-overview-controls">
                  <div class="archive-section__header">
                    <div>
                      <h3>运行设置</h3>
                      <p>控制归档服务是否启用，以及哪些事件发送宿主通知。</p>
                    </div>
                  </div>
                  <div class="archive-form-grid archive-form-grid--three">
                    <VSwitch
                      v-model="draft.enabled"
                      aria-label="启用"
                      color="primary"
                      density="compact"
                      hide-details
                      label="启用"
                    /><VSwitch
                      v-model="draft.notify"
                      aria-label="发送通知"
                      color="primary"
                      density="compact"
                      hide-details
                      label="发送通知"
                    /><VSelect
                      aria-label="通知事件"
                      v-model="draft.notify_events"
                      :items="notificationEventOptions"
                      chips
                      closable-chips
                      hide-details
                      item-title="title"
                      item-value="value"
                      label="通知事件"
                      multiple
                      variant="outlined"
                    />
                  </div>
                </section>
              </template>

              <div
                v-if="activeView === 'tasks'"
                class="archive-task-layout"
                :class="{ 'archive-task-layout--editing': editorOpen }"
              >
                <section v-if="!editorOpen" class="archive-section archive-task-list">
                  <div class="archive-section__header">
                    <div>
                      <h3>归档任务</h3>
                      <p>{{ draft.tasks.length }} 个任务，点击任务查看详情。</p>
                    </div>
                    <VBtn aria-label="新增归档任务" icon size="small" variant="tonal" @click="openTaskEditor()"
                      ><VIcon icon="mdi-plus"
                    /></VBtn>
                  </div>
                  <div v-if="draft.tasks.length === 0" class="archive-empty">
                    <VIcon icon="mdi-archive-off-outline" size="34" /><strong>还没有归档任务</strong
                    ><span>创建任务后可预览文件并手动运行。</span
                    ><VBtn color="primary" prepend-icon="mdi-plus" variant="tonal" @click="openTaskEditor()"
                      >创建第一个任务</VBtn
                    >
                  </div>
                  <VList v-else class="archive-task-list__items" lines="two" nav>
                    <VListItem
                      v-for="task in draft.tasks"
                      :key="task.id"
                      :active="activeTaskId === task.id"
                      :title="task.name || '未命名任务'"
                      :subtitle="`${task.source_dir || '未设置源目录'} · ${task.format.toUpperCase()}`"
                      color="primary"
                      rounded="lg"
                      @click="selectTask(task.id)"
                    >
                      <template #prepend
                        ><VIcon
                          :color="task.enabled ? 'success' : 'disabled'"
                          :icon="task.enabled ? 'mdi-check-circle-outline' : 'mdi-pause-circle-outline'"
                      /></template>
                      <template #append
                        ><VChip :color="task.enabled ? 'success' : 'default'" size="x-small" variant="tonal">{{
                          task.enabled ? '启用' : '停用'
                        }}</VChip></template
                      >
                    </VListItem>
                  </VList>
                </section>

                <section v-if="selectedTask && !editorOpen" class="archive-section archive-task-detail">
                  <div class="archive-section__header">
                    <div>
                      <h3>{{ selectedTask.name }}</h3>
                      <p>{{ selectedTask.source_dir || '尚未设置源目录' }}</p>
                    </div>
                    <div class="archive-section__actions">
                      <VBtn
                        aria-label="编辑归档任务"
                        color="primary"
                        icon
                        size="small"
                        variant="tonal"
                        @click="openTaskEditor(selectedTask)"
                        ><VIcon icon="mdi-pencil-outline" /><VTooltip activator="parent" text="编辑任务" /></VBtn
                      ><VBtn
                        aria-label="删除归档任务"
                        color="error"
                        icon
                        size="small"
                        variant="text"
                        @click="removeTask(selectedTask)"
                        ><VIcon icon="mdi-delete-outline" /><VTooltip activator="parent" text="删除任务"
                      /></VBtn>
                    </div>
                  </div>
                  <div class="archive-detail-grid">
                    <div>
                      <span>调度</span><strong>{{ selectedTask.cron }}</strong>
                    </div>
                    <div>
                      <span>输出目录</span><strong>{{ selectedTask.output_dir || '-' }}</strong>
                    </div>
                    <div>
                      <span>清单目录</span><strong>{{ selectedTask.manifest_dir || '与归档目录相同' }}</strong>
                    </div>
                    <div>
                      <span>分组方式</span
                      ><strong>{{ groupingOptions.find(item => item.value === selectedTask.grouping)?.title }}</strong>
                    </div>
                    <div>
                      <span>文件限制</span
                      ><strong
                        >{{ selectedTask.max_files ? `${formatNumber(selectedTask.max_files)} 个` : '不限数量' }} ·
                        {{ selectedTask.max_bytes ? formatBytes(selectedTask.max_bytes) : '不限体积' }}</strong
                      >
                    </div>
                    <div>
                      <span>归档策略</span
                      ><strong
                        >{{ selectedTask.format.toUpperCase() }} ·
                        {{ selectedTask.encryption === 'aes256' ? 'AES-256' : '不加密' }}</strong
                      >
                    </div>
                  </div>
                  <div class="archive-detail-flags">
                    <VChip size="small" :color="selectedTask.verify ? 'success' : 'warning'" variant="tonal"
                      >校验 {{ selectedTask.verify ? '开启' : '关闭' }}</VChip
                    ><VChip size="small" :color="selectedTask.delete_source ? 'error' : 'default'" variant="tonal"
                      >源文件 {{ selectedTask.delete_source ? '归档后删除' : '保留' }}</VChip
                    ><VChip v-if="selectedTask.password_set" size="small" color="primary" variant="tonal"
                      >密码已保存</VChip
                    >
                  </div>
                  <div class="archive-detail-actions">
                    <VBtn prepend-icon="mdi-eye-outline" variant="tonal" @click="startPreviewForTask(selectedTask)"
                      >预览文件</VBtn
                    ><VBtn
                      color="primary"
                      prepend-icon="mdi-play"
                      type="button"
                      variant="flat"
                      @click="executeRun(selectedTask.id)"
                      >运行一次</VBtn
                    >
                  </div>
                </section>

                <section v-else-if="editorOpen" class="archive-section archive-editor">
                  <div class="archive-section__header">
                    <div>
                      <h3>{{ taskEditorTitle }}</h3>
                      <p>保存任务后，再点击页面顶部“保存修改”提交完整配置。</p>
                    </div>
                    <VBtn aria-label="取消编辑" icon size="small" variant="text" @click="cancelTaskEditor"
                      ><VIcon icon="mdi-close"
                    /></VBtn>
                  </div>
                  <div class="archive-editor__group">
                    <h4>基础信息</h4>
                    <div class="archive-form-grid archive-form-grid--two">
                      <VTextField
                        aria-label="任务名称"
                        v-model="taskEditor.name"
                        label="任务名称"
                        variant="outlined"
                      /><VSwitch
                        v-model="taskEditor.enabled"
                        color="primary"
                        density="compact"
                        hide-details
                        label="启用任务"
                      />
                    </div>
                  </div>
                  <div class="archive-editor__group">
                    <h4>目录与调度</h4>
                    <div class="archive-form-grid">
                      <VTextField
                        aria-label="源目录"
                        v-model="taskEditor.source_dir"
                        label="源目录"
                        prepend-inner-icon="mdi-folder-open-outline"
                        variant="outlined"
                      /><VTextField
                        aria-label="归档输出目录"
                        v-model="taskEditor.output_dir"
                        label="归档输出目录"
                        prepend-inner-icon="mdi-archive-outline"
                        variant="outlined"
                      /><VTextField
                        aria-label="清单目录（可选）"
                        v-model="taskEditor.manifest_dir"
                        hint="留空时使用归档输出目录。"
                        label="清单目录（可选）"
                        persistent-hint
                        prepend-inner-icon="mdi-file-document-outline"
                        variant="outlined"
                      /><VTextField
                        aria-label="Cron 调度"
                        v-model="taskEditor.cron"
                        hint="例如：0 2 * * *"
                        label="Cron 调度"
                        persistent-hint
                        prepend-inner-icon="mdi-clock-outline"
                        variant="outlined"
                      />
                    </div>
                  </div>
                  <div class="archive-editor__group">
                    <h4>命名规则</h4>
                    <div class="archive-form-grid archive-form-grid--two">
                      <VSelect
                        aria-label="批次目录布局"
                        class="archive-layout-select"
                        v-model="taskEditor.archive_layout"
                        :items="[
                          { title: '按目录（来源目录 / 批次名称）', value: 'directory' },
                          { title: '扁平（来源目录_批次名称）', value: 'flat' },
                        ]"
                        hint="按目录：来源目录/批次名称；扁平：来源目录_批次名称。"
                        item-title="title"
                        item-value="value"
                        label="批次目录布局"
                        persistent-hint
                        variant="outlined"
                      />
                      <VTextField
                        aria-label="批次名称模板"
                        v-model="taskEditor.batch_name_template"
                        hint="用于实际批次目录名，例如 20260911_0001；创建后固定，改模板只影响新批次。"
                        label="批次名称模板"
                        persistent-hint
                        prepend-inner-icon="mdi-label-outline"
                        variant="outlined"
                      /><VTextField
                        aria-label="归档包名称模板"
                        v-model="taskEditor.archive_name_template"
                        hint="用于实际生成的 .7z/.zip 文件名。"
                        label="归档包名称模板"
                        persistent-hint
                        prepend-inner-icon="mdi-file-certificate-outline"
                        variant="outlined"
                      />
                    </div>
                    <VAlert density="compact" type="info" variant="tonal">
                      基础变量：<code>{date}</code>=<code>20260911</code>、<code>{time}</code>=<code>040020</code>、
                      <code>{id}</code>=<code>7f3a9c</code>、<code>{sequence}</code>=<code>0001</code>；也支持
                      strftime， 例如 <code>{%Y%m%d_%H%M%S}</code>。
                    </VAlert>
                    <div class="archive-naming-preview">
                      <span>示例</span>
                      <code>批次：{{ namingExamples.batch }}</code>
                      <code>归档包：{{ namingExamples.archive }}</code>
                    </div>
                    <VAlert density="compact" type="info" variant="tonal">
                      外层归档包名会对存储端可见；需要隐藏文件名时，请使用 7z AES-256 并开启加密文件名。
                    </VAlert>
                  </div>
                  <div class="archive-editor__group">
                    <h4>文件筛选</h4>
                    <div class="archive-form-grid archive-form-grid--two">
                      <VSwitch
                        v-model="taskEditor.recursive"
                        color="primary"
                        density="compact"
                        hide-details
                        label="递归扫描子目录"
                      /><VTextField
                        aria-label="目录深度"
                        v-model.number="taskEditor.directory_depth"
                        hint="按目录分组时使用。"
                        label="目录深度"
                        min="1"
                        persistent-hint
                        type="number"
                        variant="outlined"
                      /><VTextarea
                        aria-label="包含模式"
                        v-model="includePatternsText"
                        hint="每行一个 glob，留空表示不限制。"
                        label="包含模式"
                        persistent-hint
                        rows="3"
                        variant="outlined"
                      /><VTextarea
                        aria-label="排除模式"
                        v-model="excludePatternsText"
                        hint="每行一个 glob。"
                        label="排除模式"
                        persistent-hint
                        rows="3"
                        variant="outlined"
                      />
                    </div>
                  </div>
                  <div class="archive-editor__group">
                    <h4>批次策略</h4>
                    <div class="archive-form-grid archive-form-grid--three">
                      <VSelect
                        aria-label="分组方式"
                        v-model="taskEditor.grouping"
                        :items="groupingOptions"
                        item-title="title"
                        item-value="value"
                        label="分组方式"
                        variant="outlined"
                      /><VSelect
                        aria-label="时间粒度"
                        v-model="taskEditor.time_grain"
                        :items="timeGrainOptions"
                        item-title="title"
                        item-value="value"
                        label="时间粒度"
                        variant="outlined"
                      /><VTextField
                        aria-label="最多批次"
                        v-model.number="taskEditor.max_batches"
                        label="最多批次"
                        min="1"
                        type="number"
                        variant="outlined"
                      /><VTextField
                        aria-label="每批最多文件"
                        v-model.number="taskEditor.max_files"
                        hint="0 表示不限。"
                        label="每批最多文件"
                        min="0"
                        persistent-hint
                        type="number"
                        variant="outlined"
                      /><VTextField
                        aria-label="每批最大体积"
                        v-model.number="taskEditor.max_bytes"
                        hint="0 表示不限，单位字节。"
                        label="每批最大体积"
                        min="0"
                        persistent-hint
                        type="number"
                        variant="outlined"
                      /><VTextField
                        aria-label="归档多少天之前的文件"
                        v-model.number="taskEditor.archive_age_days"
                        hint="按文件修改时间筛选，0 表示不限制。"
                        label="归档多少天之前的文件"
                        min="0"
                        persistent-hint
                        type="number"
                        variant="outlined"
                      /><VTextField
                        aria-label="稳定时间（秒）"
                        v-model.number="taskEditor.stability_seconds"
                        label="稳定时间（秒）"
                        min="1"
                        type="number"
                        variant="outlined"
                      />
                    </div>
                  </div>
                  <div class="archive-editor__group">
                    <h4>续跑与空间</h4>
                    <div class="archive-form-grid archive-form-grid--three">
                      <VSwitch
                        v-model="taskEditor.auto_continue"
                        color="primary"
                        density="compact"
                        hide-details
                        label="自动分批续跑"
                      /><VTextField
                        aria-label="本地成品最多批次"
                        v-model.number="taskEditor.max_pending_archives"
                        hint="0 表示不限。"
                        label="本地成品最多批次"
                        min="0"
                        persistent-hint
                        type="number"
                        variant="outlined"
                      /><VTextField
                        aria-label="本地成品最大体积"
                        v-model.number="taskEditor.max_pending_bytes"
                        hint="0 表示不限，单位字节。"
                        label="本地成品最大体积"
                        min="0"
                        persistent-hint
                        type="number"
                        variant="outlined"
                      /><VTextField
                        aria-label="预留磁盘空间"
                        v-model.number="minFreeGiB"
                        hint="归档后必须保留的空间，0 表示不预留。"
                        label="预留磁盘空间"
                        min="0"
                        persistent-hint
                        step="0.1"
                        suffix="GiB"
                        type="number"
                        variant="outlined"
                      />
                    </div>
                    <VAlert density="compact" type="info" variant="tonal"
                      >插件只负责本地归档，不上传、不删除成品；自动续跑会在空间或成品积压达到限制时每 60
                      秒重新检测。</VAlert
                    >
                  </div>
                  <div class="archive-editor__group">
                    <h4>压缩与安全</h4>
                    <div class="archive-form-grid archive-form-grid--three">
                      <VSelect
                        aria-label="归档格式"
                        :model-value="taskEditor.format"
                        :items="formatOptions"
                        item-title="title"
                        item-value="value"
                        label="归档格式"
                        variant="outlined"
                        @update:model-value="requestFormat"
                      /><VSelect
                        aria-label="压缩级别"
                        v-model="taskEditor.compression"
                        :items="compressionOptions"
                        item-title="title"
                        item-value="value"
                        label="压缩级别"
                        variant="outlined"
                      /><VSelect
                        aria-label="加密方式"
                        :model-value="taskEditor.encryption"
                        :items="encryptionOptions"
                        item-title="title"
                        item-value="value"
                        label="加密方式"
                        variant="outlined"
                        @update:model-value="handleEncryption"
                      /><VTextField
                        aria-label="密码（可选）"
                        v-model="taskEditor.password"
                        autocomplete="new-password"
                        :hint="
                          taskEditorHasSavedPassword ? '已保存密码不会回显；输入新值可覆盖。' : '密码只写入，不会回显。'
                        "
                        label="密码（可选）"
                        persistent-hint
                        type="password"
                        variant="outlined"
                      /><VTextField
                        aria-label="密码版本"
                        v-model="taskEditor.password_version"
                        label="密码版本"
                        variant="outlined"
                      /><VSwitch
                        :model-value="taskEditor.encrypt_names"
                        color="primary"
                        :disabled="taskEditor.encryption !== 'aes256'"
                        density="compact"
                        hide-details
                        label="加密文件名（7z）"
                        @update:model-value="requestEncryptNames"
                      />
                    </div>
                  </div>
                  <div class="archive-editor__group">
                    <h4>完成行为</h4>
                    <div class="archive-form-grid archive-form-grid--two">
                      <VSwitch
                        :model-value="taskEditor.verify"
                        color="primary"
                        :disabled="taskEditor.delete_source"
                        density="compact"
                        hide-details
                        label="归档后校验"
                        @update:model-value="handleVerify"
                      /><VSwitch
                        :model-value="taskEditor.delete_source"
                        color="error"
                        density="compact"
                        hide-details
                        label="校验通过后删除源文件"
                        @update:model-value="handleDeleteSource"
                      />
                    </div>
                    <VAlert
                      v-if="taskEditor.delete_source"
                      class="archive-editor__warning"
                      density="compact"
                      type="warning"
                      variant="tonal"
                      >启用删除源文件后，后端会强制执行校验；校验失败不会删除源文件。</VAlert
                    >
                  </div>
                  <div class="archive-editor__actions">
                    <VBtn
                      prepend-icon="mdi-eye-outline"
                      variant="tonal"
                      @click="startPreviewForTask(prepareEditorTask())"
                      >预览文件</VBtn
                    ><VSpacer /><VBtn variant="text" @click="cancelTaskEditor">取消</VBtn
                    ><VBtn color="primary" prepend-icon="mdi-check" variant="flat" @click="saveTaskEditor"
                      >保存任务</VBtn
                    >
                  </div>
                </section>
              </div>
            </section>

            <section v-else-if="activeView === 'batches'" class="archive-view archive-table-view">
              <div class="archive-filter-bar">
                <VSelect
                  aria-label="批次任务"
                  v-model="batchTaskFilter"
                  :items="[
                    { title: '全部任务', value: '' },
                    ...draft.tasks.map(task => ({ title: task.name, value: task.id })),
                  ]"
                  item-title="title"
                  item-value="value"
                  label="任务"
                  variant="outlined"
                /><VSelect
                  aria-label="批次状态"
                  v-model="batchStatusFilter"
                  :items="batchStatusOptions"
                  item-title="title"
                  item-value="value"
                  label="状态"
                  variant="outlined"
                /><VSpacer />
              </div>
              <div v-if="batchLoading" class="archive-inline-state">
                <VProgressCircular color="primary" indeterminate size="18" width="2" />正在读取批次…
              </div>
              <div v-else-if="batchData.items.length === 0" class="archive-empty archive-empty--table">
                <VIcon icon="mdi-package-variant-remove" size="34" /><strong>没有符合条件的批次</strong
                ><span>任务运行后，批次详情会显示在这里。</span>
              </div>
              <div v-else class="archive-table-wrap">
                <table class="archive-table">
                  <thead>
                    <tr>
                      <th>批次</th>
                      <th>任务</th>
                      <th>状态</th>
                      <th>创建时间</th>
                      <th class="archive-table__numeric">文件</th>
                      <th class="archive-table__numeric">归档体积</th>
                      <th>校验</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="batch in batchData.items" :key="batch.id" @click="openBatch(batch)">
                      <td>
                        <strong>{{ batch.batch_name || batch.id }}</strong
                        ><small class="archive-id">ID：{{ batch.id }}</small
                        ><small>{{ batch.archive_name || batch.archive_path || '暂无归档路径' }}</small>
                      </td>
                      <td>{{ batch.task_name }}</td>
                      <td>
                        <VChip :color="statusColor(batch.status)" size="small" variant="tonal"
                          >{{ statusLabel(batch.status) }}<template v-if="batch.superseded"> · 已替代</template></VChip
                        >
                      </td>
                      <td>{{ formatDate(batch.created_at) }}</td>
                      <td class="archive-table__numeric">{{ formatNumber(batch.file_count) }}</td>
                      <td class="archive-table__numeric">{{ formatBytes(batch.archive_size) }}</td>
                      <td>
                        <VIcon
                          :color="batch.verified ? 'success' : 'warning'"
                          :icon="batch.verified ? 'mdi-check-circle-outline' : 'mdi-help-circle-outline'"
                        /><span class="sr-only">{{ batch.verified ? '已校验' : '未校验' }}</span>
                      </td>
                      <td>
                        <VBtn aria-label="查看批次详情" icon size="small" variant="text" @click.stop="openBatch(batch)"
                          ><VIcon icon="mdi-chevron-right"
                        /></VBtn>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-if="batchData.total > 0" class="archive-pagination">
                <span>共 {{ formatNumber(batchData.total) }} 个批次</span
                ><VPagination v-model="batchPage" :length="batchPageCount" density="compact" :total-visible="5" />
              </div>
            </section>

            <section v-else class="archive-view archive-table-view">
              <div v-if="!draft.tasks.length" class="archive-empty archive-empty--table">
                <VIcon icon="mdi-archive-off-outline" size="34" /><strong>暂无归档任务</strong
                ><span>创建归档任务后，才能查询已归档文件。</span>
              </div>
              <div v-else-if="!hasFileTaskSelection" class="archive-empty archive-empty--table">
                <VIcon icon="mdi-format-list-checks" size="34" /><strong>请选择归档任务</strong
                ><span>选择任务后，可以按目录、状态或相对路径查询文件。</span>
              </div>
              <template v-else>
                <div class="archive-filter-bar">
                  <VSelect
                    aria-label="文件任务"
                    clearable
                    v-model="fileTaskFilter"
                    :items="draft.tasks.map(task => ({ title: task.name, value: task.id }))"
                    item-title="title"
                    item-value="value"
                    label="任务"
                    variant="outlined"
                  /><VTextField
                    v-model="fileQuery"
                    clearable
                    label="搜索相对路径"
                    prepend-inner-icon="mdi-magnify"
                    variant="outlined"
                    @keyup.enter="submitFileSearch"
                  /><VSelect
                    aria-label="文件状态"
                    v-model="fileStatus"
                    clearable
                    :items="[
                      { title: '待处理', value: 'pending' },
                      { title: '已归档', value: 'archived' },
                      { title: '失败', value: 'failed' },
                      { title: '已删除', value: 'deleted' },
                    ]"
                    item-title="title"
                    item-value="value"
                    label="文件状态"
                    variant="outlined"
                  /><VBtn aria-label="搜索文件" icon variant="tonal" @click="submitFileSearch"
                    ><VIcon icon="mdi-magnify"
                  /></VBtn>
                </div>
                <nav aria-label="文件目录" class="archive-breadcrumbs">
                  <VBtn
                    v-for="crumb in breadcrumbs"
                    :key="crumb.path || 'root'"
                    size="small"
                    variant="text"
                    @click="navigateDirectory(crumb.path)"
                    >{{ crumb.title }}</VBtn
                  >
                </nav>
                <div v-if="fileLoading" class="archive-inline-state">
                  <VProgressCircular color="primary" indeterminate size="18" width="2" />正在读取文件…
                </div>
                <div
                  v-else-if="fileData.items.length === 0 && fileData.directories.length === 0"
                  class="archive-empty archive-empty--table"
                >
                  <VIcon icon="mdi-file-search-outline" size="34" /><strong>没有找到文件</strong
                  ><span>调整任务、目录或搜索条件后重试。</span>
                </div>
                <div v-else class="archive-files-browser">
                  <div v-if="fileData.directories.length" class="archive-directory-list">
                    <div class="archive-directory-list__heading">子目录</div>
                    <button
                      v-for="directory in fileData.directories"
                      :key="directory.path"
                      class="archive-directory"
                      type="button"
                      @click="navigateDirectory(directory.path)"
                    >
                      <VIcon icon="mdi-folder-outline" /><span>{{ directory.name }}</span
                      ><VIcon icon="mdi-chevron-right" size="18" />
                    </button>
                  </div>
                  <div class="archive-table-wrap">
                    <table class="archive-table">
                      <thead>
                        <tr>
                          <th>相对路径</th>
                          <th class="archive-table__numeric">大小</th>
                          <th>修改时间</th>
                          <th>状态</th>
                          <th>批次</th>
                          <th>SHA-256</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="file in fileData.items" :key="`${file.batch_id}:${file.relative_path}`">
                          <td>
                            <strong>{{ file.relative_path }}</strong>
                          </td>
                          <td class="archive-table__numeric">{{ formatBytes(file.size) }}</td>
                          <td>
                            {{ file.mtime_ns ? formatDate(new Date(file.mtime_ns / 1000000).toISOString()) : '-' }}
                          </td>
                          <td>
                            <VChip :color="statusColor(file.status)" size="small" variant="tonal">{{
                              statusLabel(file.status)
                            }}</VChip>
                          </td>
                          <td>{{ file.batch_id ? file.batch_id.slice(0, 12) : '-' }}</td>
                          <td>
                            <code>{{ file.sha256 ? file.sha256.slice(0, 16) : '-' }}</code>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
                <div v-if="fileData.total > 0" class="archive-pagination">
                  <span>共 {{ formatNumber(fileData.total) }} 个文件</span
                  ><VPagination v-model="filePage" :length="filePageCount" density="compact" :total-visible="5" />
                </div>
              </template>
            </section>
          </main>
        </div>
      </div>
      <div v-if="isDirty" class="archive-mobile-save-dock">
        <span aria-live="polite" class="archive-mobile-save-dock__state"
          ><VIcon color="warning" icon="mdi-circle" size="8" />有未保存修改</span
        >
        <VSpacer />
        <VBtn class="archive-mobile-save-dock__save" color="primary" :disabled="!isDirty" type="submit" variant="flat"
          ><VIcon icon="mdi-content-save" start />保存修改</VBtn
        >
      </div>
    </form>

    <VBottomSheet v-model="mobileNavOpen"
      ><VCard
        ><VCardTitle>切换工作区</VCardTitle
        ><VList lines="two" nav
          ><VListItem
            v-for="(view, key) in viewLabels"
            :key="key"
            :active="activeView === key"
            :prepend-icon="view.icon"
            :subtitle="view.summary"
            :title="view.title"
            color="primary"
            @click="selectMobileView(key)"
            ><template #append
              ><VIcon v-if="activeView === key" icon="mdi-check" /></template></VListItem></VList></VCard
    ></VBottomSheet>

    <VDialog v-model="compatibilityOpen" max-width="480" width="calc(100% - 24px)"
      ><VCard
        ><VCardTitle>格式兼容性确认</VCardTitle
        ><VCardText v-if="compatibilityReason === 'format'"
          >ZIP 不支持加密文件名。切换为 ZIP 会关闭“加密文件名”，是否继续？</VCardText
        ><VCardText v-else>ZIP 不支持加密文件名。要启用此选项，需要切换到 7z，是否继续？</VCardText
        ><VCardActions
          ><VSpacer /><VBtn variant="text" @click="cancelCompatibilityChange">取消</VBtn
          ><VBtn color="primary" variant="flat" @click="acceptCompatibilityChange">确认切换</VBtn></VCardActions
        ></VCard
      ></VDialog
    >

    <VDialog v-model="previewOpen" max-width="760" scrollable width="calc(100% - 24px)"
      ><VCard
        ><VCardTitle class="archive-dialog__title"
          ><span>文件预览</span
          ><VBtn aria-label="关闭文件预览" icon size="small" variant="text" @click="closePreview"
            ><VIcon icon="mdi-close" /></VBtn></VCardTitle
        ><VCardText
          ><div v-if="previewState === 'running'" class="archive-dialog-state">
            <VProgressCircular color="primary" indeterminate size="28" width="3" /><strong>{{ previewMessage }}</strong
            ><span>扫描过程不会写入归档，也不会删除源文件。</span>
          </div>
          <div v-else-if="previewState === 'failed'" class="archive-dialog-state archive-dialog-state--error">
            <VIcon color="error" icon="mdi-alert-circle-outline" size="30" /><strong>{{ previewMessage }}</strong
            ><span>请检查目录、权限和筛选条件。</span>
          </div>
          <template v-else-if="previewResult"
            ><div class="archive-preview-metrics">
              <div>
                <span>文件数</span><strong>{{ formatNumber(previewResult.file_count) }}</strong>
              </div>
              <div>
                <span>总大小</span><strong>{{ formatBytes(previewResult.total_bytes) }}</strong>
              </div>
              <div>
                <span>预计批次</span><strong>{{ formatNumber(previewResult.batch_count) }}</strong>
              </div>
              <div>
                <span>跳过文件</span><strong>{{ formatNumber(previewResult.skipped_count) }}</strong>
              </div>
            </div>
            <div class="archive-table-wrap">
              <table class="archive-table">
                <thead>
                  <tr>
                    <th>分组</th>
                    <th class="archive-table__numeric">文件数</th>
                    <th class="archive-table__numeric">大小</th>
                    <th>限制</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="batch in previewResult.batches" :key="batch.group">
                    <td>{{ batch.group }}</td>
                    <td class="archive-table__numeric">{{ formatNumber(batch.file_count) }}</td>
                    <td class="archive-table__numeric">{{ formatBytes(batch.total_bytes) }}</td>
                    <td>
                      <VChip v-if="batch.oversized" color="warning" size="small" variant="tonal">超出限制</VChip
                      ><span v-else>正常</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div></template
          ></VCardText
        ><VCardActions><VSpacer /><VBtn variant="text" @click="closePreview">关闭</VBtn></VCardActions></VCard
      ></VDialog
    >

    <VDialog v-model="batchDialogOpen" max-width="980" scrollable width="calc(100% - 24px)"
      ><VCard v-if="selectedBatch"
        ><VCardTitle class="archive-dialog__title"
          ><div>
            <span>{{ selectedBatch.batch_name || '批次详情' }}</span
            ><small>ID：{{ selectedBatch.id }}</small>
          </div>
          <VBtn aria-label="关闭批次详情" icon size="small" variant="text" @click="batchDialogOpen = false"
            ><VIcon icon="mdi-close" /></VBtn></VCardTitle
        ><VCardText
          ><div v-if="batchDetailLoading" class="archive-dialog-state">
            <VProgressCircular color="primary" indeterminate size="24" width="2" />正在读取批次详情…
          </div>
          <template v-else
            ><VAlert v-if="selectedBatch.superseded" type="info" variant="tonal"
              >该批次已被源文件的新版本替代，仅保留作审计记录，不能重试。</VAlert
            >
            <div class="archive-batch-summary">
              <div>
                <span>状态</span
                ><VChip :color="statusColor(selectedBatch.status)" size="small" variant="tonal">{{
                  statusLabel(selectedBatch.status)
                }}</VChip>
              </div>
              <div>
                <span>任务</span><strong>{{ selectedBatch.task_name }}</strong>
              </div>
              <div>
                <span>批次名称</span><strong>{{ selectedBatch.batch_name || selectedBatch.id }}</strong>
              </div>
              <div>
                <span>源文件</span
                ><strong
                  >{{ formatNumber(selectedBatch.file_count) }} · {{ formatBytes(selectedBatch.source_bytes) }}</strong
                >
              </div>
              <div>
                <span>归档文件</span><strong>{{ formatBytes(selectedBatch.archive_size) }}</strong>
              </div>
              <div>
                <span>本地成品</span
                ><VChip :color="selectedBatch.archive_available ? 'success' : 'warning'" size="small" variant="tonal">{{
                  selectedBatch.archive_available ? '可用' : '已不在本地'
                }}</VChip>
              </div>
              <div>
                <span>校验</span><strong>{{ selectedBatch.verified ? '已通过' : '未通过或未执行' }}</strong>
              </div>
              <div>
                <span>清单</span><strong>{{ selectedBatch.manifest_available ? '可用' : '待补全' }}</strong>
              </div>
            </div>
            <VAlert v-if="selectedBatch.error" type="error" variant="tonal">{{ selectedBatch.error }}</VAlert>
            <div class="archive-paths">
              <div>
                <span>归档路径</span><code>{{ selectedBatch.archive_path || '-' }}</code>
              </div>
              <div>
                <span>清单路径</span><code>{{ selectedBatch.manifest_path || '-' }}</code>
              </div>
              <div>
                <span>SHA-256</span><code>{{ selectedBatch.archive_sha256 || '-' }}</code>
              </div>
            </div>
            <div v-if="selectedBatch.files?.length" class="archive-table-wrap">
              <table class="archive-table">
                <thead>
                  <tr>
                    <th>文件</th>
                    <th class="archive-table__numeric">大小</th>
                    <th>状态</th>
                    <th>SHA-256</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="file in selectedBatch.files" :key="file.relative_path">
                    <td>{{ file.relative_path }}</td>
                    <td class="archive-table__numeric">{{ formatBytes(file.size) }}</td>
                    <td>
                      <VChip :color="statusColor(batchFileStatus(file, selectedBatch))" size="small" variant="tonal">{{
                        statusLabel(batchFileStatus(file, selectedBatch))
                      }}</VChip>
                    </td>
                    <td>
                      <code>{{ file.sha256 || '-' }}</code>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="Object.keys(selectedBatch.cleanup || {}).length" class="archive-cleanup">
              <h4>清理结果</h4>
              <div class="archive-cleanup-grid">
                <div v-for="(status, path) in selectedBatch.cleanup" :key="path">
                  <span>{{ path }}</span
                  ><VChip :color="statusColor(status)" size="small" variant="tonal">{{ statusLabel(status) }}</VChip>
                </div>
              </div>
            </div></template
          ></VCardText
        ><VCardActions
          ><VSpacer /><VBtn
            v-if="selectedBatch.status === 'manifest_pending' || !selectedBatch.manifest_available"
            color="primary"
            prepend-icon="mdi-file-document-refresh-outline"
            variant="tonal"
            @click="executeBatchAction('repair', selectedBatch)"
            >补全清单</VBtn
          ><VBtn
            v-if="
              !selectedBatch.superseded &&
              selectedBatch.status !== 'superseded' &&
              ['failed', 'cleanup_failed', 'cancelled', 'interrupted'].includes(selectedBatch.status)
            "
            color="primary"
            prepend-icon="mdi-replay"
            variant="flat"
            @click="executeBatchAction('retry', selectedBatch)"
            >重试批次</VBtn
          ><VBtn variant="text" @click="batchDialogOpen = false">关闭</VBtn></VCardActions
        ></VCard
      ></VDialog
    >
  </section>
</template>

<style scoped>
.archive-config {
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  block-size: min(900px, calc(100dvh - 64px));
  max-block-size: calc(100dvh - 64px);
  min-block-size: 0;
  min-inline-size: 0;
  overflow: hidden;
  color: rgb(var(--v-theme-on-surface));
  letter-spacing: 0;
}
.archive-config,
.archive-config * {
  box-sizing: border-box;
}
.archive-config > form {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-block-size: 0;
}
.archive-header {
  position: relative;
  z-index: 1;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-block-size: 72px;
  gap: 16px;
  padding: 10px 16px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: transparent;
  backdrop-filter: none;
}
.archive-header__identity,
.archive-header__crumbs,
.archive-header__title-row,
.archive-header__actions,
.archive-main__title,
.archive-main__heading-actions,
.archive-section__header,
.archive-section__actions,
.archive-detail-actions,
.archive-running__copy,
.archive-pagination,
.archive-breadcrumbs,
.archive-dialog__title,
.archive-dialog__title > div {
  display: flex;
  align-items: center;
}
.archive-header__identity {
  flex-direction: column;
  align-items: flex-start;
  min-inline-size: 0;
}
.archive-header__brand {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  min-inline-size: 0;
  gap: 10px;
}
.archive-header__crumbs {
  margin-block-end: 3px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 0.6875rem;
  line-height: 1rem;
  gap: 2px;
}
.archive-header__title-row {
  gap: 8px;
}
.archive-header__title-row h1 {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 1.06rem;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.4rem;
}
.archive-header__actions {
  align-items: center;
  flex: 0 0 auto;
  gap: 7px;
}
.archive-header__logo {
  display: block;
  flex: 0 0 40px;
  inline-size: 40px;
  block-size: 40px;
  object-fit: contain;
}
.archive-header__close-icon {
  display: none;
}
.archive-body {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  min-inline-size: 0;
  overflow: hidden;
  padding: 18px;
}
.archive-alert {
  margin-block: 10px;
}
.archive-alert span {
  display: block;
  margin-block-start: 4px;
}
.archive-metrics {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  margin-block-end: 12px;
}
.archive-metric {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: center;
  min-inline-size: 0;
  gap: 3px 8px;
  padding: 11px 12px;
  border: var(--app-surface-border, 1px solid rgba(var(--v-theme-on-surface), 0.12));
  border-radius: var(--app-surface-radius, 8px);
  background: var(--app-grouped-list-background, rgba(var(--v-theme-surface), 0.5));
  box-shadow: none;
}
.archive-metric > span {
  overflow: hidden;
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 0.7rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.archive-metric > strong {
  grid-column: 2;
  font-size: 1rem;
}
.archive-metric > .v-icon {
  grid-row: span 2;
  color: rgb(var(--v-theme-primary));
}
.archive-metric--warning > .v-icon,
.archive-metric--warning > strong {
  color: rgb(var(--v-theme-error));
}
.archive-workspace {
  flex: 1 1 auto;
  display: grid;
  min-block-size: 0;
  min-inline-size: 0;
  gap: 14px;
  grid-template-columns: 168px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  overflow: hidden;
}
.archive-nav {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  min-inline-size: 0;
  overflow: hidden;
  border-inline-end: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  padding-inline-end: 10px;
}
.archive-nav__heading {
  padding: 6px 10px 10px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 0.75rem;
  font-weight: 600;
}
.archive-nav__list {
  flex: 1 1 auto;
  min-block-size: 0;
  overflow-y: auto;
  padding: 0 4px;
  background: transparent;
}
.archive-nav__list :deep(.v-list-item) {
  min-block-size: 50px;
  margin-block: 4px;
}
.archive-nav__list :deep(.v-list-item-title) {
  overflow-wrap: anywhere;
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.2rem;
}
.archive-nav__help {
  padding: 12px;
  margin-block-start: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.025);
}
.archive-nav__help-title {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
}
.archive-nav__help p {
  margin: 4px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 0.68rem;
  line-height: 1.1rem;
}
.archive-nav__help-link {
  padding-inline: 0;
  margin-block-start: 4px;
}
.archive-main {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  min-inline-size: 0;
}
.archive-main__heading {
  flex: 0 0 auto;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  min-inline-size: 0;
  padding: 2px 2px 12px;
  gap: 12px;
}
.archive-main__title {
  gap: 8px;
}
.archive-main__title h2 {
  margin: 0;
  font-size: 1rem;
  line-height: 1.3rem;
}
.archive-main__heading p {
  margin: 3px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 0.72rem;
}
.archive-main__heading-actions {
  gap: 4px;
}
.archive-mobile-nav {
  display: none;
}
.archive-view {
  flex: 1 1 auto;
  min-block-size: 0;
  min-inline-size: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0 3px 6px;
}
.archive-overview {
  display: block;
}
.archive-table-view {
  display: flex;
  flex-direction: column;
}
.archive-inline-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-block-size: 68px;
  color: rgba(var(--v-theme-on-surface), 0.64);
  font-size: 0.8rem;
  gap: 8px;
}
.archive-inline-state--error {
  color: rgb(var(--v-theme-error));
}
.archive-running {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-inline-size: 0;
  padding: 10px 12px;
  margin-block-end: 12px;
  border: 1px solid rgba(var(--v-theme-primary), 0.28);
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.06);
  gap: 12px;
}
.archive-running__copy {
  min-inline-size: 0;
  gap: 9px;
}
.archive-running__copy > div {
  display: grid;
  min-inline-size: 0;
  gap: 2px;
}
.archive-running__copy strong,
.archive-running__copy span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.archive-running__copy span {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 0.72rem;
}
.archive-progress {
  margin-block-end: 12px;
}
.archive-progress__list {
  display: grid;
  margin-block-start: 10px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.archive-progress__row {
  display: grid;
  align-items: center;
  min-inline-size: 0;
  padding: 9px 2px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  gap: 8px;
  grid-template-columns: minmax(140px, 1fr) auto minmax(180px, 1.4fr) minmax(150px, 0.9fr);
}
.archive-progress__identity {
  display: flex;
  min-inline-size: 0;
  align-items: center;
  gap: 7px;
}
.archive-progress__identity strong,
.archive-progress__detail,
.archive-progress__capacity {
  overflow-wrap: anywhere;
  font-size: 0.72rem;
}
.archive-progress__detail {
  color: rgba(var(--v-theme-on-surface), 0.62);
}
.archive-progress__capacity {
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 0.66rem;
  line-height: 1.1rem;
  text-align: end;
}
.archive-task-layout {
  flex: 1 1 auto;
  display: grid;
  min-block-size: 0;
  min-inline-size: 0;
  gap: 12px;
  grid-template-columns: minmax(210px, 0.35fr) minmax(0, 1fr);
}
.archive-task-layout--editing {
  min-block-size: max-content;
  grid-template-columns: minmax(0, 1fr);
}
.archive-editor {
  min-block-size: max-content;
}
.archive-section {
  min-inline-size: 0;
  padding: 18px 0;
  background: transparent;
}
.archive-overview > .archive-section {
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.archive-task-layout > .archive-task-detail {
  border-inline-start: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  padding-inline-start: 18px;
}
.archive-section__header {
  justify-content: space-between;
  min-inline-size: 0;
  gap: 10px;
}
.archive-section__header > div:first-child {
  min-inline-size: 0;
}
.archive-section__header > .v-chip {
  flex: 0 0 auto;
}
.archive-section__header h3 {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 0.98rem;
  line-height: 1.25rem;
}
.archive-section__header p {
  margin: 3px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 0.7rem;
  line-height: 1.1rem;
  overflow-wrap: anywhere;
}
.archive-section__actions {
  flex: 0 0 auto;
  gap: 3px;
}
.archive-task-list__items {
  padding: 5px 0 0;
  background: transparent;
}
.archive-task-list__items :deep(.v-list-item) {
  min-block-size: 58px;
  padding-inline: 9px;
  margin-block: 4px;
}
.archive-task-list__items :deep(.v-list-item-title) {
  overflow-wrap: anywhere;
  font-size: 0.82rem;
  font-weight: 600;
}
.archive-task-list__items :deep(.v-list-item-subtitle) {
  overflow-wrap: anywhere;
  font-size: 0.67rem;
}
.archive-empty {
  display: grid;
  justify-items: center;
  min-block-size: 250px;
  padding: 30px 16px;
  color: rgba(var(--v-theme-on-surface), 0.56);
  text-align: center;
  gap: 8px;
}
.archive-empty strong {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.9rem;
}
.archive-empty span {
  max-inline-size: 30rem;
  font-size: 0.72rem;
  line-height: 1.25rem;
}
.archive-empty--table {
  min-block-size: 220px;
}
.archive-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0;
  margin-block-start: 18px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.archive-detail-grid > div {
  min-inline-size: 0;
  padding: 11px 6px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.archive-detail-grid span,
.archive-batch-summary span,
.archive-paths span,
.archive-preview-metrics span {
  display: block;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 0.68rem;
}
.archive-detail-grid strong {
  display: block;
  margin-block-start: 4px;
  overflow-wrap: anywhere;
  font-size: 0.78rem;
  font-weight: 600;
}
.archive-detail-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-block-start: 12px;
}
.archive-detail-actions {
  justify-content: flex-end;
  margin-block-start: 18px;
  gap: 7px;
}
.archive-editor__group {
  padding-block: 15px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.archive-editor__group:last-of-type {
  border-block-end: 0;
}
.archive-editor__group h4 {
  margin: 0 0 10px;
  font-size: 0.82rem;
}
.archive-naming-preview {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
  padding: 8px 10px;
  margin-block-start: 2px;
  border-inline-start: 3px solid rgba(var(--v-theme-primary), 0.45);
  background: rgba(var(--v-theme-primary), 0.05);
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.68rem;
}
.archive-naming-preview span {
  flex: 0 0 100%;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-weight: 600;
}
.archive-naming-preview code {
  overflow-wrap: anywhere;
  color: rgb(var(--v-theme-on-surface));
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.68rem;
}
.archive-form-grid {
  display: grid;
  min-inline-size: 0;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.archive-form-grid--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.archive-form-grid--three {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.archive-layout-select :deep(.v-select__selection-text) {
  overflow-wrap: anywhere;
  white-space: normal;
}
.archive-config :deep(.v-list-item-title) {
  overflow-wrap: anywhere;
  white-space: normal;
}
.archive-editor__warning {
  margin-block-start: 10px;
}
.archive-editor__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding-block-start: 16px;
}
.archive-filter-bar {
  display: flex;
  align-items: center;
  min-inline-size: 0;
  gap: 8px;
  padding-block-start: 8px;
  margin-block-end: 18px;
}
.archive-filter-bar > .v-input {
  flex: 0 1 220px;
  min-inline-size: 120px;
}
.archive-table-wrap {
  flex: 1 1 auto;
  min-inline-size: 0;
  min-block-size: 0;
  overflow: auto;
  border: var(--app-surface-border, 1px solid rgba(var(--v-theme-on-surface), 0.12));
  border-radius: 8px;
}
.archive-table {
  width: 100%;
  min-width: 720px;
  border-collapse: collapse;
  font-size: 0.75rem;
}
.archive-table th,
.archive-table td {
  padding: 10px 11px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.09);
  text-align: start;
  vertical-align: middle;
}
.archive-table th {
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 0.68rem;
  font-weight: 600;
  white-space: nowrap;
}
.archive-table tbody tr {
  cursor: pointer;
  transition: background-color 150ms ease;
}
.archive-table tbody tr:hover {
  background: rgba(var(--v-theme-primary), 0.05);
}
.archive-table tbody tr:last-child td {
  border-block-end: 0;
}
.archive-table td strong,
.archive-table td small {
  display: block;
  overflow-wrap: anywhere;
}
.archive-table td small.archive-id {
  color: rgba(var(--v-theme-on-surface), 0.42);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.archive-table td small {
  margin-block-start: 3px;
  color: rgba(var(--v-theme-on-surface), 0.52);
  font-size: 0.65rem;
}
.archive-table__numeric {
  text-align: end !important;
  white-space: nowrap;
}
.archive-table code,
.archive-paths code {
  overflow-wrap: anywhere;
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.68rem;
}
.archive-pagination {
  justify-content: space-between;
  min-inline-size: 0;
  padding-block-start: 10px;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 0.7rem;
  gap: 8px;
}
.archive-breadcrumbs {
  min-inline-size: 0;
  overflow-x: auto;
  padding: 3px 0 10px;
}
.archive-breadcrumbs .v-btn {
  flex: 0 0 auto;
  min-inline-size: 0;
  padding-inline: 4px;
  font-size: 0.73rem;
}
.archive-breadcrumbs .v-btn:not(:last-child)::after {
  margin-inline-start: 7px;
  color: rgba(var(--v-theme-on-surface), 0.38);
  content: '/';
}
.archive-files-browser {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-block-size: 0;
  min-inline-size: 0;
}
.archive-directory-list {
  margin-block-end: 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 8px;
}
.archive-directory-list__heading {
  padding: 8px 11px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 0.68rem;
  font-weight: 600;
}
.archive-directory {
  display: flex;
  align-items: center;
  width: 100%;
  min-block-size: 38px;
  padding: 7px 11px;
  border: 0;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: transparent;
  color: inherit;
  text-align: start;
  gap: 8px;
}
.archive-directory:hover {
  background: rgba(var(--v-theme-primary), 0.05);
}
.archive-directory span {
  flex: 1 1 auto;
  overflow-wrap: anywhere;
  font-size: 0.75rem;
}
.archive-dialog__title {
  justify-content: space-between;
  gap: 12px;
}
.archive-dialog__title > div {
  min-inline-size: 0;
  align-items: flex-start;
  flex-direction: column;
  gap: 2px;
}
.archive-dialog__title small {
  color: rgba(var(--v-theme-on-surface), 0.52);
  font-size: 0.65rem;
  font-weight: 400;
}
.archive-dialog-state {
  display: grid;
  justify-items: center;
  min-block-size: 180px;
  padding: 30px 16px;
  color: rgba(var(--v-theme-on-surface), 0.62);
  text-align: center;
  gap: 10px;
}
.archive-dialog-state strong {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.88rem;
}
.archive-dialog-state span {
  font-size: 0.7rem;
}
.archive-dialog-state--error strong {
  color: rgb(var(--v-theme-error));
}
.archive-preview-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-block-end: 14px;
}
.archive-preview-metrics > div {
  padding: 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.11);
  border-radius: 7px;
}
.archive-preview-metrics strong {
  display: block;
  margin-block-start: 4px;
  font-size: 1rem;
}
.archive-batch-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-block-end: 14px;
}
.archive-batch-summary > div {
  min-inline-size: 0;
  padding: 9px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 7px;
}
.archive-batch-summary strong {
  display: block;
  margin-block-start: 4px;
  overflow-wrap: anywhere;
  font-size: 0.77rem;
}
.archive-paths {
  display: grid;
  gap: 8px;
  margin-block: 14px;
}
.archive-paths > div {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr);
  min-inline-size: 0;
  gap: 8px;
}
.archive-cleanup h4 {
  margin: 18px 0 8px;
  font-size: 0.8rem;
}
.archive-cleanup-grid {
  display: grid;
  gap: 6px;
}
.archive-cleanup-grid > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-inline-size: 0;
  padding: 6px 8px;
  border-radius: 5px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  gap: 8px;
}
.archive-cleanup-grid span {
  overflow-wrap: anywhere;
  font-size: 0.68rem;
}
.sr-only {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.archive-mobile-save-dock {
  display: none;
}
.archive-mobile-save-dock__state {
  display: inline-flex;
  align-items: center;
  color: rgb(var(--v-theme-warning));
  font-size: 0.8125rem;
  font-weight: 600;
  white-space: nowrap;
  gap: 8px;
}
.archive-mobile-save-dock__save {
  min-inline-size: 128px;
  font-weight: 600;
}
@media (max-width: 1100px) {
  .archive-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .archive-task-layout {
    grid-template-columns: minmax(180px, 0.4fr) minmax(0, 1fr);
  }
}
@media (max-width: 820px) {
  .archive-header {
    align-items: center;
    min-block-size: 72px;
  }
  .archive-header__actions > .archive-header__run,
  .archive-header__actions > .archive-header__save,
  .archive-header__close-action {
    display: none;
  }
  .archive-header__close-icon {
    display: inline-flex;
  }
  .archive-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
  .archive-nav {
    display: none;
  }
  .archive-mobile-nav {
    display: inline-flex;
  }
  .archive-task-layout {
    grid-template-columns: 1fr;
  }
  .archive-task-layout > .archive-task-detail {
    border-inline-start: 0;
    border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.1);
    padding-inline-start: 0;
  }
  .archive-filter-bar {
    flex-wrap: wrap;
  }
  .archive-filter-bar > .v-input {
    flex: 1 1 180px;
  }
  .archive-mobile-save-dock {
    position: sticky;
    z-index: 20;
    inset-block-end: calc(12px + env(safe-area-inset-bottom));
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-block-size: 64px;
    padding-block: 10px;
    padding-inline: 14px;
    margin-inline: 12px;
    border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
    border-radius: var(--app-surface-radius);
    background: rgba(var(--v-theme-surface), 0.94);
    backdrop-filter: blur(20px);
    box-shadow: 0 -8px 24px rgba(var(--v-theme-on-surface), 0.06);
    gap: 12px;
  }
}
:global(html[data-theme='transparent'] .archive-mobile-save-dock) {
  background: rgba(var(--v-theme-surface), 0.92);
  backdrop-filter: blur(24px);
}
:global(html[data-theme='transparent'].transparent-blur-disabled .archive-mobile-save-dock) {
  background: rgba(var(--v-theme-surface), 0.98);
  backdrop-filter: none;
}
@media (max-width: 620px) {
  .archive-editor__actions {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
  .archive-editor__actions > .v-spacer {
    display: none;
  }
  .archive-editor__actions > .v-btn:last-child {
    grid-column: 1 / -1;
  }
  .archive-config {
    block-size: calc(100dvh - 16px);
    max-block-size: calc(100dvh - 16px);
    min-block-size: 0;
  }
  .archive-body {
    padding: 14px 16px 24px;
  }
  .archive-header {
    min-block-size: 62px;
    padding: 8px 10px;
    align-items: center;
  }
  .archive-header__logo {
    flex-basis: 34px;
    block-size: 34px;
    inline-size: 34px;
  }
  .archive-header__crumbs {
    display: none;
  }
  .archive-header__title-row h1 {
    max-inline-size: 190px;
    overflow-wrap: anywhere;
    font-size: 0.95rem;
  }
  .archive-header__save {
    min-inline-size: 0;
    padding-inline: 10px;
  }
  .archive-header__save :deep(.v-btn__content) {
    font-size: 0;
  }
  .archive-header__save :deep(.v-icon) {
    margin-inline: 0;
  }
  .archive-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .archive-metric {
    padding: 9px 10px;
  }
  .archive-form-grid,
  .archive-form-grid--two,
  .archive-form-grid--three {
    grid-template-columns: 1fr;
  }
  .archive-detail-grid {
    grid-template-columns: 1fr;
  }
  .archive-preview-metrics,
  .archive-batch-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .archive-pagination {
    align-items: flex-start;
    flex-direction: column;
  }
  .archive-progress__row {
    align-items: flex-start;
    grid-template-columns: 1fr auto;
  }
  .archive-progress__detail,
  .archive-progress__capacity {
    grid-column: 1 / -1;
    text-align: start;
  }
}
@media (prefers-reduced-motion: reduce) {
  .archive-table tbody tr,
  .archive-directory {
    transition: none;
  }
}
</style>
