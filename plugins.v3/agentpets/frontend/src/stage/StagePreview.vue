<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref } from 'vue'

import { AGENT_HOST_KEY, type AgentRect, type MoviePilotAgentHost, type PluginApi } from '@/host'
import type { RoamMode } from '@/stage/geometry'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import { DEFAULT_SETTINGS, ROAM_MODES, SCALE_RANGE, SETTINGS_EVENT, SPEED_RANGE } from '@/stage/settings'
import AgentPet from './AgentPet.vue'

/**
 * 开发预览页：用页面内模拟宿主驱动一只独立的小映，手动触发每个宿主事件。
 *
 * 宿主事件只能由宿主发出，插件的 `emit` 不能伪造 `agent.*`，所以即使主程序提供了
 * `moviepilot:agent`，预览实例也始终连接模拟对象；真实宿主只用于展示可用状态。
 */
const props = withDefaults(defineProps<{ api?: PluginApi | null; pluginId?: string }>(), {
  api: null,
  pluginId: '',
})

const realHost = inject<MoviePilotAgentHost | null>(AGENT_HOST_KEY, null)
const instanceId = computed(() => props.pluginId || 'AgentPets')
const running = ref(false)
const anchor = ref<AgentRect | null>(null)
const interacting = ref(false)
const bubbleText = ref('')
const callLog = ref<string[]>([])
const motionAllowed = ref(true)
const pageVisible = ref(true)
const available = ref(true)
const panelShown = ref(false)
const keyboardInset = ref(0)
const scale = ref(DEFAULT_SETTINGS.scale)
const speed = ref(DEFAULT_SETTINGS.speed)
const roam = ref<RoamMode>(DEFAULT_SETTINGS.roam)

let host = createMockHost(instanceId.value, call => {
  callLog.value = [call, ...callLog.value].slice(0, 8)
})
let pet = createPet()
let bubbleTimer = 0

function createPet() {
  return createMockPet('stage', 'ying', {
    onAnchor: rect => (anchor.value = rect),
    onInteracting: value => (interacting.value = value),
  })
}

const panelRect = computed<AgentRect | null>(() => {
  if (!panelShown.value) return null
  const width = Math.min(380, window.innerWidth - 32)
  const height = Math.round(window.innerHeight * 0.6)
  return { x: window.innerWidth - width - 16, y: window.innerHeight - height - 16, width, height }
})

const bubbleStyle = computed(() => {
  if (!anchor.value) return { display: 'none' }
  const left = Math.min(Math.max(8, anchor.value.x + anchor.value.width / 2 - 110), window.innerWidth - 228)
  return { left: `${left}px`, top: `${Math.max(8, anchor.value.y - 64)}px` }
})

function start() {
  host.dispose()
  host = createMockHost(instanceId.value, call => {
    callLog.value = [call, ...callLog.value].slice(0, 8)
  })
  pet = createPet()
  host.patch({ motionAllowed: motionAllowed.value, pageVisible: pageVisible.value, available: available.value })
  running.value = true
}

function stop() {
  running.value = false
  anchor.value = null
}

function say(text: string) {
  bubbleText.value = text
  window.clearTimeout(bubbleTimer)
  bubbleTimer = window.setTimeout(() => (bubbleText.value = ''), 2400)
}

/** 每个按钮同时更新模拟状态并派发宿主事件，与真实宿主的顺序一致。 */
const events: Array<{ label: string; run: () => void }> = [
  {
    label: 'panel.open',
    run: () => {
      panelShown.value = true
      host.patch({ panelOpen: true, panelRect: panelRect.value })
      host.fire('agent.panel.open')
    },
  },
  {
    label: 'panel.close',
    run: () => {
      panelShown.value = false
      host.patch({ panelOpen: false, panelRect: null })
      host.fire('agent.panel.close')
    },
  },
  {
    label: 'thinking.start',
    run: () => {
      host.patch({ thinking: true, phase: 'thinking' })
      host.fire('agent.thinking.start')
    },
  },
  {
    label: 'thinking.end',
    run: () => {
      host.patch({ thinking: false, phase: 'idle' })
      host.fire('agent.thinking.end')
    },
  },
  {
    label: 'tool.start',
    run: () => {
      host.patch({ phase: 'tool', toolName: 'search_media' })
      host.fire('agent.tool.start', { name: 'search_media' })
    },
  },
  {
    label: 'tool.end',
    run: () => {
      host.patch({ phase: 'thinking', toolName: null })
      host.fire('agent.tool.end', { name: 'search_media' })
    },
  },
  {
    label: 'awaiting',
    run: () => {
      host.patch({ phase: 'awaiting', thinking: false })
      host.fire('agent.awaiting')
    },
  },
  {
    label: 'done',
    run: () => {
      host.patch({ phase: 'done', thinking: false })
      host.fire('agent.done', { message: '已完成' })
      say('搞定啦')
    },
  },
  {
    label: 'error',
    run: () => {
      host.patch({ phase: 'error', thinking: false })
      host.fire('agent.error', { message: '出错了' })
      say('好像出错了')
    },
  },
  {
    label: 'preview',
    run: () => {
      host.fire('agent.preview', { text: '正在为你查找影片…' })
      say('正在为你查找影片…')
    },
  },
  {
    label: 'bubble',
    run: () => {
      host.fire('agent.bubble', { id: 'demo', kind: 'notification', variant: 'info', text: '订阅已更新' })
      say('订阅已更新')
    },
  },
]

