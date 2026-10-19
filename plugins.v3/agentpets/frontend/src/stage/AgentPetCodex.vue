<script setup lang="ts">
import type { Calibration } from '@/sprites/calibration'
import { ref } from 'vue'

import type { AgentPetContext, MoviePilotAgentHost, PluginApi } from '@/host'
import { stageAction, type ActionMappings } from '@/sprites/mappings'
import type { SpritePack } from '@/sprites/schema'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import type { Pose } from '@/stage/poses'
import type { PeekEdge, PeekEye } from '@/stage/peek'
import type { YingSettings } from '@/stage/settings'
import AgentPet from './AgentPet.vue'

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
</script>

<template>
  <AgentPet
    v-bind="props"
    :character-name="appearance.name"
    :aspect-ratio="appearance.aspectRatio"
    :peek-eye="appearance.eye"
  >
    <template #default="{ pose, facingLeft, motionActive, peekEdge, peekFromLeft }">
      <AgentPetSprite
        v-bind="props"
        :action="stageAction(pose, facingLeft, !!peekEdge).action"
        :mapping-key="stageAction(pose, facingLeft, !!peekEdge).key"
        :native-action="peekEdge ? undefined : props.nativeAction"
        :motion-active="motionActive"
        :mirror-x="pet?.key === 'builtin-chibiterasu' && !!peekEdge && peekFromLeft"
        :strict-preview="!!props.previewRoot"
        @load-state="emit('load-state', $event)"
        @pack-ready="emit('pack-ready', $event)"
        @appearance="appearance = $event"
      />
    </template>
  </AgentPet>
</template>
