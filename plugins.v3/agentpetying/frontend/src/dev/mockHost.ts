import type { AgentHostEvent, AgentHostState, AgentPetContext, AgentRect, MoviePilotAgentHost } from '@/host'

/** 开发预览页里可手动驱动的宿主模拟对象。 */
export interface MockAgentHost extends MoviePilotAgentHost {
  /** 合并更新状态并通知订阅者。 */
  patch(partial: Partial<AgentHostState>): void
  /** 以宿主身份派发事件。 */
  fire(name: string, data?: Record<string, unknown>): void
  /** `open`/`close` 等调用记录，便于在预览页展示。 */
  calls: string[]
  /** 释放窗口监听。 */
  dispose(): void
}

function windowViewport(): AgentHostState['viewport'] {
  return {
    width: window.innerWidth,
    height: window.innerHeight,
    keyboardInset: 0,
    safeArea: { top: 0, right: 0, bottom: 0, left: 0 },
  }
}

/**
 * 创建页面内宿主模拟。
 *
 * 宿主事件只能由宿主发出，插件的 `emit` 不能伪造 `agent.*`，所以预览页始终用模拟对象
 * 驱动被预览的形象实例；`pluginId` 作为自定义事件的来源标记。
 */
export function createMockHost(pluginId: string, onCall?: (call: string) => void): MockAgentHost {
  let state: AgentHostState = {
    available: true,
    panelOpen: false,
    thinking: false,
    phase: 'idle',
    toolName: null,
    pageVisible: true,
    motionAllowed: true,
    reducedMotion: false,
    theme: 'light',
    isMobile: window.innerWidth < 600,
    viewport: windowViewport(),
    panelRect: null,
  }
  const listeners = new Set<(value: AgentHostState) => void>()
  const handlers = new Map<string, Set<(payload: AgentHostEvent) => void>>()
  const calls: string[] = []

  function record(call: string) {
    calls.unshift(call)
    calls.splice(20)
    onCall?.(call)
  }

  function dispatch(name: string, source: string, data: Record<string, unknown> = {}) {
    const payload: AgentHostEvent = { name, source, data, at: Date.now() }
    for (const handler of handlers.get(name) ?? []) handler(payload)
  }

  function patch(partial: Partial<AgentHostState>) {
    state = { ...state, ...partial }
    for (const listener of listeners) listener(state)
  }

  const onResize = () =>
    patch({ viewport: { ...state.viewport, width: window.innerWidth, height: window.innerHeight } })
  window.addEventListener('resize', onResize)

  return {
    version: 1,
    calls,
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener)
      listener(state)
      return () => listeners.delete(listener)
    },
    open(options) {
      record(options?.draft ? `open(draft=${options.draft})` : 'open()')
      if (!state.available) return
      if (!state.panelOpen) {
        patch({ panelOpen: true })
        dispatch('agent.panel.open', 'host')
      }
    },
    close() {
      record('close()')
      if (state.panelOpen) {
        patch({ panelOpen: false, panelRect: null })
        dispatch('agent.panel.close', 'host')
      }
    },
    on(name, handler) {
      const set = handlers.get(name) ?? new Set()
      set.add(handler)
      handlers.set(name, set)
      return () => set.delete(handler)
    },
    emit(name, data) {
      if (name.startsWith('agent.')) return
      dispatch(name, pluginId, data ?? {})
    },
    patch,
    fire(name, data) {
      dispatch(name, 'host', data ?? {})
    },
    dispose() {
      window.removeEventListener('resize', onResize)
      listeners.clear()
      handlers.clear()
    },
  }
}

/** 预览用形象上下文：锚点交给回调绘制模拟气泡，存储只留在内存。 */
export function createMockPet(
  mode: 'stage' | 'renderer',
  key: string,
  hooks: { onAnchor?: (rect: AgentRect | null) => void; onInteracting?: (value: boolean) => void } = {},
): AgentPetContext {
  let stored: unknown = null
  return {
    mode,
    key,
    setBubbleAnchor: rect => hooks.onAnchor?.(rect),
    setInteracting: value => hooks.onInteracting?.(value),
    storage: {
      get: async <T>() => stored as T | null,
      set: async (value: unknown) => {
        if (JSON.stringify(value ?? null).length > 16 * 1024) throw new Error('storage value exceeds 16KB')
        stored = value
      },
    },
  }
}
