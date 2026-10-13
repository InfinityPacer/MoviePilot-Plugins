<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { AGENT_HOST_KEY, type MoviePilotAgentHost, type PluginApi } from '@/host'
import { framePosition } from './schema'
import { sameCalibration } from './calibration'
import { PACK_UPDATED_EVENT } from './mappings'
import { readPackArchive, type ArchiveTarget, type PackArchive } from './packArchive'

const props = defineProps<{ api: PluginApi | null; pluginId: string; targets: ArchiveTarget[] }>()
const emit = defineEmits<{ changed: []; busy: [value: boolean] }>()
const agent = inject<MoviePilotAgentHost | null>(AGENT_HOST_KEY, null)
const file = ref<File | null>(null)
const archive = ref<PackArchive | null>(null)
const target = ref<ArchiveTarget | null>(null)
const name = ref('')
const mode = ref<'new' | 'copy' | 'replace'>('new')
const error = ref('')
const message = ref('')
const busy = ref(false)
watch(busy, value => emit('busy', value))
let alive = true
let operation = 0
onBeforeUnmount(() => {
  alive = false
  operation++
})
watch(
  () => props.pluginId,
  () => {
    operation++
    busy.value = false
    archive.value = null
    target.value = null
    file.value = null
    error.value = ''
    message.value = ''
  },
)
const previewStyle = computed(() => {
  if (!archive.value) return {}
  const { pack, image } = archive.value
  const position = framePosition(pack, 'idle')
  return {
    backgroundImage: `url(${JSON.stringify(image)})`,
    backgroundSize: `${pack.grid.cols * 100}% ${pack.grid.rows * 100}%`,
    backgroundPosition: `${position.x}% ${position.y}%`,
  }
})
const duplicateName = computed(() =>
  props.targets.some(
    item => item.name === name.value.trim() && (mode.value !== 'replace' || item.id !== target.value?.id),
  ),
)
const stale = computed(
  () =>
    mode.value === 'replace' &&
    props.targets.find(item => item.id === target.value?.id)?.revision !== target.value?.revision,
)
const valid = computed(
  () =>
    !!archive.value &&
    !!name.value.trim() &&
    [...name.value.trim()].length <= 40 &&
    !busy.value &&
    !stale.value &&
    (mode.value !== 'replace' || (!!target.value?.revision && !target.value.builtin)),
)
const choices = computed(() =>
  target.value
    ? [
        { title: '导入副本（保留已有素材）', value: 'copy' },
        ...(!target.value.builtin ? [{ title: '更新同 ID 素材', value: 'replace' }] : []),
      ]
    : [{ title: '新增素材', value: 'new' }],
)
watch(mode, value => {
  if (value === 'replace' && archive.value) name.value = archive.value.pack.name
})

async function read(value?: File | File[] | null) {
  const nextFile = value === undefined ? file.value : Array.isArray(value) ? value[0] : value
  file.value = nextFile ?? null
  const version = ++operation
  const instance = props.pluginId
  archive.value = null
  error.value = ''
  message.value = ''
  if (!nextFile) {
    busy.value = false
    return
  }
  busy.value = true
  try {
    const result = await readPackArchive(nextFile)
    if (!alive || version !== operation || instance !== props.pluginId) return
    archive.value = result
    const match = props.targets.find(item => item.id === result.pack.id)
    target.value = match ? { ...match } : null
    mode.value = target.value ? 'copy' : 'new'
    name.value = props.targets.some(item => item.name === result.pack.name)
      ? result.pack.name.slice(0, 35) + '（副本）'
      : result.pack.name
  } catch (reason) {
    if (alive && version === operation) error.value = reason instanceof Error ? reason.message : '素材包读取失败'
  } finally {
    if (alive && version === operation) busy.value = false
  }
}

async function submit() {
  if (!valid.value || !props.api || !archive.value) return
  const instance = props.pluginId
  const version = ++operation
  const key = archive.value.pack.id
  const request = {
    pack: { ...archive.value.pack, name: name.value.trim() },
    image: archive.value.image,
    mode: mode.value,
    expected_revision: mode.value === 'replace' ? target.value?.revision : undefined,
  }
  busy.value = true
  error.value = ''
  try {
    const response = await props.api.post<ArchiveTarget>(`plugin/${instance}/packs/import`, request)
    if (!alive || version !== operation || instance !== props.pluginId) return
    if (!response?.success || !response.data?.id || (request.mode === 'replace' && response.data.id !== key))
      throw new Error(response?.message || '导入结果未确认，请刷新后核对')
    if (request.mode === 'replace') agent?.emit(PACK_UPDATED_EVENT, { key })
    message.value = `已${request.mode === 'replace' ? '更新' : '导入'} ${response.data.name}`
    archive.value = null
    emit('changed')
  } catch (reason) {
    if (alive && version === operation)
      error.value = reason instanceof Error ? reason.message : '导入失败，请刷新后核对'
  } finally {
    if (alive && version === operation) busy.value = false
  }
}
</script>

