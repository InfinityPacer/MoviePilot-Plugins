<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { AGENT_HOST_KEY, type MoviePilotAgentHost, type PluginApi } from '@/host'
import { PACK_UPDATED_EVENT } from '@/sprites/mappings'
import PackArchiveImport from './PackArchiveImport.vue'
import { exportPackArchive } from './packArchive'
import { builtinAvatar } from '@/editor/avatars'
import { extractCodexPetArchive, isCodexPetArchive, MAX_CODEX_PET_ARCHIVE_BYTES } from '@/sprites/codexPetArchive'
import { buildCodexPetPack, validatePack, type CodexPetMetadata } from '@/sprites/schema'

/** 素材包列表项，与后端 `_summary` 一致。 */
interface PackSummary {
  id: string
  name: string
  description: string
  /** 是否为内置素材包（不可删除）。 */
  builtin: boolean
  /** builtin、upload 或 url。 */
  source: string
  mode?: 'stage' | 'renderer'
  /** 预览图：内置为相对联邦产物目录的路径，其余为 data/http URL，可能为空。 */
  preview: string
  grid: { cols: number; rows: number } | null
  frame_count: number
  action_count: number
  revision?: string
  mapping_count?: number
  calibrated?: boolean
}

type HostToast = Partial<Record<'success' | 'error' | 'warning' | 'info', (message: string) => unknown>>
type HostConfirm = (options?: {
  type?: 'info' | 'warn' | 'error'
  title?: string
  content?: string
}) => Promise<boolean>

const props = withDefaults(
  defineProps<{
    api?: PluginApi | null
    pluginId?: string
  }>(),
  { api: null, pluginId: '' },
)

const emit = defineEmits<{ changed: [] }>()
const importMode = ref<'codex' | 'archive' | 'custom'>('codex')
const archiveBusy = ref(false)
let previousInputMode: 'codex' | 'custom' = 'codex'
const listError = ref('')
const deleting = ref('')
const exporting = ref('')
const renameTarget = ref<PackSummary | null>(null)
const renameName = ref('')
const renameError = ref('')
const renaming = ref(false)
const agent = inject<MoviePilotAgentHost | null>(AGENT_HOST_KEY, null)
const renameValid = computed(() => !!renameName.value.trim() && [...renameName.value.trim()].length <= 40)
let alive = true
let listVersion = 0
let instanceVersion = 0
onBeforeUnmount(() => {
  alive = false
  instanceVersion++
  listVersion++
})

const MAX_IMAGE_BYTES = 4 * 1024 * 1024
const IMAGE_TYPES = ['image/png', 'image/webp', 'image/gif', 'image/jpeg']
const EXAMPLE = JSON.stringify(
  {
    id: 'my-pet',
    name: '我的形象',
    sheet: 'https://example.com/sheet.png',
    grid: { cols: 4, rows: 2 },
    frames: { idle: 0, blink: 1, talk: 2, think: 3 },
    actions: {
      idle: { frames: ['idle', 'idle', 'blink'], frame_ms: 600, loop: true },
      thinking: { frames: ['think'], loop: true },
      speaking: ['talk', 'idle'],
    },
    random_actions: ['wave'],
  },
  null,
  2,
)

const toast = inject<HostToast | null>('moviepilot:toast', null)
const confirm = inject<HostConfirm | null>('moviepilot:confirm', null)
const instanceId = computed(() => props.pluginId || 'AgentPets')
const packs = ref<PackSummary[]>([])
const loading = ref(false)
const submitting = ref(false)
const codexImporting = ref(false)
const packText = ref('')
const imageMode = ref<'upload' | 'url'>('upload')
watch(importMode, value => {
  if (value === 'archive') return
  if (value === 'codex' && previousInputMode !== 'codex') {
    imageMode.value = 'upload'
    parsedCodexFile.value = null
    packText.value = ''
    importMessage.value = ''
  }
  previousInputMode = value
})
const selectedFile = ref<File | null>(null)
const parsedCodexFile = ref<File | null>(null)
const imageFile = ref<File | null>(null)
const fileModel = ref<File[]>([])
const imageError = ref('')
const importMessage = ref('')
const importError = ref('')
const serverError = ref('')

