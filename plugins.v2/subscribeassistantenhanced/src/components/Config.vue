<script setup lang="ts">
defineProps<{
  initialConfig?: Record<string, unknown>
  api?: unknown
}>()

defineEmits<{
  save: [Record<string, unknown>]
  close: []
  switch: []
}>()
</script>

<template>
  <section class="sae-config-shell">
    <VAlert type="info" variant="tonal">订阅助手（增强版）配置页正在加载。</VAlert>
  </section>
</template>

<style scoped>
.sae-config-shell {
  padding: 24px;
  color: rgb(var(--v-theme-on-surface));
}
</style>
