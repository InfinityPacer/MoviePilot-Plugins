<script setup lang="ts">
import { computed, getCurrentInstance, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useTheme } from 'vuetify'

import saeLogo from '../assets/sae-logo.svg'
import { loadSummary, type PluginApi, type SummaryPayload } from '../config/api'
import type { ConfigKey, NumberConfigKey, SaeConfig } from '../config/defaults'
import { useConfigDraft } from '../config/draft'
import { fields, groups, type FieldMeta, type GroupKey } from '../config/fields'
import { localizeFields, localizeGroups, normalizeLocale, t } from '../config/i18n'
import { buildImpactPreview, type PreviewItem } from '../config/preview'
import { normalizeFiniteNumber } from '../config/values'

const props = defineProps<{
  /** 宿主传入的动态 JSON 配置模型，进入草稿前按稳定配置契约规范化。 */
  initialConfig?: unknown
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
const { draft, changedCount, buildSavePayload } = useConfigDraft(props.initialConfig)
const instance = getCurrentInstance()
const locale = computed(() => normalizeLocale(instance?.appContext.config.globalProperties.$i18n?.locale))
const localizedGroups = computed(() => localizeGroups(locale.value, groups))
const localizedFields = computed(() => localizeFields(locale.value, fields))
const fieldsByKey = computed(() => new Map(
  localizedFields.value
    .filter(field => !field.legacyUiKey && !field.dialogOnly)
    .map(field => [field.key, field]),
))
const trackerField = computed(() => localizedFields.value.find(
  field => field.key === 'default_tracker_response' && field.dialogOnly,
)!)
const activeGroup = ref<GroupKey>('global')
const impactItems = computed(() => buildImpactPreview(draft, locale.value))
const runtimeSummary = ref<SummaryPayload | null>(null)
const summaryState = ref<'loading' | 'available' | 'unavailable'>('loading')
// 对话框开关只控制当前界面，持久化的旧版触发字段始终保持 false。
const trackerDialogOpen = ref(false)
const yamlDialogOpen = ref(false)
const mobileGroupSheet = ref(false)
const configHeaderSentinel = ref<HTMLElement | null>(null)
const fieldSurfaceHeading = ref<HTMLElement | null>(null)
const headerScrolled = ref(false)
const theme = useTheme()
const aceTheme = computed(() => theme.current.value.dark ? 'github_dark' : 'github')
let headerObserver: IntersectionObserver | undefined
let configScrollRoot: HTMLElement | null = null
let scrollIdleTimer: number | undefined

interface SectionDefinition {
  /** 当前业务分组内的稳定章节翻译键。 */
  titleKey: string
  /** 章节覆盖的配置键，顺序同时决定表单展示顺序。 */
  keys: ConfigKey[]
}

const sectionDefinitions: Record<GroupKey, SectionDefinition[]> = {
  global: [
    { titleKey: 'section.running', keys: ['enabled', 'notify'] },
    { titleKey: 'section.oneTime', keys: ['onlyonce', 'reset_task'] },
    {
      titleKey: 'section.schedule',
      keys: [
        'auto_check_interval_minutes',
        'download_check_interval_minutes',
        'meta_check_interval_hours',
        'best_version_cron',
      ],
    },
  ],
  cleanup: [
    {
      titleKey: 'section.download',
      keys: [
        'download_monitor_enabled',
        'manual_delete_listen',
        'tracker_response_listen',
        'auto_search_when_delete',
        'skip_deletion',
      ],
    },
    {
      titleKey: 'section.timeout',
      keys: [
        'download_timeout_minutes',
        'download_progress_threshold',
        'download_retry_limit',
        'delete_exclude_tags',
        'delete_record_retention_hours',
      ],
    },
    {
      titleKey: 'section.cleanup',
      keys: ['subscription_cleanup_history_type', 'subscription_cleanup_history_scenes'],
    },
  ],
  pending: [
    {
      titleKey: 'section.pending',
      keys: ['pending_enhanced_enabled', 'pending_download_enabled'],
    },
    {
      titleKey: 'section.tvDecision',
      keys: ['auto_tv_pending_days', 'auto_tv_pending_episodes', 'pending_use_volatility'],
    },
  ],
  pause: [
    {
      titleKey: 'section.autoPause',
      keys: ['pause_enhanced_enabled', 'auto_pause_users'],
    },
    {
      titleKey: 'section.airing',
      keys: ['airing_pause_days', 'movie_air_pause_days', 'tv_air_pause_days'],
    },
    {
      titleKey: 'section.noDownload',
      keys: ['movie_no_download_days', 'tv_no_download_days', 'no_download_actions'],
    },
  ],
  completion: [
    { titleKey: 'section.siteProbe', keys: ['site_total_probe_enabled'] },
    {
      titleKey: 'section.diagnostic',
      keys: [
        'progress_diagnostic_mode',
        'progress_diagnostic_stalled_rounds',
        'progress_diagnostic_cooldown_hours',
      ],
    },
    {
      titleKey: 'section.pausedProbe',
      keys: [
        'paused_probe_reasons',
        'paused_probe_min_pause_days',
        'paused_probe_interval_hours',
      ],
    },
  ],
  bestVersion: [
    {
      titleKey: 'section.bestVersionScope',
      keys: [
        'best_version_type',
        'best_version_movie_remaining_days',
        'best_version_tv_remaining_days',
      ],
    },
    {
      titleKey: 'section.backfill',
      keys: [
        'best_version_episode_to_full',
        'best_version_backfill_enabled',
        'backfill_best_version_now',
      ],
    },
  ],
  guard: [
    {
      titleKey: 'section.guard',
      keys: [
        'completion_guard_mode',
        'site_completion_evidence_enabled',
        'volatility_enabled',
        'volatility_window_days',
      ],
    },
    {
      titleKey: 'section.cadence',
      keys: [
        'cadence_enabled',
        'cadence_multiplier',
        'cadence_min_window_days',
        'cadence_min_episodes',
        'season_cooldown_days',
      ],
    },
    {
      titleKey: 'section.correction',
      keys: [
        'verify_enabled',
        'verify_interval_hours',
        'verify_retention_days',
        'timeout_release_days',
        'timeout_cadence_acceleration',
      ],
    },
  ],
  recognition: [
    {
      titleKey: 'section.recognition',
      keys: [
        'recognition_guard_mode',
        'recognition_guard_notify',
        'recognition_guard_notify_interval',
        'recognition_guard_tmdb_recheck_mode',
        'recognition_guard_cache_maxsize',
      ],
    },
    { titleKey: 'section.custom', keys: ['recognition_guard_custom_config'] },
  ],
}

const impactToneIcons: Record<PreviewItem['tone'], string> = {
  info: 'mdi-information-outline',
  success: 'mdi-check-circle-outline',
  warning: 'mdi-alert-outline',
  error: 'mdi-alert-circle-outline',
}

const activeGroupMeta = computed(
  () => localizedGroups.value.find(group => group.key === activeGroup.value) ?? localizedGroups.value[0]!,
)
const activeSections = computed(() =>
  sectionDefinitions[activeGroup.value].map(section => ({
    ...section,
    title: t(locale.value, section.titleKey),
    fields: section.keys
      .map(key => fieldsByKey.value.get(key))
      .filter((field): field is FieldMeta => Boolean(field)),
  })),
)
const summaryDomains = computed(() => Object.entries(runtimeSummary.value?.domains ?? {}))
const domainTranslationKeys: Record<string, string> = {
  '完结守卫模式': 'domain.completionGuard',
  '待定增强': 'domain.pending',
  '暂停优化': 'domain.pause',
  '自动洗版': 'domain.bestVersion',
  '下载管理': 'domain.download',
  '完成后验证': 'domain.verify',
  '站点集数探测': 'domain.siteTotal',
  '站点完结信号': 'domain.siteCompletion',
  '识别增强': 'domain.recognition',
}

function handleConfigScroll(): void {
  if (!configScrollRoot) return
  configScrollRoot.classList.add('sae-config-scroll-root--active')
  window.clearTimeout(scrollIdleTimer)
  scrollIdleTimer = window.setTimeout(() => {
    configScrollRoot?.classList.remove('sae-config-scroll-root--active')
  }, 600)
}

onMounted(() => {
  void loadSummary(props.api).then(payload => {
    runtimeSummary.value = payload
    summaryState.value = payload ? 'available' : 'unavailable'
  })

  const scrollRoot = configHeaderSentinel.value?.closest<HTMLElement>('.v-card-text') ?? null
  configScrollRoot = scrollRoot
  scrollRoot?.classList.add('sae-config-scroll-root')
  scrollRoot?.addEventListener('scroll', handleConfigScroll, { passive: true })
  headerObserver = new IntersectionObserver(
    ([entry]) => {
      headerScrolled.value = !entry?.isIntersecting
    },
    { root: scrollRoot, threshold: 1 },
  )
  if (configHeaderSentinel.value) headerObserver.observe(configHeaderSentinel.value)
})

onBeforeUnmount(() => {
  headerObserver?.disconnect()
  window.clearTimeout(scrollIdleTimer)
  configScrollRoot?.removeEventListener('scroll', handleConfigScroll)
  configScrollRoot?.classList.remove('sae-config-scroll-root', 'sae-config-scroll-root--active')
})

/** 按概览契约本地化布尔状态和已知模式，未知字符串保持后端原值。 */
function formatDomainStatus(value: boolean | string): string {
  if (typeof value === 'boolean') return t(locale.value, value ? 'config.enabled' : 'config.off')
  const modeFields: ConfigKey[] = ['completion_guard_mode', 'recognition_guard_mode', 'best_version_type']
  for (const key of modeFields) {
    const option = localizedFields.value.find(field => field.key === key)?.options
      ?.find(item => String(item.value) === value)
    if (option) return option.title
  }
  return value
}

/** 后端概览保持稳定中文键，展示层按 Host locale 翻译。 */
function formatDomainName(name: string): string {
  const key = domainTranslationKeys[name]
  return key ? t(locale.value, key) : name
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

/** 数值步进使用字段契约所需精度，避免小数系数被整数步长破坏。 */
function numberStep(key: NumberConfigKey): number {
  return key === 'cadence_multiplier' ? 0.5 : 1
}

/** 为视觉步进器计算下一有限值。 */
function stepNumber(key: NumberConfigKey, direction: -1 | 1): void {
  updateNumber(key, draft[key] + numberStep(key) * direction)
}

/** 从字段名称提取紧凑单位，百分比字段补充业务单位。 */
function fieldUnit(field: FieldMeta): string | undefined {
  if (field.key === 'download_progress_threshold') return '%'
  return field.label.match(/（([^）]+)）/)?.[1]
}

/** 多选摘要仅显示首项和剩余数量，避免可删除标签挤占控件宽度。 */
function selectionOverflowCount(key: ConfigKey): number {
  const value = draft[key]
  return Array.isArray(value) ? Math.max(0, value.length - 1) : 0
}

/** 移动端分组切换后收起导航，并将当前分组标题带回可视区域。 */
async function selectMobileGroup(group: GroupKey): Promise<void> {
  activeGroup.value = group
  mobileGroupSheet.value = false
  await nextTick()
  fieldSurfaceHeading.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

/** 保存完整配置，并确保弹窗触发位始终按关闭状态持久化。 */
function saveConfig(): void {
  emit('save', buildSavePayload())
}
</script>

<template>
  <section class="sae-config">
    <form class="sae-config__form" @submit.prevent="saveConfig">
      <div ref="configHeaderSentinel" class="sae-config-header-sentinel" aria-hidden="true" />
      <header :class="['sae-config-header', { 'sae-config-header--scrolled': headerScrolled }]">
        <div class="sae-config-header__brand">
          <img :src="saeLogo" alt="" class="sae-config-header__logo" />
          <div class="sae-config-header__identity">
            <div class="sae-config-header__crumbs">
              <span>MoviePilot</span>
              <VIcon icon="mdi-chevron-right" size="14" />
              <span>{{ t(locale, 'config.plugin') }}</span>
              <VIcon icon="mdi-chevron-right" size="14" />
            </div>
            <div class="sae-config-header__title-row">
              <h1 class="sae-config-header__title">{{ t(locale, 'config.title') }}</h1>
              <VChip color="primary" size="x-small" variant="tonal">BETA</VChip>
            </div>
          </div>
        </div>

        <div class="sae-config-header__actions">
          <span v-if="changedCount > 0" class="sae-config-header__change-state">
            <VIcon color="success" icon="mdi-check-circle" size="16" />
            {{ t(locale, 'config.changedCount', { count: changedCount }) }}
          </span>
          <VBtn
            :aria-label="t(locale, 'config.save')"
            class="sae-config-header__save"
            color="primary"
            type="submit"
            variant="flat"
          >
            <VIcon icon="mdi-content-save" start />
            {{ t(locale, 'config.save') }}
          </VBtn>
          <VBtn
            :aria-label="t(locale, 'config.close')"
            class="sae-config-header__close"
            type="button"
            variant="outlined"
            @click="emit('close')"
          >
            <VIcon icon="mdi-close" start />
            <span class="sae-config-header__close-label">{{ t(locale, 'config.close') }}</span>
          </VBtn>
        </div>
      </header>

      <div class="sae-config__body">
        <div class="sae-config-layout">
          <div class="sae-mobile-group-selector">
            <VBtn
              :aria-expanded="mobileGroupSheet"
              aria-haspopup="dialog"
              class="sae-mobile-group-trigger"
              type="button"
              variant="outlined"
              @click="mobileGroupSheet = true"
            >
              <VIcon :icon="activeGroupMeta.icon" size="19" start />
              <span>{{ activeGroupMeta.title }}</span>
              <VSpacer />
              <VIcon icon="mdi-chevron-up" size="18" />
            </VBtn>
            <VBtn
              :href="README_URL"
              :aria-label="t(locale, 'config.help')"
              class="sae-mobile-help"
              icon
              rel="noopener noreferrer"
              size="small"
              target="_blank"
              variant="text"
            >
              <VIcon icon="mdi-help-circle-outline" size="18" />
              <VTooltip activator="parent" :text="t(locale, 'config.help')" />
            </VBtn>
          </div>

          <nav class="sae-group-nav" :aria-label="t(locale, 'config.selectGroup')">
            <div class="sae-group-nav__heading">{{ t(locale, 'config.settings') }}</div>
            <VList class="sae-group-nav__list" density="compact" nav>
              <VListItem
                v-for="group in localizedGroups"
                :key="group.key"
                :active="activeGroup === group.key"
                :prepend-icon="group.icon"
                :title="group.title"
                color="primary"
                rounded="lg"
                @click="activeGroup = group.key"
              />
            </VList>
            <VBtn
              :href="README_URL"
              class="sae-group-nav__help"
              append-icon="mdi-open-in-new"
              prepend-icon="mdi-help-circle-outline"
              rel="noopener noreferrer"
              target="_blank"
              variant="text"
            >
              {{ t(locale, 'config.help') }}
            </VBtn>
          </nav>

          <main class="sae-field-surface">
            <div ref="fieldSurfaceHeading" class="sae-field-surface__heading">
              <div class="sae-field-surface__heading-copy">
                <VIcon :icon="activeGroupMeta.icon" color="primary" size="22" />
                <div>
                  <h2>{{ activeGroupMeta.title }}</h2>
                  <p>{{ activeGroupMeta.summary }}</p>
                </div>
              </div>
            </div>

            <section
              v-for="(section, sectionIndex) in activeSections"
              :key="section.title"
              class="sae-field-section"
            >
              <h3>{{ sectionIndex + 1 }}. {{ section.title }}</h3>
              <div class="sae-field-section__rows">
                <div
                  v-for="field in section.fields"
                  :key="field.key"
                  :class="['sae-field-row', { 'sae-field-row--switch': field.kind === 'switch' }]"
                >
                  <div class="sae-field-row__copy">
                    <div class="sae-field-row__label">{{ field.label }}</div>
                    <p v-if="field.hint">{{ field.hint }}</p>
                  </div>
                  <div class="sae-field-control">
                    <VSwitch
                      v-if="field.kind === 'switch'"
                      :id="`sae-field-${field.key}`"
                      v-model="draft[field.key]"
                      :aria-label="field.label"
                      color="primary"
                      density="compact"
                      hide-details
                    />
                    <VSelect
                      v-else-if="field.kind === 'select' || field.kind === 'multi-select'"
                      v-model="draft[field.key]"
                      :aria-label="field.label"
                      density="compact"
                      hide-details
                      item-title="title"
                      item-value="value"
                      :items="field.options"
                      :multiple="field.kind === 'multi-select'"
                      variant="outlined"
                    >
                      <template v-if="field.kind === 'multi-select'" #selection="{ item, index }">
                        <span v-if="index === 0" class="sae-select-summary__primary">
                          {{ item.title }}
                        </span>
                        <span v-else-if="index === 1" class="sae-select-summary__count">
                          +{{ selectionOverflowCount(field.key) }}
                        </span>
                      </template>
                    </VSelect>
                    <div
                      v-else-if="field.kind === 'number'"
                      class="sae-number-stepper"
                    >
                      <VBtn
                        :aria-label="t(locale, 'config.decrease', { label: field.label })"
                        icon
                        type="button"
                        variant="text"
                        @click="stepNumber(field.key as NumberConfigKey, -1)"
                      >
                        <VIcon icon="mdi-minus" />
                      </VBtn>
                      <VTextField
                        :id="`sae-field-${field.key}`"
                        :aria-label="field.label"
                        density="compact"
                        hide-details
                        :model-value="draft[field.key]"
                        :step="numberStep(field.key as NumberConfigKey)"
                        type="number"
                        variant="plain"
                        @update:model-value="updateNumber(field.key as NumberConfigKey, $event)"
                      />
                      <VBtn
                        :aria-label="t(locale, 'config.increase', { label: field.label })"
                        icon
                        type="button"
                        variant="text"
                        @click="stepNumber(field.key as NumberConfigKey, 1)"
                      >
                        <VIcon icon="mdi-plus" />
                      </VBtn>
                      <span v-if="fieldUnit(field)" class="sae-number-stepper__unit">
                        {{ fieldUnit(field) }}
                      </span>
                    </div>
                    <VCronField
                      v-else-if="field.kind === 'cron'"
                      v-model="draft[field.key]"
                      :aria-label="field.label"
                      density="compact"
                      hide-details
                      :placeholder="t(locale, 'config.cronPlaceholder')"
                      variant="outlined"
                    />
                    <VTextField
                      v-else-if="field.kind === 'text'"
                      :id="`sae-field-${field.key}`"
                      v-model="draft[field.key]"
                      :aria-label="field.label"
                      density="compact"
                      hide-details
                      variant="outlined"
                    />
                    <VBtn
                      v-else-if="field.kind === 'textarea'"
                      :aria-label="field.label"
                      block
                      prepend-icon="mdi-code-braces"
                      type="button"
                      variant="tonal"
                      @click="yamlDialogOpen = true"
                    >
                      {{ t(locale, 'config.editYaml') }}
                    </VBtn>
                  </div>
                </div>
              </div>
            </section>

            <section v-if="activeGroup === 'cleanup'" class="sae-field-section sae-tracker-entry">
              <div class="sae-tracker-entry__copy">
                <VIcon color="primary" icon="mdi-message-text-outline" size="22" />
                <div>
                  <strong>{{ trackerField.label }}</strong>
                  <p>{{ trackerField.hint }}</p>
                </div>
              </div>
              <VBtn
                :aria-label="t(locale, 'config.editLabel', { label: trackerField.label })"
                color="primary"
                prepend-icon="mdi-pencil-outline"
                type="button"
                variant="tonal"
                @click="trackerDialogOpen = true"
              >
                {{ t(locale, 'config.edit') }}
              </VBtn>
            </section>
          </main>

          <aside class="sae-impact-preview">
            <div class="sae-impact-preview__title">
              <VIcon color="primary" icon="mdi-eye-outline" size="20" />
              <h2>{{ t(locale, 'config.preview') }}</h2>
              <span v-if="changedCount > 0" class="sae-impact-preview__draft-state">
                <VIcon icon="mdi-pencil-outline" size="14" />
                {{ t(locale, 'config.unsaved') }}
              </span>
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

            <section :aria-label="t(locale, 'config.runtime')" class="sae-runtime-summary">
              <div class="sae-runtime-summary__title">
                <VIcon color="primary" icon="mdi-chart-box-outline" size="19" />
                <h3>{{ t(locale, 'config.runtime') }}</h3>
              </div>

              <div v-if="summaryState === 'loading'" class="sae-runtime-summary__state">
                <VProgressCircular color="primary" indeterminate size="18" width="2" />
                <span>{{ t(locale, 'config.runtimeLoading') }}</span>
              </div>

              <template v-else-if="summaryState === 'available' && runtimeSummary">
                <div class="sae-runtime-summary__metrics">
                  <div class="sae-runtime-summary__row">
                    <VIcon icon="mdi-timer-sand" size="18" />
                    <span>{{ t(locale, 'config.pendingCount') }}</span>
                    <strong>{{ runtimeSummary.pending_count }}</strong>
                  </div>
                  <div class="sae-runtime-summary__row">
                    <VIcon icon="mdi-download-network-outline" size="18" />
                    <span>{{ t(locale, 'config.monitoredCount') }}</span>
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
                    <span>{{ formatDomainName(name) }}</span>
                    <strong>{{ formatDomainStatus(status) }}</strong>
                  </div>
                </div>
              </template>

              <p v-else class="sae-runtime-summary__unavailable">{{ t(locale, 'config.runtimeUnavailable') }}</p>
            </section>
          </aside>
        </div>
      </div>

      <div class="sae-mobile-savebar">
        <span v-if="changedCount > 0" class="sae-mobile-savebar__state">
          <VIcon color="success" icon="mdi-check-circle" size="16" />
          {{ t(locale, 'config.changedCount', { count: changedCount }) }}
        </span>
        <VSpacer />
        <VBtn
          color="primary"
          :disabled="changedCount === 0"
          prepend-icon="mdi-content-save"
          type="submit"
          variant="flat"
        >
          {{ t(locale, 'config.save') }}
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
              :aria-label="`${t(locale, 'config.close')} ${trackerField.label}`"
            icon
            size="small"
            variant="text"
            @click="trackerDialogOpen = false"
          >
            <VIcon icon="mdi-close" />
            <VTooltip activator="parent" :text="t(locale, 'config.close')" />
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
            {{ t(locale, 'config.done') }}
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VBottomSheet v-model="mobileGroupSheet" class="sae-mobile-group-sheet">
      <VCard>
        <VCardTitle>{{ t(locale, 'config.selectGroup') }}</VCardTitle>
        <VList lines="two" nav>
          <VListItem
            v-for="group in localizedGroups"
            :key="group.key"
            :active="activeGroup === group.key"
            :prepend-icon="group.icon"
            :subtitle="group.summary"
            :title="group.title"
            color="primary"
            @click="selectMobileGroup(group.key)"
          >
            <template #append>
              <VIcon v-if="activeGroup === group.key" icon="mdi-check" />
            </template>
          </VListItem>
        </VList>
      </VCard>
    </VBottomSheet>

    <VDialog v-model="yamlDialogOpen" max-width="900" scrollable width="calc(100% - 24px)">
      <VCard>
        <VCardTitle class="sae-tracker-dialog__title">
          <span>{{ t(locale, 'config.yamlTitle') }}</span>
          <VBtn :aria-label="t(locale, 'config.close')" icon size="small" variant="text" @click="yamlDialogOpen = false">
            <VIcon icon="mdi-close" />
          </VBtn>
        </VCardTitle>
        <VCardText class="sae-yaml-dialog__content">
          <VAceEditor
            v-model:value="draft.recognition_guard_custom_config"
            :theme="aceTheme"
            lang="yaml"
            :options="{ fontSize: 14, showPrintMargin: false, tabSize: 2, useSoftTabs: true }"
            class="sae-yaml-editor"
          />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn color="primary" prepend-icon="mdi-check" @click="yamlDialogOpen = false">{{ t(locale, 'config.done') }}</VBtn>
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
}

:global(.sae-config-scroll-root) {
  scrollbar-color: transparent transparent;
}

:global(.sae-config-scroll-root::-webkit-scrollbar-thumb) {
  background: transparent;
  transition: background-color 160ms ease;
}

:global(.sae-config-scroll-root.sae-config-scroll-root--active) {
  scrollbar-color: rgb(var(--v-theme-perfect-scrollbar-thumb)) transparent;
}

:global(.sae-config-scroll-root.sae-config-scroll-root--active::-webkit-scrollbar-thumb) {
  background: rgb(var(--v-theme-perfect-scrollbar-thumb));
}

.sae-config-header-sentinel {
  block-size: 1px;
  margin-block-end: -1px;
  pointer-events: none;
}

.sae-field-section,
.sae-impact-preview,
.sae-mobile-savebar {
  border: var(--app-surface-border);
  border-radius: var(--app-surface-radius);
  backdrop-filter: var(--app-grouped-list-backdrop-filter);
  background: var(--app-grouped-list-background);
  box-shadow: var(--app-surface-shadow);
}

.sae-config-header {
  position: sticky;
  z-index: 20;
  inset-block-start: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-inline-size: 0;
  min-block-size: 72px;
  padding: 10px 16px;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: transparent;
  backdrop-filter: none;
  box-shadow: none;
  gap: 16px;
}

.sae-config-header--scrolled {
  --sae-header-background: var(--app-grouped-list-background);
  --sae-header-backdrop-filter: var(--app-grouped-list-backdrop-filter);

  background: var(--sae-header-background);
  backdrop-filter: var(--sae-header-backdrop-filter);
  box-shadow: var(--app-surface-shadow);
}

:global(html[data-theme='transparent'] .sae-config-header--scrolled) {
  --sae-header-background: rgba(var(--v-theme-surface), 0.72);
  --sae-header-backdrop-filter: blur(24px);
}

:global(html[data-theme='transparent'].transparent-blur-disabled .sae-config-header--scrolled) {
  --sae-header-background: rgba(var(--v-theme-surface), 0.92);
  --sae-header-backdrop-filter: none;
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
  flex: 0 0 40px;
  block-size: 40px;
  inline-size: 40px;
  object-fit: contain;
}

.sae-config-header__identity {
  min-inline-size: 0;
}

.sae-config-header__crumbs,
.sae-config-header__title-row {
  display: flex;
  align-items: center;
  min-inline-size: 0;
}

.sae-config-header__crumbs {
  margin-block-end: 3px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 0.6875rem;
  line-height: 1rem;
  gap: 2px;
}

.sae-config-header__title-row {
  gap: 8px;
}

.sae-config-header__title {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 1.0625rem;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.4rem;
}

.sae-config-header__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

.sae-config-header__change-state,
.sae-mobile-savebar > span {
  display: inline-flex;
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.66);
  font-size: 0.75rem;
  white-space: nowrap;
  gap: 7px;
}

.sae-config-header__actions :deep(.v-btn) {
  min-inline-size: 96px;
  block-size: 40px;
  font-weight: 600;
}

.sae-config__body {
  min-inline-size: 0;
  padding: 12px;
}

.sae-config-layout {
  display: grid;
  min-inline-size: 0;
  padding-block-end: calc(70px + env(safe-area-inset-bottom));
  margin-block-start: 12px;
  gap: 12px;
  grid-template-areas:
    'selector'
    'content'
    'preview';
  grid-template-columns: minmax(0, 1fr);
}

.sae-mobile-group-selector {
  display: grid;
  align-items: stretch;
  min-inline-size: 0;
  gap: 8px;
  grid-area: selector;
  grid-template-columns: minmax(0, 1fr) 48px;
}

.sae-mobile-group-trigger {
  justify-content: flex-start;
  min-inline-size: 0;
  block-size: 42px;
  padding-inline: 12px;
  text-transform: none;
}

.sae-mobile-group-trigger :deep(.v-btn__content) {
  min-inline-size: 0;
  inline-size: 100%;
  justify-content: flex-start;
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0;
}

.sae-mobile-help {
  align-self: center;
  block-size: 36px;
  inline-size: 36px;
}

.sae-group-nav {
  display: none;
  min-inline-size: 0;
  grid-area: navigation;
}

.sae-group-nav__heading {
  padding: 6px 10px 10px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 0.75rem;
  font-weight: 600;
}

.sae-group-nav > .sae-group-nav__list.v-list {
  padding: 0 4px;
  backdrop-filter: none;
  background: transparent;
  background-color: transparent;
}

.sae-group-nav__list :deep(.v-list-item) {
  position: relative;
  min-block-size: 50px;
  padding-inline: 12px;
  margin-block: 4px;
}

.sae-group-nav__list :deep(.v-list-item-title) {
  overflow-wrap: anywhere;
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.2rem;
}

.sae-group-nav__list :deep(.v-list-item__prepend > .v-icon) {
  font-size: 1.25rem;
}

.sae-group-nav__list :deep(.v-list-item--active) {
  background: rgba(var(--v-theme-primary), 0.09);
  color: rgb(var(--v-theme-primary));
}

.sae-group-nav__list :deep(.v-list-item--active)::before {
  position: absolute;
  inset-block: 8px;
  inset-inline-start: 0;
  inline-size: 3px;
  border-radius: 0 3px 3px 0;
  background: rgb(var(--v-theme-primary));
  content: '';
}

.sae-group-nav__help {
  justify-content: flex-start;
  margin-block-start: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.sae-field-surface {
  min-inline-size: 0;
  grid-area: content;
}

.sae-field-surface__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  min-inline-size: 0;
  padding: 2px 2px 12px;
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
  font-size: 1rem;
  font-weight: 700;
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

.sae-field-section {
  overflow: hidden;
  min-inline-size: 0;
}

.sae-field-section + .sae-field-section {
  margin-block-start: 12px;
}

.sae-field-section > h3 {
  padding: 14px 16px 10px;
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.25rem;
}

.sae-field-section__rows {
  padding-inline: 16px;
}

.sae-field-row {
  display: grid;
  align-items: start;
  min-inline-size: 0;
  padding-block: 13px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  gap: 18px;
  grid-template-columns: minmax(200px, 1.45fr) minmax(180px, 0.75fr);
}

.sae-field-row--switch {
  align-items: center;
}

.sae-field-row__copy {
  min-inline-size: 0;
}

.sae-field-row__label {
  display: block;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.8125rem;
  font-weight: 600;
  line-height: 1.15rem;
}

.sae-field-row__copy p {
  margin: 4px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.57);
  font-size: 0.6875rem;
  line-height: 1rem;
}

.sae-field-control,
.sae-field-control :deep(.v-input) {
  min-inline-size: 0;
  max-inline-size: 100%;
}

.sae-field-control :deep(.v-select__selection) {
  justify-content: flex-end;
  margin-inline-start: auto;
  text-align: end;
}

.sae-select-summary__primary {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sae-select-summary__count {
  flex: 0 0 auto;
  color: rgba(var(--v-theme-on-surface), 0.58);
  margin-inline-start: 6px;
  white-space: nowrap;
}

.sae-number-stepper {
  display: grid;
  align-items: center;
  min-block-size: 40px;
  inline-size: 100%;
  overflow: hidden;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.18);
  border-radius: var(--app-control-radius);
  grid-template-columns: 40px minmax(54px, 1fr) 40px auto;
}

.sae-number-stepper :deep(.v-btn) {
  min-inline-size: 40px;
  block-size: 40px;
  border-radius: 0;
}

.sae-number-stepper :deep(.v-field__input) {
  min-block-size: 40px;
  padding: 0 6px;
  text-align: center;
}

.sae-number-stepper :deep(input) {
  text-align: center;
}

.sae-number-stepper__unit {
  min-inline-size: 38px;
  padding-inline: 8px;
  border-inline-start: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 0.6875rem;
  text-align: center;
  white-space: nowrap;
}

.sae-field-row--switch .sae-field-control {
  display: flex;
  justify-content: flex-end;
}

.sae-tracker-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-inline-size: 0;
  padding: 16px;
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
  align-self: start;
  padding: 16px;
  grid-area: preview;
}

