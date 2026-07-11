<script setup lang="ts">
import { computed, getCurrentInstance, onBeforeUnmount, onMounted, ref } from 'vue'
import { useTheme } from 'vuetify'

import saeLogo from '../assets/sae-logo.svg'
import { loadSummary, type PluginApi, type SummaryPayload } from '../config/api'
import type { ConfigKey, NumberConfigKey, SaeConfig } from '../config/defaults'
import { useConfigDraft } from '../config/draft'
import { fields, groups, type FieldMeta, type GroupKey } from '../config/fields'
import { localizeFields, localizeGroups, normalizeLocale, t } from '../config/i18n'
import { displayFieldLabel, numberFieldUnit } from '../config/presentation'
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
const { draft, changedCount, changedKeys, buildSavePayload } = useConfigDraft(props.initialConfig)
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
const yamlField = computed(() => localizedFields.value.find(
  field => field.key === 'recognition_guard_custom_config',
)!)
const changedItems = computed(() => changedKeys.value
  .slice(0, 3)
  .map(key => localizedFields.value.find(field => field.key === key))
  .filter((field): field is FieldMeta => Boolean(field)))
const hiddenChangedCount = computed(() => Math.max(0, changedKeys.value.length - changedItems.value.length))
const activeGroup = ref<GroupKey>('global')
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
let fieldScrollRoot: HTMLElement | null = null
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

const activeGroupMeta = computed(
  () => localizedGroups.value.find(group => group.key === activeGroup.value) ?? localizedGroups.value[0]!,
)
const activeSections = computed(() =>
  sectionDefinitions[activeGroup.value].map(section => ({
    ...section,
    title: t(locale.value, section.titleKey),
    fields: section.keys
      .map(key => fieldsByKey.value.get(key))
      .filter((field): field is FieldMeta => Boolean(field) && field?.kind !== 'textarea'),
  })).filter(section => section.fields.length > 0),
)
const cadenceSummary = computed(() => [
  {
    icon: 'mdi-radar',
    title: t(locale.value, 'config.generalInspection'),
    value: t(locale.value, 'config.everyMinutes', { value: draft.auto_check_interval_minutes }),
  },
  {
    icon: 'mdi-download-network-outline',
    title: t(locale.value, 'config.downloadInspection'),
    value: t(locale.value, 'config.everyMinutes', { value: draft.download_check_interval_minutes }),
  },
  {
    icon: 'mdi-database-search-outline',
    title: t(locale.value, 'config.metadataInspection'),
    value: t(locale.value, 'config.everyHours', { value: draft.meta_check_interval_hours }),
  },
  {
    icon: 'mdi-auto-fix',
    title: t(locale.value, 'config.bestVersionInspection'),
    value: draft.best_version_cron || t(locale.value, 'config.notScheduled'),
  },
])
const activeDomainCount = computed(() => {
  const values = Object.values(runtimeSummary.value?.domains ?? {})
  return {
    active: values.filter(value => value === true || (typeof value === 'string' && !['off', 'no'].includes(value))).length,
    total: values.length,
  }
})

function handleConfigScroll(event: Event): void {
  const scrollRoot = event.currentTarget as HTMLElement | null
  if (!scrollRoot) return
  scrollRoot.classList.add('sae-config-scroll-root--active')
  window.clearTimeout(scrollIdleTimer)
  scrollIdleTimer = window.setTimeout(() => {
    scrollRoot.classList.remove('sae-config-scroll-root--active')
  }, 600)
}

onMounted(() => {
  void loadSummary(props.api).then(payload => {
    runtimeSummary.value = payload
    summaryState.value = payload ? 'available' : 'unavailable'
  })

  const scrollRoot = configHeaderSentinel.value?.closest<HTMLElement>('.v-card-text') ?? null
  configScrollRoot = scrollRoot
  fieldScrollRoot = fieldSurfaceHeading.value?.closest<HTMLElement>('.sae-field-surface') ?? null
  scrollRoot?.classList.add('sae-config-scroll-root')
  fieldScrollRoot?.classList.add('sae-config-scroll-root')
  scrollRoot?.addEventListener('scroll', handleConfigScroll, { passive: true })
  fieldScrollRoot?.addEventListener('scroll', handleConfigScroll, { passive: true })
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
  fieldScrollRoot?.removeEventListener('scroll', handleConfigScroll)
  configScrollRoot?.classList.remove('sae-config-scroll-root', 'sae-config-scroll-root--active')
  fieldScrollRoot?.classList.remove('sae-config-scroll-root', 'sae-config-scroll-root--active')
})

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
  return numberFieldUnit(field.key, locale.value)
}

