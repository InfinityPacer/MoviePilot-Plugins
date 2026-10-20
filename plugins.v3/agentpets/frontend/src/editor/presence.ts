import { onBeforeUnmount, onMounted } from 'vue'

const editors = new Set<symbol>()
const listeners = new Set<(active: boolean) => void>()

export function registerEditor(): () => void {
  const token = Symbol()
  editors.add(token)
  if (editors.size === 1) for (const listener of listeners) listener(true)
  return () => {
    if (editors.delete(token) && !editors.size) for (const listener of listeners) listener(false)
  }
}

export function useEditorPresence() {
  let release: (() => void) | undefined
  onMounted(() => {
    release = registerEditor()
  })
  onBeforeUnmount(() => release?.())
}

export function onEditorPresence(listener: (active: boolean) => void): () => void {
  listeners.add(listener)
  listener(editors.size > 0)
  return () => {
    listeners.delete(listener)
  }
}