.sae-impact-preview__title,
.sae-impact-preview__group {
  display: flex;
  align-items: flex-start;
  min-inline-size: 0;
  gap: 8px;
}

.sae-impact-preview__title {
  align-items: center;
}

.sae-impact-preview__draft-state {
  display: inline-flex;
  align-items: center;
  padding: 3px 6px;
  margin-inline-start: auto;
  border-radius: var(--app-control-radius);
  background: rgba(var(--v-theme-warning), 0.12);
  color: rgb(var(--v-theme-warning));
  font-size: 0.6875rem;
  font-weight: 600;
  white-space: nowrap;
  gap: 3px;
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-block: 8px calc(8px + env(safe-area-inset-bottom));
  padding-inline: 12px;
  margin-block-start: calc(-60px - env(safe-area-inset-bottom));
  border-radius: 0;
  gap: 12px;
}

.sae-mobile-savebar__state {
  color: rgb(var(--v-theme-success));
}

.sae-yaml-dialog__content {
  min-block-size: min(60dvh, 560px);
  padding: 0 !important;
}

.sae-yaml-editor {
  block-size: min(60dvh, 560px);
  inline-size: 100%;
}

.sae-mobile-group-sheet :deep(.v-bottom-sheet__content) {
  max-block-size: min(82dvh, 680px);
}

