import { fireEvent, render } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, ref } from 'vue'
import CalibrationMarkers from '@/editor/CalibrationMarkers.vue'
import { parseCalibration, type Calibration } from '@/sprites/calibration'

function pointer(type: string, x: number, y: number, id = 1) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX: x, clientY: y })
  Object.defineProperty(event, 'pointerId', { value: id })
  return event
}
function setup(zoom = 1) {
  const model = ref(
    parseCalibration({ left: 0.2, right: 0.8, top: 0.1, bottom: 0.9, baseline: 0.8, offset_x: 0.03, offset_y: -0.02 }),
  )
  const disabled = ref(false)
  const changed = vi.fn((value: Calibration) => {
    model.value = value
  })
  const wrapper = defineComponent({
    components: { CalibrationMarkers },
    setup: () => ({ model, changed, disabled, zoom }),
    template:
      '<CalibrationMarkers :model-value="model" :zoom="zoom" :disabled="disabled" @update:model-value="changed" />',
  })
  const view = render(wrapper)
  vi.spyOn(view.getByRole('group'), 'getBoundingClientRect').mockReturnValue({
    left: 100,
    top: 50,
    width: 200 * zoom,
    height: 400 * zoom,
  } as DOMRect)
  return { view, model, disabled, changed }
}

describe('draggable three-point calibration', () => {
  it('shows unplaced rings without changing the saved or draft calibration', () => {
    const { view, model, changed } = setup()
    expect(view.getAllByRole('button')).toHaveLength(3)
    expect(model.value.left_eye_x).toBeNull()
    expect(changed).not.toHaveBeenCalled()
  })
  it.each([1, 2])('uses the actual scaled viewport for mouse/touch positions at zoom %s', async zoom => {
    const { view, model } = setup(zoom)
    const left = view.getByRole('button', { name: /画面左眼校准光圈/ })
    left.dispatchEvent(pointer('pointerdown', 100 + 80 * zoom, 50 + 120 * zoom))
    await fireEvent.pointerMove(window, {})
    window.dispatchEvent(pointer('pointermove', 100 + 100 * zoom, 50 + 140 * zoom))
    await Promise.resolve()
    window.dispatchEvent(pointer('pointerup', 100 + 100 * zoom, 50 + 140 * zoom))
    expect(model.value.left_eye_x).toBeCloseTo(0.47)
    expect(model.value.left_eye_y).toBeCloseTo(0.3)
  })
  it('rolls back pointer cancellation and ignores other pointers', async () => {
    const { view, model } = setup()
    const before = { ...model.value }
    view.getByRole('button', { name: /画面左眼校准光圈/ }).dispatchEvent(pointer('pointerdown', 180, 170))
    await Promise.resolve()
    const moved = { ...model.value }
    window.dispatchEvent(pointer('pointermove', 250, 200, 2))
    expect(model.value).toEqual(moved)
    window.dispatchEvent(pointer('pointercancel', 180, 170))
    expect(model.value).toEqual(before)
  })
  it('cancels with Escape but never rolls back a newer externally supplied draft', async () => {
    const { view, model } = setup()
    const before = { ...model.value }
    const left = view.getByRole('button', { name: /画面左眼校准光圈/ })
    left.dispatchEvent(pointer('pointerdown', 180, 170))
    await Promise.resolve()
    await fireEvent.keyDown(left, { key: 'Escape' })
    expect(model.value).toEqual(before)
    left.dispatchEvent(pointer('pointerdown', 180, 170))
    await Promise.resolve()
    model.value = parseCalibration({ ...model.value, left_eye_x: 0.5 })
    await Promise.resolve()
    const external = { ...model.value }
    window.dispatchEvent(pointer('pointercancel', 180, 170))
    expect(model.value).toEqual(external)
  })
  it('supports keyboard fine tuning and stops a disabled or unmounted drag', async () => {
    const { view, model, disabled, changed } = setup()
    const top = view.getByRole('button', { name: /头顶校准光圈/ })
    await fireEvent.keyDown(top, { key: 'ArrowDown' })
    expect(model.value.head_top_x).not.toBeNull()
    top.dispatchEvent(pointer('pointerdown', 200, 100))
    disabled.value = true
    await Promise.resolve()
    const count = changed.mock.calls.length
    window.dispatchEvent(pointer('pointermove', 220, 120))
    expect(changed).toHaveBeenCalledTimes(count)
    view.unmount()
    window.dispatchEvent(pointer('pointerup', 240, 140))
    expect(changed).toHaveBeenCalledTimes(count)
  })
})
