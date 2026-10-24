import { describe, expect, it, vi } from 'vitest'

import { createMockPet } from '@/dev/mockHost'
import {
  AUTONOMOUS_DIALOGUE_INTERVAL_MS,
  defaultDialogue,
  DIALOGUE_DURATION_MS,
  DIALOGUE_INTERVAL_MS,
  DIALOGUE_LINES,
  parseDialogue,
} from '@/stage/dialogue'
import { greetingLines, LineSpeaker, LINES, type DialogueContext } from '@/stage/lines'

function setup(random: () => number = () => 0) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-24T00:00:00Z'))
  const context: DialogueContext = {
    scope: 'AgentPets',
    key: 'builtin-kurisu',
    dialogue: { mode: 'interaction', voice: 'neutral' },
  }
  const pet = createMockPet('stage', context.key)
  const say = vi.fn().mockReturnValue({ shown: true })
  Object.assign(pet, { say })
  const speaker = new LineSpeaker(
    () => pet,
    random,
    () => context,
  )
  return { speaker, say, context, pet }
}

describe('optional dialogue preferences', () => {
  it('preserves legacy Ying behavior without assigning voices from other character names', () => {
    expect(defaultDialogue('ying')).toEqual({ mode: 'interaction', voice: 'default' })
    for (const key of ['builtin-kurisu', 'builtin-nailong', 'imported-pet', 'renamed-pet'])
      expect(defaultDialogue(key)).toEqual({ mode: 'off', voice: 'neutral' })
  })

  it.each([undefined, null, [], '', 1])('does not add a preference from missing or non-object data %o', value => {
    expect(parseDialogue(value)).toBeUndefined()
  })

  it('normalizes invalid values conservatively and copies valid preferences', () => {
    expect(parseDialogue({ mode: 'unknown', voice: 'unknown' })).toEqual({ mode: 'off', voice: 'neutral' })
    expect(parseDialogue({ mode: 'interaction', voice: 'unknown' })).toEqual({ mode: 'off', voice: 'neutral' })
    expect(parseDialogue({ mode: 'interaction' })).toEqual({ mode: 'off', voice: 'neutral' })
    const settings = { mode: 'occasional' as const, voice: 'wry' as const }
    expect(parseDialogue(settings)).toEqual(settings)
    expect(parseDialogue(settings)).not.toBe(settings)
  })

  it('keeps all selectable lines short and free of task-result claims', () => {
    for (const line of Object.values(DIALOGUE_LINES).flatMap(scenes => Object.values(scenes).flat())) {
      expect(Array.from(line).length).toBeLessThanOrEqual(20)
      expect(line).not.toMatch(/下载|任务|完成订阅|整理成功/)
    }
  })
})

