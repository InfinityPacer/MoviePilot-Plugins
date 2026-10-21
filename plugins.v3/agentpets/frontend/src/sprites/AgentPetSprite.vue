<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, type ObjectDirective } from 'vue'
import {
  calibrationEye,
  calibrationForAction,
  calibrationLayout,
  calibrationPoint,
  LANDMARKS,
  mirrorFace,
  parseCalibration,
  type Calibration,
  type CalibratedFace,
} from '@/sprites/calibration'
import CalibrationMarkers from '@/editor/CalibrationMarkers.vue'
import { loadBuiltinCalibration, YING_PACK } from './builtinCalibration'
import { frameUrl } from '@/stage/poses'
import { loadImage, withLoadTimeout } from '@/loading'

import { PACK_UPDATED_EVENT, type ActionMappings } from '@/sprites/mappings'
import type { AgentPetContext, MoviePilotAgentHost, PluginApi } from '@/host'
import {
  BUILTIN_PACK,
  BUILTIN_PACKS,
  BUILTIN_PACK_ID,
  builtinAsset,
  framePosition,
  resolveAction,
  validatePack,
  withCodexStageActions,
  type SpritePack,
} from '@/sprites/schema'

/**
 * 素材包 renderer 形象。
 *
 * 宿主保留入口的拖拽、贴边、点击和气泡，本组件只在触发区内按 action / intent 播放帧。
 * 读取素材包失败时退回内置放映猫，不向宿主抛错。
 */
const props = withDefaults(
  defineProps<{
    agent?: MoviePilotAgentHost | null
    pet?: AgentPetContext | null
    api?: PluginApi | null
    pluginId?: string
    sourcePluginId?: string
    /** 宿主动作名，素材包不认识时按 intent 处理。 */
    action?: string | null
    /** 宿主 AgentPetIntent。 */
    intent?: string
    thinking?: boolean
    /** 为 false 时只显示当前动作的第一帧。 */
    motionActive?: boolean
    mirrorX?: boolean
    /** 预览加载失败时显示错误，不用其他宠物冒充选中项。 */
    strictPreview?: boolean
    calibrationOverride?: Calibration
    showCalibration?: boolean
    editCalibration?: boolean
    calibrationDisabled?: boolean
    calibrationZoom?: number
    mappingsOverride?: ActionMappings
    mappingKey?: string
    nativeAction?: string
    replay?: number
  }>(),
  {
    agent: null,
    pet: null,
    api: null,
    pluginId: '',
    sourcePluginId: '',
    action: null,
    intent: 'idle',
    thinking: false,
    motionActive: true,
  },
)

const emit = defineEmits<{
  appearance: [{ name: string; aspectRatio: number; eye: CalibratedFace | null }]
  'calibration-change': [Calibration]
  'load-state': ['loading' | 'ready' | 'error']
  'pack-ready': [SpritePack]
}>()

const packKey = props.pet?.key || BUILTIN_PACK_ID
const pack = ref<SpritePack>(BUILTIN_PACK)
const sheetSrc = ref(builtinAsset('sheet.webp'))
/**
 * 素材包是否已就绪可画。
 *
 * 用户素材包在读取完成前什么都不画，避免先闪一下放映猫；读取失败才退回内置素材包。
 */
const ready = ref(packKey === BUILTIN_PACK_ID)
const cellRatio = ref(1)
const frameIndex = ref(0)
let timer = 0
let disposed = false
let loadVersion = 0
let loadController: AbortController | null = null
let sheetRevision = ''
let unsubscribe: (() => void) | undefined

