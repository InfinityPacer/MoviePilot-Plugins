<script setup lang="ts">
import type { PluginConfigModel } from '../types'
import { topSwitchFields } from '../config/fields'
import FieldControl from './FieldControl.vue'
import RiskAlert from './RiskAlert.vue'

/**
 * 全局开关区的输入参数。
 */
interface GlobalControlsProps {
  /** 当前配置对象，字段控件会按 key 原地更新。 */
  model: PluginConfigModel
}

defineProps<GlobalControlsProps>()
</script>

<template>
  <div class="global-controls">
    <FieldControl
      v-for="field in topSwitchFields"
      :key="field.key"
      :field="field"
      :model="model"
    />
    <RiskAlert text="重置数据会清空待定、暂停、监控等任务数据；保存后执行并自动复位。" />
  </div>
</template>

<style scoped>
.global-controls {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.global-controls > .risk-alert {
  grid-column: 1 / -1;
}

@media (max-width: 900px) {
  .global-controls {
    grid-template-columns: 1fr;
  }
}
</style>
