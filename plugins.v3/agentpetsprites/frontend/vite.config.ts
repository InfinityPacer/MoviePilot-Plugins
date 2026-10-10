import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'
import { defineConfig, normalizePath, type Plugin } from 'vite'
import { configDefaults } from 'vitest/config'

const TEST_ROOT = normalizePath(fileURLToPath(new URL('../../../tests/v3/agentpetsprites/frontend', import.meta.url)))
const REPOSITORY_ROOT = normalizePath(fileURLToPath(new URL('../../..', import.meta.url)))
const PACK_DIR = fileURLToPath(new URL('./src/assets/packs', import.meta.url))

const isTestMode = (mode: string): boolean => mode === 'test' || process.env.VITEST === 'true'

function cleanFederationAssets(): Plugin {
  return {
    name: 'clean-federation-assets',
    enforce: 'post',
    generateBundle(_options, bundle) {
      for (const fileName of Object.keys(bundle)) {
        if (fileName.startsWith('assets/__federation_shared_vuetify/')) delete bundle[fileName]
      }
      const remoteEntry = bundle['assets/remoteEntry.js']
      if (remoteEntry?.type === 'chunk') {
        remoteEntry.code = remoteEntry.code
          .split('\n')
          .map(line => line.trimEnd())
          .join('\n')
      }
    },
  }
}

/**
 * 内置素材包按原名复制到 `dist/assets/packs/<id>/`。
 *
 * 宿主从插件静态文件接口加载联邦产物，组件按 `import.meta.url` 相对定位精灵图；
 * 后端声明的 `preview: packs/projector-cat/preview.png` 和读取的 `pack.json` 都依赖固定文件名。
 */
function copyPacks(): Plugin {
  return {
    name: 'copy-builtin-packs',
    generateBundle() {
      for (const pack of readdirSync(PACK_DIR).sort()) {
        for (const name of readdirSync(`${PACK_DIR}/${pack}`).sort()) {
          if (!/\.(json|png|webp)$/.test(name)) continue
          this.emitFile({
            type: 'asset',
            fileName: `assets/packs/${pack}/${name}`,
            source: readFileSync(`${PACK_DIR}/${pack}/${name}`),
          })
        }
      }
    },
  }
}

export default defineConfig(({ mode }) => {
  const plugins: Plugin[] = [vue()]
  if (!isTestMode(mode)) {
    plugins.push(
      federation({
        name: 'AgentPetSprites',
        filename: 'remoteEntry.js',
        exposes: {
          './AgentPet': './src/components/AgentPet.vue',
          './Config': './src/components/Config.vue',
          './Page': './src/components/Page.vue',
        },
        shared: {
          vue: { requiredVersion: false, generate: false },
          vuetify: { requiredVersion: false, generate: false },
          'vuetify/styles': { requiredVersion: false, generate: false },
        },
      }),
      cleanFederationAssets(),
      copyPacks(),
    )
  }

  return {
    plugins,
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        '@tests': TEST_ROOT,
      },
      dedupe: [
        '@testing-library/jest-dom',
        '@testing-library/user-event',
        '@testing-library/vue',
        'vitest',
        'vue',
        'vuetify',
      ],
    },
    build: {
      target: 'esnext',
      minify: false,
      cssCodeSplit: true,
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: { input: 'src/main.ts' },
    },
    server: { fs: { allow: [REPOSITORY_ROOT] } },
    test: {
      clearMocks: true,
      environment: 'jsdom',
      environmentOptions: { jsdom: { pretendToBeVisual: true, url: 'http://localhost/' } },
      exclude: [...configDefaults.exclude, '**/.worktrees/**'],
      include: [`${TEST_ROOT}/src/**/__tests__/**/*.spec.ts`],
      restoreMocks: true,
      server: { deps: { inline: ['vuetify'] } },
      setupFiles: [`${TEST_ROOT}/setup.ts`],
      unstubGlobals: true,
    },
  }
})
