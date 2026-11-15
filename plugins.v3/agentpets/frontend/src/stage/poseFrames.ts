import { ref, watch, type Ref } from 'vue'
import { frameUrl, POSES, type Pose } from './poses'

/** Failed frames keep the last good image and retry only when selected again. */
const FRAME_RETRY_AFTER = 5000
type FrameStatus = 'pending' | 'loaded' | 'error'

/**
 * Keeps every pose URL stable so the template can stack images and toggle visibility.
 * Only a failed frame's retry changes its URL; pose selection and layout belong to the caller.
 */
export function usePoseFrames(
  pose: Readonly<Ref<Pose>>,
  events: { aspectRatio: (ratio: number) => void; failed: (pose: Pose) => void },
) {
  const frameStatus = ref<Record<Pose, FrameStatus>>(
    Object.fromEntries(POSES.map(name => [name, 'pending'])) as Record<Pose, FrameStatus>,
  )
  const frameSrc = ref<Record<Pose, string>>(
    Object.fromEntries(POSES.map(name => [name, frameUrl(name)])) as Record<Pose, string>,
  )
  const displayed = ref<Pose | null>(null)
  const failedAt = new Map<Pose, number>()
  const retries = new Map<Pose, number>()

  function syncDisplayed() {
    const target = pose.value
    if (frameStatus.value[target] === 'loaded') {
      displayed.value = target
      return
    }
    const failed = failedAt.get(target)
    if (frameStatus.value[target] === 'error' && failed !== undefined && Date.now() - failed >= FRAME_RETRY_AFTER) {
      const attempt = (retries.get(target) ?? 0) + 1
      retries.set(target, attempt)
      failedAt.delete(target)
      frameStatus.value[target] = 'pending'
      frameSrc.value[target] = frameUrl(target) + '?retry=' + attempt
    }
    if (displayed.value && frameStatus.value[displayed.value] !== 'loaded') displayed.value = null
  }

  function onFrameLoad(name: Pose, event: Event) {
    frameStatus.value[name] = 'loaded'
    failedAt.delete(name)
    if (name === 'idle') {
      const image = event.target as HTMLImageElement
      if (image.naturalWidth && image.naturalHeight) events.aspectRatio(image.naturalWidth / image.naturalHeight)
    }
    if (name === pose.value) displayed.value = name
  }

  function onFrameError(name: Pose) {
    events.failed(name)
    frameStatus.value[name] = 'error'
    failedAt.set(name, Date.now())
    if (displayed.value === name) displayed.value = null
    syncDisplayed()
  }

  watch(pose, syncDisplayed)
  return { frameStatus, frameSrc, displayed, onFrameLoad, onFrameError }
}
