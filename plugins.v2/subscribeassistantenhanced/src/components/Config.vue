<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import saeLogo from '../assets/sae-logo.svg'
import { loadSummary, type PluginApi, type SummaryPayload } from '../config/api'
import { configDefaults, type NumberConfigKey, type SaeConfig } from '../config/defaults'
import { fields, groups, type FieldMeta, type GroupKey } from '../config/fields'
import { buildImpactPreview, type PreviewItem } from '../config/preview'
import { normalizeFiniteNumber } from '../config/values'

const props = defineProps<{
  /** 宿主读取并传入的当前插件配置模型。 */
  initialConfig?: Partial<SaeConfig>
  /** 宿主注入的已认证插件 API 客户端。 */
  api?: PluginApi
}>()

const emit = defineEmits<{
  /** 请求宿主持久化完整配置对象。 */
  save: [SaeConfig]
  /** 请求宿主关闭配置界面。 */
  close: []
  /** 请求宿主切换插件详情/配置视图。 */
  switch: []
}>()

const README_URL =
  'https://github.com/InfinityPacer/MoviePilot-Plugins/blob/main/plugins.v2/subscribeassistantenhanced/README.md'
// JS 折叠阈值必须与同文件 CSS 720px container query 保持一致。
const MOBILE_CONTAINER_WIDTH = 720

const draft = reactive<SaeConfig>({
  ...configDefaults,
  ...props.initialConfig,
  open_tracker_dialog: false,
})
const renderedFields = fields.filter(field => !field.legacyUiKey && !field.dialogOnly)
const trackerField = fields.find(
  field => field.key === 'default_tracker_response' && field.dialogOnly,
)!
const activeGroup = ref<GroupKey>('global')
const configRoot = ref<HTMLElement | null>(null)
const containerWidth = ref(0)
const expandedAdvancedKeys = ref<string[]>([])
const impactItems = computed(() => buildImpactPreview(draft))
const runtimeSummary = ref<SummaryPayload | null>(null)
const summaryState = ref<'loading' | 'available' | 'unavailable'>('loading')
// 对话框开关只控制当前界面，持久化的旧版触发字段始终保持 false。
const trackerDialogOpen = ref(false)
let resizeObserver: ResizeObserver | undefined

const impactToneIcons: Record<PreviewItem['tone'], string> = {
  info: 'mdi-information-outline',
  success: 'mdi-check-circle-outline',
  warning: 'mdi-alert-outline',
  error: 'mdi-alert-circle-outline',
}

const activeGroupMeta = computed(
  () => groups.find(group => group.key === activeGroup.value) ?? groups[0]!,
)
const activeFields = computed(() =>
  renderedFields.filter(field => field.group === activeGroup.value),
)
const coreFieldKeys = computed(() =>
  activeFields.value.filter(field => !isCollapsibleField(field)).map(field => field.key),
)
const collapsibleFieldKeys = computed(() =>
  activeFields.value.filter(isCollapsibleField).map(field => field.key),
)
const isMobileLayout = computed(() => containerWidth.value < MOBILE_CONTAINER_WIDTH)
const summaryDomains = computed(() => Object.entries(runtimeSummary.value?.domains ?? {}))
const expandedPanelKeys = computed<(string | number)[]>({
  get: () => [...coreFieldKeys.value, ...expandedAdvancedKeys.value],
  set: keys => {
    const allowedKeys = new Set(collapsibleFieldKeys.value)
    expandedAdvancedKeys.value = keys
      .filter((key): key is string => typeof key === 'string')
      .filter(key => allowedKeys.has(key as (typeof collapsibleFieldKeys.value)[number]))
  },
})

// 切换分组或跨过布局阈值时，清除上一组的展开状态并恢复当前布局默认值。
watch(
  [activeGroup, isMobileLayout],
  () => {
    expandedAdvancedKeys.value = isMobileLayout.value ? [] : [...collapsibleFieldKeys.value]
  },
  { immediate: true },
)

