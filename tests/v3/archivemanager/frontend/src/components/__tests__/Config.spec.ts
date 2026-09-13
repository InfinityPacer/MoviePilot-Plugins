import Config from '@/components/Config.vue'
import { createArchiveTask } from '@/config/values'
import { fireEvent, screen, waitFor, within } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { createConfig, createHostApi, createSummary } from '@tests/support/host'
import { renderWithHost } from '@tests/support/render'

describe('ArchiveManager federated config', () => {
  it('renders the host layout and summary contract', async () => {
    const { api, get } = createHostApi(createSummary({ archived_files: 15, archive_count: 4 }))
    const layout = vi.fn()
    renderWithHost(Config, {
      props: { api, initialConfig: createConfig(), onLayout: layout },
    })

    expect(layout).toHaveBeenCalledWith({ maxWidth: '68rem' })
    expect(screen.getByRole('heading', { name: '压缩归档' })).toBeInTheDocument()
    await waitFor(() => expect(get).toHaveBeenCalledWith('plugin/ArchiveManager/summary'))
    const main = document.querySelector('.archive-main') as HTMLElement
    await waitFor(() => expect(within(main).getByText('已归档文件').parentElement).toHaveTextContent('15'))
    await waitFor(() => expect(within(main).getByText('归档批次').parentElement).toHaveTextContent('4'))
  })

  it('creates a task, forces verification for source deletion, and emits a complete config', async () => {
    const { api } = createHostApi()
    const save = vi.fn()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig(), onSave: save } })

    await user.click(screen.getByText('任务', { exact: true }))
    expect(document.querySelector('.archive-main')?.textContent).not.toContain('已归档文件')
    await user.click(screen.getByRole('button', { name: '新增归档任务' }))
    const editor = screen.getByText('新增归档任务').closest('section') as HTMLElement
    const taskName = within(editor).getByRole('textbox', { name: '任务名' })
    await user.clear(taskName)
    await user.type(taskName, '媒体归档')
    await user.click(within(editor).getByRole('checkbox', { name: '删除源文件' }))
    expect(within(editor).getByRole('checkbox', { name: '完成校验' })).toBeChecked()
    await user.click(within(editor).getByRole('button', { name: '保存草稿' }))
    expect(document.querySelector('.archive-header__save')).toHaveTextContent('保存修改')
    await user.click(document.querySelector<HTMLButtonElement>('.archive-header__save') as HTMLButtonElement)

    expect(save).toHaveBeenCalledOnce()
    expect(screen.queryByText('配置已提交给宿主保存。')).not.toBeInTheDocument()
    const payload = save.mock.calls[0][0]
    expect(payload).toEqual(expect.objectContaining({ enabled: false, tasks: expect.any(Array) }))
    expect(payload.tasks[0]).toEqual(expect.objectContaining({ name: '媒体归档', delete_source: true, verify: true }))
    expect(Object.keys(payload.tasks[0])).toEqual(
      expect.arrayContaining([
        'id',
        'name',
        'source_dir',
        'output_dir',
        'manifest_dir',
        'include_patterns',
        'exclude_patterns',
        'password',
        'password_version',
      ]),
    )
    expect(payload.tasks[0]).not.toHaveProperty('timezone')
  })

  it('enables the main save while editing a task and lists the pending task change', async () => {
    const { api } = createHostApi()
    const save = vi.fn()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig(), onSave: save } })

    await user.click(screen.getByText('任务', { exact: true }))
    await user.click(screen.getByRole('button', { name: '新增归档任务' }))
    const editor = screen.getByText('新增归档任务').closest('section') as HTMLElement
    const taskName = within(editor).getByRole('textbox', { name: '任务名' })
    await user.clear(taskName)
    await user.type(taskName, '媒体归档')

    const saveButton = document.querySelector<HTMLButtonElement>('.archive-header__save') as HTMLButtonElement
    expect(saveButton).toBeEnabled()
    expect(screen.getByText('任务：媒体归档')).toBeInTheDocument()
    await user.click(saveButton)

    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0][0].tasks[0]).toEqual(expect.objectContaining({ name: '媒体归档' }))
  })

  it('keeps the draft dirty until the host confirms saving', async () => {
    const { api } = createHostApi()
    const save = vi.fn()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig(), onSave: save, saveResult: 'error' } })

    await user.click(screen.getByText('任务', { exact: true }))
    await user.click(screen.getByRole('button', { name: '新增归档任务' }))
    await user.click(screen.getByRole('button', { name: '保存草稿' }))
    await user.click(document.querySelector<HTMLButtonElement>('.archive-header__save') as HTMLButtonElement)

    expect(save).toHaveBeenCalledOnce()
    expect(document.querySelector('.archive-header__save')).toBeEnabled()
  })

  it('keeps batch directory layout generic and renders the default naming preview', async () => {
    const { api } = createHostApi()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig() } })

    await user.click(screen.getByText('任务', { exact: true }))
    await user.click(screen.getByRole('button', { name: '新增归档任务' }))
    const editor = screen.getByText('新增归档任务').closest('section') as HTMLElement
    const naming = within(editor).getByText('2. 命名规则').closest('.archive-editor__group') as HTMLElement
    const scope = within(editor).getByText('3. 文件范围').closest('.archive-editor__group') as HTMLElement

    expect(within(scope).getByRole('textbox', { name: '目录布局' })).toBeInTheDocument()
    expect(within(naming).queryByText('摄像头')).not.toBeInTheDocument()
    expect(within(naming).getByText(/支持任务名、日期、时间、序号和文件修改时间变量/)).toBeInTheDocument()
    expect(naming.textContent).toContain('7f3a9c')
    expect(within(naming).getByRole('textbox', { name: '批次名称' })).toHaveValue('{date}_{sequence}')
    expect(within(naming).getByText('批次：20260911_0001')).toBeInTheDocument()
    expect(within(naming).getByText('归档包：7f3a9c.7z')).toBeInTheDocument()

    const batchTemplate = within(naming).getByRole('textbox', { name: '批次名称' })
    await user.clear(batchTemplate)
    await fireEvent.update(batchTemplate, '{%Y%m%d_%H%M%S}')
    expect(within(naming).getByText('批次：20260911_040020')).toBeInTheDocument()

    // Vuetify renders the select's accessible name on its internal text input.
    const layout = within(scope).getByRole('textbox', { name: '目录布局' })
    expect(layout).toHaveValue('directory')
    await user.click(layout)
    expect(await screen.findByText('扁平（来源目录_批次名称）')).toBeInTheDocument()
  })

  it('renders task_name and file_mtime variables in the naming preview', async () => {
    const task = createArchiveTask({ id: 'task-1', name: '存量任务', batch_name_template: '{task_name}_{date}' })
    const { api } = createHostApi()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig({ tasks: [task] }) } })

    await user.click(screen.getByText('任务', { exact: true }))
    await user.click(screen.getByRole('button', { name: '编辑归档任务' }))
    const editor = screen.getByText('编辑归档任务').closest('section') as HTMLElement
    const naming = within(editor).getByText('2. 命名规则').closest('.archive-editor__group') as HTMLElement

    expect(within(naming).getByText('批次：存量任务_20260911')).toBeInTheDocument()
    expect(within(naming).getByRole('textbox', { name: '批次名称' })).toHaveValue('{task_name}_{date}')

    const batchTemplate = within(naming).getByRole('textbox', { name: '批次名称' })
    await fireEvent.update(batchTemplate, '{file_mtime:%Y-%m-%d_%H-%M-%S}')
    expect(within(naming).getByText('批次：2026-01-28_14-19-30')).toBeInTheDocument()
  })

  it('does not silently downgrade ZIP file-name encryption', async () => {
    const task = createArchiveTask({ id: 'task-1', name: '加密任务', encryption: 'aes256', encrypt_names: true })
    const { api } = createHostApi()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig({ tasks: [task] }) } })

    await user.click(screen.getByText('任务', { exact: true }))
    await user.click(screen.getByRole('button', { name: '编辑归档任务' }))
    const editor = screen.getByText('编辑归档任务').closest('section') as HTMLElement
    const format = within(editor).getByRole('textbox', { name: '格式' })
    await user.click(format)
    await user.click(await screen.findByText('ZIP', { exact: true }))
    expect(
      await screen.findByText('ZIP 不支持加密文件名。切换为 ZIP 会关闭“加密文件名”，是否继续？'),
    ).toBeInTheDocument()
    expect(format).toHaveValue('7z')
  })

  it('clears file-name encryption when switching AES-256 off', async () => {
    const task = createArchiveTask({ id: 'task-1', name: '加密任务', encryption: 'aes256', encrypt_names: true })
    const { api } = createHostApi()
    const save = vi.fn()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig({ tasks: [task] }), onSave: save } })

    await user.click(screen.getByText('任务', { exact: true }))
    await user.click(screen.getByRole('button', { name: '编辑归档任务' }))
    const editor = screen.getByText('编辑归档任务').closest('section') as HTMLElement
    const encryption = within(editor).getByRole('textbox', { name: '加密' })
    await user.click(encryption)
    await user.click(await screen.findByText('不加密', { exact: true }))
    await user.click(within(editor).getByRole('button', { name: '保存草稿' }))
    await user.click(document.querySelector<HTMLButtonElement>('.archive-header__save') as HTMLButtonElement)
    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0][0].tasks[0]).toEqual(
      expect.objectContaining({ encryption: 'none', encrypt_names: false }),
    )
  })

  it('switches between batches and files and closes through the host command', async () => {
    const { api, get } = createHostApi()
    const task = createArchiveTask({ id: 'task-1', name: '媒体归档' })
    const close = vi.fn()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig({ tasks: [task] }), onClose: close } })

    await user.click(screen.getByText('批次'))
    await waitFor(() => expect(get).toHaveBeenCalledWith(expect.stringContaining('plugin/ArchiveManager/batches')))
    await user.click(screen.getByText('文件'))
    await waitFor(() => expect(get).toHaveBeenCalledWith(expect.stringContaining('plugin/ArchiveManager/files')))
    await user.click(document.querySelector<HTMLButtonElement>('.archive-header__close-action') as HTMLButtonElement)
    expect(close).toHaveBeenCalled()
  })

  it('shows an empty state without file controls when no archive task exists', async () => {
    const { api } = createHostApi()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig() } })

    await user.click(screen.getByText('文件', { exact: true }))

    expect(await screen.findByText('暂无归档任务')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '文件任务' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '搜索文件' })).not.toBeInTheDocument()
    expect(screen.queryByText(/共 .* 个文件/)).not.toBeInTheDocument()
  })

  it('asks for a task when the file task filter is cleared', async () => {
    const task = createArchiveTask({ id: 'task-1', name: '媒体归档' })
    const { api } = createHostApi()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig({ tasks: [task] }) } })

    await user.click(screen.getByText('文件', { exact: true }))
    await user.click(screen.getByRole('button', { name: 'Clear 任务' }))

    expect(await screen.findByText('请选择归档任务')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '搜索文件' })).toBeInTheDocument()
    expect(screen.queryByText(/共 .* 个文件/)).not.toBeInTheDocument()
  })

  it('hides the zero-count pagination when the selected task has no files', async () => {
    const task = createArchiveTask({ id: 'task-1', name: '媒体归档' })
    const { api } = createHostApi()
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig({ tasks: [task] }) } })

    await user.click(screen.getByText('文件', { exact: true }))

    expect(await screen.findByText('没有找到文件')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '搜索文件' })).toBeInTheDocument()
    expect(screen.queryByText(/共 .* 个文件/)).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: '文件目录' })).toBeInTheDocument()
  })

  it('derives manifest file status and separates local archive availability from verification', async () => {
    const { api, get } = createHostApi()
    const task = createArchiveTask({ id: 'task-1', name: '媒体归档' })
    const batch = {
      id: 'batch-1',
      task_id: task.id,
      task_name: task.name,
      status: 'completed',
      created_at: '2026-09-10T12:00:00Z',
      archive_path: '/archive/batch-1.7z',
      manifest_path: '/manifest/batch-1.md',
      archive_size: 1024,
      source_bytes: 2048,
      file_count: 2,
      verified: true,
      archive_sha256: 'archive-sha',
      error: '',
      archive_available: false,
      manifest_available: true,
      cleanup: { 'deleted.mkv': 'deleted' },
      files: [
        { relative_path: 'kept.mkv', size: 1024, mtime_ns: 1, sha256: 'kept-sha' },
        { relative_path: 'deleted.mkv', size: 1024, mtime_ns: 2, sha256: 'deleted-sha' },
      ],
    }
    get.mockImplementation(async (path: string) => {
      if (path === 'plugin/ArchiveManager/summary') return { success: true, message: '', data: createSummary() }
      if (path.startsWith('plugin/ArchiveManager/batches')) {
        return { success: true, message: '', data: { items: [batch], total: 1 } }
      }
      if (path.startsWith('plugin/ArchiveManager/batch')) return { success: true, message: '', data: batch }
      return { success: true, message: '', data: { items: [], directories: [], total: 0 } }
    })
    const user = userEvent.setup()
    renderWithHost(Config, { props: { api, initialConfig: createConfig({ tasks: [task] }) } })

    await user.click(screen.getByText('批次'))
    await user.click(await screen.findByRole('button', { name: '查看批次详情' }))

    expect(await screen.findByText('已不在本地')).toBeInTheDocument()
    const fileRows = Array.from(document.querySelectorAll<HTMLTableRowElement>('.archive-table tbody tr')).filter(row =>
      row.textContent?.includes('.mkv'),
    )
    const keptRow = fileRows.find(row => row.textContent?.includes('kept.mkv'))
    const deletedRow = fileRows.find(row => row.textContent?.includes('deleted.mkv'))
    if (!keptRow || !deletedRow) throw new Error('批次详情文件行未渲染')
    expect(within(keptRow).getByText('已归档')).toBeInTheDocument()
    expect(within(deletedRow).getByText('已删除源文件')).toBeInTheDocument()
  })
})
