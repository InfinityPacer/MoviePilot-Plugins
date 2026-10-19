<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  LANDMARKS,
  calibrationPoint,
  moveCalibrationPoint,
  sameCalibration,
  suggestedLandmark,
  type Calibration,
  type Landmark,
} from '@/sprites/calibration'

const props = defineProps<{ modelValue: Calibration; disabled?: boolean; zoom?: number }>()
const emit = defineEmits<{ 'update:modelValue': [Calibration] }>()
const root = ref<HTMLElement | null>(null)
const error = ref('')
const labels: Record<Landmark, string> = { left_eye: '画面左眼', right_eye: '画面右眼', head_top: '头顶' }
const markers = computed(() =>
  LANDMARKS.map(key => ({
    key,
    label: labels[key],
    placed: !!calibrationPoint(props.modelValue, key),
    point: calibrationPoint(props.modelValue, key) ?? suggestedLandmark(props.modelValue, key),
  })),
)
let drag: { id: number; key: Landmark; original: Calibration; last: Calibration; target: HTMLButtonElement } | null =
  null

function place(key: Landmark, x: number, y: number) {
  if (props.disabled) return
  try {
    const next = moveCalibrationPoint(props.modelValue, key, { x, y })
    if (drag) drag.last = next
    emit('update:modelValue', next)
    error.value = ''
  } catch (reason) {
    error.value = (reason as Error).message
  }
}
function move(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.id) return
  const rect = root.value?.getBoundingClientRect()
  if (!rect?.width || !rect.height) return
  event.preventDefault()
  place(drag.key, (event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height)
}
function stop(rollback = false) {
  const current = drag
  drag = null
  window.removeEventListener('pointermove', move)
  window.removeEventListener('pointerup', finish)
  window.removeEventListener('pointercancel', cancel)
  window.removeEventListener('blur', blur)
  if (current?.target.hasPointerCapture?.(current.id)) current.target.releasePointerCapture(current.id)
  if (rollback && current && sameCalibration(props.modelValue, current.last))
    emit('update:modelValue', current.original)
}
function finish(event: PointerEvent) {
  if (drag?.id !== event.pointerId) return
  move(event)
  stop()
}
function cancel(event: PointerEvent) {
  if (drag?.id === event.pointerId) stop(true)
}
function blur() {
  stop()
}
function start(event: PointerEvent, key: Landmark) {
  if (props.disabled || event.button !== 0 || drag) return
  const target = event.currentTarget as HTMLButtonElement
  target.focus({ preventScroll: true })
  target.setPointerCapture?.(event.pointerId)
  drag = { id: event.pointerId, key, original: { ...props.modelValue }, last: props.modelValue, target }
  window.addEventListener('pointermove', move, { passive: false })
  window.addEventListener('pointerup', finish)
  window.addEventListener('pointercancel', cancel)
  window.addEventListener('blur', blur)
  move(event)
}
function keydown(event: KeyboardEvent, key: Landmark) {
  if (event.key === 'Escape') {
    stop(true)
    return
  }
  const directions: Record<string, [number, number]> = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1],
  }
  const direction = directions[event.key]
  if (!direction || props.disabled) return
  event.preventDefault()
  const point = calibrationPoint(props.modelValue, key) ?? suggestedLandmark(props.modelValue, key)
  const step = event.shiftKey ? 0.01 : 0.0025
  place(key, point.x + direction[0] * step, point.y + direction[1] * step)
}
watch(
  () => props.modelValue,
  value => {
    if (drag && !sameCalibration(value, drag.last)) stop()
  },
  { deep: true },
)
watch(
  () => props.disabled,
  value => {
    if (value) stop()
  },
)
onBeforeUnmount(() => stop())
</script>

<template>
  <div
    ref="root"
    class="ap-landmarks"
    role="group"
    aria-label="双眼与头顶拖拽校准"
    :style="{ '--marker-scale': 1 / (zoom || 1) }"
  >
    <span class="ap-landmarks__top" :style="{ top: `${markers[2].point.y * 100}%` }" aria-hidden="true" />
    <button
      v-for="marker in markers"
      :key="marker.key"
      type="button"
      class="ap-landmarks__point"
      :class="[`ap-landmarks__point--${marker.key}`, { 'ap-landmarks__point--pending': !marker.placed }]"
      :style="{ left: `${marker.point.x * 100}%`, top: `${marker.point.y * 100}%` }"
      :aria-label="`${marker.label}校准光圈${marker.placed ? '' : '（待标定）'}`"
      :disabled="disabled"
      :data-landmark="marker.key"
      :data-placed="marker.placed"
      @pointerdown.stop.prevent="start($event, marker.key)"
      @click.stop
      @keydown.stop="keydown($event, marker.key)"
    >
      <span>{{ marker.label }}</span>
    </button>
    <span v-if="error" role="status" class="ap-landmarks__error">{{ error }}</span>
  </div>
</template>

<style scoped>
.ap-landmarks {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.ap-landmarks__point {
  --marker-color: var(--v-theme-info);
  position: absolute;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 0;
  transform: translate(-50%, -50%) scale(var(--marker-scale));
  background: transparent;
  color: rgb(var(--marker-color));
  pointer-events: auto;
  touch-action: none;
  cursor: grab;
  user-select: none;
}
.ap-landmarks__point::before {
  content: '';
  position: absolute;
  inset: 8px;
  border: 2px solid currentColor;
  border-radius: 50%;
  box-shadow: 0 0 0 1px rgb(var(--v-theme-surface));
}
.ap-landmarks__point::after {
  content: '+';
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 16px;
}
.ap-landmarks__point--right_eye {
  --marker-color: var(--v-theme-warning);
}
.ap-landmarks__point--head_top {
  --marker-color: var(--v-theme-success);
}
.ap-landmarks__point--pending::before {
  border-style: dashed;
}
.ap-landmarks__point:focus-visible {
  outline: 2px solid currentColor;
  border-radius: 50%;
}
.ap-landmarks__point:active {
  cursor: grabbing;
}
.ap-landmarks__point:disabled {
  pointer-events: none;
  opacity: 0.5;
}
.ap-landmarks__point span {
  position: absolute;
  top: 38px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  font-size: 10px;
  text-shadow: 0 1px 2px rgb(var(--v-theme-surface));
}
.ap-landmarks__top {
  position: absolute;
  left: 0;
  right: 0;
  border-top: 1px dashed rgb(var(--v-theme-success));
  opacity: 0.65;
}
.ap-landmarks__error {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  font-size: 11px;
  color: rgb(var(--v-theme-error));
}
</style>
