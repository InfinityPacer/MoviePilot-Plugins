<script setup lang="ts">
defineProps<{
  /** 配置项的用户可见名称。 */
  label: string
  /** 说明该配置项作用与留空或关闭时的行为。 */
  hint: string
  /** 开关使用更紧凑的右侧控制区。 */
  switchField?: boolean
}>()
</script>

<template>
  <div class="archive-field-row" :class="{ 'archive-field-row--switch': switchField }">
    <div class="archive-field-row__copy">
      <div class="archive-field-row__label">{{ label }}</div>
      <p>{{ hint }}</p>
    </div>
    <div class="archive-field-row__control">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.archive-field-row {
  display: grid;
  align-items: center;
  min-inline-size: 0;
  padding: 11px 0;
  border-block-end: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  gap: 18px;
  grid-template-columns: minmax(200px, 1.45fr) minmax(180px, 0.75fr);
}
.archive-field-row:last-child {
  border-block-end: 0;
}
.archive-field-row__copy,
.archive-field-row__control {
  min-inline-size: 0;
}
.archive-field-row__label {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.15rem;
}
.archive-field-row__copy p {
  margin: 3px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 0.7rem;
  line-height: 1.1rem;
}
.archive-field-row--switch .archive-field-row__control {
  display: flex;
  justify-content: flex-end;
}

@container (width < 620px) {
  .archive-field-row {
    align-items: stretch;
    gap: 8px;
    grid-template-columns: 1fr;
  }
  .archive-field-row--switch {
    align-items: center;
    grid-template-columns: minmax(0, 1fr) auto;
  }
}
</style>
