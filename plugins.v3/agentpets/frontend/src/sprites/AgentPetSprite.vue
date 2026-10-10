<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { AgentPetContext, MoviePilotAgentHost, PluginApi } from '@/host'
import {
  BUILTIN_PACK,
  BUILTIN_PACK_ID,
  builtinAsset,
  framePosition,
  resolveAction,
  validatePack,
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

const resolved = computed(() => resolveAction(pack.value, props.action, props.intent, props.thinking))
const frame = computed(() => {
  const frames = resolved.value.action.frames
  return frames[Math.min(frameIndex.value, frames.length - 1)] ?? 'idle'
})
const frameStyle = computed(() => {
  const { cols, rows } = pack.value.grid
  const position = framePosition(pack.value, frame.value)
  return {
    '--agent-pet-sprites-ratio': String(cellRatio.value),
    backgroundImage: `url(${JSON.stringify(sheetSrc.value)})`,
    backgroundSize: `${cols * 100}% ${rows * 100}%`,
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
  if (!props.motionActive || disposed) return
  const { frames, frame_ms: frameMs, loop } = resolved.value.action
  if (frames.length < 2) return
  const advance = () => {
    const next = frameIndex.value + 1
    if (next >= frames.length && !loop) {
      timer = 0
      return
    }
    frameIndex.value = next % frames.length
    timer = window.setTimeout(advance, frameMs)
  }
  timer = window.setTimeout(advance, frameMs)
}

function measure(src: string) {
  const image = new Image()
  image.onload = () => {
    if (disposed || sheetSrc.value !== src || !image.naturalWidth) return
    const { cols, rows } = pack.value.grid
    cellRatio.value = image.naturalWidth / cols / (image.naturalHeight / rows)
  }
  image.src = src
}

/** 读取用户素材包的上限（毫秒）；超时与失败一样退回放映猫，避免入口一直空白。 */
const PACK_LOAD_TIMEOUT = 5000

function withTimeout<T>(promise: Promise<T>, timeout: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const id = window.setTimeout(() => reject(new Error('pack load timeout')), timeout)
    promise.then(
      value => {
        window.clearTimeout(id)
        resolve(value)
      },
      error => {
        window.clearTimeout(id)
        reject(error)
      },
    )
  })
}

async function loadPack(key: string) {
  if (key === BUILTIN_PACK_ID) return
  if (!props.api?.get) {
    ready.value = true
    return
  }
  const instanceId = props.pluginId || 'AgentPets'
  try {
    const response = await withTimeout(
      props.api.get<{ pack: unknown; sheet_src: string }>(`plugin/${instanceId}/pack?key=${encodeURIComponent(key)}`),
      PACK_LOAD_TIMEOUT,
    )
    const { pack: parsed } = validatePack(response?.data?.pack)
    if (!response?.success || !parsed || !response.data?.sheet_src) throw new Error(response?.message || 'invalid pack')
    if (disposed) return
    pack.value = parsed
    sheetSrc.value = response.data.sheet_src
  } catch {
    console.warn(`[AgentPets] pack ${key} unavailable, using builtin`)
  }
  if (!disposed) ready.value = true
}

watch(
  () => [resolved.value.key, props.motionActive, pack.value] as const,
  () => play(),
)
watch(sheetSrc, src => measure(src))
watch(ready, value => {
  if (value) measure(sheetSrc.value)
})

onMounted(async () => {
  if (ready.value) measure(sheetSrc.value)
  play()
  await loadPack(packKey)
})

onBeforeUnmount(() => {
  disposed = true
  stop()
})
</script>

<template>
  <div
    class="agent-pet-sprites"
    aria-hidden="true"
    :data-pack="ready ? pack.id : undefined"
    :data-action="resolved.key"
    :data-frame="frame"
  >
    <div v-if="ready" class="agent-pet-sprites__frame" :style="frameStyle" />
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

.agent-pet-sprites__frame {
  width: min(100cqw, 100cqh * var(--agent-pet-sprites-ratio));
  aspect-ratio: var(--agent-pet-sprites-ratio);
  background-repeat: no-repeat;
}
</style>
