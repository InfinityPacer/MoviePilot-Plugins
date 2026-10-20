<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'

import {
  loadEditor,
  loadHostSelection,
  savePetSettings,
  saveSharedSettings,
  saveMappings,
  saveCalibration,
  type EditorSnapshot,
  type HostSelection,
} from '@/editor/api'
import { PACK_UPDATED_EVENT, sameMappings, type ActionMappings } from '@/sprites/mappings'
import { parseCalibration, sameCalibration, type Calibration } from '@/sprites/calibration'
import type { SpritePack } from '@/sprites/schema'
import PetPreview from '@/editor/PetPreview.vue'
import { usePetSettings } from '@/editor/settings'
import { builtinAvatar } from '@/editor/avatars'
import { useEditorPresence } from '@/editor/presence'
import '@/editor/ui.css'
import { AGENT_HOST_KEY, HOST_UNSUPPORTED_MESSAGE, type MoviePilotAgentHost, type PluginApi } from '@/host'
import { SETTINGS_EVENT } from '@/stage/settings'
import { normalizePeekAngles } from '@/stage/peek'
import StageSettings from '@/stage/StageSettings.vue'

const props = withDefaults(
  defineProps<{ api?: PluginApi | null; pluginId?: string; sourcePluginId?: string; show_switch?: boolean }>(),
  { api: null, pluginId: '', sourcePluginId: '', show_switch: true },
)
const emit = defineEmits<{ close: []; switch: []; layout: [{ maxWidth: string }] }>()
emit('layout', { maxWidth: '72rem' })
const agent = inject<MoviePilotAgentHost | null>(AGENT_HOST_KEY, null)
useEditorPresence()
const snapshot = ref<EditorSnapshot | null>(null)
const avatar = builtinAvatar('ying')
const avatarFailed = ref(false)
const selection = ref<HostSelection | null>(null)
const selectedKey = ref('')
const activity = usePetSettings(selectedKey)
const draft = activity.draft
const settingsConflict = activity.hasConflict
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const hostError = ref('')
const feedback = ref('')
const feedbackType = ref<'success' | 'warning' | 'error'>('success')
const currentPet = computed(() => snapshot.value?.pets.find(pet => pet.key === selectedKey.value) ?? null)
const previewVersion = ref(0)
const calibrationDrafts = ref<Record<string, Calibration>>({})
const calibrationSaved = ref<Record<string, Calibration>>({})
const calibrationConflicts = ref<Record<string, Calibration>>({})
const calibrationDirtyKeys = computed(() =>
  Object.keys(calibrationDrafts.value).filter(
    key => !sameCalibration(calibrationDrafts.value[key], calibrationSaved.value[key]),
  ),
)
const mappingDrafts = ref<Record<string, ActionMappings>>({})
const mappingSaved = ref<Record<string, ActionMappings>>({})
const mappingConflicts = ref<Record<string, ActionMappings>>({})
const conflictingNames = computed(() =>
  [...new Set([...Object.keys(mappingConflicts.value), ...Object.keys(calibrationConflicts.value)])].map(
    key => snapshot.value?.pets.find(pet => pet.key === key)?.name ?? key,
  ),
)
const mappingDirtyKeys = computed(() =>
  Object.keys(mappingDrafts.value).filter(
    key => !sameMappings(mappingDrafts.value[key], mappingSaved.value[key] ?? {}),
  ),
)
function onPackReady(pack: SpritePack) {
  const key = selectedKey.value
  const latestCalibration = parseCalibration(pack.calibration)
  const savedCalibration = calibrationSaved.value[key]
  if (savedCalibration && !sameCalibration(calibrationDrafts.value[key], savedCalibration)) {
    if (!sameCalibration(latestCalibration, savedCalibration)) calibrationConflicts.value[key] = latestCalibration
    else delete calibrationConflicts.value[key]
  } else {
    calibrationSaved.value[key] = latestCalibration
    calibrationDrafts.value[key] = { ...latestCalibration }
    delete calibrationConflicts.value[key]
  }
  if (!pack.codex_version || currentPet.value?.builtin) return
  const latest = { ...pack.action_mappings }
  const baseline = mappingSaved.value[key]
  const preserve = baseline && !sameMappings(mappingDrafts.value[key] ?? {}, baseline)
  if (preserve) {
    // 草稿仍以最初读取的版本为基准，重新加载不能悄悄绕过后端旧值检查。
    if (!sameMappings(latest, baseline)) mappingConflicts.value[key] = latest
    else delete mappingConflicts.value[key]
    return
  }
  delete mappingConflicts.value[key]
  mappingSaved.value[key] = latest
  mappingDrafts.value[key] = { ...latest }
}
const dirty = computed(
  () => activity.dirty.value || mappingDirtyKeys.value.length > 0 || calibrationDirtyKeys.value.length > 0,
)
const changedNames = computed(() =>
  [
    activity.dirtyKeys.value.length ? `${activity.dirtyKeys.value.length} 只 Pet 的独立设置` : '',
    activity.sharedDirty.value ? '共享活动方式与范围' : '',
    mappingDirtyKeys.value.length ? `${mappingDirtyKeys.value.length} 只 Pet 的动作映射` : '',
    calibrationDirtyKeys.value.length ? `${calibrationDirtyKeys.value.length} 只 Pet 的显示校准` : '',
  ].filter(Boolean),
)
const blocked = computed(() => loading.value || busy.value || !props.api || !currentPet.value || !!error.value)
const defaultName = computed(() => {
  if (!selection.value) return '暂不可读'
  if (!selection.value.defaultId) return '内置机器人'
  return (
    snapshot.value?.pets.find(pet => `${props.pluginId}:${pet.key}` === selection.value?.defaultId)?.name ??
    '其他插件形象'
  )
})
let disposed = false
let requestVersion = 0
let operationVersion = 0

