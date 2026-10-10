<script setup lang="ts">
import { inject, ref } from 'vue'

import { AGENT_HOST_KEY, HOST_UNSUPPORTED_MESSAGE, type MoviePilotAgentHost, type PluginApi } from '@/host'
import SpritePreview from '@/sprites/SpritePreview.vue'
import StagePreview from '@/stage/StagePreview.vue'

/**
 * 开发预览页：小映和素材包各一块，都由页面内模拟宿主驱动。
 *
 * 宿主事件只能由宿主发出，插件的 `emit` 不能伪造 `agent.*`，所以即使主程序提供了
 * `moviepilot:agent`，预览实例也始终连接模拟对象；真实宿主只用于展示可用状态。
 */
const props = withDefaults(defineProps<{ api?: PluginApi | null; pluginId?: string }>(), {
  api: null,
  pluginId: '',
})
const emit = defineEmits<{ close: []; switch: [] }>()

const realHost = inject<MoviePilotAgentHost | null>(AGENT_HOST_KEY, null)
const tab = ref<'stage' | 'sprites'>('stage')
</script>

<template>
  <v-card flat class="agent-pets-page">
    <v-alert v-if="!realHost" type="warning" variant="tonal" density="compact" class="ma-4 mb-0">
      {{ HOST_UNSUPPORTED_MESSAGE }}
    </v-alert>
    <v-card-item>
      <v-card-title>助手形象 · 开发预览</v-card-title>
      <v-card-subtitle>
        {{
          realHost
            ? `主程序已提供助手宿主（Agent ${realHost.getState?.().available ? '已启用' : '未启用'}），预览实例由页面内模拟对象驱动`
            : '主程序未提供助手宿主，使用页面内模拟对象'
        }}
      </v-card-subtitle>
    </v-card-item>
    <v-tabs v-model="tab" class="px-4">
      <v-tab value="stage">小映（全屏角色）</v-tab>
      <v-tab value="sprites">素材包（入口外观）</v-tab>
    </v-tabs>
    <v-card-text>
      <StagePreview v-if="tab === 'stage'" :api="props.api" :plugin-id="props.pluginId" />
      <SpritePreview v-else :api="props.api" :plugin-id="props.pluginId" />
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn variant="text" @click="emit('switch')">设置</v-btn>
      <v-btn variant="text" @click="emit('close')">关闭</v-btn>
    </v-card-actions>
  </v-card>
</template>
