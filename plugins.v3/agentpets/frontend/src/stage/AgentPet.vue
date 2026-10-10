<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { AgentHostEvent, AgentHostState, AgentPetContext, AgentRect, MoviePilotAgentHost, PluginApi } from '@/host'
import {
  blockedSpan,
  checkSupport,
  clamp,
  computeLanding,
  coversAny,
  effectiveScale,
  pickClearX,
  escapeSpan,
  freeBounds,
  groundTop,
  isBlocked,
  pickFreeTarget,
  pickWalkTarget,
  ratioToX,
  readViewport,
  sameRect,
  surfaceXBounds,
  xBounds,
  xToRatio,
  type Landing,
  type RoamMode,
} from '@/stage/geometry'
import { eventPose, frameUrl, phasePose, POSES, resolvePose, walkFrame, type Motion, type Pose } from '@/stage/poses'
import { DEFAULT_SETTINGS, loadSettings, normalizeSettings, SETTINGS_EVENT, type YingSettings } from '@/stage/settings'
import { collectControls, measureSurface, querySurfaces, surfaceVisible, type DomSurface } from '@/stage/surfaces'

/**
 * 小映 stage 形象。
 *
 * 宿主把本组件挂在 `pointer-events: none` 的全视口图层里，组件只让角色按钮接收指针。
 * 所有订阅、rAF、计时器、DOM 观察和全局监听都在卸载时释放；旧版主程序不传 `agent`/`pet`
 * 时组件仍能显示与拖拽，只是无法打开面板和上报气泡锚点。
 *
 * 活动范围（`roam`）决定落点：surfaces 落到正下方的页面元素上，floor 只在视口底边，
 * free 没有重力、放在哪里停在哪里。可站元素只在开始下落或开始走动时查询一次，
 * 站着时靠 scroll、resize 和节流的 MutationObserver 重新校验脚下的元素。
 */
const props = withDefaults(
  defineProps<{
    agent?: MoviePilotAgentHost | null
    pet?: AgentPetContext | null
    api?: Pick<PluginApi, 'get'> | null
    pluginId?: string
    sourcePluginId?: string
  }>(),
  { agent: null, pet: null, api: null, pluginId: '', sourcePluginId: '' },
)

/** 设置为 1 倍时的角色高度（CSS 像素）。 */
const BASE_HEIGHT = 120
/**
 * 大小和速度都为 1 倍时的走路速度（像素/秒）。
 *
 * 实际速度再乘大小倍率：角色越大步子越大，配合按距离推进的走路帧保持不滑步。
 */
const BASE_WALK_SPEED = 70
/** 自由停放时游走速度相对走路速度的比例。 */
const FREE_SPEED_RATIO = 0.6
const GRAVITY = 2600
const DRAG_THRESHOLD = 6
const SIT_DURATION = 900
const DOZE_AFTER = 90_000
const PEEK_RATIO = 0.5
const PEEK_SPEED = 160
const DEFAULT_RATIO = 0.88
/** DOM 变化后重新校验脚下元素的节流间隔（毫秒）。 */
const SURFACE_CHECK_INTERVAL = 500
/** 用户放下后过多久自己走开，让用户看得出是她主动挪开的（毫秒）。 */
const DROP_CLEAR_DELAY = 1500
/** 窗口尺寸变化后合并多久再检查是否挡住控件（毫秒）。 */
const RESIZE_CLEAR_DELAY = 300
/** 写回落脚点的最短间隔（毫秒），避免频繁写服务端。 */
const SAVE_THROTTLE = 30_000
/** 站立时每隔几拍（每拍 500ms）复查一次是否挡住控件。 */
const CLEARANCE_POLL_EVERY = 4
/** 同一帧加载失败后，至少隔这么久（毫秒）才再次请求。 */
const FRAME_RETRY_AFTER = 5000

/** `pet.storage` 中保存的每用户数据。 */
interface StoredPosition {
  /** 保存时的活动范围。 */
  roam?: RoamMode
  /** 落脚点在可活动范围内的水平比例，0 为最左，1 为最右。 */
  xRatio: number
  /** 顶边在视口可用高度内的比例，0 为最上，1 为底边；只用于恢复站在元素上或自由停放的位置。 */
  yRatio?: number
}

const rootEl = ref<HTMLElement | null>(null)
const settings = ref<YingSettings>({ ...DEFAULT_SETTINGS })
const aspect = ref(198 / 240)
const x = ref(0)
const y = ref(0)
const sink = ref(0)
const facingLeft = ref(false)
const motion = ref<Motion>('idle')
const walkPhase = ref(0)
const transient = ref<Pose | null>(null)
const sustained = ref<Pose | null>(null)
const dozing = ref(false)
const blinking = ref(false)
const ready = ref(false)
const rising = ref(false)
const available = ref(true)
/** 宿主判定的窄屏布局，窄屏时角色再缩小。 */
const isMobile = ref(false)

