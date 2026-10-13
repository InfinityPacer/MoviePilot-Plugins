<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import CalibrationControls from '@/editor/CalibrationControls.vue'
import { DEFAULT_CALIBRATION, type Calibration } from '@/sprites/calibration'
import ActionMappingEditor from '@/editor/ActionMappings.vue'
import { ACTION_LABELS, nativeChoices, type ActionMappings } from '@/sprites/mappings'
import { HOST_ACTIONS, HOST_INTENTS, type SpritePack } from '@/sprites/schema'
import { POSES } from '@/stage/poses'
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
  calibration?: Calibration
  mappings?: ActionMappings
  disabled?: boolean
}>()

const emit = defineEmits<{
  error: [boolean]
  'pack-ready': [SpritePack]
  mappings: [ActionMappings]
  calibration: [Calibration]
}>()
const loadedPack = ref<SpritePack | null>(null)
const replay = ref(0)
const original = ref(false)
const displayedCalibration = computed(() => (original.value ? DEFAULT_CALIBRATION : props.calibration))
const previewGroup = ref(props.pet.key === 'ying' ? 'poses' : 'native')
function onPackReady(pack: SpritePack) {
  loadedPack.value = pack
  emit('pack-ready', pack)
}
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
const poseLabels: Record<string, string> = {
  idle: '待机',
  blink: '眨眼',
  talk: '说话',
  think: '思考',
  jump: '跳起',
  wave: '招手',
  held: '被拖起',
  fall: '下落',
  sit: '坐下',
  walk1: '行走第1帧',
  walk2: '行走第2帧',
  walk3: '行走第3帧',
  walk4: '行走第4帧',
  doze: '打盹',
  confused: '疑惑',
  alert: '提醒',
  victory: '开心',
  busy: '执行工具',
}
const animations = computed(() => (loadedPack.value ? nativeChoices(loadedPack.value) : []))
const choices = computed(() => {
  if (previewGroup.value === 'poses') return POSES.map(value => ({ value: `pose:${value}`, title: poseLabels[value] }))
  if (previewGroup.value === 'actions')
    return HOST_ACTIONS.map(value => ({ value: `action:${value}`, title: ACTION_LABELS[value] }))
  if (previewGroup.value === 'intents')
    return HOST_INTENTS.map(value => ({ value: `intent:${value}`, title: ACTION_LABELS[value] }))
  if (previewGroup.value === 'directions')
    return Object.keys(loadedPack.value?.actions ?? {})
      .filter(key => key.startsWith('look-'))
      .map(key => ({ value: `native:${key}`, title: key.slice(5).replace('-', '.') + '°' }))
  return animations.value.map(item => ({ value: `native:${item.value}`, title: item.title }))
})
const nativeAction = computed(() => (action.value.startsWith('native:') ? action.value.slice(7) : undefined))
const rendererAction = computed(() => (action.value.startsWith('action:') ? action.value.slice(7) : null))
const rendererIntent = computed(() => (action.value.startsWith('intent:') ? action.value.slice(7) : 'idle'))
const previewPose = computed(() =>
  nativeAction.value ? 'idle' : action.value.startsWith('pose:') ? (action.value.slice(5) as Pose) : undefined,
)
const events = [
  ['panel.open', '打开助手'],
  ['panel.close', '关闭助手'],
  ['thinking.start', '开始思考'],
  ['thinking.end', '结束思考'],
  ['tool.start', '开始执行工具'],
  ['tool.end', '工具结束'],
  ['awaiting', '等待用户'],
  ['done', '任务完成'],
  ['error', '任务出错'],
  ['preview', '回复预览'],
  ['bubble', '通知气泡'],
]
function playNative(name: string) {
  choose(`native:${name}`)
}
function choose(value: string) {
  action.value = value
  updateAction()
  replay.value++
}
function fireHost(name: string) {
  action.value = 'auto'
  const phase =
    name === 'thinking.start'
      ? 'thinking'
      : name === 'tool.start'
        ? 'tool'
        : name === 'awaiting'
          ? 'awaiting'
          : name === 'done'
            ? 'done'
            : name === 'error'
              ? 'error'
              : 'idle'
  host.patch({ phase, thinking: phase === 'thinking', panelOpen: name === 'panel.open' })
  host.fire(`agent.${name}`, { name: 'preview_tool', text: '预览消息' })
}
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
  host.patch({ phase: action.value === 'auto' ? 'idle' : 'thinking', thinking: false, panelOpen: false })
}
watch(previewGroup, () => choose('auto'))