onMounted(() => {
  if (configRoot.value) {
    containerWidth.value = configRoot.value.getBoundingClientRect().width
    resizeObserver = new ResizeObserver(entries => {
      const entry = entries[0]
      if (entry) containerWidth.value = entry.contentRect.width
    })
    resizeObserver.observe(configRoot.value)
  }

  void loadSummary(props.api).then(payload => {
    runtimeSummary.value = payload
    summaryState.value = payload ? 'available' : 'unavailable'
  })
})

onBeforeUnmount(() => resizeObserver?.disconnect())

/** 高级项和破坏性配置在窄屏折叠，宽屏保持直接可见。 */
function isCollapsibleField(field: FieldMeta): boolean {
  return Boolean(field.advanced || field.risk === 'danger')
}

/** 沿用 Vuetify 语义色表达字段已有风险等级。 */
function fieldColor(field: FieldMeta): 'error' | 'warning' | undefined {
  if (field.risk === 'danger') return 'error'
  if (field.risk === 'notice') return 'warning'
  return undefined
}

/** 按概览契约显示布尔状态，字符串模式保持后端原值。 */
function formatDomainStatus(value: boolean | string): string {
  if (typeof value === 'boolean') return value ? '启用' : '关闭'
  return value
}

/** 使用稳定图标区分开关状态与模式值，不推断额外运行健康度。 */
function domainIcon(value: boolean | string): string {
  if (typeof value !== 'boolean') return 'mdi-tune-variant'
  return value ? 'mdi-check-circle-outline' : 'mdi-minus-circle-outline'
}

/** 概览状态只使用 Vuetify 语义色。 */
function domainColor(value: boolean | string): 'info' | 'success' | undefined {
  if (typeof value !== 'boolean') return 'info'
  return value ? 'success' : undefined
}

/** 数值字段只接受有限 number，避免动态输入污染完整保存 payload。 */
function updateNumber(key: NumberConfigKey, incoming: unknown): void {
  draft[key] = normalizeFiniteNumber(draft[key], incoming)
}

/** 保存完整配置，并确保弹窗触发位始终按关闭状态持久化。 */
function saveConfig(): void {
  emit('save', {
    ...configDefaults,
    ...draft,
    open_tracker_dialog: false,
  })
}
</script>

