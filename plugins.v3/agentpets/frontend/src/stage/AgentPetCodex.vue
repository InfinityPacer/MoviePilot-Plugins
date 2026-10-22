<script setup lang="ts">
import type { Calibration } from '@/sprites/calibration'
import { computed, ref, shallowRef } from 'vue'

import type { AgentPetContext, MoviePilotAgentHost, PluginApi } from '@/host'
import { stageAction, type ActionMappings } from '@/sprites/mappings'
import type { SpritePack } from '@/sprites/schema'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import type { Pose } from '@/stage/poses'
import type { PeekEdge, PeekEye } from '@/stage/peek'
import type { YingSettings } from '@/stage/settings'
import AgentPet from './AgentPet.vue'
import { supportsLookDirections } from './attention'
import { greetingPlayback } from './greeting'
import { supportsRest } from './activity'

/** Codex 精灵图复用小映的运动、设置、交互与气泡锚点。 */
const props = withDefaults(
  defineProps<{
    agent?: MoviePilotAgentHost | null
    pet?: AgentPetContext | null
    api?: PluginApi | null
    pluginId?: string
    sourcePluginId?: string
    previewRoot?: HTMLElement | null
    settingsOverride?: YingSettings
    previewMaxSize?: { width: number; height: number }
    previewPose?: Pose
    previewPeekEdge?: PeekEdge | null
    previewPeekAngle?: number
    calibrationOverride?: Calibration
    showCalibration?: boolean
    mappingsOverride?: ActionMappings
    nativeAction?: string
    replay?: number
  }>(),
  { agent: null, pet: null, api: null, pluginId: '', sourcePluginId: '' },
)

const emit = defineEmits<{ 'load-state': ['loading' | 'ready' | 'error']; 'pack-ready': [SpritePack] }>()

const appearance = ref<{ name: string; aspectRatio: number; eye: PeekEye | null }>({
  name: 'Codex Pet',
  aspectRatio: 192 / 208,
  eye: null,
})
const lookDirections = ref(false)
const artworkReady = ref(false)
const loadedPack = shallowRef<SpritePack | null>(null)
const startupPlayback = computed(() =>
  loadedPack.value ? greetingPlayback(loadedPack.value, props.mappingsOverride) : null,
)
const restAvailable = computed(
  () => artworkReady.value && !!loadedPack.value && supportsRest(loadedPack.value, props.mappingsOverride),
)

function onPackReady(pack: SpritePack) {
  loadedPack.value = pack
  lookDirections.value = supportsLookDirections(pack)
  emit('pack-ready', pack)
}

function onLoadState(state: 'loading' | 'ready' | 'error') {
  artworkReady.value = state === 'ready'
  if (state !== 'ready') lookDirections.value = false
  emit('load-state', state)
}
</script>

<template>
  <AgentPet
    v-bind="props"
    :character-name="appearance.name"
    :aspect-ratio="appearance.aspectRatio"
    :peek-eye="appearance.eye"
    :look-directions="lookDirections"
    :artwork-ready="artworkReady"
    :greeting-playback="startupPlayback"
    :rest-available="restAvailable"
  >
    <template
      #default="{ pose, facingLeft, motionActive, peekEdge, peekFromLeft, gazeAction, greetingRound, greetingComplete }"
    >
      <AgentPetSprite
        v-bind="props"
        :action="stageAction(pose, facingLeft, !!peekEdge).action"
        :mapping-key="stageAction(pose, facingLeft, !!peekEdge).key"
        :native-action="peekEdge ? undefined : (gazeAction ?? props.nativeAction)"
        :motion-active="motionActive"
        :replay="(props.replay ?? 0) + greetingRound"
        :mirror-x="pet?.key === 'builtin-chibiterasu' && !!peekEdge && peekFromLeft"
        :strict-preview="!!props.previewRoot"
        @load-state="onLoadState"
        @pack-ready="onPackReady"
        @appearance="appearance = $event"
        @cycle-complete="greetingComplete($event - (props.replay ?? 0))"
      />
    </template>
  </AgentPet>
</template>
