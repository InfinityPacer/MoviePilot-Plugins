<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'

import {
  loadEditor,
  loadHostSelection,
  petImage,
  sameSettings,
  saveSettings,
  saveMappings,
  saveCalibration,
  type EditorSnapshot,
  type HostSelection,
} from '@/editor/api'
import { PACK_UPDATED_EVENT, sameMappings, type ActionMappings } from '@/sprites/mappings'
import { parseCalibration, sameCalibration, type Calibration } from '@/sprites/calibration'
import type { SpritePack } from '@/sprites/schema'
import PetPreview from '@/editor/PetPreview.vue'
import '@/editor/ui.css'
import { AGENT_HOST_KEY, HOST_UNSUPPORTED_MESSAGE, type MoviePilotAgentHost, type PluginApi } from '@/host'
import { DEFAULT_SETTINGS, SETTINGS_EVENT, type YingSettings } from '@/stage/settings'
import StageSettings from '@/stage/StageSettings.vue'

const props = withDefaults(defineProps<{ api?: PluginApi | null; pluginId?: string; sourcePluginId?: string }>(), {
  api: null,
  pluginId: '',
  sourcePluginId: '',
})
const emit = defineEmits<{ close: []; switch: []; layout: [{ maxWidth: string }] }>()
emit('layout', { maxWidth: '76rem' })
const agent = inject<MoviePilotAgentHost | null>(AGENT_HOST_KEY, null)
const snapshot = ref<EditorSnapshot | null>(null)
const selection = ref<HostSelection | null>(null)
const selectedKey = ref('')
const draft = ref<YingSettings>({ ...DEFAULT_SETTINGS })
const saved = ref<YingSettings>({ ...DEFAULT_SETTINGS })
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
  if (!currentPet.value?.builtin) {
    const latest = parseCalibration(pack.calibration)
    const baseline = calibrationSaved.value[key]
    if (baseline && !sameCalibration(calibrationDrafts.value[key], baseline)) {
      if (!sameCalibration(latest, baseline)) calibrationConflicts.value[key] = latest
      else delete calibrationConflicts.value[key]
    } else {
      calibrationSaved.value[key] = latest
      calibrationDrafts.value[key] = { ...latest }
      delete calibrationConflicts.value[key]
    }
  }
  if (!pack.codex_version) return
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
  () =>
    !sameSettings(draft.value, saved.value) ||
    mappingDirtyKeys.value.length > 0 ||
    calibrationDirtyKeys.value.length > 0,
)
const changedNames = computed(() =>
  [
    draft.value.scale !== saved.value.scale ? '大小' : '',
    draft.value.speed !== saved.value.speed ? '速度' : '',
    draft.value.roam !== saved.value.roam ? '活动范围' : '',
    draft.value.movement !== saved.value.movement ? '活动方式' : '',
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
    const preserveDraft = !reset && dirty.value
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
    saved.value = { ...editor.value.settings }
    if (!preserveDraft) draft.value = { ...saved.value }
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
  draft.value = { ...saved.value }
  mappingDrafts.value = Object.fromEntries(
    Object.entries(mappingSaved.value).map(([key, value]) => [key, { ...value }]),
  )
  feedback.value = ''
}

async function save() {
  if (blocked.value || conflictingNames.value.length || !props.api || !currentPet.value) return
  const api = props.api
  const id = props.pluginId
  const values = { ...draft.value }
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
  busy.value = true
  feedback.value = ''
  try {
    if (!sameSettings(values, saved.value)) {
      const result = await saveSettings(api, id, values)
      if (!current()) return
      saved.value = { ...result }
      agent?.emit?.(SETTINGS_EVENT, { ...result })
    }
    for (const item of mappings) {
      if (!current()) return
      const result = await saveMappings(api, id, item.key, item.values, item.expected)
      if (!current()) return
      mappingSaved.value[item.key] = { ...result }
      agent?.emit?.(PACK_UPDATED_EVENT, { key: item.key })
    }
    for (const item of calibrations) {
      if (!current()) return
      const result = await saveCalibration(api, id, item.key, item.value, item.expected)
      if (!current()) return
      calibrationSaved.value[item.key] = result
      agent?.emit?.(PACK_UPDATED_EVENT, { key: item.key })
    }
    feedbackType.value = 'success'
    feedback.value = agent ? '调整已保存，并已通知当前页面更新。' : '调整已保存。'
  } catch (reason) {
    if (!current()) return
    feedbackType.value = 'error'
    feedback.value = reason instanceof Error ? reason.message : '操作未完成，请重试'
  } finally {
    if (current()) busy.value = false
  }
}
</script>

<template>
  <section class="ap-page">
    <v-toolbar class="ap-page__toolbar" color="transparent" density="compact" flat>
      <v-icon icon="mdi-paw-outline" color="primary" class="mr-3" />
      <v-toolbar-title class="text-subtitle-1 font-weight-bold">助手形象 · 调整与预览</v-toolbar-title>
      <v-btn
        icon="mdi-refresh"
        aria-label="刷新形象列表"
        variant="text"
        :loading="loading"
        :disabled="busy"
        @click="refresh()"
      />
      <v-btn icon="mdi-cog-outline" aria-label="打开插件配置" variant="text" :disabled="busy" @click="emit('switch')" />
      <v-btn icon="mdi-close" aria-label="关闭详情页" variant="text" :disabled="busy" @click="emit('close')" />
    </v-toolbar>
    <div class="ap-page__content">
      <v-alert v-if="!agent" type="warning" variant="tonal" density="compact" class="ap-result">{{
        HOST_UNSUPPORTED_MESSAGE
      }}</v-alert>
      <v-alert v-if="error" type="error" variant="tonal" density="compact" class="ap-result">{{ error }}</v-alert>
      <v-alert v-if="hostError" type="warning" variant="tonal" density="compact" class="ap-result">{{
        hostError
      }}</v-alert>
      <v-alert v-if="conflictingNames.length" type="warning" variant="tonal" density="compact" class="ap-result">
        {{ conflictingNames.join('、') }}
        的素材调整已在其他页面更改。已保留你的草稿；请点击「撤销」载入最新值后重新调整。
      </v-alert>
      <v-alert v-if="feedback" :type="feedbackType" variant="tonal" density="compact" class="ap-result" role="status">{{
        feedback
      }}</v-alert>
      <div v-if="loading && !snapshot" class="ap-empty">
        <v-progress-circular indeterminate color="primary" /><span class="ap-muted">正在准备你的 Pet…</span>
      </div>
      <div v-else-if="snapshot && currentPet" class="ap-editor-grid">
        <aside class="ap-controls">
          <section class="ap-control-panel">
            <h2 class="ap-section-title">选择 Pet</h2>
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
            <div class="ap-pet-identity">
              <img v-if="petImage(currentPet)" :src="petImage(currentPet)" :alt="currentPet.name" />
              <div>
                <strong>{{ currentPet.name }}</strong>
                <div class="ap-muted">
                  {{ currentPet.mode === 'stage' ? '自由活动的角色' : '助手入口的形象' }} ·
                  {{ currentPet.builtin ? '内置' : '已导入' }}
                </div>
              </div>
            </div>
            <p v-if="currentPet.description" class="ap-muted mt-3 mb-0">{{ currentPet.description }}</p>
          </section>
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
        </aside>
        <PetPreview
          :key="`${props.pluginId}:${previewVersion}`"
          :pet="currentPet"
          :settings="draft"
          :api="props.api"
          :plugin-id="props.pluginId"
          :mappings="mappingDrafts[selectedKey]"
          :calibration="calibrationDrafts[selectedKey]"
          :disabled="blocked"
          @pack-ready="onPackReady"
          @mappings="mappingDrafts[selectedKey] = $event"
          @calibration="calibrationDrafts[selectedKey] = $event"
        />
      </div>
      <div v-else-if="!loading" class="ap-empty">
        <v-icon icon="mdi-paw-outline" size="44" color="primary" /><strong>{{
          error ? 'Pet 暂时未能加载' : '还没有可预览的 Pet'
        }}</strong
        ><v-btn variant="tonal" color="primary" @click="error ? refresh() : emit('switch')">{{
          error ? '重新加载' : '前往素材管理'
        }}</v-btn>
      </div>
    </div>
    <footer class="ap-footer">
      <span v-if="dirty" class="ap-change"
        ><v-icon icon="mdi-circle" size="7" />未保存 · {{ changedNames.join('、') }}</span
      >
      <span v-else class="ap-muted">预览中的调整不会自动保存</span>
      <div class="ap-footer__actions">
        <v-btn variant="text" :disabled="blocked || (!dirty && !conflictingNames.length)" @click="restore">撤销</v-btn>
        <v-btn
          variant="flat"
          color="primary"
          prepend-icon="mdi-content-save-outline"
          :disabled="blocked || !dirty || conflictingNames.length > 0"
          :loading="busy"
          @click="save"
          >保存调整</v-btn
        >
      </div>
    </footer>
  </section>
</template>
