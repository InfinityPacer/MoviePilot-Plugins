import { describe, expect, it, vi } from 'vitest'

import { createMockPet } from '@/dev/mockHost'
import { greetingLines, LineSpeaker, LINES } from '@/stage/lines'

function petWith(say?: ReturnType<typeof vi.fn>) {
  const pet = createMockPet('stage', 'ying')
  if (say) Object.assign(pet, { say })
  return pet
}

describe('greetingLines', () => {
  it.each([
    [4, '这么晚还没睡呀？'],
    [5, '早上好～今天想看点什么？'],
    [11, '中午好，吃饭配一集刚刚好～'],
    [14, '下午好，我在这儿陪你～'],
    [18, '晚上好！今晚看什么呢？'],
    [23, '这么晚还没睡呀？'],
  ])('picks the local time slot at %i:00', (hour, first) => {
    expect(greetingLines(new Date(2026, 9, 24, hour, 0))[0]).toBe(first)
  })
})

describe('LineSpeaker', () => {
  it('stays silent on hosts without pet.say', () => {
    expect(new LineSpeaker(() => petWith()).say('poke')).toBe(false)
    expect(new LineSpeaker(() => null).say('poke')).toBe(false)
  })

  it('never repeats the previous line of the same scene back to back', () => {
    const say = vi.fn().mockReturnValue({ shown: true })
    const speaker = new LineSpeaker(
      () => petWith(say),
      () => 0,
    )
    for (let index = 0; index < 6; index++) speaker.say('drop')
    const spoken = say.mock.calls.map(call => call[0])
    for (let index = 1; index < spoken.length; index++) expect(spoken[index]).not.toBe(spoken[index - 1])
    expect(spoken.every(line => LINES.drop.includes(line))).toBe(true)
  })

  it('tries one other line when the host reports a duplicate', () => {
    const say = vi.fn().mockReturnValueOnce({ shown: false, reason: 'duplicate' }).mockReturnValue({ shown: true })
    const speaker = new LineSpeaker(
      () => petWith(say),
      () => 0,
    )
    expect(speaker.say('wake')).toBe(true)
    expect(say).toHaveBeenCalledTimes(2)
    expect(say.mock.calls[1][0]).not.toBe(say.mock.calls[0][0])
  })

  it.each(['busy', 'hidden', 'rate_limited', 'unavailable'])('gives up without retrying when refused as %s', reason => {
    const say = vi.fn().mockReturnValue({ shown: false, reason })
    expect(new LineSpeaker(() => petWith(say)).say('poke')).toBe(false)
    expect(say).toHaveBeenCalledTimes(1)
  })

  it('keeps every line inside the host length limit', () => {
    const all = [
      ...Object.values(LINES).flat(),
      ...[0, 6, 12, 15, 20].flatMap(h => greetingLines(new Date(2026, 0, 1, h))),
    ]
    for (const line of all) expect(Array.from(line).length).toBeLessThanOrEqual(20)
  })
})
