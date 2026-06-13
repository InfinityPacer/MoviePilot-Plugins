<script setup lang="ts">
import { computed } from 'vue'
import type { ConfigValue, FieldMeta, PluginConfigModel } from '../types'

/**
 * 单个配置字段控件的输入参数。
 */
interface FieldControlProps {
  /** 字段元信息，决定控件类型、文案和选项。 */
  field: FieldMeta

  /** 当前配置对象，字段值按 key 读写。 */
  model: PluginConfigModel
}

const props = defineProps<FieldControlProps>()

/**
 * 当前字段值代理，保证所有控件通过同一入口读写配置对象。
 */
const fieldValue = computed({
  get() {
    return props.model[props.field.key]
  },
  set(value) {
    props.model[props.field.key] = value
  },
})

/**
 * 数值字段的值代理，保存前统一转换为 number 或 null。
 */
const numberValue = computed<ConfigValue | undefined>({
  get() {
    return props.model[props.field.key]
  },
  set(value) {
    if (value === '' || value === null || value === undefined) {
      props.model[props.field.key] = null
      return
    }

    const next = Number(value)
    props.model[props.field.key] = Number.isNaN(next) ? null : next
  },
})

/**
 * 多选字段的数组值代理，避免空值传入 VSelect multiple 时产生非数组状态。
 */
const multiValue = computed<string[]>({
  get() {
    const value = props.model[props.field.key]
    return Array.isArray(value) ? value.map(item => String(item)) : []
  },
  set(value) {
    props.model[props.field.key] = value
  },
})
</script>

<template>
  <VSwitch
    v-if="field.kind === 'switch'"
    v-model="fieldValue"
    class="field-control"
    color="primary"
    :label="field.label"
    :hint="field.hint"
    persistent-hint
  />

  <VSelect
    v-else-if="field.kind === 'multi-select'"
    v-model="multiValue"
    class="field-control"
    :items="field.options ?? []"
    :label="field.label"
    :hint="field.hint"
    item-title="title"
    item-value="value"
    multiple
    chips
    clearable
    persistent-hint
  />

  <VSelect
    v-else-if="field.kind === 'select'"
    v-model="fieldValue"
    class="field-control"
    :items="field.options ?? []"
    :label="field.label"
    :hint="field.hint"
    item-title="title"
    item-value="value"
    clearable
    persistent-hint
  />

  <VTextarea
    v-else-if="field.kind === 'textarea'"
    v-model="fieldValue"
    class="field-control"
    :label="field.label"
    :hint="field.hint"
    auto-grow
    rows="4"
    persistent-hint
  />

  <VTextField
    v-else-if="field.kind === 'number'"
    v-model="numberValue"
    class="field-control"
    type="number"
    :label="field.label"
    :hint="field.hint"
    persistent-hint
  />

  <VTextField
    v-else
    v-model="fieldValue"
    class="field-control"
    type="text"
    :label="field.label"
    :hint="field.hint"
    persistent-hint
  />
</template>

<style scoped>
.field-control {
  width: 100%;
}
</style>
