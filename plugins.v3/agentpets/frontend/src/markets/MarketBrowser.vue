<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'

import type { PluginApi } from '@/host'
import {
  importMarketPack,
  loadMarkets,
  marketError,
  marketUrl,
  searchMarket,
  type MarketImportMode,
  type MarketInfo,
  type MarketItem,
  type MarketPage,
} from './api'

const props = withDefaults(defineProps<{ api?: PluginApi | null; pluginId?: string }>(), { api: null, pluginId: '' })
const emit = defineEmits<{ imported: [] }>()
const toast = inject<{ success?: (message: string) => unknown } | null>('moviepilot:toast', null)
const markets = ref<MarketInfo[]>([])
const marketId = ref('')
const keyword = ref('')
const submittedKeyword = ref('')
const result = ref<MarketPage | null>(null)
const page = ref(1)
const listLoading = ref(false)
const loading = ref(false)
const listError = ref('')
const error = ref('')
const notice = ref('')
const failedImages = ref(new Set<string>())
const selected = ref<MarketItem | null>(null)
const mode = ref<MarketImportMode>('new')
const importing = ref(false)
const importError = ref('')
const importedIds = ref(new Set<string>())
const market = computed(() => markets.value.find(item => item.id === marketId.value))
const pageCount = computed(() =>
  result.value?.total === null ? null : Math.max(1, Math.ceil((result.value?.total ?? 0) / 12)),
)
let alive = true
let scopeVersion = 0
let queryVersion = 0

function imageFailed(item: MarketItem) {
  failedImages.value = new Set([...failedImages.value, item.id])
}

function preview(item: MarketItem): string {
  return failedImages.value.has(item.id) ? '' : marketUrl(item.preview)
}

/** 查询只接受当前实例、市场和最后一次请求；切换回来也不复用旧响应。 */
async function fetchPage(nextPage = 1) {
  if (!marketId.value) return
  const version = ++queryVersion
  const scope = scopeVersion
  const id = props.pluginId
  const target = marketId.value
  page.value = nextPage
  result.value = null
  error.value = ''
  failedImages.value = new Set()
  loading.value = true
  try {
    const data = await searchMarket(props.api, id, target, submittedKeyword.value, nextPage)
    if (!alive || scope !== scopeVersion || version !== queryVersion) return
    result.value = data
  } catch (reason) {
    if (alive && scope === scopeVersion && version === queryVersion)
      error.value = marketError(reason, '市场暂时无法读取，请重试')
  } finally {
    if (alive && scope === scopeVersion && version === queryVersion) loading.value = false
  }
}

async function initialize() {
  const scope = ++scopeVersion
  queryVersion++
  markets.value = []
  marketId.value = ''
  keyword.value = ''
  submittedKeyword.value = ''
  result.value = null
  selected.value = null
  failedImages.value = new Set()
  importing.value = false
  loading.value = false
  listError.value = ''
  error.value = ''
  notice.value = ''
  importError.value = ''
  importedIds.value = new Set()
  listLoading.value = true
  try {
    const data = await loadMarkets(props.api, props.pluginId)
    if (!alive || scope !== scopeVersion) return
    markets.value = data
    marketId.value = data[0]?.id ?? ''
    if (marketId.value) void fetchPage()
  } catch (reason) {
    if (alive && scope === scopeVersion) listError.value = marketError(reason, '市场列表读取失败，请重试')
  } finally {
    if (alive && scope === scopeVersion) listLoading.value = false
  }
}

function changeMarket(value: string) {
  if (importing.value) return
  marketId.value = value
  keyword.value = ''
  submittedKeyword.value = ''
  selected.value = null
  notice.value = ''
  void fetchPage()
}

function search() {
  if (importing.value || !marketId.value) return
  submittedKeyword.value = (keyword.value ?? '').trim()
  void fetchPage()
}

function clearSearch() {
  keyword.value = ''
  search()
}

