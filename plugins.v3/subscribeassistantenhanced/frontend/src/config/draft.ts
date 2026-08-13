import { computed, reactive } from 'vue'

import { type ConfigKey, type SaeConfig } from './defaults'
import { normalizeSaeConfig } from './values'

/** 统一管理 Host 初始配置、界面修改计数与完整保存 payload。 */
export function useConfigDraft(initialConfig: unknown) {
  const initialSnapshot = normalizeSaeConfig(initialConfig)
  const draft = reactive<SaeConfig>(structuredClone(initialSnapshot))
  const configKeys = Object.keys(initialSnapshot) as ConfigKey[]
  const changedKeys = computed(() =>
    configKeys.filter(key => JSON.stringify(draft[key]) !== JSON.stringify(initialSnapshot[key])),
  )
  const changedCount = computed(() => changedKeys.value.length)

  /** 按稳定键和默认类型重建 Host 需要的完整配置对象。 */
  function buildSavePayload(): SaeConfig {
    return normalizeSaeConfig(draft)
  }

  return { draft, changedCount, changedKeys, buildSavePayload }
}
