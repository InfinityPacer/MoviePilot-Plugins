import js from '@eslint/js'
import sonarjs from 'eslint-plugin-sonarjs'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

const managedFiles = ['**/*.{js,mjs,cjs,jsx,ts,tsx,mts,cts}', '**/*.vue']
const browserFiles = [
  'plugins.v3/archivemanager/frontend/src/**/*.{js,mjs,cjs,jsx,ts,tsx,mts,cts,vue}',
  'tests/v3/archivemanager/frontend/**/*.{js,mjs,cjs,ts,mts,cts,vue}',
]
const nodeFiles = ['plugins.v3/archivemanager/frontend/*.config.{js,mjs,cjs,ts,mts,cts}']

const browserGlobalNames = new Set(Object.keys(globals.browser))
const nodeOnlyGlobalRestrictions = Object.keys(globals.node)
  .filter(name => !browserGlobalNames.has(name))
  .sort()
  .map(name => ({
    name,
    message: `'${name}' is only available in Node.js code.`,
  }))

const typescriptConfigs = tseslint.configs.recommended.map(config => ({
  ...config,
  files: ['**/*.{ts,tsx,mts,cts}', '**/*.vue'],
}))

const vueConfigs = pluginVue.configs['flat/essential'].map(config => ({
  ...config,
  files: ['**/*.vue'],
}))

export default defineConfig([
  globalIgnores(['**/node_modules/**', '**/dist/**', '**/coverage/**', '**/.worktrees/**', '**/*.d.ts']),
  { ...js.configs.recommended, files: managedFiles },
  ...typescriptConfigs,
  ...vueConfigs,
  {
    files: ['**/*.vue'],
    rules: {
      'vue/multi-word-component-names': 'off',
      'vue/valid-v-slot': ['error', { allowModifiers: true }],
    },
  },
  {
    files: managedFiles,
    languageOptions: {
      ecmaVersion: 'latest',
      parserOptions: { parser: tseslint.parser },
      sourceType: 'module',
    },
  },
  {
    files: browserFiles,
    languageOptions: { globals: globals.browser },
    rules: { 'no-restricted-globals': ['error', ...nodeOnlyGlobalRestrictions] },
  },
  { files: nodeFiles, languageOptions: { globals: globals.node }, rules: { 'no-restricted-globals': 'off' } },
  {
    files: managedFiles,
    plugins: { sonarjs },
    rules: {
      'sonarjs/array-callback-without-return': 'error',
      'sonarjs/no-all-duplicated-branches': 'error',
      'sonarjs/no-dead-store': 'error',
      'sonarjs/no-duplicated-branches': 'error',
      'sonarjs/no-hardcoded-passwords': 'error',
      'sonarjs/no-hardcoded-secrets': 'error',
      'sonarjs/no-identical-conditions': 'error',
      'sonarjs/no-identical-expressions': 'error',
      'sonarjs/no-ignored-exceptions': 'error',
      'sonarjs/no-unthrown-error': 'error',
      'sonarjs/no-use-of-empty-return-value': 'error',
      'sonarjs/reduce-initial-value': 'error',
      'sonarjs/slow-regex': 'error',
      'sonarjs/stateful-regex': 'error',
      'sonarjs/super-linear-regex': 'error',
    },
  },
  { files: managedFiles, rules: { 'no-debugger': 'error' } },
])