<template>
  <section ref="configRoot" class="sae-config">
    <form class="sae-config__form" @submit.prevent="saveConfig">
      <header class="sae-config-header">
        <div class="sae-config-header__brand">
          <img :src="saeLogo" alt="" class="sae-config-header__logo" />
          <div class="sae-config-header__identity">
            <h1 class="sae-config-header__title">订阅助手（增强版）</h1>
            <div class="sae-config-header__status">
              <VChip color="warning" size="x-small" variant="tonal">BETA</VChip>
              <VChip :color="draft.enabled ? 'success' : undefined" size="x-small" variant="tonal">
                {{ draft.enabled ? '已启用' : '未启用' }}
              </VChip>
            </div>
          </div>
        </div>

        <div class="sae-config-header__actions">
          <VBtn
            :href="README_URL"
            aria-label="查看插件 README"
            icon
            rel="noopener noreferrer"
            size="small"
            target="_blank"
            variant="text"
          >
            <VIcon icon="mdi-book-open-page-variant-outline" />
            <VTooltip activator="parent" text="查看 README" />
          </VBtn>
          <VBtn
            aria-label="保存配置"
            class="sae-config-header__save"
            color="primary"
            icon
            size="small"
            type="submit"
            variant="text"
          >
            <VIcon icon="mdi-content-save" />
            <VTooltip activator="parent" text="保存配置" />
          </VBtn>
          <VBtn
            aria-label="关闭配置"
            icon
            size="small"
            variant="text"
            @click="emit('close')"
          >
            <VIcon icon="mdi-close" />
            <VTooltip activator="parent" text="关闭配置" />
          </VBtn>
        </div>
      </header>

      <VAlert class="sae-config-warning" density="compact" type="warning" variant="tonal">
        BETA 版本提示：本插件仍处于测试阶段，可能调整订阅状态、洗版记录、下载任务和媒体文件。
      </VAlert>

      <div class="sae-config-layout">
        <div class="sae-mobile-group-selector">
          <VSelect
            v-model="activeGroup"
            aria-label="选择配置分组"
            density="compact"
            hide-details
            item-title="title"
            item-value="key"
            :items="groups"
            label="配置分组"
            variant="outlined"
          >
            <template #prepend-inner>
              <VIcon :icon="activeGroupMeta.icon" size="20" />
            </template>
          </VSelect>
        </div>

        <nav class="sae-group-nav" aria-label="配置分组">
          <VList
            class="sae-group-nav__list app-surface-borderless app-surface-flat app-surface-square"
            density="compact"
            nav
          >
            <VListItem
              v-for="group in groups"
              :key="group.key"
              :active="activeGroup === group.key"
              :prepend-icon="group.icon"
              :subtitle="group.summary"
              :title="group.title"
              color="primary"
              rounded="0"
              @click="activeGroup = group.key"
            >
              <template v-if="group.highRisk" #append>
                <VIcon color="error" icon="mdi-alert-circle-outline" size="17" />
              </template>
            </VListItem>
          </VList>
        </nav>

        <main class="sae-field-surface">
          <div class="sae-field-surface__heading">
            <div class="sae-field-surface__heading-copy">
              <VIcon :icon="activeGroupMeta.icon" color="primary" size="22" />
              <div>
                <h2>{{ activeGroupMeta.title }}</h2>
                <p>{{ activeGroupMeta.summary }}</p>
              </div>
            </div>
            <VChip v-if="activeGroupMeta.highRisk" color="error" size="small" variant="tonal">
              高风险
            </VChip>
          </div>

          <VExpansionPanels
            v-model="expandedPanelKeys"
            class="sae-field-panels"
            multiple
            variant="accordion"
          >
            <VExpansionPanel
              v-for="field in activeFields"
              :key="field.key"
              :class="[
                'sae-field-panel',
                'app-surface-borderless',
                'app-surface-flat',
                'app-surface-square',
                isCollapsibleField(field)
                  ? 'sae-field-panel--collapsible'
                  : 'sae-field-panel--core',
              ]"
              :value="field.key"
            >
              <VExpansionPanelTitle v-if="isCollapsibleField(field)" class="sae-field-panel__title">
                <span>{{ field.label }}</span>
                <template #actions="{ expanded }">
                  <div class="sae-field-panel__title-actions">
                    <VChip
                      v-if="field.risk === 'danger'"
                      color="error"
                      size="x-small"
                      variant="tonal"
                    >
                      高风险
                    </VChip>
                    <VIcon :icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="20" />
                  </div>
                </template>
              </VExpansionPanelTitle>

              <VExpansionPanelText>
                <div class="sae-field-control">
                  <VSwitch
                    v-if="field.kind === 'switch'"
                    v-model="draft[field.key]"
                    :aria-label="field.label"
                    :color="fieldColor(field)"
                    :hint="field.hint"
                    :label="isCollapsibleField(field) ? undefined : field.label"
                    persistent-hint
                  />
                  <VSelect
                    v-else-if="field.kind === 'select'"
                    v-model="draft[field.key]"
                    :aria-label="field.label"
                    :color="fieldColor(field)"
                    :hint="field.hint"
                    :items="field.options"
                    :label="isCollapsibleField(field) ? undefined : field.label"
                    item-title="title"
                    item-value="value"
                    persistent-hint
                  />
                  <VSelect
                    v-else-if="field.kind === 'multi-select'"
                    v-model="draft[field.key]"
                    :aria-label="field.label"
                    chips
                    :color="fieldColor(field)"
                    :hint="field.hint"
                    :items="field.options"
                    :label="isCollapsibleField(field) ? undefined : field.label"
                    item-title="title"
                    item-value="value"
                    multiple
                    persistent-hint
                  />
                  <VTextField
                    v-else-if="field.kind === 'number'"
                    :aria-label="field.label"
                    :color="fieldColor(field)"
                    :hint="field.hint"
                    :label="isCollapsibleField(field) ? undefined : field.label"
                    :model-value="draft[field.key]"
                    persistent-hint
                    type="number"
                    @update:model-value="updateNumber(field.key as NumberConfigKey, $event)"
                  />
                  <VTextField
                    v-else-if="field.kind === 'text' || field.kind === 'cron'"
                    v-model="draft[field.key]"
                    :aria-label="field.label"
                    :color="fieldColor(field)"
                    :hint="field.hint"
                    :label="isCollapsibleField(field) ? undefined : field.label"
                    persistent-hint
                  />
                  <VTextarea
                    v-else-if="field.kind === 'textarea'"
                    v-model="draft[field.key]"
                    :aria-label="field.label"
                    :color="fieldColor(field)"
                    :hint="field.hint"
                    :label="isCollapsibleField(field) ? undefined : field.label"
                    persistent-hint
                  />
                </div>
              </VExpansionPanelText>
            </VExpansionPanel>
          </VExpansionPanels>

          <div v-if="activeGroup === 'cleanup'" class="sae-tracker-entry">
            <div class="sae-tracker-entry__copy">
              <VIcon color="primary" icon="mdi-message-text-outline" size="22" />
              <div>
                <strong>{{ trackerField.label }}</strong>
                <p>{{ trackerField.hint }}</p>
              </div>
            </div>
            <VBtn
              :aria-label="`编辑${trackerField.label}`"
              color="primary"
              prepend-icon="mdi-pencil-outline"
              type="button"
              variant="tonal"
              @click="trackerDialogOpen = true"
            >
              编辑{{ trackerField.label }}
            </VBtn>
          </div>
        </main>

        <aside class="sae-impact-preview">
          <div class="sae-impact-preview__title">
            <VIcon color="primary" icon="mdi-eye-outline" size="20" />
            <h2>配置影响预览</h2>
          </div>
          <div class="sae-impact-preview__group">
            <VIcon :icon="activeGroupMeta.icon" size="22" />
            <div>
              <strong>{{ activeGroupMeta.title }}</strong>
              <p>{{ activeGroupMeta.summary }}</p>
            </div>
          </div>

          <ul class="sae-impact-preview__list">
            <li v-for="item in impactItems" :key="item.title" class="sae-impact-preview__item">
              <VIcon :color="item.tone" :icon="impactToneIcons[item.tone]" size="20" />
              <div>
                <strong>{{ item.title }}</strong>
                <p>{{ item.detail }}</p>
              </div>
            </li>
          </ul>

          <section aria-label="运行概况" class="sae-runtime-summary">
            <div class="sae-runtime-summary__title">
              <VIcon color="primary" icon="mdi-chart-box-outline" size="19" />
              <h3>运行概况</h3>
            </div>

            <div v-if="summaryState === 'loading'" class="sae-runtime-summary__state">
              <VProgressCircular color="primary" indeterminate size="18" width="2" />
              <span>正在读取运行概况</span>
            </div>

            <template v-else-if="summaryState === 'available' && runtimeSummary">
              <div class="sae-runtime-summary__metrics">
                <div class="sae-runtime-summary__row">
                  <VIcon icon="mdi-timer-sand" size="18" />
                  <span>待定订阅</span>
                  <strong>{{ runtimeSummary.pending_count }}</strong>
                </div>
                <div class="sae-runtime-summary__row">
                  <VIcon icon="mdi-download-network-outline" size="18" />
                  <span>监控下载任务</span>
                  <strong>{{ runtimeSummary.monitored_torrents }}</strong>
                </div>
              </div>
              <div class="sae-runtime-summary__domains">
                <div
                  v-for="[name, status] in summaryDomains"
                  :key="name"
                  class="sae-runtime-summary__row"
                >
                  <VIcon :color="domainColor(status)" :icon="domainIcon(status)" size="18" />
                  <span>{{ name }}</span>
                  <strong>{{ formatDomainStatus(status) }}</strong>
                </div>
              </div>
            </template>

            <p v-else class="sae-runtime-summary__unavailable">运行概况暂不可用</p>
          </section>
        </aside>
      </div>

      <div class="sae-mobile-savebar">
        <VBtn block color="primary" prepend-icon="mdi-content-save" type="submit">
          保存配置
        </VBtn>
      </div>
    </form>

    <VDialog
      v-model="trackerDialogOpen"
      max-width="720"
      scrollable
      width="calc(100% - 24px)"
    >
      <VCard>
        <VCardTitle class="sae-tracker-dialog__title">
          <span>{{ trackerField.label }}</span>
          <VBtn
            :aria-label="`关闭${trackerField.label}`"
            icon
            size="small"
            variant="text"
            @click="trackerDialogOpen = false"
          >
            <VIcon icon="mdi-close" />
            <VTooltip activator="parent" text="关闭" />
          </VBtn>
        </VCardTitle>
        <VCardText>
          <VTextarea
            v-model="draft.default_tracker_response"
            :aria-label="trackerField.label"
            :hint="trackerField.hint"
            :label="trackerField.label"
            persistent-hint
            rows="10"
            variant="outlined"
          />
        </VCardText>
        <VCardActions class="sae-tracker-dialog__actions">
          <VSpacer />
          <VBtn color="primary" prepend-icon="mdi-check" @click="trackerDialogOpen = false">
            完成
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </section>
</template>

