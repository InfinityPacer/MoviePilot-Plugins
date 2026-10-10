<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import type { AgentHostEvent, AgentHostState, AgentPetContext, AgentRect, MoviePilotAgentHost, PluginApi } from '@/host'
import {
  blockedSpan,
  clamp,
  escapeSpan,
  groundTop,
  isBlocked,
  pickWalkTarget,
  ratioToX,
  readViewport,
  sameRect,
  xBounds,
  xToRatio,
} from '@/stage/geometry'
import { eventPose, frameUrl, phasePose, POSES, resolvePose, type Motion, type Pose } from '@/stage/poses'
import { DEFAULT_SETTINGS, loadSettings, normalizeSettings, SETTINGS_EVENT, type YingSettings } from '@/stage/settings'

/**
 * 小映 stage 形象。
 *
 * 宿主把本组件挂在 `pointer-events: none` 的全视口图层里，组件只让角色按钮接收指针。
 * 所有订阅、rAF、计时器和全局指针监听都在卸载时释放；旧版主程序不传 `agent`/`pet`
 * 时组件仍能显示与拖拽，只是无法打开面板和上报气泡锚点。
 */
const props = withDefaults(
  defineProps<{
    agent?: MoviePilotAgentHost | null
    pet?: AgentPetContext | null
    api?: PluginApi | null
    pluginId?: string
    sourcePluginId?: string
  }>(),
  { agent: null, pet: null, api: null, pluginId: '', sourcePluginId: '' },
)

/** 设置为 1 倍时的角色高度（CSS 像素）。 */
const BASE_HEIGHT = 120
/** 设置为 1 倍时的走路速度（像素/秒）。 */
const BASE_WALK_SPEED = 70
/** 设置为 1 倍时 walk1/walk2 的切换间隔（秒）。 */
const BASE_STEP_INTERVAL = 0.2
const GRAVITY = 2600
const DRAG_THRESHOLD = 6
const SIT_DURATION = 900
const DOZE_AFTER = 90_000
const PEEK_RATIO = 0.5
const PEEK_SPEED = 160
const DEFAULT_RATIO = 0.88

/** `pet.storage` 中保存的每用户数据。 */
interface StoredPosition {
  /** 落脚点在可活动范围内的水平比例，0 为最左，1 为最右。 */
  xRatio: number
}

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

let hostState: AgentHostState | null = null
let documentVisible = typeof document === 'undefined' || document.visibilityState !== 'hidden'
let rafId = 0
let lastFrame = 0
let anchorFrame = 0
let lastAnchor: AgentRect | null = null
let walkTarget: number | null = null
let walkClock = 0
let velocity = 0
let bounced = false
let peekTarget = 0
let lastSavedRatio = -1
let suppressClick = false
/** 散步到底边一侧后接着探头。 */
let pendingPeek = false
let disposed = false
let press: { id: number; startX: number; startY: number; offsetX: number; offsetY: number; dragging: boolean } | null =
  null

const timers = new Map<string, number>()
const cleanups: Array<() => void> = []

const charHeight = computed(() => BASE_HEIGHT * settings.value.scale)
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
const src = computed(() => frameUrl(pose.value))
const available = ref(true)
const label = computed(() => (available.value ? '打开助手（小映）' : '小映（助手未启用）'))

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

function viewport() {
  return readViewport(hostState)
}

function ground(): number {
  return groundTop(viewport(), charHeight.value)
}

function bounds(): [number, number] {
  return xBounds(viewport(), charWidth.value)
}

function panelSpan(): [number, number] | null {
  return blockedSpan(hostState?.panelRect ?? null, ground(), charWidth.value)
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
  if (walkTarget === null) {
    finishWalk()
    return
  }
  const direction = Math.sign(walkTarget - x.value)
  const next = x.value + direction * BASE_WALK_SPEED * settings.value.speed * dt
  if (isBlocked(next, panelSpan())) {
    finishWalk()
    return
  }
  walkClock += dt
  walkPhase.value = Math.floor(walkClock / (BASE_STEP_INTERVAL / settings.value.speed)) % 2
  const arrived = direction === 0 || (direction > 0 ? next >= walkTarget : next <= walkTarget)
  x.value = arrived ? walkTarget : next
  if (arrived) finishWalk()
}