let hostState: AgentHostState | null = null
let documentVisible = typeof document === 'undefined' || document.visibilityState !== 'hidden'
let rafId = 0
let lastFrame = 0
let anchorFrame = 0
let lastAnchor: AgentRect | null = null
let walkTarget: { x: number; y: number | null } | null = null
let walkDistance = 0
let velocity = 0
let bounced = false
let fallTarget: Landing<DomSurface> | null = null
let peekTarget = 0
let lastSaved = ''
let lastSaveAt = 0
/** 下一次落地后保存落脚点：用户拖拽放下或活动范围改变时置位。 */
let saveOnLand = false
let suppressClick = false
/** 散步到底边一侧后接着探头。 */
let pendingPeek = false
/** 走到元素边缘后跳下去。 */
let pendingStepOff = false
/** 当前站着的页面元素；站在底边或自由停放时为 null。 */
let surface: DomSurface | null = null
let surfaceFrame = 0
let surfaceObserver: MutationObserver | null = null
let surfacePoll = 0
let standPollTicks = 0
let disposed = false
/** 最近一次落地来自用户拖拽放下。 */
let droppedByUser = false
/** 首次出现时直接放到不挡控件的位置，不走过去。 */
let initialPlacement = true
let press: { id: number; startX: number; startY: number; offsetX: number; offsetY: number; dragging: boolean } | null =
  null

const timers = new Map<string, number>()
const cleanups: Array<() => void> = []

const charHeight = computed(() => BASE_HEIGHT * effectiveScale(settings.value.scale, isMobile.value))
const charWidth = computed(() => charHeight.value * aspect.value)
const pose = computed<Pose>(() =>
  resolvePose({
    motion: motion.value,
    walkPhase: walkPhase.value,
    transient: transient.value,
    sustained: sustained.value,
    dozing: dozing.value,
    blinking: blinking.value,
    rising: rising.value,
  }),
)
const label = computed(() => (available.value ? '打开助手（小映）' : '小映（助手未启用）'))

/** 单帧图片的加载状态。 */
type FrameStatus = 'pending' | 'loaded' | 'error'

/**
 * 所有姿态帧同时渲染成叠放的 img，换帧只切换哪一张可见。
 *
 * 宿主的插件静态文件接口不返回缓存头，若换帧时改 img 的 src，每次都会重新请求并等待解码，
 * 走路时会闪；叠放后换帧不发请求，也不等解码。只有加载失败的帧在重试时才改它自己的 src。
 */
const frameStatus = ref<Record<Pose, FrameStatus>>(
  Object.fromEntries(POSES.map(name => [name, 'pending'])) as Record<Pose, FrameStatus>,
)
/** 每帧的地址；失败重试时在该帧地址后追加序号。 */
const frameSrc = ref<Record<Pose, string>>(
  Object.fromEntries(POSES.map(name => [name, frameUrl(name)])) as Record<Pose, string>,
)
/** 当前可见的帧；目标帧未就绪时停在上一帧成功显示的图上，一帧都没有时为 null。 */
const displayed = ref<Pose | null>(null)
const failedAt = new Map<Pose, number>()
const retries = new Map<Pose, number>()

/** 目标帧就绪就显示它；还没加载好或加载失败时保留上一帧，失败满重试间隔后重新请求该帧。 */
function syncDisplayed() {
  const target = pose.value
  if (frameStatus.value[target] === 'loaded') {
    displayed.value = target
    return
  }
  const failed = failedAt.get(target)
  if (frameStatus.value[target] === 'error' && failed !== undefined && Date.now() - failed >= FRAME_RETRY_AFTER) {
    const attempt = (retries.get(target) ?? 0) + 1
    retries.set(target, attempt)
    failedAt.delete(target)
    frameStatus.value[target] = 'pending'
    frameSrc.value[target] = `${frameUrl(target)}?retry=${attempt}`
  }
  if (displayed.value && frameStatus.value[displayed.value] !== 'loaded') displayed.value = null
}

watch(pose, syncDisplayed)

function onFrameLoad(name: Pose, event: Event) {
  frameStatus.value[name] = 'loaded'
  failedAt.delete(name)
  if (name === 'idle') {
    const image = event.target as HTMLImageElement
    if (image.naturalWidth && image.naturalHeight) {
      aspect.value = image.naturalWidth / image.naturalHeight
      relayout()
    }
  }
  if (name === pose.value) displayed.value = name
}

/** 服务停掉或网络中断时帧图会加载失败；记下时间，显示上保留上一帧。 */
function onFrameError(name: Pose) {
  frameStatus.value[name] = 'error'
  failedAt.set(name, Date.now())
  if (displayed.value === name) displayed.value = null
  syncDisplayed()
}

const buttonStyle = computed(() => ({
  width: `${charWidth.value}px`,
  height: `${charHeight.value}px`,
  transform: `translate3d(${x.value}px, ${y.value + sink.value}px, 0)`,
  clipPath: sink.value > 0 ? `inset(0 0 ${sink.value}px 0)` : undefined,
}))

function setTimer(name: string, delay: number, callback: () => void) {
  clearTimer(name)
  timers.set(
    name,
    window.setTimeout(() => {
      timers.delete(name)
      callback()
    }, delay),
  )
}