async function refresh(reset = false) {
  if (busy.value) return
  const version = ++requestVersion
  const id = props.pluginId
  loading.value = true
  error.value = ''
  hostError.value = ''
  const results = await Promise.allSettled([
    loadEditor(props.api, id),
    props.api ? loadHostSelection(props.api) : Promise.reject(new Error('页面连接尚未就绪')),
  ])
  if (disposed || version !== requestVersion || id !== props.pluginId) return
  const [editor, host] = results
  if (host.status === 'fulfilled') selection.value = host.value
  else {
    selection.value = null
    hostError.value = '当前系统默认形象暂不可读，仍可预览和保存调整。'
  }
  if (editor.status === 'fulfilled') {
    snapshot.value = editor.value
    for (const values of [calibrationDrafts, calibrationSaved, calibrationConflicts]) {
      for (const key of Object.keys(values.value))
        if (!editor.value.pets.some(pet => pet.key === key)) delete values.value[key]
    }
    for (const key of Object.keys(mappingDrafts.value)) {
      if (!editor.value.pets.some(pet => pet.key === key)) {
        delete mappingDrafts.value[key]
        delete mappingSaved.value[key]
        delete mappingConflicts.value[key]
      }
    }
    previewVersion.value++
    activity.receive(editor.value, reset)
    if (!editor.value.pets.some(pet => pet.key === selectedKey.value)) {
      selectedKey.value =
        editor.value.pets.find(pet => `${id}:${pet.key}` === selection.value?.defaultId)?.key ??
        editor.value.pets[0]?.key ??
        ''
    }
  } else error.value = '无法读取 Pet 与活动设置，请刷新重试。'
  loading.value = false
}

watch(
  () => props.pluginId,
  () => {
    operationVersion++
    busy.value = false
    snapshot.value = null
    selection.value = null
    selectedKey.value = ''
    activity.clear()
    calibrationDrafts.value = {}
    calibrationSaved.value = {}
    calibrationConflicts.value = {}
    mappingDrafts.value = {}
    mappingSaved.value = {}
    mappingConflicts.value = {}
    feedback.value = ''
    void refresh(true)
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  disposed = true
  requestVersion++
  operationVersion++
})

function restore() {
  calibrationSaved.value = { ...calibrationSaved.value, ...calibrationConflicts.value }
  calibrationConflicts.value = {}
  calibrationDrafts.value = Object.fromEntries(
    Object.entries(calibrationSaved.value).map(([key, value]) => [key, { ...value }]),
  )
  mappingSaved.value = { ...mappingSaved.value, ...mappingConflicts.value }
  mappingConflicts.value = {}
  activity.restore()
  mappingDrafts.value = Object.fromEntries(
    Object.entries(mappingSaved.value).map(([key, value]) => [key, { ...value }]),
  )
  feedback.value = ''
}

