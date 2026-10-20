import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { Script } from 'node:vm'

import { describe, expect, it } from 'vitest'

const ASSETS_DIR = resolve('dist/assets')
const REMOTE_SOURCE = readFileSync(join(ASSETS_DIR, 'remoteEntry.js'), 'utf8')
const EXPOSES = ['AgentPet', 'AgentPetSprite', 'AgentPetCodex', 'Config', 'Page'] as const
const REMOTE_URLS = ['https://mp.test', 'http://localhost:3000', 'http://127.0.0.1:3000', 'http://[::1]:3000'].flatMap(
  origin =>
    ['', '/mp'].map(prefix => `${origin}${prefix}/api/v1/plugin/file/AgentPets/frontend/dist/assets/remoteEntry.js`),
)

function captureRemote(remoteUrl: string) {
  const imports: string[] = []
  const styles: string[] = []
  // Execute the built loader without fetching modules or opening a browser.
  const source = REMOTE_SOURCE.replaceAll('import.meta.url', JSON.stringify(remoteUrl))
    .replace(/\bimport\(name\)/g, '__captureImport(name)')
    .replace(/^export \{[^}]+\};?\s*$/m, '')
  const remote = new Script(`${source}\n({ get });`).runInNewContext({
    document: {
      createElement: () => ({ href: '', rel: '' }),
      head: { appendChild: (link: { href: string }) => styles.push(link.href) },
    },
    window: {},
    __captureImport: (specifier: string) => {
      imports.push(new URL(specifier, remoteUrl).href)
      return Promise.resolve({ default: {} })
    },
  }) as { get: (name: string) => Promise<() => unknown> }
  return { remote, imports, styles }
}

describe('built federation asset URLs', () => {
  it.each(REMOTE_URLS.flatMap(remoteUrl => EXPOSES.map(expose => ({ remoteUrl, expose }))))(
    '$expose resolves JS and CSS beside $remoteUrl',
    async ({ remoteUrl, expose }) => {
      const chunks = readdirSync(ASSETS_DIR).filter(
        name => name.startsWith(`__federation_expose_${expose}-`) && name.endsWith('.js'),
      )
      expect(chunks).toHaveLength(1)
      const cssCall = REMOTE_SOURCE.match(
        new RegExp(String.raw`dynamicLoadingCss\((\[[^\]]*\]), false, '\./${expose}'\)`),
      )
      expect(cssCall).not.toBeNull()
      const cssFiles = JSON.parse(cssCall![1]) as string[]
      expect(cssFiles.length).toBeGreaterThan(0)
      for (const name of cssFiles) expect(existsSync(join(ASSETS_DIR, name))).toBe(true)

      const { remote, imports, styles } = captureRemote(remoteUrl)
      expect(await remote.get(`./${expose}`)).toBeTypeOf('function')
      expect(styles).toEqual(cssFiles.map(name => new URL(name, remoteUrl).href))
      expect(imports).toEqual([new URL(chunks[0], remoteUrl).href])
    },
  )

  it.each(REMOTE_URLS)('resolves the built archive Worker beside %s', remoteUrl => {
    const chunks = readdirSync(ASSETS_DIR).filter(name => name.startsWith('Config.vue') && name.endsWith('.js'))
    expect(chunks).toHaveLength(1)
    const source = readFileSync(join(ASSETS_DIR, chunks[0]), 'utf8')
    const reference = source.match(/new URL\(['"]([^'"]*archive\.worker-[^'"]+\.js)['"], import\.meta\.url\)/)
    expect(reference).not.toBeNull()
    const workers = readdirSync(ASSETS_DIR).filter(name => /^archive\.worker-.+\.js$/.test(name))
    expect(workers).toHaveLength(1)
    expect(new URL(reference![1], new URL(chunks[0], remoteUrl)).href).toBe(new URL(workers[0], remoteUrl).href)
  })

  it('keeps generated chunk imports and CSS assets within the emitted bundle', () => {
    const remoteUrl = REMOTE_URLS[0]
    for (const file of readdirSync(ASSETS_DIR).filter(name => /\.(js|css)$/.test(name))) {
      const source = readFileSync(join(ASSETS_DIR, file), 'utf8')
      const pattern = file.endsWith('.js')
        ? /(?:\bfrom\s*|\bimport\s*\(\s*)['"]([^'"]+)['"]/g
        : /url\(\s*['"]?([^'"\s)]+)['"]?\s*\)/g
      for (const [, specifier] of source.matchAll(pattern)) {
        if (/^(data:|https?:|#)/.test(specifier)) continue
        expect(specifier, `${file}: ${specifier}`).not.toMatch(/^\//)
        const resolved = new URL(specifier, new URL(file, remoteUrl))
        const base = new URL('.', remoteUrl)
        expect(resolved.href.startsWith(base.href), `${file}: ${specifier}`).toBe(true)
        expect(existsSync(join(ASSETS_DIR, decodeURIComponent(resolved.pathname.slice(base.pathname.length))))).toBe(
          true,
        )
      }
    }
  })
})