function clearTimer(name: string) {
  const id = timers.get(name)
  if (id !== undefined) window.clearTimeout(id)
  timers.delete(name)
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

function roam(): RoamMode {
  return settings.value.roam
}

function viewport() {
  return readViewport(hostState)
}

function ground(): number {
  return groundTop(viewport(), charHeight.value)
}

/** 当前站立面的顶边 y：站在元素上时是元素上边缘减身高，否则是底边。 */
function standY(): number {
  return surface ? surface.top - charHeight.value : ground()
}

function size() {
  return { width: charWidth.value, height: charHeight.value }
}

/** 当前可走动的水平范围。 */
function bounds(): [number, number] {
  if (roam() === 'free') return freeBounds(viewport(), charWidth.value, charHeight.value).x
  if (surface) return surfaceXBounds(surface, viewport(), charWidth.value)
  return xBounds(viewport(), charWidth.value)
}

function panelSpan(): [number, number] | null {
  if (roam() === 'free') return null
  return blockedSpan(hostState?.panelRect ?? null, standY(), charWidth.value, charHeight.value)
}

function motionAllowed(): boolean {
  if (hostState) return hostState.motionAllowed
  return !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function visible(): boolean {
  return documentVisible && (hostState?.pageVisible ?? true)
}

function onGround(): boolean {
  return motion.value !== 'drag' && motion.value !== 'fall'
}

/** 只在视口底边（没有站在元素上、也不是自由停放）时才会探头。 */
function onFloor(): boolean {
  return roam() !== 'free' && !surface
}

/** 角色当前露出的矩形；探头时只报告地面以上的部分。 */
function currentRect(): AgentRect {
  return { x: x.value, y: y.value + sink.value, width: charWidth.value, height: charHeight.value - sink.value }
}

function reportAnchor() {
  anchorFrame = 0
  if (disposed || !ready.value) return
  const rect = currentRect()
  if (sameRect(rect, lastAnchor)) return
  lastAnchor = rect
  props.pet?.setBubbleAnchor?.(rect)
}

/** 每帧最多上报一次锚点；动画循环内直接上报，其余变化合并到下一帧。 */
function queueAnchor() {
  if (anchorFrame || rafId) return
  anchorFrame = window.requestAnimationFrame(reportAnchor)
}

function needsLoop(): boolean {
  if (motion.value === 'walk' || motion.value === 'fall') return true
  return motion.value === 'peek' && sink.value !== peekTarget
}

function ensureLoop() {
  if (rafId || disposed || !visible() || !needsLoop()) return
  if (anchorFrame) {
    window.cancelAnimationFrame(anchorFrame)
    anchorFrame = 0
  }
  lastFrame = 0
  rafId = window.requestAnimationFrame(tick)
}

function stopLoop() {
  if (rafId) window.cancelAnimationFrame(rafId)
  rafId = 0
}

function tick(timestamp: number) {
  rafId = 0
  const dt = lastFrame ? Math.min((timestamp - lastFrame) / 1000, 0.05) : 1 / 60
  lastFrame = timestamp
  if (motion.value === 'walk') stepWalk(dt)
  else if (motion.value === 'fall') stepFall(dt)
  else if (motion.value === 'peek') stepPeek(dt)
  reportAnchor()
  if (needsLoop() && visible()) rafId = window.requestAnimationFrame(tick)
}

function stepWalk(dt: number) {
  if (!walkTarget) {
    finishWalk()
    return
  }
  const speed =
    BASE_WALK_SPEED *
    settings.value.speed *
    (charHeight.value / BASE_HEIGHT) *
    (roam() === 'free' ? FREE_SPEED_RATIO : 1)
  const dx = walkTarget.x - x.value
  const dy = walkTarget.y === null ? 0 : walkTarget.y - y.value
  const distance = Math.hypot(dx, dy)
  const step = speed * dt
  const arrived = distance <= step
  const nextX = arrived ? walkTarget.x : x.value + (dx / distance) * step
  const nextY = arrived || walkTarget.y === null ? (walkTarget.y ?? y.value) : y.value + (dy / distance) * step
  if (isBlocked(nextX, panelSpan())) {
    finishWalk()
    return
  }
  walkDistance += Math.hypot(nextX - x.value, nextY - y.value)
  walkPhase.value = walkFrame(walkDistance, charHeight.value)
  if (Math.abs(nextX - x.value) > 0.01) facingLeft.value = nextX < x.value
  x.value = nextX
  y.value = nextY
  if (arrived) finishWalk()
}

function stepFall(dt: number) {
  const target = fallTarget?.y ?? ground()
  velocity += GRAVITY * dt
  y.value += velocity * dt
  rising.value = velocity < 0
  if (y.value < target) return
  y.value = target
  // 第一次着地按速度做一次小回弹，之后直接坐下。
  if (!bounced && velocity > 500) {
    bounced = true
    velocity = -velocity * 0.22
    return
  }
  land(true)
}

function stepPeek(dt: number) {
  const step = PEEK_SPEED * dt
  sink.value =
    sink.value < peekTarget ? Math.min(peekTarget, sink.value + step) : Math.max(peekTarget, sink.value - step)
  if (sink.value === 0 && peekTarget === 0) {
    motion.value = 'idle'
    scheduleBehavior()
  }
}

function startWalk(targetX: number, targetY: number | null = null) {
  walkTarget = { x: targetX, y: targetY }
  walkDistance = 0
  facingLeft.value = targetX < x.value
  motion.value = 'walk'
  ensureLoop()
}

function finishWalk() {
  walkTarget = null
  walkPhase.value = 0
  if (motion.value === 'walk') motion.value = 'idle'
  const peek = pendingPeek
  const stepOff = pendingStepOff
  pendingPeek = false
  pendingStepOff = false
  scheduleClearance(0)
  if (stepOff && surface) stepOffEdge()
  else if (peek) beginPeek()
  else scheduleBehavior()
}

function beginPeek() {
  if (!motionAllowed() || !onFloor()) return
  // 探头时面朝屏幕内侧。
  facingLeft.value = x.value > (bounds()[0] + bounds()[1]) / 2
  motion.value = 'peek'
  peekTarget = Math.round(charHeight.value * PEEK_RATIO)
  ensureLoop()
  setTimer('peek', randomBetween(4000, 7000), endPeek)
}

function endPeek() {
  clearTimer('peek')
  if (motion.value !== 'peek') return
  peekTarget = 0
  if (!motionAllowed()) {
    sink.value = 0
    motion.value = 'idle'
    queueAnchor()
  }
  ensureLoop()
  scheduleBehavior()
}

/** 打断散步与探头，让角色回到站立。 */
function settle() {
  if (motion.value === 'walk') {
    walkTarget = null
    walkPhase.value = 0
    motion.value = 'idle'
  }
  if (motion.value === 'peek') {
    clearTimer('peek')
    peekTarget = 0
    if (motionAllowed() && visible()) ensureLoop()
    else {
      sink.value = 0
      motion.value = 'idle'
    }
  }
  pendingPeek = false
  pendingStepOff = false
}

function calm(): boolean {
  return (
    motion.value === 'idle' && !transient.value && !sustained.value && !dozing.value && motionAllowed() && visible()
  )
}

/**
 * 空闲行为：底边上偶尔散步或走到一侧探头，元素上偶尔走到边缘跳下去，
 * 自由停放时在视口内慢慢游走。
 */
function scheduleBehavior() {
  clearTimer('behavior')
  if (!calm()) return
  setTimer('behavior', randomBetween(6000, 14000), () => {
    if (!calm()) return
    if (roam() === 'free') {
      const target = pickFreeTarget(Math.random, { x: x.value, y: y.value }, freeBounds(viewport(), ...sizePair()))
      if (target) startWalk(target.x, target.y)
      else scheduleBehavior()
      return
    }
    const [min, max] = bounds()
    const roll = Math.random()
    if (roll < 0.25) {
      const side = Math.random() < 0.5 ? min : max
      const span = panelSpan()
      if (isBlocked(side, span)) {
        scheduleBehavior()
        return
      }
      if (surface) pendingStepOff = Math.random() < 0.5
      else pendingPeek = true
      if (Math.abs(side - x.value) < 1) finishWalk()
      else startWalk(side)
      return
    }
    const target = roll < 0.85 ? pickWalkTarget(Math.random, x.value, [min, max], panelSpan()) : null
    if (target === null) scheduleBehavior()
    else startWalk(target)
  })
}

function sizePair(): [number, number] {
  return [charWidth.value, charHeight.value]
}

/** 站在元素边缘时朝外迈一步，让中心离开元素后下落。 */
function stepOffEdge() {
  if (!surface) return
  const [min, max] = bounds()
  const direction = x.value - min < max - x.value ? -1 : 1
  const range = xBounds(viewport(), charWidth.value)
  facingLeft.value = direction < 0
  const left = surface
  x.value = clamp(x.value + direction * charWidth.value * 0.6, range[0], range[1])
  startFall(left.el)
}

function scheduleBlink() {
  setTimer('blink', randomBetween(2500, 6000), () => {
    if (motionAllowed() && visible() && pose.value === 'idle') {
      blinking.value = true
      setTimer('blink-end', 140, () => {
        blinking.value = false
      })
    }
    scheduleBlink()
  })
}

/** 任何交互或宿主事件都会叫醒小映并重置打盹计时。 */
function markActivity() {
  if (dozing.value) {
    dozing.value = false
    scheduleBehavior()
  }
  setTimer('doze', DOZE_AFTER, () => {
    if (!onGround()) return
    settle()
    dozing.value = true
    clearTimer('behavior')
  })
}

function playTransient(next: Pose, duration: number) {
  if (!onGround()) return
  settle()
  clearTimer('behavior')
  transient.value = next
  setTimer('transient', duration, () => {
    transient.value = null
    scheduleBehavior()
  })
}

/** 按当前活动范围计算落点；surfaces 模式在这里查询一次可站元素。 */
function landing(exclude: Element | null = null): Landing<DomSurface> {
  const view = viewport()
  const boxes =
    roam() === 'surfaces'
      ? querySurfaces(rootEl.value, view, charHeight.value, hostState?.panelRect ?? null).filter(
          box => box.el !== exclude,
        )
      : []
  return computeLanding(roam(), boxes, { x: x.value, y: y.value }, view, size())
}

/**
 * 从当前位置开始下落。
 *
 * free 模式没有重力，原地停下；减少动态效果或页面不可见时直接瞬移到落点。
 */
function startFall(exclude: Element | null = null) {
  detachSurface()
  if (roam() === 'free') {
    const view = freeBounds(viewport(), ...sizePair())
    x.value = clamp(x.value, ...view.x)
    y.value = clamp(y.value, ...view.y)
    land(false)
    return
  }
  fallTarget = landing(exclude)
  if (!motionAllowed() || !visible() || y.value >= fallTarget.y) {
    land(false)
    return
  }
  motion.value = 'fall'
  velocity = 0
  bounced = false
  ensureLoop()
}

function land(animated: boolean) {
  velocity = 0
  rising.value = false
  sink.value = 0
  const target = fallTarget
  fallTarget = null
  if (roam() !== 'free') {
    if (target?.surface) attachSurface(target.surface)
    y.value = target ? target.y : ground()
    if (!target) surface = null
  }
  if (animated) {
    motion.value = 'sit'
    setTimer('sit', SIT_DURATION, () => {
      if (motion.value === 'sit') motion.value = 'idle'
      scheduleBehavior()
    })
  } else {
    motion.value = 'idle'
    scheduleBehavior()
  }
  if (saveOnLand) {
    saveOnLand = false
    requestSave()
  }
  queueAnchor()
  const delay = droppedByUser ? DROP_CLEAR_DELAY : 0
  droppedByUser = false
  scheduleClearance(animated ? Math.max(delay, SIT_DURATION + 50) : delay)
}

/** 站上元素后开始监听可能让它移动或消失的变化。 */
function attachSurface(next: DomSurface) {
  detachSurface()
  surface = next
  if (!visible()) return
  window.addEventListener('scroll', onSurfaceScroll, { capture: true, passive: true })
  if (typeof MutationObserver !== 'undefined') {
    surfaceObserver = new MutationObserver(records => {
      // 小映自己走路时每帧改 transform，这类变化不影响脚下元素。
      if (records.every(record => rootEl.value?.contains(record.target))) return
      if (!timers.has('surface')) setTimer('surface', SURFACE_CHECK_INTERVAL, checkSurface)
    })
    surfaceObserver.observe(document.body, { subtree: true, childList: true, attributes: true })
  }
  syncSurfacePoll()
}

/**
 * 站立时的低频复查定时器，每 500ms 一拍。
 *
 * - 站在元素上时每拍校验一次脚下元素：只靠 CSS 动画或过渡移动的元素既不触发滚动也不产生
 *   DOM 变化，观察器发现不了。
 * - 每 4 拍（约 2 秒）复查一次是否挡住可点击控件：悬浮按钮这类控件可能在页面数据加载后
 *   才出现，晚于落地时那一次检查。
 *
 * 只在拖拽中或页面不可见时停掉。不允许动画（减少动态效果）时仍然复查：校验脚下元素只是
 * 跟随位置，发现挡住控件时直接瞬移到空位，不播走路，否则她会一直挡着悬浮按钮。
 */
function syncSurfacePoll() {
  const wanted = ready.value && !disposed && visible() && motion.value !== 'drag'
  if (wanted && !surfacePoll) surfacePoll = window.setInterval(onStandPoll, SURFACE_CHECK_INTERVAL)
  if (!wanted && surfacePoll) {
    window.clearInterval(surfacePoll)
    surfacePoll = 0
  }
}

function onStandPoll() {
  standPollTicks += 1
  if (surface && surfaceObserver) checkSurface()
  // 用户刚放下时等它自己的延迟检查，复查不抢先。
  if (standPollTicks % CLEARANCE_POLL_EVERY === 0 && !timers.has('clearance')) checkClearance()
}

function detachSurface() {
  surface = null
  pauseSurfaceWatch()
}

function pauseSurfaceWatch() {
  window.removeEventListener('scroll', onSurfaceScroll, { capture: true })
  surfaceObserver?.disconnect()
  surfaceObserver = null
  syncSurfacePoll()
  clearTimer('surface')
  if (surfaceFrame) window.cancelAnimationFrame(surfaceFrame)
  surfaceFrame = 0
}

/** 滚动时元素位置每帧都可能变化，按帧合并校验，只读一个元素的位置。 */
function onSurfaceScroll() {
  if (surfaceFrame) return
  surfaceFrame = window.requestAnimationFrame(() => {
    surfaceFrame = 0
    checkSurface()
  })
}

/** 重新校验脚下的元素：跟着它移动，或在它消失、缩小、滚出视口时下落。 */
function checkSurface() {
  if (!surface || !onGround()) return
  const current = surface
  const box = measureSurface(current.el)
  const result = checkSupport(
    current,
    box && surfaceVisible(current.el) ? box : null,
    x.value + charWidth.value / 2,
    viewport(),
    charHeight.value,
    hostState?.panelRect ?? null,
  )
  if (result.kind === 'fall') {
    settle()
    startFall(current.el)
    return
  }
  if (!box) return
  surface = { ...box, el: current.el }
  x.value += result.dx
  if (walkTarget) walkTarget.x += result.dx
  if (motion.value !== 'peek') y.value = result.y
  queueAnchor()
}

/**
 * 不在可点击控件上方停留。
 *
 * 只在落地、站定和窗口尺寸变化后调用，拖拽中不做。挡住时在当前站立面上走到最近的不遮挡位置；
 * 整个面都会挡住时，站在元素上就跳下去换一个面。首次出现或不允许动画时直接放过去。
 */
function checkClearance() {
  if (disposed || !ready.value || motion.value !== 'idle' || !visible()) return
  const instant = initialPlacement || !motionAllowed()
  initialPlacement = false
  // 一次判断只读一遍控件矩形，候选位置的试探都复用它。
  const controls = collectControls(rootEl.value, viewport(), surface?.el ?? null)
  const coversAt = (left: number) => coversAny({ ...currentRect(), x: left }, controls)
  if (!coversAt(x.value)) return
  const span = panelSpan()
  const target = pickClearX(x.value, bounds(), left => !isBlocked(left, span) && !coversAt(left), charWidth.value / 2)
  settle()
  clearTimer('behavior')
  if (target === null) {
    if (surface) stepOffEdge()
    else scheduleBehavior()
    return
  }
  if (instant) {
    facingLeft.value = target < x.value
    x.value = target
    queueAnchor()
    scheduleBehavior()
    return
  }
  startWalk(target)
}

function scheduleClearance(delay: number) {
  setTimer('clearance', delay, checkClearance)
}

/**
 * 请求把落脚点写回 `pet.storage`。
 *
 * 只在三种情况下写服务端：用户拖拽放下、活动范围改变（都在随后落地时写）和页面变为隐藏。
 * 散步、自己落地和避让控件都不写。前两种 30 秒内最多写一次，期间的变化推迟到间隔结束再写；
 * 页面隐藏时立即写，因为这可能是最后的机会。
 */
function requestSave(immediate = false) {
  if (immediate) {
    clearTimer('save')
    writePosition()
    return
  }
  const wait = lastSaveAt + SAVE_THROTTLE - Date.now()
  if (wait <= 0) writePosition()
  else if (!timers.has('save')) setTimer('save', wait, writePosition)
}

function writePosition() {
  if (!ready.value || motion.value === 'drag' || motion.value === 'fall') return
  const view = viewport()
  const xRatio = Math.round(xToRatio(x.value, xBounds(view, charWidth.value)) * 1000) / 1000
  const yRatio = Math.round(xToRatio(y.value, [view.safeArea.top, ground()]) * 1000) / 1000
  const value: StoredPosition = { roam: roam(), xRatio, yRatio }
  const key = JSON.stringify(value)
  if (key === lastSaved) return
  lastSaved = key
  lastSaveAt = Date.now()
  props.pet?.storage?.set?.(value)?.catch?.(() => console.warn('[AgentPets] position not saved'))
}

/** 视口、面板或尺寸变化后把角色放回合法位置。 */
function relayout() {
  if (motion.value === 'drag' || motion.value === 'fall') {
    x.value = clamp(x.value, 0, Math.max(0, viewport().width - charWidth.value))
    y.value = clamp(y.value, 0, ground())
    queueAnchor()
    return
  }
  if (roam() === 'free') {
    const view = freeBounds(viewport(), ...sizePair())
    x.value = clamp(x.value, ...view.x)
    y.value = clamp(y.value, ...view.y)
    queueAnchor()
    return
  }
  if (surface) {
    checkSurface()
    if (!surface) return
  } else y.value = ground()
  const range = bounds()
  x.value = clamp(x.value, range[0], range[1])
  const span = panelSpan()
  if (isBlocked(x.value, span)) {
    const escaped = escapeSpan(x.value, span, range)
    settle()
    if (motionAllowed() && visible() && Math.abs(escaped - x.value) > 1) startWalk(escaped)
    else x.value = escaped
  }
  queueAnchor()
}

/** 设置变化（含设置页实时预览）；活动范围改变时按新模式重新落位。 */
function applySettings(value: unknown) {
  const before = settings.value.roam
  settings.value = normalizeSettings(value)
  if (ready.value && settings.value.roam !== before && motion.value !== 'drag') {
    settle()
    saveOnLand = true
    startFall()
    return
  }
  relayout()
}

function onHostState(state: AgentHostState) {
  const before = hostState
  hostState = state
  available.value = state.available
  const resized =
    !!before &&
    (before.viewport.width !== state.viewport.width ||
      before.viewport.height !== state.viewport.height ||
      before.viewport.keyboardInset !== state.viewport.keyboardInset ||
      before.isMobile !== state.isMobile)
  isMobile.value = state.isMobile
  const nextSustained = phasePose(state.phase)
  if (nextSustained !== sustained.value) {
    sustained.value = nextSustained
    if (nextSustained) {
      settle()
      clearTimer('behavior')
      markActivity()
    } else scheduleBehavior()
  }
  if (!state.motionAllowed && before?.motionAllowed !== false) freezeMotion()
  if (state.motionAllowed && before?.motionAllowed === false) scheduleBehavior()
  syncVisibility()
  syncSurfacePoll()
  if (resized) scheduleClearance(RESIZE_CLEAR_DELAY)
  if (ready.value) relayout()
}

/** 减少动态效果时立刻停在落点，不播下落和散步。 */
function freezeMotion() {
  stopLoop()
  clearTimer('behavior')
  clearTimer('peek')
  walkTarget = null
  walkPhase.value = 0
  pendingPeek = false
  pendingStepOff = false
  sink.value = 0
  peekTarget = 0
  blinking.value = false
  if (motion.value === 'fall') land(false)
  else if (motion.value === 'walk' || motion.value === 'peek') {
    motion.value = 'idle'
    queueAnchor()
  }
}

/** 页面不可见时停掉 rAF、行为计时与元素观察；回到可见后继续并重新校验脚下。 */
function syncVisibility() {
  if (!visible()) {
    stopLoop()
    clearTimer('behavior')
    pauseSurfaceWatch()
    if (motion.value === 'fall') land(false)
    requestSave(true)
    return
  }
  if (surface && !surfaceObserver) {
    attachSurface(surface)
    checkSurface()
  }
  ensureLoop()
  if (motion.value === 'idle' && !timers.has('behavior')) scheduleBehavior()
}

function onHostEvent(event: AgentHostEvent) {
  markActivity()
  const next = eventPose(event.name)
  if (next) playTransient(next.pose, next.duration)
}

function onSettingsEvent(event: AgentHostEvent) {
  if (props.pluginId && event.source !== props.pluginId) return
  applySettings(event.data)
}

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0 || press) return
  markActivity()
  press = {
    id: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    offsetX: event.clientX - x.value,
    offsetY: event.clientY - (y.value + sink.value),
    dragging: false,
  }
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerCancel)
}