<template>
  <section class="ap-archive-import">
    <p class="ap-muted mb-3">选择从素材卡片导出的完整 ZIP，预览后可导入副本，或核对后更新同 ID 素材。</p>
    <v-file-input
      :model-value="file ? [file] : []"
      label="选择 AgentPets 导出 ZIP"
      accept=".zip"
      density="compact"
      variant="outlined"
      :disabled="busy"
      :loading="busy"
      prepend-icon=""
      prepend-inner-icon="mdi-package-up"
      @update:model-value="read"
    />
    <v-alert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</v-alert>
    <v-alert v-if="message" type="success" variant="tonal" density="compact">{{ message }}</v-alert>
    <template v-if="archive">
      <div class="d-flex align-center ga-3 mb-3">
        <v-avatar v-if="archive.pack.preview || archive.pack.avatar" size="64" rounded="lg">
          <v-img :src="archive.pack.preview || archive.pack.avatar" :alt="archive.pack.name" />
        </v-avatar>
        <div
          v-else
          class="ap-archive-import__preview"
          :style="previewStyle"
          role="img"
          :aria-label="archive.pack.name"
        />
        <div>
          <strong>{{ archive.pack.name }}</strong>
          <div class="text-caption">
            {{ archive.pack.grid.cols }} × {{ archive.pack.grid.rows }} 网格 ·
            {{ Object.keys(archive.pack.actions).length }} 项动作
          </div>
        </div>
      </div>
      <v-select
        v-model="mode"
        :items="choices"
        label="导入方式"
        density="compact"
        variant="outlined"
        :disabled="busy"
      />
      <v-text-field
        v-model="name"
        label="导入后的名称"
        counter="40"
        density="compact"
        variant="outlined"
        :disabled="busy"
      />
      <v-alert v-if="duplicateName" type="warning" variant="tonal" density="compact" class="mb-3"
        >已有同名素材，可修改名称区分；名称相同不会自动覆盖。</v-alert
      >
      <div v-if="mode === 'replace' && target" class="ap-archive-import__review">
        <table>
          <thead>
            <tr>
              <th>内容</th>
              <th>当前素材</th>
              <th>导入后</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>名称</td>
              <td>{{ target.name }}</td>
              <td>{{ name }}</td>
            </tr>
            <tr>
              <td>网格</td>
              <td>{{ target.grid?.cols }} × {{ target.grid?.rows }}</td>
              <td>{{ archive.pack.grid.cols }} × {{ archive.pack.grid.rows }}</td>
            </tr>
            <tr>
              <td>帧／动作数量</td>
              <td>{{ target.frame_count }}／{{ target.action_count }}</td>
              <td>{{ Object.keys(archive.pack.frames).length }}／{{ Object.keys(archive.pack.actions).length }}</td>
            </tr>
            <tr>
              <td>自定义映射数量</td>
              <td>{{ target.mapping_count ?? 0 }}</td>
              <td>{{ Object.keys(archive.pack.action_mappings ?? {}).length }}</td>
            </tr>
            <tr>
              <td>显示校准</td>
              <td>{{ target.calibrated ? '已调整' : '默认' }}</td>
              <td>{{ sameCalibration(archive.pack.calibration) ? '默认' : '已调整' }}</td>
            </tr>
          </tbody>
        </table>
        <p class="text-caption mt-2">
          将替换此 ID
          的名称、说明、图片、头像、预览、帧与动作、映射及校准；原记录与已上传原图会保留恢复副本。当前形象选择和个人位置保留。
        </p>
      </div>
      <v-alert v-if="stale" type="warning" variant="tonal" density="compact"
        >当前素材已变化，请重新读取并核对覆盖范围。</v-alert
      >
      <div class="d-flex justify-end ga-2 mt-3">
        <v-btn variant="text" :disabled="busy" @click="read()">重新读取</v-btn>
        <v-btn color="primary" variant="flat" :disabled="!valid" :loading="busy" @click="submit">{{
          mode === 'replace' ? '确认覆盖此素材' : '确认导入'
        }}</v-btn>
      </div>
    </template>
  </section>
</template>

<style scoped>
.ap-archive-import {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  padding: 16px;
}
.ap-archive-import__review {
  overflow-x: auto;
}
.ap-archive-import__preview {
  width: 64px;
  height: 64px;
  flex: 0 0 64px;
  background-repeat: no-repeat;
}
.ap-archive-import table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.ap-archive-import th,
.ap-archive-import td {
  padding: 6px;
  text-align: left;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  overflow-wrap: anywhere;
}
</style>
