import { configDefaults, type SaeConfig } from '@/config/defaults'

/** 构造独立的最小完整配置，避免用例共享数组或修改生产默认值。 */
export function createConfig(overrides: Partial<SaeConfig> = {}): SaeConfig {
  return structuredClone({ ...configDefaults, ...overrides })
}
