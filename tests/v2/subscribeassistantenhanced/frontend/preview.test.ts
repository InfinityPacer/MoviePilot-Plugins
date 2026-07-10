import { describe, expect, it } from 'vitest'

import {
  configDefaults,
  type SaeConfig,
} from '../../../../plugins.v2/subscribeassistantenhanced/src/config/defaults'
import {
  buildImpactPreview,
  type PreviewItem,
} from '../../../../plugins.v2/subscribeassistantenhanced/src/config/preview'

type ConfigOverride = Partial<Record<keyof SaeConfig, unknown>>

function previewItems(overrides: ConfigOverride = {}): PreviewItem[] {
  const config = {
    ...configDefaults,
    pending_download_enabled: false,
    download_monitor_enabled: false,
    best_version_type: 'no',
    verify_enabled: false,
    subscription_cleanup_history_type: 'no',
    reset_task: false,
    backfill_best_version_now: false,
    onlyonce: false,
    ...overrides,
  } as unknown as SaeConfig

  return buildImpactPreview(config)
}

function previewTitles(overrides: ConfigOverride = {}): string[] {
  return previewItems(overrides).map(item => item.title)
}

describe('disabled plugin preview', () => {
  const cases: Array<[string, ConfigOverride, string[]]> = [
    ['without one-time actions', {}, ['插件未启用']],
    ['with reset', { reset_task: true }, ['插件未启用', '重置数据']],
    [
      'with immediate backfill',
      { backfill_best_version_now: true },
      ['插件未启用', '立即扫描存量并回填'],
    ],
    [
      'with both one-time actions',
      { reset_task: true, backfill_best_version_now: true },
      ['插件未启用', '重置数据', '立即扫描存量并回填'],
    ],
  ]

  it.each(cases)('%s keeps only initialization effects', (_name, overrides, expected) => {
    expect(previewTitles(overrides)).toEqual(expected)
  })
})

describe('enabled plugin preview matrix', () => {
  const scheduled = ['通用巡检可能运行', '元数据检查可能运行']
  const cases: Array<[string, ConfigOverride, string[]]> = [
    ['base services', { enabled: true }, scheduled],
    [
      'one-time run',
      { enabled: true, onlyonce: true },
      [...scheduled, '立即运行一次'],
    ],
    [
      'pending download checks',
      { enabled: true, pending_download_enabled: true },
      [...scheduled, '下载任务检查可能运行'],
    ],
    [
      'download monitoring',
      { enabled: true, download_monitor_enabled: true },
      [...scheduled, '下载任务检查可能运行', '可能删除下载器任务'],
    ],
    [
      'disabled wash with cron',
      { enabled: true, best_version_type: 'no', best_version_cron: '0 15 * * *' },
      scheduled,
    ],
    [
      'enabled wash without cron',
      { enabled: true, best_version_type: 'all', best_version_cron: '' },
      [...scheduled, '可能自动创建洗版订阅'],
    ],
    [
      'enabled wash with cron',
      { enabled: true, best_version_type: 'all', best_version_cron: '0 15 * * *' },
      [...scheduled, '可能自动创建洗版订阅', '洗版订阅检查可能运行'],
    ],
    [
      'completion verification',
      { enabled: true, verify_enabled: true },
      [...scheduled, '自动纠错可能运行'],
    ],
    [
      'reset action',
      { enabled: true, reset_task: true },
      ['重置数据', ...scheduled],
    ],
    [
      'immediate backfill action',
      { enabled: true, backfill_best_version_now: true },
      ['立即扫描存量并回填', ...scheduled],
    ],
    [
      'subscription cleanup',
      { enabled: true, subscription_cleanup_history_type: 'tv' },
      [...scheduled, '可能清理整理记录或文件'],
    ],
  ]

  it.each(cases)('%s returns the exact title set', (_name, overrides, expected) => {
    expect(previewTitles(overrides)).toEqual(expected)
  })
})

describe('automatic wash impact preview', () => {
  const scheduled = ['通用巡检可能运行', '元数据检查可能运行']
  const enabledCases: Array<[string, string]> = [
    ['all', 'all'],
    ['movie', 'movie'],
    ['tv', 'tv'],
    ['tv episode', 'tv_episode'],
  ]

  it.each(enabledCases)('%s with blank cron warns about automatic creation', (_name, type) => {
    expect(
      previewTitles({ enabled: true, best_version_type: type, best_version_cron: '' }),
    ).toEqual([...scheduled, '可能自动创建洗版订阅'])
  })

  it.each(enabledCases)('%s with non-blank cron keeps both wash impacts', (_name, type) => {
    expect(
      previewTitles({
        enabled: true,
        best_version_type: type,
        best_version_cron: '0 15 * * *',
      }),
    ).toEqual([
      ...scheduled,
      '可能自动创建洗版订阅',
      '洗版订阅检查可能运行',
    ])
  })

  it.each([
    ['blank cron', ''],
    ['non-blank cron', '0 15 * * *'],
  ])('disabled wash with %s shows neither wash impact', (_name, cron) => {
    expect(
      previewTitles({ enabled: true, best_version_type: 'no', best_version_cron: cron }),
    ).toEqual(scheduled)
  })

  it('hides both wash impacts while the plugin is disabled', () => {
    expect(
      previewTitles({ best_version_type: 'tv_episode', best_version_cron: '0 15 * * *' }),
    ).toEqual(['插件未启用'])
  })

  it('describes automatic wash-subscription creation as a warning', () => {
    const creation = previewItems({ enabled: true, best_version_type: 'movie' }).find(
      item => item.title === '可能自动创建洗版订阅',
    )

    expect(creation).toEqual({
      title: '可能自动创建洗版订阅',
      detail: '普通订阅完成后，符合当前洗版范围的媒体可能自动创建洗版订阅。',
      tone: 'warning',
    })
  })
})

