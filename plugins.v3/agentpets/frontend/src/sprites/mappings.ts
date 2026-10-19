import { HOST_ACTIONS, HOST_INTENTS, type SpritePack } from './schema'
import type { Pose } from '@/stage/poses'

export type ActionMappings = Record<string, string>
export const PACK_UPDATED_EVENT = 'agentpets.pack.updated'
export const ACTION_LABELS: Record<string, string> = {
  idle: '待机',
  stand: '站立',
  walk: '行走',
  run: '奔跑',
  dash: '冲刺',
  follow: '跟随姿态',
  'relaxed-sit': '放松坐下',
  'sit-feet-down': '垂腿坐下',
  'dangle-feet': '晃腿',
  'look-up': '抬头',
  think: '思考',
  lie: '躺下',
  crawl: '匍匐',
  jump: '跳跃',
  fall: '下落',
  land: '落地',
  bounce: '弹跳',
  'hold-wall': '挂墙姿态',
  'grab-wall': '抓墙姿态',
  'climb-wall': '爬墙姿态',
  'climb-wall-up': '向上攀爬',
  'climb-wall-down': '向下攀爬',
  'hold-ceiling': '悬挂姿态',
  'crawl-ceiling': '爬顶姿态',
  drag: '被拖起',
  resist: '挣扎',
  'pull-out': '拔起',
  surprise: '惊讶',
  split: '分身姿态',
  cheer: '欢呼',
  'spin-celebrate': '旋转庆祝',
  wave: '招手',
  sit: '坐下',
  'eye-roll': '翻白眼',
  faint: '晕倒',
  disassemble: '散架',
  'happy-jump': '开心跳跃',
  sleep: '睡眠',
  stretch: '伸懒腰',
  peek: '探头',
  scan: '扫视',
  charge: '蓄力',
  'spin-cheer': '旋转欢呼',
  shy: '害羞',
  confused: '疑惑',
  nod: '点头',
  wake: '醒来',
  thinking: '思考',
  speaking: '说话',
  notify: '通知',
  success: '成功',
  warning: '警告',
  error: '错误',
  dragging: '拖动',
  docked: '贴边',
  sleeping: '睡眠状态',
  reaction: '反应',
  'running-right': '向右跑',
  'running-left': '向左跑',
  waving: '原生招手',
  jumping: '原生跳跃',
  failed: '失败反应',
  waiting: '等待',
  running: '工作',
  review: '审阅',
}
export const STAGE_ACTIONS: Record<string, { label: string; action: string; group: string }> = {
  idle: { label: '待机', action: 'idle', group: '日常' },
  blink: { label: '眨眼', action: 'idle', group: '日常' },
  wave: { label: '打开助手／招手', action: 'wave', group: '会话' },
  talk: { label: '说话／气泡', action: 'speaking', group: '会话' },
  think: { label: '思考', action: 'thinking', group: '会话' },
  busy: { label: '执行工具', action: 'charge', group: '会话' },
  alert: { label: '等待用户', action: 'warning', group: '会话' },
  victory: { label: '完成', action: 'success', group: '会话' },
  confused: { label: '出错', action: 'error', group: '会话' },
  doze: { label: '打盹', action: 'sleep', group: '日常' },
  held: { label: '被拖起', action: 'thinking', group: '移动交互' },
  fall: { label: '下落', action: 'jumping', group: '移动交互' },
  jump: { label: '跳起', action: 'jumping', group: '移动交互' },
  sit: { label: '落地坐下', action: 'idle', group: '移动交互' },
  peek: { label: '底角露眼', action: 'peek', group: '移动交互' },
  'walk-left': { label: '向左行走', action: 'running-left', group: '移动交互' },
  'walk-right': { label: '向右行走', action: 'running-right', group: '移动交互' },
}
export const NATIVE_ACTIONS = [
  'idle',
  'running-right',
  'running-left',
  'waving',
  'jumping',
  'failed',
  'waiting',
  'running',
  'review',
]

export function stageAction(pose: Pose, facingLeft: boolean, peeking = false) {
  const key = peeking ? 'peek' : pose.startsWith('walk') ? (facingLeft ? 'walk-left' : 'walk-right') : pose
  return { key: `stage.${key}`, action: STAGE_ACTIONS[key]?.action ?? 'idle' }
}

/** 原生预览直接播放素材；相同帧序列的适配别名不重复列成新动画。 */
export function nativeChoices(pack: SpritePack) {
  const keys = pack.codex_version ? NATIVE_ACTIONS.filter(key => pack.actions[key]) : []
  const signature = (key: string) => pack.actions[key].frames.map(frame => pack.frames[frame]).join(',')
  const seen = new Set(keys.map(signature))
  for (const key of Object.keys(pack.actions)) {
    if (key.startsWith('look-') || keys.includes(key)) continue
    const peekFrame = pack.actions.idle?.frames[0]
    if (
      pack.codex_version &&
      key === 'peek' &&
      pack.actions[key].frames.length === 1 &&
      peekFrame &&
      pack.frames[pack.actions[key].frames[0]] === pack.frames[peekFrame]
    )
      continue
    const sequence = signature(key)
    if (pack.codex_version && seen.has(sequence)) continue
    keys.push(key)
    seen.add(sequence)
  }
  return keys.map(value => ({ value, title: `${ACTION_LABELS[value] ?? value} · ${value}` }))
}

export function mappingRows(mode: 'stage' | 'renderer') {
  if (mode === 'stage') return Object.entries(STAGE_ACTIONS).map(([key, value]) => ({ key: `stage.${key}`, ...value }))
  return [
    ...HOST_ACTIONS.map(action => ({
      key: `action.${action}`,
      action,
      label: ACTION_LABELS[action],
      group: '入口动作',
    })),
    ...HOST_INTENTS.map(action => ({
      key: `intent.${action}`,
      action,
      label: ACTION_LABELS[action],
      group: '入口状态',
    })),
  ]
}

export function sameMappings(a: ActionMappings, b: ActionMappings) {
  return Object.keys(a).length === Object.keys(b).length && Object.entries(a).every(([key, value]) => b[key] === value)
}
