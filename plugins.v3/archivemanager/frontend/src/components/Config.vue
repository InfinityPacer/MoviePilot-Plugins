<script setup lang="ts">
import { computed, getCurrentInstance, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  cleanupBatches,
  listBatches,
  listFiles,
  loadBatch,
  loadSummary,
  pollPreview,
  previewReclaim,
  reclaimSpace,
  repairBatch,
  retryBatch,
  runTask,
  runTasks,
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
import ArchiveFieldRow from './ArchiveFieldRow.vue'
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
const taskEditorOriginal = ref<ArchiveTask | null>(null)
const includePatternsText = ref('')
const excludePatternsText = ref('')
const minFreeGiB = ref(1)
const maxBytesMiB = ref(4096)
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
const previewTask = ref<ArchiveTask | null>(null)
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
const selectedBatchIds = ref<string[]>([])
const cleanupDialogOpen = ref(false)
const cleanupConfirmOpen = ref(false)
const cleanupDeleteArtifacts = ref(false)
const cleanupBusy = ref(false)

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
const taskEditorDirty = computed(
  () =>
    editorOpen.value &&
    taskEditorOriginal.value !== null &&
    JSON.stringify(taskEditor.value) !== JSON.stringify(taskEditorOriginal.value),
)
const changedItems = computed(() => {
  const items: string[] = []
  if (draft.value.enabled !== original.value.enabled) items.push('启用归档服务')
  if (draft.value.notify !== original.value.notify) items.push('发送通知')
  if (JSON.stringify(draft.value.notify_events) !== JSON.stringify(original.value.notify_events)) items.push('通知事件')
  const originalTasks = new Map(original.value.tasks.map(task => [task.id, task]))
  for (const task of draft.value.tasks) {
    const previous = originalTasks.get(task.id)
    if (!previous || JSON.stringify(task) !== JSON.stringify(previous)) items.push(`任务：${task.name}`)
    originalTasks.delete(task.id)
  }
  for (const task of originalTasks.values()) items.push(`已删除任务：${task.name}`)
  if (taskEditorDirty.value && !items.some(item => item === `任务：${taskEditor.value.name}`))
    items.push(`任务：${taskEditor.value.name}`)
  return items
})
const pendingChangeCount = computed(() => changedItems.value.length)
const hasUnsavedChanges = computed(() => isDirty.value || taskEditorDirty.value)
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
    sequence: '000001',
    global_sequence: '000001',
    file_mtime: '20260128_141930',
  }
  const formatExampleTime = (format: string, fileTime = false): string => {
    const tokens = fileTime
      ? { '%Y': '2026', '%y': '26', '%m': '01', '%d': '28', '%H': '14', '%I': '02', '%M': '19', '%S': '30' }
      : { '%Y': '2026', '%y': '26', '%m': '09', '%d': '11', '%H': '04', '%I': '04', '%M': '00', '%S': '20' }
    return format.replace(/%Y|%y|%m|%d|%H|%I|%M|%S/g, token => tokens[token as keyof typeof tokens] || token)
  }
  const render = (template: string, fallback: string): string => {
    const source = template.trim() || fallback
    const rendered = source.replace(/\{([^{}]+)\}/g, (match, expression: string) => {
      if (expression.startsWith('%')) return formatExampleTime(expression)
      const separator = expression.indexOf(':')
      const field = separator === -1 ? expression : expression.slice(0, separator)
      const format = separator === -1 ? '' : expression.slice(separator + 1)
      if (field === 'file_mtime') return format ? formatExampleTime(format, true) : values.file_mtime
      return separator === -1 && field in values ? values[field as keyof typeof values] : match
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

function openTaskEditor(task?: ArchiveTask, asNew = false): void {
  const next = cloneTask(task ?? createArchiveTask())
  if (asNew) {
    const copy = createArchiveTask({ ...next, id: '', name: `${next.name || '归档任务'}（副本）`, enabled: false })
    taskEditor.value = copy
  } else {
    taskEditor.value = next
  }
  editingTaskId.value = asNew ? null : task?.id ?? null
  includePatternsText.value = next.include_patterns.join('\n')
  excludePatternsText.value = next.exclude_patterns.join('\n')
  minFreeGiB.value = Number((next.min_free_bytes / 1024 ** 3).toFixed(2))
  maxBytesMiB.value = Number((next.max_bytes / 1024 ** 2).toFixed(2))
  taskEditorOriginal.value = cloneTask(next)
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
  task.max_bytes = Math.max(0, Number(maxBytesMiB.value) || 0) * 1024 ** 2
  if (task.delete_source) task.verify = true
  if (task.format === 'zip') task.encrypt_names = false
  if (task.password.length > 0) task.password_set = true
  return task
}

function commitTaskEditor(): void {
  const task = prepareEditorTask()
  const index = draft.value.tasks.findIndex(item => item.id === task.id)
  if (index >= 0) draft.value.tasks.splice(index, 1, task)
  else draft.value.tasks.push(task)
  selectTask(task.id)
  editorOpen.value = false
  taskEditorOriginal.value = null
}

function saveTaskEditor(): void {
  commitTaskEditor()
  saveConfig()
}

function cancelTaskEditor(): void {
  editorOpen.value = false
}

function copyTask(task: ArchiveTask): void {
  openTaskEditor(task, true)
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
  if (taskEditor.value.encryption === 'none') taskEditor.value.encrypt_names = false
  if (taskEditor.value.encryption === 'aes256' && taskEditor.value.format === '7z' && !taskEditor.value.encrypt_names) {
    taskEditor.value.encrypt_names = true
  }
}

function saveConfig(): void {
  if (taskEditorDirty.value) commitTaskEditor()
  const payload = normalizeArchiveConfig(draft.value)
  draft.value = payload
  emit('save', normalizeArchiveConfig(payload))
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

function taskIsRunning(taskId: string): boolean {
  return summaryValue.value.running?.task_id === taskId
}

function taskPhase(progress: SummaryPayload['tasks'][number]): string {
  return taskIsRunning(progress.task_id) ? summaryValue.value.running?.phase || progress.phase : progress.phase
}

function taskIsActive(progress: SummaryPayload['tasks'][number]): boolean {
  return progress.active || taskIsRunning(progress.task_id)
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
    progress.reason || `已归档 ${formatNumber(progress.pending_archives)} 批 · ${formatBytes(progress.pending_bytes)}`
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

async function executeReclaim(): Promise<void> {
  operationBusy.value = true
  const preview = await previewReclaim(props.api)
  operationBusy.value = false
  if (!preview) {
    setNotice('无法读取可回收源文件，请刷新后重试。', 'error')
    return
  }
  const batchCount = Number(preview.batch_count ?? 0)
  const fileCount = Number(preview.file_count ?? 0)
  const estimated = Number(preview.estimated_bytes ?? 0)
  const stagingCount = Number(preview.staging_count ?? 0)
  const stagingBytes = Number(preview.staging_bytes ?? 0)
  if (estimated <= 0) {
    setNotice('暂无需要回收的空间。', 'info')
    return
  }
  const content = `将扫描所有已完成的归档批次，并回收仍保留且校验通过的源文件，同时清理不可恢复的旧暂存。\n\n可回收批次：${batchCount} 个\n可回收文件：${fileCount} 个\n旧暂存目录：${stagingCount} 个\n预计释放空间：${formatBytes(estimated)}${stagingBytes > 0 ? `（其中旧暂存 ${formatBytes(stagingBytes)}）` : ''}`
  const confirmed = hostConfirm
    ? await hostConfirm({ type: 'warn', title: '回收空间', content, confirmText: '开始回收', cancelText: '取消' })
    : window.confirm(`${content}\n\n是否继续？`)
  if (!confirmed) return
  operationBusy.value = true
  const result = await reclaimSpace(props.api)
  operationBusy.value = false
  if (!result) {
    setNotice('回收请求失败，请刷新后重试。', 'error')
    return
  }
  const reclaimResult = result as { queued?: number; estimated_bytes?: number; staging_removed?: number; staging_bytes?: number }
  const queuedEstimate = Number(reclaimResult.estimated_bytes ?? 0)
  const stagingRemoved = Number(reclaimResult.staging_removed ?? 0)
  const suffix = queuedEstimate > 0 ? `，预计回收 ${formatBytes(queuedEstimate)}` : ''
  const stagingSuffix = stagingRemoved > 0 ? `，已清理 ${stagingRemoved} 个旧暂存目录` : ''
  setNotice(`已加入 ${Number(reclaimResult.queued ?? 0)} 个批次的回收队列${suffix}${stagingSuffix}。`, 'success')
  await refreshSummary()
}

async function submitRun(response: Awaited<ReturnType<typeof runTask>>, successMessage: string): Promise<void> {
  if (!response.data) {
    setNotice(response.message, 'error')
    operationMessage.value = ''
    return
  }
  setNotice(successMessage, 'success')
  operationMessage.value = '归档任务运行中…'
  await refreshSummary()
  startOperationPolling()
}

async function executeRun(taskId = activeTaskId.value): Promise<void> {
  if (!taskId) {
    setNotice('请先选择一个归档任务。', 'warning')
    return
  }
  operationMessage.value = '正在提交归档任务…'
  await submitRun(await runTask(props.api, taskId), '归档任务已提交')
}

async function executeRunAll(): Promise<void> {
  if (!draft.value.tasks.length) {
    setNotice('没有可运行的归档任务', 'warning')
    return
  }
  operationMessage.value = '正在提交全部归档任务…'
  await submitRun(await runTasks(props.api), `已提交 ${draft.value.tasks.length} 个归档任务`)
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

function previewDirectoryPath(group: string): string {
  const task = previewTask.value
  if (!task) return group
  const [directoryGroup] = group.split(' | ', 1)
  const parts = directoryGroup.split('/').filter(part => part && part !== '.' && part !== '全部文件')
  const prefix =
    task.archive_layout === 'flat' ? [...parts, '<批次名称>'].join('_') : [...parts, '<批次名称>'].join('/')
  return `${prefix || '<批次名称>'}/<归档包名称>.${task.format}`
}

function previewGroupingBasis(group: string): string {
  const [, ...basis] = group.split(' | ')
  return basis.length ? `分组依据：${basis.join(' | ')}` : '未按目录或日期分组'
}

async function startPreviewForTask(task: ArchiveTask): Promise<void> {
  previewTask.value = task
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
    if (!disposed && requestToken === batchRequestToken && activeView.value === 'batches') {
      batchData.value = result
      const visible = new Set(result.items.map(batch => batch.id))
      selectedBatchIds.value = selectedBatchIds.value.filter(id => visible.has(id))
    }
  } finally {
    if (requestToken === batchRequestToken) batchLoading.value = false
  }
}

function batchCanBeCleaned(batch: Batch): boolean {
  return ['completed', 'failed', 'cancelled', 'superseded'].includes(batch.status)
}

function toggleBatchSelection(batch: Batch, selected: unknown): void {
  if (!batchCanBeCleaned(batch)) return
  if (selected === true) {
    if (!selectedBatchIds.value.includes(batch.id)) selectedBatchIds.value = [...selectedBatchIds.value, batch.id]
  } else {
    selectedBatchIds.value = selectedBatchIds.value.filter(id => id !== batch.id)
  }
}

const allCleanableBatchesSelected = computed(() => {
  const cleanable = batchData.value.items.filter(batchCanBeCleaned)
  return cleanable.length > 0 && cleanable.every(batch => selectedBatchIds.value.includes(batch.id))
})

function toggleAllBatchSelection(selected: unknown): void {
  const ids = batchData.value.items.filter(batchCanBeCleaned).map(batch => batch.id)
  selectedBatchIds.value =
    selected === true
      ? Array.from(new Set([...selectedBatchIds.value, ...ids]))
      : selectedBatchIds.value.filter(id => !ids.includes(id))
}

function openCleanupDialog(): void {
  if (selectedBatchIds.value.length) {
    cleanupDeleteArtifacts.value = false
    cleanupDialogOpen.value = true
  }
}

async function executeBatchCleanup(deleteArtifacts: boolean): Promise<void> {
  cleanupBusy.value = true
  const result = await cleanupBatches(props.api, selectedBatchIds.value, deleteArtifacts)
  cleanupBusy.value = false
  if (!result) {
    setNotice('批次清理失败，请刷新后重试。', 'error')
    return
  }
  selectedBatchIds.value = []
  cleanupDialogOpen.value = false
  cleanupConfirmOpen.value = false
  batchDialogOpen.value = false
  setNotice(`已清理 ${result.batch_count ?? 0} 个批次。`, 'success')
  await Promise.all([loadBatchPage(), refreshSummary(), loadFilePage()])
}

function chooseCleanupOption(deleteArtifacts = cleanupDeleteArtifacts.value): void {
  cleanupDeleteArtifacts.value = deleteArtifacts
  if (cleanupDeleteArtifacts.value) {
    cleanupDialogOpen.value = false
    cleanupConfirmOpen.value = true
    return
  }
  void executeBatchCleanup(false)
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
    <form class="archive-config__form" @submit.prevent="saveConfig">
      <header class="archive-header">
        <div class="archive-header__brand">
          <img :src="archiveLogo" alt="" class="archive-header__logo" />
          <div class="archive-header__identity">
            <div class="archive-header__crumbs">
              <span>MoviePilot</span>
              <VIcon icon="mdi-chevron-right" size="14" />
              <span>插件</span>
              <VIcon icon="mdi-chevron-right" size="14" />
            </div>
            <div class="archive-header__title-row">
              <h1>压缩归档</h1>
              <VChip color="primary" size="x-small" variant="tonal">BETA</VChip>
            </div>
          </div>
        </div>
        <div class="archive-header__actions">
          <VBtn
            class="archive-header__reclaim"
            :disabled="operationBusy"
            prepend-icon="mdi-delete-sweep-outline"
            type="button"
            variant="tonal"
            @click="executeReclaim"
          >
            回收空间
          </VBtn>
          <VBtn
            class="archive-header__run"
            :disabled="!draft.tasks.length || operationBusy"
            prepend-icon="mdi-play"
            type="button"
            variant="tonal"
            @click="executeRunAll"
          >
            提交全部任务
          </VBtn>
          <VBtn
            class="archive-header__save"
            color="primary"
            :disabled="!hasUnsavedChanges"
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
                    <VIcon color="primary" icon="mdi-progress-clock" size="20" />
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
                          :color="taskIsActive(progress) ? 'primary' : 'disabled'"
                          :icon="taskIsActive(progress) ? 'mdi-progress-clock' : 'mdi-check-circle-outline'"
                        /><strong>{{ tasksById.get(progress.task_id)?.name || progress.task_id }}</strong>
                      </div>
                      <VChip
                        :color="
                          taskPhase(progress) === 'waiting_capacity' || taskPhase(progress) === 'waiting_retry'
                            ? 'warning'
                            : taskIsActive(progress)
                              ? 'primary'
                              : 'default'
                        "
                        size="small"
                        variant="tonal"
                        >{{ phaseLabel(taskPhase(progress)) }}</VChip
                      ><span class="archive-progress__detail">{{ progressLabel(progress) }}</span
                      ><span class="archive-progress__capacity"
                        >已归档 {{ formatNumber(progress.pending_archives) }} 批 · {{ formatBytes(progress.pending_bytes)
                        }}<br />可用空间 {{ formatBytes(progress.free_bytes) }}</span
                      >
                    </div>
                  </div>
                </section>
                <section class="archive-section archive-overview-controls">
                  <div class="archive-section__header">
                    <div>
                      <h3>运行设置</h3>
                      <p>控制归档服务是否启用，以及哪些事件发送宿主通知</p>
                    </div>
                  </div>
                  <div class="archive-field-list">
                    <ArchiveFieldRow label="启用插件" hint="开启后插件将处于激活状态" switch-field>
                      <VSwitch
                        v-model="draft.enabled"
                        aria-label="启用插件"
                        color="primary"
                        density="compact"
                        hide-details
                      />
                    </ArchiveFieldRow>
                    <ArchiveFieldRow label="发送通知" hint="是否在特定事件发生时发送通知" switch-field>
                      <VSwitch
                        v-model="draft.notify"
                        aria-label="发送通知"
                        color="primary"
                        density="compact"
                        hide-details
                      />
                    </ArchiveFieldRow>
                    <ArchiveFieldRow label="通知事件" hint="选择需要发送通知的事件">
                      <VSelect
                        v-model="draft.notify_events"
                        aria-label="通知事件"
                        chips
                        closable-chips
                        density="compact"
                        hide-details
                        :items="notificationEventOptions"
                        item-title="title"
                        item-value="value"
                        multiple
                        variant="outlined"
                      />
                    </ArchiveFieldRow>
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
                        aria-label="复制归档任务"
                        color="primary"
                        icon
                        size="small"
                        variant="text"
                        @click="copyTask(selectedTask)"
                        ><VIcon icon="mdi-content-copy" /><VTooltip activator="parent" text="复制任务" /></VBtn
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
                      <span>文件分组</span
                      ><strong>{{ groupingOptions.find(item => item.value === selectedTask.grouping)?.title }}</strong>
                    </div>
                    <div>
                      <span>文件限制</span
                      ><strong
                        >{{ selectedTask.max_files ? `${formatNumber(selectedTask.max_files)} 个` : '不限数量' }} ·
                        {{ selectedTask.max_bytes ? `${formatNumber(selectedTask.max_bytes / 1024 ** 2)} M` : '不限体积' }}</strong
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
                      <p>保存任务后会同步写入插件配置</p>
                    </div>
                    <VBtn aria-label="取消编辑" icon size="small" variant="text" @click="cancelTaskEditor"
                      ><VIcon icon="mdi-close"
                    /></VBtn>
                  </div>
                  <div class="archive-editor__group">
                    <h4>1. 任务与目录</h4>
                    <div class="archive-field-list">
                      <ArchiveFieldRow label="任务名" hint="用于任务列表、运行记录和归档清单中识别任务">
                        <VTextField
                          v-model="taskEditor.name"
                          aria-label="任务名"
                          density="compact"
                          hide-details
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="启用" hint="开启后按 Cron 自动运行任务" switch-field>
                        <VSwitch
                          v-model="taskEditor.enabled"
                          aria-label="启用"
                          color="primary"
                          density="compact"
                          hide-details
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="源目录" hint="扫描并归档此目录中的文件，填写容器内绝对路径">
                        <VTextField
                          v-model="taskEditor.source_dir"
                          aria-label="源目录"
                          density="compact"
                          hide-details
                          prepend-inner-icon="mdi-folder-open-outline"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="输出目录" hint="保存归档包和校验文件，填写容器内绝对路径">
                        <VTextField
                          v-model="taskEditor.output_dir"
                          aria-label="输出目录"
                          density="compact"
                          hide-details
                          prepend-inner-icon="mdi-archive-outline"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="清单目录" hint="保存 Markdown 和 JSON 清单，留空时跟随输出目录">
                        <VTextField
                          v-model="taskEditor.manifest_dir"
                          aria-label="清单目录"
                          density="compact"
                          hide-details
                          prepend-inner-icon="mdi-file-document-outline"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="Cron" hint="使用五段 Cron 表达式，例如 0 2 * * * 表示每天 02:00">
                        <VTextField
                          v-model="taskEditor.cron"
                          aria-label="Cron"
                          density="compact"
                          hide-details
                          prepend-inner-icon="mdi-clock-outline"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                    </div>
                  </div>
                  <div class="archive-editor__group">
                    <h4>2. 命名规则</h4>
                    <div class="archive-field-list">
                      <ArchiveFieldRow label="批次名称" hint="支持任务名、日期、时间、序号和文件修改时间变量">
                        <VTextField
                          v-model="taskEditor.batch_name_template"
                          aria-label="批次名称"
                          density="compact"
                          hide-details
                          prepend-inner-icon="mdi-label-outline"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="归档包名称" hint="生成不含扩展名的归档包名称，变量规则与批次名称相同">
                        <VTextField
                          v-model="taskEditor.archive_name_template"
                          aria-label="归档包名称"
                          density="compact"
                          hide-details
                          prepend-inner-icon="mdi-file-certificate-outline"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <div class="archive-naming-preview">
                        <span>名称示例</span>
                        <code>批次：{{ namingExamples.batch }}</code>
                        <code>归档包：{{ namingExamples.archive }}</code>
                      </div>
                    </div>
                  </div>
                  <div class="archive-editor__group">
                    <h4>3. 文件范围</h4>
                    <div class="archive-field-list">
                      <ArchiveFieldRow label="目录布局" hint="按目录保留来源层级，扁平布局合并为一层目录">
                        <VSelect
                          v-model="taskEditor.archive_layout"
                          aria-label="目录布局"
                          class="archive-layout-select"
                          density="compact"
                          hide-details
                          :items="[
                            { title: '按目录（来源目录 / 批次名称）', value: 'directory' },
                            { title: '扁平（来源目录_批次名称）', value: 'flat' },
                          ]"
                          item-title="title"
                          item-value="value"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="递归扫描" hint="开启后扫描源目录下的所有子目录" switch-field>
                        <VSwitch
                          v-model="taskEditor.recursive"
                          aria-label="递归扫描"
                          color="primary"
                          density="compact"
                          hide-details
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="目录深度" hint="按目录分组时保留的来源目录层级，最小为 1">
                        <VTextField
                          v-model.number="taskEditor.directory_depth"
                          aria-label="目录深度"
                          density="compact"
                          hide-details
                          min="1"
                          type="number"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="包含文件" hint="每行一个 glob，留空时允许所有文件">
                        <VTextarea
                          v-model="includePatternsText"
                          aria-label="包含文件"
                          density="compact"
                          hide-details
                          rows="3"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="排除文件" hint="每行一个 glob，命中的文件不会进入归档">
                        <VTextarea
                          v-model="excludePatternsText"
                          aria-label="排除文件"
                          density="compact"
                          hide-details
                          rows="3"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="文件分组" hint="按来源目录、文件修改日期或两者组合分组">
                        <VSelect
                          v-model="taskEditor.grouping"
                          aria-label="文件分组"
                          density="compact"
                          hide-details
                          :items="groupingOptions"
                          item-title="title"
                          item-value="value"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="时间粒度" hint="按时间分组时使用小时、天或月">
                        <VSelect
                          v-model="taskEditor.time_grain"
                          aria-label="时间粒度"
                          density="compact"
                          hide-details
                          :items="timeGrainOptions"
                          item-title="title"
                          item-value="value"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                    </div>
                  </div>
                  <div class="archive-editor__group">
                    <h4>4. 批次与续跑</h4>
                    <div class="archive-field-list">
                      <ArchiveFieldRow label="每轮批次" hint="限制单轮创建的批次数量，剩余文件下轮处理">
                        <VTextField
                          v-model.number="taskEditor.max_batches"
                          aria-label="每轮批次"
                          density="compact"
                          hide-details
                          min="1"
                          type="number"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="每批文件数" hint="限制单个归档包的文件数量，0 表示不限">
                        <VTextField
                          v-model.number="taskEditor.max_files"
                          aria-label="每批文件数"
                          density="compact"
                          hide-details
                          min="0"
                          type="number"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="每批体积" hint="限制单个归档包的源文件体积，0 表示不限">
                        <VTextField
                          v-model.number="maxBytesMiB"
                          aria-label="每批体积"
                          density="compact"
                          hide-details
                          min="0"
                          type="number"
                          suffix="M"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="文件保留天数" hint="按文件修改时间过滤近期文件，0 表示不限">
                        <VTextField
                          v-model.number="taskEditor.archive_age_days"
                          aria-label="文件保留天数"
                          density="compact"
                          hide-details
                          min="0"
                          type="number"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="稳定时间" hint="归档前等待文件属性稳定，避免处理仍在写入的文件">
                        <VTextField
                          v-model.number="taskEditor.stability_seconds"
                          aria-label="稳定时间"
                          density="compact"
                          hide-details
                          min="1"
                          type="number"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow
                        label="自动续跑"
                        hint="达到空间或成品限制后定期复核，条件恢复时继续归档"
                        switch-field
                      >
                        <VSwitch
                          v-model="taskEditor.auto_continue"
                          aria-label="自动续跑"
                          color="primary"
                          density="compact"
                          hide-details
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="成品批次上限" hint="本地成品达到此批次数量时暂停续跑，0 表示不限">
                        <VTextField
                          v-model.number="taskEditor.max_pending_archives"
                          aria-label="成品批次上限"
                          density="compact"
                          hide-details
                          min="0"
                          type="number"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="成品体积上限" hint="本地成品达到此体积时暂停续跑，0 表示不限">
                        <VTextField
                          v-model.number="taskEditor.max_pending_bytes"
                          aria-label="成品体积上限"
                          density="compact"
                          hide-details
                          min="0"
                          type="number"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="预留空间" hint="预计归档完成后至少保留的可用空间，0 表示不预留">
                        <VTextField
                          v-model.number="minFreeGiB"
                          aria-label="预留空间"
                          density="compact"
                          hide-details
                          min="0"
                          step="0.1"
                          suffix="GiB"
                          type="number"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                    </div>
                  </div>
                  <div class="archive-editor__group">
                    <h4>5. 压缩与完成</h4>
                    <div class="archive-field-list">
                      <ArchiveFieldRow label="格式" hint="选择生成 7z 或 ZIP 归档包，加密文件名仅支持 7z">
                        <VSelect
                          :model-value="taskEditor.format"
                          aria-label="格式"
                          density="compact"
                          hide-details
                          :items="formatOptions"
                          item-title="title"
                          item-value="value"
                          variant="outlined"
                          @update:model-value="requestFormat"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="压缩级别" hint="压缩级别越高通常越节省空间，同时需要更多处理时间">
                        <VSelect
                          v-model="taskEditor.compression"
                          aria-label="压缩级别"
                          density="compact"
                          hide-details
                          :items="compressionOptions"
                          item-title="title"
                          item-value="value"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="加密" hint="选择 AES-256 后需要提供密码">
                        <VSelect
                          :model-value="taskEditor.encryption"
                          aria-label="加密"
                          density="compact"
                          hide-details
                          :items="encryptionOptions"
                          item-title="title"
                          item-value="value"
                          variant="outlined"
                          @update:model-value="handleEncryption"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow
                        label="密码"
                        :hint="
                          taskEditorHasSavedPassword
                            ? '已保存密码不会回显，输入新值可覆盖'
                            : '启用 AES-256 时填写，密码只写入不会回显'
                        "
                      >
                        <VTextField
                          v-model="taskEditor.password"
                          aria-label="密码"
                          autocomplete="new-password"
                          density="compact"
                          hide-details
                          type="password"
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="密码版本" hint="用于在清单中辨认所用密码，不保存密码内容">
                        <VTextField
                          v-model="taskEditor.password_version"
                          aria-label="密码版本"
                          density="compact"
                          hide-details
                          variant="outlined"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow
                        label="加密文件名"
                        hint="使用 7z AES-256 时隐藏归档包内的文件名列表"
                        switch-field
                      >
                        <VSwitch
                          :model-value="taskEditor.encrypt_names"
                          aria-label="加密文件名"
                          color="primary"
                          :disabled="taskEditor.encryption !== 'aes256'"
                          density="compact"
                          hide-details
                          @update:model-value="requestEncryptNames"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow label="完成校验" hint="发布成品前完整读回归档并核对文件清单和哈希" switch-field>
                        <VSwitch
                          :model-value="taskEditor.verify"
                          aria-label="完成校验"
                          color="primary"
                          :disabled="taskEditor.delete_source"
                          density="compact"
                          hide-details
                          @update:model-value="handleVerify"
                        />
                      </ArchiveFieldRow>
                      <ArchiveFieldRow
                        label="删除源文件"
                        hint="归档、清单和完整校验均成功后删除对应源文件"
                        switch-field
                      >
                        <VSwitch
                          :model-value="taskEditor.delete_source"
                          aria-label="删除源文件"
                          color="error"
                          density="compact"
                          hide-details
                          @update:model-value="handleDeleteSource"
                        />
                      </ArchiveFieldRow>
                    </div>
                    <VAlert
                      v-if="taskEditor.delete_source"
                      class="archive-editor__warning"
                      density="compact"
                      type="warning"
                      variant="tonal"
                    >
                      启用后会强制校验，失败时保留源文件。
                    </VAlert>
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
              <div class="archive-filter-bar archive-filter-bar--batches">
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
                <VBtn
                  v-if="selectedBatchIds.length"
                  color="error"
                  prepend-icon="mdi-delete-sweep-outline"
                  variant="tonal"
                  @click="openCleanupDialog"
                  >清理 {{ selectedBatchIds.length }} 个批次</VBtn
                >
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
                      <th class="archive-table__selection">
                        <VCheckbox
                          aria-label="选择全部可清理批次"
                          :model-value="allCleanableBatchesSelected"
                          hide-details
                          density="compact"
                          @update:model-value="toggleAllBatchSelection"
                        />
                      </th>
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
                      <td class="archive-table__selection">
                        <VCheckbox
                          :aria-label="`选择批次 ${batch.batch_name || batch.id}`"
                          :disabled="!batchCanBeCleaned(batch)"
                          :model-value="selectedBatchIds.includes(batch.id)"
                          hide-details
                          density="compact"
                          @click.stop
                          @update:model-value="toggleBatchSelection(batch, $event)"
                        />
                      </td>
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
              <div v-else>
                <div class="archive-filter-bar archive-filter-bar--files">
                  <VSelect
                    aria-label="文件任务"
                    clearable
                    v-model="fileTaskFilter"
                    :items="draft.tasks.map(task => ({ title: task.name, value: task.id }))"
                    item-title="title"
                    item-value="value"
                    label="任务"
                    variant="outlined"
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
                  /><VTextField
                    v-model="fileQuery"
                    append-inner-icon="mdi-magnify"
                    clearable
                    label="搜索相对路径"
                    variant="outlined"
                    @click:append-inner="submitFileSearch"
                    @keyup.enter="submitFileSearch"
                  />
                </div>
                <div v-if="!hasFileTaskSelection" class="archive-empty archive-empty--table">
                  <VIcon icon="mdi-format-list-checks" size="34" /><strong>请选择归档任务</strong
                  ><span>选择任务后，可以按目录、状态或相对路径查询文件。</span>
                </div>
                <template v-else>
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
                    <div v-if="fileData.items.length" class="archive-table-wrap">
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
              </div>
            </section>
          </main>

          <aside class="archive-impact-preview">
            <div class="archive-impact-preview__title">
              <VIcon color="primary" icon="mdi-chart-box-outline" size="20" />
              <h2>运行概览</h2>
            </div>
            <ul class="archive-impact-preview__list">
              <li class="archive-impact-preview__item">
                <VIcon icon="mdi-file-check-outline" size="18" />
                <span>已归档文件</span>
                <strong>{{ formatNumber(summaryValue.archived_files) }}</strong>
              </li>
              <li class="archive-impact-preview__item">
                <VIcon icon="mdi-package-variant-closed" size="18" />
                <span>归档批次</span>
                <strong>{{ formatNumber(summaryValue.archive_count) }}</strong>
              </li>
              <li class="archive-impact-preview__item">
                <VIcon icon="mdi-database-arrow-down-outline" size="18" />
                <span>源文件体积</span>
                <strong>{{ formatBytes(summaryValue.source_bytes) }}</strong>
              </li>
              <li class="archive-impact-preview__item">
                <VIcon icon="mdi-archive-arrow-down-outline" size="18" />
                <span>归档体积</span>
                <strong>{{ formatBytes(summaryValue.archive_bytes) }}</strong>
              </li>
            </ul>
            <section v-if="changedItems.length" class="archive-change-summary">
              <div class="archive-change-summary__title">
                <VIcon color="warning" icon="mdi-format-list-checks" size="19" />
                <h3>本次修改</h3>
              </div>
              <ul>
                <li v-for="item in changedItems" :key="item">
                  <VIcon color="warning" icon="mdi-circle" size="6" /><span>{{ item }}</span>
                </li>
              </ul>
            </section>
            <section class="archive-runtime-summary">
              <div class="archive-runtime-summary__title">
                <VIcon color="primary" icon="mdi-progress-clock" size="19" />
                <h3>当前状态</h3>
              </div>
              <p v-if="summaryValue.running">
                正在处理：{{ tasksById.get(summaryValue.running.task_id)?.name || summaryValue.running.task_id }}
              </p>
              <p v-else-if="queuedTaskNames.length">排队任务：{{ queuedTaskNames.join('、') }}</p>
              <p v-else>当前没有运行中的归档任务</p>
            </section>
          </aside>
        </div>
      </div>
      <div v-if="hasUnsavedChanges" class="archive-mobile-save-dock">
        <span aria-live="polite" class="archive-mobile-save-dock__state"
          ><VIcon color="warning" icon="mdi-circle" size="8" />{{ pendingChangeCount }} 项待保存</span
        >
        <VSpacer />
        <VBtn
          class="archive-mobile-save-dock__save"
          color="primary"
          :disabled="!hasUnsavedChanges"
          type="submit"
          variant="flat"
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
                    <th>目录结构</th>
                    <th class="archive-table__numeric">文件数</th>
                    <th class="archive-table__numeric">大小</th>
                    <th>限制</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="batch in previewResult.batches" :key="batch.group">
                    <td>
                      <strong>{{ previewDirectoryPath(batch.group) }}</strong>
                      <small>{{ previewGroupingBasis(batch.group) }}</small>
                    </td>
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

    <VDialog v-model="cleanupDialogOpen" max-width="720" width="calc(100% - 24px)">
      <VCard>
        <VCardTitle>确认清理 {{ selectedBatchIds.length }} 条记录？</VCardTitle>
        <VCardText>
          <p class="archive-cleanup-dialog__intro">请选择清理范围，源文件不会被删除或修改</p>
          <div class="archive-cleanup-options">
            <VBtn
              class="archive-cleanup-option"
              prepend-icon="mdi-database-remove-outline"
              variant="tonal"
              :loading="cleanupBusy && !cleanupDeleteArtifacts"
              @click="executeBatchCleanup(false)"
            >
              仅清理批次记录
              <small>保留归档包和外部清单</small>
            </VBtn>
            <VBtn
              class="archive-cleanup-option archive-cleanup-option--danger"
              color="error"
              prepend-icon="mdi-archive-remove-outline"
              variant="tonal"
              :disabled="cleanupBusy"
              @click="chooseCleanupOption(true)"
            >
              清理批次记录和归档产物
              <small>删除归档包、校验文件和外部清单</small>
            </VBtn>
          </div>
        </VCardText>
        <VCardActions>
          <VSpacer /><VBtn variant="text" @click="cleanupDialogOpen = false">取消</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="cleanupConfirmOpen" max-width="520" width="calc(100% - 24px)">
      <VCard>
        <VCardTitle>确认清理本地归档产物</VCardTitle>
        <VCardText><strong>确定删除所选批次的归档包和外部清单吗？源文件不会被删除。</strong></VCardText>
        <VCardActions>
          <VSpacer /><VBtn variant="text" @click="cleanupConfirmOpen = false">取消</VBtn>
          <VBtn color="error" :loading="cleanupBusy" variant="flat" @click="executeBatchCleanup(true)"
            >确认删除归档产物</VBtn
          >
        </VCardActions>
      </VCard>
    </VDialog>
  </section>
</template>

<style scoped>
.archive-config {
  container-type: inline-size;
  min-inline-size: 0;
  color: rgb(var(--v-theme-on-surface));
  letter-spacing: 0;
}
.archive-config,
.archive-config * {
  box-sizing: border-box;
}
.archive-config__form {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  min-inline-size: 0;
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
  padding: 14px;
  background: transparent;
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
  grid-template-columns: repeat(3, minmax(0, 1fr));
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
  margin-block-start: 12px;
  grid-template-columns: 168px minmax(0, 1fr) 232px;
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
  color: rgba(var(--v-theme-on-surface), 0.78);
  font-size: 0.75rem;
  font-weight: 600;
}
.archive-nav > .archive-nav__list.v-list {
  flex: 1 1 auto;
  min-block-size: 0;
  overflow-y: auto;
  padding: 6px 4px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.18);
  border-radius: var(--app-surface-radius);
  backdrop-filter: none;
  background: rgba(var(--v-theme-surface), 0.72);
  background-color: rgba(var(--v-theme-surface), 0.72);
}
.archive-nav__list :deep(.v-list-item) {
  position: relative;
  min-block-size: 50px;
  padding-inline: 12px;
  margin-block: 4px;
}
.archive-nav__list :deep(.v-list-item-title) {
  overflow-wrap: anywhere;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.2rem;
}
.archive-nav__list :deep(.v-list-item__prepend > .v-icon) {
  color: rgba(var(--v-theme-on-surface), 0.94);
  font-size: 1.25rem;
}
.archive-nav__list :deep(.v-list-item:hover) {
  background: rgba(var(--v-theme-primary), 0.12);
}
.archive-nav__list :deep(.v-list-item--active) {
  border: 1px solid rgba(var(--v-theme-primary), 0.38);
  background: rgba(var(--v-theme-primary), 0.24);
  color: rgb(var(--v-theme-on-surface));
}
.archive-nav__list :deep(.v-list-item--active .v-list-item-title),
.archive-nav__list :deep(.v-list-item--active .v-list-item__prepend > .v-icon) {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 700;
}
.archive-nav__list :deep(.v-list-item--active)::before {
  position: absolute;
  inset-block: 8px;
  inset-inline-start: 0;
  inline-size: 3px;
  border-radius: 0 3px 3px 0;
  background: rgb(var(--v-theme-primary));
  content: '';
}
.archive-nav__help {
  padding: 12px;
  margin-block-start: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.18);
  border-radius: var(--app-control-radius);
  background: rgba(var(--v-theme-surface), 0.56);
}
.archive-nav__help-title {
  display: block;
  font-size: 0.8125rem;
  line-height: 1.1rem;
}
.archive-nav__help p {
  margin: 6px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 0.6875rem;
  line-height: 1rem;
}
.archive-nav__help-link {
  min-inline-size: 0;
  min-block-size: 28px;
  padding-inline: 0;
  margin-block-start: 7px;
  font-size: 0.75rem;
}
.archive-main {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  min-inline-size: 0;
  background: transparent;
}
.archive-impact-preview {
  min-inline-size: 0;
  overflow: auto;
  padding: 16px;
  border: var(--app-surface-border, 1px solid rgba(var(--v-theme-on-surface), 0.12));
  border-radius: var(--app-surface-radius, 8px);
  background: var(--app-grouped-list-background, rgba(var(--v-theme-surface), 0.5));
  backdrop-filter: var(--app-grouped-list-backdrop-filter, none);
  box-shadow: var(--app-surface-shadow, none);
  background-clip: padding-box;
}
.archive-impact-preview__title,
.archive-runtime-summary__title {
  display: grid;
  align-items: center;
  min-inline-size: 0;
  gap: 10px;
  grid-template-columns: 28px minmax(0, 1fr);
}
.archive-impact-preview h2,
.archive-runtime-summary h3 {
  margin: 0;
  font-size: 0.95rem;
  line-height: 1.25rem;
}
.archive-impact-preview__list {
  padding: 0;
  margin: 10px 0 0;
  list-style: none;
}
.archive-impact-preview__item {
  display: grid;
  align-items: center;
  min-inline-size: 0;
  padding-block: 10px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 0.82rem;
  gap: 10px;
  grid-template-columns: 28px minmax(0, 1fr) auto;
}
.archive-impact-preview__item > .v-icon {
  justify-self: center;
  color: rgba(var(--v-theme-on-surface), 0.54);
}
.archive-impact-preview__item span,
.archive-impact-preview__item strong {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}
.archive-impact-preview__item strong {
  text-align: end;
}

.archive-change-summary {
  padding-block-start: 16px;
  margin-block-start: 16px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.archive-change-summary__title {
  display: grid;
  align-items: center;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 10px;
}
.archive-change-summary__title h3 {
  margin: 0;
  font-size: 0.85rem;
  line-height: 1.2rem;
}
.archive-change-summary ul {
  display: grid;
  gap: 6px;
  padding: 0;
  margin: 10px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 0.76rem;
  list-style: none;
}
.archive-change-summary li {
  display: flex;
  align-items: center;
  min-inline-size: 0;
  gap: 8px;
}
.archive-change-summary li span {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}
.archive-runtime-summary {
  padding-block-start: 16px;
  margin-block-start: 16px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.archive-runtime-summary p {
  margin: 10px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.76rem;
  line-height: 1.25rem;
  overflow-wrap: anywhere;
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
  gap: 9px;
}
.archive-main__title h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.25rem;
}
.archive-main__heading p {
  margin: 3px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.75rem;
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
  padding: 0;
  border: 0;
  background: transparent;
  backdrop-filter: none;
}
.archive-editor > .archive-section__header {
  padding: 18px 16px 0;
  margin-block-end: 12px;
}
.archive-section {
  min-inline-size: 0;
  overflow: hidden;
  padding: 18px 16px;
  border: var(--app-surface-border, 1px solid rgba(var(--v-theme-on-surface), 0.12));
  border-radius: var(--app-surface-radius, 8px);
  background: var(--app-grouped-list-background, rgba(var(--v-theme-surface), 0.5));
  backdrop-filter: var(--app-grouped-list-backdrop-filter, none);
  background-clip: padding-box;
  /* 透明主题下避免外投影被滚动边界裁成内容区矩形暗带。 */
  box-shadow: none;
}
.archive-overview > .archive-section {
  margin-block-start: 12px;
}
.archive-task-layout > .archive-task-detail {
  border-inline-start: var(--app-surface-border, 1px solid rgba(var(--v-theme-on-surface), 0.12));
  padding-inline-start: 16px;
}
.archive-section.archive-editor {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
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
  align-content: center;
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
  min-inline-size: 0;
  padding: 0 16px 14px;
  border: var(--app-surface-border, 1px solid rgba(var(--v-theme-on-surface), 0.12));
  border-radius: var(--app-surface-radius, 8px);
  background: var(--app-grouped-list-background, rgba(var(--v-theme-surface), 0.5));
  background-clip: padding-box;
}
.archive-editor__group + .archive-editor__group {
  margin-block-start: 12px;
}
.archive-editor__group h4 {
  padding: 14px 0 10px;
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 700;
  line-height: 1.25rem;
}
.archive-field-list {
  display: grid;
  min-inline-size: 0;
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
  padding: 16px;
}
.archive-filter-bar {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: center;
  min-inline-size: 0;
  gap: 8px;
  padding-block-start: 8px;
  margin-block-end: 18px;
}
.archive-filter-bar > .v-input {
  width: 100%;
  min-inline-size: 0;
}
.archive-filter-bar > .v-spacer {
  display: none;
}
.archive-filter-bar > .v-btn {
  justify-self: end;
}
.archive-filter-bar--batches {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
}
.archive-filter-bar--files {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}
.archive-filter-bar--files > :nth-child(3) {
  grid-column: 1 / -1;
}
.archive-filter-bar--files > .v-input {
  min-inline-size: 0;
  max-inline-size: 100%;
}
.archive-filter-bar--files > .v-btn {
  justify-self: stretch;
  align-self: center;
}
.archive-filter-bar--files :deep(.v-field),
.archive-filter-bar--files :deep(.v-field__input) {
  min-inline-size: 0;
}
.archive-cleanup-dialog__intro {
  margin: 0;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.76rem;
}
.archive-cleanup-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-block-start: 18px;
}
.archive-cleanup-option {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  min-block-size: 82px;
  padding: 14px 16px;
  text-align: start;
  white-space: normal;
}
.archive-cleanup-option small {
  display: block;
  margin-block-start: 4px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 0.68rem;
  font-weight: 400;
}
.archive-cleanup-option--danger small {
  color: rgba(var(--v-theme-error), 0.82);
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
.archive-table__selection {
  width: 48px;
  padding-inline: 6px !important;
  text-align: center !important;
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
  .archive-header__actions > .archive-header__reclaim,
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
  .archive-impact-preview {
    display: none;
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
    border-block-start: var(--app-surface-border, 1px solid rgba(var(--v-theme-on-surface), 0.12));
    padding-inline-start: 16px;
  }
  .archive-filter-bar,
  .archive-filter-bar--batches,
  .archive-filter-bar--files {
    grid-template-columns: minmax(0, 1fr);
  }
  .archive-filter-bar > .v-btn {
    justify-self: start;
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
  .archive-cleanup-options {
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

@container (width >= 880px) {
  .archive-config__form {
    overflow: hidden;
    block-size: min(90dvh, 820px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .archive-table tbody tr,
  .archive-directory {
    transition: none;
  }
}
</style>