/** 多选摘要仅显示首项和剩余数量，避免可删除标签挤占控件宽度。 */
function selectionOverflowCount(key: ConfigKey): number {
  const value = draft[key]
  return Array.isArray(value) ? Math.max(0, value.length - 1) : 0
}

/** 移动端分组切换只更新内容并收起导航，保留用户当前阅读位置。 */
function selectMobileGroup(group: GroupKey): void {
  activeGroup.value = group
  mobileGroupSheet.value = false
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
            <VIcon color="warning" icon="mdi-circle" size="8" />
            {{ t(locale, 'config.changedCount', { count: changedCount }) }}
          </span>
          <VBtn
            class="sae-config-header__save"
            color="primary"
            :disabled="changedCount === 0"
            type="submit"
            variant="flat"
          >
            <VIcon icon="mdi-content-save" start />
            {{ t(locale, 'config.save') }}
          </VBtn>
          <VBtn
            :aria-label="t(locale, 'config.close')"
            class="sae-config-header__close"
            icon
            size="small"
            variant="text"
            @click="emit('close')"
          >
            <VIcon icon="mdi-close" />
          </VBtn>
        </div>
      </header>

      <div class="sae-config__body">
        <div class="sae-config-layout">
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
              <div class="sae-field-surface__mobile-actions">
                <VBtn
                  :aria-expanded="mobileGroupSheet"
                  :aria-label="t(locale, 'config.selectGroup')"
                  aria-haspopup="dialog"
                  class="sae-mobile-group-action"
                  icon
                  size="small"
                  type="button"
                  variant="tonal"
                  @click="mobileGroupSheet = true"
                >
                  <VIcon icon="mdi-view-list-outline" size="18" />
                  <VTooltip activator="parent" :text="t(locale, 'config.selectGroup')" />
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
                    <div class="sae-field-row__label">{{ displayFieldLabel(field) }}</div>
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
                      class="sae-text-control"
                      :clearable="false"
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
                      class="sae-text-control"
                      density="compact"
                      hide-details
                      variant="outlined"
                    />
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

            <section v-if="activeGroup === 'recognition'" class="sae-field-section sae-tracker-entry">
              <div class="sae-tracker-entry__copy">
                <VIcon color="primary" icon="mdi-code-braces" size="22" />
                <div>
                  <strong>{{ yamlField.label }}</strong>
                  <p>{{ yamlField.hint }}</p>
                </div>
              </div>
              <VBtn
                :aria-label="t(locale, 'config.editLabel', { label: yamlField.label })"
                color="primary"
                prepend-icon="mdi-pencil-outline"
                type="button"
                variant="tonal"
                @click="yamlDialogOpen = true"
              >
                {{ t(locale, 'config.edit') }}
              </VBtn>
            </section>
          </main>

          <aside class="sae-impact-preview">
            <div class="sae-impact-preview__title sae-summary-section__title">
              <VIcon color="primary" icon="mdi-clock-outline" size="20" />
              <h2>{{ t(locale, 'config.cadence') }}</h2>
            </div>
            <ul class="sae-impact-preview__list">
              <li v-for="item in cadenceSummary" :key="item.title" class="sae-impact-preview__item">
                <VIcon :icon="item.icon" size="18" />
                <span>{{ item.title }}</span>
                <strong>{{ item.value }}</strong>
              </li>
            </ul>

            <section v-if="changedItems.length" class="sae-change-summary">
              <div class="sae-change-summary__title sae-summary-section__title">
                <VIcon color="warning" icon="mdi-format-list-checks" size="19" />
                <h3>{{ t(locale, 'config.changes') }}</h3>
              </div>
              <ul>
                <li v-for="item in changedItems" :key="item.key">
                  <VIcon color="warning" icon="mdi-circle" size="6" />
                  <span>{{ displayFieldLabel(item) }}</span>
                </li>
              </ul>
              <p v-if="hiddenChangedCount > 0">
                {{ t(locale, 'config.moreChanges', { count: hiddenChangedCount }) }}
              </p>
            </section>

            <section :aria-label="t(locale, 'config.runtime')" class="sae-runtime-summary">
              <div class="sae-runtime-summary__title sae-summary-section__title">
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
                  <div class="sae-runtime-summary__row">
                    <VIcon icon="mdi-toggle-switch-outline" size="18" />
                    <span>{{ t(locale, 'config.activeDomains') }}</span>
                    <strong>{{ activeDomainCount.active }} / {{ activeDomainCount.total }}</strong>
                  </div>
                </div>
              </template>

              <p v-else class="sae-runtime-summary__unavailable">{{ t(locale, 'config.runtimeUnavailable') }}</p>
            </section>
          </aside>
        </div>
      </div>

      <div v-if="changedCount > 0" class="sae-mobile-save-dock">
        <span class="sae-mobile-save-dock__state">
          <VIcon color="warning" icon="mdi-circle" size="8" />
          {{ t(locale, 'config.changedCount', { count: changedCount }) }}
        </span>
        <VSpacer />
        <VBtn
          class="sae-mobile-save-dock__save"
          color="primary"
          :disabled="changedCount === 0"
          type="submit"
          variant="flat"
        >
          <VIcon icon="mdi-content-save" start />
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
.sae-impact-preview {
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

.sae-config-header__change-state {
  display: inline-flex;
  align-items: center;
  color: rgb(var(--v-theme-warning));
  font-size: 0.8125rem;
  font-weight: 600;
  white-space: nowrap;
  gap: 8px;
}

.sae-config-header__save {
  min-inline-size: 128px;
  font-weight: 600;
}

.sae-config-header__close {
  flex: 0 0 40px;
  block-size: 40px;
  inline-size: 40px;
}

.sae-config__body {
  min-inline-size: 0;
  padding: 12px;
}

.sae-config-layout {
  display: grid;
  min-inline-size: 0;
  margin-block-start: 12px;
  gap: 12px;
  grid-template-areas:
    'content'
    'preview';
  grid-template-columns: minmax(0, 1fr);
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

.sae-field-surface__mobile-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 4px;
}

.sae-mobile-group-action,
.sae-mobile-help {
  block-size: 36px;
  inline-size: 36px;
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

.sae-text-control :deep(input) {
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

.sae-impact-preview__title {
  display: flex;
  align-items: center;
  min-inline-size: 0;
  gap: 8px;
}

.sae-impact-preview strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: 0.875rem;
  letter-spacing: 0;
  line-height: 1.25rem;
}

.sae-impact-preview__list {
  padding: 0;
  margin: 10px 0 0;
  list-style: none;
}

.sae-impact-preview__item,
.sae-runtime-summary__row,
.sae-runtime-summary__state,
.sae-runtime-summary__title {
  display: grid;
  align-items: start;
  min-inline-size: 0;
  gap: 10px;
  grid-template-columns: 28px minmax(0, 1fr);
}

.sae-impact-preview__item {
  align-items: center;
  padding-block: 10px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 0.875rem;
  line-height: 1.25rem;
  grid-template-columns: 28px minmax(0, 1fr) minmax(0, auto);
}

.sae-impact-preview__item > .v-icon,
.sae-runtime-summary__row > .v-icon {
  justify-self: center;
  color: rgba(var(--v-theme-on-surface), 0.54);
}

.sae-impact-preview__item > span,
.sae-impact-preview__item > strong {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}

.sae-impact-preview__item > strong {
  text-align: end;
}

.sae-runtime-summary,
.sae-change-summary {
  padding-block-start: 16px;
  margin-block-start: 16px;
  border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}

.sae-summary-section__title {
  display: grid;
  align-items: center;
  gap: 10px;
  grid-template-columns: 28px minmax(0, 1fr);
}

.sae-summary-section__title > .v-icon {
  block-size: 28px;
  inline-size: 28px;
  border-radius: var(--app-control-radius);
  background: rgba(var(--v-theme-primary), 0.1);
}

.sae-change-summary .sae-summary-section__title > .v-icon {
  background: rgba(var(--v-theme-warning), 0.12);
}

.sae-summary-section__title h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.25rem;
}

.sae-runtime-summary__state,
.sae-runtime-summary__row {
  align-items: center;
  padding-block: 7px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 0.875rem;
  letter-spacing: 0;
  line-height: 1.25rem;
}

.sae-runtime-summary__state {
  margin-block-start: 6px;
}

.sae-runtime-summary__metrics {
  margin-block-start: 10px;
}

.sae-runtime-summary__row {
  grid-template-columns: 28px minmax(0, 1fr) minmax(0, auto);
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

.sae-change-summary ul {
  padding: 0;
  margin: 8px 0 0;
  list-style: none;
}

.sae-change-summary li {
  display: grid;
  align-items: center;
  min-inline-size: 0;
  padding-block: 6px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 0.875rem;
  line-height: 1.25rem;
  gap: 8px;
  grid-template-columns: 12px minmax(0, 1fr);
}

.sae-change-summary li span {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}

.sae-change-summary > p {
  margin: 4px 0 0 20px;
  color: rgb(var(--v-theme-warning));
  font-size: 0.75rem;
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

.sae-mobile-save-dock {
  position: sticky;
  z-index: 20;
  inset-block-end: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-block-size: 64px;
  padding-block: 10px calc(10px + env(safe-area-inset-bottom));
  padding-inline: 14px;
  margin-inline: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: var(--app-surface-radius);
  background: rgba(var(--v-theme-surface), 0.94);
  backdrop-filter: blur(20px);
  box-shadow: 0 -8px 24px rgba(var(--v-theme-on-surface), 0.06);
  gap: 12px;
}

.sae-mobile-save-dock__state {
  display: inline-flex;
  align-items: center;
  color: rgb(var(--v-theme-warning));
  font-size: 0.8125rem;
  font-weight: 600;
  white-space: nowrap;
  gap: 8px;
}

.sae-mobile-save-dock__save {
  min-inline-size: 128px;
  font-weight: 600;
}

:global(html[data-theme='transparent'] .sae-mobile-save-dock) {
  background: rgba(var(--v-theme-surface), 0.92);
  backdrop-filter: blur(24px);
}

:global(html[data-theme='transparent'].transparent-blur-disabled .sae-mobile-save-dock) {
  background: rgba(var(--v-theme-surface), 0.98);
  backdrop-filter: none;
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

  .sae-config-header__crumbs {
    display: none;
  }

  .sae-config-header__title {
    font-size: 0.875rem;
    line-height: 1.1rem;
  }

  .sae-config-header__title-row {
    gap: 5px;
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
  .sae-config-header__change-state,
  .sae-config-header__save {
    display: none;
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

  .sae-field-surface__mobile-actions,
  .sae-mobile-save-dock {
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
  .sae-config__form {
    display: grid;
    overflow: hidden;
    block-size: min(90dvh, 820px);
    grid-template-rows: 1px auto minmax(0, 1fr);
  }

  .sae-config__body,
  .sae-config-layout {
    min-block-size: 0;
    block-size: 100%;
  }

  .sae-config__body {
    overflow: hidden;
  }

  .sae-config-layout {
    align-items: stretch;
    grid-template-areas: 'navigation content preview';
    grid-template-columns: 168px minmax(0, 1fr) 232px;
  }

  .sae-group-nav {
    position: static;
    overflow: hidden;
    block-size: 100%;
  }

  .sae-impact-preview {
    position: static;
    overflow: hidden;
    block-size: 100%;
  }

  .sae-field-surface {
    overflow-x: hidden;
    overflow-y: auto;
    min-block-size: 0;
    padding-inline-end: 4px;
  }

  .sae-impact-preview {
    align-self: stretch;
  }
}
</style>
