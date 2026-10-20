<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'

import { loadEditor, prepareEnabledConfig, type EditorSnapshot } from '@/editor/api'
import { builtinAvatar } from '@/editor/avatars'
import { useEditorPresence } from '@/editor/presence'
import '@/editor/ui.css'
import { AGENT_HOST_KEY, HOST_UNSUPPORTED_MESSAGE, type MoviePilotAgentHost, type PluginApi } from '@/host'
import PackManager from '@/sprites/PackManager.vue'
import MarketBrowser from '@/markets/MarketBrowser.vue'

const props = withDefaults(
  defineProps<{
    initialConfig?: Record<string, unknown> | null
    api?: PluginApi | null
    pluginId?: string
    sourcePluginId?: string
  }>(),
  { initialConfig: null, api: null, pluginId: '', sourcePluginId: '' },
)
const emit = defineEmits<{
  save: [Record<string, unknown>]
  close: []
  switch: []
  layout: [{ maxWidth: string }]
}>()
emit('layout', { maxWidth: '72rem' })

const agent = inject<MoviePilotAgentHost | null>(AGENT_HOST_KEY, null)
useEditorPresence()
const activeMain = ref('overview')
const visitedPacks = ref(false)
const visitedMarket = ref(false)
const packManager = ref<{ refresh: () => Promise<void> } | null>(null)
const enabled = ref(Boolean(props.initialConfig?.enabled))
const baseline = ref(Boolean(props.initialConfig?.enabled))
const changed = computed(() => enabled.value !== baseline.value)
const snapshot = ref<EditorSnapshot | null>(null)
const loading = ref(false)
const saving = ref(false)
const saveError = ref('')
const error = ref('')
const avatar = builtinAvatar('ying')
const avatarFailed = ref(false)
const groups = [
  {
    key: 'overview',
    title: '运行总览',
    icon: 'mdi-view-dashboard-outline',
    description: '从准备形象到正式使用，状态一目了然。',
  },
  { key: 'basic', title: '基础设置', icon: 'mdi-tune-variant', description: '设置插件开关，调整形象请前往详情页。' },
  {
    key: 'packs',
    title: '素材管理',
    icon: 'mdi-package-variant-closed',
    description: '导入你的 Pet，或管理已有的素材包。',
  },
  { key: 'market', title: '在线市场', icon: 'mdi-storefront-outline', description: '' },
]
const group = computed(() => groups.find(item => item.key === activeMain.value) ?? groups[0]!)
const stageCount = computed(() => snapshot.value?.pets.filter(pet => pet.mode === 'stage').length ?? 0)
let disposed = false
let requestVersion = 0
let draftInstance = props.pluginId

watch(
  [() => props.pluginId, () => props.initialConfig],
  ([id, value]) => {
    const incoming = Boolean(value?.enabled)
    if (id !== draftInstance || !changed.value || incoming === enabled.value) {
      enabled.value = incoming
      baseline.value = incoming
      draftInstance = id
    }
  },
  { deep: true },
)
watch(activeMain, value => {
  if (value === 'packs') visitedPacks.value = true
  if (value === 'market') visitedMarket.value = true
})

function marketImported() {
  void refresh()
  void packManager.value?.refresh()
}

async function refresh() {
  const version = ++requestVersion
  const id = props.pluginId
  loading.value = true
  error.value = ''
  try {
    const result = await loadEditor(props.api, id)
    if (disposed || version !== requestVersion || id !== props.pluginId) return
    snapshot.value = result
  } catch {
    if (!disposed && version === requestVersion) error.value = '运行状态暂时无法读取，可刷新重试。'
  } finally {
    if (!disposed && version === requestVersion) loading.value = false
  }
}

watch(
  () => props.pluginId,
  () => {
    snapshot.value = null
    saving.value = false
    saveError.value = ''
    void refresh()
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  disposed = true
  requestVersion++
})

async function save() {
  if (saving.value || !changed.value) return
  const id = props.pluginId
  saving.value = true
  saveError.value = ''
  try {
    const config = await prepareEnabledConfig(props.api, id, enabled.value, baseline.value)
    if (!disposed && id === props.pluginId) emit('save', config)
  } catch (reason) {
    if (!disposed && id === props.pluginId)
      saveError.value = reason instanceof Error ? reason.message : '无法读取最新配置，未提交修改，请重试'
  } finally {
    if (!disposed && id === props.pluginId) saving.value = false
  }
}
</script>

