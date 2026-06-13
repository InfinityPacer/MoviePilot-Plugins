<script setup lang="ts">
import type { PluginConfigModel } from '../types'
import { periodFields } from '../config/fields'
import FieldControl from './FieldControl.vue'
import SectionPanel from './SectionPanel.vue'

/**
 * 运行计划区的输入参数。
 */
interface RuntimePlanProps {
  /** 当前配置对象，周期字段会按 key 原地更新。 */
  model: PluginConfigModel
}

defineProps<RuntimePlanProps>()
</script>

<template>
  <SectionPanel title="运行计划" subtitle="这些周期控制插件定时检查频率，与具体业务策略分开配置。">
    <div class="runtime-plan">
      <FieldControl
        v-for="field in periodFields"
        :key="field.key"
        :field="field"
        :model="model"
      />
    </div>
  </SectionPanel>
</template>

<style scoped>
.runtime-plan {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

@media (max-width: 900px) {
  .runtime-plan {
    grid-template-columns: 1fr;
  }
}
</style>