describe('enabled operational risk preview matrix', () => {
  const scheduled = ['通用巡检可能运行', '元数据检查可能运行']
  const actionCases: Array<[string, string, string]> = [
    ['pause movie', 'pause_movie', '可能暂停订阅'],
    ['pause tv', 'pause_tv', '可能暂停订阅'],
    ['complete movie', 'complete_movie', '可能完成订阅'],
    ['complete tv', 'complete_tv', '可能完成订阅'],
    ['delete movie', 'delete_movie', '可能删除订阅'],
    ['delete tv', 'delete_tv', '可能删除订阅'],
  ]

  it.each(actionCases)('%s adds its exact risk category', (_name, action, expectedTitle) => {
    expect(previewTitles({ enabled: true, no_download_actions: [action] })).toEqual([
      ...scheduled,
      expectedTitle,
    ])
  })

  it('deduplicates categories and keeps pause, completion, deletion order', () => {
    expect(
      previewTitles({
        enabled: true,
        no_download_actions: [
          'delete_tv',
          'pause_movie',
          'complete_tv',
          'pause_tv',
          'delete_movie',
          'complete_movie',
        ],
      }),
    ).toEqual([...scheduled, '可能暂停订阅', '可能完成订阅', '可能删除订阅'])
  })

  const thresholdCases: Array<[string, ConfigOverride, string[]]> = [
    [
      'movie zero',
      { movie_no_download_days: 0, no_download_actions: ['pause_movie'] },
      scheduled,
    ],
    [
      'TV zero',
      { tv_no_download_days: 0, no_download_actions: ['complete_tv'] },
      scheduled,
    ],
    [
      'both zero',
      {
        movie_no_download_days: 0,
        tv_no_download_days: 0,
        no_download_actions: ['pause_movie', 'complete_tv', 'delete_movie'],
      },
      scheduled,
    ],
    [
      'mixed action and media thresholds',
      {
        movie_no_download_days: 0,
        tv_no_download_days: 2,
        no_download_actions: ['delete_movie', 'pause_tv', 'complete_movie', 'complete_tv'],
      },
      [...scheduled, '可能暂停订阅', '可能完成订阅'],
    ],
    [
      'non-zero thresholds',
      {
        movie_no_download_days: 1,
        tv_no_download_days: 2,
        no_download_actions: ['delete_tv', 'pause_movie', 'complete_tv'],
      },
      [...scheduled, '可能暂停订阅', '可能完成订阅', '可能删除订阅'],
    ],
    [
      'negative finite thresholds',
      {
        movie_no_download_days: -1,
        tv_no_download_days: -2,
        no_download_actions: ['delete_movie', 'pause_tv', 'complete_movie'],
      },
      [...scheduled, '可能暂停订阅', '可能完成订阅', '可能删除订阅'],
    ],
  ]

  it.each(thresholdCases)(
    '%s aligns action risks with enabled media thresholds',
    (_name, overrides, expected) => {
      expect(previewTitles({ enabled: true, ...overrides })).toEqual(expected)
    },
  )

  it('adds episode-wash to full-wash conversion risk', () => {
    expect(previewTitles({ enabled: true, best_version_episode_to_full: true })).toEqual([
      ...scheduled,
      '可能从分集洗版转为全集洗版',
    ])
  })

  it.each(['audit', ' Audit '])('%s distinguishes non-filtering audit mode', mode => {
    const audit = previewItems({ enabled: true, recognition_guard_mode: mode }).at(-1)

    expect(audit).toEqual({
      title: '识别增强可能记录候选风险',
      detail: '审计模式可能记录判定与通知，但不会过滤或移除候选。',
      tone: 'info',
    })
  })

  it.each(['loose', 'balanced', 'strict', ' STRICT '])(
    '%s warns about candidate filtering',
    mode => {
      const filtering = previewItems({ enabled: true, recognition_guard_mode: mode }).at(-1)

      expect(filtering).toEqual({
        title: '识别增强可能过滤候选',
        detail: '当前模式和生效的自定义策略覆盖可能过滤或移除候选。',
        tone: 'warning',
      })
    },
  )

  it('keeps all operational risks behind the plugin-enabled gate', () => {
    expect(
      previewTitles({
        no_download_actions: ['pause_movie', 'complete_tv', 'delete_movie'],
        best_version_episode_to_full: true,
        recognition_guard_mode: 'strict',
      }),
    ).toEqual(['插件未启用'])
  })
})

describe('backend-equivalent boolean parsing', () => {
  const trueValues: Array<[string, unknown]> = [
    ['boolean true', true],
    ['true', 'true'],
    ['on', 'on'],
    ['yes', 'yes'],
    ['one string', '1'],
    ['guard', 'guard'],
    ['positive number', 1],
    ['negative number', -1],
  ]
  const falseValues: Array<[string, unknown]> = [
    ['boolean false', false],
    ['false', 'false'],
    ['off', 'off'],
    ['no', 'no'],
    ['zero string', '0'],
    ['zero number', 0],
  ]

  it.each(trueValues)('%s enables scheduled previews', (_name, enabled) => {
    expect(previewTitles({ enabled })).toEqual(['通用巡检可能运行', '元数据检查可能运行'])
  })

  it.each(falseValues)('%s keeps scheduled previews disabled', (_name, enabled) => {
    expect(previewTitles({ enabled })).toEqual(['插件未启用'])
  })
})
