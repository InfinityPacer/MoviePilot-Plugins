const SCALE_RANGE = [0.6, 1.6];
const SPEED_RANGE = [0.5, 2];
const ROAM_MODES = ["surfaces", "floor", "free"];
const DEFAULT_SETTINGS = { scale: 1, speed: 1, roam: "surfaces" };
const SETTINGS_EVENT = "agentpets.settings";
function bounded(value, range, fallback) {
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.round(Math.min(Math.max(number, range[0]), range[1]) * 100) / 100;
}
function normalizeSettings(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    scale: bounded(source.scale, SCALE_RANGE, DEFAULT_SETTINGS.scale),
    speed: bounded(source.speed, SPEED_RANGE, DEFAULT_SETTINGS.speed),
    roam: ROAM_MODES.includes(source.roam) ? source.roam : DEFAULT_SETTINGS.roam
  };
}
async function loadSettings(api, pluginId) {
  if (!api?.get || !pluginId) return { ...DEFAULT_SETTINGS };
  try {
    const response = await api.get(`plugin/${pluginId}/settings`);
    if (response?.success && response.data) return normalizeSettings(response.data);
  } catch {
    console.warn("[AgentPets] settings unavailable");
  }
  return { ...DEFAULT_SETTINGS };
}

export { DEFAULT_SETTINGS as D, ROAM_MODES as R, SETTINGS_EVENT as S, SCALE_RANGE as a, SPEED_RANGE as b, loadSettings as l, normalizeSettings as n };
