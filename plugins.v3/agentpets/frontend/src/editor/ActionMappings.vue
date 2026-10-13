<script setup lang="ts">
import { computed } from 'vue'
import type { SpritePack } from '@/sprites/schema'
import { ACTION_LABELS, mappingRows, type ActionMappings } from '@/sprites/mappings'

const props = defineProps<{
  pack: SpritePack
  mode: 'stage' | 'renderer'
  modelValue: ActionMappings
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [ActionMappings]; preview: [string, string] }>()
const rows = computed(() => mappingRows(props.mode))
const groups = computed(() => [...new Set(rows.value.map(row => row.group))])
const animations = computed(() =>
  Object.keys(props.pack.actions).map(value => ({
    value,
    title: ACTION_LABELS[value] ? `${ACTION_LABELS[value]} · ${value}` : value,
  })),
)
function set(key: string, value: string | null) {
  const next = { ...props.modelValue }
  if (value) next[key] = value
  else delete next[key]
  emit('update:modelValue', next)
}
function defaultAction(action: string) {
  return props.pack.actions[action] ? action : 'idle'
}
</script>

<template>
  <section class="ap-mappings">
    <div class="ap-inline mb-2">
      <h2 class="ap-section-title mb-0">动作映射 · {{ pack.name }}</h2>
      <v-spacer />
      <v-btn
        size="small"
        variant="text"
        :disabled="disabled || !Object.keys(modelValue).length"
        @click="emit('update:modelValue', {})"
        >恢复全部默认</v-btn
      >
    </div>
    <p class="ap-muted">选择触发时播放的动画。留空使用原有映射，修改后可试播，点击底部「保存调整」保存。</p>
    <v-expansion-panels variant="accordion" multiple>
      <v-expansion-panel v-for="group in groups" :key="group" :title="group">
        <v-expansion-panel-text>
          <div v-for="row in rows.filter(item => item.group === group)" :key="row.key" class="ap-mappings__row">
            <v-select
              :model-value="modelValue[row.key] ?? null"
              :items="animations"
              :label="row.label"
              :placeholder="`默认：${ACTION_LABELS[defaultAction(row.action)] ?? defaultAction(row.action)}`"
              :hint="!pack.actions[row.action] && !modelValue[row.key] ? '素材没有专用动画，默认使用待机' : undefined"
              persistent-placeholder
              persistent-hint
              clearable
              density="compact"
              variant="outlined"
              :disabled="disabled"
              @update:model-value="set(row.key, $event)"
            />
            <v-btn
              icon="mdi-play-outline"
              :aria-label="`试播${row.label}`"
              variant="text"
              size="small"
              :disabled="disabled"
              @click="emit('preview', modelValue[row.key] ?? defaultAction(row.action), row.label)"
            />
          </div>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </section>
</template>

<style scoped>
.ap-mappings {
  padding: 16px;
  border-top: 1px solid rgba(var(--v-border-color), 0.12);
}
.ap-mappings__row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
}
.ap-mappings :deep(.v-expansion-panel) {
  background: transparent;
}
</style>
