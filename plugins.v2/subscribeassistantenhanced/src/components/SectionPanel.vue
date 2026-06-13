<script setup lang="ts">
/**
 * 配置分区容器的输入参数。
 */
interface SectionPanelProps {
  /** 分区标题。 */
  title: string

  /** 分区辅助说明。 */
  subtitle?: string
}

defineProps<SectionPanelProps>()
</script>

<template>
  <section class="section-panel">
    <header class="section-header">
      <div class="text-subtitle-1 font-weight-medium">{{ title }}</div>
      <div v-if="subtitle" class="text-body-2 text-medium-emphasis">{{ subtitle }}</div>
    </header>
    <div class="section-content">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.section-panel {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 16px;
}

.section-header {
  display: grid;
  gap: 4px;
  margin-block-end: 16px;
}

.section-content {
  display: grid;
  gap: 16px;
}
</style>