<style scoped>
.sae-config {
  container-type: inline-size;
  min-inline-size: 0;
  color: rgb(var(--v-theme-on-surface));
  letter-spacing: 0;
}

.sae-config,
.sae-config * {
  box-sizing: border-box;
}

.sae-config__form {
  min-inline-size: 0;
  padding: 12px;
}

.sae-config-header,
.sae-group-nav,
.sae-field-surface,
.sae-impact-preview,
.sae-mobile-savebar {
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
  backdrop-filter: var(--app-grouped-list-backdrop-filter);
  background: var(--app-grouped-list-background);
  box-shadow: var(--app-surface-shadow);
}

.sae-config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-inline-size: 0;
  padding: 10px 12px;
  gap: 12px;
}

.sae-config-header__brand {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  min-inline-size: 0;
  gap: 10px;
}

.sae-config-header__logo {
  display: block;
  flex: 0 0 44px;
  block-size: 44px;
  inline-size: 44px;
  object-fit: contain;
}

.sae-config-header__identity {
  min-inline-size: 0;
}

.sae-config-header__title {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.35rem;
}

.sae-config-header__status,
.sae-config-header__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sae-config-header__status {
  margin-block-start: 4px;
}

.sae-config-header__actions {
  flex: 0 0 auto;
}

.sae-config-header__actions :deep(.v-btn) {
  block-size: 36px;
  inline-size: 36px;
}