<template>
  <section class="ap-config" data-agentpets-editor>
    <div class="ap-shell">
      <header class="ap-header">
        <div class="ap-brand">
          <img v-if="!avatarFailed" :src="avatar" alt="" class="ap-brand__avatar" @error="avatarFailed = true" />
          <span v-else class="ap-brand__avatar d-flex align-center justify-center" aria-hidden="true">
            <v-icon icon="mdi-paw-outline" color="primary" size="28" />
          </span>
          <div>
            <div class="ap-eyebrow">MoviePilot / 插件设置</div>
            <h1>助手形象</h1>
          </div>
          <v-chip :color="snapshot?.enabled ? 'success' : 'default'" size="x-small" variant="tonal">{{
            snapshot ? (snapshot.enabled ? '运行中' : '未启用') : '待读取'
          }}</v-chip>
        </div>
        <v-btn
          class="ap-header__close"
          icon="mdi-close"
          aria-label="关闭配置页"
          variant="text"
          size="small"
          @click="emit('close')"
        />
      </header>
      <div class="ap-config__body">
        <nav class="ap-nav" aria-label="配置分组">
          <div class="ap-nav__label">PET 设置</div>
          <v-list density="compact" nav>
            <v-list-item
              v-for="item in groups"
              :key="item.key"
              :active="activeMain === item.key"
              :prepend-icon="item.icon"
              :title="item.title"
              color="primary"
              rounded="lg"
              @click="activeMain = item.key"
            />
          </v-list>
        </nav>
        <main class="ap-pane" :class="{ 'ap-pane--overview': activeMain === 'overview' }">
          <div class="ap-section-heading">
            <v-icon :icon="group.icon" color="primary" size="22" />
            <div>
              <h2>{{ group.title }}</h2>
              <p>{{ group.description }}</p>
            </div>
          </div>
          <v-alert v-if="!agent" type="warning" variant="tonal" density="compact" class="mb-4">{{
            HOST_UNSUPPORTED_MESSAGE
          }}</v-alert>
          <v-alert v-if="saveError" type="error" variant="tonal" density="compact" class="mb-4">{{
            saveError
          }}</v-alert>
          <template v-if="activeMain === 'overview'">
            <h3 class="ap-section-title">从形象到陪伴</h3>
            <div class="ap-flow">
              <div class="ap-flow__step">
                <v-icon icon="mdi-power" color="primary" /><strong>启用插件</strong
                ><span class="ap-muted">让 MP 发现可选形象</span>
              </div>
              <div class="ap-flow__step">
                <v-icon icon="mdi-package-down" color="primary" /><strong>准备 Pet</strong
                ><span class="ap-muted">使用内置或导入素材</span>
              </div>
              <div class="ap-flow__step">
                <v-icon icon="mdi-tune" color="primary" /><strong>调整预览</strong
                ><span class="ap-muted">在详情页边调边看</span>
              </div>
              <div class="ap-flow__step">
                <v-icon icon="mdi-check-circle-outline" color="primary" /><strong>选择形象</strong
                ><span class="ap-muted">在 MP 设置中选择</span>
              </div>
            </div>
            <div class="ap-inline">
              <h3 class="ap-section-title mb-0">当前状态</h3>
              <v-spacer /><v-btn
                icon="mdi-refresh"
                aria-label="刷新运行状态"
                variant="text"
                size="small"
                :loading="loading"
                @click="refresh"
              />
            </div>
            <v-alert v-if="error" type="warning" variant="tonal" density="compact">{{ error }}</v-alert>
            <div class="ap-metrics">
              <div class="ap-metric">
                <span class="ap-muted">可选 Pet</span><strong>{{ snapshot?.pets.length ?? '—' }}</strong>
              </div>
              <div class="ap-metric">
                <span class="ap-muted">自由活动</span><strong>{{ snapshot ? stageCount : '—' }}</strong>
              </div>
              <div class="ap-metric">
                <span class="ap-muted">入口形象</span
                ><strong>{{ snapshot ? snapshot.pets.length - stageCount : '—' }}</strong>
              </div>
            </div>
            <div class="ap-note">
              <v-icon icon="mdi-information-outline" color="primary" size="18" />
              <div>
                插件没有后台任务。素材暂时不可用时，MP 会回退到内置形象；检查素材并重新选择即可。<br />当前配置页管理开关和素材，Pet
                的大小、活动与实时预览集中在详情页。
              </div>
            </div>
            <v-btn class="mt-4" color="primary" variant="tonal" prepend-icon="mdi-paw-outline" @click="emit('switch')"
              >前往调整与预览</v-btn
            >
          </template>
          <template v-if="activeMain === 'basic'">
            <v-card variant="outlined" class="mb-4" style="background: transparent">
              <v-card-item title="启用助手形象" subtitle="启用后，内置与导入的 Pet 会出现在 MP 的助手形象列表中。">
                <template #append
                  ><v-switch
                    v-model="enabled"
                    :disabled="saving"
                    aria-label="启用助手形象"
                    color="success"
                    inset
                    hide-details
                    density="compact"
                /></template>
              </v-card-item>
            </v-card>
            <div class="ap-setting-row">
              <h3>形象调整</h3>
              <p class="ap-muted">角色大小、移动速度和活动范围在详情页统一调整，预览满意后点击「保存调整」。</p>
              <v-btn class="mt-3" color="primary" variant="tonal" prepend-icon="mdi-tune" @click="emit('switch')"
                >打开详情页</v-btn
              >
            </div>
            <div class="ap-setting-row">
              <h3>选择优先级</h3>
              <p class="ap-muted">
                个人指定的形象优先；选择“跟随系统默认”的用户会使用系统默认 Pet。请在 MP 的智能助手配置中选择形象。
              </p>
            </div>
          </template>
          <PackManager
            ref="packManager"
            v-if="visitedPacks"
            v-show="activeMain === 'packs'"
            :key="props.pluginId"
            :api="props.api"
            :plugin-id="props.pluginId"
            @changed="refresh"
          />
          <MarketBrowser
            v-if="visitedMarket"
            v-show="activeMain === 'market'"
            :key="props.pluginId"
            :api="props.api"
            :plugin-id="props.pluginId"
            @imported="marketImported"
          />
        </main>
      </div>
      <footer class="ap-footer">
        <span v-if="changed" class="ap-change" role="status"
          ><v-icon icon="mdi-circle" size="7" />1 项未保存 · 启用助手形象</span
        >
        <span v-else class="ap-muted">{{
          activeMain === 'packs' || activeMain === 'market' ? '素材的导入与删除即时保存' : '修改配置后点击保存'
        }}</span>
        <div class="ap-footer__actions">
          <v-btn variant="text" @click="emit('close')">取消</v-btn
          ><v-btn
            color="primary"
            variant="flat"
            prepend-icon="mdi-content-save-outline"
            :disabled="!changed || saving"
            :loading="saving"
            @click="save"
            >保存配置</v-btn
          >
        </div>
      </footer>
    </div>
  </section>
</template>
