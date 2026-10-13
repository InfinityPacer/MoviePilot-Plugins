import { parseCalibration, type Calibration } from './calibration'
import builtinPackJson from '@/assets/packs/projector-cat/pack.json'

/** 宿主 renderer 模式的动作名，random_actions 只能取其中的值。 */
export const HOST_ACTIONS = [
  'wave',
  'sit',
  'eye-roll',
  'faint',
  'disassemble',
  'happy-jump',
  'sleep',
  'stretch',
  'peek',
  'scan',
  'charge',
  'spin-cheer',
  'shy',
  'confused',
  'nod',
  'wake',
] as const

/** 宿主 intent，actions 中可用它们为没有专属映射的动作提供回落。 */
export const HOST_INTENTS = [
  'idle',
  'thinking',
  'speaking',
  'notify',
  'success',
  'warning',
  'error',
  'dragging',
  'docked',
  'sleeping',
  'reaction',
] as const

export const BUILTIN_PACK_ID = 'projector-cat'
export const DEFAULT_FRAME_MS = 160

const CODEX_PET_LAYOUTS = [
  { version: 'v1', width: 1536, height: 1872, rows: 9 },
  { version: 'v2', width: 1536, height: 2288, rows: 11 },
] as const

const CODEX_ANIMATION_ROWS = [
  { id: 'idle', count: 6 },
  { id: 'running-right', count: 8 },
  { id: 'running-left', count: 8 },
  { id: 'waving', count: 4 },
  { id: 'jumping', count: 5 },
  { id: 'failed', count: 8 },
  { id: 'waiting', count: 6 },
  { id: 'running', count: 6 },
  { id: 'review', count: 6 },
] as const

const CODEX_LOOK_DIRECTIONS = [
  '000',
  '022-5',
  '045',
  '067-5',
  '090',
  '112-5',
  '135',
  '157-5',
  '180',
  '202-5',
  '225',
  '247-5',
  '270',
  '292-5',
  '315',
  '337-5',
] as const

export interface CodexPetMetadata {
  id?: string
  displayName?: string
  description?: string
}

function codexPetId(value: string): string {
  const slugChars: string[] = []
  for (const character of value.toLowerCase()) {
    const code = character.charCodeAt(0)
    const allowed = (code >= 48 && code <= 57) || (code >= 97 && code <= 122) || character === '_' || character === '-'
    if (allowed) slugChars.push(character)
    else if (slugChars[slugChars.length - 1] !== '-') slugChars.push('-')
  }
  let start = 0
  while (start < slugChars.length && slugChars[start] === '-') start += 1
  let end = slugChars.length
  while (end > start && slugChars[end - 1] === '-') end -= 1
  return slugChars.slice(start, end).join('').slice(0, 32)
}

