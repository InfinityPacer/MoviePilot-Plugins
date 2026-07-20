import { fileURLToPath } from 'node:url'

import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'
import { defineConfig, normalizePath, type Plugin } from 'vite'
import { configDefaults } from 'vitest/config'

const TEST_ROOT = normalizePath(
  fileURLToPath(new URL('../../../tests/v2/subscribeassistantenhanced/frontend', import.meta.url)),
)
const REPOSITORY_ROOT = normalizePath(fileURLToPath(new URL('../../..', import.meta.url)))

const isTestMode = (mode: string): boolean => mode === 'test' || process.env.VITEST === 'true'

function cleanFederationAssets(): Plugin {
  return {
    name: 'clean-federation-assets',
    enforce: 'post',
    generateBundle(_options, bundle) {
      for (const fileName of Object.keys(bundle)) {
        // Federation 在 generate:false 移除 JS fallback 后仍可能残留抽取出的 CSS。
        if (fileName.startsWith('assets/__federation_shared_vuetify/')) {
          delete bundle[fileName]
        }
      }

      const remoteEntry = bundle['assets/remoteEntry.js']
      if (remoteEntry?.type === 'chunk') {
        // 规范化生成器空白，确保重复构建通过仓库检查。
        remoteEntry.code = remoteEntry.code
          .split('\n')
          .map(line => line.trimEnd())
          .join('\n')
      }
    },
  }
}

export default defineConfig(({ mode }) => {
  const plugins: Plugin[] = [vue()]
  if (!isTestMode(mode)) {
    plugins.push(
      federation({
        name: 'SubscribeAssistantEnhanced',
        filename: 'remoteEntry.js',
        exposes: {
          './Config': './src/components/Config.vue',
        },
        shared: {
          vue: {
            requiredVersion: false,
            generate: false,
          },
          vuetify: {
            requiredVersion: false,
            generate: false,
          },
          'vuetify/styles': {
            requiredVersion: false,
            generate: false,
          },
        },
      }),
      cleanFederationAssets(),
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
        'msw',
        'vitest',
        'vue',
        'vuetify',
      ],
    },
    build: {
      target: 'esnext',
      minify: false,
      cssCodeSplit: true,
      assetsInlineLimit(filePath) {
        // 联邦组件由宿主动态加载，品牌图需内联以免静态资源按宿主根路径解析。
        if (filePath.endsWith('sae-logo.png')) return true
        return undefined
      },
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: {
        input: 'src/main.ts',
      },
    },
    server: {
      fs: {
        allow: [REPOSITORY_ROOT],
      },
    },
    test: {
      clearMocks: true,
      environment: 'jsdom',
      environmentOptions: {
        jsdom: {
          pretendToBeVisual: true,
          url: 'http://localhost/',
        },
      },
      exclude: [...configDefaults.exclude, '**/.worktrees/**'],
      include: [`${TEST_ROOT}/src/**/__tests__/**/*.spec.ts`],
      restoreMocks: true,
      server: {
        deps: {
          inline: ['vuetify'],
        },
      },
      setupFiles: [`${TEST_ROOT}/setup.ts`],
      unstubGlobals: true,
      coverage: {
        include: [
          'src/components/Config.vue',
          'src/config/api.ts',
          'src/config/defaults.ts',
          'src/config/draft.ts',
          'src/config/fields.ts',
          'src/config/i18n.ts',
          'src/config/presentation.ts',
          'src/config/values.ts',
        ],
        provider: 'v8',
        reporter: ['text', 'json-summary', 'html'],
        reportsDirectory: '../../../coverage-reports/subscribeassistantenhanced-frontend',
        thresholds: {
          branches: 80,
          functions: 85,
          lines: 85,
          statements: 85,
          'src/components/Config.vue': {
            branches: 75,
            functions: 80,
            lines: 80,
            statements: 80,
          },
          'src/config/api.ts': {
            branches: 75,
            functions: 80,
            lines: 80,
            statements: 80,
          },
          'src/config/defaults.ts': {
            branches: 75,
            functions: 80,
            lines: 80,
            statements: 80,
          },
          'src/config/draft.ts': {
            branches: 75,
            functions: 80,
            lines: 80,
            statements: 80,
          },
          'src/config/fields.ts': {
            branches: 75,
            functions: 80,
            lines: 80,
            statements: 80,
          },
          'src/config/i18n.ts': {
            branches: 75,
            functions: 80,
            lines: 80,
            statements: 80,
          },
          'src/config/presentation.ts': {
            branches: 75,
            functions: 80,
            lines: 80,
            statements: 80,
          },
          'src/config/values.ts': {
            branches: 75,
            functions: 80,
            lines: 80,
            statements: 80,
          },
        },
      },
    },
  }
})
