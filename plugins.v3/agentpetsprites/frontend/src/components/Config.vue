<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'

import type { PluginApi } from '@/host'
import { BUILTIN_PACK_ID, builtinAsset, validatePack } from '@/pack/schema'

/** 素材包列表项，与后端 `_summary` 一致。 */
interface PackSummary {
  id: string
  name: string
  description: string
  /** 是否为内置素材包（不可删除）。 */
  builtin: boolean
  /** builtin、upload 或 url。 */
  source: string
  /** 预览图：内置为相对联邦产物目录的路径，其余为 data/http URL，可能为空。 */
  preview: string
  grid: { cols: number; rows: number } | null
  frame_count: number
  action_count: number
}

type HostToast = Partial<Record<'success' | 'error' | 'warning' | 'info', (message: string) => unknown>>
type HostConfirm = (options?: {
  type?: 'info' | 'warn' | 'error'
  title?: string
  content?: string
}) => Promise<boolean>

const props = withDefaults(
  defineProps<{
    initialConfig?: Record<string, unknown> | null
    api?: PluginApi | null
    pluginId?: string
  }>(),
  { initialConfig: null, api: null, pluginId: '' },
)

const emit = defineEmits<{
  /** 请求宿主持久化配置；素材包不在配置里，已经通过插件接口即时保存。 */
  save: [{ enabled: boolean }]
  close: []
}>()

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
const instanceId = computed(() => props.pluginId || 'AgentPetSprites')
const enabled = ref(Boolean(props.initialConfig?.enabled))
const packs = ref<PackSummary[]>([])
const loading = ref(false)
const submitting = ref(false)
const packText = ref('')
const imageMode = ref<'upload' | 'url'>('upload')
const imageFile = ref<File | null>(null)
const fileModel = ref<File[]>([])
const imageError = ref('')
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
    !!validation.value?.pack &&
    !clientErrors.value.length &&
    !submitting.value &&
    (imageMode.value === 'url' || (!!imageFile.value && !imageError.value)),
)

function previewSrc(pack: PackSummary): string {
  if (pack.builtin) return builtinAsset('preview.png')
  return pack.preview
}

function notify(kind: 'success' | 'error', message: string) {
  toast?.[kind]?.(message)
}

async function refresh() {
  if (!props.api?.get) return
  loading.value = true
  try {
    const response = await props.api.get<PackSummary[]>(`plugin/${instanceId.value}/packs`)
    if (response?.success && Array.isArray(response.data)) packs.value = response.data
  } catch {
    console.warn('[AgentPetSprites] packs unavailable')
  } finally {
    loading.value = false
  }
}

function onImage(value: File | File[] | null | undefined) {
  const file = Array.isArray(value) ? (value[0] ?? null) : (value ?? null)
  imageFile.value = file
  imageError.value = ''
  if (!file) return
  if (!IMAGE_TYPES.includes(file.type)) imageError.value = '只支持 PNG、WebP、GIF 或 JPEG'
  else if (file.size > MAX_IMAGE_BYTES) imageError.value = '精灵图不能超过 4MB'
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
  submitting.value = true
  serverError.value = ''
  try {
    const image = imageMode.value === 'upload' && imageFile.value ? await readDataUrl(imageFile.value) : null
    const response = await props.api.post<PackSummary>(`plugin/${instanceId.value}/packs`, {
      pack: packText.value,
      image,
    })
    if (!response?.success) {
      serverError.value = response?.message || '添加失败'
      return
    }
    notify('success', `已添加素材包 ${response.data?.name ?? ''}`)
    packText.value = ''
    imageFile.value = null
    fileModel.value = []
    await refresh()
  } catch {
    serverError.value = '添加失败，请检查网络或稍后重试'
  } finally {
    submitting.value = false
  }
}

async function removePack(pack: PackSummary) {
  if (!props.api?.post) return
  const accepted = confirm
    ? await confirm({
        type: 'warn',
        title: '删除素材包',
        content: `删除「${pack.name}」后，选择它的用户会回到内置机器人。`,
      })
    : window.confirm(`删除素材包「${pack.name}」？`)
  if (!accepted) return
  const response = await props.api.post(`plugin/${instanceId.value}/packs/delete`, { id: pack.id })
  if (response?.success) {
    notify('success', `已删除素材包 ${pack.name}`)
    await refresh()
  } else notify('error', response?.message || '删除失败')
}

