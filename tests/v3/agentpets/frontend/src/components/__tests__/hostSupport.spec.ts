import { render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import Config from '@/components/Config.vue'
import Page from '@/components/Page.vue'
import { createMockHost } from '@/dev/mockHost'
import { AGENT_HOST_KEY, HOST_UNSUPPORTED_MESSAGE } from '@/host'

function mount(component: typeof Config | typeof Page, withHost: boolean) {
  const vuetify = createVuetify({ components, directives })
  return render(component, {
    props: { pluginId: 'AgentPets' },
    global: {
      plugins: [vuetify],
      provide: withHost ? { [AGENT_HOST_KEY]: createMockHost('AgentPets') } : {},
    },
  })
}

describe('host support notice', () => {
  it.each([
    ['Config', Config],
    ['Page', Page],
  ])('%s warns when the host has no agent capability', (_name, component) => {
    mount(component, false)
    expect(screen.getByText(HOST_UNSUPPORTED_MESSAGE)).toBeInTheDocument()
    expect(HOST_UNSUPPORTED_MESSAGE).toBe('当前主程序版本不支持助手形象，请升级到 v3.1.4 及以上')
  })

  it.each([
    ['Config', Config],
    ['Page', Page],
  ])('%s hides the notice when the host provides moviepilot:agent', (_name, component) => {
    mount(component, true)
    expect(screen.queryByText(HOST_UNSUPPORTED_MESSAGE)).toBeNull()
  })
})