function choose(item: MarketItem) {
  selected.value = item
  mode.value = importedIds.value.has(`${marketId.value}:${item.id}`) ? 'copy' : 'new'
  importError.value = ''
}

function closeReview(value: boolean) {
  if (!value && !importing.value) selected.value = null
}

/** 导入结果只通知发起操作的页面实例，失败保持确认内容与模式供重试。 */
async function importSelected() {
  if (!selected.value || importing.value) return
  const item = selected.value
  const scope = scopeVersion
  const target = marketId.value
  const id = props.pluginId
  importing.value = true
  importError.value = ''
  try {
    const saved = await importMarketPack(props.api, id, target, item.id, mode.value)
    if (!alive || scope !== scopeVersion) return
    importedIds.value = new Set([...importedIds.value, `${target}:${item.id}`])
    notice.value = `已导入 ${saved.name}`
    selected.value = null
    toast?.success?.(notice.value)
    emit('imported')
  } catch (reason) {
    if (alive && scope === scopeVersion) importError.value = marketError(reason, '导入未完成，请刷新我的素材核对后重试')
  } finally {
    if (alive && scope === scopeVersion) importing.value = false
  }
}

watch([() => props.pluginId, () => props.api], () => void initialize(), { immediate: true })
onBeforeUnmount(() => {
  alive = false
  scopeVersion++
  queryVersion++
})
</script>

