<script setup lang="ts">
import type { PluginConfigModel } from '../types'
import { fields } from '../config/fields'
import FieldControl from '../components/FieldControl.vue'
import RiskAlert from '../components/RiskAlert.vue'
import SectionPanel from '../components/SectionPanel.vue'

/**
 * 订阅洗版配置页的输入参数。
 */
interface BestVersionTabProps {
  /** 当前配置对象，洗版策略字段会按 key 原地更新。 */
  model: PluginConfigModel
}

defineProps<BestVersionTabProps>()
</script>

<template>
  <SectionPanel title="洗版范围" subtitle="洗版是否启用由洗版类型决定，关闭时不创建和巡检洗版订阅。">
    <FieldControl :field="fields.best_version_type" :model="model" />
  </SectionPanel>

  <SectionPanel title="时限与转换">
    <div class="tab-grid tab-grid--two">
      <FieldControl :field="fields.best_version_remaining_days" :model="model" />
      <FieldControl :field="fields.best_version_episode_to_full" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="存量回填">
    <div class="tab-grid tab-grid--two">
      <FieldControl :field="fields.best_version_backfill_enabled" :model="model" />
      <FieldControl :field="fields.backfill_best_version_now" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="整理记录清理">
    <FieldControl :field="fields.best_version_clear_history_type" :model="model" />
    <RiskAlert type="error" text="清理整理记录和文件属于破坏性能力，应先确认媒体库与下载器路径关系。" />
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
