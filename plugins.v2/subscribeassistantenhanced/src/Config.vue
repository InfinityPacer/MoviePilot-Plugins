<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import type { PluginConfigModel } from './types'
import DomainNav, { type DomainItem } from './components/DomainNav.vue'
import GlobalControls from './components/GlobalControls.vue'
import RuntimePlan from './components/RuntimePlan.vue'
import BestVersionTab from './tabs/BestVersionTab.vue'
import CompletionSignalTab from './tabs/CompletionSignalTab.vue'
import DeleteTab from './tabs/DeleteTab.vue'
import PauseTab from './tabs/PauseTab.vue'
import PendingTab from './tabs/PendingTab.vue'

/**
 * 插件 Vue 配置页接收的宿主参数。
 */
interface ConfigProps {
  /** 宿主传入的当前插件配置。 */
  initialConfig?: PluginConfigModel
}

/**
 * 插件 Vue 配置页向宿主提交的事件。
 */
interface ConfigEmits {
  /** 保存当前配置副本，由宿主负责调用配置保存接口。 */
  save: [config: PluginConfigModel]

  /** 请求关闭配置窗口。 */
  close: []
}

const props = withDefaults(defineProps<ConfigProps>(), {
  initialConfig: () => ({}),
})

const emit = defineEmits<ConfigEmits>()

const config = reactive<PluginConfigModel>({})
const activeDomain = ref('delete')

/**
 * 业务域导航项，key 只服务于前端分区切换，不写入插件配置。
 */
const domains: DomainItem[] = [
  { key: 'delete', title: '种子删除', icon: 'mdi-delete-clock' },
  { key: 'pending', title: '订阅待定', icon: 'mdi-timer-sand' },
  { key: 'pause', title: '订阅暂停', icon: 'mdi-pause-circle-outline' },
  { key: 'best-version', title: '订阅洗版', icon: 'mdi-auto-fix' },
  { key: 'completion', title: '完结信号', icon: 'mdi-shield-check-outline' },
]

/** 保持本地编辑副本与宿主传入配置同步，避免直接修改 props。 */
function syncConfig(nextConfig: PluginConfigModel) {
  Object.keys(config).forEach(key => {
    delete config[key]
  })
  Object.assign(config, nextConfig)
}

/** 将本地配置副本提交给宿主保存。 */
function saveConfig() {
  emit('save', { ...config })
}

watch(
  () => props.initialConfig,
  nextConfig => syncConfig(nextConfig ?? {}),
  { immediate: true, deep: true },
)
</script>

<template>
  <VCard class="subscribe-assistant-config" flat>
    <VCardTitle class="config-title">
      <div>
        <div class="text-h6 font-weight-medium">订阅助手（增强版）</div>
        <div class="text-body-2 text-medium-emphasis">按业务域组织配置，保存后由插件运行时读取同一套配置键。</div>
      </div>
      <VSpacer />
      <VBtn icon="mdi-close" variant="text" density="comfortable" aria-label="关闭" @click="emit('close')" />
    </VCardTitle>

    <VDivider />

    <VCardText class="config-content">
      <VAlert
        type="warning"
        variant="tonal"
        title="BETA 功能"
        text="本插件仍处于测试阶段，可能调整订阅状态、洗版记录、下载任务和媒体文件。"
      />

      <GlobalControls :model="config" class="mt-6" />
      <RuntimePlan :model="config" class="mt-4" />

      <div class="config-domains">
        <DomainNav v-model="activeDomain" :items="domains" />
        <main class="domain-content">
          <DeleteTab v-if="activeDomain === 'delete'" :model="config" />
          <PendingTab v-else-if="activeDomain === 'pending'" :model="config" />
          <PauseTab v-else-if="activeDomain === 'pause'" :model="config" />
          <BestVersionTab v-else-if="activeDomain === 'best-version'" :model="config" />
          <CompletionSignalTab v-else :model="config" />
        </main>
      </div>
    </VCardText>

    <VDivider />

    <VCardActions class="config-actions">
      <VSpacer />
      <VBtn variant="text" @click="emit('close')">取消</VBtn>
      <VBtn color="primary" variant="flat" prepend-icon="mdi-content-save" @click="saveConfig">
        保存
      </VBtn>
    </VCardActions>
  </VCard>
</template>

<style scoped>
.subscribe-assistant-config {
  width: 100%;
}

.config-title {
  align-items: center;
  display: flex;
  gap: 16px;
  padding: 20px 24px;
}

.config-content {
  padding: 24px;
}

.config-domains {
  align-items: start;
  display: grid;
  gap: 18px;
  grid-template-columns: 220px minmax(0, 1fr);
  margin-block-start: 16px;
}

.domain-content {
  min-width: 0;
}

.config-actions {
  padding: 16px 24px;
}

@media (max-width: 900px) {
  .config-title,
  .config-actions,
  .config-content {
    padding-inline: 16px;
  }

  .config-domains {
    grid-template-columns: 1fr;
  }
}
</style>
