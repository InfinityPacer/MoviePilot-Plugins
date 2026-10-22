import { p as parseCalibration, B as BUILTIN_PACKS, r as resolveAction } from './_plugin-vue_export-helper-Cx9XzNqS.js';
import { importShared } from './__federation_fn_import-JrT3xvdd.js';

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

const {computed,nextTick,onBeforeUnmount,ref,watch} = await importShared('vue');
const GREETING_MARKER = Symbol.for("moviepilot.agentpets.startup-greeting");
const GREETING_SETTLE_MS = 300;
const GREETING_WAIT_MS = 5e3;
const SINGLE_GREETING_MS = 600;
const GREETING_PAUSE_MS = 220;
function claimPageGreeting(page, owner = true) {
  if (Reflect.get(page, GREETING_MARKER)) return false;
  Reflect.defineProperty(page, GREETING_MARKER, { value: owner, configurable: true });
  return true;
}
function greetingPlayback(pack, mappings, stage = true) {
  const resolved = resolveAction(pack, "wave", void 0, false, {
    mappings,
    mappingKey: stage ? "stage.wave" : void 0
  });
  if (resolved.key === "idle") return null;
  const action = resolved.action;
  if (!action.frames.length || action.frames.some((frame) => !(frame in pack.frames))) return null;
  if (action.frames.length === 1) return { duration: SINGLE_GREETING_MS, pause: GREETING_PAUSE_MS };
  const duration = action.frames.reduce(
    (total, _, index) => total + (action.frame_durations?.[index] ?? action.frame_ms),
    0
  );
  return Number.isFinite(duration) && duration > 0 ? { duration, pause: 0, frameDriven: true } : null;
}
function useStartupGreeting(options) {
  const pending = ref(false);
  const phase = ref(null);
  const round = ref(0);
  const active = computed(() => pending.value || phase.value !== null);
  let handled = false;
  let stopped = false;
  let timer = 0;
  let deadline = 0;
  let playback = null;
  const owner = Symbol();
  function consumeOpportunity() {
    if (typeof document === "undefined") return;
    if (Reflect.get(document, GREETING_MARKER) === owner)
      Reflect.defineProperty(document, GREETING_MARKER, { value: true, configurable: true });
  }
  function clearTimers() {
    window.clearTimeout(timer);
    window.clearTimeout(deadline);
    timer = deadline = 0;
  }
  function finish(notify = true) {
    consumeOpportunity();
    const wasActive = active.value;
    handled = true;
    clearTimers();
    pending.value = false;
    phase.value = null;
    if (wasActive && notify) options.finished?.();
  }
  async function playRound() {
    if (stopped || !options.allowed() || !options.ready() || !playback) return finish();
    consumeOpportunity();
    pending.value = false;
    phase.value = "wave";
    const current = ++round.value;
    await nextTick();
    if (stopped || phase.value !== "wave" || round.value !== current) return;
    if (!playback.frameDriven) timer = window.setTimeout(completeRound, playback.duration);
  }
  function completeRound() {
    if (phase.value !== "wave" || !playback) return;
    if (round.value === 2) return finish();
    if (playback.pause) {
      phase.value = "pause";
      timer = window.setTimeout(() => void playRound(), playback.pause);
    } else void playRound();
  }
  function frameComplete(completedRound = round.value) {
    if (!playback?.frameDriven || completedRound !== round.value) return;
    if (options.ready() && options.allowed()) completeRound();
    else if (phase.value) finish();
  }
  function prepare() {
    if (!pending.value) return;
    window.clearTimeout(timer);
    if (!options.allowed()) return finish();
    if (!options.ready()) return;
    playback = options.playback();
    if (!playback) return finish();
    timer = window.setTimeout(() => {
      window.clearTimeout(deadline);
      void playRound();
    }, GREETING_SETTLE_MS);
  }
  function arm() {
    if (typeof document === "undefined" || handled || !claimPageGreeting(document, owner)) return;
    handled = true;
    if (!options.allowed()) return finish();
    pending.value = true;
    deadline = window.setTimeout(() => finish(), GREETING_WAIT_MS);
    prepare();
  }
  watch([options.ready, options.stable, options.playback], prepare, { flush: "post" });
  watch(
    options.allowed,
    (allowed) => {
      if (!allowed && active.value) finish();
    },
    { flush: "sync" }
  );
  watch(
    options.ready,
    (ready) => {
      if (!ready && phase.value) finish();
    },
    { flush: "sync" }
  );
  onBeforeUnmount(() => {
    stopped = true;
    if (pending.value && !round.value && Reflect.get(document, GREETING_MARKER) === owner)
      Reflect.deleteProperty(document, GREETING_MARKER);
    finish(false);
  });
  return { pending, phase, round, active, arm, frameComplete, cancel: finish };
}

export { GREETING_PAUSE_MS as G, POSES as P, SINGLE_GREETING_MS as S, YING_PACK as Y, loadImage as a, builtinDefaultCalibration as b, walkFrame as c, eventPose as e, frameUrl as f, greetingPlayback as g, loadBuiltinCalibration as l, phasePose as p, resolvePose as r, useStartupGreeting as u, withLoadTimeout as w };
