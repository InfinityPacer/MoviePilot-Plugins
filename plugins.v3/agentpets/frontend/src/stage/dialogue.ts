export const DIALOGUE_MODES = ['off', 'interaction', 'occasional'] as const
export const DIALOGUE_VOICES = ['default', 'ying', 'neutral', 'lively', 'wry'] as const

export interface DialogueSettings {
  mode: (typeof DIALOGUE_MODES)[number]
  voice: (typeof DIALOGUE_VOICES)[number]
}

export const DIALOGUE_VOICE_OPTIONS = [
  { title: '小映', value: 'ying' },
  { title: '自然', value: 'neutral' },
  { title: '软萌', value: 'lively' },
  { title: '傲娇', value: 'wry' },
] as const

/** Display legacy defaults by their existing meaning without rewriting stored preferences. */
export function dialogueVoiceForDisplay(key: string, voice: DialogueSettings['voice']) {
  return voice === 'default' ? (key === 'ying' ? 'ying' : 'neutral') : voice
}

export type DialogueScene = 'greeting' | 'poke' | 'tease' | 'drop' | 'wake' | 'hop' | 'idle'
export const DIALOGUE_INTERVAL_MS = 15_000
export const AUTONOMOUS_DIALOGUE_INTERVAL_MS = 75_000
export const IDLE_DIALOGUE_DELAY_MS = 120_000
export const IDLE_DIALOGUE_JITTER_MS = 60_000
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
export const DIALOGUE_LINES: Record<
  Exclude<DialogueSettings['voice'], 'default' | 'ying'>,
  Record<DialogueScene, string[]>
> = {
  neutral: {
    greeting: ['你好，我在这里。', '来了，又见面了。', '今天也请多关照。'],
    poke: ['在呢，我听见了。', '嗯，找我有事吗？', '收到，慢慢来。'],
    tease: ['知道啦，不用再提醒。', '我还在这里呢。', '好啦，我在听。'],
    drop: ['落稳了，换个地方看看。', '这里也不错。', '好了，就在这里。'],
    wake: ['刚刚歇了一会儿。', '醒了，继续啦。', '嗯，我回来了。'],
    hop: ['上来了，歇一下。', '站高一点看看。', '这里也能站稳。'],
    idle: ['不着急，我在这里。', '偶尔发会儿呆也不错。', '安静待一会儿吧。'],
  },
  lively: {
    greeting: ['你来啦，我在这里呢～', '又见面啦，今天也陪着你。', '一起待一会儿，好不好呀？'],
    poke: ['唔，我在呢～轻一点嘛。', '嘿嘿，有点痒，被你找到啦。', '是在叫我吗？我听着呢。'],
    tease: ['呜，听见啦，不许一直戳嘛～', '好啦好啦，让我缓一小下。', '这下真的有点痒啦，轻轻的嘛～'],
    drop: ['呼，站稳啦，这里也不错呢。', '到啦！下次也轻轻放我哦～', '换个地方，继续陪着你呀。'],
    wake: ['唔，醒啦，刚刚眯了一小会儿。', '休息好啦，继续陪你～', '嗯？我在呢，刚才有点困困的。'],
    hop: ['嘿咻，跳上来啦～', '这里高一点，能看得更远呢。', '稳稳站好啦，夸我一下嘛～'],
    idle: ['嘿嘿，安静陪着你呀。', '偶尔发会儿呆，也很舒服呢。', '不用找我，我就在这里哦～'],
  },
  wry: {
    greeting: ['来了？才没有特意等你呢。', '今天也陪你一会儿，顺便而已。', '哼，既然来了，就别急着走。'],
    poke: ['我在呢，笨蛋，轻一点。', '听见啦，才不是没理你。', '有事就说，我又没说不帮你。'],
    tease: ['别一直戳啦……会痒的！', '知道了知道了，真拿你没办法。', '再闹就不理你……一小会儿。'],
    drop: ['站稳了，下次轻一点啦。', '这个位置还不错……算你会挑。', '这里挺好的，不过我可没夸你哦。'],
    wake: ['只是眯了一下，才没有偷懒。', '醒啦……有事叫我就好了。', '休息够了，继续陪你。别多想！'],
    hop: ['这点高度，当然难不倒我。', '站高一点看看，才不是想显摆。', '跳上来了……夸一句也不是不行。'],
    idle: ['我就在这儿，又没有要走。', '只是发会儿呆，才没偷懒。', '安静陪一会儿，也不是不行。'],
  },
}
