<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { PluginConfigModel } from './types'

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
        <div class="text-body-2 text-medium-emphasis">多场景管理订阅，实现订阅全生命周期管理。</div>
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

      <VSwitch
        v-model="config.enabled"
        class="mt-6"
        color="primary"
        hide-details
        label="启用插件"
      />
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

.config-actions {
  padding: 16px 24px;
}
</style>
