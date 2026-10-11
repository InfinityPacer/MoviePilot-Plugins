import { n as normalizeSettings } from './settings-CQFXVfMf.js';

function unwrap(value) {
  if (value && typeof value === "object" && typeof value.success === "boolean") {
    const response = value;
    if (!response.success) throw new Error(response.message || "操作失败，请重试");
    return response.data;
  }
  if (value === void 0 || value === null) throw new Error("未收到有效响应，请重试");
  return value;
}
function requireApi(api) {
  if (!api?.get || !api.post) throw new Error("页面连接尚未就绪，请重新打开");
  return api;
}
async function loadEditor(api, pluginId) {
  if (!pluginId) throw new Error("未取得插件实例，请重新打开");
  const data = unwrap(await requireApi(api).get(`plugin/${pluginId}/editor`));
  if (!data || typeof data.enabled !== "boolean" || !Array.isArray(data.pets) || !data.settings) {
    throw new Error("无法读取形象列表，请刷新后重试");
  }
  return { ...data, settings: normalizeSettings(data.settings) };
}
function petImage(pet) {
  if (!pet.preview) return "";
  if (!pet.builtin) return pet.preview;
  const relativePath = `./${pet.preview}`;
  return new URL(relativePath, import.meta.url).href;
}
function sameSettings(a, b) {
  return a.scale === b.scale && a.speed === b.speed && a.roam === b.roam;
}
async function saveSettings(api, pluginId, settings) {
  const values = normalizeSettings(settings);
  const saved = unwrap(await api.post(`plugin/${pluginId}/settings`, values));
  if (!saved || !sameSettings(saved, values)) throw new Error("活动设置回读不一致，请刷新后核对");
  return { ...saved };
}
async function readDefaultPet(api) {
  const result = unwrap(
    await api.get("system/settings?setting_key=AI_AGENT_PET")
  );
  const item = result?.settings?.find((value) => value.setting_key === "AI_AGENT_PET");
  if (!item || item.redacted || typeof item.value !== "string") throw new Error("无法读取系统默认形象，需要管理员权限");
  return item.value;
}
async function readUserPet(api) {
  const result = unwrap(await api.get("user/config/AgentPet"));
  if (!result || !Object.hasOwn(result, "value")) throw new Error("无法读取当前用户的形象选择");
  const value = result.value;
  if (value === "builtin") return value;
  if (value && typeof value === "object") {
    const pet = value;
    if (typeof pet.plugin_id === "string" && typeof pet.key === "string")
      return { plugin_id: pet.plugin_id, key: pet.key };
  }
  return null;
}
async function loadHostSelection(api) {
  const [defaultId, user] = await Promise.all([readDefaultPet(api), readUserPet(api)]);
  return { defaultId, user };
}
async function checkAvailablePet(api, pluginId, key) {
  const pets = unwrap(await api.get("plugin/agent_pets"));
  if (!Array.isArray(pets) || !pets.some((pet) => pet.plugin_id === pluginId && pet.key === key)) {
    throw new Error("此 Pet 当前不可用，请先启用插件或刷新形象列表");
  }
}
async function applyDefaultPet(api, pluginId, key, followDefault, isCurrent = () => true) {
  const guard = () => {
    if (!isCurrent()) throw new DOMException("页面已关闭", "AbortError");
  };
  const id = `${pluginId}:${key}`;
  try {
    guard();
    const current = await readDefaultPet(api);
    guard();
    if (current !== id) unwrap(await api.post("system/env", { AI_AGENT_PET: id }));
    if (await readDefaultPet(api) !== id) throw new Error("默认形象回读不一致");
  } catch (error) {
    if (!isCurrent()) throw error;
    throw new Error("系统默认形象尚未确认生效，请重试；活动调整已保存", { cause: error });
  }
  try {
    guard();
    let user = await readUserPet(api);
    guard();
    if (followDefault && user !== null) {
      unwrap(await api.post("user/config/AgentPet", null));
      user = await readUserPet(api);
      if (user !== null) throw new Error("个人选择回读不一致");
    }
    return { defaultId: id, user };
  } catch (error) {
    if (!isCurrent()) throw error;
    throw new Error("系统默认形象已设置；当前用户选择未确认，请重试", { cause: error });
  }
}
function reloadForPet() {
  window.location.reload();
}

const AGENT_HOST_KEY = "moviepilot:agent";
const HOST_UNSUPPORTED_MESSAGE = "当前主程序版本不支持助手形象，请将主程序升级到最新版本";

export { AGENT_HOST_KEY as A, HOST_UNSUPPORTED_MESSAGE as H, loadHostSelection as a, saveSettings as b, checkAvailablePet as c, applyDefaultPet as d, loadEditor as l, petImage as p, reloadForPet as r, sameSettings as s };