.sae-config-warning {
  margin-block-start: 10px;
  font-size: 0.8125rem;
  letter-spacing: 0;
}

.sae-config-layout {
  display: grid;
  min-inline-size: 0;
  /* 72px + safe-area 预留与 sticky 保存栏的回拉配对，避免末字段被遮挡。 */
  padding-block-end: calc(72px + env(safe-area-inset-bottom));
  margin-block-start: 10px;
  gap: 10px;
  grid-template-areas:
    'selector'
    'content'
    'preview';
  grid-template-columns: minmax(0, 1fr);
}

.sae-mobile-group-selector {
  min-inline-size: 0;
  grid-area: selector;
}

.sae-group-nav {
  display: none;
  min-inline-size: 0;
  overflow: hidden;
  grid-area: navigation;
}

.sae-group-nav > .sae-group-nav__list.v-list {
  padding: 0;
  backdrop-filter: none;
  background: transparent;
  background-color: transparent;
}

.sae-group-nav__list :deep(.v-list-item) {
  min-block-size: 58px;
  padding-block: 7px;
  padding-inline: 10px;
}

.sae-group-nav__list :deep(.v-list-item-title) {
  overflow-wrap: anywhere;
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.15rem;
}

.sae-group-nav__list :deep(.v-list-item-subtitle) {
  display: -webkit-box;
  overflow: hidden;
  margin-block-start: 2px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 0.6875rem;
  line-height: 0.95rem;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.sae-field-surface {
  min-inline-size: 0;
  overflow: hidden;
  grid-area: content;
}

.sae-field-surface__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  min-inline-size: 0;
  padding: 13px 14px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  gap: 12px;
}

