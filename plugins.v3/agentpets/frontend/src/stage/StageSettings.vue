<script setup lang="ts">
import type { RoamMode } from '@/stage/geometry'
import { DEFAULT_SETTINGS, SCALE_RANGE, SPEED_RANGE, type YingSettings } from '@/stage/settings'

/** 小映的外观与活动范围设置；值的保存和实时预览由配置页统一处理。 */
const props = defineProps<{
  modelValue: YingSettings
  /** 主程序是否提供 `moviepilot:agent`，决定能否实时预览。 */
  livePreview: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [YingSettings] }>()

const ROAM_OPTIONS: Array<{ value: RoamMode; title: string; hint: string }> = [
  { value: 'surfaces', title: '站在页面元素上', hint: '落到卡片、对话框等元素的上边，元素移动或消失时跟着走或掉下来' },
  { value: 'floor', title: '只在底边', hint: '始终站在屏幕底边' },
  { value: 'free', title: '自由停放', hint: '没有重力，放在哪里停在哪里，空闲时在屏幕内慢慢游走' },
]

function update(patch: Partial<YingSettings>) {
  emit('update:modelValue', { ...props.modelValue, ...patch })
}

function reset() {
  emit('update:modelValue', { ...DEFAULT_SETTINGS })
}
</script>

<template>
  <div class="agent-pets-stage-settings">
    <div class="text-subtitle-2 mb-1">角色大小</div>
    <v-slider
      :model-value="props.modelValue.scale"
      :min="SCALE_RANGE[0]"
      :max="SCALE_RANGE[1]"
      :step="0.05"
      color="primary"
      thumb-label
      hide-details
      aria-label="角色大小"
      @update:model-value="(value: number) => update({ scale: Number(value) })"
    >
      <template #append>
        <span class="agent-pets-stage-settings__value">{{ props.modelValue.scale.toFixed(2) }}×</span>
      </template>
    </v-slider>
    <div class="text-subtitle-2 mt-4 mb-1">移动速度</div>
    <v-slider
      :model-value="props.modelValue.speed"
      :min="SPEED_RANGE[0]"
      :max="SPEED_RANGE[1]"
      :step="0.05"
      color="primary"
      thumb-label
      hide-details
      aria-label="移动速度"
      @update:model-value="(value: number) => update({ speed: Number(value) })"
    >
      <template #append>
        <span class="agent-pets-stage-settings__value">{{ props.modelValue.speed.toFixed(2) }}×</span>
      </template>
    </v-slider>
    <v-select
      :model-value="props.modelValue.roam"
      :items="ROAM_OPTIONS"
      item-title="title"
      item-value="value"
      label="活动范围"
      variant="outlined"
      density="comfortable"
      class="mt-5"
      :hint="ROAM_OPTIONS.find(option => option.value === props.modelValue.roam)?.hint"
      persistent-hint
      @update:model-value="(value: RoamMode) => update({ roam: value })"
    />
    <div class="d-flex align-center mt-3">
      <span class="text-caption text-medium-emphasis">
        {{
          props.livePreview
            ? '调整时页面上正在运行的小映会实时变化，保存后对所有用户生效。'
            : '当前主程序不支持实时预览，保存后刷新页面生效。'
        }}
      </span>
      <v-spacer />
      <v-btn variant="text" size="small" @click="reset">恢复默认</v-btn>
    </div>
  </div>
</template>

<style scoped>
.agent-pets-stage-settings__value {
  min-width: 3.5rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
