<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useSlots, watch } from 'vue'
import { withLoadTimeout } from '@/loading'
import { onEditorPresence } from '@/editor/presence'
import { PausableTimers } from './timers'
import { builtinDefaultCalibration, loadBuiltinCalibration, YING_PACK } from '@/sprites/builtinCalibration'
import {
  calibrationEye,
  calibrationLayout,
  calibrationPoint,
  LANDMARKS,
  mirrorFace,
  parseCalibration,
  type Calibration,
} from '@/sprites/calibration'
import { PACK_UPDATED_EVENT } from '@/sprites/mappings'
import type { SpritePack } from '@/sprites/schema'

import type { AgentHostEvent, AgentHostState, AgentPetContext, AgentRect, MoviePilotAgentHost, PluginApi } from '@/host'
import {
  avoidPanel,
  blockedSpan,
  checkSupport,
  clamp,
  computeLanding,
  effectiveScale,
  floorLine,
  hopVelocity,
  intersectionArea,
  nearestEdge,
  pickClearX,
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
import {
  dropPeekEdge,
  isPeekEdge,
  peekHome,
  peekLayout,
  peekPanelShift,
  PEEK_TUCK,
  PEEK_RISE_SECONDS,
  PEEK_TILT_SECONDS,
  type PeekEdge,
  type PeekEye,
} from '@/stage/peek'
import { eventPose, frameUrl, phasePose, POSES, resolvePose, walkFrame, type Motion, type Pose } from '@/stage/poses'
import { DEFAULT_SETTINGS, loadSettings, normalizeSettings, SETTINGS_EVENT, type YingSettings } from '@/stage/settings'
import { normalizePeekAngles } from '@/stage/peek'
import {
  coversControlAt,
  bottomFixedFloor,
  BOTTOM_FLOOR_GAP,
  measureSurface,
  querySurfaces,
  surfacesNear,
  surfaceVisible,
  type DomSurface,
} from '@/stage/surfaces'

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
    /** 使用自定义外观时的名称与格子宽高比。 */
    characterName?: string
    aspectRatio?: number
    /** undefined 使用小映眼位，null 表示素材尚未校准。 */
    peekEye?: PeekEye | null
    /** 详情页局部预览边界；缺省仍在整个页面活动。 */
    previewRoot?: HTMLElement | null
    /** 预览草稿直接传入，不读取或写入已保存设置。 */
    settingsOverride?: YingSettings
    /** 仅预览按窗口容纳角色，不更改活动设置的大小。 */
    previewMaxSize?: { width: number; height: number }
    previewPose?: Pose
    previewPeekEdge?: PeekEdge | null
    /** 仅局部贴边试览使用；正式舞台读取当前 Pet 保存的角度。 */
    previewPeekAngle?: number
    calibrationOverride?: Calibration
    showCalibration?: boolean
  }>(),
  {
    agent: null,
    pet: null,
    api: null,
    pluginId: '',
    sourcePluginId: '',
    characterName: '小映',
    aspectRatio: 0,
    previewRoot: null,
  },
)
const emit = defineEmits<{ 'pack-ready': [SpritePack]; 'load-state': ['loading' | 'ready' | 'error'] }>()
const ownFrames = !useSlots().default

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
const PEEK_SPEED = 1.8
/** 跳到别的面时顶点比两端较高者再高出的身高比例。 */
const HOP_LIFT_RATIO = 0.5
/** 当前面找不到空位时，最多再尝试的其他站立面数（含底边）。 */
const MAX_OTHER_SURFACES = 3
/** 在其他站立面上最多试探的候选位置数。 */
const OTHER_SURFACE_CANDIDATES = 4
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
  peekEdge?: PeekEdge
}

const rootEl = ref<HTMLElement | null>(null)
const settings = ref<YingSettings>({ ...DEFAULT_SETTINGS })
const imageAspect = ref(198 / 240)
const ownCalibration = ref(builtinDefaultCalibration('ying'))
const effectiveCalibration = computed(() => parseCalibration(props.calibrationOverride ?? ownCalibration.value))
const ownLayout = computed(() => calibrationLayout(effectiveCalibration.value, imageAspect.value))
const aspect = computed(() => (props.aspectRatio > 0 ? props.aspectRatio : ownLayout.value.aspectRatio))
const ownGuides = computed(() =>
  ['eye', ...LANDMARKS].flatMap(key => {
    const point = calibrationPoint(effectiveCalibration.value, key as 'eye' | (typeof LANDMARKS)[number])
    return point ? [{ key, ...point }] : []
  }),
)
const x = ref(0)
const y = ref(0)
const peekProgress = ref(0)
const peekRevealing = ref(false)
const peekTiltProgress = ref(0)
const peekEdge = ref<PeekEdge | null>(null)
const peekPhase = ref<'tuck' | 'pause' | 'tilt' | 'look' | 'leave' | null>(null)
const layoutRevision = ref(0)
const facingLeft = ref(false)
const ownEye = computed(() => {
  const face = calibrationEye(effectiveCalibration.value)
  return facingLeft.value ? mirrorFace(face) : face
})
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
const animationActive = ref(false)

let hostState: AgentHostState | null = null
let bottomFloor: number | null = null
let documentVisible = typeof document === 'undefined' || document.visibilityState !== 'hidden'
let editorPaused = false
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
let peekPinned = false
/** 无处可站时在底边一侧下沉躲开控件；与随机探头不同，没有结束计时，由复查决定何时站起来。 */
let sheltering = false
/** 到达目的地后进入稳定眼位，不再逐次加深。 */
let pendingShelter = false
/** 跳向另一个面时的水平速度与落点 x。 */
let hopVx = 0
let hopTargetX: number | null = null
let fixedPosition: { xRatio: number; yRatio: number } | null = null
let lastSaved = ''
let lastSaveAt = 0
/** 下一次落地后保存落脚点：用户拖拽放下或活动范围改变时置位。 */
let saveOnLand = false
let suppressClick = false
/** 散步到底边一侧后接着探头。 */
let pendingPeek: PeekEdge | null = null
/** 走到元素边缘后跳下去。 */
let pendingStepOff = false
/** 当前站着的页面元素；站在底边或自由停放时为 null。 */
let surface: DomSurface | null = null
/** 手动选中的站立面优先于控件避让，离开或支撑失效后解除。 */
let manualSurface: Element | null = null
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