const validation = computed(() => (packText.value.trim() ? validatePack(packText.value) : null))
const clientErrors = computed(() => {
  const errors = [...(validation.value?.errors ?? [])]
  if (imageMode.value === 'url' && validation.value?.pack && !/^https?:\/\/\S+$/.test(validation.value.pack.sheet)) {
    errors.push('填写 URL 方式时，JSON 的 sheet 必须是 http(s) 图片地址')
  }
  return errors
})
const canSubmit = computed(
  () =>
    importMode.value !== 'archive' &&
    !!validation.value?.pack &&
    !clientErrors.value.length &&
    !submitting.value &&
    (importMode.value !== 'codex' || (!!selectedFile.value && parsedCodexFile.value === selectedFile.value)) &&
    (imageMode.value === 'url' || (!!imageFile.value && !imageError.value)),
)

function captureScope() {
  const version = instanceVersion
  return { api: props.api, id: instanceId.value, current: () => alive && version === instanceVersion }
}

function previewSrc(pack: PackSummary): string {
  if (pack.builtin) return builtinAvatar(pack.id)
  return pack.preview
}

function notify(kind: 'success' | 'error', message: string) {
  toast?.[kind]?.(message)
}

async function refresh() {
  if (!props.api?.get) {
    listError.value = '页面连接尚未就绪'
    return
  }
  const version = ++listVersion
  loading.value = true
  listError.value = ''
  try {
    const response = await props.api.get<PackSummary[]>(`plugin/${instanceId.value}/packs`)
    if (!alive || version !== listVersion) return
    if (!response?.success || !Array.isArray(response.data)) throw new Error('invalid packs')
    packs.value = response.data
  } catch {
    if (alive && version === listVersion) listError.value = '素材列表读取失败，请刷新重试'
  } finally {
    if (alive && version === listVersion) loading.value = false
  }
}

function onImage(value: File | File[] | null | undefined) {
  const file = Array.isArray(value) ? (value[0] ?? null) : (value ?? null)
  selectedFile.value = file
  parsedCodexFile.value = null
  if (importMode.value === 'codex') packText.value = ''
  imageFile.value = file
  imageError.value = ''
  importMessage.value = ''
  importError.value = ''
  serverError.value = ''
  if (!file) return
  if (isCodexPetArchive(file)) {
    imageFile.value = null
    if (file.size > MAX_CODEX_PET_ARCHIVE_BYTES) imageError.value = 'Codex Pet 压缩包不能超过 8MB'
    return
  }
  if (!IMAGE_TYPES.includes(file.type)) {
    imageFile.value = null
    imageError.value = '只支持 PNG、WebP、GIF、JPEG 或 ZIP'
  } else if (file.size > MAX_IMAGE_BYTES) {
    imageFile.value = null
    imageError.value = '精灵图不能超过 4MB'
  }
}

async function importCodexPet() {
  const file = selectedFile.value
  if (!file || imageError.value || codexImporting.value) return
  const { current } = captureScope()
  codexImporting.value = true
  parsedCodexFile.value = null
  if (importMode.value === 'codex') packText.value = ''
  imageError.value = ''
  importMessage.value = ''
  importError.value = ''
  try {
    let image = file
    let metadata: CodexPetMetadata | undefined
    if (isCodexPetArchive(file)) {
      const extracted = await extractCodexPetArchive(file)
      image = extracted.spritesheet
      metadata = extracted.manifest
    } else if (file.type !== 'image/png' && file.type !== 'image/webp') {
      throw new Error('Codex Pet 导入只支持 PNG 或 WebP')
    }
    if (!current()) return
    const bitmap = await createImageBitmap(image)
    const { width, height } = bitmap
    bitmap.close()
    if (!current()) return
    const result = buildCodexPetPack(image.name, width, height, metadata)
    imageMode.value = 'upload'
    imageFile.value = image
    packText.value = JSON.stringify(result.pack, null, 2)
    parsedCodexFile.value = file
    serverError.value = ''
    importMessage.value =
      (metadata ? '已从 Codex Pet 包读取精灵图，' : '已识别 Codex Pet ') + result.version + '，动作映射已生成'
  } catch (error) {
    if (!current()) return
    importError.value = error instanceof Error ? error.message : '无法读取 Codex Pet 精灵图'
  } finally {
    if (current()) codexImporting.value = false
  }
}

function readDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

