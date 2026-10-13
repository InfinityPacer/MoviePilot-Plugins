<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { PluginApi } from '@/host'
import { DEFAULT_CALIBRATION, parseCalibration, type Calibration } from '@/sprites/calibration'
import { unwrap } from './api'

const props = defineProps<{
  modelValue: Calibration
  packId: string
  api: PluginApi | null
  pluginId: string
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [Calibration] }>()
const busy = ref(false)
const error = ref('')
let alive = true
onBeforeUnmount(() => {
  alive = false
})
const fields: Array<{ key: keyof Calibration; title: string; min: number; max: number }> = [
  { key: 'left', title: '左边界', min: 0, max: 90 },
  { key: 'right', title: '右边界', min: 10, max: 100 },
  { key: 'top', title: '上边界', min: 0, max: 90 },
  { key: 'bottom', title: '下边界', min: 10, max: 100 },
  { key: 'baseline', title: '脚底基线', min: 1, max: 100 },
  { key: 'offset_x', title: '水平偏移', min: -25, max: 25 },
  { key: 'offset_y', title: '垂直偏移', min: -25, max: 25 },
]
const disabled = computed(() => props.disabled || busy.value)
function update(key: keyof Calibration, percent: number) {
  try {
    const next = { ...props.modelValue, [key]: Number(percent) / 100 }
    if (key === 'bottom') next.baseline = Math.min(next.baseline, next.bottom)
    error.value = ''
    emit('update:modelValue', parseCalibration(next))
  } catch (reason) {
    error.value = (reason as Error).message
  }
}
async function suggest() {
  if (!props.api || busy.value) return
  const id = props.packId
  const instance = props.pluginId
  const baseline = JSON.stringify(props.modelValue)
  busy.value = true
  error.value = ''
  try {
    const response = await props.api.get(`plugin/${instance}/packs/calibration/suggest?key=${encodeURIComponent(id)}`)
    if (!alive || id !== props.packId || instance !== props.pluginId || baseline !== JSON.stringify(props.modelValue))
      return
    emit('update:modelValue', parseCalibration(unwrap(response)))
  } catch (reason) {
    if (alive && id === props.packId && instance === props.pluginId) error.value = (reason as Error).message
  } finally {
    if (alive) busy.value = false
  }
}
</script>

<template>
  <section class="ap-calibration">
    <div class="d-flex align-center ga-2 mb-2">
      <strong>显示校准</strong><v-spacer />
      <v-btn size="small" variant="text" :loading="busy" :disabled="disabled" @click="suggest">识别建议</v-btn>
      <v-btn
        size="small"
        variant="text"
        :disabled="disabled"
        @click="emit('update:modelValue', { ...DEFAULT_CALIBRATION })"
        >恢复默认</v-btn
      >
    </div>
    <p class="text-caption text-medium-emphasis">
      坐标为原图单格百分比，所有帧共用。虚线框为显示与拖拽范围，底线为站立线；原图保留，框外内容不显示。点击底部「保存调整」生效，「撤销」放弃草稿。
    </p>
    <div class="ap-calibration__fields">
      <v-text-field
        v-for="field in fields"
        :key="field.key"
        :label="field.title"
        :model-value="Math.round(modelValue[field.key] * 10000) / 100"
        type="number"
        suffix="%"
        :step="1"
        :min="field.min"
        :max="field.max"
        density="compact"
        variant="outlined"
        hide-details
        :disabled="disabled"
        @update:model-value="update(field.key, Number($event))"
      />
    </div>
    <v-alert v-if="error" type="warning" variant="tonal" density="compact" class="mt-2">{{ error }}</v-alert>
  </section>
</template>

<style scoped>
.ap-calibration {
  padding: 16px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.ap-calibration__fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(125px, 1fr));
  gap: 12px;
}
</style>