.sae-field-surface__heading-copy {
  display: flex;
  align-items: flex-start;
  min-inline-size: 0;
  gap: 9px;
}

.sae-field-surface h2,
.sae-impact-preview h2 {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.25rem;
}

.sae-field-surface__heading p,
.sae-impact-preview p {
  margin: 3px 0 0;
  overflow-wrap: anywhere;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.75rem;
  letter-spacing: 0;
  line-height: 1.05rem;
}

.sae-field-panels {
  gap: 0;
}

.sae-field-panel {
  background: rgba(var(--v-theme-surface), 0) !important;
}

.sae-field-panel + .sae-field-panel {
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.09);
}

.sae-field-panel__title {
  min-block-size: 46px;
  padding-block: 9px;
  padding-inline: 14px;
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.2rem;
}

.sae-field-panel__title > span {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}

.sae-field-panel__title-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 7px;
}

.sae-field-panel :deep(.v-expansion-panel-text__wrapper) {
  padding: 10px 14px 14px;
}

.sae-field-panel--core :deep(.v-expansion-panel-text__wrapper) {
  padding-block-start: 14px;
}

.sae-field-control,
.sae-field-control :deep(.v-input) {
  min-inline-size: 0;
  max-inline-size: 100%;
}

.sae-field-control :deep(.v-messages__message) {
  overflow-wrap: anywhere;
  line-height: 1rem;
}

.sae-tracker-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-inline-size: 0;
  padding: 14px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.09);
  gap: 12px;
}

.sae-tracker-entry__copy {
  display: flex;
  align-items: flex-start;
  min-inline-size: 0;
  gap: 9px;
}

.sae-tracker-entry__copy > div {
  min-inline-size: 0;
}

.sae-tracker-entry strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: 0.875rem;
  letter-spacing: 0;
  line-height: 1.2rem;
}

.sae-tracker-entry p {
  margin: 3px 0 0;
  overflow-wrap: anywhere;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.75rem;
  letter-spacing: 0;
  line-height: 1.05rem;
}

.sae-tracker-entry :deep(.v-btn) {
  flex: 0 1 auto;
  min-inline-size: 0;
  block-size: auto;
  min-block-size: 36px;
  padding-block: 7px;
}

.sae-tracker-entry :deep(.v-btn__content) {
  white-space: normal;
  overflow-wrap: anywhere;
}

.sae-impact-preview {
  min-inline-size: 0;
  padding: 14px;
  grid-area: preview;
}

.sae-impact-preview__title,
.sae-impact-preview__group {
  display: flex;
  align-items: flex-start;
  min-inline-size: 0;
  gap: 8px;
}

.sae-impact-preview__group {
  padding-block: 13px;
  margin-block: 12px;
  border-block: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}

