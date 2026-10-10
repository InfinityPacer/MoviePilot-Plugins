import { readdirSync, readFileSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'
import { defineConfig, normalizePath, type Plugin } from 'vite'
import { configDefaults } from 'vitest/config'

const TEST_ROOT = normalizePath(fileURLToPath(new URL('../../../tests/v3/agentpets/frontend', import.meta.url)))
const REPOSITORY_ROOT = normalizePath(fileURLToPath(new URL('../../..', import.meta.url)))
const ASSET_DIR = fileURLToPath(new URL('./src/assets', import.meta.url))
/** 按原名复制进联邦产物的素材目录：小映逐帧图与内置素材包。 */
const STATIC_DIRS = ['ying', 'packs']

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

function listFiles(dir: string): string[] {
  return readdirSync(dir)
    .sort()
    .flatMap(name => {
      const path = `${dir}/${name}`
      return statSync(path).isDirectory() ? listFiles(path).map(child => `${name}/${child}`) : [name]
    })
}

/**
 * 小映逐帧图和内置素材包按原名复制到 `dist/assets/` 下。
 *
 * 宿主从插件静态文件接口加载联邦产物，组件按 `import.meta.url` 相对定位这些图片；
 * 后端声明的 `preview`、`avatar` 和读取的 `pack.json` 都依赖固定文件名，替换美术也不受构建哈希影响。
 */
function copyStaticAssets(): Plugin {
  return {
    name: 'copy-agent-pet-assets',
    generateBundle() {
      for (const dir of STATIC_DIRS) {
        for (const file of listFiles(`${ASSET_DIR}/${dir}`)) {
          if (!/\.(json|png|webp)$/.test(file)) continue
          this.emitFile({
            type: 'asset',
            fileName: `assets/${dir}/${file}`,
            source: readFileSync(`${ASSET_DIR}/${dir}/${file}`),
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
        name: 'AgentPets',
        filename: 'remoteEntry.js',
        exposes: {
          './AgentPet': './src/stage/AgentPet.vue',
          './AgentPetSprite': './src/sprites/AgentPetSprite.vue',
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
      copyStaticAssets(),
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
