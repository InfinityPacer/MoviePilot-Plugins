import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

/**
 * 插件本地 Vue 配置页的联邦构建入口。
 *
 * 运行时由主程序按插件 ID 发现 dist/assets/remoteEntry.js，并加载暴露的 Config 组件。
 */
export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'SubscribeAssistantEnhanced',
      filename: 'remoteEntry.js',
      format: 'esm',
      exposes: {
        './Config': './src/Config.vue',
      },
      shared: {
        vue: {
          requiredVersion: false,
          generate: false,
        },
        vuetify: {
          singleton: true,
          requiredVersion: false,
          generate: false,
        },
        'vuetify/styles': {
          singleton: true,
          requiredVersion: false,
          generate: false,
        },
      },
    }),
  ],
  build: {
    target: 'esnext',
    minify: 'esbuild',
    cssCodeSplit: true,
    rollupOptions: {
      input: './src/Config.vue',
    },
  },
})
