/**
 * Agent 助手形象契约 v1 中插件侧需要的宿主类型。
 *
 * 结构与主程序 `MoviePilotAgentHost` 保持一致；插件按结构使用，不依赖宿主源码。
 * 旧版主程序没有这些能力，调用方必须对宿主对象和每个方法做空值保护。
 */

/** 视口矩形，单位为 CSS 像素。 */
export interface AgentRect {
  x: number
  y: number
  width: number
  height: number
}

/** 宿主归纳的会话阶段。 */
export type AgentPhase = 'idle' | 'thinking' | 'tool' | 'awaiting' | 'done' | 'error'

/** 宿主状态快照，由 `subscribe` 推送。 */
export interface AgentHostState {
  /** Agent 是否启用；为 false 时 `open` 为空操作。 */
  available: boolean
  /** 原生面板是否打开。 */
  panelOpen: boolean
  /** 是否正在等待模型输出。 */
  thinking: boolean
  /** 会话阶段。 */
  phase: AgentPhase
  /** phase 为 tool 时的工具名，可能为空。 */
  toolName: string | null
  /** 页面是否可见。 */
  pageVisible: boolean
  /** 宿主动画开关与系统减少动态效果合并后的结论。 */
  motionAllowed: boolean
  /** 系统是否要求减少动态效果。 */
  reducedMotion: boolean
  /** 当前主题。 */
  theme: 'light' | 'dark'
  /** 是否为移动端布局。 */
  isMobile: boolean
  /** 视口尺寸、软键盘占用高度与安全区。 */
  viewport: {
    width: number
    height: number
    keyboardInset: number
    safeArea: { top: number; right: number; bottom: number; left: number }
  }
  /** 面板打开时占据的视口矩形，关闭时为 null。 */
  panelRect: AgentRect | null
}

/** 宿主或其他插件广播的事件。 */
export interface AgentHostEvent {
  /** 事件名，宿主事件以 `agent.` 开头。 */
  name: string
  /** `host` 或发出事件的插件实例 ID。 */
  source: string
  /** 事件数据。 */
  data: Record<string, unknown>
  /** 发生时间戳（毫秒）。 */
  at: number
}

/** `moviepilot:agent` 宿主对象，已按插件实例绑定。 */
export interface MoviePilotAgentHost {
  version: 1
  getState(): AgentHostState
  /** 立即以当前快照回调一次，之后每次变化回调；返回取消函数。 */
  subscribe(listener: (state: AgentHostState) => void): () => void
  /** 打开原生面板；draft 只填入输入框，不发送。 */
  open(options?: { draft?: string }): void
  close(): void
  /** 订阅事件，返回取消函数。 */
  on(event: string, handler: (payload: AgentHostEvent) => void): () => void
  /** 广播自定义事件；名称不得以 `agent.` 开头，宿主自动附 source。 */
  emit(name: string, data?: Record<string, unknown>): void
}

/** 宿主传给形象组件的形象上下文。 */
export interface AgentPetContext {
  mode: 'stage' | 'renderer'
  key: string
  /** 上报角色在视口中的矩形，宿主把原生气泡画在旁边；null 隐藏宿主气泡。 */
  setBubbleAnchor(rect: AgentRect | null): void
  /** 声明角色是否正在被拖拽，宿主据此不弹预览。 */
  setInteracting(value: boolean): void
  /** 每用户每形象的小块持久数据，序列化后不超过 16KB。 */
  storage: { get<T = unknown>(): Promise<T | null>; set(value: unknown): Promise<void> }
}

/** 插件接口统一响应。 */
export interface ApiResponse<T> {
  success?: boolean
  message?: string
  data?: T | null
}

/** 宿主 `api` prop 的最小结构（已绑定插件实例）。 */
export interface PluginApi {
  get<T = unknown>(path: string): Promise<ApiResponse<T> | null | undefined>
  post<T = unknown>(path: string, body?: unknown): Promise<ApiResponse<T> | null | undefined>
}

/** 宿主提供 `moviepilot:agent` 的注入键。 */
export const AGENT_HOST_KEY = 'moviepilot:agent'

/**
 * 主程序缺少 `moviepilot:agent` 时的提示。
 *
 * 插件仓版本门禁把 V3 插件的 `system_version` 固定为 `>=3.0.0`，挡不住旧主程序；
 * 旧主程序能安装插件但不会显示形象，因此在配置页和预览页顶部说明需要的版本。
 */
export const HOST_UNSUPPORTED_MESSAGE = '当前主程序版本不支持助手形象，请升级到 v3.1.4 及以上'