function patchState() {
  host.patch({
    motionAllowed: motionAllowed.value,
    reducedMotion: !motionAllowed.value,
    pageVisible: pageVisible.value,
    available: available.value,
    viewport: { ...host.getState().viewport, keyboardInset: keyboardInset.value },
  })
}

function pushSettings() {
  host.emit(SETTINGS_EVENT, { scale: scale.value, speed: speed.value, roam: roam.value })
}

onBeforeUnmount(() => {
  window.clearTimeout(bubbleTimer)
  running.value = false
  host.dispose()
})
</script>

<template>
  <div class="agent-pet-ying-page">
    <div class="d-flex flex-wrap ga-2 mb-4">
      <v-btn v-if="!running" color="primary" variant="flat" @click="start">放出预览小映</v-btn>
      <v-btn v-else variant="tonal" @click="stop">收起预览小映</v-btn>
      <v-btn v-if="realHost" variant="text" @click="realHost.open?.()">打开真实助手面板</v-btn>
    </div>

    <div class="text-subtitle-2 mb-2">宿主事件</div>
    <div class="d-flex flex-wrap ga-2 mb-4">
      <v-btn
        v-for="item in events"
        :key="item.label"
        size="small"
        variant="tonal"
        :disabled="!running"
        @click="item.run"
      >
        {{ item.label }}
      </v-btn>
    </div>

    <div class="text-subtitle-2 mb-1">宿主状态</div>
    <div class="d-flex flex-wrap ga-4 mb-2">
      <v-switch
        v-model="motionAllowed"
        label="允许动画"
        hide-details
        density="compact"
        @update:model-value="patchState"
      />
      <v-switch
        v-model="pageVisible"
        label="页面可见"
        hide-details
        density="compact"
        @update:model-value="patchState"
      />
      <v-switch
        v-model="available"
        label="Agent 可用"
        hide-details
        density="compact"
        @update:model-value="patchState"
      />
    </div>
    <v-slider
      v-model="keyboardInset"
      :min="0"
      :max="320"
      :step="10"
      label="键盘高度"
      thumb-label
      hide-details
      class="mb-2"
      @update:model-value="patchState"
    />
    <v-slider
      v-model="scale"
      :min="SCALE_RANGE[0]"
      :max="SCALE_RANGE[1]"
      :step="0.05"
      label="角色大小"
      thumb-label
      hide-details
      class="mb-2"
      @update:model-value="pushSettings"
    />
    <v-slider
      v-model="speed"
      :min="SPEED_RANGE[0]"
      :max="SPEED_RANGE[1]"
      :step="0.05"
      label="移动速度"
      thumb-label
      hide-details
      @update:model-value="pushSettings"
    />
    <v-btn-toggle
      v-model="roam"
      mandatory
      density="comfortable"
      variant="outlined"
      divided
      class="mt-3"
      @update:model-value="pushSettings"
    >
      <v-btn v-for="mode in ROAM_MODES" :key="mode" :value="mode" size="small">{{ mode }}</v-btn>
    </v-btn-toggle>

    <div class="text-caption text-medium-emphasis mt-4">
      锚点：{{
        anchor
          ? `${Math.round(anchor.x)}, ${Math.round(anchor.y)} · ${Math.round(anchor.width)}×${Math.round(anchor.height)}`
          : '无'
      }}
      · 拖拽中：{{ interacting ? '是' : '否' }} · 最近调用：{{ callLog.join('，') || '无' }}
    </div>

    <!-- 预览图层挂到 body，避免弹窗的 transform 让 fixed 定位相对弹窗计算。 -->
    <Teleport v-if="running" to="body">
      <div class="agent-pet-ying-page__stage">
        <div
          v-if="panelRect"
          class="agent-pet-ying-page__panel"
          :style="{
            left: `${panelRect.x}px`,
            top: `${panelRect.y}px`,
            width: `${panelRect.width}px`,
            height: `${panelRect.height}px`,
          }"
        >
          模拟面板
        </div>
        <AgentPet :agent="host" :pet="pet" :api="props.api" :plugin-id="instanceId" />
        <div v-if="bubbleText && anchor" class="agent-pet-ying-page__bubble" :style="bubbleStyle">{{ bubbleText }}</div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.agent-pet-ying-page__panel {
  position: fixed;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.3);
  border-radius: 16px;
  background: rgba(var(--v-theme-surface), 0.85);
  color: rgba(var(--v-theme-on-surface), 0.6);
  pointer-events: none;
}

.agent-pet-ying-page__bubble {
  position: fixed;
  max-width: 220px;
  padding: 8px 12px;
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.16);
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.875rem;
  pointer-events: none;
}

.agent-pet-ying-page__stage {
  position: fixed;
  inset: 0;
  z-index: 2600;
  pointer-events: none;
}
</style>
