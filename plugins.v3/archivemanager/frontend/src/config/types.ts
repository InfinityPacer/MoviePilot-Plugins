export type ArchiveFormat = '7z' | 'zip'
export type CompressionLevel = 'store' | 'fast' | 'normal' | 'high'
export type EncryptionMode = 'none' | 'aes256'
export type GroupingMode = 'none' | 'directory' | 'date' | 'directory_date'
export type ArchiveLayout = 'directory' | 'flat'
export type TimeGrain = 'hour' | 'day' | 'month'
export type NotificationEvent = 'success' | 'failure' | 'other'

export type BatchStatus =
  | 'building'
  | 'verifying'
  | 'publishing'
  | 'manifest_pending'
  | 'completed'
  | 'cleaning'
  | 'cleanup_failed'
  | 'failed'
  | 'cancelled'
  | 'interrupted'
  | 'superseded'

export type FileStatus = 'pending' | 'archived' | 'deleted' | 'failed' | 'missing' | 'changed' | string

/** 宿主保存的单个归档任务，字段与插件后端配置模型保持一一对应。 */
export interface ArchiveTask {
  id: string
  name: string
  /** 创建批次时冻结的可读显示名模板。 */
  batch_name_template: string
  /** 外层归档包文件名模板；后端负责补充扩展名和必要的批次 ID。 */
  archive_name_template: string
  archive_layout: ArchiveLayout
  enabled: boolean
  source_dir: string
  output_dir: string
  manifest_dir: string
  cron: string
  timezone: string
  recursive: boolean
  include_patterns: string[]
  exclude_patterns: string[]
  grouping: GroupingMode
  directory_depth: number
  time_grain: TimeGrain
  max_files: number
  max_bytes: number
  max_batches: number
  archive_age_days: number
  stability_seconds: number
  auto_continue: boolean
  max_pending_archives: number
  max_pending_bytes: number
  min_free_bytes: number
  format: ArchiveFormat
  compression: CompressionLevel
  encryption: EncryptionMode
  encrypt_names: boolean
  password: string
  password_version: string
  verify: boolean
  delete_source: boolean
  /** 后端可提供的只读密码状态；不会把密码本身回显到表单。 */
  password_set?: boolean
}

export interface ArchiveConfig {
  enabled: boolean
  /** 是否发送归档运行通知。 */
  notify: boolean
  /** 发送通知的事件类型。 */
  notify_events: NotificationEvent[]
  tasks: ArchiveTask[]
}

export interface RunningJob {
  task_id: string
  batch_id: string
  phase: string
}

export interface LastError {
  task_id: string
  message: string
}

export type TaskPhase = 'history' | 'incremental' | 'waiting_capacity' | 'waiting_retry' | 'idle' | 'stopped' | string

export interface TaskProgress {
  task_id: string
  phase: TaskPhase
  history_total: number
  history_remaining: number
  history_archived: number
  history_unavailable: number
  pending_archives: number
  pending_bytes: number
  free_bytes: number
  reason: string
  active: boolean
}

export interface SummaryPayload {
  archived_files: number
  archive_count: number
  source_bytes: number
  archive_bytes: number
  deleted_files: number
  failed_batches: number
  pending_files: number
  running: RunningJob | null
  queued: string[]
  config_error: string
  last_error: LastError | string | null
  tasks: TaskProgress[]
}

export interface ArchiveFile {
  relative_path: string
  size: number
  mtime_ns: number
  /** manifest 文件项没有状态；状态来自批次 cleanup 或批次阶段。 */
  status?: FileStatus
  batch_id: string
  sha256: string
}

export interface Batch {
  id: string
  task_id: string
  task_name: string
  /** 创建批次时冻结的显示名；旧批次没有该字段时回退到 ID。 */
  batch_name?: string
  /** 创建批次时冻结的外层归档包名；旧批次没有该字段时从路径读取。 */
  archive_name?: string
  status: BatchStatus
  created_at: string
  archive_path: string
  manifest_path: string
  archive_size: number
  source_bytes: number
  file_count: number
  verified: boolean
  archive_sha256: string
  error: string
  archive_available: boolean
  manifest_available: boolean
  /** 源文件版本已变化，旧失败批次仅供审计，不能再次重试。 */
  superseded?: boolean
  files?: ArchiveFile[]
  cleanup: Record<string, 'retained' | 'deleted' | 'missing' | 'changed' | 'failed' | string>
}

export interface BatchPage {
  items: Batch[]
  total: number
}

export interface DirectoryEntry {
  name: string
  path: string
}

export interface FilePage {
  items: ArchiveFile[]
  directories: DirectoryEntry[]
  total: number
}

export interface PreviewBatch {
  group: string
  file_count: number
  total_bytes: number
  oversized: boolean
}

export interface PreviewData {
  file_count: number
  total_bytes: number
  batch_count: number
  batches: PreviewBatch[]
  skipped_count: number
}

export type PreviewStatus = 'running' | 'complete' | 'failed'

export interface PreviewResult {
  status: PreviewStatus
  data: PreviewData | null
  message: string
}

export interface ActionResult {
  job_id?: string
  queued?: boolean
}