async function addPack() {
  if (!canSubmit.value || !props.api?.post) return
  const { api, id, current } = captureScope()
  const pack = packText.value
  const file = imageMode.value === 'upload' ? imageFile.value : null
  submitting.value = true
  serverError.value = ''
  try {
    const image = file ? await readDataUrl(file) : null
    if (!current()) return
    const response = await api!.post<PackSummary>(`plugin/${id}/packs`, {
      pack,
      image,
    })
    if (!current()) return
    if (!response?.success) {
      serverError.value = response?.message || '添加失败'
      return
    }
    notify('success', `已添加 Pet ${response.data?.name ?? ''}`)
    emit('changed')
    packText.value = ''
    selectedFile.value = null
    parsedCodexFile.value = null
    imageFile.value = null
    fileModel.value = []
    importMessage.value = ''
    importError.value = ''
    await refresh()
  } catch {
    if (current()) serverError.value = '添加失败，请检查网络或稍后重试'
  } finally {
    if (current()) submitting.value = false
  }
}

async function removePack(pack: PackSummary) {
  if (!props.api?.post) return
  const { api, id, current } = captureScope()
  const accepted = confirm
    ? await confirm({
        type: 'warn',
        title: '删除素材包',
        content: `删除「${pack.name}」后，选择它的用户会回到内置机器人。`,
      })
    : window.confirm(`删除素材包「${pack.name}」？`)
  if (!accepted || !current()) return
  deleting.value = pack.id
  listError.value = ''
  try {
    const response = await api!.post(`plugin/${id}/packs/delete`, { id: pack.id })
    if (!current()) return
    if (response?.success) {
      notify('success', `已删除素材包 ${pack.name}`)
      emit('changed')
      await refresh()
    } else listError.value = response?.message || '删除失败'
  } catch {
    if (current()) listError.value = '删除未完成，请刷新核对后重试'
  } finally {
    if (current()) deleting.value = ''
  }
}

