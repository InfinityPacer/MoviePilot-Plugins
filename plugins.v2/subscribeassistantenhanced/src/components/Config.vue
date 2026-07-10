<script setup lang="ts">
import { reactive } from 'vue'

import { type PluginApi } from '../config/api'
import { configDefaults, type NumberConfigKey, type SaeConfig } from '../config/defaults'
import { fields } from '../config/fields'
import { normalizeFiniteNumber } from '../config/values'

const props = defineProps<{
  /** 宿主读取并传入的当前插件配置模型。 */
  initialConfig?: Partial<SaeConfig>
  /** 宿主注入的已认证插件 API 客户端。 */
  api?: PluginApi
}>()

const emit = defineEmits<{
  /** 请求宿主持久化完整配置对象。 */
  save: [SaeConfig]
  /** 请求宿主关闭配置界面。 */
  close: []
  /** 请求宿主切换插件详情/配置视图。 */
  switch: []
}>()

const draft = reactive<SaeConfig>({
  ...configDefaults,
  ...props.initialConfig,
  open_tracker_dialog: false,
})
const renderedFields = fields.filter(field => !field.legacyUiKey && !field.dialogOnly)

/** 数值字段只接受有限 number，避免动态输入污染完整保存 payload。 */
function updateNumber(key: NumberConfigKey, incoming: unknown): void {
  draft[key] = normalizeFiniteNumber(draft[key], incoming)
}

/** 保存完整配置，并确保旧版弹窗状态不会被持久化为开启。 */
function saveConfig(): void {
  emit('save', {
    ...configDefaults,
    ...draft,
    open_tracker_dialog: false,
  })
}
</script>

<template>
  <section class="sae-config-shell">
    <form @submit.prevent="saveConfig">
      <div class="sae-config-fields">
        <template v-for="field in renderedFields" :key="field.key">
          <VSwitch
            v-if="field.kind === 'switch'"
            v-model="draft[field.key]"
            :label="field.label"
            :hint="field.hint"
            :color="field.risk === 'danger' ? 'error' : field.risk === 'notice' ? 'warning' : undefined"
            persistent-hint
          />
          <VSelect
            v-else-if="field.kind === 'select'"
            v-model="draft[field.key]"
            :label="field.label"
            :hint="field.hint"
            :items="field.options"
            :color="field.risk === 'danger' ? 'error' : field.risk === 'notice' ? 'warning' : undefined"
            item-title="title"
            item-value="value"
            persistent-hint
          />
          <VSelect
            v-else-if="field.kind === 'multi-select'"
            v-model="draft[field.key]"
            :label="field.label"
            :hint="field.hint"
            :items="field.options"
            :color="field.risk === 'danger' ? 'error' : field.risk === 'notice' ? 'warning' : undefined"
            item-title="title"
            item-value="value"
            multiple
            chips
            persistent-hint
          />
          <VTextField
            v-else-if="field.kind === 'number'"
            :model-value="draft[field.key]"
            :label="field.label"
            :hint="field.hint"
            :color="field.risk === 'danger' ? 'error' : field.risk === 'notice' ? 'warning' : undefined"
            type="number"
            persistent-hint
            @update:model-value="updateNumber(field.key as NumberConfigKey, $event)"
          />
          <VTextField
            v-else-if="field.kind === 'text' || field.kind === 'cron'"
            v-model="draft[field.key]"
            :label="field.label"
            :hint="field.hint"
            :color="field.risk === 'danger' ? 'error' : field.risk === 'notice' ? 'warning' : undefined"
            persistent-hint
          />
          <VTextarea
            v-else-if="field.kind === 'textarea'"
            v-model="draft[field.key]"
            :label="field.label"
            :hint="field.hint"
            :color="field.risk === 'danger' ? 'error' : field.risk === 'notice' ? 'warning' : undefined"
            persistent-hint
          />
        </template>
      </div>

      <div class="sae-config-actions">
        <VBtn color="primary" type="submit">保存</VBtn>
      </div>
    </form>
  </section>
</template>

<style scoped>
.sae-config-shell {
  padding: 24px;
  color: rgb(var(--v-theme-on-surface));
}

.sae-config-fields {
  display: grid;
  gap: 16px;
}

.sae-config-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 24px;
}
</style>