function onPointerMove(event: PointerEvent) {
  if (!press || event.pointerId !== press.id) return
  if (!press.dragging) {
    if (Math.hypot(event.clientX - press.startX, event.clientY - press.startY) < DRAG_THRESHOLD) return
    press.dragging = true
    settle()
    stopLoop()
    detachSurface()
    clearTimer('behavior')
    clearTimer('sit')
    clearTimer('clearance')
    transient.value = null
    sink.value = 0
    peekTarget = 0
    velocity = 0
    fallTarget = null
    motion.value = 'drag'
    syncSurfacePoll()
    props.pet?.setInteracting?.(true)
  }
  event.preventDefault()
  const view = viewport()
  x.value = clamp(event.clientX - press.offsetX, 0, Math.max(0, view.width - charWidth.value))
  y.value = clamp(event.clientY - press.offsetY, 0, ground())
  facingLeft.value = false
  queueAnchor()
}

function releasePointer() {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerCancel)
}

function finishDrag() {
  props.pet?.setInteracting?.(false)
  droppedByUser = true
  saveOnLand = true
  x.value = clamp(x.value, ...xBounds(viewport(), charWidth.value))
  // 先离开拖拽状态，站立复查随之恢复。
  motion.value = 'idle'
  syncSurfacePoll()
  startFall()
}

