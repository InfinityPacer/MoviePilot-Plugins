import { p as parseCalibration, B as BUILTIN_PACKS } from './_plugin-vue_export-helper-DQ595t25.js';

function withLoadTimeout(operation, signal, timeout = 5e3) {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    };
    const abort = () => {
      cleanup();
      reject(new Error("loading cancelled"));
    };
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("loading timed out"));
    }, timeout);
    signal.addEventListener("abort", abort, { once: true });
    operation.then(
      (value) => {
        cleanup();
        resolve(value);
      },
      (error) => {
        cleanup();
        reject(error);
      }
    );
    if (signal.aborted) abort();
  });
}
async function loadImage(src, signal) {
  const image = new Image();
  try {
    return await withLoadTimeout(
      new Promise((resolve, reject) => {
        image.onload = () => {
          const width = image.naturalWidth;
          const height = image.naturalHeight;
          if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0)
            reject(new Error("invalid image dimensions"));
          else resolve({ width, height });
        };
        image.onerror = () => reject(new Error("image unavailable"));
        image.src = src;
      }),
      signal
    );
  } finally {
    image.onload = null;
    image.onerror = null;
  }
}

const YING_PACK = {
  id: "ying",
  name: "小映",
  description: "小映校准参考帧",
  sheet: "",
  grid: { cols: 1, rows: 1 },
  frames: { idle: 0 },
  actions: {
    idle: { frames: ["idle"], frame_ms: 160, loop: false },
    peek: { frames: ["idle"], frame_ms: 160, loop: false }
  },
  random_actions: [],
  calibration: parseCalibration({ eye_x: 0.5, eye_y: 0.38 })
};
function builtinDefaultCalibration(key) {
  return parseCalibration((key === "ying" ? YING_PACK : BUILTIN_PACKS[key])?.calibration);
}
async function loadBuiltinCalibration(api, pluginId, key, signal) {
  const fallback = builtinDefaultCalibration(key);
  if (!api?.get || !pluginId) return fallback;
  const response = await withLoadTimeout(
    api.get(
      `plugin/${pluginId}/packs/calibration?key=${encodeURIComponent(key)}`
    ),
    signal
  );
  if (!response?.success || response.data?.id !== key || !response.data.calibration) throw new Error("内置校准读取失败");
  return parseCalibration(response.data.calibration);
}

const POSES = [
  "idle",
  "blink",
  "talk",
  "think",
  "jump",
  "wave",
  "held",
  "fall",
  "sit",
  "walk1",
  "walk2",
  "walk3",
  "walk4",
  "doze",
  "confused",
  "alert",
  "victory",
  "busy"
];
const ASSET_BASE = import.meta.url;
function frameUrl(pose, base = ASSET_BASE) {
  return new URL(`ying/${pose}.webp`, base).href;
}
function phasePose(phase) {
  if (phase === "thinking") return "think";
  if (phase === "tool") return "busy";
  if (phase === "awaiting") return "alert";
  return null;
}
function eventPose(name) {
  switch (name) {
    case "agent.done":
      return { pose: "victory", duration: 2200 };
    case "agent.error":
      return { pose: "confused", duration: 2600 };
    case "agent.preview":
    case "agent.bubble":
      return { pose: "talk", duration: 1600 };
    case "agent.panel.open":
      return { pose: "wave", duration: 1200 };
    default:
      return null;
  }
}
function resolvePose(input) {
  if (input.motion === "drag") return "held";
  if (input.motion === "fall") return input.rising ? "jump" : "fall";
  if (input.motion === "sit") return "sit";
  if (input.transient) return input.transient;
  if (input.sustained) return input.sustained;
  if (input.motion === "walk") return WALK_CYCLE[(input.walkPhase % 4 + 4) % 4];
  if (input.dozing) return "doze";
  if (input.blinking) return "blink";
  return "idle";
}
const WALK_CYCLE = ["walk1", "walk2", "walk3", "walk4"];
const WALK_FRAME_STRIDE_PERCENT = 14;
function walkFrame(distance, charHeight) {
  const stride = Math.max(1, charHeight * WALK_FRAME_STRIDE_PERCENT / 100);
  return Math.floor(Math.max(0, distance) / stride) % WALK_CYCLE.length;
}

export { POSES as P, YING_PACK as Y, loadImage as a, builtinDefaultCalibration as b, walkFrame as c, eventPose as e, frameUrl as f, loadBuiltinCalibration as l, phasePose as p, resolvePose as r, withLoadTimeout as w };
