import { describe, expect, it } from 'vitest'
import { InteractionMemory, LONG_PRESS_MS } from '@/stage/interaction'

describe('short-lived interaction memory', () => {
  it('keeps the shared long-press threshold at 450ms', () => {
    expect(LONG_PRESS_MS).toBe(450)
  })

  it('starts with a wave and the original landing pause', () => {
    const memory = new InteractionMemory()
    memory.record('source:pet', 0)
    expect(memory.respond('source:pet', 0)).toEqual({ pose: 'wave', duration: 1200 })
    expect(memory.landingDelay('source:pet', 0)).toBe(900)
  })

  it('alternates actual responses at the exact cooldown boundary', () => {
    const memory = new InteractionMemory()
    memory.record('pet', 0)
    expect(memory.respond('pet', 0)?.pose).toBe('wave')
    expect(memory.respond('pet', 2399)).toBeNull()
    expect(memory.respond('pet', 2400)?.pose).toBe('jump')
    expect(memory.respond('pet', 4799)).toBeNull()
    expect(memory.respond('pet', 4800)?.pose).toBe('wave')
  })

  it('lengthens the cooldown without consuming a silenced response', () => {
    const memory = new InteractionMemory()
    memory.record('pet', 0)
    memory.respond('pet', 0)
    memory.record('pet', 1000)
    expect(memory.landingDelay('pet', 1000)).toBe(1050)
    expect(memory.respond('pet', 3599)).toBeNull()
    expect(memory.respond('pet', 3600)).toEqual({ pose: 'jump', duration: 1050 })
  })

  it('bounds repeated attention and landing pauses', () => {
    const memory = new InteractionMemory()
    memory.record('pet', 0)
    memory.respond('pet', 0)
    for (let time = 1; time <= 100; time++) memory.record('pet', time)
    expect(memory.landingDelay('pet', 100)).toBe(1350)
    expect(memory.respond('pet', 5999)).toBeNull()
    expect(memory.respond('pet', 6000)).toEqual({ pose: 'jump', duration: 750 })
  })

  it('fades at 30 seconds without interaction, not at 29999ms', () => {
    const memory = new InteractionMemory()
    memory.record('pet', 0)
    memory.record('pet', 0)
    memory.respond('pet', 0)
    expect(memory.landingDelay('pet', 29999)).toBe(1050)
    expect(memory.respond('pet', 29999)?.pose).toBe('jump')
    expect(memory.landingDelay('pet', 30000)).toBe(900)
    expect(memory.respond('pet', 30000)).toEqual({ pose: 'wave', duration: 1200 })
  })

  it('resets the count, cooldown and pose on a fresh interaction', () => {
    const memory = new InteractionMemory()
    memory.record('pet', 0)
    memory.record('pet', 0)
    memory.respond('pet', 0)
    memory.record('pet', 30000)
    expect(memory.respond('pet', 30000)).toEqual({ pose: 'wave', duration: 1200 })
    expect(memory.landingDelay('pet', 30000)).toBe(900)
  })

  it('keeps plugin instances and pet keys independent', () => {
    const memory = new InteractionMemory()
    memory.record('instance-a:pet-a', 0)
    memory.respond('instance-a:pet-a', 0)
    memory.record('instance-a:pet-a', 100)
    for (const key of ['instance-a:pet-b', 'instance-b:pet-a']) {
      memory.record(key, 100)
      expect(memory.respond(key, 100)).toEqual({ pose: 'wave', duration: 1200 })
      expect(memory.landingDelay(key, 100)).toBe(900)
    }
    expect(memory.respond('instance-a:pet-a', 100)).toBeNull()
  })

  it('evicts the oldest record when a 21st key is stored', () => {
    const memory = new InteractionMemory()
    for (let index = 0; index < 20; index++) {
      memory.record(String(index), 0)
      memory.respond(String(index), 0)
    }
    memory.record('20', 1)
    expect(memory.respond('1', 1)).toBeNull()
    expect(memory.respond('0', 1)?.pose).toBe('wave')
  })

  it('refreshes the eviction order when a pet is touched again', () => {
    const memory = new InteractionMemory()
    for (let index = 0; index < 20; index++) {
      memory.record(String(index), 0)
      memory.respond(String(index), 0)
    }
    memory.record('0', 1)
    memory.record('20', 1)
    expect(memory.respond('0', 1)).toBeNull()
    expect(memory.respond('1', 1)?.pose).toBe('wave')
  })

  it('does not create or evict records when querying a landing delay', () => {
    const memory = new InteractionMemory()
    for (let index = 0; index < 20; index++) {
      memory.record(String(index), 0)
      memory.respond(String(index), 0)
    }
    for (let index = 20; index < 60; index++) expect(memory.landingDelay(String(index), 1)).toBe(900)
    expect(memory.respond('0', 1)).toBeNull()
    expect(memory.landingDelay('0', 30000)).toBe(900)
  })

  it('can safely respond before the first recorded interaction', () => {
    const memory = new InteractionMemory()
    expect(memory.respond('pet', 0)).toEqual({ pose: 'wave', duration: 1200 })
    expect(memory.landingDelay('pet', 0)).toBe(900)
    memory.record('pet', 1)
    expect(memory.respond('pet', 1)).toBeNull()
  })
})
