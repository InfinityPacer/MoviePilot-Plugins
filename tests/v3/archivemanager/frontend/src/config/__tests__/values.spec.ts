import { describe, expect, it } from 'vitest'

import { configDefaults, taskDefaults } from '@/config/defaults'
import { createArchiveTask, normalizeArchiveConfig } from '@/config/values'

describe('ArchiveManager config normalization', () => {
  it('creates a complete task with stable defaults and isolated arrays', () => {
    const first = createArchiveTask({})
    const second = createArchiveTask({})

    expect({ ...first, id: '' }).toMatchObject(taskDefaults)
    expect(first.batch_name_template).toBe('{date}_{sequence}')
    expect(first.archive_layout).toBe('directory')
    expect(first.id).not.toBe('')
    expect(first.id).not.toBe(second.id)
    expect(first.include_patterns).not.toBe(second.include_patterns)
    expect(first.exclude_patterns).not.toBe(second.exclude_patterns)
  })

  it('normalizes dynamic host data without mutating it', () => {
    const input = {
      enabled: 'true',
      tasks: [
        {
          id: 'task-1',
          archive_layout: 'flat',
          enabled: 'false',
          include_patterns: '*.mkv, *.mp4',
          exclude_patterns: [' tmp ', ''],
          max_files: '25',
          max_bytes: 'Infinity',
          delete_source: true,
          verify: false,
          archive_age_days: 14,
          auto_continue: true,
          max_pending_archives: 2,
          max_pending_bytes: 0,
          min_free_bytes: 4096,
          format: 'zip',
          encrypt_names: true,
          password_set: true,
        },
      ],
      retired: true,
    }
    const before = structuredClone(input)

    const result = normalizeArchiveConfig(input)

    expect(result.enabled).toBe(true)
    expect(result.tasks[0]).toMatchObject({
      id: 'task-1',
      archive_layout: 'flat',
      enabled: false,
      include_patterns: ['*.mkv', '*.mp4'],
      exclude_patterns: ['tmp'],
      max_files: 25,
      max_bytes: taskDefaults.max_bytes,
      delete_source: true,
      verify: true,
      format: 'zip',
      encrypt_names: false,
      password_set: true,
      archive_age_days: 14,
      auto_continue: true,
      max_pending_archives: 2,
      max_pending_bytes: 0,
      min_free_bytes: 4096,
    })
    expect(result.tasks[0]).not.toHaveProperty('retired')
    expect(input).toEqual(before)
  })

  it('keeps an empty config valid', () => {
    expect(normalizeArchiveConfig({})).toEqual(configDefaults)
  })

  it('preserves an explicitly empty notification selection', () => {
    expect(normalizeArchiveConfig({ notify: true, notify_events: [] }).notify_events).toEqual([])
    expect(normalizeArchiveConfig({ notify_events: ['success', 'unknown'] }).notify_events).toEqual(['success'])
  })
})
