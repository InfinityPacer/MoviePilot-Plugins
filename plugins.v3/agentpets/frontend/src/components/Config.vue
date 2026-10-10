<script setup lang="ts">
import { inject, onBeforeUnmount, ref, watch } from 'vue'

import { AGENT_HOST_KEY, type MoviePilotAgentHost, type PluginApi } from '@/host'
import PackManager from '@/sprites/PackManager.vue'
import { normalizeSettings, SETTINGS_EVENT, type YingSettings } from '@/stage/settings'
import StageSettings from '@/stage/StageSettings.vue'

/** 插件配置；与后端 `get_form` 默认值一致。素材包存于插件数据，不在配置里。 */
interface AgentPetsConfig extends YingSettings {
  /** 是否启用插件，启用后小映和素材包形象出现在助手形象列表中。 */
  enabled: boolean
}

const props = withDefaults(
  defineProps<{
    initialConfig?: Record<string, unknown> | null
    api?: PluginApi | null
    pluginId?: string
  }>(),
  { initialConfig: null, api: null, pluginId: '' },
)

const emit = defineEmits<{
  /** 请求宿主持久化配置。 */
  save: [AgentPetsConfig]
  /** 请求宿主关闭配置页。 */
  close: []
}>()

// 旧版主程序没有该注入；此时仍可保存，只是没有实时预览。
const agent = inject<MoviePilotAgentHost | null>(AGENT_HOST_KEY, null)
const saved = normalizeSettings(props.initialConfig)
const enabled = ref(Boolean(props.initialConfig?.enabled))
const stage = ref<YingSettings>({ ...saved })
let committed = false

// 调整时把未保存的值推给页面上运行中的小映。
watch(stage, value => agent?.emit?.(SETTINGS_EVENT, { ...value }), { deep: true })

function save() {
  committed = true
  emit('save', { enabled: enabled.value, ...normalizeSettings(stage.value) })
}

// 未保存就离开时把运行中的小映恢复为已保存的值。
onBeforeUnmount(() => {
  if (!committed) agent?.emit?.(SETTINGS_EVENT, { ...saved })
})
</script>

<template>
  <v-card flat class="agent-pets-config">
    <v-card-text>
      <v-switch v-model="enabled" label="启用插件" color="primary" hide-details class="mb-2" />
      <div class="text-caption text-medium-emphasis mb-6">
        启用后，小映和每个素材包都会出现在个人设置的「助手形象」里，由用户自行选择。
      </div>

      <div class="text-subtitle-1 mb-1">小映（全屏角色）</div>
      <div class="text-caption text-medium-emphasis mb-4">在整个页面上活动，可拖拽、站在页面元素上、散步和探头。</div>
      <StageSettings v-model="stage" :live-preview="!!agent" />

      <v-divider class="my-6" />

      <div class="text-subtitle-1 mb-1">素材包（入口外观）</div>
      <div class="text-caption text-medium-emphasis mb-4">
        替换右下角助手入口的画面，拖拽和气泡仍由主程序负责。每个素材包都是一个可选形象。
      </div>
      <PackManager :api="props.api" :plugin-id="props.pluginId" />
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn variant="text" @click="emit('close')">关闭</v-btn>
      <v-btn color="primary" variant="flat" @click="save">保存</v-btn>
    </v-card-actions>
  </v-card>
</template>
