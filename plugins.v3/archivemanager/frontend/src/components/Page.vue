<script setup lang="ts">
import { onMounted, ref } from 'vue'

import Config from './Config.vue'
import type { ApiResponse, PluginApi } from '../config/api'
import type { ArchiveConfig } from '../config/types'
import { normalizeArchiveConfig } from '../config/values'

const props = defineProps<{
  /** 宿主传入的已认证插件 API 客户端。 */
  api?: PluginApi
}>()

const emit = defineEmits<{
  /** 请求宿主关闭插件数据页。 */
  close: []
  /** 请求宿主为联邦页面提供适合的横向空间。 */
  layout: [{ maxWidth: string }]
}>()

const config = ref<ArchiveConfig | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const saving = ref(false)

function isApiResponse(value: unknown): value is ApiResponse<unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    'success' in value &&
    typeof value.success === 'boolean' &&
    'data' in value
  )
}

function responseData(value: unknown): unknown {
  return isApiResponse(value) ? value.data : value
}

async function loadConfig(): Promise<void> {
  loading.value = config.value === null
  errorMessage.value = ''
  if (!props.api) {
    config.value = null
    errorMessage.value = '宿主 API 不可用，无法读取归档配置。'
    loading.value = false
    return
  }

  try {
    const response = await props.api.get<ArchiveConfig | ApiResponse<ArchiveConfig>>('plugin/ArchiveManager')
    const data = responseData(response)
    if (data === null || data === undefined || (isApiResponse(response) && !response.success)) {
      throw new Error(isApiResponse(response) ? response.message || '归档配置读取失败' : '归档配置读取失败')
    }
    config.value = normalizeArchiveConfig(data)
  } catch {
    config.value = null
    errorMessage.value = '归档配置读取失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

async function saveConfig(next: ArchiveConfig): Promise<void> {
  if (!props.api || saving.value) return
  saving.value = true
  errorMessage.value = ''
  try {
    const response = await props.api.put<null>('plugin/ArchiveManager', next)
    if (isApiResponse(response) && !response.success) {
      throw new Error(response.message || '归档配置保存失败')
    }
    // 保存后保持 Config 挂载，读回结果不能重置当前工作区和滚动位置。
    await loadConfig()
  } catch {
    errorMessage.value = '归档配置保存失败，请稍后重试。'
  } finally {
    saving.value = false
  }
}

function handleLayout(layout: { maxWidth: string }): void {
  emit('layout', layout)
}

onMounted(() => {
  void loadConfig()
})
</script>

<template>
  <section class="archive-page">
    <div v-if="loading" class="archive-page__state">
      <VProgressCircular color="primary" indeterminate size="28" width="2" />
      <span>正在读取归档配置…</span>
    </div>
    <VAlert v-else-if="errorMessage && !config" class="archive-page__error" type="error" variant="tonal">
      {{ errorMessage }}
      <template #append>
        <VBtn size="small" variant="text" @click="loadConfig">重试</VBtn>
      </template>
    </VAlert>
    <template v-else-if="config">
      <VAlert v-if="errorMessage" class="archive-page__error" type="error" variant="tonal">
        {{ errorMessage }}
      </VAlert>
      <Config :api="api" :initial-config="config" @close="emit('close')" @layout="handleLayout" @save="saveConfig" />
    </template>
  </section>
</template>

<style scoped>
.archive-page {
  min-inline-size: 0;
}
.archive-page__state {
  display: grid;
  justify-items: center;
  min-block-size: 220px;
  padding: 36px 16px;
  color: rgba(var(--v-theme-on-surface), 0.62);
  gap: 10px;
}
.archive-page__state span {
  font-size: 0.8rem;
}
.archive-page__error {
  margin: 12px;
}
</style>