async function save() {
  if (blocked.value || conflictingNames.value.length || activity.hasConflict.value || !props.api || !currentPet.value)
    return
  const api = props.api
  const id = props.pluginId
  const shared = activity.sharedDirty.value
    ? {
        values: { ...activity.sharedDraft.value },
        expected: { ...activity.sharedSaved.value },
      }
    : null
  const appearances = activity.dirtyKeys.value.map(key => ({
    key,
    values: { ...activity.drafts.value[key] },
    expected: { ...activity.saved.value[key] },
  }))
  const mappings = mappingDirtyKeys.value.map(key => ({
    key,
    values: { ...mappingDrafts.value[key] },
    expected: { ...mappingSaved.value[key] },
  }))
  const calibrations = calibrationDirtyKeys.value.map(key => ({
    key,
    value: { ...calibrationDrafts.value[key] },
    expected: { ...calibrationSaved.value[key] },
  }))
  const version = ++operationVersion
  const current = () => !disposed && version === operationVersion && id === props.pluginId
  const updatedPacks = new Set<string>()
  busy.value = true
  feedback.value = ''
  try {
    if (shared) {
      const result = await saveSharedSettings(api, id, shared.values, shared.expected)
      if (!current()) return
      activity.sharedSaved.value = { ...result }
      agent?.emit?.(SETTINGS_EVENT, { ...result })
    }
    for (const item of appearances) {
      if (!current()) return
      const result = await savePetSettings(api, id, item.key, item.values, item.expected)
      if (!current()) return
      activity.saved.value[item.key] = { ...result }
      agent?.emit?.(SETTINGS_EVENT, { key: item.key, ...result, peek_angles: normalizePeekAngles(result.peek_angles) })
    }
    for (const item of mappings) {
      if (!current()) return
      const result = await saveMappings(api, id, item.key, item.values, item.expected)
      if (!current()) return
      mappingSaved.value[item.key] = { ...result }
      updatedPacks.add(item.key)
    }
    for (const item of calibrations) {
      if (!current()) return
      const result = await saveCalibration(api, id, item.key, item.value, item.expected)
      if (!current()) return
      calibrationSaved.value[item.key] = result
      updatedPacks.add(item.key)
    }
    feedbackType.value = 'success'
    feedback.value = agent ? '调整已保存，并已通知当前页面更新。' : '调整已保存。'
  } catch (reason) {
    if (!current()) return
    feedbackType.value = 'error'
    feedback.value = reason instanceof Error ? reason.message : '操作未完成，请重试'
  } finally {
    if (current()) {
      for (const key of updatedPacks) agent?.emit?.(PACK_UPDATED_EVENT, { key })
      busy.value = false
    }
  }
}
</script>