const timers = new PausableTimers()
const cleanups: Array<() => void> = []
const startup = new AbortController()
let settingsRevision = 0

const charHeight = computed(() => {
  const height = BASE_HEIGHT * effectiveScale(settings.value.scale, isMobile.value)
  const fit = props.previewRoot ? props.previewMaxSize : undefined
  return fit ? Math.min(height, Math.max(1, fit.height), Math.max(1, fit.width) / aspect.value) : height
})
const charWidth = computed(() => charHeight.value * aspect.value)
const previewEdge = computed(() => (props.previewRoot ? (props.previewPeekEdge ?? null) : null))
const activePeekEdge = computed(() => previewEdge.value ?? peekEdge.value)
const settledPeek = computed(
  () => !previewEdge.value && motion.value === 'peek' && peekPhase.value === 'look' && peekProgress.value === 1,
)
const pose = computed<Pose>(() =>
  activePeekEdge.value
    ? settledPeek.value && animationActive.value && blinking.value
      ? 'blink'
      : 'alert'
    : props.previewRoot && props.previewPose
      ? props.previewPose
      : resolvePose({
          motion: motion.value,
          walkPhase: walkPhase.value,
          transient: transient.value,
          sustained: sustained.value,
          dozing: dozing.value,
          blinking: blinking.value,
          rising: rising.value,
        }),
)
const label = computed(() =>
  available.value ? `打开助手（${props.characterName}）` : `${props.characterName}（助手未启用）`,
)
watch(
  () => props.aspectRatio,
  () => {
    if (ready.value) relayout()
  },
)

watch([charHeight, charWidth], () => {
  if (ready.value && props.previewRoot) relayout()
})
watch(
  [() => props.peekEye, previewEdge, ownEye],
  () => {
    if (ready.value) relayout()
  },
  { deep: true },
)
watch(
  effectiveCalibration,
  () => {
    if (ready.value && ownFrames) relayout()
  },
  { deep: true },
)

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
      imageAspect.value = image.naturalWidth / image.naturalHeight
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

const drawing = computed(() => {
  // 宿主快照不是响应式对象，布局事件需要使裁切边界重新计算。
  void layoutRevision.value
  const edge = activePeekEdge.value
  const view = peekViewport()
  const position = previewEdge.value
    ? peekHome({ x: x.value, y: y.value }, view, size(), previewEdge.value)
    : { x: x.value, y: y.value }
  const eye = props.peekEye === undefined ? ownEye.value : props.peekEye
  return peekLayout(
    position,
    size(),
    view,
    edge,
    previewEdge.value ? 1 : peekProgress.value,
    eye,
    !!previewEdge.value || peekRevealing.value,
    previewEdge.value ? 1 : peekTiltProgress.value,
    previewEdge.value && props.previewPeekAngle !== undefined
      ? props.previewPeekAngle
      : normalizePeekAngles(settings.value.peek_angles)[activePeekEdge.value ?? 'bottom'],
  )
})
const buttonStyle = computed(() => ({
  width: `${drawing.value.hit.width}px`,
  height: `${drawing.value.hit.height}px`,
  transform: `translate3d(${drawing.value.hit.x}px, ${drawing.value.hit.y}px, 0)`,
}))
const clipStyle = computed(() => ({
  left: `${drawing.value.visible.x - drawing.value.hit.x}px`,
  top: `${drawing.value.visible.y - drawing.value.hit.y}px`,
  width: `${drawing.value.visible.width}px`,
  height: `${drawing.value.visible.height}px`,
}))
const artworkStyle = computed(() => ({
  left: `${drawing.value.artwork.x - drawing.value.visible.x}px`,
  top: `${drawing.value.artwork.y - drawing.value.visible.y}px`,
  width: `${drawing.value.artwork.width}px`,
  height: `${drawing.value.artwork.height}px`,
  transform: `rotate(${drawing.value.artwork.rotation}deg)`,
}))

function setTimer(name: string, delay: number, callback: () => void) {
  timers.set(name, delay, callback)
}