// 重置或切换 Pet 时使用新的内存存储，避免重新挂载后恢复旧的拖拽位置。
watch([() => props.pet.mode, () => props.pet.key, positionVersion], () => {
  context.value = createMockPet(props.pet.mode, props.pet.key)
})
watch(paused, updateMotion)
watch(
  () => props.pet.key,
  () => {
    onLoadState('loading')
    loadedPack.value = null
    previewGroup.value = props.pet.key === 'ying' ? 'poses' : 'native'
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
        :native-action="nativeAction"
        :mappings-override="mappings"
        :calibration-override="displayedCalibration"
        :show-calibration="!!calibration && !original"
        :replay="replay"
        @pack-ready="onPackReady"
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
          :intent="rendererIntent"
          :native-action="nativeAction"
          :mappings-override="mappings"
          :calibration-override="displayedCalibration"
          :show-calibration="!!calibration && !original"
          :replay="replay"
          @pack-ready="onPackReady"
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
    <footer class="ap-preview__library">
      <div class="ap-inline mb-2">
        <strong>完整动作预览</strong><v-spacer />
        <v-btn size="small" :variant="action === 'auto' ? 'tonal' : 'text'" @click="choose('auto')">自主活动</v-btn>
      </div>
      <v-tabs v-model="previewGroup" density="compact" color="primary">
        <v-tab v-if="pet.key !== 'ying'" value="native">原生动画</v-tab>
        <v-tab v-if="loadedPack?.codex_version === 'v2'" value="directions">视线方向</v-tab>
        <v-tab v-if="pet.mode === 'stage'" value="poses">活动姿态</v-tab>
        <v-tab v-if="pet.mode === 'stage'" value="events">MP 事件</v-tab>
        <v-tab v-if="pet.mode === 'renderer'" value="actions">MP 动作</v-tab>
        <v-tab v-if="pet.mode === 'renderer'" value="intents">入口状态</v-tab>
      </v-tabs>
      <div class="ap-preview__choices">
        <template v-if="previewGroup === 'events'">
          <v-btn v-for="[key, label] in events" :key="key" size="small" variant="tonal" @click="fireHost(key)">{{
            label
          }}</v-btn>
        </template>
        <template v-else>
          <v-btn
            v-for="item in choices"
            :key="item.value"
            size="small"
            :variant="action === item.value ? 'flat' : 'tonal'"
            :color="action === item.value ? 'primary' : undefined"
            :disabled="failed"
            @click="choose(item.value)"
            >{{ item.title }}</v-btn
          >
        </template>
      </div>
      <p class="ap-muted mb-0">
        {{
          previewGroup === 'native' || previewGroup === 'directions'
            ? '直接播放素材原始动画，不受动作映射影响。'
            : '按当前映射预览；自主活动时可拖动 Pet 验证移动交互。'
        }}
      </p>
    </footer>
    <div v-if="loadedPack && !pet.builtin" class="px-4">
      <v-switch v-model="original" label="对照原始显示" density="compact" hide-details />
    </div>
    <CalibrationControls
      v-if="loadedPack && !pet.builtin && calibration"
      :key="pet.key"
      :model-value="calibration"
      :pack-id="pet.key"
      :api="api"
      :plugin-id="pluginId"
      :disabled="disabled"
      @update:model-value="emit('calibration', $event)"
    />
    <ActionMappingEditor
      v-if="loadedPack?.codex_version && !pet.builtin"
      :pack="loadedPack"
      :mode="pet.mode"
      :model-value="mappings ?? loadedPack.action_mappings ?? {}"
      :disabled="disabled"
      @update:model-value="emit('mappings', $event)"
      @preview="playNative"
    />
  </section>
</template>

<style scoped>
.ap-preview__library {
  padding: 12px 16px;
}
.ap-preview__choices {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 0;
  max-height: 240px;
  overflow-y: auto;
}

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
