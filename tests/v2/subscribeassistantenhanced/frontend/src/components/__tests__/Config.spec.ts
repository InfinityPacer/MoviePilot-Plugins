import Config from '@/components/Config.vue'
import { fields, groups } from '@/config/fields'
import { localizeFields, localizeGroups, type SupportedLocale } from '@/config/i18n'
import { fireEvent, screen, waitFor, within } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { createConfig } from '@tests/support/factories/config'
import { createHostApi, createSummary } from '@tests/support/host'
import { renderWithHost } from '@tests/support/render'

interface RenderConfigOptions {
  initialConfig?: ReturnType<typeof createConfig>
  locale?: SupportedLocale
  summary?: ReturnType<typeof createSummary>
}

async function renderConfig(options: RenderConfigOptions = {}) {
  const events = {
    close: vi.fn(),
    layout: vi.fn(),
    save: vi.fn(),
  }
  const { api, get } = createHostApi(options.summary)
  const result = renderWithHost(Config, {
    locale: options.locale,
    props: {
      api,
      initialConfig: options.initialConfig ?? createConfig(),
      onClose: events.close,
      onLayout: events.layout,
      onSave: events.save,
    },
  })

  await waitFor(() => {
    expect(get).toHaveBeenCalledWith('plugin/SubscribeAssistantEnhanced/summary')
  })

  return { ...result, events, get, user: userEvent.setup() }
}

function headerButton(className: string): HTMLButtonElement {
  const button = document.querySelector<HTMLButtonElement>(`.${className}`)
  expect(button).not.toBeNull()
  return button as HTMLButtonElement
}

