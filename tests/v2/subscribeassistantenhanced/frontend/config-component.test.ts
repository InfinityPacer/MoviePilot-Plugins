import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'

import { describe, expect, it } from 'vitest'

import { fields } from '../../../../plugins.v2/subscribeassistantenhanced/src/config/fields'

interface TemplateProp {
  name?: string
  value?: { content?: string } | null
}

interface TemplateNode {
  tag?: string
  props?: TemplateProp[]
  children?: TemplateNode[]
  loc?: { source?: string }
}

interface CompilerSfcModule {
  compileStyle: (options: {
    filename: string
    id: string
    scoped: boolean
    source: string
  }) => { code: string; errors: unknown[] }
  parse: (
    source: string,
    options: { filename: string },
  ) => {
    descriptor: {
      styles: Array<{ content: string; scoped?: boolean }>
      template?: { ast?: TemplateNode }
    }
    errors: unknown[]
  }
}

const pluginPackageUrl = new URL(
  '../../../../plugins.v2/subscribeassistantenhanced/package.json',
  import.meta.url,
)
const requireFromPlugin = createRequire(pluginPackageUrl)
const { compileStyle, parse } = requireFromPlugin('@vue/compiler-sfc') as CompilerSfcModule
const configUrl = new URL('src/components/Config.vue', pluginPackageUrl)
const source = readFileSync(configUrl, 'utf8')
const { descriptor, errors } = parse(source, { filename: 'Config.vue' })
const componentStyle = descriptor.styles.find(style => style.scoped)
const compiledStyle = compileStyle({
  filename: 'Config.vue',
  id: 'data-v-sae-config-test',
  scoped: true,
  source: componentStyle?.content ?? '',
})

function staticAttribute(node: TemplateNode | undefined, name: string): string | undefined {
  return node?.props?.find(prop => prop.name === name)?.value?.content
}

function findElements(node: TemplateNode, tag: string): TemplateNode[] {
  const matches = node.tag === tag ? [node] : []
  return [...matches, ...(node.children?.flatMap(child => findElements(child, tag)) ?? [])]
}