function clearTimer(name: string) {
  timers.clear(name)
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

function fixed(): boolean {
  return settings.value.movement === 'fixed'
}

/** 只在用户放置或切入固定模式时更新，临时视口收缩不能改写这个落点。 */
function rememberFixedPosition() {
  const view = freeBounds(viewport(), ...sizePair())
  fixedPosition = { xRatio: xToRatio(x.value, view.x), yRatio: xToRatio(y.value, view.y) }
}

function placeFixed() {
  const view = freeBounds(viewport(), ...sizePair())
  x.value = ratioToX(fixedPosition?.xRatio ?? DEFAULT_RATIO, view.x)
  y.value = ratioToX(fixedPosition?.yRatio ?? 1, view.y)
  const point = avoidPanel({ x: x.value, y: y.value }, hostState?.panelRect ?? null, viewport(), size())
  x.value = point.x
  y.value = point.y
  queueAnchor()
}

function resetMotion() {
  stopLoop()
  for (const name of ['behavior', 'peek', 'peek-pause', 'landing-peek', 'sit', 'clearance']) clearTimer(name)
  walkTarget = null
  walkPhase.value = 0
  fallTarget = null
  hopVx = 0
  hopTargetX = null
  velocity = 0
  rising.value = false
  pendingPeek = null
  pendingStepOff = false
  pendingShelter = false
  sheltering = false
  peekProgress.value = 0
  peekTiltProgress.value = 0
  peekEdge.value = null
  peekPhase.value = null
  peekPinned = false
  peekTarget = 0
  motion.value = 'idle'
  detachSurface()
}

function pinHere() {
  resetMotion()
  rememberFixedPosition()
  placeFixed()
  if (saveOnLand) {
    saveOnLand = false
    requestSave()
  }
}

function roam(): RoamMode {
  return settings.value.roam
}

function viewport() {
  const view = readViewport(hostState, !props.previewRoot)
  if (bottomFloor === null || props.previewRoot) return view
  return {
    ...view,
    safeArea: { ...view.safeArea, bottom: Math.max(view.safeArea.bottom, view.height - bottomFloor) },
  }
}

/** 只在布局变化和低频避让检查中测量固定底栏。 */
function refreshBottomFloor(): boolean {
  const next = !props.previewRoot ? bottomFixedFloor(rootEl.value, readViewport(hostState)) : null
  const changed = next !== bottomFloor
  bottomFloor = next
  return changed
}

/** 正常站立保留底栏间隔；偷窥直接贴住底栏上沿。 */
function peekViewport() {
  const view = readViewport(hostState, !props.previewRoot)
  if (bottomFloor === null || props.previewRoot || bottomFloor >= floorLine(view)) return view
  return {
    ...view,
    safeArea: {
      ...view.safeArea,
      bottom: Math.max(view.safeArea.bottom, view.height - bottomFloor - BOTTOM_FLOOR_GAP),
    },
  }
}

function placePeek() {
  if (!peekEdge.value) return
  const point = peekHome({ x: x.value, y: y.value }, peekViewport(), size(), peekEdge.value)
  x.value = point.x
  y.value = point.y
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
  return !editorPaused && documentVisible && (hostState?.pageVisible ?? true)
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
  return drawing.value.visible
}

function reportAnchor() {
  anchorFrame = 0
  if (disposed || !ready.value || editorPaused) return
  const rect = currentRect()
  if (sameRect(rect, lastAnchor)) return
  lastAnchor = rect
  props.pet?.setBubbleAnchor?.(rect)
}

/** 每帧最多上报一次锚点；动画循环内直接上报，其余变化合并到下一帧。 */
function queueAnchor() {
  if (editorPaused || anchorFrame || rafId) return
  anchorFrame = window.requestAnimationFrame(reportAnchor)
}

function needsLoop(): boolean {
  if (motion.value === 'walk' || motion.value === 'fall') return true
  return motion.value === 'peek' && (peekPhase.value === 'tilt' || peekProgress.value !== peekTarget)
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
  clearPanelOverlap()
  reportAnchor()
  if (!rafId && needsLoop() && visible()) rafId = window.requestAnimationFrame(tick)
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
  const range = freeBounds(viewport(), ...sizePair())
  const target = clamp(fallTarget?.y ?? range.y[1], ...range.y)
  if (fallTarget && target !== fallTarget.y) fallTarget = { y: target, surface: null }
  if (hopTargetX !== null) hopTargetX = clamp(hopTargetX, ...range.x)
  velocity += GRAVITY * dt
  y.value = clamp(y.value + velocity * dt, ...range.y)
  x.value = clamp(x.value + hopVx * dt, ...range.x)
  rising.value = velocity < 0
  // 跳上更高的面时起点在落点下方，上升段不能判定着地。
  if (velocity < 0 || y.value < target) return
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
  if (peekPhase.value === 'tilt') {
    peekTiltProgress.value = Math.min(1, peekTiltProgress.value + dt / PEEK_TILT_SECONDS)
    if (peekTiltProgress.value === 1) {
      peekPhase.value = 'look'
      peekTarget = 1
    }
    return
  }
  const step = (peekPhase.value === 'look' ? (PEEK_TUCK - 1) / PEEK_RISE_SECONDS : PEEK_SPEED) * dt
  peekProgress.value =
    peekProgress.value < peekTarget
      ? Math.min(peekTarget, peekProgress.value + step)
      : Math.max(peekTarget, peekProgress.value - step)
  if (peekProgress.value === PEEK_TUCK && peekPhase.value === 'tuck') {
    peekPhase.value = 'pause'
    setTimer('peek-pause', 420, () => {
      if (motion.value !== 'peek' || peekPhase.value !== 'pause') return
      peekRevealing.value = true
      // 底边先在完全隐藏的位置完成倾斜与横向靠角，再只沿竖直方向探出。
      peekPhase.value = peekEdge.value === 'bottom' ? 'tilt' : 'look'
      peekTarget = peekEdge.value === 'bottom' ? PEEK_TUCK : 1
      ensureLoop()
    })
  }
  if (peekProgress.value === 0 && peekTarget === 0) {
    const fromSide = peekEdge.value === 'left' || peekEdge.value === 'right'
    peekEdge.value = null
    peekPhase.value = null
    peekPinned = false
    motion.value = 'idle'
    y.value = onFloor() ? ground() : y.value
    if (fromSide && roam() !== 'free' && !onFloor()) startFall()
    else scheduleBehavior()
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
  pendingPeek = null
  pendingStepOff = false
  if (pendingShelter) {
    pendingShelter = false
    beginShelter(false)
    return
  }
  scheduleClearance(0)
  if (stepOff && surface) stepOffEdge()
  else if (peek) beginPeek(peek)
  else scheduleBehavior()
}

function beginPeek(edge: PeekEdge = 'bottom', pinned = false, instant = false) {
  if (fixed()) return
  for (const name of ['behavior', 'peek', 'peek-pause', 'landing-peek', 'sit', 'clearance']) clearTimer(name)
  detachSurface()
  peekEdge.value = edge
  peekPinned = pinned
  x.value = nearestEdge(x.value, bounds())
  placePeek()
  facingLeft.value = x.value > (bounds()[0] + bounds()[1]) / 2
  motion.value = 'peek'
  const still = instant || !motionAllowed()
  peekRevealing.value = still
  peekTiltProgress.value = still ? 1 : 0
  peekPhase.value = still ? 'look' : 'tuck'
  peekProgress.value = still ? 1 : 0
  peekTarget = still ? 1 : PEEK_TUCK
  if (still) queueAnchor()
  else ensureLoop()
  schedulePeekExit()
  syncSurfacePoll()
}

function schedulePeekExit() {
  clearTimer('peek')
  if (!peekPinned && !sheltering && motionAllowed()) setTimer('peek', randomBetween(5000, 8000), endPeek)
}

function endPeek() {
  clearTimer('peek')
  clearTimer('peek-pause')
  if (motion.value !== 'peek') return
  peekPhase.value = 'leave'
  peekTarget = 0
  if (!motionAllowed()) {
    peekProgress.value = 0
    stepPeek(0)
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
  if (motion.value === 'peek' && !sheltering) {
    endPeek()
  }
  pendingPeek = null
  pendingStepOff = false
  // 打断后不再执行走向底边途中的下沉，否则会在别处的落点沉下去，交给下一次复查重新判断。
  pendingShelter = false
}

function calm(): boolean {
  return (
    motion.value === 'idle' &&
    !sheltering &&
    !transient.value &&
    !sustained.value &&
    !dozing.value &&
    motionAllowed() &&
    visible()
  )
}

/**
 * 空闲行为：底边上偶尔散步或走到下角，从底边或对应侧边探头；元素上偶尔走到边缘跳下去，
 * 自由停放时在视口内慢慢游走。
 */
function scheduleBehavior() {
  clearTimer('behavior')
  if (fixed() || !calm()) return
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
      else pendingPeek = Math.random() < 0.5 ? 'bottom' : side === min ? 'left' : 'right'
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
  const nextX = clamp(x.value + direction * charWidth.value * 0.6, range[0], range[1])
  // 视口限位可能让这一步仍站在原表面上；只有中心真正离开支撑才排除原表面。
  const center = nextX + charWidth.value / 2
  if (center >= left.left && center <= left.right) {
    x.value = nextX
    facingLeft.value = direction > 0
    queueAnchor()
    scheduleBehavior()
    return
  }
  // 主动跳下不能落到避让逻辑必定赶走的位置，否则会在卡片与地面之间循环。
  const target = landing(left.el, 0, { x: nextX, y: y.value })
  const view = viewport()
  if (
    isBlocked(nextX, blockedSpan(hostState?.panelRect ?? null, target.y, charWidth.value, charHeight.value)) ||
    coversControlAt(
      rectAt(nextX, target.y),
      rootEl.value,
      view,
      target.surface?.el ?? null,
      charWidth.value * charHeight.value,
      props.previewRoot,
    )
  ) {
    scheduleBehavior()
    return
  }
  x.value = nextX
  startFall(left.el)
}

function scheduleBlink() {
  setTimer('blink', randomBetween(2500, 6000), () => {
    if (motionAllowed() && visible() && (pose.value === 'idle' || settledPeek.value)) {
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
function landing(
  exclude: Element | null = null,
  dropSnap = 0,
  position = { x: x.value, y: y.value },
): Landing<DomSurface> {
  const view = viewport()
  const boxes =
    roam() === 'surfaces'
      ? querySurfaces(rootEl.value, view, charHeight.value, hostState?.panelRect ?? null, props.previewRoot).filter(
          box => box.el !== exclude,
        )
      : []
  return computeLanding(roam(), boxes, position, view, size(), dropSnap)
}

/**
 * 从当前位置开始下落。
 *
 * free 模式没有重力，原地停下；减少动态效果或页面不可见时直接瞬移到落点。
 */
function startFall(exclude: Element | null = null) {
  clearTimer('landing-peek')
  if (fixed()) {
    pinHere()
    return
  }
  x.value = clamp(x.value, ...xBounds(viewport(), charWidth.value))
  clearTimer('peek')
  clearTimer('peek-pause')
  peekProgress.value = 0
  peekTarget = 0
  peekEdge.value = null
  peekPhase.value = null
  peekPinned = false
  sheltering = false
  detachSurface()
  hopVx = 0
  hopTargetX = null
  if (roam() === 'free') {
    const view = freeBounds(viewport(), ...sizePair())
    x.value = clamp(x.value, ...view.x)
    y.value = clamp(y.value, ...view.y)
    land(false)
    return
  }
  fallTarget = landing(exclude, droppedByUser ? Math.min(24, charHeight.value * 0.2) : 0)
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
  peekProgress.value = 0
  peekTarget = 0
  peekEdge.value = null
  peekPhase.value = null
  peekPinned = false
  sheltering = false
  hopVx = 0
  if (hopTargetX !== null) {
    x.value = hopTargetX
    hopTargetX = null
  }
  const target = fallTarget
  fallTarget = null
  if (roam() !== 'free') {
    if (target?.surface) attachSurface(target.surface)
    y.value = target ? target.y : ground()
    if (!target) surface = null
  }
  if (droppedByUser) manualSurface = surface?.el ?? null
  if (animated) {
    motion.value = 'sit'
    setTimer('sit', SIT_DURATION, () => {
      if (motion.value !== 'sit') return
      motion.value = 'idle'
      scheduleBehavior()
    })
  } else {
    motion.value = 'idle'
    scheduleBehavior()
  }
  // 避让后仍在下落时，把保存责任留给最终落地，不能提前消耗用户拖放标记。
  if (clearPanelOverlap() && !onGround()) return
  if (saveOnLand) {
    saveOnLand = false
    requestSave()
  }
  queueAnchor()
  if (pendingShelter) {
    pendingShelter = false
    clearTimer('sit')
    beginShelter(!animated)
    return
  }
  const delay = animated
    ? Math.max(droppedByUser ? DROP_CLEAR_DELAY : 0, SIT_DURATION + 50)
    : droppedByUser
      ? DROP_CLEAR_DELAY
      : 0
  droppedByUser = false
  scheduleClearance(delay)
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
    surfaceObserver.observe(props.previewRoot ?? document.body, { subtree: true, childList: true, attributes: true })
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
  manualSurface = null
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
  const box = measureSurface(current.el, props.previewRoot)
  const result = checkSupport(
    current,
    box && surfaceVisible(current.el) ? box : null,
    x.value + charWidth.value / 2,
    viewport(),
    charHeight.value,
    hostState?.panelRect ?? null,
    charWidth.value,
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

/** 角色以完整身高站在 (left, top) 时的矩形。 */
function rectAt(left: number, top: number): AgentRect {
  return { x: left, y: top, width: charWidth.value, height: charHeight.value }
}

/**
 * 不在可点击控件上方停留。
 *
 * 只在落地、站定、窗口尺寸变化和站立低频复查时调用，拖拽中不做。挡住时依次兜底：
 * 1. 在当前站立面上走到最近的空位；
 * 2. surfaces 模式换到其他可站且不遮挡的面（含底边），跳过去；free 模式在视口内另找空位；
 * 3. 都没有时退到底边最近的一侧，以稳定眼位偷窥，不继续加深。
 * 首次出现或不允许动画时直接放过去。候选位置与候选面数都有上限，控制单次判断的耗时。
 */
function checkClearance() {
  if (fixed()) {
    if (refreshBottomFloor()) relayout()
    return
  }
  if (disposed || !ready.value || !visible()) return
  if (refreshBottomFloor()) relayout()
  if (sheltering) {
    recheckShelter()
    return
  }
  if (motion.value !== 'idle') return
  // 卡片网格中上一排内容可能压在角色身后，不能因此立刻推翻手动选定的落点。
  if (surface && surface.el === manualSurface) return
  const instant = initialPlacement || !motionAllowed()
  initialPlacement = false
  const view = viewport()
  const body = charWidth.value * charHeight.value
  const covers = (rect: AgentRect, standingOn: Element | null) =>
    coversControlAt(rect, rootEl.value, view, standingOn, body, props.previewRoot)
  const standingOn = surface?.el ?? null
  if (!covers(currentRect(), standingOn)) return
  settle()
  clearTimer('behavior')

  const span = panelSpan()
  const here = pickClearX(
    x.value,
    bounds(),
    left => !isBlocked(left, span) && !covers(rectAt(left, y.value), standingOn),
    charWidth.value / 2,
  )
  if (here !== null) {
    moveTo(here, y.value, surface, instant)
    return
  }
  const elsewhere = roam() === 'free' ? findFreeSpot(covers) : findOtherSurface(covers)
  if (elsewhere) {
    moveTo(elsewhere.x, elsewhere.y, elsewhere.surface, instant)
    return
  }
  goShelter(instant)
}

/** 其他可站面上的空位：按距离由近到远最多试 3 个面（含底边），每个面最多试 4 个位置。 */
function findOtherSurface(
  covers: (rect: AgentRect, standingOn: Element | null) => boolean,
): { x: number; y: number; surface: DomSurface | null } | null {
  if (roam() !== 'surfaces' && !surface) return null
  const view = viewport()
  const options: Array<{ y: number; bounds: [number, number]; surface: DomSurface | null }> = []
  if (surface) options.push({ y: ground(), bounds: xBounds(view, charWidth.value), surface: null })
  if (roam() === 'surfaces') {
    // 用命中测试在她所在的竖线和视口左右各一条竖线上找面，避免在大页面上全页扫描。
    const columns = [x.value + charWidth.value / 2, view.width * 0.25, view.width * 0.75]
    for (const box of surfacesNear(
      rootEl.value,
      view,
      charHeight.value,
      hostState?.panelRect ?? null,
      columns,
      props.previewRoot,
    )) {
      if (box.el === surface?.el) continue
      options.push({ y: box.top - charHeight.value, bounds: surfaceXBounds(box, view, charWidth.value), surface: box })
    }
  }
  const centerX = x.value
  options.sort((a, b) => distanceTo(a, centerX) - distanceTo(b, centerX))
  for (const option of options.slice(0, MAX_OTHER_SURFACES)) {
    const start = clamp(x.value, ...option.bounds)
    const standingOn = option.surface?.el ?? null
    const span = blockedSpan(hostState?.panelRect ?? null, option.y, charWidth.value, charHeight.value)
    const clear = (left: number) => !isBlocked(left, span) && !covers(rectAt(left, option.y), standingOn)
    const left = clear(start)
      ? start
      : pickClearX(start, option.bounds, clear, charWidth.value / 2, OTHER_SURFACE_CANDIDATES)
    if (left !== null) return { x: left, y: option.y, surface: option.surface }
  }
  return null
}

function distanceTo(option: { y: number; bounds: [number, number] }, centerX: number): number {
  const left = clamp(centerX, ...option.bounds)
  return Math.hypot(left - centerX, option.y - y.value)
}

/** 自由停放时在视口的上、中、下三行各试少量位置。 */
function findFreeSpot(
  covers: (rect: AgentRect, standingOn: Element | null) => boolean,
): { x: number; y: number; surface: null } | null {
  const range = freeBounds(viewport(), ...sizePair())
  for (const top of [range.y[0], (range.y[0] + range.y[1]) / 2, range.y[1]]) {
    if (Math.abs(top - y.value) < 1) continue
    const start = clamp(x.value, ...range.x)
    const clear = (left: number) => !covers(rectAt(left, top), null)
    const left = clear(start) ? start : pickClearX(start, range.x, clear, charWidth.value / 2, OTHER_SURFACE_CANDIDATES)
    if (left !== null) return { x: left, y: top, surface: null }
  }
  return null
}

/** 退到底边最近的一侧，视觉避让与可操作命中区分开。 */
function goShelter(instant: boolean) {
  const edge = nearestEdge(x.value, xBounds(viewport(), charWidth.value))
  const floorY = ground()
  pendingShelter = true
  if (instant || (Math.abs(edge - x.value) < 1 && Math.abs(floorY - y.value) < 1 && !surface)) {
    pendingShelter = false
    detachSurface()
    x.value = edge
    y.value = floorY
    beginShelter(instant)
    return
  }
  moveTo(edge, floorY, null, false)
}

/** 进入边缘躲避，保持眼位直到完整站起已不会挡住控件。 */
function beginShelter(instant: boolean) {
  sheltering = true
  beginPeek('bottom', false, instant)
}

/** 躲避中只检查能否恢复，不以持续遮挡为由反复下沉。 */
function recheckShelter() {
  const view = viewport()
  const body = charWidth.value * charHeight.value
  if (!coversControlAt(rectAt(x.value, ground()), rootEl.value, view, null, body, props.previewRoot)) {
    sheltering = false
    endPeek()
  }
}

/**
 * 移动到指定站立面上的位置。
 *
 * 同一个面上走过去；换面时沿抛物线跳过去（跳上更高的面也一样）；首次出现或不允许动画时瞬移。
 */
function moveTo(targetX: number, targetY: number, target: DomSurface | null, instant: boolean) {
  const sameLevel = Math.abs(targetY - y.value) < 1 && (target?.el ?? null) === (surface?.el ?? null)
  if (instant) {
    facingLeft.value = targetX < x.value
    detachSurface()
    x.value = targetX
    y.value = targetY
    fallTarget = { y: targetY, surface: target }
    land(false)
    return
  }
  if (sameLevel || roam() === 'free') {
    if (Math.abs(targetX - x.value) < 1 && Math.abs(targetY - y.value) < 1) finishWalk()
    else startWalk(targetX, roam() === 'free' ? targetY : null)
    return
  }
  detachSurface()
  const { vx, vy } = hopVelocity(
    { x: x.value, y: y.value },
    { x: targetX, y: targetY },
    GRAVITY,
    Math.min(charHeight.value * HOP_LIFT_RATIO, Math.max(0, Math.min(y.value, targetY) - viewport().safeArea.top)),
  )
  facingLeft.value = targetX < x.value
  hopVx = vx
  hopTargetX = targetX
  velocity = vy
  bounced = true
  fallTarget = { y: targetY, surface: target }
  motion.value = 'fall'
  ensureLoop()
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
  const value: StoredPosition = {
    roam: roam(),
    xRatio,
    yRatio,
    ...(peekPinned && peekEdge.value ? { peekEdge: peekEdge.value } : {}),
    ...(fixed() && fixedPosition
      ? {
          xRatio: Math.round(fixedPosition.xRatio * 1000) / 1000,
          yRatio: Math.round(fixedPosition.yRatio * 1000) / 1000,
        }
      : {}),
  }
  const key = JSON.stringify(value)
  if (key === lastSaved) return
  lastSaved = key
  lastSaveAt = Date.now()
  props.pet?.storage?.set?.(value)?.catch?.(() => console.warn('[AgentPets] position not saved'))
}

/** 已经被面板盖住时直接移到空位，不能让“禁止走进面板”的规则把退出路径也封住。 */
function clearPanelOverlap(): boolean {
  if (motion.value === 'drag') return false
  if (activePeekEdge.value) {
    const rect = currentRect()
    const panel = hostState?.panelRect
    if (!panel || intersectionArea(rect, panel) === 0) return false
    const shift = peekPanelShift(rect, panel, peekViewport(), activePeekEdge.value)
    if (shift) {
      x.value += shift.x
      y.value += shift.y
      queueAnchor()
      return true
    }
  }
  const view = viewport()
  const point = avoidPanel({ x: x.value, y: y.value }, hostState?.panelRect ?? null, view, size())
  if (point.x === x.value && point.y === y.value) return false
  const horizontal = point.y === y.value
  const previous = surface
  const manual = manualSurface
  resetMotion()
  x.value = point.x
  y.value = point.y
  // 横移后仍在同一张卡片上时继续跟随；否则解除旧支撑与旧抛物线。
  if (
    previous &&
    point.y === previous.top - charHeight.value &&
    checkSupport(
      previous,
      previous,
      point.x + charWidth.value / 2,
      view,
      charHeight.value,
      hostState?.panelRect ?? null,
      charWidth.value,
    ).kind === 'follow'
  ) {
    attachSurface(previous)
    manualSurface = manual
  }
  // 横向退出面板后继续按活动范围落位；垂直避让时先停在面板外，避免马上掉回遮挡区。
  if (horizontal && !surface && !fixed() && roam() !== 'free') startFall()
  scheduleBehavior()
  queueAnchor()
  return true
}

/** 视口、面板或尺寸变化后把角色放回合法位置。 */
function relayout() {
  layoutRevision.value++
  if (fixed() && motion.value !== 'drag') {
    placeFixed()
    return
  }
  if (motion.value === 'peek' && peekEdge.value) {
    placePeek()
    clearPanelOverlap()
    queueAnchor()
    return
  }
  if (clearPanelOverlap()) return
  const view = freeBounds(viewport(), ...sizePair())
  if (walkTarget) {
    walkTarget.x = clamp(walkTarget.x, ...view.x)
    if (walkTarget.y !== null) walkTarget.y = clamp(walkTarget.y, ...view.y)
  }
  if (motion.value === 'drag' || motion.value === 'fall') {
    const outside = x.value < view.x[0] || x.value > view.x[1] || y.value > view.y[1]
    const targetOutside = fallTarget && (fallTarget.y < view.y[0] || fallTarget.y > view.y[1])
    const hopOutside = hopTargetX !== null && (hopTargetX < view.x[0] || hopTargetX > view.x[1])
    x.value = clamp(x.value, ...view.x)
    y.value = clamp(y.value, ...view.y)
    // 收回当前位置还不够：取消越界的旧抛物线和落点，防止下一帧再次离屏。
    if (motion.value === 'fall' && (outside || targetOutside || hopOutside)) {
      pendingShelter = false
      startFall()
    }
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
  clearPanelOverlap()
  queueAnchor()
}

/** 设置变化（含设置页实时预览）；活动范围改变时按新模式重新落位。 */
function applySettings(value: unknown) {
  settingsRevision++
  const before = settings.value.roam
  const wasFixed = fixed()
  settings.value = normalizeSettings(value)
  if (ready.value && wasFixed !== fixed() && motion.value !== 'drag') {
    saveOnLand = true
    if (fixed()) pinHere()
    else {
      fixedPosition = null
      startFall()
    }
    return
  }
  if (ready.value && !fixed() && settings.value.roam !== before && motion.value !== 'drag') {
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
  if (editorPaused) return
  available.value = state.available
  const resized =
    !!before &&
    (before.viewport.width !== state.viewport.width ||
      before.viewport.height !== state.viewport.height ||
      before.viewport.keyboardInset !== state.viewport.keyboardInset ||
      before.isMobile !== state.isMobile)
  isMobile.value = state.isMobile
  if (resized) refreshBottomFloor()
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
  if (state.motionAllowed && before?.motionAllowed === false) {
    if (motion.value === 'peek') schedulePeekExit()
    else scheduleBehavior()
  }
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
  clearTimer('peek-pause')
  walkTarget = null
  walkPhase.value = 0
  pendingPeek = null
  pendingStepOff = false
  pendingShelter = false
  blinking.value = false
  if (motion.value === 'peek' && peekEdge.value) {
    peekProgress.value = 1
    peekTarget = 1
    peekPhase.value = 'look'
    peekRevealing.value = true
    peekTiltProgress.value = 1
    queueAnchor()
    return
  }
  peekProgress.value = 0
  peekTarget = 0
  if (motion.value === 'fall') land(false)
  else if (motion.value === 'walk' || motion.value === 'peek') {
    motion.value = 'idle'
    queueAnchor()
  }
}

/** 页面不可见时停掉 rAF、行为计时与元素观察；回到可见后继续并重新校验脚下。 */
function syncVisibility() {
  animationActive.value = motionAllowed() && visible()
  if (editorPaused) {
    stopLoop()
    pauseSurfaceWatch()
    if (anchorFrame) window.cancelAnimationFrame(anchorFrame)
    anchorFrame = 0
    return
  }
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
  if (editorPaused) return
  markActivity()
  const next = eventPose(event.name)
  if (next) playTransient(next.pose, next.duration)
}

async function refreshPetSettings() {
  if (props.settingsOverride) return
  const revision = ++settingsRevision
  const loaded = await withLoadTimeout(
    loadSettings(props.api, props.pluginId, props.pet?.key || 'ying'),
    startup.signal,
  ).catch(() => settings.value)
  if (!disposed && revision === settingsRevision) applySettings(loaded)
}

function onSettingsEvent(event: AgentHostEvent) {
  if (props.pluginId && event.source !== props.pluginId) return
  const data = event.data as (Partial<YingSettings> & { key?: string }) | null
  if (!data || typeof data !== 'object' || (data.key && data.key !== (props.pet?.key || 'ying'))) return
  if (!ready.value && props.api && !props.settingsOverride) {
    void refreshPetSettings()
    return
  }
  applySettings({ ...settings.value, ...data })
}

watch([() => props.pluginId, () => props.pet?.key], () => {
  ownCalibration.value = builtinDefaultCalibration('ying')
  void refreshPetSettings()
  void refreshOwnCalibration()
})

let calibrationRevision = 0
async function refreshOwnCalibration() {
  const version = ++calibrationRevision
  if (!ownFrames) return
  if (props.pet?.key && props.pet.key !== 'ying') {
    ownCalibration.value = builtinDefaultCalibration('ying')
    return
  }
  emit('load-state', 'loading')
  try {
    const value = await loadBuiltinCalibration(props.api, props.pluginId, 'ying', startup.signal)
    if (disposed || version !== calibrationRevision) return
    ownCalibration.value = value
    emit('pack-ready', { ...YING_PACK, calibration: value })
    emit('load-state', 'ready')
  } catch {
    if (disposed || version !== calibrationRevision) return
    if (props.previewRoot) emit('load-state', 'error')
  }
}

function pointerPosition(event: PointerEvent) {
  const origin = props.previewRoot?.getBoundingClientRect()
  return { x: event.clientX - (origin?.left ?? 0), y: event.clientY - (origin?.top ?? 0) }
}

watch(
  () => props.settingsOverride,
  value => {
    if (value) applySettings(value)
  },
  { deep: true },
)

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0 || press) return
  markActivity()
  press = {
    id: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    offsetX: activePeekEdge.value ? charWidth.value / 2 : pointerPosition(event).x - x.value,
    offsetY: activePeekEdge.value ? charHeight.value * 0.3 : pointerPosition(event).y - y.value,
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
    clearTimer('peek')
    clearTimer('peek-pause')
    clearTimer('landing-peek')
    transient.value = null
    peekProgress.value = 0
    peekEdge.value = null
    peekPhase.value = null
    peekPinned = false
    peekTarget = 0
    sheltering = false
    pendingShelter = false
    hopVx = 0
    hopTargetX = null
    velocity = 0
    fallTarget = null
    motion.value = 'drag'
    syncSurfacePoll()
    props.pet?.setInteracting?.(true)
  }
  event.preventDefault()
  const view = freeBounds(viewport(), ...sizePair())
  x.value = clamp(pointerPosition(event).x - press.offsetX, ...view.x)
  y.value = clamp(pointerPosition(event).y - press.offsetY, ...view.y)
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
  const edge = fixed() || previewEdge.value ? null : dropPeekEdge({ x: x.value, y: y.value }, viewport(), size())
  const snap = Math.min(24, charHeight.value * 0.2)
  const nearby = !fixed() && roam() === 'surfaces' ? landing(null, snap) : null
  const onPlatform = !!nearby?.surface && Math.abs(nearby.y - y.value) <= snap
  if (edge && !onPlatform) {
    droppedByUser = false
    saveOnLand = false
    beginPeek(edge, true)
    requestSave()
    return
  }
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
  if (fixed()) {
    rememberFixedPosition()
    placeFixed()
    return
  }
  if (isPeekEdge(stored?.peekEdge)) {
    const home = peekHome({ x: x.value, y: y.value }, view, size(), stored.peekEdge)
    if (stored.peekEdge === 'bottom' || (Math.abs(home.x - x.value) < 1 && Math.abs(home.y - y.value) < 1)) {
      beginPeek(stored.peekEdge, true, true)
      return
    }
  }
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
  if (!ready.value || editorPaused || props.previewRoot) return
  refreshBottomFloor()
  relayout()
  scheduleClearance(RESIZE_CLEAR_DELAY)
}

onMounted(async () => {
  if (!props.previewRoot)
    cleanups.push(
      onEditorPresence(active => {
        editorPaused = active
        if (active) timers.pause()
        else timers.resume()
        if (!active && hostState) onHostState(hostState)
        syncVisibility()
        syncSurfacePoll()
      }),
    )
  void refreshOwnCalibration()
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
    if (ownFrames)
      cleanups.push(
        agent.on(PACK_UPDATED_EVENT, event => {
          if (event.source === props.pluginId && event.data.key === 'ying') void refreshOwnCalibration()
        }),
      )
  }
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('resize', onWindowResize)
  cleanups.push(() => document.removeEventListener('visibilitychange', onVisibilityChange))
  cleanups.push(() => window.removeEventListener('resize', onWindowResize))
  const visual = window.visualViewport
  if (visual && !props.previewRoot) {
    visual.addEventListener('resize', onWindowResize)
    visual.addEventListener('scroll', onWindowResize)
    cleanups.push(() => {
      visual.removeEventListener('resize', onWindowResize)
      visual.removeEventListener('scroll', onWindowResize)
    })
  }

  const revision = settingsRevision
  const [loaded, stored] = await Promise.all([
    withLoadTimeout(
      Promise.resolve(props.settingsOverride ?? loadSettings(props.api, props.pluginId, props.pet?.key || 'ying')),
      startup.signal,
    ).catch(() => DEFAULT_SETTINGS),
    withLoadTimeout(readStoredPosition(), startup.signal).catch(() => null),
  ])
  if (disposed) return
  if (revision === settingsRevision) settings.value = normalizeSettings(props.settingsOverride ?? loaded)
  refreshBottomFloor()
  restorePosition(stored)
  ready.value = true
  syncVisibility()
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
  startup.abort()
  stopLoop()
  pauseSurfaceWatch()
  if (anchorFrame) window.cancelAnimationFrame(anchorFrame)
  anchorFrame = 0
  timers.dispose()
  releasePointer()
  if (press?.dragging) props.pet?.setInteracting?.(false)
  press = null
  for (const cleanup of cleanups.splice(0)) cleanup()
  props.pet?.setBubbleAnchor?.(null)
})
</script>

<template>
  <div
    ref="rootEl"
    class="agent-pet-ying"
    :class="{ 'agent-pet-ying--contained': !!props.previewRoot }"
    :data-pose="pose"
    :data-motion="motion"
    :data-roam="settings.roam"
    :data-movement="settings.movement"
    :data-peek-edge="activePeekEdge ?? undefined"
    :data-peek-phase="previewEdge ? 'look' : (peekPhase ?? undefined)"
  >
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
      <span class="agent-pet-ying__clip" :style="clipStyle">
        <span class="agent-pet-ying__artwork" :style="artworkStyle">
          <slot
            :pose="pose"
            :facing-left="facingLeft"
            :motion-active="animationActive && (!activePeekEdge || settledPeek)"
            :peek-edge="activePeekEdge"
            :peek-from-left="drawing.fromLeft"
          >
            <span
              class="agent-pet-ying__frames"
              :class="{ 'agent-pet-ying__frames--flip': facingLeft, 'agent-pet-ying__frames--pending': !displayed }"
              :data-frame="displayed ?? undefined"
            >
              <span class="agent-pet-ying__frame-crop" :style="ownLayout.frame">
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
              <template v-if="showCalibration">
                <span
                  v-for="point in ownGuides"
                  :key="point.key"
                  class="agent-pet-ying__eye"
                  :style="{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }"
                />
              </template>
            </span>
          </slot>
        </span>
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

.agent-pet-ying--contained {
  position: absolute;
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

.agent-pet-ying__clip {
  position: absolute;
  overflow: hidden;
  pointer-events: none;
}

.agent-pet-ying__artwork {
  position: absolute;
  display: block;
  transform-origin: center;
  pointer-events: none;
}

/* 翻转只作用于画面，命中区不随裁切或旋转缩小。 */
.agent-pet-ying__frames {
  position: absolute;
  inset: 0;
  display: block;
  pointer-events: none;
  overflow: hidden;
}

.agent-pet-ying__frame-crop {
  position: absolute;
  display: block;
}
.agent-pet-ying__eye {
  position: absolute;
  width: 10px;
  height: 10px;
  border: 2px solid rgb(var(--v-theme-warning));
  border-radius: 50%;
  transform: translate(-50%, -50%);
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