const resolved = computed(() =>
  resolveAction(pack.value, props.action, props.intent, props.thinking, {
    mappings: props.mappingsOverride,
    mappingKey: props.mappingKey,
    nativeAction: props.nativeAction,
  }),
)
const frame = computed(() => {
  const frames = resolved.value.action.frames
  return frames[Math.min(frameIndex.value, frames.length - 1)] ?? 'idle'
})
const baseCalibration = computed(() => parseCalibration(props.calibrationOverride ?? pack.value.calibration))
const calibration = computed(() =>
  calibrationForAction(
    baseCalibration.value,
    pack.value.action_baselines,
    resolved.value.key,
    BUILTIN_PACKS[pack.value.id]?.calibration?.baseline,
  ),
)
const eye = computed(() => {
  const face = calibrationEye(calibration.value)
  return props.mirrorX ? mirrorFace(face) : face
})
const guidePoints = computed(() =>
  LANDMARKS.flatMap(key => {
    const point = calibrationPoint(calibration.value, key)
    return point ? [{ key, ...point, x: props.mirrorX ? 1 - point.x : point.x }] : []
  }),
)
const layout = computed(() => calibrationLayout(calibration.value, cellRatio.value))
const sheetStyle = computed(() => ({
  'background-image': `url(${JSON.stringify(sheetSrc.value)})`,
  'background-size': `${pack.value.grid.cols * 100}% ${pack.value.grid.rows * 100}%`,
}))
// Large data URLs exceed Chromium's custom-property limit; write the image directly, only when changed.
const vSpriteSheet: ObjectDirective<HTMLElement, Record<string, string>> = {
  mounted: (el, { value }) => {
    for (const [key, next] of Object.entries(value)) el.style.setProperty(key, next)
  },
  updated: (el, { value, oldValue }) => {
    for (const [key, next] of Object.entries(value)) if (next !== oldValue?.[key]) el.style.setProperty(key, next)
  },
}
const frameStyle = computed(() => {
  const position = framePosition(pack.value, frame.value)
  return {
    ...layout.value.frame,
    backgroundPosition: `${position.x}% ${position.y}%`,
  }
})

function stop() {
  if (timer) window.clearTimeout(timer)
  timer = 0
}

/** 从第一帧重新播放当前动作；非循环动作停在最后一帧。 */
function play() {
  stop()
  frameIndex.value = 0
  if (!props.motionActive || !ready.value || disposed) return
  const { frames, frame_ms: frameMs, frame_durations: durations, loop } = resolved.value.action
  if (frames.length < 2) return
  const advance = () => {
    const next = frameIndex.value + 1
    if (next >= frames.length && !loop) {
      timer = 0
      return
    }
    frameIndex.value = next % frames.length
    timer = window.setTimeout(advance, durations?.[frameIndex.value] ?? frameMs)
  }
  timer = window.setTimeout(advance, durations?.[0] ?? frameMs)
}

async function loadPack(key: string) {
  loadController?.abort()
  const controller = new AbortController()
  loadController = controller
  const signal = controller.signal
  const version = ++loadVersion
  const current = () => !disposed && version === loadVersion && !signal.aborted
  emit('load-state', 'loading')
  try {
    const builtin = key === 'ying' || Object.hasOwn(BUILTIN_PACKS, key)
    let nextPack = key === 'ying' ? YING_PACK : builtin ? BUILTIN_PACKS[key] : BUILTIN_PACK
    let nextSheet =
      key === 'ying'
        ? frameUrl('idle')
        : builtinAsset(nextPack.sheet || 'sheet.webp', undefined, builtin ? key : BUILTIN_PACK_ID)
    let nextRevision = ''
    if (builtin) {
      try {
        nextPack = { ...nextPack, calibration: await loadBuiltinCalibration(props.api, props.pluginId, key, signal) }
      } catch {
        if (props.strictPreview && props.api?.get) throw new Error('内置校准读取失败')
        // Keep bundled art available when the service is temporarily unreachable.
      }
    } else {
      if (!props.api?.get) throw new Error('pack API unavailable')
      const instanceId = props.pluginId || 'AgentPets'
      const known = ready.value && pack.value.id === key ? sheetRevision : ''
      const response = await withLoadTimeout(
        props.api.get<{ pack: unknown; sheet_src: string; sheet_revision?: string }>(
          `plugin/${instanceId}/pack?key=${encodeURIComponent(key)}${known ? `&known_sheet=${encodeURIComponent(known)}` : ''}`,
        ),
        signal,
      )
      const { pack: parsed } = validatePack(response?.data?.pack)
      if (
        !response?.success ||
        !parsed ||
        (!response.data?.sheet_src && (!known || response.data?.sheet_revision !== known))
      )
        throw new Error(response?.message || 'invalid pack')
      nextPack = props.pet?.mode === 'stage' ? withCodexStageActions(parsed) : parsed
      nextSheet = response.data.sheet_src || sheetSrc.value
      nextRevision = response.data.sheet_revision || ''
    }
    const reuseImage =
      !!nextRevision &&
      nextRevision === sheetRevision &&
      ready.value &&
      nextSheet === sheetSrc.value &&
      nextPack.grid.cols === pack.value.grid.cols &&
      nextPack.grid.rows === pack.value.grid.rows
    const dimensions = reuseImage ? null : await loadImage(nextSheet, signal)
    if (!current()) return
    pack.value = nextPack
    sheetSrc.value = nextSheet
    sheetRevision = nextRevision
    if (dimensions) cellRatio.value = dimensions.width / nextPack.grid.cols / (dimensions.height / nextPack.grid.rows)
    ready.value = true
    emit('pack-ready', nextPack)
    emit('load-state', 'ready')
  } catch {
    if (!current()) return
    console.warn(`[AgentPets] pack ${key} unavailable`)
    ready.value = false
    sheetRevision = ''
    emit('load-state', 'error')
    if (props.strictPreview || key === BUILTIN_PACK_ID) return
    try {
      const src = builtinAsset('sheet.webp')
      const dimensions = await loadImage(src, signal)
      if (!current()) return
      pack.value = BUILTIN_PACK
      sheetSrc.value = src
      cellRatio.value = dimensions.width / BUILTIN_PACK.grid.cols / (dimensions.height / BUILTIN_PACK.grid.rows)
      ready.value = true
    } catch {
      // 内置图片也不可达时保留错误状态，宿主按钮仍可操作。
    }
  }
}

