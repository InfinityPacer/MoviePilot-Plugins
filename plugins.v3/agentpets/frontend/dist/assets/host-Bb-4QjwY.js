import { a as sameMappings, b as sameCalibration } from './mappings-wSixMRjX.js';
import { n as normalizeSettings } from './settings-tnFA6UQD.js';

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
async function prepareEnabledConfig(api, pluginId, enabled, expectedEnabled) {
  if (!pluginId) throw new Error("未取得插件实例，请重新打开");
  const current = unwrap(await requireApi(api).get(`plugin/${pluginId}`));
  if (!current || typeof current !== "object" || Array.isArray(current))
    throw new Error("无法读取最新配置，未提交修改，请重试");
  if (Boolean(current.enabled) !== expectedEnabled) throw new Error("启用状态已在其他页面更改，请重新打开配置页后再试");
  return { ...current, enabled };
}
function sameSettings(a, b) {
  return a.scale === b.scale && a.speed === b.speed && a.roam === b.roam && (a.movement ?? "auto") === (b.movement ?? "auto");
}
async function saveSettings(api, pluginId, settings) {
  const values = normalizeSettings(settings);
  const saved = unwrap(await api.post(`plugin/${pluginId}/settings`, values));
  if (!saved || !sameSettings(saved, values)) throw new Error("活动设置回读不一致，请刷新后核对");
  return { ...saved };
}
async function saveMappings(api, pluginId, key, mappings, expected) {
  const result = unwrap(
    await api.post(`plugin/${pluginId}/packs/mappings`, { id: key, mappings, expected_mappings: expected })
  );
  if (result?.id !== key || !result.mappings || !sameMappings(result.mappings, mappings))
    throw new Error("动作映射回读不一致，请刷新后核对");
  return { ...result.mappings };
}
async function saveCalibration(api, pluginId, key, calibration, expected) {
  const result = unwrap(
    await api.post(`plugin/${pluginId}/packs/calibration`, {
      id: key,
      calibration,
      expected_calibration: expected
    })
  );
  if (result?.id !== key || !result.calibration || !sameCalibration(result.calibration, calibration))
    throw new Error("显示校准回读不一致，请刷新后核对");
  return { ...result.calibration };
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

const AGENT_HOST_KEY = "moviepilot:agent";
const HOST_UNSUPPORTED_MESSAGE = "当前主程序版本不支持助手形象，请将主程序升级到最新版本";

export { AGENT_HOST_KEY as A, HOST_UNSUPPORTED_MESSAGE as H, loadHostSelection as a, saveSettings as b, saveMappings as c, saveCalibration as d, loadEditor as l, prepareEnabledConfig as p, sameSettings as s, unwrap as u };