@container (width <= 480px) {
  .sae-config-header {
    min-block-size: 64px;
    padding-inline: 10px;
    gap: 8px;
  }

  .sae-config-header__logo {
    flex-basis: 34px;
    block-size: 34px;
    inline-size: 34px;
  }

  .sae-config-header__crumbs,
  .sae-config-header__change-state,
  .sae-config-header__close-label {
    display: none;
  }

  .sae-config-header__title {
    font-size: 0.875rem;
    line-height: 1.1rem;
  }

  .sae-config-header__title-row {
    gap: 5px;
  }

  .sae-config-header__actions {
    gap: 4px;
  }

  .sae-config-header__actions :deep(.v-btn) {
    min-inline-size: 42px;
    block-size: 38px;
    padding-inline: 10px;
  }

  .sae-config-header__save :deep(.v-btn__prepend) {
    display: none;
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

  .sae-config-header__actions :deep(.sae-config-header__close) {
    min-inline-size: 40px;
    block-size: 40px;
    padding-inline: 0;
  }

  .sae-field-row {
    gap: 10px;
    grid-template-columns: minmax(0, 1fr);
  }

  .sae-field-row--switch {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .sae-field-row--switch .sae-field-control {
    align-self: center;
  }

  .sae-impact-preview__group {
    margin-block: 10px;
  }
}

@container (width >= 720px) {
  .sae-config__body {
    padding: 14px;
  }

  .sae-config-layout {
    padding-block-end: 0;
    gap: 14px;
    grid-template-areas:
      'navigation content'
      'navigation preview';
    grid-template-columns: 168px minmax(0, 1fr);
  }

  .sae-mobile-group-selector,
  .sae-mobile-savebar {
    display: none;
  }

  .sae-group-nav {
    position: sticky;
    inset-block-start: 86px;
    display: flex;
    align-self: start;
    flex-direction: column;
    block-size: clamp(480px, calc(100dvh - 150px), 760px);
    padding-block-end: 2px;
    border-inline-end: 1px solid rgba(var(--v-theme-on-surface), 0.1);
    padding-inline-end: 10px;
  }

  .sae-impact-preview {
    align-self: start;
  }
}

@container (width >= 880px) {
  .sae-config-layout {
    align-items: start;
    grid-template-areas: 'navigation content preview';
    grid-template-columns: 168px minmax(0, 1fr) 220px;
  }

  .sae-impact-preview {
    position: sticky;
    inset-block-start: 86px;
  }
}
</style>