function onPointerUp(event: PointerEvent) {
  if (!press || event.pointerId !== press.id) return
  const dragged = press.dragging
  press = null
  releasePointer()
  if (!dragged) return
  // 拖拽结束后浏览器仍会派发一次 click，同一轮事件内忽略它，避免松手即打开面板。
  suppressClick = true
  window.setTimeout(() => {
    suppressClick = false
  }, 0)
  finishDrag()
}

function onPointerCancel(event: PointerEvent) {
  if (!press || event.pointerId !== press.id) return
  const dragged = press.dragging
  press = null
  releasePointer()
  if (dragged) finishDrag()
}

/** 鼠标点击与键盘 Enter/Space 都经按钮的 click 打开原生面板。 */
function onActivate() {
  if (suppressClick) {
    suppressClick = false
    return
  }
  markActivity()
  props.agent?.open?.()
}

/** 读取上次的落脚点；按当前活动范围重新落位由调用方完成。 */
async function readStoredPosition(): Promise<StoredPosition | null> {
  try {
    const stored = await props.pet?.storage?.get?.<StoredPosition>()
    if (stored && typeof stored.xRatio === 'number' && Number.isFinite(stored.xRatio)) return stored
  } catch {
    console.warn('[AgentPets] position unavailable')
  }
  return null
}

