import 'vuetify/styles'

import { render } from '@testing-library/vue'
import { defineComponent, h, ref, type Component } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import type { SupportedLocale } from '@/config/i18n'

type TestingLibraryRenderOptions = NonNullable<Parameters<typeof render>[1]>
type GlobalRenderOptions = NonNullable<TestingLibraryRenderOptions['global']>
type GlobalProperties = NonNullable<NonNullable<GlobalRenderOptions['config']>['globalProperties']>

export interface RenderWithHostOptions extends Omit<TestingLibraryRenderOptions, 'global'> {
  global?: TestingLibraryRenderOptions['global']
  locale?: SupportedLocale
}

const CronFieldStub = defineComponent({
  name: 'VCronField',
  inheritAttrs: false,
  props: {
    modelValue: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  setup(props, { attrs, emit }) {
    return () =>
      h('input', {
        ...attrs,
        value: props.modelValue,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
      })
  },
})

const AceEditorStub = defineComponent({
  name: 'VAceEditor',
  inheritAttrs: false,
  props: {
    value: { type: String, default: '' },
  },
  emits: ['update:value'],
  setup(props, { attrs, emit }) {
    return () =>
      h('textarea', {
        ...attrs,
        'aria-label': 'YAML',
        value: props.value,
        onInput: (event: Event) => emit('update:value', (event.target as HTMLTextAreaElement).value),
      })
  },
})

/** 使用真实 Vuetify 与最小 Host 契约渲染联邦配置组件。 */
export function renderWithHost(component: Component, options: RenderWithHostOptions = {}) {
  const { global: globalOptions, locale = 'zh-CN', ...renderOptions } = options
  const localeRef = ref(locale)
  const vuetify = createVuetify({ components, directives })
  // Vuetify 在插件安装阶段注入自身全局属性，挂载配置只需补充 Host 语言契约。
  const globalProperties = {
    ...globalOptions?.config?.globalProperties,
    $i18n: { locale: localeRef },
  } as GlobalProperties

  const result = render(component, {
    ...renderOptions,
    global: {
      ...globalOptions,
      components: {
        VAceEditor: AceEditorStub,
        VCronField: CronFieldStub,
        ...globalOptions?.components,
      },
      config: {
        ...globalOptions?.config,
        globalProperties,
      },
      plugins: [vuetify, ...(globalOptions?.plugins ?? [])],
    },
  })

  return { ...result, locale: localeRef }
}