describe('contextual LineSpeaker', () => {
  it('leaves unconfigured non-Ying stage Pets silent', () => {
    const { speaker, say, context } = setup()
    delete context.dialogue
    expect(speaker.greet()).toBe(false)
    expect(speaker.say('poke')).toBe(false)
    expect(speaker.say('hop', true)).toBe(false)
    expect(say).not.toHaveBeenCalled()
  })

  it('keeps unconfigured Ying pools, host arguments and timing unchanged', () => {
    const { speaker, say, context } = setup()
    context.key = 'ying'
    delete context.dialogue
    expect(speaker.say('poke')).toBe(true)
    expect(speaker.say('poke')).toBe(true)
    expect(say.mock.calls.every(call => call.length === 1 && LINES.poke.includes(call[0]))).toBe(true)
    expect(speaker.say('wake', true)).toBe(false)
    expect(speaker.say('hop')).toBe(false)
    speaker.greet()
    expect(greetingLines(new Date())).toContain(say.mock.calls.at(-1)![0])
  })

  it.each(['neutral', 'lively', 'wry'] as const)('uses only a user-selected %s pool', voice => {
    const { speaker, say, context } = setup()
    context.dialogue!.voice = voice
    speaker.say('poke')
    expect(DIALOGUE_LINES[voice].poke).toContain(say.mock.calls[0][0])
  })

  it.each(['ying', 'builtin-kurisu'] as const)('resolves the explicit default voice for %s without inference', key => {
    const { speaker, say, context } = setup()
    context.key = key
    context.dialogue!.voice = 'default'
    speaker.say('poke')
    expect(key === 'ying' ? LINES.poke : DIALOGUE_LINES.neutral.poke).toContain(say.mock.calls[0][0])
  })

  it.each(['off', 'interaction', 'occasional'] as const)('separates %s mode from autonomous speech', mode => {
    const { speaker, say, context } = setup()
    context.dialogue!.mode = mode
    expect(speaker.say('poke')).toBe(mode !== 'off')
    vi.advanceTimersByTime(DIALOGUE_INTERVAL_MS)
    expect(speaker.say('hop')).toBe(mode === 'occasional')
    expect(say).toHaveBeenCalledTimes(mode === 'off' ? 0 : mode === 'interaction' ? 1 : 2)
  })

  it('shares the 15-second interaction cooldown across scenes and requests a four-second native bubble', () => {
    const { speaker, say } = setup()
    expect(speaker.say('poke')).toBe(true)
    expect(say.mock.calls[0][1]).toEqual({ duration: DIALOGUE_DURATION_MS })
    vi.advanceTimersByTime(DIALOGUE_INTERVAL_MS - 1)
    expect(speaker.say('drop')).toBe(false)
    vi.advanceTimersByTime(1)
    expect(speaker.say('drop')).toBe(true)
    expect(say).toHaveBeenCalledTimes(2)
  })

  it('keeps autonomous remarks 75 seconds apart without imposing that wait on user interactions', () => {
    const { speaker, say, context } = setup()
    context.dialogue!.mode = 'occasional'
    expect(speaker.say('wake', true)).toBe(true)
    vi.advanceTimersByTime(AUTONOMOUS_DIALOGUE_INTERVAL_MS - 1)
    expect(speaker.say('hop', true)).toBe(false)
    vi.advanceTimersByTime(1)
    expect(speaker.say('hop', true)).toBe(true)
    vi.advanceTimersByTime(DIALOGUE_INTERVAL_MS)
    expect(speaker.say('poke')).toBe(true)
    expect(say).toHaveBeenCalledTimes(3)
  })

  it('samples autonomous events at 25 percent instead of scheduling a later replay', () => {
    const random = vi.fn().mockReturnValue(0)
    const { speaker, say, context } = setup(random)
    context.dialogue!.mode = 'occasional'
    random.mockReturnValueOnce(0.25)
    expect(speaker.say('hop', true)).toBe(false)
    random.mockReturnValueOnce(0.249)
    expect(speaker.say('hop', true)).toBe(true)
    expect(say).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not repeat adjacent contextual lines even after a small pool is exhausted', () => {
    const { speaker, say } = setup()
    for (let index = 0; index < 12; index++) {
      speaker.say('drop')
      vi.advanceTimersByTime(DIALOGUE_INTERVAL_MS)
    }
    const spoken = say.mock.calls.map(call => call[0])
    for (let index = 1; index < spoken.length; index++) expect(spoken[index]).not.toBe(spoken[index - 1])
  })

  it('avoids a recent shared line across scenes and releases it after two minutes', () => {
    const { speaker, say } = setup()
    const original = DIALOGUE_LINES.neutral.drop[0]
    DIALOGUE_LINES.neutral.drop[0] = DIALOGUE_LINES.neutral.poke[0]
    try {
      speaker.say('poke')
      const first = say.mock.calls[0][0]
      vi.advanceTimersByTime(DIALOGUE_INTERVAL_MS)
      speaker.say('drop')
      expect(say.mock.calls[1][0]).not.toBe(first)
      vi.advanceTimersByTime(120_001)
      speaker.say('drop')
      expect(say.mock.calls[2][0]).toBe(first)
    } finally {
      DIALOGUE_LINES.neutral.drop[0] = original
    }
  })

  it.each(['scope', 'key', 'voice'] as const)('isolates throttling and recent lines after a %s change', field => {
    const { speaker, say, context } = setup()
    speaker.say('poke')
    if (field === 'scope') context.scope = 'Clone1'
    if (field === 'key') context.key = 'another-pet'
    if (field === 'voice') context.dialogue!.voice = 'lively'
    expect(speaker.say('poke')).toBe(true)
    expect(say).toHaveBeenCalledTimes(2)
  })

  it.each(['busy', 'hidden', 'rate_limited', 'unavailable'])(
    'drops a %s refusal without polling or queueing',
    reason => {
      const { speaker, say } = setup()
      say.mockReturnValue({ shown: false, reason })
      expect(speaker.say('poke')).toBe(false)
      vi.advanceTimersByTime(DIALOGUE_INTERVAL_MS - 1)
      expect(speaker.say('drop')).toBe(false)
      expect(say).toHaveBeenCalledOnce()
      expect(vi.getTimerCount()).toBe(0)
    },
  )

  it('tries at most one distinct alternative for a contextual duplicate', () => {
    const { speaker, say } = setup()
    say.mockReturnValue({ shown: false, reason: 'duplicate' })
    expect(speaker.say('poke')).toBe(false)
    expect(say).toHaveBeenCalledTimes(2)
    expect(say.mock.calls[1][0]).not.toBe(say.mock.calls[0][0])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('releases the synchronous speaking guard on an exception and does not retry', () => {
    const { speaker, say } = setup()
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    say.mockImplementation(() => {
      throw new Error('host failure')
    })
    expect(speaker.say('poke')).toBe(false)
    expect(speaker.speaking).toBe(false)
    expect(say).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('blocks synchronous reentrant speech', () => {
    const { speaker, say } = setup()
    say.mockImplementation(() => {
      expect(speaker.speaking).toBe(true)
      expect(speaker.say('drop')).toBe(false)
      return { shown: true }
    })
    expect(speaker.say('poke')).toBe(true)
    expect(speaker.speaking).toBe(false)
    expect(say).toHaveBeenCalledOnce()
  })

  it('silently tolerates an old or temporarily unavailable host', () => {
    const { speaker, pet, say } = setup()
    delete pet.say
    expect(speaker.say('poke')).toBe(false)
    expect(say).not.toHaveBeenCalled()
    expect(new LineSpeaker(() => null).greet()).toBe(false)
  })
})
