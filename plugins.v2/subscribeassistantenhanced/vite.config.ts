import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

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
        remoteEntry.code = remoteEntry.code.replace(/[ \t]+$/gm, '')
      }
    },
  }
}

export default defineConfig({
  plugins: [
    vue(),
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
  ],
  build: {
    target: 'esnext',
    minify: false,
    cssCodeSplit: true,
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: 'src/main.ts',
    },
  },
})
