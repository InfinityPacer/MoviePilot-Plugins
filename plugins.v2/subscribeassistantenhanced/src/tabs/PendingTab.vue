<script setup lang="ts">
import type { PluginConfigModel } from '../types'
import { fields } from '../config/fields'
import FieldControl from '../components/FieldControl.vue'
import SectionPanel from '../components/SectionPanel.vue'

/**
 * 订阅待定配置页的输入参数。
 */
interface PendingTabProps {
  /** 当前配置对象，待定策略字段会按 key 原地更新。 */
  model: PluginConfigModel
}

defineProps<PendingTabProps>()
</script>

<template>
  <SectionPanel title="待定入口" subtitle="下载未完成或剧集仍处于播出早期时，避免订阅提前完成。">
    <div class="tab-grid tab-grid--two">
      <FieldControl :field="fields.pending_download_enabled" :model="model" />
      <FieldControl :field="fields.pending_enhanced_enabled" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="播出待定阈值" subtitle="天数和集数任一规则命中时可进入待定；0 表示对应规则不参与。">
    <div class="tab-grid tab-grid--two">
      <FieldControl :field="fields.auto_tv_pending_days" :model="model" />
      <FieldControl :field="fields.auto_tv_pending_episodes" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="信号辅助">
    <FieldControl :field="fields.pending_use_volatility" :model="model" />
  </SectionPanel>
</template>

<style scoped>
.tab-grid {
  display: grid;
  gap: 16px;
}

.tab-grid--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 900px) {
  .tab-grid--two {
    grid-template-columns: 1fr;
  }
}
</style>