describe('config header actions', () => {
  it('parses the real component template', () => {
    expect(errors).toEqual([])
    expect(descriptor.template?.ast).toBeDefined()
  })

  it.each([
    ['sae-config-header__save', 'mdi-content-save'],
    ['sae-config-header__close', 'mdi-close'],
  ] as const)('%s renders an explicit %s icon', (className, expectedIcon) => {
    const template = descriptor.template?.ast
    expect(template).toBeDefined()

    const button = findElements(template!, 'VBtn').find(
      node => staticAttribute(node, 'class') === className,
    )
    expect(button, `未找到 class="${className}" 的 VBtn`).toBeDefined()

    const icon = button?.children?.find(child => child.tag === 'VIcon')
    expect(icon, `${className} 缺少显式 VIcon 子节点`).toBeDefined()
    expect(staticAttribute(icon, 'icon')).toBe(expectedIcon)
  })

  it('uses the approved sticky command-bar hierarchy', () => {
    expect(source).toMatch(/\.sae-config-header\s*{[\s\S]*?position:\s*sticky/)
    expect(source).toMatch(/\.sae-config-header\s*{[\s\S]*?background:\s*transparent/)
    expect(source).toMatch(/\.sae-config-header--scrolled\s*{[\s\S]*?background:\s*var\(--sae-header-background\)/)
    expect(source).toMatch(/\.sae-config-header--scrolled\s*{[\s\S]*?backdrop-filter:\s*var\(--sae-header-backdrop-filter\)/)
    expect(source).toContain('v-if="changedCount > 0"')
    expect(source).toContain('class="sae-config-header__change-state"')
    expect(source).toContain(":aria-label=\"t(locale, 'config.save')\"")
    expect(source).toContain(":aria-label=\"t(locale, 'config.close')\"")
  })

  it('keeps the scrolled header legible across transparent-theme blur modes', () => {
    expect(compiledStyle.errors).toEqual([])
    expect(compiledStyle.code).toMatch(
      /\.sae-config-header--scrolled\[data-v-sae-config-test\]\s*\{/,
    )
    expect(compiledStyle.code).toMatch(
      /html\[data-theme='transparent'\] \.sae-config-header--scrolled\s*\{[\s\S]*?--sae-header-background:\s*rgba\(var\(--v-theme-surface\), var\(--transparent-opacity-heavy, 0\.5\)\);[\s\S]*?--sae-header-backdrop-filter:\s*blur\(var\(--transparent-blur-heavy, 16px\)\);/,
    )
    expect(compiledStyle.code).toMatch(
      /html\[data-theme='transparent'\]\.transparent-blur-disabled \.sae-config-header--scrolled\s*\{[\s\S]*?--sae-header-background:\s*rgba\(var\(--v-theme-surface\), 0\.92\);[\s\S]*?--sae-header-backdrop-filter:\s*none;/,
    )
    expect(compiledStyle.code).not.toContain(
      "html[data-theme='transparent'] .sae-config-header--scrolled[data-v-sae-config-test]",
    )
  })

  it('keeps the close icon visible when only its mobile label is hidden', () => {
    expect(source).toContain('class="sae-config-header__close-label"')
    expect(source).toMatch(/\.sae-config-header__close-label\s*{[\s\S]*?display:\s*none/)
    expect(source).not.toContain('.sae-config-header__close :deep(.v-btn__content)')
  })
})

describe('configuration navigation', () => {
  it('keeps README help at the bottom of the navigation rail', () => {
    const template = descriptor.template?.ast
    expect(template).toBeDefined()
    const header = findElements(template!, 'header')[0]
    expect(header, '未找到配置页 Header').toBeDefined()
    const headerSource = header?.loc?.source ?? ''

    expect(source).toContain('class="sae-group-nav__help"')
    expect(source).toContain('append-icon="mdi-open-in-new"')
    expect(headerSource).not.toBe('')
    expect(headerSource).not.toContain(':href="README_URL"')
  })

  it('removes the generic advanced-feature warning', () => {
    expect(source).not.toContain('高级功能：部分操作会影响订阅状态、下载任务和媒体文件')
  })

  it('does not render visible high-risk taxonomy', () => {
    expect(source).not.toContain('高风险')
    expect(source).not.toContain('fieldColor(')
  })

  it('keeps the desktop help rail within short viewports', () => {
    expect(source).toMatch(/\.sae-group-nav\s*{[\s\S]*?block-size:\s*clamp\(/)
  })

  it('uses a bottom sheet instead of horizontally scrolling mobile tabs', () => {
    expect(source).toContain('<VBottomSheet v-model="mobileGroupSheet"')
    expect(source).toContain('selectMobileGroup(group.key)')
    expect(source).toContain('class="sae-mobile-group-trigger"')
    expect(source).not.toContain('<VTabs')
    expect(source).toContain('class="sae-mobile-help"')
    expect(source).toContain('<VIcon icon="mdi-help-circle-outline" size="18" />')
  })
})

describe('configuration controls', () => {
  it('uses segmented choices only for compact option sets', () => {
    expect(source).toContain('class="sae-choice-group"')
    expect(source).toContain('useSegmentedControl(field)')
    expect(source).toContain('<VSelect')
    expect(source).toContain(':multiple="field.kind === \'multi-select\'"')
  })

  it('reuses Host-native cron and YAML editors', () => {
    expect(source).toContain('<VCronField')
    expect(source).toContain('<VAceEditor')
    expect(source).toContain('lang="yaml"')
    expect(source).not.toContain('mode="yaml"')
    expect(source).toContain('yamlDialogOpen')
  })

  it('renders explicit decrement and increment actions for numeric settings', () => {
    expect(source).toContain("t(locale, 'config.decrease', { label: field.label })")
    expect(source).toContain("t(locale, 'config.increase', { label: field.label })")
    expect(source).toContain('class="sae-number-stepper"')
  })

  it('inherits the Host control radius for custom selection controls', () => {
    const radiusUses = source.match(/border-radius:\s*var\(--app-control-radius\)/g) ?? []

    expect(radiusUses).toHaveLength(3)
  })

  it('does not bind visual field headings to composite controls as labels', () => {
    expect(source).toContain('class="sae-field-row__label"')
    expect(source).not.toContain('<label :for=')
  })

  it('wires Tracker editing and save submission through the draft contract', () => {
    expect(source).toContain('v-model="draft.default_tracker_response"')
    expect(source).toContain("emit('save', buildSavePayload())")
  })

  it('assigns every directly rendered field to exactly one visual section', () => {
    const sectionSource = source.slice(
      source.indexOf('const sectionDefinitions'),
      source.indexOf('const impactToneIcons'),
    )
    const sectionKeys = [...sectionSource.matchAll(/'([a-z][a-z0-9_]*)'/g)].map(match => match[1])
    const expectedKeys = fields
      .filter(field => !field.legacyUiKey && !field.dialogOnly)
      .map(field => field.key)

    expect(new Set(sectionKeys).size).toBe(sectionKeys.length)
    expect(sectionKeys.toSorted()).toEqual(expectedKeys.toSorted())
    expect(source).toContain("field.key === 'default_tracker_response' && field.dialogOnly")
  })
})

describe('configuration preview', () => {
  it('labels the panel as a draft-aware configuration preview', () => {
    expect(source).toContain("<h2>{{ t(locale, 'config.preview') }}</h2>")
    expect(source).toContain('v-if="changedCount > 0" class="sae-impact-preview__draft-state"')
    expect(source).toContain('mdi-pencil-outline')
    expect(source).toContain("t(locale, 'config.unsaved')")
  })

  it('localizes fields, groups, sections, preview, and runtime copy from the Host locale', () => {
    expect(source).toContain('normalizeLocale(instance?.appContext.config.globalProperties.$i18n?.locale)')
    expect(source).toContain('localizeGroups(locale.value, groups)')
    expect(source).toContain('localizeFields(locale.value, fields)')
    expect(source).toContain('buildImpactPreview(draft, locale.value)')
  })
})

describe('mobile command bar', () => {
  it('keeps save as a single mobile-only bottom action', () => {
    expect(source).toContain(':disabled="changedCount === 0"')
    expect(source).toMatch(/@container \(width < 720px\)[\s\S]*?\.sae-config-header__save\s*{[\s\S]*?display:\s*none/)
    expect(source).toContain('v-if="changedCount > 0" class="sae-mobile-savebar__state"')
    expect(source).not.toContain("'暂无修改'")
  })
})

describe('tracker dialog title', () => {
  it('renders an explicit close icon', () => {
    const template = descriptor.template?.ast
    expect(template).toBeDefined()

    const title = findElements(template!, 'VCardTitle').find(
      node => staticAttribute(node, 'class') === 'sae-tracker-dialog__title',
    )
    expect(title, '未找到 Tracker 弹窗标题').toBeDefined()

    const closeButton = title?.children?.find(child => child.tag === 'VBtn')
    expect(closeButton, 'Tracker 弹窗标题缺少关闭 VBtn').toBeDefined()

    const icon = closeButton?.children?.find(child => child.tag === 'VIcon')
    expect(icon, 'Tracker 弹窗标题关闭按钮缺少显式 VIcon 子节点').toBeDefined()
    expect(staticAttribute(icon, 'icon')).toBe('mdi-close')
  })
})
