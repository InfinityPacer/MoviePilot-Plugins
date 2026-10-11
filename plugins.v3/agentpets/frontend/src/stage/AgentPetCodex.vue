<script setup lang="ts">
import { ref } from 'vue'

import type { AgentPetContext, MoviePilotAgentHost, PluginApi } from '@/host'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import type { Pose } from '@/stage/poses'
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
    previewPose?: Pose
  }>(),
  { agent: null, pet: null, api: null, pluginId: '', sourcePluginId: '' },
)

const emit = defineEmits<{ 'load-state': ['loading' | 'ready' | 'error'] }>()

const appearance = ref({ name: 'Codex Pet', aspectRatio: 192 / 208 })
const POSE_ACTIONS: Partial<Record<Pose, string>> = {
  wave: 'wave',
  held: 'thinking',
  fall: 'jumping',
  jump: 'jumping',
  talk: 'speaking',
  think: 'thinking',
  busy: 'charge',
  victory: 'success',
  confused: 'error',
  alert: 'warning',
  doze: 'sleep',
}

function actionForPose(pose: Pose, facingLeft: boolean): string {
  if (pose.startsWith('walk')) return facingLeft ? 'running-left' : 'running-right'
  return POSE_ACTIONS[pose] ?? 'idle'
}
</script>

<template>
  <AgentPet v-bind="props" :character-name="appearance.name" :aspect-ratio="appearance.aspectRatio">
    <template #default="{ pose, facingLeft, motionActive }">
      <AgentPetSprite
        v-bind="props"
        :action="actionForPose(pose, facingLeft)"
        :motion-active="motionActive"
        :strict-preview="!!props.previewRoot"
        @load-state="emit('load-state', $event)"
        @appearance="appearance = $event"
      />
    </template>
  </AgentPet>
</template>
