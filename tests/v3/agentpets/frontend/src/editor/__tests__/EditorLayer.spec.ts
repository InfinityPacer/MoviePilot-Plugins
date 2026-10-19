import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// Vitest strips CSS imports; read the real stylesheet for this layout check.
const editorCss = readFileSync(
  resolve(
    dirname(fileURLToPath(import.meta.url)),
    '../../../../../../../plugins.v3/agentpets/frontend/src/editor/ui.css',
  ),
  'utf8',
)

describe('editor interaction layer', () => {
  it('hides only the global pet while an editor is present and restores it after the last editor closes', () => {
    const style = document.createElement('style')
    style.textContent = editorCss
    const host = document.createElement('div')
    host.innerHTML = `
      <div class="agent-pet-ying" data-motion="idle"><button>Global pet</button></div>
      <div class="agent-pet-ying agent-pet-ying--contained"><button>Preview pet</button></div>
      <div class="unrelated-pet"><button>Other plugin</button></div>
    `
    document.head.append(style)
    document.body.append(host)
    const pet = host.querySelector<HTMLElement>('.agent-pet-ying')!
    const preview = host.querySelector<HTMLElement>('.agent-pet-ying--contained')!
    const other = host.querySelector<HTMLElement>('.unrelated-pet')!
    const page = document.createElement('section')
    const config = document.createElement('section')
    page.setAttribute('data-agentpets-editor', '')
    config.setAttribute('data-agentpets-editor', '')
    try {
      expect(getComputedStyle(pet).visibility).toBe('visible')
      host.append(page, config)
      expect(getComputedStyle(pet).visibility).toBe('hidden')
      expect(getComputedStyle(preview).visibility).toBe('visible')
      expect(getComputedStyle(other).visibility).toBe('visible')
      page.remove()
      expect(getComputedStyle(pet).visibility).toBe('hidden')
      config.remove()
      expect(getComputedStyle(pet).visibility).toBe('visible')
      expect(pet.dataset.motion).toBe('idle')
      expect(pet.querySelector('button')?.isConnected).toBe(true)
    } finally {
      host.remove()
      style.remove()
    }
  })
})