watch(
  () => [resolved.value.key, props.motionActive, ready.value, pack.value, props.replay] as const,
  () => play(),
)
watch(
  [ready, pack, cellRatio, calibration, () => props.mirrorX],
  () => {
    if (ready.value)
      emit('appearance', { name: pack.value.name, aspectRatio: layout.value.aspectRatio, eye: eye.value })
  },
  { immediate: true },
)

onMounted(async () => {
  if (!props.strictPreview)
    unsubscribe = props.agent?.on(PACK_UPDATED_EVENT, event => {
      if (event.source === props.pluginId && event.data.key === packKey) void loadPack(packKey)
    })
  play()
  await loadPack(packKey)
})

onBeforeUnmount(() => {
  disposed = true
  loadVersion++
  loadController?.abort()
  unsubscribe?.()
  stop()
})
</script>

<template>
  <div
    class="agent-pet-sprites"
    :class="{ 'agent-pet-sprites--stage': pet?.mode === 'stage' }"
    :aria-hidden="editCalibration ? undefined : true"
    :data-pack="ready ? pack.id : undefined"
    :data-action="resolved.key"
    :data-frame="frame"
    :data-mirrored="!!mirrorX"
  >
    <div
      v-if="ready"
      class="agent-pet-sprites__viewport"
      :class="{ 'agent-pet-sprites__viewport--guides': showCalibration }"
      :style="{ '--agent-pet-sprites-ratio': String(layout.aspectRatio) }"
    >
      <div class="agent-pet-sprites__crop" :style="mirrorX ? { transform: 'scaleX(-1)' } : undefined">
        <div class="agent-pet-sprites__frame" :style="frameStyle" v-sprite-sheet="sheetStyle" />
      </div>
      <CalibrationMarkers
        v-if="editCalibration && (pack.codex_version || pet?.mode === 'stage')"
        :model-value="calibration"
        :disabled="calibrationDisabled"
        :zoom="calibrationZoom"
        @update:model-value="emit('calibration-change', { ...$event, baseline: baseCalibration.baseline })"
      />
      <span
        v-if="showCalibration && eye && !editCalibration"
        class="agent-pet-sprites__eye"
        :style="{ left: `${eye.x * 100}%`, top: `${eye.y * 100}%` }"
      />
      <template v-if="showCalibration && !editCalibration">
        <span
          v-for="point in guidePoints"
          :key="point.key"
          class="agent-pet-sprites__eye"
          :style="{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
.agent-pet-sprites {
  container-type: size;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  width: 100%;
  height: 100%;
  min-width: 3rem;
  min-height: 3rem;
  pointer-events: none;
}

.agent-pet-sprites__viewport {
  position: relative;
  overflow: visible;
  width: min(100cqw, 100cqh * var(--agent-pet-sprites-ratio));
  aspect-ratio: var(--agent-pet-sprites-ratio);
}
.agent-pet-sprites--stage {
  min-width: 0;
  min-height: 0;
}
.agent-pet-sprites__eye {
  position: absolute;
  width: 10px;
  height: 10px;
  border: 2px solid rgb(var(--v-theme-warning));
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 1px rgb(var(--v-theme-surface));
}
.agent-pet-sprites__frame {
  position: absolute;
  background-repeat: no-repeat;
}
.agent-pet-sprites__crop {
  position: absolute;
  inset: 0;
  overflow: hidden;
}
.agent-pet-sprites__viewport--guides {
  outline: 1px dashed rgb(var(--v-theme-primary));
}
.agent-pet-sprites__viewport--guides::after {
  content: '';
  position: absolute;
  inset: auto 0 0;
  border-bottom: 2px solid rgb(var(--v-theme-primary));
}
</style>