.sae-impact-preview__group > div {
  min-inline-size: 0;
}

.sae-impact-preview strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: 0.8125rem;
  letter-spacing: 0;
  line-height: 1.1rem;
}

.sae-impact-preview__list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.sae-impact-preview__item,
.sae-runtime-summary__row,
.sae-runtime-summary__state,
.sae-runtime-summary__title {
  display: grid;
  align-items: start;
  min-inline-size: 0;
  gap: 8px;
  grid-template-columns: 20px minmax(0, 1fr);
}

.sae-impact-preview__item {
  padding-block: 10px;
}

.sae-impact-preview__item + .sae-impact-preview__item {
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.09);
}

.sae-impact-preview__item > div {
  min-inline-size: 0;
}

.sae-runtime-summary {
  padding-block-start: 13px;
  margin-block-start: 12px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}

.sae-runtime-summary__title {
  align-items: center;
}

.sae-runtime-summary__title h3 {
  margin: 0;
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.1rem;
}

.sae-runtime-summary__state,
.sae-runtime-summary__row {
  align-items: center;
  padding-block: 7px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 0.75rem;
  letter-spacing: 0;
  line-height: 1.05rem;
}

.sae-runtime-summary__state {
  margin-block-start: 6px;
}

.sae-runtime-summary__metrics,
.sae-runtime-summary__domains {
  margin-block-start: 6px;
}

.sae-runtime-summary__domains {
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.09);
}

.sae-runtime-summary__row {
  grid-template-columns: 20px minmax(0, 1fr) minmax(0, auto);
}

.sae-runtime-summary__row span,
.sae-runtime-summary__row strong {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}

.sae-runtime-summary__row strong {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
  text-align: end;
}

.sae-runtime-summary__unavailable {
  margin-block-start: 9px;
}

.sae-tracker-dialog__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-inline-size: 0;
  gap: 12px;
}

.sae-tracker-dialog__title > span {
  min-inline-size: 0;
  overflow-wrap: anywhere;
  white-space: normal;
}

.sae-tracker-dialog__actions {
  flex-wrap: wrap;
}

.sae-mobile-savebar {
  position: sticky;
  z-index: 5;
  inset-block-end: 0;
  padding-block: 8px calc(8px + env(safe-area-inset-bottom));
  padding-inline: 10px;
  /* -62px - safe-area 回拉与内容底部预留配对，避免 sticky 保存栏遮挡末字段。 */
  margin-block-start: calc(-62px - env(safe-area-inset-bottom));
}

@container (width <= 480px) {
  .sae-config-header {
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .sae-config-header__brand,
  .sae-config-header__actions {
    inline-size: 100%;
  }

  .sae-config-header__actions {
    justify-content: flex-end;
  }

  .sae-tracker-entry {
    align-items: stretch;
    flex-direction: column;
  }

  .sae-tracker-entry :deep(.v-btn) {
    inline-size: 100%;
  }
}

@container (width < 720px) {
  .sae-config-header__save {
    display: none;
  }
}

@container (width >= 720px) {
  .sae-config__form {
    padding: 16px;
  }

  .sae-config-layout {
    padding-block-end: 0;
    gap: 12px;
    grid-template-areas:
      'navigation content'
      'navigation preview';
    grid-template-columns: minmax(190px, 214px) minmax(0, 1fr);
  }

  .sae-mobile-group-selector,
  .sae-mobile-savebar {
    display: none;
  }

  .sae-group-nav {
    display: block;
  }

  .sae-impact-preview {
    align-self: start;
  }
}

@container (width >= 1180px) {
  .sae-config-layout {
    align-items: start;
    grid-template-areas: 'navigation content preview';
    grid-template-columns: 210px minmax(0, 1fr) 248px;
  }

  .sae-group-nav,
  .sae-impact-preview {
    position: sticky;
    inset-block-start: 12px;
  }
}
</style>