function stepFall(dt: number) {
  velocity += GRAVITY * dt
  y.value += velocity * dt
  rising.value = velocity < 0
  const floor = ground()
  if (y.value < floor) return
  y.value = floor
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

function startWalk(target: number) {
  walkTarget = target
  walkClock = 0
  facingLeft.value = target < x.value
  motion.value = 'walk'
  ensureLoop()
}

function finishWalk() {
  walkTarget = null
  walkPhase.value = 0
  if (motion.value === 'walk') motion.value = 'idle'
  const after = pendingPeek
  pendingPeek = false
  if (after) beginPeek()
  else scheduleBehavior()
  savePosition()
}

function beginPeek() {
  if (!motionAllowed()) return
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
    savePosition()
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
}

function calm(): boolean {
  return (
    motion.value === 'idle' && !transient.value && !sustained.value && !dozing.value && motionAllowed() && visible()
  )
}

/** 空闲时偶尔散步，或走到一侧底边探出上半身。 */
function scheduleBehavior() {
  clearTimer('behavior')
  if (!calm()) return
  setTimer('behavior', randomBetween(6000, 14000), () => {
    if (!calm()) return
    const [min, max] = bounds()
    const roll = Math.random()
    if (roll < 0.22) {
      const side = Math.random() < 0.5 ? min : max
      const span = panelSpan()
      if (isBlocked(side, span) || Math.abs(side - x.value) < 1) {
        if (!isBlocked(side, span)) beginPeek()
        else scheduleBehavior()
        return
      }
      pendingPeek = true
      startWalk(side)
      return
    }
    const target = roll < 0.85 ? pickWalkTarget(Math.random, x.value, [min, max], panelSpan()) : null
    if (target === null) scheduleBehavior()
    else startWalk(target)
  })
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

function land(animated: boolean) {
  velocity = 0
  rising.value = false
  y.value = ground()
  sink.value = 0
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
  savePosition()
  queueAnchor()
}

function savePosition() {
  const ratio = Math.round(xToRatio(x.value, bounds()) * 1000) / 1000
  if (Math.abs(ratio - lastSavedRatio) < 0.005) return
  lastSavedRatio = ratio
  const value: StoredPosition = { xRatio: ratio }
  props.pet?.storage?.set?.(value)?.catch?.(() => console.warn('[AgentPetYing] position not saved'))
}

/** 视口、面板或尺寸变化后把角色放回合法位置。 */
function relayout() {
  const range = bounds()
  if (motion.value === 'drag') {
    x.value = clamp(x.value, 0, Math.max(0, viewport().width - charWidth.value))
    y.value = clamp(y.value, 0, ground())
    queueAnchor()
    return
  }
  x.value = clamp(x.value, range[0], range[1])
  if (onGround()) y.value = ground()
  const span = panelSpan()
  if (onGround() && isBlocked(x.value, span)) {
    const escaped = escapeSpan(x.value, span, range)
    settle()
    if (motionAllowed() && visible() && Math.abs(escaped - x.value) > 1) startWalk(escaped)
    else x.value = escaped
  }
  queueAnchor()
}

function applySettings(value: unknown) {
  settings.value = normalizeSettings(value)
  relayout()
}

function onHostState(state: AgentHostState) {
  const before = hostState
  hostState = state
  available.value = state.available
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
  relayout()
}

/** 减少动态效果时立刻停在地面，不播下落和散步。 */
function freezeMotion() {
  stopLoop()
  clearTimer('behavior')
  clearTimer('peek')
  walkTarget = null
  walkPhase.value = 0
  pendingPeek = false
  sink.value = 0
  peekTarget = 0
  blinking.value = false
  if (motion.value === 'walk' || motion.value === 'peek' || motion.value === 'fall') land(false)
}

/** 页面不可见时停掉 rAF 与行为计时；回到可见后继续。 */
function syncVisibility() {
  if (!visible()) {
    stopLoop()
    clearTimer('behavior')
    if (motion.value === 'fall') land(false)
    return
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
    clearTimer('behavior')
    clearTimer('sit')
    transient.value = null
    sink.value = 0
    peekTarget = 0
    velocity = 0
    motion.value = 'drag'
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
  x.value = clamp(x.value, ...bounds())
  if (motionAllowed() && visible()) {
    motion.value = 'fall'
    velocity = 0
    bounced = false
    ensureLoop()
  } else land(false)
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

function preloadFrames() {
  for (const name of POSES) {
    const image = new Image()
    image.src = frameUrl(name)
    if (name === 'idle') {
      image.onload = () => {
        if (image.naturalWidth && image.naturalHeight) {
          aspect.value = image.naturalWidth / image.naturalHeight
          relayout()
        }
      }
    }
  }
}

async function restorePosition() {
  let ratio = DEFAULT_RATIO
  try {
    const stored = await props.pet?.storage?.get?.<StoredPosition>()
    if (stored && typeof stored.xRatio === 'number' && Number.isFinite(stored.xRatio)) ratio = stored.xRatio
  } catch {
    console.warn('[AgentPetYing] position unavailable')
  }
  if (disposed) return
  lastSavedRatio = ratio
  x.value = ratioToX(ratio, bounds())
  y.value = ground()
}

function onVisibilityChange() {
  documentVisible = document.visibilityState !== 'hidden'
  syncVisibility()
}

function onWindowResize() {
  if (!hostState) relayout()
}

onMounted(async () => {
  preloadFrames()
  const agent = props.agent
  if (agent?.subscribe) cleanups.push(agent.subscribe(onHostState))
  else hostState = null
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

  const [loaded] = await Promise.all([loadSettings(props.api, props.pluginId), restorePosition()])
  if (disposed) return
  settings.value = loaded
  relayout()
  ready.value = true
  reportAnchor()
  scheduleBlink()
  markActivity()
  scheduleBehavior()
})

onBeforeUnmount(() => {
  disposed = true
  stopLoop()
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
  <div class="agent-pet-ying" :data-pose="pose" :data-motion="motion">
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
      <img
        class="agent-pet-ying__frame"
        :class="{ 'agent-pet-ying__frame--flip': facingLeft }"
        :src="src"
        alt=""
        draggable="false"
      />
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

.agent-pet-ying__frame {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: bottom center;
  pointer-events: none;
}

.agent-pet-ying__frame--flip {
  transform: scaleX(-1);
}
</style>
