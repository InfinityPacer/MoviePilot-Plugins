import { sameMappings, type ActionMappings } from '@/sprites/mappings'
import type { PluginApi } from '@/host'
import { builtinAvatar } from './avatars'
import { normalizeSettings, type YingSettings } from '@/stage/settings'

export interface PetChoice {
  key: string
  name: string
  description: string
  mode: 'stage' | 'renderer'
  preview: string
  builtin: boolean
}

export interface EditorSnapshot {
  enabled: boolean
  settings: YingSettings
  pets: PetChoice[]
}

export type UserPetSelection = { plugin_id: string; key: string } | 'builtin' | null
export interface HostSelection {
  defaultId: string
  user: UserPetSelection
}

/** 联邦 API 返回 endpoint 原始载荷；宿主接口有 envelope，形象目录是裸数组。 */
export function unwrap<T>(value: unknown): T {
  if (value && typeof value === 'object' && typeof (value as { success?: unknown }).success === 'boolean') {
    const response = value as { success: boolean; message?: string; data?: T }
    if (!response.success) throw new Error(response.message || '操作失败，请重试')
    return response.data as T
  }
  if (value === undefined || value === null) throw new Error('未收到有效响应，请重试')
  return value as T
}

function requireApi(api: PluginApi | null | undefined): PluginApi {
  if (!api?.get || !api.post) throw new Error('页面连接尚未就绪，请重新打开')
  return api
}

export async function loadEditor(api: PluginApi | null | undefined, pluginId: string): Promise<EditorSnapshot> {
  if (!pluginId) throw new Error('未取得插件实例，请重新打开')
  const data = unwrap<EditorSnapshot>(await requireApi(api).get(`plugin/${pluginId}/editor`))
  if (!data || typeof data.enabled !== 'boolean' || !Array.isArray(data.pets) || !data.settings) {
    throw new Error('无法读取形象列表，请刷新后重试')
  }
  return { ...data, settings: normalizeSettings(data.settings) }
}

export function petImage(pet: PetChoice): string {
  if (!pet.preview) return ''
  return pet.builtin ? builtinAvatar(pet.key) : pet.preview
}

export function sameSettings(a: YingSettings, b: YingSettings): boolean {
  return a.scale === b.scale && a.speed === b.speed && a.roam === b.roam
}

export async function saveSettings(api: PluginApi, pluginId: string, settings: YingSettings): Promise<YingSettings> {
  const values = normalizeSettings(settings)
  const saved = unwrap<YingSettings>(await api.post(`plugin/${pluginId}/settings`, values))
  if (!saved || !sameSettings(saved, values)) throw new Error('活动设置回读不一致，请刷新后核对')
  return { ...saved }
}

export async function saveMappings(
  api: PluginApi,
  pluginId: string,
  key: string,
  mappings: ActionMappings,
  expected: ActionMappings,
): Promise<ActionMappings> {
  const result = unwrap<{ id: string; mappings: ActionMappings }>(
    await api.post(`plugin/${pluginId}/packs/mappings`, { id: key, mappings, expected_mappings: expected }),
  )
  if (result?.id !== key || !result.mappings || !sameMappings(result.mappings, mappings))
    throw new Error('动作映射回读不一致，请刷新后核对')
  return { ...result.mappings }
}

/** 只查询所需字段，不读取系统环境或其他用户设置。 */
export async function readDefaultPet(api: PluginApi): Promise<string> {
  const result = unwrap<{ settings: Array<{ setting_key: string; value?: unknown; redacted?: boolean }> }>(
    await api.get('system/settings?setting_key=AI_AGENT_PET'),
  )
  const item = result?.settings?.find(value => value.setting_key === 'AI_AGENT_PET')
  if (!item || item.redacted || typeof item.value !== 'string') throw new Error('无法读取系统默认形象，需要管理员权限')
  return item.value
}

export async function readUserPet(api: PluginApi): Promise<UserPetSelection> {
  const result = unwrap<{ value: unknown }>(await api.get('user/config/AgentPet'))
  if (!result || !Object.hasOwn(result, 'value')) throw new Error('无法读取当前用户的形象选择')
  const value = result.value
  if (value === 'builtin') return value
  if (value && typeof value === 'object') {
    const pet = value as { plugin_id?: unknown; key?: unknown }
    if (typeof pet.plugin_id === 'string' && typeof pet.key === 'string')
      return { plugin_id: pet.plugin_id, key: pet.key }
  }
  return null
}

export async function loadHostSelection(api: PluginApi): Promise<HostSelection> {
  const [defaultId, user] = await Promise.all([readDefaultPet(api), readUserPet(api)])
  return { defaultId, user }
}

/** 应用前重新确认形象仍在宿主目录里，停用或已删除的形象不可设为默认。 */
export async function checkAvailablePet(api: PluginApi, pluginId: string, key: string): Promise<void> {
  const pets = unwrap<Array<{ plugin_id: string; key: string }>>(await api.get('plugin/agent_pets'))
  if (!Array.isArray(pets) || !pets.some(pet => pet.plugin_id === pluginId && pet.key === key)) {
    throw new Error('此 Pet 当前不可用，请先启用插件或刷新形象列表')
  }
}

/** 仅写系统默认形象和用户明确勾选的当前用户偏好，逐步回读，失败保留真实阶段。 */
export async function applyDefaultPet(
  api: PluginApi,
  pluginId: string,
  key: string,
  followDefault: boolean,
  isCurrent: () => boolean = () => true,
): Promise<HostSelection> {
  const guard = () => {
    if (!isCurrent()) throw new DOMException('页面已关闭', 'AbortError')
  }
  const id = `${pluginId}:${key}`
  try {
    guard()
    const current = await readDefaultPet(api)
    guard()
    if (current !== id) unwrap(await api.post('system/env', { AI_AGENT_PET: id }))
    if ((await readDefaultPet(api)) !== id) throw new Error('默认形象回读不一致')
  } catch (error) {
    if (!isCurrent()) throw error
    throw new Error('系统默认形象尚未确认生效，请重试；活动调整已保存', { cause: error })
  }
  try {
    guard()
    let user = await readUserPet(api)
    guard()
    if (followDefault && user !== null) {
      unwrap(await api.post('user/config/AgentPet', null))
      user = await readUserPet(api)
      if (user !== null) throw new Error('个人选择回读不一致')
    }
    return { defaultId: id, user }
  } catch (error) {
    if (!isCurrent()) throw error
    throw new Error('系统默认形象已设置；当前用户选择未确认，请重试', { cause: error })
  }
}

/** 宿主尚未公开联邦形象切换方法；保存并回读后重新加载页面，交由宿主正常解析选择。 */
export function reloadForPet(): void {
  window.location.reload()
}
