<script setup lang="ts">
/**
 * 配置页风险提示的输入参数。
 */
interface RiskAlertProps {
  /** Vuetify 提示类型。 */
  type: 'success' | 'info' | 'warning' | 'error'

  /** 提示正文。 */
  text: string
}

withDefaults(defineProps<RiskAlertProps>(), {
  type: 'warning',
})
</script>

<template>
  <VAlert
    class="risk-alert"
    :type="type"
    :text="text"
    variant="tonal"
    density="comfortable"
  />
</template>

<style scoped>
.risk-alert {
  border-radius: 8px;
}
</style>