<template>
  <section class="ap-market" aria-label="在线形象市场">
    <div class="ap-market__toolbar">
      <v-select
        :model-value="marketId"
        :items="markets"
        item-title="name"
        item-value="id"
        label="形象市场"
        aria-label="形象市场"
        variant="outlined"
        density="compact"
        hide-details
        :loading="listLoading"
        :disabled="listLoading || !markets.length || importing"
        @update:model-value="changeMarket"
      />
      <form class="ap-market__search" @submit.prevent="search">
        <v-text-field
          v-model="keyword"
          label="搜索形象"
          maxlength="200"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          :disabled="!marketId || importing"
          @click:clear="clearSearch"
        />
        <v-btn
          type="submit"
          color="primary"
          variant="tonal"
          icon="mdi-magnify"
          aria-label="搜索市场形象"
          :disabled="!marketId || importing"
        />
      </form>
    </div>
    <div v-if="market" class="ap-market__source">
      <span>{{ market.description }}</span>
      <v-btn
        v-if="marketUrl(market.homepage)"
        :href="marketUrl(market.homepage)"
        target="_blank"
        rel="noopener noreferrer"
        size="small"
        variant="text"
        append-icon="mdi-open-in-new"
        >市场主页</v-btn
      >
    </div>
    <v-alert v-if="notice" role="status" type="success" variant="tonal" density="compact" class="mb-4">{{
      notice
    }}</v-alert>
    <v-alert v-if="listError || error" role="alert" type="error" variant="tonal" density="compact" class="mb-4">
      {{ listError || error }}
      <template #append
        ><v-btn
          size="small"
          variant="text"
          prepend-icon="mdi-refresh"
          @click="listError ? initialize() : fetchPage(page)"
          >重试</v-btn
        ></template
      >
    </v-alert>
    <v-alert v-if="failedImages.size" role="status" type="info" variant="tonal" density="compact" class="mb-4">
      部分预览图加载失败。图片由浏览器直接加载，请打开原图检查浏览器网络；MoviePilot 图片安全域不影响此处。
    </v-alert>
    <div v-if="listLoading || loading" class="ap-market__grid" aria-label="正在加载市场形象" aria-busy="true">
      <div v-for="index in 6" :key="index" class="ap-market__skeleton">
        <v-skeleton-loader type="image, list-item-two-line" />
      </div>
    </div>
    <div v-else-if="!listError && !markets.length" class="ap-market__empty" role="status">
      <v-icon icon="mdi-storefront-outline" size="36" />
      <p>暂未接入形象市场</p>
    </div>
    <div v-else-if="result && !result.items.length" class="ap-market__empty" role="status">
      <v-icon icon="mdi-magnify" size="36" />
      <p>{{ submittedKeyword ? '没有找到匹配的形象' : '当前市场暂无形象' }}</p>
    </div>
    <div v-else-if="result" class="ap-market__grid" role="list" aria-label="市场形象">
      <article v-for="item in result.items" :key="item.id" class="ap-market__item" role="listitem">
        <button
          class="ap-market__preview"
          type="button"
          :aria-label="`预览 ${item.name}`"
          :disabled="importing"
          @click="choose(item)"
        >
          <img
            v-if="preview(item)"
            :src="preview(item)"
            :alt="item.name"
            loading="lazy"
            referrerpolicy="no-referrer"
            @error="imageFailed(item)"
          />
          <v-icon v-else icon="mdi-paw-outline" size="38" aria-hidden="true" />
        </button>
        <div class="ap-market__item-body">
          <h3 :title="item.name">{{ item.name }}</h3>
          <p class="ap-market__author">{{ item.author || '作者未提供' }}</p>
          <p class="ap-market__description" :title="item.description">{{ item.description || '暂无说明' }}</p>
          <v-btn
            v-if="failedImages.has(item.id) && marketUrl(item.preview)"
            :href="marketUrl(item.preview)"
            :aria-label="`查看 ${item.name} 原图`"
            target="_blank"
            rel="noopener noreferrer"
            size="small"
            variant="text"
            append-icon="mdi-open-in-new"
            >查看原图</v-btn
          >
          <div class="ap-market__item-actions">
            <v-chip v-if="importedIds.has(`${marketId}:${item.id}`)" size="x-small" color="success" variant="tonal"
              >已导入</v-chip
            >
            <v-spacer />
            <v-btn
              size="small"
              variant="tonal"
              color="primary"
              prepend-icon="mdi-download-outline"
              :aria-label="`导入 ${item.name}`"
              :disabled="importing"
              @click="choose(item)"
              >导入</v-btn
            >
          </div>
        </div>
      </article>
    </div>
    <div v-if="result" class="ap-market__pagination" aria-label="市场分页">
      <span role="status"
        >{{ result.total === null ? '总量未知' : `共 ${result.total} 个形象` }} · 第 {{ page }} 页{{
          pageCount ? ` / ${pageCount}` : ''
        }}</span
      >
      <div>
        <v-btn
          icon="mdi-chevron-left"
          aria-label="上一页"
          variant="text"
          size="small"
          :disabled="page <= 1 || loading || importing"
          @click="fetchPage(page - 1)"
        />
        <v-btn
          icon="mdi-chevron-right"
          aria-label="下一页"
          variant="text"
          size="small"
          :disabled="!result.has_more || loading || importing"
          @click="fetchPage(page + 1)"
        />
      </div>
    </div>
    <v-dialog :model-value="!!selected" max-width="580" :persistent="importing" @update:model-value="closeReview">
      <v-card v-if="selected" :title="selected.name">
        <v-card-text>
          <div class="ap-market__review-preview">
            <img
              v-if="preview(selected)"
              :src="preview(selected)"
              :alt="selected.name"
              referrerpolicy="no-referrer"
              @error="imageFailed(selected)"
            />
            <v-icon v-else icon="mdi-paw-outline" size="60" />
          </div>
          <v-alert
            v-if="failedImages.has(selected.id)"
            role="status"
            type="info"
            variant="tonal"
            density="compact"
            class="mt-3"
          >
            浏览器无法加载预览图，不影响尝试导入。
            <v-btn
              v-if="marketUrl(selected.preview)"
              :href="marketUrl(selected.preview)"
              :aria-label="`查看 ${selected.name} 原图`"
              target="_blank"
              rel="noopener noreferrer"
              size="small"
              variant="text"
              append-icon="mdi-open-in-new"
              >查看原图</v-btn
            >
          </v-alert>
          <p class="ap-market__review-description">{{ selected.description || '暂无说明' }}</p>
          <dl class="ap-market__metadata">
            <dt>市场</dt>
            <dd>{{ market?.name }}</dd>
            <dt>作者</dt>
            <dd>{{ selected.author || '未提供' }}</dd>
            <dt>许可</dt>
            <dd>{{ selected.license || '未提供' }}</dd>
          </dl>
          <v-btn
            v-if="marketUrl(selected.source_url)"
            :href="marketUrl(selected.source_url)"
            target="_blank"
            rel="noopener noreferrer"
            size="small"
            variant="text"
            append-icon="mdi-open-in-new"
            class="mb-3"
            >查看来源</v-btn
          >
          <v-radio-group v-model="mode" label="导入方式" :disabled="importing" hide-details>
            <v-radio label="新增素材" value="new" /><v-radio label="导入副本" value="copy" />
          </v-radio-group>
          <v-alert v-if="importError" role="alert" type="error" variant="tonal" density="compact" class="mt-3">{{
            importError
          }}</v-alert>
        </v-card-text>
        <v-card-actions
          ><v-spacer /><v-btn :disabled="importing" @click="selected = null">取消</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            prepend-icon="mdi-download-outline"
            :loading="importing"
            :disabled="importing"
            @click="importSelected"
            >确认导入</v-btn
          >
        </v-card-actions>
      </v-card>
    </v-dialog>
  </section>