/** 将 Codex Pet 原生精灵图布局映射成 AgentPets 可保存的素材包。 */
export function buildCodexPetPack(
  filename: string,
  width: number,
  height: number,
  metadata?: CodexPetMetadata,
): { version: 'v1' | 'v2'; pack: SpritePack } {
  const layout = CODEX_PET_LAYOUTS.find(item => item.width === width && item.height === height)
  if (!layout) {
    throw new Error('只支持 Codex Pet v1（1536×1872）或 v2（1536×2288）精灵图')
  }

  const separatorIndex = Math.max(filename.lastIndexOf('/'), filename.lastIndexOf('\\'))
  const basename = filename.slice(separatorIndex + 1)
  const extensionIndex = basename.lastIndexOf('.')
  const stem = (extensionIndex > 0 ? basename.slice(0, extensionIndex) : basename).trim() || 'Codex Pet'
  const displayName = metadata?.displayName?.trim() || stem
  const id = codexPetId(metadata?.id?.trim() || '') || codexPetId(displayName) || codexPetId(stem) || 'codex-pet'
  const frames: Record<string, number> = {}
  const rowFrames: Record<string, string[]> = {}

  CODEX_ANIMATION_ROWS.forEach((row, rowIndex) => {
    rowFrames[row.id] = Array.from({ length: row.count }, (_, column) => {
      const frame = row.id === 'idle' && column === 0 ? 'idle' : row.id + '-' + (column + 1)
      frames[frame] = rowIndex * 8 + column
      return frame
    })
  })

  const lookFrames: string[] = []
  if (layout.version === 'v2') {
    CODEX_LOOK_DIRECTIONS.forEach((direction, index) => {
      const frame = 'look-' + direction
      frames[frame] = (9 + Math.floor(index / 8)) * 8 + (index % 8)
      lookFrames.push(frame)
    })
  }

  const action = (sequence: string[], frame_ms = 160, loop = false) => ({
    frames: [...sequence],
    frame_ms,
    loop,
  })
  const scanFrames = layout.version === 'v2' ? [...lookFrames, lookFrames[0]] : rowFrames.review
  const actions = {
    idle: action(rowFrames.idle, 360, true),
    'running-right': action(rowFrames['running-right'], 140, true),
    'running-left': action(rowFrames['running-left'], 140, true),
    waving: action(rowFrames.waving, 160),
    jumping: action(rowFrames.jumping, 160),
    failed: action(rowFrames.failed, 180),
    waiting: action(rowFrames.waiting, 220, true),
    running: action(rowFrames.running, 160, true),
    review: action(rowFrames.review, 180),
    wave: action(rowFrames.waving, 160),
    notify: action(rowFrames.waving, 160),
    'happy-jump': action(rowFrames.jumping, 160),
    success: action(rowFrames.jumping, 180),
    faint: action(rowFrames.failed, 180),
    error: action(rowFrames.failed, 180),
    thinking: action(rowFrames.waiting, 220, true),
    charge: action(rowFrames.running, 160, true),
    speaking: action(rowFrames.running, 160, true),
    warning: action(rowFrames.review, 180),
    'eye-roll': action(rowFrames.review, 180),
    scan: action(scanFrames, 140),
    ...Object.fromEntries(lookFrames.map(frame => [frame, action([frame])])),
  }

  return {
    version: layout.version,
    pack: {
      id,
      codex_version: layout.version,
      name: displayName.slice(0, 40),
      description: metadata?.description?.trim().slice(0, 120) || '从 Codex Pet ' + layout.version + ' 精灵图导入',
      sheet: '',
      grid: { cols: 8, rows: layout.rows },
      frames,
      actions,
      random_actions: ['wave'],
    },
  }
}

/** 一个动作的帧序列。 */
export interface PackAction {
  /** 依次播放的帧名。 */
  frames: string[]
  /** 每帧停留毫秒数。 */
  frame_ms: number
  /** 播完是否从头循环；否则停在最后一帧。 */
  loop: boolean
}

/** 规范化后的素材包，与后端 `parse_pack` 的输出一致。 */
export interface SpritePack {
  id: string
  name: string
  description: string
  /** Codex 原生布局；旧包由后端按动作布局识别后补充。 */
  codex_version?: 'v1' | 'v2'
  /** 图片路径或 URL；上传方式添加的素材包由后端改为 data URL 提供。 */
  sheet: string
  grid: { cols: number; rows: number }
  /** 帧名到格子索引（行优先，从 0 开始）。 */
  frames: Record<string, number>
  /** 宿主动作名或 intent 到帧序列。 */
  actions: Record<string, PackAction>
  /** 宿主随机动作的候选。 */
  random_actions: string[]
  /** 用户映射覆盖；原始 actions 保持不变。 */
  action_mappings?: Record<string, string>
  calibration?: Calibration
  preview?: string
  avatar?: string
}

const NAME = /^[a-z0-9_-]{1,32}$/

function integer(value: unknown, field: string, low: number, high: number, errors: string[]): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < low || value > high) {
    errors.push(`${field} 必须是 ${low} 到 ${high} 之间的整数`)
    return low
  }
  return value
}

/**
 * 校验素材包 JSON，返回规范结构与错误列表。
 *
 * 规则与后端 `pack.py` 保持一致，用于配置页即时提示；保存时仍以后端校验为准。
 */
