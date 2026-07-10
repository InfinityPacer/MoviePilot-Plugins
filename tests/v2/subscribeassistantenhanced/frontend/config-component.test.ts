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
}

interface CompilerSfcModule {
  parse: (
    source: string,
    options: { filename: string },
  ) => {
    descriptor: { template?: { ast?: TemplateNode } }
    errors: unknown[]
  }
}

const pluginPackageUrl = new URL(
  '../../../../plugins.v2/subscribeassistantenhanced/package.json',
  import.meta.url,
)
const requireFromPlugin = createRequire(pluginPackageUrl)
const { parse } = requireFromPlugin('@vue/compiler-sfc') as CompilerSfcModule
const configUrl = new URL('src/components/Config.vue', pluginPackageUrl)
const source = readFileSync(configUrl, 'utf8')
const { descriptor, errors } = parse(source, { filename: 'Config.vue' })

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
    ['保存更改', 'mdi-content-save'],
    ['关闭配置', 'mdi-close'],
  ] as const)('%s renders an explicit %s icon', (ariaLabel, expectedIcon) => {
    const template = descriptor.template?.ast
    expect(template).toBeDefined()

    const button = findElements(template!, 'VBtn').find(
      node => staticAttribute(node, 'aria-label') === ariaLabel,
    )
    expect(button, `未找到 aria-label="${ariaLabel}" 的 VBtn`).toBeDefined()

    const icon = button?.children?.find(child => child.tag === 'VIcon')
    expect(icon, `${ariaLabel} 缺少显式 VIcon 子节点`).toBeDefined()
    expect(staticAttribute(icon, 'icon')).toBe(expectedIcon)
  })

  it('uses the approved sticky command-bar hierarchy', () => {
    expect(source).toMatch(/\.sae-config-header\s*{[\s\S]*?position:\s*sticky/)
    expect(source).toMatch(/\.sae-config-header\s*{[\s\S]*?background:\s*var\(--app-grouped-list-background\)/)
    expect(source).toMatch(/\.sae-config-header\s*{[\s\S]*?backdrop-filter:\s*var\(--app-grouped-list-backdrop-filter\)/)
    expect(source).toMatch(/\.sae-config-header\s*{[\s\S]*?box-shadow:\s*var\(--app-surface-shadow\)/)
    expect(source).toContain('class="sae-config-header__change-state"')
    expect(source).toContain('aria-label="保存更改"')
    expect(source).toContain('aria-label="关闭配置"')
  })

  it('keeps the close icon visible when only its mobile label is hidden', () => {
    expect(source).toContain('class="sae-config-header__close-label"')
    expect(source).toMatch(/\.sae-config-header__close-label\s*{[\s\S]*?display:\s*none/)
    expect(source).not.toContain('.sae-config-header__close :deep(.v-btn__content)')
  })
})

describe('configuration navigation', () => {
  it('keeps README help at the bottom of the navigation rail', () => {
    const headerSource = source.slice(
      source.indexOf('<header class="sae-config-header">'),
      source.indexOf('</header>') + '</header>'.length,
    )

    expect(source).toContain('class="sae-group-nav__help"')
    expect(headerSource).not.toContain(':href="README_URL"')
  })

  it('does not render visible high-risk taxonomy', () => {
    expect(source).not.toContain('高风险')
    expect(source).not.toContain('fieldColor(')
  })

  it('keeps the desktop help rail within short viewports', () => {
    expect(source).toMatch(/\.sae-group-nav\s*{[\s\S]*?block-size:\s*clamp\(/)
  })
})

describe('configuration controls', () => {
  it('renders direct segmented choices instead of field dropdowns', () => {
    expect(source).toContain('class="sae-choice-group"')
    expect(source).toContain('class="sae-choice-group sae-choice-group--multiple"')
    expect(source).not.toContain('<VSelect')
  })

  it('renders explicit decrement and increment actions for numeric settings', () => {
    expect(source).toContain(':aria-label="`减小${field.label}`"')
    expect(source).toContain(':aria-label="`增大${field.label}`"')
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
