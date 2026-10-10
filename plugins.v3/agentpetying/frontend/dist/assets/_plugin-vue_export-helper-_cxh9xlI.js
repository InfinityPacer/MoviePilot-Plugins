const SCALE_RANGE = [0.6, 1.6];
const SPEED_RANGE = [0.5, 2];
const DEFAULT_SETTINGS = { scale: 1, speed: 1 };
const SETTINGS_EVENT = "agentpetying.settings";
function bounded(value, range, fallback) {
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.round(Math.min(Math.max(number, range[0]), range[1]) * 100) / 100;
}
function normalizeSettings(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    scale: bounded(source.scale, SCALE_RANGE, DEFAULT_SETTINGS.scale),
    speed: bounded(source.speed, SPEED_RANGE, DEFAULT_SETTINGS.speed)
  };
}
async function loadSettings(api, pluginId) {
  if (!api?.get || !pluginId) return { ...DEFAULT_SETTINGS };
  try {
    const response = await api.get(`plugin/${pluginId}/settings`);
    if (response?.success && response.data) return normalizeSettings(response.data);
  } catch {
    console.warn("[AgentPetYing] settings unavailable");
  }
  return { ...DEFAULT_SETTINGS };
}

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

export { DEFAULT_SETTINGS as D, SETTINGS_EVENT as S, _export_sfc as _, SCALE_RANGE as a, SPEED_RANGE as b, loadSettings as l, normalizeSettings as n };