/** 按记住的比例放回原处，再按当前活动范围瞬移落位（启动时不播下落）。 */
function restorePosition(stored: StoredPosition | null) {
  const view = viewport()
  x.value = ratioToX(stored?.xRatio ?? DEFAULT_RATIO, xBounds(view, charWidth.value))
  const yRatio = typeof stored?.yRatio === 'number' && Number.isFinite(stored.yRatio) ? stored.yRatio : 1
  y.value = ratioToX(yRatio, [view.safeArea.top, ground()])
  if (roam() === 'free') {
    land(false)
    return
  }
  // 站在元素上时上边缘就是脚底，从略高处查询才能落回同一个元素。
  y.value = Math.max(view.safeArea.top, y.value - 4)
  fallTarget = landing()
  land(false)
}

function onVisibilityChange() {
  documentVisible = document.visibilityState !== 'hidden'
  syncVisibility()
}

function onWindowResize() {
  if (!hostState || surface) relayout()
  if (!hostState) scheduleClearance(RESIZE_CLEAR_DELAY)
}

onMounted(async () => {
  const agent = props.agent
  if (agent?.subscribe) cleanups.push(agent.subscribe(onHostState))
  if (agent?.on) {
    for (const name of [
      'agent.panel.open',
      'agent.panel.close',
      'agent.thinking.start',
      'agent.thinking.end',
      'agent.tool.start',
      'agent.tool.end',
      'agent.awaiting',
      'agent.done',
      'agent.error',
      'agent.preview',
      'agent.bubble',
    ]) {
      cleanups.push(agent.on(name, onHostEvent))
    }
    cleanups.push(agent.on(SETTINGS_EVENT, onSettingsEvent))
  }
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('resize', onWindowResize)
  cleanups.push(() => document.removeEventListener('visibilitychange', onVisibilityChange))
  cleanups.push(() => window.removeEventListener('resize', onWindowResize))

  const [loaded, stored] = await Promise.all([loadSettings(props.api, props.pluginId), readStoredPosition()])
  if (disposed) return
  settings.value = loaded
  restorePosition(stored)
  ready.value = true
  syncSurfacePoll()
  reportAnchor()
  scheduleBlink()
  markActivity()
  scheduleBehavior()
})

