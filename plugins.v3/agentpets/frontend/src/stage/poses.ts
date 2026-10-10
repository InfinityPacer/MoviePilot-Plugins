import type { AgentPhase } from '@/host'

/** 小映的全部逐帧姿态；文件名即 `assets/ying/<pose>.webp`。 */
export const POSES = [
  'idle',
  'blink',
  'talk',
  'think',
  'jump',
  'wave',
  'held',
  'fall',
  'sit',
  'walk1',
  'walk2',
  'walk3',
  'walk4',
  'doze',
  'confused',
  'alert',
  'victory',
  'busy',
] as const

export type Pose = (typeof POSES)[number]

// 帧图由构建复制到联邦产物的 `assets/ying/`，与暴露组件的 chunk 位于同一目录。
// 先存成变量再交给 URL，避免 Vite 把 `new URL(..., import.meta.url)` 当作静态资源再打包一份。
const ASSET_BASE = import.meta.url

/** 返回某个姿态帧图的绝对地址。 */
export function frameUrl(pose: Pose, base: string = ASSET_BASE): string {
  return new URL(`ying/${pose}.webp`, base).href
}

/** 会话阶段对应的持续姿态；没有持续姿态的阶段返回 null。 */
export function phasePose(phase: AgentPhase | undefined): Pose | null {
  if (phase === 'thinking') return 'think'
  if (phase === 'tool') return 'busy'
  if (phase === 'awaiting') return 'alert'
  return null
}

/** 一次性动作：姿态与保持时长（毫秒）。 */
export interface TransientPose {
  pose: Pose
  duration: number
}

/** 宿主事件对应的一次性动作；不播动作的事件返回 null。 */
export function eventPose(name: string): TransientPose | null {
  switch (name) {
    case 'agent.done':
      return { pose: 'victory', duration: 2200 }
    case 'agent.error':
      return { pose: 'confused', duration: 2600 }
    case 'agent.preview':
    case 'agent.bubble':
      return { pose: 'talk', duration: 1600 }
    case 'agent.panel.open':
      return { pose: 'wave', duration: 1200 }
    default:
      return null
  }
}

/** 角色运动状态。 */
export type Motion = 'idle' | 'walk' | 'drag' | 'fall' | 'sit' | 'peek'

/** 姿态选择的输入。 */
export interface PoseInput {
  motion: Motion
  /** 走路时的帧相位，0 到 3，对应 walk1 到 walk4。 */
  walkPhase: number
  transient: Pose | null
  sustained: Pose | null
  dozing: boolean
  blinking: boolean
  /** 下落中的回弹上升段，用 jump 帧表现离地。 */
  rising?: boolean
}

/**
 * 计算当前应显示的姿态。
 *
 * 拖拽、下落和落地坐下优先于事件动作，因为它们表达的是角色此刻的物理状态；
 * 站定后一次性动作优先于阶段姿态，阶段姿态优先于打盹和眨眼。
 */
export function resolvePose(input: PoseInput): Pose {
  if (input.motion === 'drag') return 'held'
  if (input.motion === 'fall') return input.rising ? 'jump' : 'fall'
  if (input.motion === 'sit') return 'sit'
  if (input.transient) return input.transient
  if (input.sustained) return input.sustained
  if (input.motion === 'walk') return WALK_CYCLE[((input.walkPhase % 4) + 4) % 4]
  if (input.dozing) return 'doze'
  if (input.blinking) return 'blink'
  return 'idle'
}

/**
 * 走路循环：左脚在前着地、经过、右脚在前着地、经过。
 *
 * 帧按走过的距离推进而不是按时间推进，任何移动速度下脚步都与地面位移对齐，不会滑步。
 */
export const WALK_CYCLE: readonly Pose[] = ['walk1', 'walk2', 'walk3', 'walk4']

/** 每帧对应的位移占角色高度的百分比；一个完整循环迈两步，约 0.56 个身高。 */
export const WALK_FRAME_STRIDE_PERCENT = 14

/** 走过的距离换算成走路帧相位。 */
export function walkFrame(distance: number, charHeight: number): number {
  const stride = Math.max(1, (charHeight * WALK_FRAME_STRIDE_PERCENT) / 100)
  return Math.floor(Math.max(0, distance) / stride) % WALK_CYCLE.length
}
