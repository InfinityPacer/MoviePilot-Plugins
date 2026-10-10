<script setup lang="ts">
import { inject, onBeforeUnmount, ref } from 'vue'

import { AGENT_HOST_KEY, type MoviePilotAgentHost } from '@/host'
import { normalizeSettings, SCALE_RANGE, SETTINGS_EVENT, SPEED_RANGE, type YingSettings } from '@/stage/settings'

/** 插件配置；`scale`、`speed` 与后端 `get_form` 默认值一致。 */
interface YingConfig extends YingSettings {
  /** 是否启用插件，启用后形象才会出现在助手形象列表中。 */
  enabled: boolean
}

const props = withDefaults(
  defineProps<{
    initialConfig?: Record<string, unknown> | null
    pluginId?: string
  }>(),
  { initialConfig: null, pluginId: '' },
)

const emit = defineEmits<{
  /** 请求宿主持久化配置。 */
  save: [YingConfig]
  /** 请求宿主关闭配置页。 */
  close: []
}>()

// 旧版主程序没有该注入；此时仍可保存，只是没有实时预览。
const agent = inject<MoviePilotAgentHost | null>(AGENT_HOST_KEY, null)

function normalizeConfig(value: Record<string, unknown> | null): YingConfig {
  return { enabled: Boolean(value?.enabled), ...normalizeSettings(value) }
}

const saved = normalizeConfig(props.initialConfig)
const config = ref<YingConfig>({ ...saved })
let committed = false

/** 滑块拖动时把未保存的值推给页面上运行中的小映。 */
function preview() {
  agent?.emit?.(SETTINGS_EVENT, { ...normalizeSettings(config.value) })
}

function save() {
  committed = true
  emit('save', { ...config.value, ...normalizeSettings(config.value) })
}

function reset() {
  config.value = { ...config.value, scale: 1, speed: 1 }
  preview()
}

// 未保存就离开时把运行中的形象恢复为已保存的值。
onBeforeUnmount(() => {
  if (!committed) agent?.emit?.(SETTINGS_EVENT, { scale: saved.scale, speed: saved.speed })
})
</script>

<template>
  <v-card flat class="agent-pet-ying-config">
    <v-card-text>
      <v-switch v-model="config.enabled" label="启用插件" color="primary" hide-details class="mb-4" />
      <div class="text-subtitle-2 mb-1">角色大小</div>
      <v-slider
        v-model="config.scale"
        :min="SCALE_RANGE[0]"
        :max="SCALE_RANGE[1]"
        :step="0.05"
        color="primary"
        thumb-label
        hide-details
        aria-label="角色大小"
        @update:model-value="preview"
      >
        <template #append>
          <span class="agent-pet-ying-config__value">{{ config.scale.toFixed(2) }}×</span>
        </template>
      </v-slider>
      <div class="text-subtitle-2 mt-4 mb-1">移动速度</div>
      <v-slider
        v-model="config.speed"
        :min="SPEED_RANGE[0]"
        :max="SPEED_RANGE[1]"
        :step="0.05"
        color="primary"
        thumb-label
        hide-details
        aria-label="移动速度"
        @update:model-value="preview"
      >
        <template #append>
          <span class="agent-pet-ying-config__value">{{ config.speed.toFixed(2) }}×</span>
        </template>
      </v-slider>
      <div class="text-caption text-medium-emphasis mt-3">
        {{
          agent
            ? '拖动滑块时，页面上正在运行的小映会实时变化；保存后对所有用户生效。'
            : '当前主程序不支持实时预览，保存后刷新页面生效。'
        }}
        在个人设置的「助手形象」中选择小映后，她会出现在屏幕底部。
      </div>
    </v-card-text>
    <v-card-actions>
      <v-btn variant="text" @click="reset">恢复默认</v-btn>
      <v-spacer />
      <v-btn variant="text" @click="emit('close')">关闭</v-btn>
      <v-btn color="primary" variant="flat" @click="save">保存</v-btn>
    </v-card-actions>
  </v-card>
</template>

<style scoped>
.agent-pet-ying-config__value {
  min-width: 3.5rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
