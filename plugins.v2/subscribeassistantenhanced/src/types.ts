/**
 * 插件配置项允许保存的基础值类型。
 */
export type ConfigValue = string | number | boolean | string[] | number[] | null

/**
 * 订阅助手增强插件的配置模型。
 */
export interface PluginConfigModel {
  /** 是否启用插件主开关。 */
  enabled?: boolean

  /** 兼容后续配置项的动态字段。 */
  [key: string]: ConfigValue | undefined
}

/**
 * 表单选择项的展示和值定义。
 */
export interface SelectOption {
  /** 选项显示文案。 */
  title: string

  /** 选项保存值。 */
  value: ConfigValue
}

/**
 * 配置字段的元信息，供后续按字段渲染时复用。
 */
export interface FieldMeta {
  /** 配置字段名。 */
  key: keyof PluginConfigModel | string

  /** 字段渲染控件类型。 */
  kind: 'switch' | 'number' | 'text' | 'select' | 'multi-select' | 'cron' | 'textarea'

  /** 字段显示名称。 */
  label: string

  /** 字段辅助说明。 */
  hint?: string

  /** 字段可选项。 */
  options?: SelectOption[]
}
