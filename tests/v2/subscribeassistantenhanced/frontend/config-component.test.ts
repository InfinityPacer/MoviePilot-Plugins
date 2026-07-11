import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'

import { describe, expect, it } from 'vitest'

import { fields } from '../../../../plugins.v2/subscribeassistantenhanced/frontend/src/config/fields'

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
  '../../../../plugins.v2/subscribeassistantenhanced/frontend/package.json',
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

  it.each(['sae-config-header__save', 'sae-mobile-save-dock__save'])(
    'renders an explicit save icon in %s',
    className => {
    const template = descriptor.template?.ast
    expect(template).toBeDefined()

    const button = findElements(template!, 'VBtn').find(
      node => staticAttribute(node, 'class') === className,
    )
    expect(button, `未找到 class="${className}" 的保存 VBtn`).toBeDefined()

    const icon = button?.children?.find(child => child.tag === 'VIcon')
    expect(icon, `${className} 缺少显式 VIcon 子节点`).toBeDefined()
    expect(staticAttribute(icon, 'icon')).toBe('mdi-content-save')
    },
  )

  it('uses the approved sticky command-bar hierarchy', () => {
    expect(compiledStyle.code).toMatch(/\.sae-config-header\[data-v-sae-config-test\]\s*\{[^}]*position:\s*sticky;/)
    expect(compiledStyle.code).toMatch(/\.sae-config-header\[data-v-sae-config-test\]\s*\{[^}]*background:\s*transparent;/)
    expect(compiledStyle.code).toMatch(/\.sae-config-header--scrolled\[data-v-sae-config-test\]\s*\{[^}]*background:\s*var\(--sae-header-background\);/)
    expect(compiledStyle.code).toMatch(/\.sae-config-header--scrolled\[data-v-sae-config-test\]\s*\{[^}]*backdrop-filter:\s*var\(--sae-header-backdrop-filter\);/)
    expect(source).not.toContain('<VDialogCloseBtn')
    expect(source).toContain('class="sae-config-header__close"')
    expect(source).toContain(":aria-label=\"t(locale, 'config.close')\"")
    expect(source).toMatch(/class="sae-config-header__actions"[\s\S]*?class="sae-config-header__close"/)
    expect(source).toContain('class="sae-config-header__change-state"')
    expect(source).toContain('class="sae-config-header__save"')
    expect(source).toContain('class="sae-mobile-save-dock"')
  })

  it('uses warning semantics for pending unsaved changes', () => {
    expect(source).toContain('<VIcon color="warning" icon="mdi-circle" size="8" />')
    expect(source).not.toContain('<VIcon color="success" icon="mdi-check-circle" size="16" />')
    expect(source).not.toContain('<VIcon color="warning" icon="mdi-pencil-outline" size="16" />')
    expect(source).toContain("t(locale, 'config.changedCount', { count: changedCount })")
  })

  it('keeps the scrolled header legible across transparent-theme blur modes', () => {
    expect(compiledStyle.errors).toEqual([])
    expect(compiledStyle.code).toMatch(
      /\.sae-config-header--scrolled\[data-v-sae-config-test\]\s*\{/,
    )
    expect(compiledStyle.code).toMatch(
      /html\[data-theme='transparent'\] \.sae-config-header--scrolled\s*\{[\s\S]*?--sae-header-background:\s*rgba\(var\(--v-theme-surface\), 0\.72\);[\s\S]*?--sae-header-backdrop-filter:\s*blur\(24px\);/,
    )
    expect(compiledStyle.code).toMatch(
      /html\[data-theme='transparent'\]\.transparent-blur-disabled \.sae-config-header--scrolled\s*\{[\s\S]*?--sae-header-background:\s*rgba\(var\(--v-theme-surface\), 0\.92\);[\s\S]*?--sae-header-backdrop-filter:\s*none;/,
    )
    expect(compiledStyle.code).not.toContain(
      "html[data-theme='transparent'] .sae-config-header--scrolled[data-v-sae-config-test]",
    )
  })

  it('only reveals the dialog scrollbar while the user is scrolling', () => {
    expect(source).toContain("scrollRoot?.classList.add('sae-config-scroll-root')")
    expect(source).toContain("fieldScrollRoot?.classList.add('sae-config-scroll-root')")
    expect(source).toContain("scrollRoot.classList.add('sae-config-scroll-root--active')")
    expect(source).toContain("scrollRoot.classList.remove('sae-config-scroll-root--active')")
    expect(source).toContain("scrollRoot?.addEventListener('scroll', handleConfigScroll, { passive: true })")
    expect(source).toContain("fieldScrollRoot?.addEventListener('scroll', handleConfigScroll, { passive: true })")
    expect(source).toContain("fieldScrollRoot?.removeEventListener('scroll', handleConfigScroll)")
    expect(source).toContain('window.setTimeout(() =>')
    expect(compiledStyle.code).toMatch(
      /\.sae-config-scroll-root::-webkit-scrollbar-thumb\s*\{[\s\S]*?background:\s*transparent;/,
    )
    expect(compiledStyle.code).toMatch(
      /\.sae-config-scroll-root\.sae-config-scroll-root--active::-webkit-scrollbar-thumb\s*\{[\s\S]*?background:\s*rgb\(var\(--v-theme-perfect-scrollbar-thumb\)\);/,
    )
  })
})

describe('global section order', () => {
  it('shows schedules before one-time actions', () => {
    const globalSections = source.match(/global:\s*\[([\s\S]*?)\],\s*cleanup:/)?.[1] ?? ''

    expect(globalSections.indexOf("titleKey: 'section.running'")).toBeLessThan(
      globalSections.indexOf("titleKey: 'section.schedule'"),
    )
    expect(globalSections.indexOf("titleKey: 'section.schedule'")).toBeLessThan(
      globalSections.indexOf("titleKey: 'section.oneTime'"),
    )
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
    expect(source).not.toContain('scrollIntoView')
    expect(source).toContain('class="sae-mobile-group-action"')
    expect(source).not.toContain('<VTabs')
    expect(source).toContain('class="sae-field-surface__mobile-actions"')
    expect(source).toContain('class="sae-mobile-help"')
    expect(source).toContain('<VIcon icon="mdi-help-circle-outline" size="18" />')
    expect(source).not.toContain('class="sae-mobile-group-selector"')
  })
})

describe('configuration controls', () => {
  it('uses dropdowns for all single-select and multi-select fields', () => {
    expect(source).toContain('<VSelect')
    expect(source).toContain(':multiple="field.kind === \'multi-select\'"')
    expect(source).not.toContain('<VBtnToggle')
    expect(source).not.toContain('useSegmentedControl(field)')
  })

  it('reserves more desktop width for field guidance than option controls', () => {
    expect(compiledStyle.code).toContain(
      'grid-template-columns: minmax(200px, 1.45fr) minmax(180px, 0.75fr);',
    )
  })

  it('uses aligned text summaries without removable chips for select controls', () => {
    expect(source).not.toContain('closable-chips')
    expect(source).not.toContain(':chips=')
    expect(source).toContain('<template v-if="field.kind === \'multi-select\'" #selection="{ item, index }">')
    expect(source).toContain('selectionOverflowCount(field.key)')
    expect(compiledStyle.code).toMatch(
      /\.sae-field-control\[data-v-sae-config-test\] \.v-select__selection\s*\{[\s\S]*?justify-content:\s*flex-end;[\s\S]*?text-align:\s*end;/,
    )
  })

  it('right-aligns text and CRON values with the other field controls', () => {
    expect(source).toContain('class="sae-text-control"')
    expect(compiledStyle.code).toMatch(
      /\.sae-text-control\[data-v-sae-config-test\] input\s*\{[\s\S]*?text-align:\s*end;/,
    )
  })

  it('reuses Host-native cron and YAML editors', () => {
    expect(source).toContain('<VCronField')
    expect(source).toContain(':clearable="false"')
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

  it('inherits the Host control radius for remaining custom controls', () => {
    const radiusUses = source.match(/border-radius:\s*var\(--app-control-radius\)/g) ?? []

    expect(radiusUses).toHaveLength(2)
  })

  it('does not bind visual field headings to composite controls as labels', () => {
    expect(source).toContain('class="sae-field-row__label"')
    expect(source).not.toContain('<label :for=')
  })

  it('wires Tracker editing and save submission through the draft contract', () => {
    expect(source).toContain('v-model="draft.default_tracker_response"')
    expect(source).toContain("emit('save', buildSavePayload())")
  })

  it('renders custom recognition rules as a dedicated edit entry', () => {
    expect(source).toContain("activeGroup === 'recognition'")
    expect(source).toContain('class="sae-field-section sae-tracker-entry"')
    expect(source).toContain('yamlField.label')
    expect(source).toContain('yamlField.hint')
    expect(source).not.toContain("v-else-if=\"field.kind === 'textarea'\"")
  })

  it('assigns every directly rendered field to exactly one visual section', () => {
    const sectionSource = source.slice(
      source.indexOf('const sectionDefinitions'),
      source.indexOf('const activeGroupMeta'),
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

describe('configuration summary', () => {
  it('shows factual schedule values instead of speculative impact copy', () => {
    expect(source).toContain("<h2>{{ t(locale, 'config.cadence') }}</h2>")
    expect(source).toContain('v-for="item in cadenceSummary"')
    expect(source).not.toContain('impactItems')
    expect(source).not.toContain('impactToneIcons')
    expect(source).not.toContain('可能运行')
  })

  it('keeps the schedule summary draft-aware', () => {
    expect(source).not.toContain('sae-impact-preview__draft-state')
    expect(source).toContain('v-if="changedItems.length" class="sae-change-summary"')
    expect(source).toContain('v-for="item in changedItems"')
    expect(source).toContain("t(locale, 'config.moreChanges', { count: hiddenChangedCount })")
  })

  it('uses one compact typography scale across the summary rail', () => {
    expect(compiledStyle.code).toMatch(/\.sae-impact-preview__item\[data-v-sae-config-test\]\s*\{[^}]*font-size:\s*0\.875rem;/)
    expect(compiledStyle.code).toMatch(/\.sae-runtime-summary__row\[data-v-sae-config-test\]\s*\{[^}]*font-size:\s*0\.875rem;/)
    expect(compiledStyle.code).toMatch(/\.sae-impact-preview strong\[data-v-sae-config-test\]\s*\{[^}]*font-size:\s*0\.875rem;/)
    expect(compiledStyle.code).toMatch(/\.sae-summary-section__title h3\[data-v-sae-config-test\]\s*\{[^}]*font-size:\s*1rem;/)
    expect(compiledStyle.code).toMatch(/\.sae-impact-preview__item\[data-v-sae-config-test\]\s*\{[^}]*grid-template-columns:\s*28px minmax\(0, 1fr\) minmax\(0, auto\);/)
    expect(compiledStyle.code).not.toMatch(/\.sae-impact-preview__item \+ \.sae-impact-preview__item/)
  })

  it('condenses runtime status instead of listing every domain', () => {
    expect(source).toContain('activeDomainCount')
    expect(source).toContain("t(locale, 'config.activeDomains')")
    expect(source).not.toContain('v-for="[name, status] in summaryDomains"')
  })

  it('localizes fields, groups, sections, cadence, and runtime copy from the Host locale', () => {
    expect(source).toContain('normalizeLocale(instance?.appContext.config.globalProperties.$i18n?.locale)')
    expect(source).toContain('localizeGroups(locale.value, groups)')
    expect(source).toContain('localizeFields(locale.value, fields)')
    expect(source).toContain('cadenceSummary')
  })
})

describe('responsive command bar', () => {
  it('uses desktop header actions and a mobile-only save dock', () => {
    expect(source).toContain(':disabled="changedCount === 0"')
    expect(source).toContain('v-if="changedCount > 0" class="sae-mobile-save-dock"')
    expect(source).toMatch(/@container \(width < 720px\)\s*\{[\s\S]*?\.sae-config-header__change-state,[\s\S]*?\.sae-config-header__save\s*\{[^}]*display:\s*none;/)
    expect(source).toMatch(/@container \(width >= 720px\)\s*\{[\s\S]*?\.sae-mobile-save-dock\s*\{[^}]*display:\s*none;/)
    expect(source).not.toContain("'暂无修改'")
  })

  it('keeps the mobile header sticky while using the compact save dock', () => {
    expect(compiledStyle.code).toMatch(/\.sae-config-header\[data-v-sae-config-test\]\s*\{[^}]*position:\s*sticky;/)
    expect(source).not.toMatch(/@container \(width < 720px\)\s*\{[\s\S]*?\.sae-config-header\s*\{[^}]*position:\s*relative;/)
  })

  it('keeps only the desktop center pane scrollable at wide widths', () => {
    expect(source).toMatch(/@container \(width >= 880px\)\s*\{[\s\S]*?\.sae-field-surface\s*\{[^}]*overflow-y:\s*auto;/)
    expect(source).toMatch(/@container \(width >= 880px\)\s*\{[\s\S]*?\.sae-group-nav\s*\{[^}]*overflow:\s*hidden;/)
    expect(source).toMatch(/@container \(width >= 880px\)\s*\{[\s\S]*?\.sae-impact-preview\s*\{[^}]*overflow:\s*hidden;/)
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