describe('SubscribeAssistantEnhanced config', () => {
  it('renders with the Host contract and exposes the requested layout', async () => {
    const summary = createSummary({ pending_count: 4, monitored_torrents: 6 })
    const { events } = await renderConfig({ summary })

    expect(events.layout).toHaveBeenCalledWith({ maxWidth: '68rem' })
    expect(screen.getByRole('heading', { name: '订阅助手（增强版）' })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('待定订阅').parentElement).toHaveTextContent('4')
      expect(screen.getByText('下载任务').parentElement).toHaveTextContent('6')
      expect(screen.getByText('已启用能力').parentElement).toHaveTextContent('3 / 3')
    })
  })

  it('enables save after editing and emits a complete normalized payload', async () => {
    const { events, user } = await renderConfig()
    const saveButton = headerButton('sae-config-header__save')
    const notify = screen.getByRole('checkbox', { name: '发送通知' })

    expect(saveButton).toBeDisabled()
    await user.click(notify)
    expect(saveButton).toBeEnabled()
    expect(screen.getByText('本次修改')).toBeInTheDocument()
    expect(screen.queryByText(/项待保存/)).not.toBeInTheDocument()

    await user.click(saveButton)

    expect(events.save).toHaveBeenCalledOnce()
    const payload = events.save.mock.calls[0][0]
    expect(payload.notify).toBe(!createConfig().notify)
    expect(Object.keys(payload)).toEqual(Object.keys(createConfig()))
  })

  it('runs once through save without emitting close and clears reset data', async () => {
    const { events, user } = await renderConfig()

    await user.click(screen.getByRole('checkbox', { name: '重置数据' }))
    await user.click(headerButton('sae-config-header__run'))

    expect(events.save).toHaveBeenCalledOnce()
    expect(events.save).toHaveBeenCalledWith(
      expect.objectContaining({
        onlyonce: true,
        reset_task: false,
      }),
    )
    expect(events.close).not.toHaveBeenCalled()
  })

  it('closes directly from desktop and mobile controls even when the draft is dirty', async () => {
    const { events, user } = await renderConfig()

    await user.click(screen.getByRole('checkbox', { name: '发送通知' }))
    await user.click(headerButton('sae-config-header__close-action'))
    await user.click(headerButton('sae-config-header__close-icon'))

    expect(events.close).toHaveBeenCalledTimes(2)
  })

  it('keeps every editable field reachable through its business group', async () => {
    const { user } = await renderConfig()
    const navigation = document.querySelector<HTMLElement>('.sae-group-nav__list')
    expect(navigation).not.toBeNull()
    const localizedGroups = localizeGroups('zh-CN', groups)
    const localizedFields = localizeFields('zh-CN', fields)

    for (const group of localizedGroups) {
      await user.click(within(navigation as HTMLElement).getByText(group.title))
      await waitFor(() => {
        expect(screen.getByRole('heading', { name: group.title })).toBeInTheDocument()
      })
      for (const field of localizedFields.filter(
        item => item.group === group.key && !item.legacyUiKey && !item.dialogOnly && item.kind !== 'textarea',
      )) {
        expect(
          screen.queryAllByLabelText(field.label, { exact: true }).length,
          `${group.key}/${field.key}`,
        ).toBeGreaterThan(0)
      }
    }
  })

  it('edits Tracker and YAML values through their dedicated dialogs', async () => {
    const { events, user } = await renderConfig()
    const navigation = document.querySelector<HTMLElement>('.sae-group-nav__list') as HTMLElement

    await user.click(within(navigation).getByText('订阅清理'))
    await user.click(screen.getByRole('button', { name: '编辑Tracker响应关键字' }))
    const tracker = await screen.findByRole('textbox', {
      name: 'Tracker响应关键字',
    })
    const trackerDialog = tracker.closest<HTMLElement>('[role="dialog"]') as HTMLElement
    await user.clear(tracker)
    await user.type(tracker, 'tracker failure')
    await user.click(
      within(trackerDialog).getByRole('button', {
        name: '关闭 Tracker响应关键字',
      }),
    )

    await user.click(within(navigation).getByText('识别增强'))
    await user.click(screen.getByRole('button', { name: '编辑自定义识别规则' }))
    const yaml = await screen.findByRole('textbox', { name: 'YAML' })
    const yamlDialog = yaml.closest<HTMLElement>('[role="dialog"]') as HTMLElement
    await user.clear(yaml)
    await user.type(yaml, 'rules: enabled')
    await user.click(within(yamlDialog).getByRole('button', { name: '关闭' }))
    await user.click(headerButton('sae-config-header__save'))

    expect(events.save).toHaveBeenCalledWith(
      expect.objectContaining({
        default_tracker_response: 'tracker failure',
        recognition_guard_custom_config: 'rules: enabled',
      }),
    )
  })

  it('updates number and text controls while keeping multi-select summaries compact', async () => {
    const { user } = await renderConfig({
      initialConfig: createConfig({
        no_download_actions: ['pause_movie', 'pause_tv'],
      }),
    })
    const navigation = document.querySelector<HTMLElement>('.sae-group-nav__list') as HTMLElement

    await user.click(within(navigation).getByText('订阅清理'))
    const timeout = screen.getByRole('spinbutton', {
      name: '下载超时时间（分钟）',
    })
    await user.click(screen.getByRole('button', { name: '减小下载超时时间（分钟）' }))
    expect(timeout).toHaveValue(119)
    await user.click(screen.getByRole('button', { name: '增大下载超时时间（分钟）' }))
    expect(timeout).toHaveValue(120)
    await fireEvent.update(timeout, '90')
    expect(timeout).toHaveValue(90)

    const tags = screen.getByRole('textbox', { name: '排除标签' })
    await user.clear(tags)
    await user.type(tags, 'free')
    expect(tags).toHaveValue('free')

    await user.click(within(navigation).getByText('订阅暂停'))
    expect(screen.getByText('暂停电影订阅')).toBeInTheDocument()
    expect(screen.getByText('+1')).toBeInTheDocument()
  })

  it('switches business groups through the mobile group sheet', async () => {
    const { user } = await renderConfig()

    await user.click(headerButton('sae-mobile-group-action'))
    const groupSheet = await screen.findByRole('dialog')
    await user.click(within(groupSheet).getByText('订阅暂停'))

    expect(screen.getByRole('heading', { name: '订阅暂停' })).toBeInTheDocument()
    await waitFor(() => expect(groupSheet).not.toHaveClass('v-overlay--active'))
  })

  it('uses the Host locale for visible commands', async () => {
    await renderConfig({ locale: 'en-US' })

    const header = document.querySelector<HTMLElement>('.sae-config-header')
    expect(header).not.toBeNull()
    expect(within(header as HTMLElement).getByRole('button', { name: 'Run once' })).toBeInTheDocument()
    expect(
      within(header as HTMLElement).getByRole('button', {
        name: 'Save changes',
      }),
    ).toBeInTheDocument()
    expect(within(header as HTMLElement).getAllByRole('button', { name: 'Close' })).toHaveLength(2)
  })

  it('shows a fixed unavailable state without exposing Host request details', async () => {
    const get = vi.fn().mockRejectedValue(new Error('private request details'))
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)

    renderWithHost(Config, {
      props: {
        api: { get },
        initialConfig: createConfig(),
      },
    })

    expect(await screen.findByText('运行概况暂不可用')).toBeInTheDocument()
    expect(warn).toHaveBeenCalledWith('[SubscribeAssistantEnhanced] summary unavailable')
    expect(document.body).not.toHaveTextContent('private request details')
  })

  it('removes scroll listeners and disconnects observers when unmounted', async () => {
    const disconnect = vi.fn()
    const observerCallbacks: IntersectionObserverCallback[] = []
    const removeEventListener = vi.spyOn(HTMLElement.prototype, 'removeEventListener')
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(callback: IntersectionObserverCallback) {
          observerCallbacks.push(callback)
        }
        disconnect = disconnect
        observe() {}
        takeRecords() {
          return []
        }
        unobserve() {}
      },
    )
    const { unmount } = await renderConfig()
    const fieldSurface = document.querySelector<HTMLElement>('.sae-field-surface') as HTMLElement
    const header = document.querySelector<HTMLElement>('.sae-config-header') as HTMLElement

    await fireEvent.scroll(fieldSurface)
    expect(fieldSurface).toHaveClass('sae-config-scroll-root--active')
    observerCallbacks.at(-1)?.([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver)
    await waitFor(() => expect(header).toHaveClass('sae-config-header--scrolled'))

    unmount()

    expect(disconnect).toHaveBeenCalled()
    expect(removeEventListener).toHaveBeenCalledWith('scroll', expect.any(Function))
  })
})
