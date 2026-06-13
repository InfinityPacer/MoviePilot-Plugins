<script setup lang="ts">
import type { PluginConfigModel } from '../types'
import { fields } from '../config/fields'
import FieldControl from '../components/FieldControl.vue'
import SectionPanel from '../components/SectionPanel.vue'

/**
 * 完结信号配置页的输入参数。
 */
interface CompletionSignalTabProps {
  /** 当前配置对象，完结守卫字段会按 key 原地更新。 */
  model: PluginConfigModel
}

defineProps<CompletionSignalTabProps>()
</script>

<template>
  <SectionPanel title="守卫策略总览" subtitle="选择完成前复核强度。平衡模式适合作为默认策略。">
    <FieldControl :field="fields.completion_guard_mode" :model="model" />
  </SectionPanel>

  <SectionPanel title="信号来源" subtitle="变更速率判断总集数稳定性；播出节奏用于估算等待期。">
    <div class="tab-grid tab-grid--three">
      <FieldControl :field="fields.volatility_enabled" :model="model" />
      <FieldControl :field="fields.cadence_enabled" :model="model" />
      <FieldControl :field="fields.season_cooldown_days" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="待定释放" subtitle="完成守卫待定不会无限保留；信号不稳定时重新计时。">
    <div class="tab-grid tab-grid--three">
      <FieldControl :field="fields.timeout_release_enabled" :model="model" />
      <FieldControl :field="fields.timeout_release_days" :model="model" />
      <FieldControl :field="fields.timeout_cadence_acceleration" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="完成后纠错" subtitle="完成后复查 TMDB 集数，检测到增集时自动重建订阅。">
    <div class="tab-grid tab-grid--three">
      <FieldControl :field="fields.verify_enabled" :model="model" />
      <FieldControl :field="fields.verify_interval_hours" :model="model" />
      <FieldControl :field="fields.verify_retention_days" :model="model" />
    </div>
  </SectionPanel>

  <VExpansionPanels variant="accordion">
    <VExpansionPanel title="高级信号参数">
      <VExpansionPanelText>
        <div class="tab-grid tab-grid--two">
          <FieldControl :field="fields.volatility_window_days" :model="model" />
          <FieldControl :field="fields.cadence_multiplier" :model="model" />
          <FieldControl :field="fields.cadence_min_window_days" :model="model" />
          <FieldControl :field="fields.cadence_min_episodes" :model="model" />
        </div>
      </VExpansionPanelText>
    </VExpansionPanel>
  </VExpansionPanels>
</template>

<style scoped>
.tab-grid {
  display: grid;
  gap: 16px;
}

.tab-grid--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.tab-grid--three {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

@media (max-width: 900px) {
  .tab-grid--two,
  .tab-grid--three {
    grid-template-columns: 1fr;
  }
}
</style>
