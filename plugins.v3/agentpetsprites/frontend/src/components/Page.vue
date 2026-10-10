<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref } from 'vue'

import { AGENT_HOST_KEY, type MoviePilotAgentHost, type PluginApi } from '@/host'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import { BUILTIN_PACK, BUILTIN_PACK_ID, HOST_ACTIONS, HOST_INTENTS } from '@/pack/schema'
import AgentPet from './AgentPet.vue'

/**
 * 开发预览页：在与宿主入口触发区等大的框里渲染素材包，手动切换动作、intent 和宿主事件。
 *
 * renderer 模式下宿主把事件归纳成 action / intent 再传给组件，这里的事件按钮按同样的方式
 * 换算成 props；宿主对象只用于展示可用状态，预览实例始终连接页面内模拟对象。
 */
const props = withDefaults(defineProps<{ api?: PluginApi | null; pluginId?: string }>(), {
  api: null,
  pluginId: '',
})
const emit = defineEmits<{ close: []; switch: [] }>()

const realHost = inject<MoviePilotAgentHost | null>(AGENT_HOST_KEY, null)
const instanceId = computed(() => props.pluginId || 'AgentPetSprites')
const packs = ref<Array<{ id: string; name: string }>>([{ id: BUILTIN_PACK_ID, name: BUILTIN_PACK.name }])
const selected = ref(BUILTIN_PACK_ID)
const action = ref<string | null>(null)
const intent = ref<string>('idle')
const thinking = ref(false)
const motionActive = ref(true)
const large = ref(false)
const status = ref({ action: '', frame: '' })
const stageRef = ref<HTMLElement | null>(null)
const host = createMockHost(instanceId.value)
const pet = computed(() => createMockPet('renderer', selected.value))
let actionTimer = 0
let statusTimer = 0

/** 宿主事件到 renderer props 的近似换算，用于观察素材包对各阶段的反应。 */
const events: Array<{ label: string; run: () => void }> = [
  { label: 'panel.open', run: () => playAction('wave') },
  { label: 'panel.close', run: () => (intent.value = 'docked') },
  { label: 'thinking.start', run: () => ((thinking.value = true), (intent.value = 'thinking')) },
  { label: 'thinking.end', run: () => ((thinking.value = false), (intent.value = 'idle')) },
  { label: 'tool.start', run: () => (intent.value = 'thinking') },
  { label: 'tool.end', run: () => (intent.value = thinking.value ? 'thinking' : 'idle') },
  { label: 'awaiting', run: () => (intent.value = 'notify') },
  { label: 'done', run: () => ((thinking.value = false), (intent.value = 'success')) },
  { label: 'error', run: () => ((thinking.value = false), (intent.value = 'error')) },
  { label: 'preview', run: () => (intent.value = 'speaking') },
  { label: 'bubble', run: () => (intent.value = 'notify') },
]

/** 与宿主一致：动作播放一段时间后清空，回到 intent 对应的序列。 */
function playAction(name: string) {
  action.value = name
  window.clearTimeout(actionTimer)
  actionTimer = window.setTimeout(() => (action.value = null), 2400)
}

async function loadPacks() {
  if (!props.api?.get) return
  try {
    const response = await props.api.get<Array<{ id: string; name: string }>>(`plugin/${instanceId.value}/packs`)
    if (response?.success && Array.isArray(response.data) && response.data.length) packs.value = response.data
  } catch {
    console.warn('[AgentPetSprites] packs unavailable')
  }
}

onMounted(() => {
  loadPacks()
  statusTimer = window.setInterval(() => {
    const root = stageRef.value?.querySelector<HTMLElement>('.agent-pet-sprites')
    status.value = { action: root?.dataset.action ?? '', frame: root?.dataset.frame ?? '' }
  }, 150)
})

onBeforeUnmount(() => {
  window.clearTimeout(actionTimer)
  window.clearInterval(statusTimer)
  host.dispose()
})
</script>

<template>
  <v-card flat class="agent-pet-sprites-page">
    <v-card-item>
      <v-card-title>助手形象素材包 · 开发预览</v-card-title>
      <v-card-subtitle>
        {{
          realHost
            ? `主程序已提供助手宿主（Agent ${realHost.getState?.().available ? '已启用' : '未启用'}），预览使用页面内模拟对象`
            : '主程序未提供助手宿主，使用页面内模拟对象'
        }}
      </v-card-subtitle>
    </v-card-item>
    <v-card-text>
      <div class="agent-pet-sprites-page__layout">
        <div>
          <div
            ref="stageRef"
            class="agent-pet-sprites-page__stage"
            :class="{ 'agent-pet-sprites-page__stage--large': large }"
          >
            <AgentPet
              :key="selected"
              :agent="host"
              :pet="pet"
              :api="props.api"
              :plugin-id="instanceId"
              :action="action"
              :intent="intent"
              :thinking="thinking"
              :motion-active="motionActive"
            />
          </div>
          <div class="text-caption text-medium-emphasis mt-2">
            播放：{{ status.action || '—' }} · 帧：{{ status.frame || '—' }}
          </div>
        </div>
        <div class="flex-grow-1">
          <v-select
            v-model="selected"
            :items="packs"
            item-title="name"
            item-value="id"
            label="素材包"
            density="compact"
            variant="outlined"
            hide-details
            class="mb-3"
          />
          <div class="d-flex flex-wrap ga-4">
            <v-switch v-model="motionActive" label="motionActive" density="compact" hide-details />
            <v-switch v-model="thinking" label="thinking" density="compact" hide-details />
            <v-switch v-model="large" label="放大预览框" density="compact" hide-details />
          </div>
        </div>
      </div>

      <div class="text-subtitle-2 mt-4 mb-2">宿主事件</div>
      <div class="d-flex flex-wrap ga-2">
        <v-btn v-for="item in events" :key="item.label" size="small" variant="tonal" @click="item.run">
          {{ item.label }}
        </v-btn>
      </div>

      <div class="text-subtitle-2 mt-4 mb-2">宿主动作</div>
      <div class="d-flex flex-wrap ga-2">
        <v-btn
          v-for="name in HOST_ACTIONS"
          :key="name"
          size="small"
          :variant="action === name ? 'flat' : 'tonal'"
          :color="action === name ? 'primary' : undefined"
          @click="playAction(name)"
        >
          {{ name }}
        </v-btn>
      </div>

      <div class="text-subtitle-2 mt-4 mb-2">Intent</div>
      <v-chip-group v-model="intent" mandatory selected-class="text-primary" column>
        <v-chip v-for="name in HOST_INTENTS" :key="name" :value="name" size="small" variant="outlined">
          {{ name }}
        </v-chip>
      </v-chip-group>
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn variant="text" @click="emit('switch')">设置</v-btn>
      <v-btn variant="text" @click="emit('close')">关闭</v-btn>
    </v-card-actions>
  </v-card>
</template>

<style scoped>
.agent-pet-sprites-page__layout {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  align-items: flex-start;
}

/* 与宿主入口触发区等大。 */
.agent-pet-sprites-page__stage {
  position: relative;
  width: 5.4rem;
  height: 5.1rem;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.24);
  border-radius: 12px;
}

.agent-pet-sprites-page__stage--large {
  width: 10.8rem;
  height: 10.2rem;
}
</style>
