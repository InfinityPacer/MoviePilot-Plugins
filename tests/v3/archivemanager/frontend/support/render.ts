import 'vuetify/styles'

import { render } from '@testing-library/vue'
import { ref, type Component } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

type TestingLibraryRenderOptions = NonNullable<Parameters<typeof render>[1]>
type GlobalRenderOptions = NonNullable<TestingLibraryRenderOptions['global']>
type GlobalProperties = NonNullable<NonNullable<GlobalRenderOptions['config']>['globalProperties']>

export interface RenderWithHostOptions extends Omit<TestingLibraryRenderOptions, 'global'> {
  global?: TestingLibraryRenderOptions['global']
  locale?: string
}

export function renderWithHost(component: Component, options: RenderWithHostOptions = {}) {
  const { global: globalOptions, locale = 'zh-CN', ...renderOptions } = options
  const localeRef = ref(locale)
  const vuetify = createVuetify({ components, directives })
  const globalProperties = {
    ...globalOptions?.config?.globalProperties,
    $i18n: { locale: localeRef },
  } as GlobalProperties
  return {
    ...render(component, {
      ...renderOptions,
      global: {
        ...globalOptions,
        config: { ...globalOptions?.config, globalProperties },
        plugins: [vuetify, ...(globalOptions?.plugins ?? [])],
      },
    }),
    locale: localeRef,
  }
}
