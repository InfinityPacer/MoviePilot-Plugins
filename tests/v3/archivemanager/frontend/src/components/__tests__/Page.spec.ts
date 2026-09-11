import Page from '@/components/Page.vue'
import { screen, waitFor } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { createHostApi, createSummary } from '@tests/support/host'
import { renderWithHost } from '@tests/support/render'

describe('ArchiveManager federated page', () => {
  it('loads the host config and keeps password_set without echoing the password', async () => {
    const { api, get } = createHostApi()
    get.mockImplementation(async (path: string) => {
      if (path === 'plugin/ArchiveManager') {
        return {
          success: true,
          message: '',
          data: {
            enabled: true,
            tasks: [{ id: 'task-1', name: '媒体归档', password: '', password_set: true }],
          },
        }
      }
      if (path === 'plugin/ArchiveManager/summary') return { success: true, message: '', data: createSummary() }
      return { success: true, message: '', data: { items: [], directories: [], total: 0 } }
    })

    renderWithHost(Page, { props: { api } })

    await waitFor(() => expect(get).toHaveBeenCalledWith('plugin/ArchiveManager'))
    await userEvent.setup().click(await screen.findByText('任务', { exact: true }))
    expect(await screen.findByText('密码已保存')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('secret')).not.toBeInTheDocument()
  })

  it('persists through the plugin PUT endpoint and reloads without leaving the active view', async () => {
    const { api, get, put } = createHostApi()
    const config = { enabled: true, tasks: [{ id: 'task-1', name: '媒体归档' }] }
    put.mockImplementation(async (_path: string, body: unknown) => {
      Object.assign(config, body as Partial<typeof config>)
      return { success: true, message: '', data: null }
    })
    get.mockImplementation(async (path: string) => {
      if (path === 'plugin/ArchiveManager') return { success: true, message: '', data: config }
      if (path === 'plugin/ArchiveManager/summary') return { success: true, message: '', data: createSummary() }
      return { success: true, message: '', data: { items: [], directories: [], total: 0 } }
    })
    const user = userEvent.setup()
    renderWithHost(Page, { props: { api } })

    await user.click(await screen.findByText('任务', { exact: true }))
    await screen.findByRole('heading', { name: '媒体归档' })
    await user.click(screen.getByRole('button', { name: '编辑归档任务' }))
    const name = screen.getByRole('textbox', { name: '任务名称' })
    await user.clear(name)
    await user.type(name, '媒体归档 2')
    await user.click(screen.getByRole('button', { name: '保存任务' }))
    expect(document.querySelector('.archive-header__save')).toHaveTextContent('保存修改')
    await user.click(document.querySelector<HTMLButtonElement>('.archive-header__save') as HTMLButtonElement)

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith('plugin/ArchiveManager', expect.objectContaining({ enabled: true })),
    )
    expect(screen.getByRole('heading', { name: '任务' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '媒体归档 2' })).toBeInTheDocument()
    await waitFor(() => expect(get.mock.calls.filter(([path]) => path === 'plugin/ArchiveManager')).toHaveLength(2))
  })

  it('forwards close and layout events to the host', async () => {
    const { api, get } = createHostApi()
    get.mockImplementation(async (path: string) => {
      if (path === 'plugin/ArchiveManager') return { success: true, message: '', data: { enabled: false, tasks: [] } }
      if (path === 'plugin/ArchiveManager/summary') return { success: true, message: '', data: createSummary() }
      return { success: true, message: '', data: { items: [], directories: [], total: 0 } }
    })
    const close = vi.fn()
    const layout = vi.fn()
    renderWithHost(Page, { props: { api, onClose: close, onLayout: layout } })

    await waitFor(() => expect(layout).toHaveBeenCalledWith({ maxWidth: '68rem' }))
    await userClickClose()
    expect(close).toHaveBeenCalledOnce()
  })
})

async function userClickClose(): Promise<void> {
  const user = userEvent.setup()
  const closeButton = document.querySelector<HTMLButtonElement>('.archive-header__close-action')
  if (!closeButton) throw new Error('ArchiveManager close button not found')
  await user.click(closeButton)
}
