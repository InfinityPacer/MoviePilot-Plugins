import type { AgentPetContext } from '@/host'
import {
  AUTONOMOUS_DIALOGUE_INTERVAL_MS,
  defaultDialogue,
  DIALOGUE_DURATION_MS,
  DIALOGUE_INTERVAL_MS,
  DIALOGUE_LINES,
  type DialogueScene,
  type DialogueSettings,
} from './dialogue'

/**
 * 小映的台词场景。每句都跟在已有动作之后说出，不额外制造主动搭话：
 * - `greeting` 页面首次招手，按当地时段问好，每页一次
 * - `poke` 长按戳一下
 * - `tease` 30 秒内被连续戳到第 3 次及以后
 * - `drop` 被拖起后放下
 * - `wake` 打盹时被指针或点击叫醒
 */
export type LineScene = 'poke' | 'tease' | 'drop' | 'wake'
export interface DialogueContext {
  scope: string
  key: string
  dialogue?: DialogueSettings
}

/** 按小时划分的问候时段，区间为 [开始, 结束)。 */
const GREETINGS: Array<{ from: number; to: number; lines: string[] }> = [
  { from: 5, to: 11, lines: ['早上好～今天想看点什么？', '早呀，昨晚的剧追完了吗？'] },
  { from: 11, to: 14, lines: ['中午好，吃饭配一集刚刚好～', '午安！找部片子下饭吧'] },
  { from: 14, to: 18, lines: ['下午好，我在这儿陪你～', '下午好，有新的更新吗？'] },
  { from: 18, to: 23, lines: ['晚上好！今晚看什么呢？', '晚上好，片单准备好了吗？'] },
]
const LATE_NIGHT = ['这么晚还没睡呀？', '夜深了，看完这集就休息吧']

export const LINES: Record<LineScene, string[]> = {
  poke: ['在呢～', '找我有事吗？', '点我一下就能聊天哦', '嘿嘿，有点痒', '今天也一起追剧吧！', '要我帮你找片子吗？'],
  tease: ['再戳要生气了哦！', '好啦好啦，我在听～', '你是不是很闲呀？'],
  drop: ['哇，换个地方～', '这里视野不错！', '轻一点嘛…', '到啦！'],
  wake: ['唔…我没睡着！', '啊，被发现了…', '嗯？刚刚眯了一下'],
}

/** 当地时间对应的问候候选。 */
export function greetingLines(date: Date): string[] {
  const hour = date.getHours()
  return GREETINGS.find(slot => hour >= slot.from && hour < slot.to)?.lines ?? LATE_NIGHT
}

/**
 * 通过宿主 `pet.say` 说台词。旧版主程序没有 `say` 时静默跳过。
 *
 * 宿主负责截断、限流、去重和让位，这里只挑句子：同一场景不连说同一句，
 * 被宿主判为 `duplicate` 时换一句再试一次，其他拒绝原因直接放弃，不重试也不排队。
 */
export class LineSpeaker {
  private last = new Map<string, string>()
  private readonly pet: () => AgentPetContext | null | undefined
  private readonly random: () => number
  private readonly context?: () => DialogueContext
  private contextKey = ''
  private recent: Array<{ line: string; at: number }> = []
  private nextLineAt = 0
  private nextAutonomousAt = 0
  private sending = false

  /** `pet` 每次说话时读取，返回 null 表示当前不该说（预览、工作中等）。 */
  constructor(
    pet: () => AgentPetContext | null | undefined,
    random: () => number = Math.random,
    context?: () => DialogueContext,
  ) {
    this.pet = pet
    this.random = random
    this.context = context
  }

  get speaking(): boolean {
    return this.sending
  }

  reset() {
    this.last.clear()
    this.recent = []
    this.nextLineAt = 0
    this.nextAutonomousAt = 0
  }

  say(scene: LineScene | 'hop', autonomous = false): boolean {
    return this.request(scene, Date.now(), autonomous || scene === 'hop')
  }

  greet(now = new Date()): boolean {
    return this.request('greeting', now.getTime(), false)
  }

  private request(scene: DialogueScene, now: number, autonomous: boolean): boolean {
    const pet = this.pet()
    if (typeof pet?.say !== 'function' || this.sending) return false
    const context = this.context?.()
    const signature = JSON.stringify(context)
    if (signature !== this.contextKey) {
      this.reset()
      this.contextKey = signature
    }
    const legacy = !context || (context.key === 'ying' && !context.dialogue)
    if (legacy) {
      if (autonomous || scene === 'hop') return false
      return this.speak(scene, scene === 'greeting' ? greetingLines(new Date(now)) : LINES[scene], pet)
    }
    const settings = context.dialogue ?? defaultDialogue(context.key)
    if (settings.mode === 'off' || (autonomous && settings.mode !== 'occasional')) return false
    if (now < this.nextLineAt || (autonomous && now < this.nextAutonomousAt)) return false
    if (autonomous && this.random() >= 0.25) return false
    this.nextLineAt = now + DIALOGUE_INTERVAL_MS
    if (autonomous) this.nextAutonomousAt = now + AUTONOMOUS_DIALOGUE_INTERVAL_MS
    const yingVoice = settings.voice === 'ying' || (settings.voice === 'default' && context.key === 'ying')
    const voice = settings.voice === 'default' || settings.voice === 'ying' ? 'neutral' : settings.voice
    const pool =
      yingVoice && scene !== 'hop'
        ? scene === 'greeting'
          ? greetingLines(new Date(now))
          : LINES[scene]
        : DIALOGUE_LINES[voice][scene]
    this.recent = this.recent.filter(item => now >= item.at && now - item.at < 120_000).slice(-6)
    const fresh = pool.filter(line => !this.recent.some(item => item.line === line))
    return this.speak(scene, fresh.length ? fresh : pool, pet, now)
  }

  private speak(scene: string, pool: string[], pet: AgentPetContext, now?: number): boolean {
    if (typeof pet?.say !== 'function' || !pool.length) return false
    const first = this.pick(scene, pool)
    this.sending = true
    try {
      const send = (line: string) => {
        if (now !== undefined) this.recent = [...this.recent, { line, at: now }].slice(-6)
        return now === undefined ? pet.say!(line) : pet.say!(line, { duration: DIALOGUE_DURATION_MS })
      }
      const result = send(first)
      if (result.shown) return true
      if (result.reason !== 'duplicate' || pool.length < 2) return false
      return send(this.pick(scene, pool)).shown
    } catch {
      console.warn('[AgentPets] role dialogue unavailable')
      return false
    } finally {
      this.sending = false
    }
  }

  private pick(scene: string, pool: string[]): string {
    const previous = this.last.get(scene)
    const choices = pool.length > 1 ? pool.filter(line => line !== previous) : pool
    const line = choices[Math.min(choices.length - 1, Math.floor(this.random() * choices.length))]
    this.last.set(scene, line)
    return line
  }
}
