<script setup lang="ts">
import type { PluginConfigModel } from '../types'
import { fields } from '../config/fields'
import FieldControl from '../components/FieldControl.vue'
import RiskAlert from '../components/RiskAlert.vue'
import SectionPanel from '../components/SectionPanel.vue'

/**
 * 种子删除配置页的输入参数。
 */
interface DeleteTabProps {
  /** 当前配置对象，删除策略字段会按 key 原地更新。 */
  model: PluginConfigModel
}

defineProps<DeleteTabProps>()
</script>

<template>
  <SectionPanel title="删除入口" subtitle="分别控制下载超时、手动删除和 Tracker 响应三类触发来源。">
    <div class="tab-grid tab-grid--three">
      <FieldControl :field="fields.download_monitor_enabled" :model="model" />
      <FieldControl :field="fields.manual_delete_listen" :model="model" />
      <FieldControl :field="fields.tracker_response_listen" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="删除后动作" subtitle="删除后补搜与跳过删除指纹共同减少坏种重复命中。">
    <div class="tab-grid tab-grid--two">
      <FieldControl :field="fields.auto_search_when_delete" :model="model" />
      <FieldControl :field="fields.skip_deletion" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="下载进度观察窗口">
    <div class="tab-grid tab-grid--three">
      <FieldControl :field="fields.download_timeout_minutes" :model="model" />
      <FieldControl :field="fields.download_progress_threshold" :model="model" />
      <FieldControl :field="fields.download_retry_limit" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="记录与排除">
    <div class="tab-grid tab-grid--two">
      <FieldControl :field="fields.delete_record_retention_hours" :model="model" />
      <FieldControl :field="fields.delete_exclude_tags" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="Tracker 关键字">
    <div class="tab-grid tab-grid--two">
      <FieldControl :field="fields.open_tracker_dialog" :model="model" />
      <FieldControl :field="fields.default_tracker_response" :model="model" />
    </div>
    <RiskAlert text="命中 Tracker 关键字会触发自动删种，请仅填写明确代表无效种子的响应。" />
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