</template>

<style scoped>
.ap-market {
  min-width: 0;
}
.ap-market__toolbar {
  display: grid;
  grid-template-columns: minmax(160px, 210px) minmax(0, 1fr);
  gap: 12px;
}
.ap-market__search {
  display: flex;
  gap: 8px;
  min-width: 0;
  align-items: center;
}
.ap-market__search > :first-child {
  min-width: 0;
  flex: 1;
}
.ap-market__source {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 12px 0 18px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.ap-market__source > span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.ap-market__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 180px), 1fr));
  gap: 14px;
}
.ap-market__item {
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
.ap-market__preview {
  display: grid;
  place-items: center;
  width: 100%;
  aspect-ratio: 1;
  border: 0;
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-on-surface), 0.035);
  cursor: pointer;
}
.ap-market__preview:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -3px;
}
.ap-market__preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  padding: 12px;
}
.ap-market__item-body {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 12px;
  flex: 1;
}
.ap-market__item h3 {
  font-size: 14px;
  line-height: 1.5;
  font-weight: 600;
}
.ap-market__item h3,
.ap-market__description {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.ap-market__author,
.ap-market__description {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.ap-market__author {
  overflow-wrap: anywhere;
}
.ap-market__description {
  min-height: 3em;
}
.ap-market__item-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: auto;
  padding-top: 5px;
}
.ap-market__pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 18px;
  font-size: 12px;
}
.ap-market__empty {
  padding: 44px 12px;
  display: grid;
  justify-items: center;
  gap: 10px;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.ap-market__review-preview {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  place-items: center;
  height: 210px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.035);
  border-radius: 8px;
}
.ap-market__review-preview img {
  display: block;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
.ap-market__review-description {
  margin: 16px 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.ap-market__metadata {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  gap: 8px 12px;
  font-size: 13px;
}
.ap-market__metadata dt {
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.ap-market__metadata dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.ap-market__skeleton {
  border-radius: 8px;
  overflow: hidden;
}
@media (max-width: 600px) {
  .ap-market__toolbar {
    grid-template-columns: minmax(0, 1fr);
  }
  .ap-market__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  .ap-market__item-body {
    padding: 10px;
  }
  .ap-market__source {
    align-items: flex-start;
  }
  .ap-market__pagination {
    flex-wrap: wrap;
  }
}
@media (max-width: 340px) {
  .ap-market__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
