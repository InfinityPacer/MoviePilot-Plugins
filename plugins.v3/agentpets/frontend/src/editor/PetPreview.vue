<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import CalibrationControls from '@/editor/CalibrationControls.vue'
import { DEFAULT_CALIBRATION, type Calibration } from '@/sprites/calibration'
import ActionMappingEditor from '@/editor/ActionMappings.vue'
import { ACTION_LABELS, nativeChoices, stageAction, type ActionMappings } from '@/sprites/mappings'
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

const props = withDefaults(
  defineProps<{
    pet: PetChoice
    settings: YingSettings
    api: PluginApi | null
    pluginId: string
    calibration?: Calibration
    mappings?: ActionMappings
    disabled?: boolean
    initialTab?: 'activity' | 'animations' | 'calibration' | 'mappings'
  }>(),
  { initialTab: 'animations' },
)

const emit = defineEmits<{
  error: [boolean]
  'pack-ready': [SpritePack]
  mappings: [ActionMappings]
  calibration: [Calibration]
}>()
const loadedPack = ref<SpritePack | null>(null)
const replay = ref(0)
const original = ref(false)
const editorTab = ref(props.initialTab)
const expanded = ref(false)
const previewMode = ref<'debug' | 'movement'>('debug')
const previewSettings = computed<YingSettings>(() =>
  previewMode.value === 'debug' ? { ...props.settings, movement: 'fixed', roam: 'free' } : props.settings,
)
const previewMaxSize = ref({ width: 280, height: 220 })
const playing = ref('自主动作')
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
function newContext() {
  const pet = createMockPet(props.pet.mode, props.pet.key)
  if (previewMode.value === 'debug') void pet.storage?.set?.({ roam: 'free', xRatio: 0.5, yRatio: 0.5 })
  return pet
}
const context = shallowRef(newContext())
const comparisonContext = computed(() => createMockPet('renderer', props.pet.key))
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
function playNative(name: string, trigger?: string) {
  choose(`native:${name}`)
  if (trigger) playing.value = `${trigger} → ${ACTION_LABELS[name] ?? name}`
}
function choose(value: string) {
  action.value = value
  playing.value =
    value === 'auto'
      ? '自主动作'
      : (choices.value.find(item => item.value === value)?.title ?? value.slice(value.indexOf(':') + 1))
  updateAction()
  replay.value++
}
function fireHost(name: string) {
  action.value = 'auto'
  playing.value = events.find(item => item[0] === name)?.[1] ?? name
  replay.value++
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
  previewMaxSize.value = { width: Math.max(1, width - 32), height: Math.max(1, height - 40) }
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
watch([() => props.pet.mode, () => props.pet.key, positionVersion, previewMode], () => {
  context.value = newContext()
})
watch(paused, updateMotion)
watch(
  () => props.pet.key,
  () => {
    onLoadState('loading')
    loadedPack.value = null
    previewGroup.value = props.pet.key === 'ying' ? 'poses' : 'native'
    action.value = 'auto'
    playing.value = '自主动作'
    original.value = false
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
  <section class="ap-preview" :class="{ 'ap-preview--expanded': expanded }" aria-label="Pet 实时预览">
    <div class="ap-preview__viewer">
      <header class="ap-preview__header">
        <div class="ap-inline"><span class="ap-live-dot" /><strong>实时预览</strong></div>
        <v-btn size="small" variant="text" :aria-pressed="expanded" @click="expanded = !expanded">
          {{ expanded ? '收起预览' : '放大预览' }}
        </v-btn>
      </header>
      <div v-if="pet.mode === 'stage'" class="ap-preview__mode">
        <v-btn-toggle
          v-model="previewMode"
          mandatory
          divided
          density="compact"
          color="primary"
          variant="outlined"
          aria-label="预览模式"
        >
          <v-btn value="debug" size="small">动作调试</v-btn>
          <v-btn value="movement" size="small">运动测试</v-btn>
        </v-btn-toggle>
      </div>
      <div class="ap-preview__canvases" :class="{ 'ap-preview__canvases--compare': original }">
        <div
          ref="canvas"
          class="ap-preview__canvas"
          :class="{ 'ap-preview__canvas--debug': previewMode === 'debug' }"
          :data-roam="previewSettings.roam"
        >
          <template v-if="pet.mode === 'stage' && previewMode === 'movement' && settings.roam === 'surfaces'">
            <div class="v-sheet ap-preview__surface ap-preview__surface--left"><span>小平台</span></div>
            <div class="v-sheet ap-preview__surface ap-preview__surface--right"><span>休息台</span></div>
          </template>
          <div class="ap-preview__floor" aria-hidden="true" />
          <component
            :is="stageComponent"
            v-if="mounted && pet.mode === 'stage'"
            :key="`${pluginId}:${pet.key}:${positionVersion}:${previewMode}`"
            :agent="host"
            :pet="context"
            :api="api"
            :plugin-id="pluginId"
            :preview-root="canvas"
            :preview-max-size="previewMaxSize"
            :settings-override="previewSettings"
            :preview-pose="previewPose"
            :native-action="nativeAction"
            :mappings-override="mappings"
            :calibration-override="calibration"
            :show-calibration="editorTab === 'calibration' && !!calibration"
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
              :calibration-override="calibration"
              :show-calibration="editorTab === 'calibration' && !!calibration"
              :replay="replay"
              :motion-active="!paused && !reducedMotion"
              strict-preview
              @pack-ready="onPackReady"
              @load-state="onLoadState"
            />
          </div>
          <v-alert v-if="failed" type="error" variant="tonal" density="compact" class="ap-preview__error"
            >此 Pet 加载失败，请点击重置重试。</v-alert
          >
          <span class="ap-preview__hint">{{
            original ? '当前校准' : previewMode === 'debug' ? '居中播放 · 不会自行走开' : '拖动 Pet · 测试移动与跳跃'
          }}</span>
        </div>
        <div v-if="original && loadedPack" class="ap-preview__original" aria-label="原始显示对照">
          <div class="ap-preview__entry">
            <AgentPetSprite
              :agent="host"
              :pet="comparisonContext"
              :api="api"
              :plugin-id="pluginId"
              :action="previewPose ? stageAction(previewPose, false).action : rendererAction"
              :mapping-key="previewPose ? stageAction(previewPose, false).key : undefined"
              :intent="rendererIntent"
              :native-action="nativeAction"
              :mappings-override="mappings"
              :calibration-override="DEFAULT_CALIBRATION"
              :replay="replay"
              :motion-active="!paused && !reducedMotion"
              strict-preview
            />
          </div>
          <span class="ap-preview__hint">原始显示</span>
        </div>
      </div>
      <div class="ap-preview__playback">
        <span class="ap-preview__playing" role="status">{{ paused ? '已暂停' : '正在播放' }}：{{ playing }}</span>
        <div class="ap-inline">
          <v-btn
            :icon="paused ? 'mdi-play' : 'mdi-pause'"
            :aria-label="paused ? '播放预览' : '暂停预览'"
            size="small"
            variant="text"
            @click="paused = !paused"
          />
          <v-btn icon="mdi-replay" aria-label="重播当前动作" size="small" variant="text" @click="replay++" />
          <v-btn icon="mdi-restore" aria-label="重置预览位置" size="small" variant="text" @click="positionVersion++" />
        </div>
      </div>
      <v-switch
        v-if="loadedPack && !pet.builtin"
        v-model="original"
        label="对照原始显示"
        density="compact"
        hide-details
        class="ap-preview__comparison"
      />
    </div>
    <div class="ap-preview__editor">
      <v-tabs v-model="editorTab" density="compact" color="primary" class="ap-preview__tabs">
        <v-tab value="activity">活动</v-tab>
        <v-tab value="animations">动作试播</v-tab>
        <v-tab value="calibration">校准</v-tab>
        <v-tab value="mappings">映射</v-tab>
      </v-tabs>
      <div class="ap-preview__scroll">
        <div v-show="editorTab === 'activity'" class="ap-preview__panel">
          <slot name="activity"><p class="ap-muted">活动设置在详情页中调整，预览不会自动保存。</p></slot>
        </div>
        <div v-show="editorTab === 'animations'" class="ap-preview__library">
          <div class="ap-inline mb-2">
            <strong>完整动作预览</strong><v-spacer />
            <v-btn size="small" :variant="action === 'auto' ? 'tonal' : 'text'" @click="choose('auto')">自主动作</v-btn>
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
                : '按当前映射预览；运动测试中可拖动 Pet。'
            }}
          </p>
        </div>
        <div v-show="editorTab === 'calibration'">
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
          <p v-else class="ap-preview__panel ap-muted">
            {{ pet.builtin ? '内置形象无需显示校准。' : '素材加载后可调整显示区域与脚底基线。' }}
          </p>
        </div>
        <div v-show="editorTab === 'mappings'">
          <ActionMappingEditor
            v-if="loadedPack?.codex_version && !pet.builtin"
            :pack="loadedPack"
            :mode="pet.mode"
            :model-value="mappings ?? loadedPack.action_mappings ?? {}"
            :disabled="disabled"
            @update:model-value="emit('mappings', $event)"
            @preview="playNative"
          />
          <p v-else class="ap-preview__panel ap-muted">此形象使用内置动作，无需设置动作映射。</p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.ap-preview {
  --ap-preview-width: clamp(280px, 28vw, 300px);
  --ap-canvas-height: 260px;
  display: grid;
  grid-template-columns: var(--ap-preview-width) minmax(0, 1fr);
  gap: 14px;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: transparent;
}
.ap-preview--expanded {
  --ap-preview-width: clamp(320px, 40vw, 480px);
  --ap-canvas-height: clamp(260px, 42dvh, 400px);
}
.ap-preview__viewer {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  align-self: start;
  max-height: 100%;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  /* 调试时需要稳定底色，避免宿主壁纸干扰素材和小字。 */
  background: rgba(var(--v-theme-surface), 0.94);
}
.ap-preview__header {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  padding: 8px 10px;
  font-size: 13px;
}
.ap-preview__mode {
  flex: 0 0 auto;
  padding: 0 10px 8px;
}
.ap-preview__canvases {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  height: var(--ap-canvas-height);
  flex: 0 1 var(--ap-canvas-height);
  min-height: 0;
}
.ap-preview__canvases--compare {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.ap-preview__canvas,
.ap-preview__viewer :deep(.agent-pet-sprites) {
  min-width: 0;
  min-height: 0;
}
/* 两块画布都必须建立坐标边界；角色、底线和提示不能定位到宿主弹窗。 */
.ap-preview__canvas,
.ap-preview__original {
  position: relative;
  isolation: isolate;
  contain: paint;
  overflow: hidden;
  min-width: 0;
  min-height: 0;
  background-color: rgba(var(--v-theme-on-surface), 0.025);
  background-image: radial-gradient(rgba(var(--v-theme-on-surface), 0.09) 0.8px, transparent 0.8px);
  background-size: 20px 20px;
}
.ap-preview__original {
  border-left: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity));
}
.ap-preview__canvas--debug :deep(.agent-pet-ying__character) {
  pointer-events: none;
}
.ap-preview__entry {
  position: absolute;
  width: min(144px, calc(100% - 32px));
  height: min(156px, calc(100% - 40px));
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}
.ap-preview__hint {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 4px;
  text-align: center;
  font-size: 10px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  pointer-events: none;
}
.ap-preview__surface {
  position: absolute;
  width: 36%;
  height: 28px;
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
  border-top: 3px solid rgba(var(--v-theme-primary), 0.4);
  border-radius: 6px;
  background: rgba(var(--v-theme-primary), 0.04);
  color: rgba(var(--v-theme-on-surface), 0.4);
  text-align: center;
  font-size: 10px;
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
  bottom: 18px;
  left: 16px;
  right: 16px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  pointer-events: none;
}
.ap-preview__error {
  position: absolute;
  inset: 12px;
  z-index: 1;
  overflow: auto;
}
.ap-preview__playback {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  padding: 6px 10px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.ap-preview__playing {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.ap-preview__comparison {
  flex: 0 0 auto;
  padding: 0 10px;
}
.ap-preview__editor {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  background: rgba(var(--v-theme-surface), 0.94);
}
.ap-preview__tabs {
  flex: 0 0 auto;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.ap-preview__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.ap-preview__panel,
.ap-preview__library {
  padding: 16px;
}
.ap-preview__choices {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 0;
}
@media (max-width: 760px) {
  .ap-preview {
    display: flex;
    flex-direction: column;
    gap: 8px;
    --ap-canvas-height: clamp(160px, 24dvh, 200px);
  }
  .ap-preview--expanded {
    --ap-canvas-height: clamp(200px, 34dvh, 320px);
  }
  .ap-preview__viewer {
    flex: 0 1 auto;
    align-self: stretch;
  }
  .ap-preview__header {
    padding: 2px 8px;
  }
  .ap-preview__mode {
    padding: 0 8px 4px;
  }
  .ap-preview__playback {
    padding: 0 8px;
    flex-wrap: nowrap;
    gap: 4px;
  }
  .ap-preview__playing {
    flex: 1;
    min-width: 0;
    font-size: 11px;
  }
  .ap-preview__comparison {
    padding: 0 8px;
  }
  .ap-preview__editor {
    flex: 1;
    min-height: min(120px, 20dvh);
  }
  .ap-preview__panel,
  .ap-preview__library {
    padding: 12px;
  }
}
@media (max-height: 600px) and (max-width: 760px) {
  .ap-preview {
    --ap-canvas-height: clamp(100px, 20dvh, 140px);
  }
  .ap-preview--expanded {
    --ap-canvas-height: clamp(140px, 30dvh, 200px);
  }
}
</style>
