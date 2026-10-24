<script setup lang="ts">
import { computed } from 'vue'
import type { RoamMode } from '@/stage/geometry'
import { DEFAULT_SETTINGS, SCALE_RANGE, SPEED_RANGE, type YingSettings } from '@/stage/settings'
import { defaultDialogue, type DialogueSettings } from './dialogue'

/** 全屏角色的外观与活动范围设置；值的保存和实时预览由配置页统一处理。 */
const props = defineProps<{
  modelValue: YingSettings
  /** 主程序是否提供 `moviepilot:agent`，决定能否实时预览。 */
  livePreview: boolean
  disabled?: boolean
  previewOnly?: boolean
  petKey?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [YingSettings] }>()
const dialogue = computed(() => props.modelValue.dialogue ?? defaultDialogue(props.petKey ?? 'ying'))

const ROAM_OPTIONS: Array<{ value: RoamMode; title: string; hint: string }> = [
  { value: 'surfaces', title: '站在页面元素上', hint: '落到卡片、对话框等元素的上边，元素移动或消失时跟着走或掉下来' },
  { value: 'floor', title: '只在底边', hint: '始终站在屏幕底边' },
  { value: 'free', title: '自由活动', hint: '没有重力，空闲时在屏幕内慢慢游走' },
]

function update(patch: Partial<YingSettings>) {
  emit('update:modelValue', { ...props.modelValue, ...patch })
}

function reset() {
  emit('update:modelValue', {
    ...DEFAULT_SETTINGS,
    ...(props.modelValue.peek_angles ? { peek_angles: props.modelValue.peek_angles } : {}),
    ...(props.modelValue.dialogue ? { dialogue: { ...props.modelValue.dialogue } } : {}),
  })
}
</script>

<template>
  <div class="agent-pets-stage-settings">
    <v-select
      :model-value="props.modelValue.movement ?? 'auto'"
      :items="[
        { title: '自主活动', value: 'auto' },
        { title: '固定位置', value: 'fixed' },
      ]"
      label="活动方式"
      variant="outlined"
      density="compact"
      :disabled="props.disabled"
      :hint="
        props.modelValue.movement === 'fixed'
          ? '拖到哪里就停在哪里；保留会话动作，仅在超出可见区域时限位。'
          : '按活动范围散步、下落和避让控件。'
      "
      persistent-hint
      class="mb-4"
      @update:model-value="(value: 'auto' | 'fixed') => update({ movement: value })"
    />
    <div class="text-subtitle-2 mb-1">角色大小</div>
    <v-slider
      :model-value="props.modelValue.scale"
      :min="SCALE_RANGE[0]"
      :max="SCALE_RANGE[1]"
      :step="0.05"
      color="primary"
      thumb-label
      :disabled="props.disabled"
      hide-details
      aria-label="角色大小"
      @update:model-value="(value: number) => update({ scale: Number(value) })"
    >
      <template #append>
        <span class="agent-pets-stage-settings__value">{{ props.modelValue.scale.toFixed(2) }}×</span>
      </template>
    </v-slider>
    <template v-if="props.modelValue.movement !== 'fixed'">
      <div class="text-subtitle-2 mt-4 mb-1">移动速度</div>
      <v-slider
        :model-value="props.modelValue.speed"
        :min="SPEED_RANGE[0]"
        :max="SPEED_RANGE[1]"
        :step="0.05"
        color="primary"
        thumb-label
        :disabled="props.disabled"
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
        density="compact"
        :disabled="props.disabled"
        class="mt-5"
        :hint="ROAM_OPTIONS.find(option => option.value === props.modelValue.roam)?.hint"
        persistent-hint
        @update:model-value="(value: RoamMode) => update({ roam: value })"
      />
    </template>
    <template v-if="props.petKey">
      <div class="text-subtitle-2 mt-5 mb-2">角色台词</div>
      <v-select
        :model-value="dialogue.mode"
        :items="[
          { title: '关闭', value: 'off' },
          { title: '仅互动与问候', value: 'interaction' },
          { title: '互动与偶尔感叹', value: 'occasional' },
        ]"
        label="话量"
        variant="outlined"
        density="compact"
        :disabled="props.disabled"
        hint="只控制角色短句，不影响自主活动或系统通知。"
        persistent-hint
        class="mb-4"
        @update:model-value="(mode: DialogueSettings['mode']) => update({ dialogue: { ...dialogue, mode } })"
      />
      <v-select
        :model-value="dialogue.voice"
        :items="[
          { title: props.petKey === 'ying' ? '原有小映台词' : '默认自然语气', value: 'default' },
          { title: '自然', value: 'neutral' },
          { title: '活泼', value: 'lively' },
          { title: '轻微嘴硬', value: 'wry' },
        ]"
        label="语气"
        variant="outlined"
        density="compact"
        :disabled="props.disabled || dialogue.mode === 'off'"
        hint="按当前 Pet 独立保存；需主程序支持原生角色台词。预览区不说话。"
        persistent-hint
        @update:model-value="(voice: DialogueSettings['voice']) => update({ dialogue: { ...dialogue, voice } })"
      />
    </template>
    <div class="d-flex align-start flex-column ga-2 mt-3">
      <!-- 没有宿主对象时配置页顶部已提示升级主程序，这里不再重复。 -->
      <span v-if="props.livePreview" class="text-caption text-medium-emphasis">
        {{
          props.previewOnly
            ? '仅在预览区试调。大小、速度与台词按当前 Pet 独立保存；活动方式与范围仍共享。'
            : '大小、速度与台词属于当前 Pet；活动方式与范围共享，保存后对所有用户生效。'
        }}
      </span>
      <v-spacer />
      <v-btn
        variant="text"
        size="small"
        :disabled="props.disabled"
        title="只恢复活动参数，保留台词与偷看角度"
        @click="reset"
        >恢复默认</v-btn
      >
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
