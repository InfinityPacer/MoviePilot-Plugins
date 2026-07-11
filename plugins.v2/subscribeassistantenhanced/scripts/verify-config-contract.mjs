import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')
const defaultsText = readFileSync(resolve(root, 'src/config/defaults.ts'), 'utf8')
const fieldsText = readFileSync(resolve(root, 'src/config/fields.ts'), 'utf8')

const defaultsMarker = 'export const configDefaults: SaeConfig = '
const fieldsMarker = 'export const fields: FieldMeta[] = '
const defaultsStart = defaultsText.indexOf(defaultsMarker)
const fieldsStart = fieldsText.indexOf(fieldsMarker)
if (defaultsStart < 0) throw new Error('configDefaults export not found')
if (fieldsStart < 0) throw new Error('fields export not found')

const defaults = JSON.parse(defaultsText.slice(defaultsStart + defaultsMarker.length).trim())
const fields = JSON.parse(fieldsText.slice(fieldsStart + fieldsMarker.length).trim())
if (!Array.isArray(fields)) throw new Error('fields export must be an array')

const keyMatches = fields.map(field => field.key)
const defaultKeys = Object.keys(defaults).sort()
const fieldKeys = [...keyMatches].sort()
const missing = defaultKeys.filter(key => !fieldKeys.includes(key))
const extra = fieldKeys.filter(key => !defaultKeys.includes(key))
const duplicates = fieldKeys.filter((key, index) => fieldKeys.indexOf(key) !== index)

if (missing.length || extra.length || duplicates.length) {
  console.error({ missing, extra, duplicates })
  throw new Error('Config field contract mismatch')
}

const allowedGroups = new Set(['global', 'cleanup', 'pending', 'pause', 'completion', 'bestVersion', 'guard', 'recognition'])
const allowedKinds = new Set(['switch', 'number', 'text', 'select', 'multi-select', 'cron', 'textarea'])

function expectedKind(field) {
  const value = defaults[field.key]
  if (field.key === 'best_version_cron') return 'cron'
  if (['default_tracker_response', 'recognition_guard_custom_config'].includes(field.key)) return 'textarea'
  if (Array.isArray(value)) return 'multi-select'
  if (field.options) return 'select'
  if (typeof value === 'boolean') return 'switch'
  if (typeof value === 'number') return 'number'
  return 'text'
}

for (const field of fields) {
  if (typeof field.label !== 'string' || !field.label.trim() || field.label === field.key) {
    throw new Error(`Invalid label for ${field.key}`)
  }
  if (!allowedGroups.has(field.group)) throw new Error(`Invalid group for ${field.key}: ${field.group}`)
  if (!allowedKinds.has(field.kind)) throw new Error(`Invalid kind for ${field.key}: ${field.kind}`)
  if (field.kind !== expectedKind(field)) {
    throw new Error(`Unexpected kind for ${field.key}: ${field.kind}`)
  }

  const needsOptions = field.kind === 'select' || field.kind === 'multi-select'
  if (needsOptions) {
    if (!Array.isArray(field.options) || field.options.length === 0) {
      throw new Error(`Options required for ${field.key}`)
    }
    const values = new Set()
    for (const option of field.options) {
      if (typeof option.title !== 'string' || !option.title.trim()) {
        throw new Error(`Invalid option title for ${field.key}`)
      }
      if (!['string', 'number'].includes(typeof option.value)) {
        throw new Error(`Invalid option value for ${field.key}`)
      }
      if (field.kind === 'multi-select' && typeof option.value !== 'string') {
        throw new Error(`Multi-select option values must be strings for ${field.key}`)
      }
      const token = `${typeof option.value}:${String(option.value)}`
      if (values.has(token)) throw new Error(`Duplicate option value for ${field.key}: ${option.value}`)
      values.add(token)
    }
  } else if ('options' in field) {
    throw new Error(`Options are not allowed for ${field.key}`)
  }
}

const byKey = new Map(fields.map(field => [field.key, field]))
const trackerResponse = byKey.get('default_tracker_response')
if (trackerResponse?.group !== 'cleanup' || trackerResponse.dialogOnly !== true || trackerResponse.advanced !== true || trackerResponse.legacyUiKey) {
  throw new Error('default_tracker_response must be the cleanup dialog-only field')
}
if (fields.some(field => field.legacyUiKey)) {
  throw new Error('Legacy UI keys are not allowed')
}
if (fields.some(field => field.key !== 'default_tracker_response' && field.dialogOnly)) {
  throw new Error('Only default_tracker_response may be dialog-only')
}

console.log(`Verified ${defaultKeys.length} SubscribeAssistantEnhanced config keys`)