async function exportPack(pack: PackSummary) {
  if (!props.api || exporting.value) return
  const { api, id, current } = captureScope()
  exporting.value = pack.id
  listError.value = ''
  try {
    const blob = await exportPackArchive(api!, id, pack.id)
    if (!current()) return
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${pack.id}.agentpets.zip`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (reason) {
    if (current()) listError.value = `未生成完整素材包：${reason instanceof Error ? reason.message : '图片读取失败'}`
  } finally {
    if (current()) exporting.value = ''
  }
}
function archiveImported() {
  emit('changed')
  void refresh()
}

function startRename(pack: PackSummary) {
  renameTarget.value = pack
  renameName.value = pack.name
  renameError.value = ''
}
async function renamePack() {
  if (renaming.value || !renameValid.value || !props.api || !renameTarget.value) return
  const target = renameTarget.value
  const { api, id, current } = captureScope()
  const name = renameName.value.trim()
  renaming.value = true
  renameError.value = ''
  try {
    const response = await api!.post<PackSummary>(`plugin/${id}/packs/rename`, {
      id: target.id,
      name,
      expected_name: target.name,
    })
    if (!current()) return
    if (!response?.success || response.data?.id !== target.id || response.data?.name !== name) {
      renameError.value = response?.message || '重命名未确认，请刷新后核对'
      return
    }
    packs.value = packs.value.map(pack => (pack.id === target.id ? response.data! : pack))
    renameTarget.value = null
    agent?.emit?.(PACK_UPDATED_EVENT, { key: target.id })
    emit('changed')
  } catch {
    if (current()) renameError.value = '重命名未完成，请刷新核对后重试'
  } finally {
    if (current()) renaming.value = false
  }
}
watch(instanceId, () => {
  instanceVersion++
  listVersion++
  packs.value = []
  submitting.value = false
  codexImporting.value = false
  archiveBusy.value = false
  deleting.value = ''
  packText.value = ''
  selectedFile.value = null
  parsedCodexFile.value = null
  imageFile.value = null
  fileModel.value = []
  imageError.value = ''
  importMessage.value = ''
  importError.value = ''
  serverError.value = ''
  previousInputMode = 'codex'
  importMode.value = 'codex'
  imageMode.value = 'upload'
  exporting.value = ''
  renameTarget.value = null
  renaming.value = false
  void refresh()
})
onMounted(refresh)
defineExpose({ refresh })
</script>

<template>
  <div class="agent-pet-sprites-config">
    <div class="ap-inline mb-2">
      <h3 class="ap-section-title mb-0">我的素材</h3>
      <v-spacer /><v-btn
        icon="mdi-refresh"
        aria-label="刷新素材列表"
        variant="text"
        size="small"
        :loading="loading"
        @click="refresh"
      />
    </div>
    <v-alert v-if="listError" type="error" variant="tonal" density="compact" class="mb-3">{{ listError }}</v-alert>
    <v-progress-linear v-if="loading" indeterminate color="primary" />
    <div class="agent-pet-sprites-config__list mb-6" role="list" aria-label="已有 Pet 素材">
      <article v-for="pack in packs" :key="pack.id" class="agent-pet-sprites-config__card" role="listitem">
        <v-avatar rounded="lg" size="52" class="agent-pet-sprites-config__thumb">
          <v-img v-if="previewSrc(pack)" :src="previewSrc(pack)" :alt="pack.name" />
          <v-icon v-else icon="mdi-image-outline" />
        </v-avatar>
        <div class="agent-pet-sprites-config__info">
          <div class="agent-pet-sprites-config__name" :title="pack.name">{{ pack.name }}</div>
          <div class="agent-pet-sprites-config__meta">
            <span>{{ pack.builtin ? '内置素材' : '已导入' }}</span>
            <span>{{ pack.mode === 'stage' ? '自由活动' : '入口形象' }}</span>
            <span>{{ pack.action_count }} 项动作定义</span>
          </div>
        </div>
        <div class="agent-pet-sprites-config__actions">
          <v-chip v-if="pack.builtin" size="x-small" variant="tonal">内置</v-chip>
          <v-btn
            v-if="!pack.builtin"
            icon="mdi-download-outline"
            variant="text"
            size="small"
            :aria-label="`导出 ${pack.name}`"
            :loading="exporting === pack.id"
            :disabled="!!exporting || !!deleting || submitting || renaming"
            @click="exportPack(pack)"
          />
          <v-btn
            v-if="!pack.builtin && pack.mode === 'stage'"
            icon="mdi-pencil-outline"
            variant="text"
            size="small"
            :aria-label="`重命名 ${pack.name}`"
            :disabled="!!deleting || submitting || renaming"
            @click="startRename(pack)"
          />
          <v-btn
            v-if="!pack.builtin"
            icon="mdi-delete-outline"
            variant="text"
            size="small"
            :aria-label="`删除 ${pack.name}`"
            :loading="deleting === pack.id"
            :disabled="!!deleting || submitting || renaming"
            @click="removePack(pack)"
          />
        </div>
      </article>
      <p v-if="!packs.length && !loading && !listError" class="agent-pet-sprites-config__empty ap-muted">
        暂无素材，导入一个 Pet 开始吧
      </p>
    </div>
    <v-dialog
      :model-value="!!renameTarget"
      max-width="420"
      :persistent="renaming"
      @update:model-value="!$event && !renaming && (renameTarget = null)"
    >
      <v-card title="重命名 Pet">
        <v-card-text>
          <v-text-field
            v-model="renameName"
            label="显示名称"
            density="compact"
            variant="outlined"
            counter="40"
            :disabled="renaming"
            :error-messages="renameError || (!renameValid ? '请输入 1～40 个字符的名称' : '')"
            @keydown.enter.prevent="renamePack"
          />
          <p class="ap-muted mb-0">只修改名称，当前选择、动作映射和位置保持不变。</p>
        </v-card-text>
        <v-card-actions
          ><v-spacer /><v-btn variant="text" :disabled="renaming" @click="renameTarget = null">取消</v-btn>
          <v-btn
            variant="flat"
            color="primary"
            :disabled="!renameValid || renameName.trim() === renameTarget?.name"
            :loading="renaming"
            @click="renamePack"
            >保存名称</v-btn
          >
        </v-card-actions>
      </v-card>
    </v-dialog>
    <div class="agent-pet-sprites-config__import">
      <div class="ap-section-heading">
        <v-icon icon="mdi-package-down" color="primary" />
        <div>
          <h2>导入 Pet</h2>
          <p>支持 Codex Pet、AgentPets 导出包和自定义精灵图，读取并核对后再导入。</p>
        </div>
      </div>
      <v-btn-toggle
        v-model="importMode"
        mandatory
        density="compact"
        color="primary"
        variant="tonal"
        class="agent-pet-sprites-config__import-modes mb-4"
        aria-label="导入类型"
        :disabled="submitting || codexImporting || archiveBusy"
      >
        <v-btn value="codex">Codex Pet</v-btn>
        <v-btn value="archive">AgentPets 素材包</v-btn>
        <v-btn value="custom">自定义素材</v-btn>
      </v-btn-toggle>
      <PackArchiveImport
        v-show="importMode === 'archive'"
        :api="api"
        :plugin-id="instanceId"
        :targets="packs"
        @busy="archiveBusy = $event"
        @changed="archiveImported"
      />
      <div v-show="importMode !== 'archive'">
        <template v-if="importMode === 'custom'">
          <v-textarea
            v-model="packText"
            label="素材包 JSON"
            :placeholder="EXAMPLE"
            rows="6"
            variant="outlined"
            density="compact"
            class="agent-pet-sprites-config__json"
            hide-details="auto"
            :disabled="submitting"
          />
          <v-btn-toggle
            v-model="imageMode"
            mandatory
            density="compact"
            variant="outlined"
            class="my-3"
            :disabled="submitting || codexImporting"
            ><v-btn value="upload">上传精灵图</v-btn><v-btn value="url">使用图片 URL</v-btn></v-btn-toggle
          >
        </template>
        <v-file-input
          v-if="imageMode === 'upload'"
          v-model="fileModel"
          label="选择精灵图或 ZIP"
          accept="image/png,image/webp,image/gif,image/jpeg,.zip"
          variant="outlined"
          density="compact"
          prepend-icon=""
          prepend-inner-icon="mdi-paperclip"
          :error-messages="imageError ? [imageError] : []"
          hint="图片不超过 4MB，ZIP 不超过 8MB"
          persistent-hint
          :disabled="submitting || codexImporting"
          @update:model-value="onImage"
        />
        <v-alert v-if="importMessage" type="success" variant="tonal" density="compact" class="mt-3"
          >{{ validation?.pack?.name }} · 已准备好，可以添加到我的素材。</v-alert
        >
        <v-expansion-panels v-if="importMode === 'codex' && packText" variant="accordion" class="mt-3"
          ><v-expansion-panel title="编辑名称与动作映射"
            ><v-expansion-panel-text
              ><v-textarea
                v-model="packText"
                label="素材包 JSON"
                rows="6"
                variant="outlined"
                density="compact"
                hide-details
                class="agent-pet-sprites-config__json"
                :disabled="submitting" /></v-expansion-panel-text></v-expansion-panel
        ></v-expansion-panels>
        <v-alert
          v-if="importError || clientErrors.length || serverError"
          type="error"
          variant="tonal"
          density="compact"
          class="mt-3"
          ><div
            v-for="message in [
              ...(importError ? [importError] : []),
              ...clientErrors,
              ...(serverError ? [serverError] : []),
            ]"
            :key="message"
          >
            {{ message }}
          </div></v-alert
        >
        <div class="d-flex align-center justify-end flex-wrap ga-2 mt-4">
          <v-btn
            v-if="imageMode === 'upload'"
            color="primary"
            variant="tonal"
            prepend-icon="mdi-file-find-outline"
            :loading="codexImporting"
            :disabled="!selectedFile || !!imageError || codexImporting || submitting"
            @click="importCodexPet"
            >读取 Codex Pet</v-btn
          >
          <v-btn
            color="primary"
            variant="flat"
            prepend-icon="mdi-plus"
            :loading="submitting"
            :disabled="!canSubmit || codexImporting"
            @click="addPack"
            >添加 Pet</v-btn
          >
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-pet-sprites-config__thumb {
  background: rgba(var(--v-theme-on-surface), 0.025);
}
.agent-pet-sprites-config__list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 250px), 1fr));
  gap: 12px;
  background: transparent;
}
.agent-pet-sprites-config__card {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-width: 0;
  min-height: 96px;
  padding: 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  background: transparent;
}
.agent-pet-sprites-config__info {
  min-width: 0;
}
.agent-pet-sprites-config__name {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  overflow-wrap: anywhere;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}
.agent-pet-sprites-config__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 8px;
  margin-top: 5px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 11px;
  line-height: 1.5;
}
.agent-pet-sprites-config__meta span {
  white-space: nowrap;
}
.agent-pet-sprites-config__actions {
  align-self: start;
}
.agent-pet-sprites-config__empty {
  grid-column: 1 / -1;
  margin: 0;
  padding: 20px 12px;
  text-align: center;
}
.agent-pet-sprites-config__import {
  padding: 18px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}
.agent-pet-sprites-config__import-modes {
  display: flex;
  flex-wrap: wrap;
  height: auto;
}
.agent-pet-sprites-config__json :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}
</style>
