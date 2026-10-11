<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'

import {
  applyDefaultPet,
  checkAvailablePet,
  loadEditor,
  loadHostSelection,
  petImage,
  reloadForPet,
  sameSettings,
  saveSettings,
  type EditorSnapshot,
  type HostSelection,
} from '@/editor/api'
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
const followDefault = ref(true)
const previewFailed = ref(false)
const currentPet = computed(() => snapshot.value?.pets.find(pet => pet.key === selectedKey.value) ?? null)
const dirty = computed(() => !sameSettings(draft.value, saved.value))
const changedNames = computed(() =>
  [
    draft.value.scale !== saved.value.scale ? '大小' : '',
    draft.value.speed !== saved.value.speed ? '速度' : '',
    draft.value.roam !== saved.value.roam ? '活动范围' : '',
  ].filter(Boolean),
)
const hasPersonalChoice = computed(() => selection.value?.user != null)
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
    hostError.value = '无法读取系统默认或个人选择；管理员连接恢复后可保存和立即生效。'
  }
  if (editor.status === 'fulfilled') {
    const preserveDraft = !reset && dirty.value
    snapshot.value = editor.value
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
    previewFailed.value = false
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
  draft.value = { ...saved.value }
  feedback.value = ''
}

async function commit(apply: boolean) {
  if (blocked.value || !props.api || !currentPet.value || !selection.value) return
  const api = props.api
  const id = props.pluginId
  const key = currentPet.value.key
  const name = currentPet.value.name
  const values = { ...draft.value }
  const shouldFollow = hasPersonalChoice.value && followDefault.value
  const version = ++operationVersion
  const current = () => !disposed && version === operationVersion && id === props.pluginId
  busy.value = true
  feedback.value = ''
  try {
    if (apply) await checkAvailablePet(api, id, key)
    if (!current()) return
    if (!sameSettings(values, saved.value)) {
      const result = await saveSettings(api, id, values)
      if (!current()) return
      saved.value = { ...result }
      agent?.emit?.(SETTINGS_EVENT, { ...result })
    }
    if (apply) {
      const result = await applyDefaultPet(api, id, key, shouldFollow, current)
      if (!current()) return
      selection.value = result
      feedbackType.value = 'success'
      feedback.value = `已将 ${name} 设为系统默认形象，正在刷新页面。`
      reloadForPet()
    } else {
      feedbackType.value = 'success'
      feedback.value = agent ? '活动调整已保存，并已通知当前页面更新。' : '活动调整已保存。'
    }
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
              此 Pet 显示在助手入口，位置与拖拽由 MP 控制。可在预览区切换动作，并设为默认形象。
            </p>
          </section>
          <section class="ap-control-panel">
            <h2 class="ap-section-title">应用到 MP</h2>
            <div class="ap-muted">当前系统默认</div>
            <strong>{{ defaultName }}</strong>
            <v-switch
              v-if="hasPersonalChoice"
              v-model="followDefault"
              label="当前用户跟随系统默认"
              color="primary"
              density="compact"
              inset
              hide-details
              class="mt-2"
              :disabled="blocked"
            />
            <p v-if="hasPersonalChoice && !followDefault" class="ap-muted mt-2 mb-0">当前用户仍使用个人选择的形象。</p>
            <p class="ap-muted mt-3 mb-0">
              “立即生效”会保存调整、设置系统默认形象，并刷新当前页面。其他用户的个人选择保持有效。
            </p>
            <v-alert v-if="!snapshot.enabled" type="info" variant="tonal" density="compact" class="mt-3"
              >先在配置页启用插件，再使用“立即生效”。</v-alert
            >
          </section>
        </aside>
        <PetPreview
          :key="props.pluginId"
          :pet="currentPet"
          :settings="draft"
          :api="props.api"
          :plugin-id="props.pluginId"
          @error="previewFailed = $event"
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
        <v-btn variant="text" :disabled="blocked || !dirty" @click="restore">撤销</v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          :disabled="blocked || !dirty || !selection"
          :loading="busy"
          @click="commit(false)"
          >保存调整</v-btn
        >
        <v-btn
          color="primary"
          variant="flat"
          prepend-icon="mdi-check"
          :disabled="blocked || !selection || !snapshot?.enabled || !agent || previewFailed"
          :loading="busy"
          @click="commit(true)"
          >立即生效</v-btn
        >
      </div>
    </footer>
  </section>
</template>
