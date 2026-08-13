import { configDefaults, type ConfigKey, type SaeConfig } from './defaults'

/** 将动态数值输入归一化为有限 number；空值或非法值保留最近一次有效值。 */
export function normalizeFiniteNumber(current: number, incoming: unknown): number {
  if (incoming === null || incoming === undefined) return current
  if (typeof incoming === 'string' && !incoming.trim()) return current
  const parsed = typeof incoming === 'number' ? incoming : Number(incoming)
  return Number.isFinite(parsed) ? parsed : current
}

function normalizeBoolean(defaultValue: boolean, incoming: unknown): boolean {
  if (incoming === null || incoming === undefined) return defaultValue
  if (typeof incoming === 'boolean') return incoming
  if (typeof incoming === 'string') {
    return ['true', 'on', 'yes', '1', 'guard'].includes(incoming.trim().toLowerCase())
  }
  if (typeof incoming === 'number') return incoming !== 0
  if (Array.isArray(incoming)) return incoming.length > 0
  if (typeof incoming === 'object') return Object.keys(incoming).length > 0
  return Boolean(incoming)
}

function normalizeNumber(defaultValue: number, incoming: unknown): number {
  if (incoming === null || incoming === undefined) return defaultValue
  if (typeof incoming === 'string' && !incoming.trim()) return defaultValue
  if (typeof incoming !== 'number' && typeof incoming !== 'string') return defaultValue
  const parsed = Number(incoming)
  return Number.isFinite(parsed) ? parsed : defaultValue
}

function normalizeString(defaultValue: string, incoming: unknown): string {
  return incoming === null || incoming === undefined ? defaultValue : String(incoming)
}

function normalizeStringArray(defaultValue: string[], incoming: unknown): string[] {
  if (Array.isArray(incoming)) {
    return incoming.map(value => String(value).trim()).filter(Boolean)
  }
  if (typeof incoming === 'string') {
    return incoming
      .split(',')
      .map(value => value.trim())
      .filter(Boolean)
  }
  return [...defaultValue]
}

/** Host 配置来自动态 JSON；这里只接受稳定键并按默认值类型重建完整持久化契约。 */
export function normalizeSaeConfig(input: unknown): SaeConfig {
  const source =
    input !== null && typeof input === 'object' && !Array.isArray(input) ? (input as Record<string, unknown>) : {}
  const entries = (Object.keys(configDefaults) as ConfigKey[]).map(key => {
    const defaultValue = configDefaults[key]
    const incoming = source[key]

    if (Array.isArray(defaultValue)) {
      return [key, normalizeStringArray(defaultValue, incoming)]
    }
    if (typeof defaultValue === 'boolean') {
      return [key, normalizeBoolean(defaultValue, incoming)]
    }
    if (typeof defaultValue === 'number') {
      return [key, normalizeNumber(defaultValue, incoming)]
    }
    return [key, normalizeString(defaultValue, incoming)]
  })

  return Object.fromEntries(entries) as SaeConfig
}