onBeforeUnmount(() => {
  // 还有推迟的保存时在卸载前写掉（例如切换形象）。
  if (timers.has('save')) writePosition()
  disposed = true
  stopLoop()
  pauseSurfaceWatch()
  if (anchorFrame) window.cancelAnimationFrame(anchorFrame)
  anchorFrame = 0
  for (const id of timers.values()) window.clearTimeout(id)
  timers.clear()
  releasePointer()
  if (press?.dragging) props.pet?.setInteracting?.(false)
  press = null
  for (const cleanup of cleanups.splice(0)) cleanup()
  props.pet?.setBubbleAnchor?.(null)
})
</script>

<template>
  <div ref="rootEl" class="agent-pet-ying" :data-pose="pose" :data-motion="motion" :data-roam="settings.roam">
    <button
      v-show="ready"
      type="button"
      class="agent-pet-ying__character"
      :style="buttonStyle"
      :aria-label="label"
      @pointerdown="onPointerDown"
      @click="onActivate"
      @dragstart.prevent
    >
      <span
        class="agent-pet-ying__frames"
        :class="{ 'agent-pet-ying__frames--flip': facingLeft, 'agent-pet-ying__frames--pending': !displayed }"
        :data-frame="displayed ?? undefined"
      >
        <img
          v-for="name in POSES"
          :key="name"
          class="agent-pet-ying__frame"
          :class="{ 'agent-pet-ying__frame--visible': name === displayed }"
          :src="frameSrc[name]"
          :data-pose="name"
          alt=""
          draggable="false"
          @load="onFrameLoad(name, $event)"
          @error="onFrameError(name)"
        />
      </span>
    </button>
  </div>
</template>

<style scoped>
.agent-pet-ying {
  position: fixed;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.agent-pet-ying__character {
  position: absolute;
  top: 0;
  left: 0;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: grab;
  pointer-events: auto;
  touch-action: none;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
  will-change: transform;
}

.agent-pet-ying[data-motion='drag'] .agent-pet-ying__character {
  cursor: grabbing;
}

.agent-pet-ying__character:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary, 145 85 253));
  outline-offset: 2px;
  border-radius: 12px;
}

/* 翻转作用在容器上，所有帧表现一致；下沉的 clip-path 在按钮上。 */
.agent-pet-ying__frames {
  position: absolute;
  inset: 0;
  display: block;
  pointer-events: none;
}

.agent-pet-ying__frames--pending {
  visibility: hidden;
}

.agent-pet-ying__frames--flip {
  transform: scaleX(-1);
}

/* 不可见帧用 opacity 0 而不是 display none，保持已解码，切换时不用等待。 */
.agent-pet-ying__frame {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: bottom center;
  opacity: 0;
  pointer-events: none;
}

.agent-pet-ying__frame--visible {
  opacity: 1;
}
</style>