<template>
  <section class="ap-page" data-agentpets-editor>
    <header class="ap-header">
      <div class="ap-brand">
        <img v-if="!avatarFailed" :src="avatar" alt="" class="ap-brand__avatar" @error="avatarFailed = true" />
        <span v-else class="ap-brand__avatar d-flex align-center justify-center" aria-hidden="true">
          <v-icon icon="mdi-paw-outline" color="primary" size="28" />
        </span>
        <div>
          <div class="ap-eyebrow">MoviePilot / 调整与预览</div>
          <h1>助手形象</h1>
        </div>
      </div>
      <div class="ap-header__actions">
        <v-btn
          icon="mdi-refresh"
          aria-label="刷新形象列表"
          variant="text"
          size="small"
          :loading="loading"
          :disabled="busy"
          @click="refresh()"
        />
        <v-btn
          v-if="show_switch"
          icon="mdi-cog-outline"
          aria-label="打开插件配置"
          variant="text"
          size="small"
          :disabled="busy"
          @click="emit('switch')"
        />
        <v-btn
          icon="mdi-close"
          aria-label="关闭详情页"
          variant="text"
          size="small"
          :disabled="busy"
          @click="emit('close')"
        />
      </div>
    </header>
    <div class="ap-page__content">
      <div class="ap-page__notices">
        <v-alert v-if="!agent" type="warning" variant="tonal" density="compact" class="ap-result">{{
          HOST_UNSUPPORTED_MESSAGE
        }}</v-alert>
        <v-alert v-if="error" type="error" variant="tonal" density="compact" class="ap-result">{{ error }}</v-alert>
        <v-alert v-if="hostError" type="warning" variant="tonal" density="compact" class="ap-result">{{
          hostError
        }}</v-alert>
        <v-alert v-if="settingsConflict" type="warning" variant="tonal" density="compact" class="ap-result">
          大小、速度、偷看角度或共享活动设置已在其他页面更改。已保留草稿；请点击「撤销」载入最新值后重新调整。
        </v-alert>
        <v-alert v-if="conflictingNames.length" type="warning" variant="tonal" density="compact" class="ap-result">
          {{ conflictingNames.join('、') }}
          的素材调整已在其他页面更改。已保留你的草稿；请点击「撤销」载入最新值后重新调整。
        </v-alert>
        <v-alert
          v-if="feedback"
          :type="feedbackType"
          variant="tonal"
          density="compact"
          class="ap-result"
          role="status"
          >{{ feedback }}</v-alert
        >
      </div>
      <div v-if="loading && !snapshot" class="ap-empty">
        <v-progress-circular indeterminate color="primary" /><span class="ap-muted">正在准备你的 Pet…</span>
      </div>
      <div v-else-if="snapshot && currentPet" class="ap-editor-grid">
        <div class="ap-page__selector">
          <v-select
            v-model="selectedKey"
            :items="snapshot.pets"
            item-title="name"
            item-value="key"
            label="预览形象"
            density="compact"
            variant="outlined"
            hide-details
            :disabled="blocked"
          />
          <span class="ap-muted"
            >{{ currentPet.mode === 'stage' ? '自由活动的角色' : '助手入口的形象' }} ·
            {{ currentPet.builtin ? '内置' : '已导入' }}</span
          >
        </div>
        <PetPreview
          :key="`${props.pluginId}:${previewVersion}`"
          :pet="currentPet"
          :settings="draft"
          :api="props.api"
          :plugin-id="props.pluginId"
          :mappings="mappingDrafts[selectedKey]"
          :calibration="calibrationDrafts[selectedKey]"
          :disabled="blocked"
          initial-tab="activity"
          @pack-ready="onPackReady"
          @mappings="mappingDrafts[selectedKey] = $event"
          @calibration="calibrationDrafts[selectedKey] = $event"
          @settings="draft = $event"
        >
          <template #activity>
            <p v-if="currentPet.description" class="ap-muted mb-3">{{ currentPet.description }}</p>
            <section class="ap-control-panel">
              <h2 class="ap-section-title">{{ currentPet.mode === 'stage' ? '活动调整' : '入口外观' }}</h2>
              <StageSettings
                v-if="currentPet.mode === 'stage'"
                v-model="draft"
                :live-preview="true"
                :disabled="blocked"
                :preview-only="true"
              />
              <p v-else class="ap-muted mb-0">
                此 Pet 显示在助手入口，位置与拖拽由 MP 控制。可在预览区切换动作，在 MP 设置中选择使用。
              </p>
            </section>
            <section class="ap-control-panel">
              <h2 class="ap-section-title">在 MP 中使用</h2>
              <div class="ap-muted">当前系统默认</div>
              <strong>{{ defaultName }}</strong>
              <p class="ap-muted mt-3 mb-0">保存调整后，在「设定 → 系统 → 智能助手配置 → 助手形象」中选择 Pet。</p>
              <v-alert v-if="!snapshot.enabled" type="info" variant="tonal" density="compact" class="mt-3"
                >先在配置页启用插件，形象才会出现在 MP 的可选列表中。</v-alert
              >
            </section>
          </template>
        </PetPreview>
      </div>
      <div v-else-if="!loading" class="ap-empty">
        <v-icon icon="mdi-paw-outline" size="44" color="primary" /><strong>{{
          error ? 'Pet 暂时未能加载' : '还没有可预览的 Pet'
        }}</strong
        ><v-btn
          v-if="error || show_switch"
          variant="tonal"
          color="primary"
          @click="error ? refresh() : emit('switch')"
          >{{ error ? '重新加载' : '前往素材管理' }}</v-btn
        >
        <p v-else class="ap-muted">请从「插件 → 助手形象 → 设置」打开素材管理。</p>
      </div>
    </div>
    <footer class="ap-footer">
      <span v-if="dirty" class="ap-change"
        ><v-icon icon="mdi-circle" size="7" />未保存 · {{ changedNames.join('、') }}</span
      >
      <span v-else class="ap-muted">预览中的调整不会自动保存</span>
      <div class="ap-footer__actions">
        <v-btn
          variant="text"
          :disabled="blocked || (!dirty && !conflictingNames.length && !settingsConflict)"
          @click="restore"
          >撤销</v-btn
        >
        <v-btn
          variant="flat"
          color="primary"
          prepend-icon="mdi-content-save-outline"
          :disabled="blocked || !dirty || conflictingNames.length > 0 || settingsConflict"
          :loading="busy"
          @click="save"
          >保存调整</v-btn
        >
      </div>
    </footer>
  </section>
</template>
