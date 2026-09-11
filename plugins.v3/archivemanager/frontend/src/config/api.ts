import type {
  ActionResult,
  ArchiveConfig,
  ArchiveTask,
  Batch,
  BatchPage,
  FilePage,
  PreviewResult,
  SummaryPayload,
} from './types'

export interface ApiResponse<T> {
  success: boolean
  message: string
  data: T | null
}

export interface PluginApi {
  get<T = unknown>(path: string): Promise<ApiResponse<T>>
  post<T = unknown>(path: string, body?: unknown): Promise<ApiResponse<T>>
  put<T = unknown>(path: string, body?: unknown): Promise<ApiResponse<T>>
}

const ROOT = 'plugin/ArchiveManager/'

function queryPath(endpoint: string, params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  const suffix = query.toString()
  return `${ROOT}${endpoint}${suffix ? `?${suffix}` : ''}`
}

async function getData<T>(api: PluginApi | undefined, path: string, fallback: T): Promise<T> {
  if (!api) return fallback
  try {
    const response = await api.get<T>(path)
    if (response.success && response.data !== null) return response.data
    throw new Error(response.message || '请求失败')
  } catch {
    console.warn(`[ArchiveManager] ${path} unavailable`)
    return fallback
  }
}

async function postData<T>(api: PluginApi | undefined, path: string, body: unknown): Promise<T | null> {
  if (!api) return null
  try {
    const response = await api.post<T>(path, body)
    if (response.success) return response.data
    throw new Error(response.message || '请求失败')
  } catch {
    console.warn(`[ArchiveManager] ${path} failed`)
    return null
  }
}

const emptySummary: SummaryPayload = {
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
}

export async function loadSummary(api?: PluginApi): Promise<SummaryPayload | null> {
  if (!api) return null
  try {
    const response = await api.get<SummaryPayload>(`${ROOT}summary`)
    if (response.success && response.data) return response.data
    throw new Error(response.message || '请求失败')
  } catch {
    console.warn('[ArchiveManager] summary unavailable')
    return null
  }
}

export function loadSummaryOrEmpty(api?: PluginApi): Promise<SummaryPayload> {
  return loadSummary(api).then(value => value ?? emptySummary)
}

export function listBatches(
  api: PluginApi | undefined,
  params: { task_id?: string; page?: number; page_size?: number; status?: string },
): Promise<BatchPage> {
  return getData(api, queryPath('batches', params), { items: [], total: 0 })
}

export function loadBatch(api: PluginApi | undefined, batchId: string): Promise<Batch | null> {
  return getData<Batch | null>(api, queryPath('batch', { batch_id: batchId }), null)
}

export function listFiles(
  api: PluginApi | undefined,
  params: {
    task_id?: string
    directory?: string
    query?: string
    status?: string
    page?: number
    page_size?: number
  },
): Promise<FilePage> {
  return getData(api, queryPath('files', params), { items: [], directories: [], total: 0 })
}

export function startPreview(api: PluginApi | undefined, task: ArchiveTask): Promise<{ job_id?: string } | null> {
  return postData(api, `${ROOT}preview`, { task })
}

export function pollPreview(api: PluginApi | undefined, jobId: string): Promise<PreviewResult | null> {
  return getData<PreviewResult | null>(api, queryPath('preview', { job_id: jobId }), null)
}

export function runTask(api: PluginApi | undefined, taskId: string): Promise<ActionResult | null> {
  return postData(api, `${ROOT}run`, { task_id: taskId })
}

export function stopTask(api: PluginApi | undefined, taskId?: string): Promise<ActionResult | null> {
  return postData(api, `${ROOT}stop`, taskId ? { task_id: taskId } : {})
}

export function retryBatch(api: PluginApi | undefined, batchId: string): Promise<ActionResult | null> {
  return postData(api, `${ROOT}retry`, { batch_id: batchId })
}

export function repairBatch(api: PluginApi | undefined, batchId: string): Promise<ActionResult | null> {
  return postData(api, `${ROOT}repair`, { batch_id: batchId })
}

export function saveConfig(api: PluginApi | undefined, config: ArchiveConfig): Promise<ActionResult | null> {
  return postData(api, `${ROOT}config`, config)
}