export function validatePack(raw: unknown): { pack: SpritePack | null; errors: string[] } {
  const errors: string[] = []
  let source = raw
  if (typeof source === 'string') {
    if (source.length > 64 * 1024) return { pack: null, errors: ['素材包 JSON 不能超过 64KB'] }
    try {
      source = JSON.parse(source)
    } catch (error) {
      return { pack: null, errors: [`素材包 JSON 解析失败：${(error as Error).message}`] }
    }
  }
  if (!source || typeof source !== 'object' || Array.isArray(source)) {
    return { pack: null, errors: ['素材包 JSON 顶层必须是对象'] }
  }
  const data = source as Record<string, unknown>
  const id = data.id ?? ''
  if (id !== '' && (typeof id !== 'string' || !NAME.test(id))) {
    errors.push('id 只能包含小写字母、数字、- 和 _，长度 1 到 32')
  }
  const name = typeof data.name === 'string' ? data.name.trim() : ''
  if (!name || name.length > 40) errors.push('name 必须是 1 到 40 个字符')
  const grid = (data.grid ?? {}) as Record<string, unknown>
  const cols = integer(grid.cols, 'grid.cols', 1, 16, errors)
  const rows = integer(grid.rows, 'grid.rows', 1, 16, errors)
  const codexVersion = data.codex_version
  if (codexVersion != null) {
    if (codexVersion !== 'v1' && codexVersion !== 'v2') errors.push('codex_version 只支持 v1 或 v2')
    else if (cols !== 8 || rows !== (codexVersion === 'v1' ? 9 : 11)) {
      errors.push('codex_version 与网格不匹配，v1 为 8×9，v2 为 8×11')
    }
  }

  const frames: Record<string, number> = {}
  const rawFrames = data.frames
  if (!rawFrames || typeof rawFrames !== 'object' || Array.isArray(rawFrames)) {
    errors.push('frames 必须是帧名到格子索引的非空对象')
  } else {
    for (const [frame, index] of Object.entries(rawFrames)) {
      if (!NAME.test(frame)) errors.push(`帧名 ${frame} 只能包含小写字母、数字、- 和 _`)
      frames[frame] = integer(index, `frames.${frame}`, 0, cols * rows - 1, errors)
    }
    if (!('idle' in frames)) errors.push('frames 必须包含 idle 帧')
  }

  const actions: Record<string, PackAction> = {}
  const rawActions = data.actions ?? {}
  if (typeof rawActions !== 'object' || Array.isArray(rawActions)) errors.push('actions 必须是对象')
  else {
    for (const [key, value] of Object.entries(rawActions as Record<string, unknown>)) {
      const entry = (Array.isArray(value) ? { frames: value } : value) as Record<string, unknown> | null
      const sequence = entry?.frames
      if (!NAME.test(key)) errors.push(`动作名 ${key} 只能包含小写字母、数字、- 和 _`)
      if (!Array.isArray(sequence) || !sequence.length || sequence.length > 64) {
        errors.push(`actions.${key}.frames 必须是 1 到 64 个帧名`)
        continue
      }
      const missing = sequence.filter(frame => typeof frame !== 'string' || !(frame in frames))
      if (missing.length) errors.push(`actions.${key} 引用了未定义的帧 ${missing.join(', ')}`)
      const frameMs = integer(entry?.frame_ms ?? DEFAULT_FRAME_MS, `actions.${key}.frame_ms`, 40, 5000, errors)
      if (entry?.loop !== undefined && typeof entry.loop !== 'boolean') errors.push(`actions.${key}.loop 必须是布尔值`)
      actions[key] = { frames: sequence as string[], frame_ms: frameMs, loop: entry?.loop === true }
    }
  }

  const randomActions = Array.isArray(data.random_actions) ? (data.random_actions as unknown[]) : []
  if (data.random_actions !== undefined && !Array.isArray(data.random_actions)) errors.push('random_actions 必须是列表')
  const unknown = randomActions.filter(item => !(HOST_ACTIONS as readonly unknown[]).includes(item))
  if (unknown.length) errors.push(`random_actions 中 ${unknown.join(', ')} 不是宿主动作名`)

  for (const field of ['preview', 'avatar'] as const) {
    const value = data[field]
    if (value === undefined || value === null || value === '') continue
    if (typeof value !== 'string' || !/^(https?:\/\/\S+|data:image\/)/.test(value)) {
      errors.push(`${field} 只支持 http(s) 地址或 data:image URL`)
    }
  }
  const sheet = typeof data.sheet === 'string' ? data.sheet : ''
  let calibration: Calibration | undefined
  try {
    calibration = parseCalibration(data.calibration)
  } catch (reason) {
    errors.push((reason as Error).message)
  }
  if (errors.length) return { pack: null, errors }
  return {
    pack: {
      id: typeof id === 'string' ? id : '',
      ...(codexVersion === 'v1' || codexVersion === 'v2' ? { codex_version: codexVersion } : {}),
      name,
      description: typeof data.description === 'string' ? data.description.trim() : '',
      sheet,
      grid: { cols, rows },
      frames,
      actions,
      random_actions: [...new Set(randomActions as string[])],
      calibration,
      preview: typeof data.preview === 'string' ? data.preview : '',
      avatar: typeof data.avatar === 'string' ? data.avatar : '',
      action_mappings: Object.fromEntries(
        Object.entries((data.action_mappings ?? {}) as object).filter(
          (entry): entry is [string, string] => typeof entry[1] === 'string',
        ),
      ),
    },
    errors,
  }
}

