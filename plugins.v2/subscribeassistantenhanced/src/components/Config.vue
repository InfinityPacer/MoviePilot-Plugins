<script setup lang="ts">
defineProps<{
  /** 宿主读取并传入的当前插件配置模型。 */
  initialConfig?: Record<string, unknown>
  /** 宿主注入的已认证插件 API 客户端。 */
  api?: unknown
}>()

defineEmits<{
  /** 请求宿主持久化完整配置对象。 */
  save: [Record<string, unknown>]
  /** 请求宿主关闭配置界面。 */
  close: []
  /** 请求宿主切换插件详情/配置视图。 */
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
