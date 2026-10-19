<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { PluginApi } from '@/host'
import {
  DEFAULT_CALIBRATION,
  LANDMARKS,
  calibrationPoint,
  moveCalibrationPoint,
  suggestedLandmark,
  type Landmark,
  parseCalibration,
  type Calibration,
  type CalibrationNumberKey,
} from '@/sprites/calibration'
import { unwrap } from './api'

const props = defineProps<{
  modelValue: Calibration
  packId: string
  api: PluginApi | null
  pluginId: string
  disabled?: boolean
  codex?: boolean
  defaultValue?: Calibration
}>()
const emit = defineEmits<{ 'update:modelValue': [Calibration] }>()
const busy = ref(false)
const error = ref('')
let alive = true
onBeforeUnmount(() => {
  alive = false
})
const fields: Array<{ key: CalibrationNumberKey; title: string; min: number; max: number }> = [
  { key: 'left', title: '左边界', min: 0, max: 90 },
  { key: 'right', title: '右边界', min: 10, max: 100 },
  { key: 'top', title: '上边界', min: 0, max: 90 },
  { key: 'bottom', title: '下边界', min: 10, max: 100 },
  { key: 'baseline', title: '脚底基线', min: 1, max: 100 },
  { key: 'offset_x', title: '水平偏移', min: -25, max: 25 },
  { key: 'offset_y', title: '垂直偏移', min: -25, max: 25 },
]
const disabled = computed(() => props.disabled || busy.value)
const eyeEnabled = computed(() => props.modelValue.eye_x != null && props.modelValue.eye_y != null)
const eyeFields = [
  { key: 'eye_x', title: '双眼中心横坐标' },
  { key: 'eye_y', title: '眼线纵坐标' },
] as const
const landmarkLabels: Record<Landmark, string> = { left_eye: '画面左眼', right_eye: '画面右眼', head_top: '头顶' }
const landmarkFields = LANDMARKS.flatMap(point =>
  (['x', 'y'] as const).map(axis => ({
    point,
    axis,
    key: `${point}_${axis}` as const,
    title: `${landmarkLabels[point]}${axis === 'x' ? '横' : '纵'}坐标`,
  })),
)
const placed = computed(() => LANDMARKS.filter(key => calibrationPoint(props.modelValue, key)).length)
function updateLandmark(key: Landmark, axis: 'x' | 'y', percent: number) {
  try {
    const current = calibrationPoint(props.modelValue, key)
      ? props.modelValue
      : moveCalibrationPoint(props.modelValue, key, suggestedLandmark(props.modelValue, key))
    emit('update:modelValue', parseCalibration({ ...current, [`${key}_${axis}`]: percent / 100 }))
    error.value = ''
  } catch (reason) {
    error.value = (reason as Error).message
  }
}
function clearLandmarks() {
  emit(
    'update:modelValue',
    parseCalibration({ ...props.modelValue, ...Object.fromEntries(landmarkFields.map(field => [field.key, null])) }),
  )
}

function toggleEye(enabled: boolean) {
  const value = props.modelValue
  try {
    emit(
      'update:modelValue',
      parseCalibration({
        ...value,
        eye_x: enabled ? value.left + (value.right - value.left) * 0.5 - value.offset_x : null,
        eye_y: enabled
          ? value.top + (value.bottom - value.top) * 0.35 - value.bottom + value.baseline - value.offset_y
          : null,
      }),
    )
    error.value = ''
  } catch (reason) {
    error.value = (reason as Error).message
  }
}
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
    const suggested = parseCalibration(unwrap(response))
    emit(
      'update:modelValue',
      parseCalibration({
        ...suggested,
        eye_x: props.modelValue.eye_x,
        eye_y: props.modelValue.eye_y,
        ...Object.fromEntries(landmarkFields.map(field => [field.key, props.modelValue[field.key]])),
      }),
    )
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
      <v-btn v-if="!defaultValue" size="small" variant="text" :loading="busy" :disabled="disabled" @click="suggest"
        >识别建议</v-btn
      >
      <v-btn
        size="small"
        variant="text"
        :disabled="disabled"
        @click="emit('update:modelValue', { ...(defaultValue ?? DEFAULT_CALIBRATION) })"
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
    <v-switch
      v-if="!codex"
      class="mt-3"
      label="校准偷窥眼位"
      :model-value="eyeEnabled"
      :disabled="disabled"
      density="compact"
      hide-details
      @update:model-value="toggleEye(!!$event)"
    />
    <p v-if="!codex" class="text-caption text-medium-emphasis mb-2">
      标记正面偷窥首帧的双眼中点，再选择底边或下角侧边试览微调；倾斜后只露一只眼。未校准时先安全露头，不保证露眼精度。
    </p>
    <div v-if="eyeEnabled && !codex" class="ap-calibration__fields">
      <v-text-field
        v-for="field in eyeFields"
        :key="field.key"
        :label="field.title"
        :model-value="Math.round((modelValue[field.key] ?? 0) * 10000) / 100"
        type="number"
        suffix="%"
        :step="0.5"
        :min="0"
        :max="100"
        density="compact"
        variant="outlined"
        hide-details
        :disabled="disabled"
        @update:model-value="update(field.key, Number($event))"
      />
    </div>
    <template v-if="codex">
      <div class="d-flex align-center ga-2 mt-3">
        <strong>双眼与头顶 · {{ placed }}/3</strong><v-spacer />
        <v-btn size="small" variant="text" :disabled="disabled || !placed" @click="clearLandmarks">清除三点</v-btn>
      </div>
      <p class="text-caption text-medium-emphasis mb-2">
        在完整形象中拖动光圈到两只瞳孔中心和实际头顶；左右以画面为准。虚线圈仅为待标定位置，不会自动保存。
        双眼都标定后用于单眼偷看定位，头顶用于露头边界；未标定时仍沿用旧中点。方向键可微调，Esc 取消本次拖动。
      </p>
      <div class="ap-calibration__fields">
        <v-text-field
          v-for="field in landmarkFields"
          :key="field.key"
          :label="field.title"
          :model-value="modelValue[field.key] == null ? '' : Math.round(modelValue[field.key]! * 10000) / 100"
          type="number"
          suffix="%"
          :step="0.1"
          :min="0"
          :max="100"
          density="compact"
          variant="outlined"
          hide-details
          :disabled="disabled"
          @update:model-value="updateLandmark(field.point, field.axis, Number($event))"
        />
      </div>
    </template>
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