/** 补齐旧 Codex 包缺少的舞台动作；只生成显示副本，保留原有帧名和自定义动作。 */
export function withCodexStageActions(pack: SpritePack): SpritePack {
  const layout = CODEX_PET_LAYOUTS.find(item => item.version === pack.codex_version)
  if (!layout) return pack
  const defaults = buildCodexPetPack(pack.id, layout.width, layout.height).pack
  const frames = { ...pack.frames }
  const actions = { ...pack.actions }
  const namesByIndex = new Map(Object.entries(frames).map(([name, index]) => [index, name]))

  function frameName(index: number): string {
    const existing = namesByIndex.get(index)
    if (existing) return existing
    let name = `codex-${index}`
    for (let suffix = 1; name in frames; suffix += 1) name = `codex-${index}-${suffix}`
    frames[name] = index
    namesByIndex.set(index, name)
    return name
  }

  for (const [key, action] of Object.entries(defaults.actions)) {
    if (actions[key]) continue
    actions[key] = { ...action, frames: action.frames.map(name => frameName(defaults.frames[name])) }
  }
  return { ...pack, frames, actions }
}

/** 内置放映猫素材包；精灵图随构建原名复制到 `assets/packs/projector-cat/`。 */
export const BUILTIN_PACK: SpritePack = (() => {
  const { pack } = validatePack(builtinPackJson)
  if (!pack) throw new Error('builtin pack is invalid')
  return { ...pack, id: BUILTIN_PACK_ID }
})()

// 先存成变量再交给 URL，避免 Vite 把 `new URL(..., import.meta.url)` 当作静态资源再打包一份。
const ASSET_BASE = import.meta.url

/** 内置素材包内文件的绝对地址。 */
export function builtinAsset(file: string, base: string = ASSET_BASE): string {
  return new URL(`packs/${BUILTIN_PACK_ID}/${file}`, base).href
}

/**
 * 按宿主 props 选择要播放的动作。
 *
 * 查找顺序为 action、intent、thinking 时的 `thinking`、最后回落 `idle`；
 * 素材包没有 idle 动作时用 idle 帧组成单帧序列。
 */
export function resolveAction(
  pack: SpritePack,
  action: string | null | undefined,
  intent: string | null | undefined,
  thinking: boolean,
  options: { mappings?: Record<string, string>; mappingKey?: string; nativeAction?: string } = {},
): { key: string; action: PackAction } {
  if (options.nativeAction && pack.actions[options.nativeAction])
    return { key: options.nativeAction, action: pack.actions[options.nativeAction] }
  const mappings = options.mappings ?? pack.action_mappings ?? {}
  const candidates = [
    options.mappingKey ? mappings[options.mappingKey] : null,
    action ? (mappings[`action.${action}`] ?? action) : null,
    intent ? (mappings[`intent.${intent}`] ?? intent) : null,
    thinking ? (mappings['intent.thinking'] ?? 'thinking') : null,
    'idle',
  ]
  for (const key of candidates) {
    if (key && pack.actions[key]) return { key, action: pack.actions[key] }
  }
  return { key: 'idle', action: { frames: ['idle'], frame_ms: DEFAULT_FRAME_MS, loop: false } }
}

/** 帧在精灵图中的背景定位百分比。 */
export function framePosition(pack: SpritePack, frame: string): { x: number; y: number } {
  const index = pack.frames[frame] ?? pack.frames.idle ?? 0
  const { cols, rows } = pack.grid
  const col = index % cols
  const row = Math.floor(index / cols)
  return { x: cols > 1 ? (col / (cols - 1)) * 100 : 0, y: rows > 1 ? (row / (rows - 1)) * 100 : 0 }
}