function save() {
  emit('save', { enabled: enabled.value })
}

onMounted(refresh)
</script>

<template>
  <v-card flat class="agent-pet-sprites-config">
    <v-card-text>
      <v-switch v-model="enabled" label="启用插件" color="primary" hide-details class="mb-4" />

      <div class="text-subtitle-1 mb-2">素材包</div>
      <v-progress-linear v-if="loading" indeterminate class="mb-2" />
      <v-list density="comfortable" class="mb-6" border rounded>
        <v-list-item v-for="pack in packs" :key="pack.id">
          <template #prepend>
            <v-avatar rounded="lg" size="48" class="agent-pet-sprites-config__thumb">
              <v-img v-if="previewSrc(pack)" :src="previewSrc(pack)" :alt="pack.name" />
              <v-icon v-else icon="mdi-image-outline" />
            </v-avatar>
          </template>
          <v-list-item-title>{{ pack.name }}</v-list-item-title>
          <v-list-item-subtitle>
            {{ pack.id }} · {{ pack.builtin ? '内置' : pack.source === 'upload' ? '已上传' : '远程图片' }} ·
            {{ pack.frame_count }} 帧 · {{ pack.action_count }} 个动作
          </v-list-item-subtitle>
          <template v-if="!pack.builtin" #append>
            <v-btn
              icon="mdi-delete-outline"
              variant="text"
              :aria-label="`删除 ${pack.name}`"
              @click="removePack(pack)"
            />
          </template>
        </v-list-item>
        <v-list-item v-if="!packs.length && !loading">
          <v-list-item-title class="text-medium-emphasis">
            {{ props.api ? '暂无素材包' : '当前环境无法读取素材包' }}
          </v-list-item-title>
        </v-list-item>
      </v-list>

      <div class="text-subtitle-1 mb-2">添加素材包</div>
      <v-textarea
        v-model="packText"
        label="素材包 JSON"
        :placeholder="EXAMPLE"
        rows="8"
        auto-grow
        variant="outlined"
        class="agent-pet-sprites-config__json"
        persistent-placeholder
        hide-details="auto"
      />
      <v-btn-toggle v-model="imageMode" mandatory density="comfortable" variant="outlined" class="my-3" divided>
        <v-btn value="upload">上传精灵图</v-btn>
        <v-btn value="url">使用 JSON 中的图片 URL</v-btn>
      </v-btn-toggle>
      <v-file-input
        v-if="imageMode === 'upload'"
        v-model="fileModel"
        label="精灵图（PNG、WebP、GIF、JPEG，不超过 4MB）"
        accept="image/png,image/webp,image/gif,image/jpeg"
        variant="outlined"
        prepend-icon="mdi-image-outline"
        :error-messages="imageError ? [imageError] : []"
        hide-details="auto"
        @update:model-value="onImage"
      />
      <v-alert v-if="clientErrors.length || serverError" type="error" variant="tonal" density="compact" class="mt-3">
        <div v-for="error in [...clientErrors, ...(serverError ? [serverError] : [])]" :key="error">{{ error }}</div>
      </v-alert>
      <div class="d-flex align-center mt-3">
        <span class="text-caption text-medium-emphasis">
          格式说明见插件 README；内置素材包 ID {{ BUILTIN_PACK_ID }} 不可占用。
        </span>
        <v-spacer />
        <v-btn color="primary" variant="tonal" :loading="submitting" :disabled="!canSubmit" @click="addPack">
          校验并添加
        </v-btn>
      </div>
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn variant="text" @click="emit('close')">关闭</v-btn>
      <v-btn color="primary" variant="flat" @click="save">保存</v-btn>
    </v-card-actions>
  </v-card>
</template>

<style scoped>
.agent-pet-sprites-config__thumb {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.agent-pet-sprites-config__json :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.8125rem;
}
</style>
