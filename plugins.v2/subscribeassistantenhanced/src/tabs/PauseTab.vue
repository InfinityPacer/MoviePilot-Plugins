<script setup lang="ts">
import type { PluginConfigModel } from '../types'
import { fields } from '../config/fields'
import FieldControl from '../components/FieldControl.vue'
import RiskAlert from '../components/RiskAlert.vue'
import SectionPanel from '../components/SectionPanel.vue'

/**
 * 订阅暂停配置页的输入参数。
 */
interface PauseTabProps {
  /** 当前配置对象，暂停策略字段会按 key 原地更新。 */
  model: PluginConfigModel
}

defineProps<PauseTabProps>()
</script>

<template>
  <SectionPanel title="暂停入口" subtitle="控制新增订阅自动暂停，以及名单内用户新增订阅的暂停策略。">
    <div class="tab-grid tab-grid--two">
      <FieldControl :field="fields.pause_enhanced_enabled" :model="model" />
      <FieldControl :field="fields.auto_pause_users" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="开播前暂停">
    <div class="tab-grid tab-grid--three">
      <FieldControl :field="fields.movie_air_pause_days" :model="model" />
      <FieldControl :field="fields.tv_air_pause_days" :model="model" />
      <FieldControl :field="fields.airing_pause_days" :model="model" />
    </div>
  </SectionPanel>

  <SectionPanel title="无下载处理" subtitle="媒体上映后长时间没有下载时，按选择的策略调整订阅。">
    <div class="tab-grid tab-grid--three">
      <FieldControl :field="fields.movie_no_download_days" :model="model" />
      <FieldControl :field="fields.tv_no_download_days" :model="model" />
      <FieldControl :field="fields.no_download_actions" :model="model" />
    </div>
    <RiskAlert text="无下载处理中的删除订阅属于高风险策略，请只在确认不再需要该订阅时启用。" />
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
