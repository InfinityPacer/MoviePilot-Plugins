<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { PluginConfigModel } from './types'
import { fieldSections } from './config/fields'
import DomainNav, { type DomainItem } from './components/DomainNav.vue'
import FieldControl from './components/FieldControl.vue'
import GlobalControls from './components/GlobalControls.vue'
import RuntimePlan from './components/RuntimePlan.vue'
import SectionPanel from './components/SectionPanel.vue'

/**
 * 插件 Vue 配置页接收的宿主参数。
 */
interface ConfigProps {
  /** 宿主传入的当前插件配置。 */
  initialConfig?: PluginConfigModel
}

/**
 * 插件 Vue 配置页向宿主提交的事件。
 */
interface ConfigEmits {
  /** 保存当前配置副本，由宿主负责调用配置保存接口。 */
  save: [config: PluginConfigModel]

  /** 请求关闭配置窗口。 */
  close: []
}

const props = withDefaults(defineProps<ConfigProps>(), {
  initialConfig: () => ({}),
})

const emit = defineEmits<ConfigEmits>()

const config = reactive<PluginConfigModel>({})
const activeDomain = ref('种子删除')

/**
 * 业务域导航项，标题与字段分区标题保持一致以便直接定位分区。
 */
const domains: DomainItem[] = [
  { key: '种子删除', title: '种子删除', icon: 'mdi-delete-clock' },
  { key: '订阅待定', title: '订阅待定', icon: 'mdi-timer-sand' },
  { key: '订阅暂停', title: '订阅暂停', icon: 'mdi-pause-circle-outline' },
  { key: '订阅洗版', title: '订阅洗版', icon: 'mdi-auto-fix' },
  { key: '完结信号', title: '完结信号', icon: 'mdi-shield-check-outline' },
]

/**
 * 当前业务域字段分区，所有配置字段都通过 FieldControl 进入保存路径。
 */
const activeSection = computed(() => fieldSections.find(section => section.title === activeDomain.value) ?? fieldSections[0])

/** 保持本地编辑副本与宿主传入配置同步，避免直接修改 props。 */
function syncConfig(nextConfig: PluginConfigModel) {
  Object.keys(config).forEach(key => {
    delete config[key]
  })
  Object.assign(config, nextConfig)
}

/** 将本地配置副本提交给宿主保存。 */
function saveConfig() {
  emit('save', { ...config })
}

watch(
  () => props.initialConfig,
  nextConfig => syncConfig(nextConfig ?? {}),
  { immediate: true, deep: true },
)
</script>

<template>
  <VCard class="subscribe-assistant-config" flat>
    <VCardTitle class="config-title">
      <div>
        <div class="text-h6 font-weight-medium">订阅助手（增强版）</div>
        <div class="text-body-2 text-medium-emphasis">按业务域组织配置，保存后由插件运行时读取同一套配置键。</div>
      </div>
      <VSpacer />
      <VBtn icon="mdi-close" variant="text" density="comfortable" aria-label="关闭" @click="emit('close')" />
    </VCardTitle>

    <VDivider />

    <VCardText class="config-content">
      <VAlert
        type="warning"
        variant="tonal"
        title="BETA 功能"
        text="本插件仍处于测试阶段，可能调整订阅状态、洗版记录、下载任务和媒体文件。"
      />

      <GlobalControls :model="config" class="mt-6" />
      <RuntimePlan :model="config" class="mt-4" />

      <div class="config-domains">
        <DomainNav v-model="activeDomain" :items="domains" />
        <main class="domain-content">
          <SectionPanel :title="activeSection.title" :subtitle="activeSection.subtitle">
            <VRow
              v-for="(row, rowIndex) in activeSection.rows"
              :key="`${activeSection.title}-${rowIndex}`"
              dense
            >
              <VCol
                v-for="field in row"
                :key="field.key"
                cols="12"
                :md="field.md ?? 4"
              >
                <FieldControl :field="field" :model="config" />
              </VCol>
            </VRow>
          </SectionPanel>
        </main>
      </div>
    </VCardText>

    <VDivider />

    <VCardActions class="config-actions">
      <VSpacer />
      <VBtn variant="text" @click="emit('close')">取消</VBtn>
      <VBtn color="primary" variant="flat" prepend-icon="mdi-content-save" @click="saveConfig">
        保存
      </VBtn>
    </VCardActions>
  </VCard>
</template>

<style scoped>
.subscribe-assistant-config {
  width: 100%;
}

.config-title {
  align-items: center;
  display: flex;
  gap: 16px;
  padding: 20px 24px;
}

.config-content {
  padding: 24px;
}

.config-domains {
  align-items: start;
  display: grid;
  gap: 18px;
  grid-template-columns: 220px minmax(0, 1fr);
  margin-block-start: 16px;
}

.domain-content {
  min-width: 0;
}

.config-actions {
  padding: 16px 24px;
}

@media (max-width: 900px) {
  .config-title,
  .config-actions,
  .config-content {
    padding-inline: 16px;
  }

  .config-domains {
    grid-template-columns: 1fr;
  }
}
</style>
