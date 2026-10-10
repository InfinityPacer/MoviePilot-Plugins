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
  /** 图片路径或 URL；上传方式添加的素材包由后端改为 data URL 提供。 */
  sheet: string
  grid: { cols: number; rows: number }
  /** 帧名到格子索引（行优先，从 0 开始）。 */
  frames: Record<string, number>
  /** 宿主动作名或 intent 到帧序列。 */
  actions: Record<string, PackAction>
  /** 宿主随机动作的候选。 */
  random_actions: string[]
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
  if (errors.length) return { pack: null, errors }
  return {
    pack: {
      id: typeof id === 'string' ? id : '',
      name,
      description: typeof data.description === 'string' ? data.description.trim() : '',
      sheet,
      grid: { cols, rows },
      frames,
      actions,
      random_actions: [...new Set(randomActions as string[])],
    },
    errors,
  }
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
): { key: string; action: PackAction } {
  const candidates = [action, intent, thinking ? 'thinking' : null, 'idle']
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
