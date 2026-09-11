import { configDefaults, taskDefaults } from './defaults'
import type { ArchiveConfig, ArchiveTask, NotificationEvent } from './types'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function toBoolean(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (['true', '1', 'yes', 'on'].includes(normalized)) return true
    if (['false', '0', 'no', 'off', ''].includes(normalized)) return false
  }
  return fallback
}

function toStringValue(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback
}

function toFiniteNumber(value: unknown, fallback: number, minimum = 0): number {
  const parsed =
    typeof value === 'number' ? value : typeof value === 'string' && value.trim() ? Number(value) : Number.NaN
  return Number.isFinite(parsed) ? Math.max(minimum, parsed) : fallback
}

function toStringArray(value: unknown): string[] {
  const source = Array.isArray(value) ? value : typeof value === 'string' ? value.split(/\r?\n|,/) : []
  return source.map(item => String(item).trim()).filter(Boolean)
}

function makeId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `archive-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function createArchiveTask(value: unknown = {}): ArchiveTask {
  const source = isRecord(value) ? value : {}
  const password = toStringValue(source.password, taskDefaults.password)
  const task: ArchiveTask = {
    ...taskDefaults,
    id: toStringValue(source.id, '') || makeId(),
    name: toStringValue(source.name, taskDefaults.name),
    batch_name_template: toStringValue(source.batch_name_template, taskDefaults.batch_name_template),
    archive_name_template: toStringValue(source.archive_name_template, taskDefaults.archive_name_template),
    archive_layout: source.archive_layout === 'flat' ? 'flat' : 'directory',
    enabled: toBoolean(source.enabled, taskDefaults.enabled),
    source_dir: toStringValue(source.source_dir, taskDefaults.source_dir),
    output_dir: toStringValue(source.output_dir, taskDefaults.output_dir),
    manifest_dir: toStringValue(source.manifest_dir, taskDefaults.manifest_dir),
    cron: toStringValue(source.cron, taskDefaults.cron),
    timezone: toStringValue(source.timezone, taskDefaults.timezone),
    recursive: toBoolean(source.recursive, taskDefaults.recursive),
    include_patterns: toStringArray(source.include_patterns),
    exclude_patterns: toStringArray(source.exclude_patterns),
    grouping: ['none', 'directory', 'date', 'directory_date'].includes(source.grouping as string)
      ? (source.grouping as ArchiveTask['grouping'])
      : taskDefaults.grouping,
    directory_depth: toFiniteNumber(source.directory_depth, taskDefaults.directory_depth, 1),
    time_grain: ['hour', 'day', 'month'].includes(source.time_grain as string)
      ? (source.time_grain as ArchiveTask['time_grain'])
      : taskDefaults.time_grain,
    max_files: toFiniteNumber(source.max_files, taskDefaults.max_files),
    max_bytes: toFiniteNumber(source.max_bytes, taskDefaults.max_bytes),
    max_batches: toFiniteNumber(source.max_batches, taskDefaults.max_batches),
    archive_age_days: toFiniteNumber(source.archive_age_days, taskDefaults.archive_age_days),
    stability_seconds: toFiniteNumber(source.stability_seconds, taskDefaults.stability_seconds),
    auto_continue: toBoolean(source.auto_continue, taskDefaults.auto_continue),
    max_pending_archives: toFiniteNumber(source.max_pending_archives, taskDefaults.max_pending_archives),
    max_pending_bytes: toFiniteNumber(source.max_pending_bytes, taskDefaults.max_pending_bytes),
    min_free_bytes: toFiniteNumber(source.min_free_bytes, taskDefaults.min_free_bytes),
    format: source.format === 'zip' ? 'zip' : taskDefaults.format,
    compression: ['store', 'fast', 'normal', 'high'].includes(source.compression as string)
      ? (source.compression as ArchiveTask['compression'])
      : taskDefaults.compression,
    encryption: source.encryption === 'aes256' ? 'aes256' : taskDefaults.encryption,
    encrypt_names: toBoolean(source.encrypt_names, taskDefaults.encrypt_names),
    password,
    password_version: toStringValue(source.password_version, taskDefaults.password_version),
    verify: toBoolean(source.verify, taskDefaults.verify),
    delete_source: toBoolean(source.delete_source, taskDefaults.delete_source),
  }
  if (source.password_set !== undefined || password.length > 0)
    task.password_set = toBoolean(source.password_set, password.length > 0)
  if (task.delete_source) task.verify = true
  if (task.format === 'zip') task.encrypt_names = false
  return task
}

export function normalizeArchiveConfig(value: unknown): ArchiveConfig {
  const source = isRecord(value) ? value : {}
  const tasks = Array.isArray(source.tasks) ? source.tasks.map(createArchiveTask) : []
  const notifyEvents = toStringArray(source.notify_events).filter((event): event is NotificationEvent =>
    ['success', 'failure', 'other'].includes(event),
  )
  return {
    enabled: toBoolean(source.enabled, configDefaults.enabled),
    notify: toBoolean(source.notify, configDefaults.notify),
    notify_events: source.notify_events === undefined ? [...configDefaults.notify_events] : notifyEvents,
    tasks,
  }
}

export function cloneTask(task: ArchiveTask): ArchiveTask {
  return {
    ...task,
    include_patterns: [...task.include_patterns],
    exclude_patterns: [...task.exclude_patterns],
  }
}
