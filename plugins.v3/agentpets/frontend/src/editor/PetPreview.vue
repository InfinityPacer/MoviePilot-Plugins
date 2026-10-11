<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { PluginApi } from '@/host'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import AgentPet from '@/stage/AgentPet.vue'
import AgentPetCodex from '@/stage/AgentPetCodex.vue'
import type { YingSettings } from '@/stage/settings'
import type { Pose } from '@/stage/poses'
import type { PetChoice } from './api'

const props = defineProps<{
  pet: PetChoice
  settings: YingSettings
  api: PluginApi | null
  pluginId: string
}>()

const emit = defineEmits<{ error: [boolean] }>()
const failed = ref(false)
function onLoadState(state: 'loading' | 'ready' | 'error') {
  failed.value = state === 'error'
  emit('error', failed.value)
}

const canvas = ref<HTMLElement | null>(null)
const mounted = ref(false)
const paused = ref(false)
const action = ref('auto')
const positionVersion = ref(0)
const host = createMockHost(props.pluginId)
const context = shallowRef(createMockPet(props.pet.mode, props.pet.key))
const actions: Record<string, string> = {
  auto: 'idle',
  wave: 'wave',
  thinking: 'thinking',
  speaking: 'speaking',
  happy: 'happy-jump',
}
const poses: Record<string, Pose> = { wave: 'wave', thinking: 'think', speaking: 'talk', happy: 'victory' }
const rendererAction = computed(() => actions[action.value] ?? 'idle')
const previewPose = computed(() => poses[action.value])
const stageComponent = computed(() => (props.pet.key === 'ying' ? AgentPet : AgentPetCodex))
const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
const reducedMotion = ref(mediaQuery.matches)
let observer: ResizeObserver | undefined

function resize() {
  if (!canvas.value) return
  const { width, height } = canvas.value.getBoundingClientRect()
  host.patch({
    isMobile: window.innerWidth < 600,
    viewport: {
      width: Math.max(1, width),
      height: Math.max(1, height),
      keyboardInset: 0,
      safeArea: { top: 12, right: 16, bottom: 16, left: 16 },
    },
  })
}

function updateMotion() {
  reducedMotion.value = mediaQuery.matches
  host.patch({ motionAllowed: !paused.value && !reducedMotion.value, reducedMotion: reducedMotion.value })
}

function updateAction() {
  host.patch({ phase: action.value === 'auto' ? 'idle' : 'thinking' })
  if (action.value === 'wave') host.fire('agent.panel.open')
  if (action.value === 'happy') host.fire('agent.done')
  if (action.value === 'speaking') host.fire('agent.preview')
}

// 重置或切换 Pet 时使用新的内存存储，避免重新挂载后恢复旧的拖拽位置。
watch([() => props.pet.mode, () => props.pet.key, positionVersion], () => {
  context.value = createMockPet(props.pet.mode, props.pet.key)
})
watch(paused, updateMotion)
watch(action, updateAction)
watch(
  () => props.pet.key,
  () => {
    onLoadState('loading')
    action.value = 'auto'
    updateAction()
  },
)
onMounted(() => {
  resize()
  updateMotion()
  observer = new ResizeObserver(resize)
  if (canvas.value) observer.observe(canvas.value)
  window.addEventListener('resize', resize)
  mediaQuery.addEventListener('change', updateMotion)
  mounted.value = true
})
onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('resize', resize)
  mediaQuery.removeEventListener('change', updateMotion)
  host.dispose()
})
</script>

