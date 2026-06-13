<script setup lang="ts">
/**
 * 业务域导航项，描述一个配置域入口。
 */
export interface DomainItem {
  /** 业务域唯一键。 */
  key: string

  /** 导航展示标题。 */
  title: string

  /** Vuetify 图标名称。 */
  icon: string
}

/**
 * 业务域导航的输入参数。
 */
interface DomainNavProps {
  /** 可切换的业务域列表。 */
  items: DomainItem[]

  /** 当前选中的业务域键。 */
  modelValue: string
}

defineProps<DomainNavProps>()

const emit = defineEmits<{
  /** 更新当前选中的业务域。 */
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <VList class="domain-nav" density="comfortable" nav>
    <VListItem
      v-for="item in items"
      :key="item.key"
      :active="item.key === modelValue"
      :prepend-icon="item.icon"
      :title="item.title"
      color="primary"
      @click="emit('update:modelValue', item.key)"
    />
  </VList>
</template>

<style scoped>
.domain-nav {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
</style>
