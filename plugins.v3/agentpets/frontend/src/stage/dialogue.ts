export const DIALOGUE_MODES = ['off', 'interaction', 'occasional'] as const
export const DIALOGUE_VOICES = ['default', 'neutral', 'lively', 'wry'] as const

export interface DialogueSettings {
  mode: (typeof DIALOGUE_MODES)[number]
  voice: (typeof DIALOGUE_VOICES)[number]
}

export type DialogueScene = 'greeting' | 'poke' | 'tease' | 'drop' | 'wake' | 'hop'
export const DIALOGUE_INTERVAL_MS = 15_000
export const AUTONOMOUS_DIALOGUE_INTERVAL_MS = 75_000
export const DIALOGUE_DURATION_MS = 4000

/** Omitted preferences preserve Ying's legacy lines and keep other Pets silent. */
export function defaultDialogue(key: string): DialogueSettings {
  return { mode: key === 'ying' ? 'interaction' : 'off', voice: key === 'ying' ? 'default' : 'neutral' }
}

export function parseDialogue(value: unknown): DialogueSettings | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  const source = value as Partial<DialogueSettings>
  const validVoice = DIALOGUE_VOICES.includes(source.voice!)
  return {
    mode: DIALOGUE_MODES.includes(source.mode!) && validVoice ? source.mode! : 'off',
    voice: validVoice ? source.voice! : 'neutral',
  }
}

/** These selectable voices are not assigned from a character's artwork or name. */
export const DIALOGUE_LINES: Record<Exclude<DialogueSettings['voice'], 'default'>, Record<DialogueScene, string[]>> = {
  neutral: {
    greeting: ['你好，我在这里。', '来了，又见面了。', '今天也请多关照。'],
    poke: ['在呢，我听见了。', '嗯，找我有事吗？', '收到，慢慢来。'],
    tease: ['知道啦，不用再提醒。', '我还在这里呢。', '好啦，我在听。'],
    drop: ['落稳了，换个地方看看。', '这里也不错。', '好了，就在这里。'],
    wake: ['刚刚歇了一会儿。', '醒了，继续啦。', '嗯，我回来了。'],
    hop: ['上来了，歇一下。', '站高一点看看。', '这里也能站稳。'],
  },
  lively: {
    greeting: ['来啦，今天也一起玩！', '嘿，又见面啦！', '你好呀，我在这里！'],
    poke: ['嘿嘿，被你找到啦！', '我在呢，什么事呀？', '收到，精神满满！'],
    tease: ['好啦好啦，有点痒！', '听见啦，不用连着戳！', '嘿嘿，我还在呢！'],
    drop: ['到啦，这里不错！', '换个地方，出发！', '稳稳落地啦！'],
    wake: ['醒啦，继续玩！', '小憩结束，精神回来啦！', '刚刚眯了一下！'],
    hop: ['跳上来啦！', '这个高度刚刚好！', '稳稳站住啦！'],
  },
  wry: {
    greeting: ['来了？我可没在等你。', '今天也在，顺便而已。', '你好，别闹就行。'],
    poke: ['知道了，别连着戳。', '我在，不用确认这么多次。', '听见了，有事直说。'],
    tease: ['再戳也不会变出第二个我。', '好啦，已经收到。', '这点耐心我还是有的。'],
    drop: ['站稳了，这次还不错。', '行吧，就在这里。', '换好了，轻一点就更好了。'],
    wake: ['只是歇一下，别想太多。', '醒了，没耽误事。', '休息结束，继续。'],
    hop: ['上来了，这点高度而已。', '站得住，问题不大。', '换个位置罢了。'],
  },
}