<template>
  <section class="ap-preview" aria-label="Pet 实时预览">
    <header class="ap-preview__header">
      <div class="ap-inline">
        <span class="ap-live-dot" /><strong>实时预览</strong><span class="ap-muted">{{ pet.name }}</span>
      </div>
      <div class="ap-inline">
        <v-btn
          :icon="paused ? 'mdi-play' : 'mdi-pause'"
          :aria-label="paused ? '播放预览' : '暂停预览'"
          size="small"
          variant="text"
          @click="paused = !paused"
        />
        <v-btn icon="mdi-restore" aria-label="重置预览位置" size="small" variant="text" @click="positionVersion++" />
      </div>
    </header>
    <div ref="canvas" class="ap-preview__canvas" :data-roam="settings.roam">
      <div class="ap-preview__watermark" aria-hidden="true">
        <v-icon icon="mdi-paw-outline" size="40" /><span>你的 Pet，在这里活动</span>
      </div>
      <template v-if="pet.mode === 'stage' && settings.roam === 'surfaces'">
        <div class="v-sheet ap-preview__surface ap-preview__surface--left"><span>小平台</span></div>
        <div class="v-sheet ap-preview__surface ap-preview__surface--right"><span>休息台</span></div>
      </template>
      <div class="ap-preview__floor" aria-hidden="true" />
      <component
        :is="stageComponent"
        v-if="mounted && pet.mode === 'stage'"
        :key="`${pluginId}:${pet.key}:${positionVersion}`"
        :agent="host"
        :pet="context"
        :api="api"
        :plugin-id="pluginId"
        :preview-root="canvas"
        :settings-override="settings"
        :preview-pose="previewPose"
        @load-state="onLoadState"
      />
      <div v-else-if="mounted" class="ap-preview__entry">
        <AgentPetSprite
          :key="`${pluginId}:${pet.key}:${positionVersion}`"
          :agent="host"
          :pet="context"
          :api="api"
          :plugin-id="pluginId"
          :action="rendererAction"
          :motion-active="!paused && !reducedMotion"
          strict-preview
          @load-state="onLoadState"
        />
      </div>
      <v-alert v-if="failed" type="error" variant="tonal" density="compact" class="ap-preview__error"
        >此 Pet 加载失败，请点击右上角重置重试。</v-alert
      >
      <span class="ap-preview__hint">{{
        pet.mode === 'stage' ? '拖动 Pet 试试 · 调整会即时显示' : '助手入口外观 · 试试下方动作'
      }}</span>
    </div>
    <footer class="ap-preview__actions">
      <span class="ap-muted">预览动作</span>
      <v-btn-toggle
        v-model="action"
        mandatory
        density="compact"
        variant="text"
        color="primary"
        class="ap-preview__toggle"
      >
        <v-btn value="auto" size="small">自主活动</v-btn>
        <v-btn value="wave" size="small">招手</v-btn>
        <v-btn value="thinking" size="small">思考</v-btn>
        <v-btn value="speaking" size="small">说话</v-btn>
        <v-btn value="happy" size="small">开心</v-btn>
      </v-btn-toggle>
    </footer>
  </section>
</template>

<style scoped>
.ap-preview {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  background: transparent;
}
.ap-preview__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  font-size: 13px;
}
.ap-preview__error {
  position: absolute;
  left: 16px;
  right: 16px;
  top: 42%;
  z-index: 1;
}
.ap-preview__canvas {
  position: relative;
  isolation: isolate;
  contain: paint;
  overflow: hidden;
  min-height: 330px;
  height: clamp(330px, 51vh, 530px);
  background-image: radial-gradient(rgba(var(--v-theme-on-surface), 0.09) 0.8px, transparent 0.8px);
  background-size: 20px 20px;
}
.ap-preview__watermark {
  position: absolute;
  top: 26px;
  left: 0;
  right: 0;
  display: grid;
  justify-items: center;
  gap: 8px;
  color: rgba(var(--v-theme-on-surface), 0.22);
  font-size: 12px;
  pointer-events: none;
}
.ap-preview__surface {
  position: absolute;
  width: 36%;
  min-width: 120px;
  height: 38px;
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
  border-top: 3px solid rgba(var(--v-theme-primary), 0.4);
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.04);
  color: rgba(var(--v-theme-on-surface), 0.4);
  text-align: center;
  font-size: 11px;
  padding-top: 8px;
}
.ap-preview__surface--left {
  left: 5%;
  top: 69%;
}
.ap-preview__surface--right {
  right: 5%;
  top: 55%;
}
.ap-preview__floor {
  position: absolute;
  bottom: 15px;
  left: 16px;
  right: 16px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  pointer-events: none;
}
.ap-preview__entry {
  position: absolute;
  width: 144px;
  height: 156px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -35%);
}
.ap-preview__hint {
  position: absolute;
  left: 12px;
  bottom: 0;
  right: 12px;
  text-align: center;
  font-size: 10px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  pointer-events: none;
}
.ap-preview__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 4px 12px;
  padding: 10px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  font-size: 12px;
}
.ap-preview__toggle {
  max-width: 100%;
  height: auto;
  flex-wrap: wrap;
}
.ap-preview__toggle :deep(.v-btn) {
  min-width: 48px;
  border-radius: 6px !important;
}
@media (max-width: 760px) {
  .ap-preview__canvas {
    height: 330px;
  }
  .ap-preview__header {
    padding: 6px 10px;
  }
}
</style>
