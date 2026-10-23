import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { b as builtinDefaultCalibration, u as useStartupGreeting, r as resolvePose, P as POSES, f as frameUrl, l as loadBuiltinCalibration, Y as YING_PACK, w as withLoadTimeout, p as phasePose, e as eventPose, G as GREETING_PAUSE_MS, S as SINGLE_GREETING_MS, c as walkFrame } from './greeting-B7a9rq7Z.js';
import { r as resolveAction, p as parseCalibration, j as calibrationLayout, L as LANDMARKS, c as calibrationPoint, h as calibrationEye, i as mirrorFace, o as onEditorPresence, P as PACK_UPDATED_EVENT, _ as _export_sfc } from './_plugin-vue_export-helper-Cx9XzNqS.js';
import { p as pickFreeTarget, a as pickWalkTarget, i as isBlocked, f as floorLine, s as standable, c as coversAny, D as DEFAULT_SETTINGS, e as effectiveScale, b as peekHome, d as peekLayout, n as normalizePeekAngles, r as readViewport, g as freeBounds, h as clamp, S as SETTINGS_EVENT, l as loadSettings, j as normalizeSettings, k as ratioToX, m as avoidPanel, o as groundTop, x as xBounds, q as sameRect, t as checkSupport, u as pickClearX, v as surfaceXBounds, w as blockedSpan, y as nearestEdge, z as hopVelocity, A as xToRatio, B as isPeekEdge, C as intersectionArea, E as peekPanelShift, F as computeLanding, G as dropPeekEdge, P as PEEK_TILT_SECONDS, H as PEEK_TUCK, I as PEEK_RISE_SECONDS } from './settings-DI0CwwAz.js';

class PausableTimers {
  paused = false;
  jobs = /* @__PURE__ */ new Map();
  has(name) {
    return this.jobs.has(name);
  }
  clear(name) {
    const job = this.jobs.get(name);
    if (job?.id !== void 0) window.clearTimeout(job.id);
    this.jobs.delete(name);
  }
  set(name, delay, callback) {
    this.clear(name);
    const job = { remaining: delay, started: 0, callback };
    this.jobs.set(name, job);
    if (!this.paused) this.start(name);
  }
  start(name) {
    const job = this.jobs.get(name);
    job.started = performance.now();
    job.id = window.setTimeout(() => {
      this.jobs.delete(name);
      job.callback();
    }, job.remaining);
  }
  pause() {
    if (this.paused) return;
    this.paused = true;
    for (const job of this.jobs.values()) {
      if (job.id !== void 0) window.clearTimeout(job.id);
      job.remaining = Math.max(0, job.remaining - (performance.now() - job.started));
      job.id = void 0;
    }
  }
  resume() {
    if (!this.paused) return;
    this.paused = false;
    for (const name of this.jobs.keys()) this.start(name);
  }
  dispose() {
    for (const name of this.jobs.keys()) this.clear(name);
  }
}

const LONG_PRESS_MS = 450;
const MEMORY_LIMIT = 20;
const MEMORY_WINDOW_MS = 3e4;
const INTERACTION_LIMIT = 4;
class InteractionMemory {
  states = /* @__PURE__ */ new Map();
  active(key, now) {
    const state = this.states.get(key);
    return state && now >= state.lastAt && now - state.lastAt < MEMORY_WINDOW_MS ? state : void 0;
  }
  remember(key, state) {
    this.states.delete(key);
    this.states.set(key, state);
    if (this.states.size > MEMORY_LIMIT) this.states.delete(this.states.keys().next().value);
  }
  record(key, now) {
    const state = this.active(key, now) ?? { lastAt: now, count: 0 };
    state.lastAt = now;
    state.count = Math.min(INTERACTION_LIMIT, state.count + 1);
    this.remember(key, state);
  }
  respond(key, now) {
    const state = this.active(key, now) ?? { lastAt: now, count: 0 };
    const duration = this.duration(state, now);
    if (duration === null) return null;
    const pose = state.lastPose === "wave" ? "jump" : "wave";
    state.lastResponseAt = now;
    state.lastPose = pose;
    this.remember(key, state);
    return { pose, duration };
  }
  /** Touch previews reserve nothing until release; attention keeps explicit pose order. */
  attend(key, now, commit = true) {
    const prior = this.active(key, now) ?? { lastAt: now, count: 0 };
    const next = { ...prior, lastAt: now, count: Math.min(INTERACTION_LIMIT, prior.count + 1) };
    const duration = this.duration(next, now);
    if (duration === null) return null;
    if (commit) this.remember(key, { ...next, lastResponseAt: now });
    return { duration };
  }
  duration(state, now) {
    const repeated = Math.max(0, state.count - 1);
    const cooldown = Math.min(6e3, 2400 + repeated * 1200);
    if (state.lastResponseAt !== void 0 && now - state.lastResponseAt < cooldown) return null;
    return Math.max(700, 1200 - repeated * 150);
  }
  landingDelay(key, now) {
    const count = this.active(key, now)?.count ?? 0;
    return Math.min(1350, 900 + Math.max(0, count - 1) * 150);
  }
}

function supportsRest(pack, mappings) {
  const resolved = resolveAction(pack, "sleep", void 0, false, { mappings, mappingKey: "stage.doze" });
  const indices = resolved.action.frames.map((frame) => pack.frames[frame]);
  const idle = pack.actions.idle?.frames.map((frame) => pack.frames[frame]) ?? [pack.frames.idle];
  return resolved.key !== "idle" && indices.length > 0 && indices.every((index) => Number.isInteger(index) && index >= 0 && index < pack.grid.cols * pack.grid.rows) && indices.some((index) => !idle.includes(index));
}
function activityRadius(height, mobile) {
  return Math.max(48, Math.min(260, height * (mobile ? 0.9 : 1.8)));
}
const VISIT_WINDOW = 45e3;
const EPISODE_WINDOW = 25e3;
const INTERACTION_WINDOW = 16e3;
class ActivityPolicy {
  visits = [];
  remaining = 0;
  episodeUntil = 0;
  excitedUntil = 0;
  nearbyOrigin = null;
  boostPending = false;
  stepsTaken = 0;
  prune(now) {
    this.visits = this.visits.filter((visit) => now >= visit.at && now - visit.at < VISIT_WINDOW);
    if (now >= this.episodeUntil) this.remaining = 0;
    if (now >= this.excitedUntil) {
      this.nearbyOrigin = null;
      this.boostPending = false;
    }
  }
  continuing(now) {
    this.prune(now);
    return this.remaining > 0;
  }
  excited(now) {
    this.prune(now);
    return this.nearbyOrigin !== null;
  }
  delay(now, random) {
    const short = this.continuing(now) || this.excited(now) && this.boostPending;
    return short ? 800 + random() * 1e3 : 6e3 + random() * 8e3;
  }
  begin(now, random) {
    if (this.continuing(now)) return;
    this.remaining = this.excited(now) ? 3 : random() < 0.5 ? 2 : 3;
    this.episodeUntil = now + EPISODE_WINDOW;
    this.stepsTaken = 0;
    this.boostPending = false;
  }
  remainingTime(now) {
    this.prune(now);
    return this.remaining > 0 ? Math.max(0, this.episodeUntil - now) : 0;
  }
  interact(point, now) {
    this.cancel();
    this.nearbyOrigin = { ...point };
    this.excitedUntil = now + INTERACTION_WINDOW;
    this.boostPending = true;
  }
  arrived(from, to, now) {
    this.prune(now);
    this.visits.push({ ...from, at: now }, { ...to, at: now });
    this.visits = this.visits.slice(-6);
    this.remaining = Math.max(0, this.remaining - 1);
    this.stepsTaken++;
  }
  cancel() {
    this.remaining = 0;
    this.episodeUntil = 0;
    this.excitedUntil = 0;
    this.nearbyOrigin = null;
    this.boostPending = false;
    this.stepsTaken = 0;
  }
  reset() {
    this.cancel();
    this.visits = [];
  }
  upwardTarget(area, candidates, now) {
    this.prune(now);
    if (area.free) return null;
    const radius = activityRadius(area.height, area.mobile);
    const riseLimit = Math.min(area.mobile ? 240 : 360, area.height * (area.mobile ? 1.6 : 2));
    let selected = null;
    let lowestPenalty = Infinity;
    for (const point of candidates) {
      const rise = area.current.y - point.y;
      if (rise < 12 || rise > riseLimit || Math.abs(point.x - area.current.x) > radius) continue;
      if (this.nearbyOrigin && (Math.abs(point.x - this.nearbyOrigin.x) > radius || Math.abs(point.y - this.nearbyOrigin.y) > radius))
        continue;
      const avoidRadius = Math.max(24, area.height * 0.5);
      const penalty = this.visits.reduce(
        (sum, visit) => sum + Math.max(0, 1 - Math.hypot(point.x - visit.x, point.y - visit.y) / avoidRadius),
        0
      ) + Math.hypot(point.x - area.current.x, rise) / 1e5;
      if (penalty < lowestPenalty) {
        lowestPenalty = penalty;
        selected = point;
      }
    }
    return selected;
  }
  target(area, now, random) {
    this.prune(now);
    const nearby = area.mobile || this.stepsTaken > 0 || this.excited(now) || random() < 0.8;
    const origin = this.nearbyOrigin ?? area.current;
    const radius = activityRadius(area.height, area.mobile);
    const minDistance = Math.max(12, Math.min(area.mobile ? 24 : 40, area.height * 0.25));
    const bounds = nearby ? {
      x: [Math.max(area.bounds.x[0], origin.x - radius), Math.min(area.bounds.x[1], origin.x + radius)],
      y: [Math.max(area.bounds.y[0], origin.y - radius), Math.min(area.bounds.y[1], origin.y + radius)]
    } : { x: [...area.bounds.x], y: [...area.bounds.y] };
    if (area.span) {
      if (area.current.x <= area.span[0]) bounds.x[1] = Math.min(bounds.x[1], area.span[0]);
      else if (area.current.x >= area.span[1]) bounds.x[0] = Math.max(bounds.x[0], area.span[1]);
    }
    if (bounds.x[0] > bounds.x[1] || bounds.y[0] > bounds.y[1]) return null;
    const candidates = [];
    for (let attempt = 0; attempt < 4; attempt++) {
      if (area.free) {
        const point = pickFreeTarget(random, area.current, bounds, minDistance);
        if (point) candidates.push(point);
      } else {
        const x = pickWalkTarget(random, area.current.x, bounds.x, area.span, minDistance);
        if (x !== null) candidates.push({ x, y: area.current.y });
      }
    }
    candidates.push({ x: bounds.x[0], y: area.current.y }, { x: bounds.x[1], y: area.current.y });
    if (area.free) candidates.push({ x: area.current.x, y: bounds.y[0] }, { x: area.current.x, y: bounds.y[1] });
    let selected = null;
    let lowestPenalty = Infinity;
    const seen = /* @__PURE__ */ new Set();
    for (const point of candidates) {
      const signature = `${point.x}:${point.y}`;
      if (seen.has(signature)) continue;
      seen.add(signature);
      if (point.x < bounds.x[0] || point.x > bounds.x[1] || point.y < bounds.y[0] || point.y > bounds.y[1] || Math.hypot(point.x - area.current.x, point.y - area.current.y) < minDistance || isBlocked(point.x, area.span) || !area.allowed(point))
        continue;
      const avoidRadius = Math.max(24, area.height * 0.5);
      const penalty = this.visits.reduce(
        (sum, visit) => sum + Math.max(0, 1 - Math.hypot(point.x - visit.x, point.y - visit.y) / avoidRadius),
        0
      );
      if (penalty < lowestPenalty) {
        lowestPenalty = penalty;
        selected = point;
      }
    }
    return selected;
  }
}

const ATTENTION_DWELL_MS = 350;
const ATTENTION_LEAVE_MS = 300;
const TOUCH_LOOK_MS = 700;
const GAZE_INTERVAL_MS = 120;
const LOOK_DIRECTIONS = [
  "000",
  "022-5",
  "045",
  "067-5",
  "090",
  "112-5",
  "135",
  "157-5",
  "180",
  "202-5",
  "225",
  "247-5",
  "270",
  "292-5",
  "315",
  "337-5"
];
function supportsLookDirections(pack) {
  return pack.codex_version === "v2" && LOOK_DIRECTIONS.every((direction) => {
    const action = pack.actions[`look-${direction}`];
    const index = action?.frames.length === 1 ? pack.frames[action.frames[0]] : void 0;
    return !!action && !action.loop && Number.isInteger(index) && index >= 0 && index < pack.grid.cols * pack.grid.rows;
  });
}
class ProximityTracker {
  anchor = null;
  entered = false;
  consumed = false;
  sample(point, rect, requireStillness = true) {
    const radius = Math.min(96, Math.max(48, rect.height / 2));
    const dx = Math.max(rect.x - point.x, 0, point.x - rect.x - rect.width);
    const dy = Math.max(rect.y - point.y, 0, point.y - rect.y - rect.height);
    if (!Number.isFinite(point.x + point.y) || Math.hypot(dx, dy) > radius + (this.entered ? 16 : 0)) {
      this.reset();
      return "leave";
    }
    this.entered = true;
    if (this.consumed) return "near";
    if (!this.anchor || requireStillness && Math.hypot(point.x - this.anchor.x, point.y - this.anchor.y) > 8) {
      this.anchor = point;
      return "arm";
    }
    return "near";
  }
  consume() {
    this.consumed = true;
  }
  reset() {
    this.anchor = null;
    this.entered = false;
    this.consumed = false;
  }
}
class GazeTracker {
  direction = null;
  changedAt = 0;
  select(point, origin, now) {
    const dx = point.x - origin.x, dy = point.y - origin.y;
    if (!Number.isFinite(dx + dy + now)) return this.action();
    if (Math.hypot(dx, dy) < 12) return this.action();
    const degrees = (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
    if (this.direction !== null) {
      const delta = Math.abs((degrees - this.direction * 22.5 + 540) % 360 - 180);
      if (delta <= 17.25 || this.remainingDelay(now) > 0) return this.action();
    }
    this.direction = Math.round(degrees / 22.5) % 16;
    this.changedAt = now;
    return this.action();
  }
  action() {
    return this.direction === null ? null : `look-${LOOK_DIRECTIONS[this.direction]}`;
  }
  remainingDelay(now) {
    return this.direction === null ? 0 : Math.max(0, GAZE_INTERVAL_MS - (now - this.changedAt));
  }
  reset() {
    this.direction = null;
    this.changedAt = 0;
  }
}

const SURFACE_SELECTOR = '.v-card, .v-sheet, .v-overlay__content, [role="dialog"]';
const MAX_SURFACE_CANDIDATES = 400;
function measureSurface(el, scope = null) {
  if (!el.isConnected) return null;
  const rect = el.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;
  const origin = scope?.getBoundingClientRect();
  return {
    left: rect.left - (origin?.left ?? 0),
    top: rect.top - (origin?.top ?? 0),
    right: rect.right - (origin?.left ?? 0)
  };
}
function surfaceVisible(el) {
  const style = window.getComputedStyle(el);
  return style.pointerEvents !== "none" && style.visibility !== "hidden" && style.display !== "none";
}
function surfaceUnobstructed(el, box, layer, viewportWidth, scope = null) {
  if (typeof document.elementsFromPoint !== "function") return true;
  const left = Math.max(box.left, 0);
  const right = Math.min(box.right, viewportWidth);
  if (right <= left) return false;
  const origin = scope?.getBoundingClientRect();
  const hit = document.elementsFromPoint((left + right) / 2 + (origin?.left ?? 0), box.top + 2 + (origin?.top ?? 0)).find((item) => !layer?.contains(item));
  return !!hit && (hit === el || el.contains(hit));
}
function querySurfaces(layer, viewport, charHeight, panel, scope = null) {
  const floor = floorLine(viewport);
  const candidates = [];
  for (const el of Array.from((scope ?? document).querySelectorAll(SURFACE_SELECTOR))) {
    const box = measureSurface(el, scope);
    if (!box || box.right <= 0 || box.left >= viewport.width || box.top >= floor) continue;
    if (!standable(box, viewport, charHeight, panel)) continue;
    if (layer && (layer.contains(el) || el.contains(layer))) continue;
    candidates.push({ ...box, el });
    if (candidates.length >= MAX_SURFACE_CANDIDATES) break;
  }
  return candidates.filter(
    (candidate) => surfaceVisible(candidate.el) && surfaceUnobstructed(candidate.el, candidate, layer, viewport.width, scope)
  );
}
const BOTTOM_FLOOR_GAP = 8;
function bottomFixedFloor(layer, viewport) {
  const floor = floorLine(viewport);
  if (typeof document.elementsFromPoint !== "function") return floor;
  const left = viewport.safeArea.left;
  const width = viewport.width - viewport.safeArea.right - left;
  const seen = /* @__PURE__ */ new Set();
  let result = floor;
  for (const ratio of [0.1, 0.5, 0.9]) {
    for (const depth of [2, 24, 60, 120, 180]) {
      const y = floor - depth;
      if (y <= viewport.safeArea.top) continue;
      const hit = document.elementsFromPoint(left + width * ratio, y).find((item) => !layer?.contains(item));
      if (!hit || !surfaceVisible(hit)) continue;
      let el = hit;
      for (let level = 0; el && level < 8; level += 1, el = el.parentElement) {
        if (seen.has(el)) break;
        seen.add(el);
        if (layer && el.contains(layer)) continue;
        const rect = el.getBoundingClientRect();
        if (rect.width < width * 0.5 || rect.height <= 0 || rect.height > Math.min(200, (floor - viewport.safeArea.top) * 0.35) || rect.bottom < floor - 96 || rect.top >= floor || rect.top <= viewport.safeArea.top)
          continue;
        const style = window.getComputedStyle(el);
        if ((style.position === "fixed" || style.position === "sticky") && style.visibility !== "hidden" && style.display !== "none") {
          result = Math.min(result, rect.top - BOTTOM_FLOOR_GAP);
        }
      }
    }
  }
  return result;
}
const NEARBY_SURFACE_ROWS = 4;
function surfacesNear(layer, viewport, charHeight, panel, columns, scope = null) {
  if (scope) return querySurfaces(layer, viewport, charHeight, panel, scope);
  if (typeof document.elementsFromPoint !== "function") return [];
  const top = viewport.safeArea.top + charHeight;
  const bottom = floorLine(viewport);
  const seen = /* @__PURE__ */ new Set();
  const result = [];
  for (const x of columns) {
    if (x < 0 || x >= viewport.width) continue;
    for (let row = 0; row < NEARBY_SURFACE_ROWS; row += 1) {
      const y = top + (row + 0.5) * (bottom - top) / NEARBY_SURFACE_ROWS;
      const hit = document.elementsFromPoint(x, y).find((item) => !layer?.contains(item));
      const el = hit?.closest(SURFACE_SELECTOR);
      if (!el || seen.has(el)) continue;
      seen.add(el);
      if (layer && el.contains(layer)) continue;
      const box = measureSurface(el, scope);
      if (!box || !standable(box, viewport, charHeight, panel) || !surfaceVisible(el)) continue;
      if (!surfaceUnobstructed(el, box, layer, viewport.width)) continue;
      result.push({ ...box, el });
    }
  }
  return result;
}
const CONTROL_SELECTOR = 'a, button, [role="button"], input, textarea, select, .v-btn, .v-card--link, .v-list-item, [tabindex]:not([tabindex="-1"])';
const SAMPLE_COLS = 3;
const SAMPLE_ROWS = 4;
function samplePoints(rect, cols = SAMPLE_COLS, rows = SAMPLE_ROWS) {
  const points = [];
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      points.push({ x: rect.x + (col + 0.5) * rect.width / cols, y: rect.y + (row + 0.5) * rect.height / rows });
    }
  }
  return points;
}
function coversControlAt(rect, layer, viewport, standingOn, bodyArea = rect.width * rect.height, scope = null) {
  for (const control of eachControlUnder(rect, layer, viewport, standingOn, scope)) {
    if (coversAny(rect, [control], bodyArea)) return true;
  }
  return false;
}
function* eachControlUnder(rect, layer, viewport, standingOn, scope = null) {
  if (typeof document.elementsFromPoint !== "function") return;
  const viewportArea = viewport.width * viewport.height;
  const origin = scope?.getBoundingClientRect();
  const seen = /* @__PURE__ */ new Set();
  for (const point of samplePoints(rect)) {
    if (point.x < 0 || point.y < 0 || point.x >= viewport.width || point.y >= viewport.height) continue;
    const hit = document.elementsFromPoint(point.x + (origin?.left ?? 0), point.y + (origin?.top ?? 0)).find((item) => !layer?.contains(item));
    const control = hit?.closest(CONTROL_SELECTOR);
    if (!control || seen.has(control) || scope && !scope.contains(control)) continue;
    seen.add(control);
    if (layer && control.contains(layer)) continue;
    if (standingOn && (control === standingOn || control.contains(standingOn))) continue;
    const box = control.getBoundingClientRect();
    if (box.width * box.height > viewportArea / 2) continue;
    yield { x: box.left - (origin?.left ?? 0), y: box.top - (origin?.top ?? 0), width: box.width, height: box.height };
  }
}

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,renderSlot:_renderSlot,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,normalizeClass:_normalizeClass,normalizeStyle:_normalizeStyle,createElementVNode:_createElementVNode,createCommentVNode:_createCommentVNode,vShow:_vShow,withModifiers:_withModifiers,withDirectives:_withDirectives} = await importShared('vue');

const _hoisted_1 = ["data-pose", "data-motion", "data-reaction", "data-greeting", "data-greeting-round", "data-attention", "data-gaze", "data-roam", "data-movement", "data-peek-edge", "data-peek-phase"];
const _hoisted_2 = ["aria-label"];
const _hoisted_3 = ["data-frame"];
const _hoisted_4 = ["src", "data-pose", "onLoad", "onError"];
const {computed,onBeforeUnmount,onMounted,ref,useSlots,watch} = await importShared('vue');
const BASE_HEIGHT = 120;
const BASE_WALK_SPEED = 70;
const FREE_SPEED_RATIO = 0.6;
const GRAVITY = 2600;
const DRAG_THRESHOLD = 6;
const SIT_DURATION = 900;
const DOZE_AFTER = 9e4;
const PEEK_SPEED = 1.8;
const HOP_LIFT_RATIO = 0.5;
const MAX_OTHER_SURFACES = 3;
const OTHER_SURFACE_CANDIDATES = 4;
const DEFAULT_RATIO = 0.88;
const SURFACE_CHECK_INTERVAL = 500;
const DROP_CLEAR_DELAY = 1500;
const RESIZE_CLEAR_DELAY = 300;
const SAVE_THROTTLE = 3e4;
const CLEARANCE_POLL_EVERY = 4;
const FRAME_RETRY_AFTER = 5e3;
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "AgentPet",
  props: {
    agent: { default: null },
    pet: { default: null },
    api: { default: null },
    pluginId: { default: "" },
    sourcePluginId: { default: "" },
    characterName: { default: "小映" },
    aspectRatio: { default: 0 },
    peekEye: {},
    lookDirections: { type: Boolean },
    artworkReady: { type: Boolean },
    greetingPlayback: {},
    restAvailable: { type: Boolean },
    previewRoot: { default: null },
    settingsOverride: {},
    previewMaxSize: {},
    previewPose: {},
    previewPeekEdge: {},
    previewPeekAngle: {},
    calibrationOverride: {},
    showCalibration: { type: Boolean }
  },
  emits: ["pack-ready", "load-state"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const ownFrames = !useSlots().default;
    const rootEl = ref(null);
    const settings = ref({ ...DEFAULT_SETTINGS });
    const imageAspect = ref(198 / 240);
    const ownCalibration = ref(builtinDefaultCalibration("ying"));
    const effectiveCalibration = computed(() => parseCalibration(props.calibrationOverride ?? ownCalibration.value));
    const ownLayout = computed(() => calibrationLayout(effectiveCalibration.value, imageAspect.value));
    const aspect = computed(() => props.aspectRatio > 0 ? props.aspectRatio : ownLayout.value.aspectRatio);
    const ownGuides = computed(
      () => ["eye", ...LANDMARKS].flatMap((key) => {
        const point = calibrationPoint(effectiveCalibration.value, key);
        return point ? [{ key, ...point }] : [];
      })
    );
    const x = ref(0);
    const y = ref(0);
    const peekProgress = ref(0);
    const peekRevealing = ref(false);
    const peekTiltProgress = ref(0);
    const peekEdge = ref(null);
    const peekPhase = ref(null);
    const layoutRevision = ref(0);
    const facingLeft = ref(false);
    const ownEye = computed(() => {
      const face = calibrationEye(effectiveCalibration.value);
      return facingLeft.value ? mirrorFace(face) : face;
    });
    const motion = ref("idle");
    const walkPhase = ref(0);
    const transient = ref(null);
    const reaction = ref(null);
    const attention = ref(null);
    const gazeAction = ref(null);
    const sustained = ref(null);
    const dozing = ref(false);
    const blinking = ref(false);
    const ready = ref(false);
    const rising = ref(false);
    const available = ref(true);
    const isMobile = ref(false);
    const animationActive = ref(false);
    let hostState = null;
    let pendingHostState = null;
    let bottomFloor = null;
    let documentVisible = typeof document === "undefined" || document.visibilityState !== "hidden";
    let editorPaused = false;
    let pendingViewportResize = false;
    let rafId = 0;
    let lastFrame = 0;
    let anchorFrame = 0;
    let lastAnchor = null;
    let walkTarget = null;
    let walkDistance = 0;
    let velocity = 0;
    let bounced = false;
    let fallTarget = null;
    let peekTarget = 0;
    let peekPinned = false;
    let sheltering = false;
    let pendingShelter = false;
    let hopVx = 0;
    let hopTargetX = null;
    let activityHop = false;
    let fixedPosition = null;
    let lastSaved = "";
    let lastSaveAt = 0;
    let saveOnLand = false;
    let suppressedPointer = null;
    let pendingDropReaction = null;
    let pendingPeek = null;
    let pendingStepOff = false;
    let surface = null;
    let manualSurface = null;
    let surfaceFrame = 0;
    let surfaceObserver = null;
    let surfacePoll = 0;
    let standPollTicks = 0;
    let disposed = false;
    let droppedByUser = false;
    let initialPlacement = true;
    let press = null;
    const timers = new PausableTimers();
    const interactionMemory = new InteractionMemory();
    const activityPolicy = new ActivityPolicy();
    let activityOrigin = null;
    const proximity = new ProximityTracker();
    const gaze = new GazeTracker();
    let nearbyPointer = null;
    const cleanups = [];
    const startup = new AbortController();
    let settingsRevision = 0;
    const charHeight = computed(() => {
      const height = BASE_HEIGHT * effectiveScale(settings.value.scale, isMobile.value);
      const fit = props.previewRoot ? props.previewMaxSize : void 0;
      return fit ? Math.min(height, Math.max(1, fit.height), Math.max(1, fit.width) / aspect.value) : height;
    });
    const charWidth = computed(() => charHeight.value * aspect.value);
    const previewEdge = computed(() => props.previewRoot ? props.previewPeekEdge ?? null : null);
    const activePeekEdge = computed(() => previewEdge.value ?? peekEdge.value);
    const settledPeek = computed(
      () => !previewEdge.value && motion.value === "peek" && peekPhase.value === "look" && peekProgress.value === 1
    );
    const greeting = useStartupGreeting({
      allowed: () => !disposed && !props.previewRoot && available.value && visible() && motionAllowed() && hostIdle() && !transient.value && !sustained.value && !press && !activePeekEdge.value && !sheltering,
      ready: () => ready.value && motion.value === "idle" && (ownFrames ? frameStatus.value.idle === "loaded" && frameStatus.value.wave === "loaded" : props.artworkReady === true),
      stable: () => `${x.value}:${y.value}:${charWidth.value}:${charHeight.value}`,
      playback: () => ownFrames ? { duration: SINGLE_GREETING_MS, pause: GREETING_PAUSE_MS } : props.greetingPlayback ?? null,
      finished: () => scheduleBehavior()
    });
    const pose = computed(
      () => activePeekEdge.value ? settledPeek.value && animationActive.value && blinking.value ? "blink" : "alert" : props.previewRoot && props.previewPose ? props.previewPose : resolvePose({
        motion: motion.value,
        walkPhase: walkPhase.value,
        transient: transient.value ?? reaction.value ?? (greeting.phase.value === "wave" ? "wave" : greeting.phase.value === "pause" ? "idle" : attention.value && !gazeAction.value ? "wave" : null),
        sustained: sustained.value,
        dozing: dozing.value,
        blinking: blinking.value,
        rising: rising.value
      })
    );
    const label = computed(
      () => available.value ? `打开助手（${props.characterName}）` : `${props.characterName}（助手未启用）`
    );
    watch(
      () => props.aspectRatio,
      () => {
        if (ready.value) relayout();
      }
    );
    watch([charHeight, charWidth], () => {
      if (ready.value && props.previewRoot) relayout();
    });
    watch(
      [() => props.peekEye, previewEdge, ownEye],
      () => {
        if (ready.value) relayout();
      },
      { deep: true }
    );
    watch(
      effectiveCalibration,
      () => {
        if (ready.value && ownFrames) relayout();
      },
      { deep: true }
    );
    const frameStatus = ref(
      Object.fromEntries(POSES.map((name) => [name, "pending"]))
    );
    const restAvailable = computed(() => ownFrames ? frameStatus.value.doze === "loaded" : props.restAvailable === true);
    watch(restAvailable, (supported) => {
      if (!supported && dozing.value) {
        cancelRest();
        scheduleRest();
        scheduleBehavior();
      }
    });
    const frameSrc = ref(
      Object.fromEntries(POSES.map((name) => [name, frameUrl(name)]))
    );
    const displayed = ref(null);
    const failedAt = /* @__PURE__ */ new Map();
    const retries = /* @__PURE__ */ new Map();
    function syncDisplayed() {
      const target = pose.value;
      if (frameStatus.value[target] === "loaded") {
        displayed.value = target;
        return;
      }
      const failed = failedAt.get(target);
      if (frameStatus.value[target] === "error" && failed !== void 0 && Date.now() - failed >= FRAME_RETRY_AFTER) {
        const attempt = (retries.get(target) ?? 0) + 1;
        retries.set(target, attempt);
        failedAt.delete(target);
        frameStatus.value[target] = "pending";
        frameSrc.value[target] = `${frameUrl(target)}?retry=${attempt}`;
      }
      if (displayed.value && frameStatus.value[displayed.value] !== "loaded") displayed.value = null;
    }
    watch(pose, syncDisplayed);
    function onFrameLoad(name, event) {
      frameStatus.value[name] = "loaded";
      failedAt.delete(name);
      if (name === "idle") {
        const image = event.target;
        if (image.naturalWidth && image.naturalHeight) {
          imageAspect.value = image.naturalWidth / image.naturalHeight;
          relayout();
        }
      }
      if (name === pose.value) displayed.value = name;
    }
    function onFrameError(name) {
      if (name === "idle" || name === "wave") greeting.cancel();
      frameStatus.value[name] = "error";
      failedAt.set(name, Date.now());
      if (displayed.value === name) displayed.value = null;
      syncDisplayed();
    }
    const drawing = computed(() => {
      void layoutRevision.value;
      const edge = activePeekEdge.value;
      const view = peekViewport();
      const position = previewEdge.value ? peekHome({ x: x.value, y: y.value }, view, size(), previewEdge.value) : { x: x.value, y: y.value };
      const eye = props.peekEye === void 0 ? ownEye.value : props.peekEye;
      return peekLayout(
        position,
        size(),
        view,
        edge,
        previewEdge.value ? 1 : peekProgress.value,
        eye,
        !!previewEdge.value || peekRevealing.value,
        previewEdge.value ? 1 : peekTiltProgress.value,
        previewEdge.value && props.previewPeekAngle !== void 0 ? props.previewPeekAngle : normalizePeekAngles(settings.value.peek_angles)[activePeekEdge.value ?? "bottom"]
      );
    });
    const buttonStyle = computed(() => ({
      width: `${drawing.value.hit.width}px`,
      height: `${drawing.value.hit.height}px`,
      transform: `translate3d(${drawing.value.hit.x}px, ${drawing.value.hit.y}px, 0)`
    }));
    const clipStyle = computed(() => ({
      left: `${drawing.value.visible.x - drawing.value.hit.x}px`,
      top: `${drawing.value.visible.y - drawing.value.hit.y}px`,
      width: `${drawing.value.visible.width}px`,
      height: `${drawing.value.visible.height}px`
    }));
    const artworkStyle = computed(() => ({
      left: `${drawing.value.artwork.x - drawing.value.visible.x}px`,
      top: `${drawing.value.artwork.y - drawing.value.visible.y}px`,
      width: `${drawing.value.artwork.width}px`,
      height: `${drawing.value.artwork.height}px`,
      transform: `rotate(${drawing.value.artwork.rotation}deg)`
    }));
    function setTimer(name, delay, callback) {
      timers.set(name, delay, callback);
    }
    function clearTimer(name) {
      timers.clear(name);
    }
    function randomBetween(min, max) {
      return min + Math.random() * (max - min);
    }
    function fixed() {
      return settings.value.movement === "fixed";
    }
    function rememberFixedPosition() {
      const view = freeBounds(viewport(), ...sizePair());
      fixedPosition = { xRatio: xToRatio(x.value, view.x), yRatio: xToRatio(y.value, view.y) };
    }
    function placeFixed() {
      const view = freeBounds(viewport(), ...sizePair());
      x.value = ratioToX(fixedPosition?.xRatio ?? DEFAULT_RATIO, view.x);
      y.value = ratioToX(fixedPosition?.yRatio ?? 1, view.y);
      const point = avoidPanel({ x: x.value, y: y.value }, hostState?.panelRect ?? null, viewport(), size());
      x.value = point.x;
      y.value = point.y;
      queueAnchor();
    }
    function resetMotion() {
      cancelActivity();
      clearAttention();
      stopLoop();
      for (const name of ["behavior", "peek", "peek-pause", "landing-peek", "sit", "clearance"]) clearTimer(name);
      walkTarget = null;
      walkPhase.value = 0;
      fallTarget = null;
      hopVx = 0;
      hopTargetX = null;
      velocity = 0;
      rising.value = false;
      pendingPeek = null;
      pendingStepOff = false;
      pendingShelter = false;
      sheltering = false;
      peekProgress.value = 0;
      peekTiltProgress.value = 0;
      peekEdge.value = null;
      peekPhase.value = null;
      peekPinned = false;
      peekTarget = 0;
      motion.value = "idle";
      detachSurface();
    }
    function pinHere() {
      resetMotion();
      rememberFixedPosition();
      placeFixed();
      if (saveOnLand) {
        saveOnLand = false;
        requestSave();
      }
      finishDropReaction();
    }
    function roam() {
      return settings.value.roam;
    }
    function viewport() {
      const view = readViewport(hostState, !props.previewRoot);
      if (bottomFloor === null || props.previewRoot) return view;
      return {
        ...view,
        safeArea: { ...view.safeArea, bottom: Math.max(view.safeArea.bottom, view.height - bottomFloor) }
      };
    }
    function refreshBottomFloor() {
      const next = !props.previewRoot ? bottomFixedFloor(rootEl.value, readViewport(hostState)) : null;
      const changed = next !== bottomFloor;
      bottomFloor = next;
      return changed;
    }
    function peekViewport() {
      const view = readViewport(hostState, !props.previewRoot);
      if (bottomFloor === null || props.previewRoot || bottomFloor >= floorLine(view)) return view;
      return {
        ...view,
        safeArea: {
          ...view.safeArea,
          bottom: Math.max(view.safeArea.bottom, view.height - bottomFloor - BOTTOM_FLOOR_GAP)
        }
      };
    }
    function placePeek() {
      if (!peekEdge.value) return;
      const point = peekHome({ x: x.value, y: y.value }, peekViewport(), size(), peekEdge.value);
      x.value = point.x;
      y.value = point.y;
    }
    function ground() {
      return groundTop(viewport(), charHeight.value);
    }
    function standY() {
      return surface ? surface.top - charHeight.value : ground();
    }
    function size() {
      return { width: charWidth.value, height: charHeight.value };
    }
    function bounds() {
      if (roam() === "free") return freeBounds(viewport(), charWidth.value, charHeight.value).x;
      if (surface) return surfaceXBounds(surface, viewport(), charWidth.value);
      return xBounds(viewport(), charWidth.value);
    }
    function panelSpan() {
      if (roam() === "free") return null;
      return blockedSpan(hostState?.panelRect ?? null, standY(), charWidth.value, charHeight.value);
    }
    function motionAllowed() {
      if (hostState) return hostState.motionAllowed;
      return !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    }
    function visible() {
      return !editorPaused && documentVisible && (hostState?.pageVisible ?? true);
    }
    function onGround() {
      return motion.value !== "drag" && motion.value !== "fall";
    }
    function onFloor() {
      return roam() !== "free" && !surface;
    }
    function currentRect() {
      return drawing.value.visible;
    }
    function reportAnchor() {
      anchorFrame = 0;
      if (disposed || !ready.value || editorPaused) return;
      const rect = currentRect();
      if (sameRect(rect, lastAnchor)) return;
      lastAnchor = rect;
      if (attention.value === "mouse") updateNearbyAttention();
      props.pet?.setBubbleAnchor?.(rect);
    }
    function queueAnchor() {
      if (editorPaused || anchorFrame || rafId) return;
      anchorFrame = window.requestAnimationFrame(reportAnchor);
    }
    function needsLoop() {
      if (motion.value === "walk" || motion.value === "fall") return true;
      return motion.value === "peek" && (peekPhase.value === "tilt" || peekProgress.value !== peekTarget);
    }
    function ensureLoop() {
      if (rafId || disposed || !visible() || !needsLoop()) return;
      if (anchorFrame) {
        window.cancelAnimationFrame(anchorFrame);
        anchorFrame = 0;
      }
      lastFrame = 0;
      rafId = window.requestAnimationFrame(tick);
    }
    function stopLoop() {
      if (rafId) window.cancelAnimationFrame(rafId);
      rafId = 0;
    }
    function tick(timestamp) {
      rafId = 0;
      const dt = lastFrame ? Math.min((timestamp - lastFrame) / 1e3, 0.05) : 1 / 60;
      lastFrame = timestamp;
      if (motion.value === "walk") stepWalk(dt);
      else if (motion.value === "fall") stepFall(dt);
      else if (motion.value === "peek") stepPeek(dt);
      clearPanelOverlap();
      reportAnchor();
      if (!rafId && needsLoop() && visible()) rafId = window.requestAnimationFrame(tick);
    }
    function stepWalk(dt) {
      if (!walkTarget) {
        finishWalk(false);
        return;
      }
      const speed = BASE_WALK_SPEED * settings.value.speed * (charHeight.value / BASE_HEIGHT) * (roam() === "free" ? FREE_SPEED_RATIO : 1);
      const dx = walkTarget.x - x.value;
      const dy = walkTarget.y === null ? 0 : walkTarget.y - y.value;
      const distance = Math.hypot(dx, dy);
      const step = speed * dt;
      const arrived = distance <= step;
      const nextX = arrived ? walkTarget.x : x.value + dx / distance * step;
      const nextY = arrived || walkTarget.y === null ? walkTarget.y ?? y.value : y.value + dy / distance * step;
      if (isBlocked(nextX, panelSpan())) {
        finishWalk(false);
        return;
      }
      walkDistance += Math.hypot(nextX - x.value, nextY - y.value);
      walkPhase.value = walkFrame(walkDistance, charHeight.value);
      if (Math.abs(nextX - x.value) > 0.01) facingLeft.value = nextX < x.value;
      x.value = nextX;
      y.value = nextY;
      if (arrived) finishWalk();
    }
    function stepFall(dt) {
      const range = freeBounds(viewport(), ...sizePair());
      const target = clamp(fallTarget?.y ?? range.y[1], ...range.y);
      if (fallTarget && target !== fallTarget.y) fallTarget = { y: target, surface: null };
      if (hopTargetX !== null) hopTargetX = clamp(hopTargetX, ...range.x);
      velocity += GRAVITY * dt;
      y.value = clamp(y.value + velocity * dt, ...range.y);
      x.value = clamp(x.value + hopVx * dt, ...range.x);
      rising.value = velocity < 0;
      if (velocity < 0 || y.value < target) return;
      if (activityHop && fallTarget?.surface && !validHopLanding(fallTarget.surface, hopTargetX ?? x.value)) {
        const rejected = fallTarget.surface.el;
        activityHop = false;
        startFall(rejected);
        return;
      }
      y.value = target;
      if (!bounced && velocity > 500) {
        bounced = true;
        velocity = -velocity * 0.22;
        return;
      }
      land(true);
    }
    function stepPeek(dt) {
      if (peekPhase.value === "tilt") {
        peekTiltProgress.value = Math.min(1, peekTiltProgress.value + dt / PEEK_TILT_SECONDS);
        if (peekTiltProgress.value === 1) {
          peekPhase.value = "look";
          peekTarget = 1;
        }
        return;
      }
      const step = (peekPhase.value === "look" ? (PEEK_TUCK - 1) / PEEK_RISE_SECONDS : PEEK_SPEED) * dt;
      peekProgress.value = peekProgress.value < peekTarget ? Math.min(peekTarget, peekProgress.value + step) : Math.max(peekTarget, peekProgress.value - step);
      if (peekProgress.value === PEEK_TUCK && peekPhase.value === "tuck") {
        peekPhase.value = "pause";
        setTimer("peek-pause", 420, () => {
          if (motion.value !== "peek" || peekPhase.value !== "pause") return;
          peekRevealing.value = true;
          peekPhase.value = peekEdge.value === "bottom" ? "tilt" : "look";
          peekTarget = peekEdge.value === "bottom" ? PEEK_TUCK : 1;
          ensureLoop();
        });
      }
      if (peekProgress.value === 0 && peekTarget === 0) {
        const fromSide = peekEdge.value === "left" || peekEdge.value === "right";
        peekEdge.value = null;
        peekPhase.value = null;
        peekPinned = false;
        motion.value = "idle";
        y.value = onFloor() ? ground() : y.value;
        finishActivityStep();
        if (fromSide && roam() !== "free" && !onFloor()) startFall();
        else scheduleBehavior();
      }
    }
    function startWalk(targetX, targetY = null, autonomous = false) {
      if (!autonomous) cancelActivity();
      if (greeting.phase.value) greeting.cancel();
      clearAttention();
      clearReaction();
      walkTarget = { x: targetX, y: targetY };
      walkDistance = 0;
      facingLeft.value = targetX < x.value;
      motion.value = "walk";
      ensureLoop();
    }
    function finishWalk(arrived = true) {
      walkTarget = null;
      walkPhase.value = 0;
      if (motion.value === "walk") motion.value = "idle";
      const peek = pendingPeek;
      const stepOff = pendingStepOff;
      pendingPeek = null;
      pendingStepOff = false;
      if (!arrived) cancelActivity();
      if (pendingShelter) {
        pendingShelter = false;
        beginShelter(false);
        return;
      }
      scheduleClearance(0);
      if (arrived && stepOff && surface) stepOffEdge();
      else if (arrived && peek) beginPeek(peek, false, false, activityOrigin !== null);
      else {
        finishActivityStep();
        scheduleBehavior();
      }
    }
    function beginPeek(edge = "bottom", pinned = false, instant = false, autonomous = false) {
      if (fixed()) return;
      cancelInteractionFeedback(autonomous);
      for (const name of ["behavior", "peek", "peek-pause", "landing-peek", "sit", "clearance"]) clearTimer(name);
      detachSurface();
      peekEdge.value = edge;
      peekPinned = pinned;
      x.value = nearestEdge(x.value, bounds());
      placePeek();
      facingLeft.value = x.value > (bounds()[0] + bounds()[1]) / 2;
      motion.value = "peek";
      const still = instant || !motionAllowed();
      peekRevealing.value = still;
      peekTiltProgress.value = still ? 1 : 0;
      peekPhase.value = still ? "look" : "tuck";
      peekProgress.value = still ? 1 : 0;
      peekTarget = still ? 1 : PEEK_TUCK;
      if (still) queueAnchor();
      else ensureLoop();
      schedulePeekExit();
      syncSurfacePoll();
    }
    function schedulePeekExit() {
      clearTimer("peek");
      if (!peekPinned && !sheltering && motionAllowed()) setTimer("peek", randomBetween(5e3, 8e3), endPeek);
    }
    function endPeek() {
      clearTimer("peek");
      clearTimer("peek-pause");
      if (motion.value !== "peek") return;
      peekPhase.value = "leave";
      peekTarget = 0;
      if (!motionAllowed()) {
        peekProgress.value = 0;
        stepPeek(0);
        queueAnchor();
      }
      ensureLoop();
      scheduleBehavior();
    }
    function settle() {
      cancelActivity();
      if (motion.value === "walk") {
        walkTarget = null;
        walkPhase.value = 0;
        motion.value = "idle";
      }
      if (motion.value === "peek" && !sheltering) {
        endPeek();
      }
      pendingPeek = null;
      pendingStepOff = false;
      pendingShelter = false;
    }
    function calm() {
      return !disposed && ready.value && available.value && hostIdle() && (ownFrames || props.artworkReady !== false) && motion.value === "idle" && !sheltering && !transient.value && !reaction.value && !attention.value && !greeting.active.value && !sustained.value && !press && !dozing.value && motionAllowed() && visible();
    }
    function cancelRest() {
      clearTimer("rest");
      dozing.value = false;
    }
    function cancelActivity() {
      const moving = activityOrigin !== null;
      const hopping = activityHop;
      activityHop = false;
      const resting = dozing.value;
      activityOrigin = null;
      activityPolicy.cancel();
      clearTimer("behavior");
      clearTimer("activity-end");
      cancelRest();
      if (resting) scheduleRest();
      if (!visible() || !motionAllowed()) clearTimer("doze");
      if (!moving) return;
      pendingPeek = null;
      pendingStepOff = false;
      if (motion.value === "walk") {
        walkTarget = null;
        walkPhase.value = 0;
        motion.value = "idle";
      } else if (motion.value === "fall" && hopping && !disposed) startFall();
      else if (motion.value === "peek" && !peekPinned && !sheltering && motionAllowed()) endPeek();
    }
    function beginActivity() {
      const now = Date.now();
      const continuing = activityPolicy.continuing(now);
      activityPolicy.begin(now, Math.random);
      if (!continuing)
        setTimer("activity-end", activityPolicy.remainingTime(now), () => {
          cancelActivity();
          scheduleBehavior();
        });
      activityOrigin = { x: x.value, y: y.value };
    }
    function finishActivityStep() {
      if (!activityOrigin) return;
      activityPolicy.arrived(activityOrigin, { x: x.value, y: y.value }, Date.now());
      activityOrigin = null;
      if (!activityPolicy.continuing(Date.now())) clearTimer("activity-end");
    }
    function activityArea() {
      const free = roam() === "free";
      const range = freeBounds(viewport(), ...sizePair());
      const view = viewport();
      return {
        current: { x: x.value, y: y.value },
        bounds: { x: bounds(), y: free ? range.y : [y.value, y.value] },
        free,
        height: charHeight.value,
        mobile: isMobile.value,
        span: panelSpan(),
        allowed: (point) => !intersectionArea(rectAt(point.x, point.y), hostState?.panelRect ?? { x: 0, y: 0, width: 0, height: 0 }) && !coversControlAt(
          rectAt(point.x, point.y),
          rootEl.value,
          view,
          surface?.el ?? null,
          charWidth.value * charHeight.value,
          props.previewRoot
        )
      };
    }
    function scheduleBehavior() {
      clearTimer("behavior");
      if (fixed() || !calm()) return;
      setTimer("behavior", activityPolicy.delay(Date.now(), Math.random), () => {
        if (fixed() || !calm()) return;
        const local = activityPolicy.continuing(Date.now()) || activityPolicy.excited(Date.now());
        const area = activityArea();
        const [min, max] = area.bounds.x;
        if (roam() === "surfaces" && Math.random() < 0.2 && tryActivityHop(area)) return;
        if (!local && roam() !== "free" && Math.random() < 0.25) {
          const side = Math.random() < 0.5 ? min : max;
          if (!isBlocked(side, area.span) && (!area.mobile || Math.abs(side - x.value) <= activityRadius(area.height, true)) && area.allowed({ x: side, y: y.value })) {
            if (surface) pendingStepOff = Math.random() < 0.5;
            else pendingPeek = Math.random() < 0.5 ? "bottom" : side === min ? "left" : "right";
            beginActivity();
            if (Math.abs(side - x.value) < 1) finishWalk();
            else startWalk(side, null, true);
            return;
          }
        }
        beginActivity();
        const target = activityPolicy.target(area, Date.now(), Math.random);
        if (!target) {
          cancelActivity();
          scheduleBehavior();
        } else startWalk(target.x, roam() === "free" ? target.y : null, true);
      });
    }
    function validHopLanding(target, left) {
      const box = measureSurface(target.el, props.previewRoot);
      const view = viewport();
      if (!box || !surfaceVisible(target.el) || !standable(box, view, charHeight.value, hostState?.panelRect ?? null) || Math.abs(box.top - target.top) > 1 || left < box.left || left + charWidth.value > box.right || !surfaceUnobstructed(target.el, box, rootEl.value, view.width, props.previewRoot))
        return false;
      const rect = rectAt(left, box.top - charHeight.value);
      return !intersectionArea(rect, hostState?.panelRect ?? { x: 0, y: 0, width: 0, height: 0 }) && !coversControlAt(rect, rootEl.value, view, target.el, charWidth.value * charHeight.value, props.previewRoot);
    }
    function tryActivityHop(area) {
      const view = viewport();
      const radius = activityRadius(charHeight.value, isMobile.value);
      const center = x.value + charWidth.value / 2;
      const candidates = [];
      const boxes = surfacesNear(
        rootEl.value,
        view,
        charHeight.value,
        hostState?.panelRect ?? null,
        [center, center - radius, center + radius],
        props.previewRoot
      ).filter((box) => box.el !== surface?.el && box.top < y.value + charHeight.value - 12).sort((a, b) => Math.abs(a.top - y.value - charHeight.value) - Math.abs(b.top - y.value - charHeight.value));
      for (const box of boxes.slice(0, MAX_OTHER_SURFACES)) {
        const range = xBounds(view, charWidth.value);
        const min = Math.max(range[0], box.left);
        const max = Math.min(range[1], box.right - charWidth.value);
        if (min > max) continue;
        const top = box.top - charHeight.value;
        const lift = Math.min(charHeight.value * HOP_LIFT_RATIO, Math.max(0, Math.min(y.value, top) - view.safeArea.top));
        for (const left of /* @__PURE__ */ new Set([clamp(x.value, min, max), (min + max) / 2, min, max])) {
          const corridor = {
            x: Math.min(x.value, left),
            y: top - lift,
            width: Math.abs(left - x.value) + charWidth.value,
            height: y.value + charHeight.value - top + lift
          };
          if (hostState?.panelRect && intersectionArea(corridor, hostState.panelRect)) continue;
          if (validHopLanding(box, left)) candidates.push({ x: left, y: top, surface: box });
        }
      }
      const target = activityPolicy.upwardTarget(area, candidates, Date.now());
      if (!target) return false;
      beginActivity();
      activityHop = true;
      startHop(target.x, target.y, target.surface);
      return true;
    }
    function sizePair() {
      return [charWidth.value, charHeight.value];
    }
    function stepOffEdge() {
      if (!surface) return;
      const [min, max] = bounds();
      const direction = x.value - min < max - x.value ? -1 : 1;
      const range = xBounds(viewport(), charWidth.value);
      facingLeft.value = direction < 0;
      const left = surface;
      const nextX = clamp(x.value + direction * charWidth.value * 0.6, range[0], range[1]);
      const center = nextX + charWidth.value / 2;
      if (center >= left.left && center <= left.right) {
        x.value = nextX;
        facingLeft.value = direction > 0;
        queueAnchor();
        finishActivityStep();
        scheduleBehavior();
        return;
      }
      const target = landing(left.el, 0, { x: nextX, y: y.value });
      const view = viewport();
      if (isBlocked(nextX, blockedSpan(hostState?.panelRect ?? null, target.y, charWidth.value, charHeight.value)) || coversControlAt(
        rectAt(nextX, target.y),
        rootEl.value,
        view,
        target.surface?.el ?? null,
        charWidth.value * charHeight.value,
        props.previewRoot
      )) {
        finishActivityStep();
        scheduleBehavior();
        return;
      }
      x.value = nextX;
      startFall(left.el, activityOrigin !== null);
    }
    function scheduleBlink() {
      setTimer("blink", randomBetween(2500, 6e3), () => {
        if (motionAllowed() && visible() && (pose.value === "idle" || settledPeek.value)) {
          blinking.value = true;
          setTimer("blink-end", 140, () => {
            blinking.value = false;
          });
        }
        scheduleBlink();
      });
    }
    function scheduleRest() {
      clearTimer("doze");
      if (disposed || props.previewRoot || !visible() || !motionAllowed()) return;
      setTimer("doze", DOZE_AFTER, () => {
        if (!calm() || activePeekEdge.value || !restAvailable.value) {
          scheduleRest();
          return;
        }
        cancelActivity();
        dozing.value = true;
        setTimer("rest", randomBetween(3500, 6e3), () => {
          dozing.value = false;
          scheduleRest();
          scheduleBehavior();
        });
      });
    }
    function markActivity() {
      const resting = dozing.value;
      cancelRest();
      scheduleRest();
      if (resting) scheduleBehavior();
    }
    function playTransient(next, duration) {
      if (!onGround()) return;
      settle();
      clearTimer("behavior");
      transient.value = next;
      setTimer("transient", duration, () => {
        transient.value = null;
        scheduleBehavior();
      });
    }
    function interactionKey() {
      return JSON.stringify([props.pluginId, props.pet?.key || "ying"]);
    }
    function hostIdle() {
      return !hostState || hostState.phase === "idle" && !hostState.thinking;
    }
    function clearReaction() {
      const active = reaction.value !== null;
      clearTimer("reaction");
      reaction.value = null;
      if (active) scheduleBehavior();
    }
    function cancelInteractionFeedback(preserveActivity = false) {
      if (!preserveActivity) cancelActivity();
      greeting.cancel();
      clearAttention();
      clearTimer("long-press");
      if (press) press.longPressCancelled = true;
      pendingDropReaction = null;
      clearReaction();
    }
    function interactionAllowed() {
      return !disposed && ready.value && !props.previewRoot && available.value && visible() && motionAllowed() && hostIdle() && !transient.value && !sustained.value && !activePeekEdge.value && !sheltering;
    }
    function playInteraction() {
      greeting.cancel();
      clearAttention();
      if (!interactionAllowed() || motion.value !== "idle" && motion.value !== "walk") return;
      const next = interactionMemory.respond(interactionKey(), Date.now());
      if (!next) return;
      settle();
      activityPolicy.interact({ x: x.value, y: y.value }, Date.now());
      clearTimer("behavior");
      reaction.value = next.pose;
      setTimer("reaction", next.duration, () => {
        reaction.value = null;
        scheduleBehavior();
      });
    }
    function finishDropReaction() {
      const key = pendingDropReaction;
      pendingDropReaction = null;
      if (key === interactionKey()) playInteraction();
    }
    function clearAttention(resetProximity = true) {
      const active = attention.value !== null;
      clearTimer("attention-dwell");
      clearTimer("attention");
      clearTimer("attention-leave");
      clearTimer("attention-gaze");
      attention.value = null;
      gazeAction.value = null;
      gaze.reset();
      if (resetProximity) {
        proximity.reset();
        nearbyPointer = null;
      }
      if (active) scheduleBehavior();
    }
    function attentionAllowed() {
      return interactionAllowed() && (ownFrames || props.artworkReady !== false) && !reaction.value && !greeting.active.value && motion.value === "idle";
    }
    function selectGaze(point) {
      const rect = currentRect();
      return gaze.select(point, { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 }, Date.now());
    }
    function beginAttention(point, mode) {
      if (!attentionAllowed() || mode === "touch" && !props.lookDirections) return false;
      const action = props.lookDirections ? selectGaze(point) : null;
      if (props.lookDirections && !action) return false;
      const persistent = mode === "mouse" && props.lookDirections;
      const next = persistent ? null : interactionMemory.attend(interactionKey(), Date.now(), mode === "mouse");
      if (!persistent && !next) {
        gaze.reset();
        return false;
      }
      cancelActivity();
      markActivity();
      clearTimer("behavior");
      gazeAction.value = action;
      attention.value = mode;
      if (next) setTimer("attention", mode === "touch" ? TOUCH_LOOK_MS : next.duration, () => clearAttention(false));
      return true;
    }
    function updateMouseGaze() {
      if (!nearbyPointer || !gazeAction.value) return;
      clearTimer("attention-gaze");
      const before = gazeAction.value;
      gazeAction.value = selectGaze(nearbyPointer);
      const delay = gaze.remainingDelay(Date.now());
      if (before === gazeAction.value && delay > 0)
        setTimer("attention-gaze", delay, () => {
          if (nearbyPointer && attention.value === "mouse" && attentionAllowed() && !timers.has("attention-leave"))
            gazeAction.value = selectGaze(nearbyPointer);
        });
    }
    function updateNearbyAttention() {
      if (!nearbyPointer) return;
      if (press || isMobile.value || !attentionAllowed() || !Number.isFinite(nearbyPointer.x + nearbyPointer.y)) {
        clearAttention();
        return;
      }
      const state = proximity.sample(nearbyPointer, currentRect(), !props.lookDirections);
      if (state === "leave") {
        clearTimer("attention-dwell");
        clearTimer("attention-gaze");
        if (attention.value === "mouse" && gazeAction.value) {
          if (!timers.has("attention-leave")) setTimer("attention-leave", ATTENTION_LEAVE_MS, () => clearAttention());
        } else clearAttention();
        return;
      }
      clearTimer("attention-leave");
      if (attention.value === "mouse") {
        updateMouseGaze();
      } else if (state === "arm") {
        setTimer("attention-dwell", ATTENTION_DWELL_MS, () => {
          if (!nearbyPointer || press || isMobile.value || !attentionAllowed()) return;
          if (proximity.sample(nearbyPointer, currentRect(), !props.lookDirections) === "leave") return;
          if (beginAttention(nearbyPointer, "mouse") || !props.lookDirections) proximity.consume();
          else proximity.reset();
        });
      }
    }
    function onAttentionPointerMove(event) {
      if (event.pointerType !== "mouse" || event.isPrimary === false || press) return;
      if (event.buttons !== 0) {
        clearAttention();
        return;
      }
      nearbyPointer = { x: event.clientX, y: event.clientY };
      updateNearbyAttention();
    }
    function onAttentionPointerOut(event) {
      if (event.relatedTarget === null && attention.value !== "touch") clearAttention();
    }
    function onPagePointerDown() {
      if (!press) {
        greeting.cancel();
        clearAttention();
      }
    }
    function landing(exclude = null, dropSnap = 0, position = { x: x.value, y: y.value }) {
      const view = viewport();
      const boxes = roam() === "surfaces" ? querySurfaces(rootEl.value, view, charHeight.value, hostState?.panelRect ?? null, props.previewRoot).filter(
        (box) => box.el !== exclude
      ) : [];
      return computeLanding(roam(), boxes, position, view, size(), dropSnap);
    }
    function startFall(exclude = null, autonomous = false) {
      if (!autonomous) cancelActivity();
      if (greeting.phase.value) greeting.cancel();
      clearAttention();
      clearReaction();
      clearTimer("landing-peek");
      if (fixed()) {
        pinHere();
        return;
      }
      x.value = clamp(x.value, ...xBounds(viewport(), charWidth.value));
      clearTimer("peek");
      clearTimer("peek-pause");
      peekProgress.value = 0;
      peekTarget = 0;
      peekEdge.value = null;
      peekPhase.value = null;
      peekPinned = false;
      sheltering = false;
      detachSurface();
      hopVx = 0;
      hopTargetX = null;
      if (roam() === "free") {
        const view = freeBounds(viewport(), ...sizePair());
        x.value = clamp(x.value, ...view.x);
        y.value = clamp(y.value, ...view.y);
        land(false);
        return;
      }
      fallTarget = landing(exclude, droppedByUser ? Math.min(24, charHeight.value * 0.2) : 0);
      if (!motionAllowed() || !visible() || y.value >= fallTarget.y) {
        land(false);
        return;
      }
      motion.value = "fall";
      velocity = 0;
      bounced = false;
      ensureLoop();
    }
    function land(animated) {
      activityHop = false;
      velocity = 0;
      rising.value = false;
      peekProgress.value = 0;
      peekTarget = 0;
      peekEdge.value = null;
      peekPhase.value = null;
      peekPinned = false;
      sheltering = false;
      hopVx = 0;
      if (hopTargetX !== null) {
        x.value = hopTargetX;
        hopTargetX = null;
      }
      const target = fallTarget;
      fallTarget = null;
      if (roam() !== "free") {
        if (target?.surface) attachSurface(target.surface);
        y.value = target ? target.y : ground();
        if (!target) surface = null;
      }
      if (droppedByUser) manualSurface = surface?.el ?? null;
      if (animated) {
        motion.value = "sit";
        const duration = pendingDropReaction ? interactionMemory.landingDelay(pendingDropReaction, Date.now()) : SIT_DURATION;
        setTimer("sit", duration, () => {
          if (motion.value !== "sit") return;
          motion.value = "idle";
          finishActivityStep();
          finishDropReaction();
          scheduleBehavior();
        });
      } else {
        motion.value = "idle";
        finishActivityStep();
        scheduleBehavior();
      }
      if (clearPanelOverlap() && !onGround()) return;
      if (saveOnLand) {
        saveOnLand = false;
        requestSave();
      }
      queueAnchor();
      if (pendingShelter) {
        pendingShelter = false;
        clearTimer("sit");
        beginShelter(!animated);
        pendingDropReaction = null;
        return;
      }
      if (!animated) finishDropReaction();
      const delay = animated ? Math.max(droppedByUser ? DROP_CLEAR_DELAY : 0, SIT_DURATION + 50) : droppedByUser ? DROP_CLEAR_DELAY : 0;
      droppedByUser = false;
      scheduleClearance(delay);
    }
    function attachSurface(next) {
      detachSurface();
      surface = next;
      if (!visible()) return;
      window.addEventListener("scroll", onSurfaceScroll, { capture: true, passive: true });
      if (typeof MutationObserver !== "undefined") {
        surfaceObserver = new MutationObserver((records) => {
          if (records.every((record) => rootEl.value?.contains(record.target))) return;
          if (!timers.has("surface")) setTimer("surface", SURFACE_CHECK_INTERVAL, checkSurface);
        });
        surfaceObserver.observe(props.previewRoot ?? document.body, { subtree: true, childList: true, attributes: true });
      }
      syncSurfacePoll();
    }
    function syncSurfacePoll() {
      const wanted = ready.value && !disposed && visible() && motion.value !== "drag";
      if (wanted && !surfacePoll) surfacePoll = window.setInterval(onStandPoll, SURFACE_CHECK_INTERVAL);
      if (!wanted && surfacePoll) {
        window.clearInterval(surfacePoll);
        surfacePoll = 0;
      }
    }
    function onStandPoll() {
      standPollTicks += 1;
      if (surface && surfaceObserver) checkSurface();
      if (standPollTicks % CLEARANCE_POLL_EVERY === 0 && !timers.has("clearance")) checkClearance();
    }
    function detachSurface() {
      surface = null;
      manualSurface = null;
      pauseSurfaceWatch();
    }
    function pauseSurfaceWatch() {
      window.removeEventListener("scroll", onSurfaceScroll, { capture: true });
      surfaceObserver?.disconnect();
      surfaceObserver = null;
      syncSurfacePoll();
      clearTimer("surface");
      if (surfaceFrame) window.cancelAnimationFrame(surfaceFrame);
      surfaceFrame = 0;
    }
    function onSurfaceScroll() {
      if (surfaceFrame) return;
      surfaceFrame = window.requestAnimationFrame(() => {
        surfaceFrame = 0;
        checkSurface();
      });
    }
    function checkSurface() {
      if (!surface || !onGround()) return;
      const current = surface;
      const box = measureSurface(current.el, props.previewRoot);
      const result = checkSupport(
        current,
        box && surfaceVisible(current.el) ? box : null,
        x.value + charWidth.value / 2,
        viewport(),
        charHeight.value,
        hostState?.panelRect ?? null,
        charWidth.value
      );
      if (result.kind === "fall") {
        settle();
        startFall(current.el);
        return;
      }
      if (!box) return;
      surface = { ...box, el: current.el };
      x.value += result.dx;
      if (walkTarget) walkTarget.x += result.dx;
      if (motion.value !== "peek") y.value = result.y;
      queueAnchor();
    }
    function rectAt(left, top) {
      return { x: left, y: top, width: charWidth.value, height: charHeight.value };
    }
    function checkClearance() {
      if (fixed()) {
        if (refreshBottomFloor()) relayout();
        return;
      }
      if (disposed || !ready.value || !visible()) return;
      if (refreshBottomFloor()) relayout();
      if (sheltering) {
        recheckShelter();
        return;
      }
      if (motion.value !== "idle") return;
      if (surface && surface.el === manualSurface) return;
      const instant = initialPlacement || !motionAllowed();
      initialPlacement = false;
      const view = viewport();
      const body = charWidth.value * charHeight.value;
      const covers = (rect, standingOn2) => coversControlAt(rect, rootEl.value, view, standingOn2, body, props.previewRoot);
      const standingOn = surface?.el ?? null;
      if (!covers(currentRect(), standingOn)) return;
      settle();
      clearTimer("behavior");
      const span = panelSpan();
      const here = pickClearX(
        x.value,
        bounds(),
        (left) => !isBlocked(left, span) && !covers(rectAt(left, y.value), standingOn),
        charWidth.value / 2
      );
      if (here !== null) {
        moveTo(here, y.value, surface, instant);
        return;
      }
      const elsewhere = roam() === "free" ? findFreeSpot(covers) : findOtherSurface(covers);
      if (elsewhere) {
        moveTo(elsewhere.x, elsewhere.y, elsewhere.surface, instant);
        return;
      }
      goShelter(instant);
    }
    function findOtherSurface(covers) {
      if (roam() !== "surfaces" && !surface) return null;
      const view = viewport();
      const options = [];
      if (surface) options.push({ y: ground(), bounds: xBounds(view, charWidth.value), surface: null });
      if (roam() === "surfaces") {
        const columns = [x.value + charWidth.value / 2, view.width * 0.25, view.width * 0.75];
        for (const box of surfacesNear(
          rootEl.value,
          view,
          charHeight.value,
          hostState?.panelRect ?? null,
          columns,
          props.previewRoot
        )) {
          if (box.el === surface?.el) continue;
          options.push({ y: box.top - charHeight.value, bounds: surfaceXBounds(box, view, charWidth.value), surface: box });
        }
      }
      const centerX = x.value;
      options.sort((a, b) => distanceTo(a, centerX) - distanceTo(b, centerX));
      for (const option of options.slice(0, MAX_OTHER_SURFACES)) {
        const start = clamp(x.value, ...option.bounds);
        const standingOn = option.surface?.el ?? null;
        const span = blockedSpan(hostState?.panelRect ?? null, option.y, charWidth.value, charHeight.value);
        const clear = (left2) => !isBlocked(left2, span) && !covers(rectAt(left2, option.y), standingOn);
        const left = clear(start) ? start : pickClearX(start, option.bounds, clear, charWidth.value / 2, OTHER_SURFACE_CANDIDATES);
        if (left !== null) return { x: left, y: option.y, surface: option.surface };
      }
      return null;
    }
    function distanceTo(option, centerX) {
      const left = clamp(centerX, ...option.bounds);
      return Math.hypot(left - centerX, option.y - y.value);
    }
    function findFreeSpot(covers) {
      const range = freeBounds(viewport(), ...sizePair());
      for (const top of [range.y[0], (range.y[0] + range.y[1]) / 2, range.y[1]]) {
        if (Math.abs(top - y.value) < 1) continue;
        const start = clamp(x.value, ...range.x);
        const clear = (left2) => !covers(rectAt(left2, top), null);
        const left = clear(start) ? start : pickClearX(start, range.x, clear, charWidth.value / 2, OTHER_SURFACE_CANDIDATES);
        if (left !== null) return { x: left, y: top, surface: null };
      }
      return null;
    }
    function goShelter(instant) {
      const edge = nearestEdge(x.value, xBounds(viewport(), charWidth.value));
      const floorY = ground();
      pendingShelter = true;
      if (instant || Math.abs(edge - x.value) < 1 && Math.abs(floorY - y.value) < 1 && !surface) {
        pendingShelter = false;
        detachSurface();
        x.value = edge;
        y.value = floorY;
        beginShelter(instant);
        return;
      }
      moveTo(edge, floorY, null, false);
    }
    function beginShelter(instant) {
      sheltering = true;
      beginPeek("bottom", false, instant);
    }
    function recheckShelter() {
      const view = viewport();
      const body = charWidth.value * charHeight.value;
      if (!coversControlAt(rectAt(x.value, ground()), rootEl.value, view, null, body, props.previewRoot)) {
        sheltering = false;
        endPeek();
      }
    }
    function moveTo(targetX, targetY, target, instant) {
      cancelActivity();
      if (greeting.phase.value) greeting.cancel();
      clearAttention();
      clearReaction();
      const sameLevel = Math.abs(targetY - y.value) < 1 && (target?.el ?? null) === (surface?.el ?? null);
      if (instant) {
        facingLeft.value = targetX < x.value;
        detachSurface();
        x.value = targetX;
        y.value = targetY;
        fallTarget = { y: targetY, surface: target };
        land(false);
        return;
      }
      if (sameLevel || roam() === "free") {
        if (Math.abs(targetX - x.value) < 1 && Math.abs(targetY - y.value) < 1) finishWalk();
        else startWalk(targetX, roam() === "free" ? targetY : null);
        return;
      }
      startHop(targetX, targetY, target);
    }
    function startHop(targetX, targetY, target) {
      detachSurface();
      const { vx, vy } = hopVelocity(
        { x: x.value, y: y.value },
        { x: targetX, y: targetY },
        GRAVITY,
        Math.min(charHeight.value * HOP_LIFT_RATIO, Math.max(0, Math.min(y.value, targetY) - viewport().safeArea.top))
      );
      facingLeft.value = targetX < x.value;
      hopVx = vx;
      hopTargetX = targetX;
      velocity = vy;
      bounced = true;
      fallTarget = { y: targetY, surface: target };
      motion.value = "fall";
      ensureLoop();
    }
    function scheduleClearance(delay) {
      setTimer("clearance", delay, checkClearance);
    }
    function requestSave(immediate = false) {
      if (immediate) {
        clearTimer("save");
        writePosition();
        return;
      }
      const wait = lastSaveAt + SAVE_THROTTLE - Date.now();
      if (wait <= 0) writePosition();
      else if (!timers.has("save")) setTimer("save", wait, writePosition);
    }
    function writePosition() {
      if (!ready.value || motion.value === "drag" || motion.value === "fall") return;
      const view = viewport();
      const xRatio = Math.round(xToRatio(x.value, xBounds(view, charWidth.value)) * 1e3) / 1e3;
      const yRatio = Math.round(xToRatio(y.value, [view.safeArea.top, ground()]) * 1e3) / 1e3;
      const value = {
        roam: roam(),
        xRatio,
        yRatio,
        ...peekPinned && peekEdge.value ? { peekEdge: peekEdge.value } : {},
        ...fixed() && fixedPosition ? {
          xRatio: Math.round(fixedPosition.xRatio * 1e3) / 1e3,
          yRatio: Math.round(fixedPosition.yRatio * 1e3) / 1e3
        } : {}
      };
      const key = JSON.stringify(value);
      if (key === lastSaved) return;
      lastSaved = key;
      lastSaveAt = Date.now();
      props.pet?.storage?.set?.(value)?.catch?.(() => console.warn("[AgentPets] position not saved"));
    }
    function clearPanelOverlap() {
      if (motion.value === "drag") return false;
      if (activePeekEdge.value) {
        const rect = currentRect();
        const panel = hostState?.panelRect;
        if (!panel || intersectionArea(rect, panel) === 0) return false;
        const shift = peekPanelShift(rect, panel, peekViewport(), activePeekEdge.value);
        if (shift) {
          x.value += shift.x;
          y.value += shift.y;
          queueAnchor();
          return true;
        }
      }
      const view = viewport();
      const point = avoidPanel({ x: x.value, y: y.value }, hostState?.panelRect ?? null, view, size());
      if (point.x === x.value && point.y === y.value) return false;
      const horizontal = point.y === y.value;
      const previous = surface;
      const manual = manualSurface;
      resetMotion();
      x.value = point.x;
      y.value = point.y;
      if (previous && point.y === previous.top - charHeight.value && checkSupport(
        previous,
        previous,
        point.x + charWidth.value / 2,
        view,
        charHeight.value,
        hostState?.panelRect ?? null,
        charWidth.value
      ).kind === "follow") {
        attachSurface(previous);
        manualSurface = manual;
      }
      if (horizontal && !surface && !fixed() && roam() !== "free") startFall();
      scheduleBehavior();
      queueAnchor();
      return true;
    }
    function relayout() {
      layoutRevision.value++;
      if (fixed() && motion.value !== "drag") {
        placeFixed();
        return;
      }
      if (motion.value === "peek" && peekEdge.value) {
        placePeek();
        clearPanelOverlap();
        queueAnchor();
        return;
      }
      if (clearPanelOverlap()) return;
      const view = freeBounds(viewport(), ...sizePair());
      if (walkTarget) {
        walkTarget.x = clamp(walkTarget.x, ...view.x);
        if (walkTarget.y !== null) walkTarget.y = clamp(walkTarget.y, ...view.y);
      }
      if (motion.value === "drag" || motion.value === "fall") {
        const outside = x.value < view.x[0] || x.value > view.x[1] || y.value > view.y[1];
        const targetOutside = fallTarget && (fallTarget.y < view.y[0] || fallTarget.y > view.y[1]);
        const hopOutside = hopTargetX !== null && (hopTargetX < view.x[0] || hopTargetX > view.x[1]);
        x.value = clamp(x.value, ...view.x);
        y.value = clamp(y.value, ...view.y);
        if (motion.value === "fall" && (outside || targetOutside || hopOutside)) {
          pendingShelter = false;
          startFall();
        }
        queueAnchor();
        return;
      }
      if (roam() === "free") {
        const view2 = freeBounds(viewport(), ...sizePair());
        x.value = clamp(x.value, ...view2.x);
        y.value = clamp(y.value, ...view2.y);
        queueAnchor();
        return;
      }
      if (surface) {
        checkSurface();
        if (!surface) return;
      } else y.value = ground();
      const range = bounds();
      x.value = clamp(x.value, range[0], range[1]);
      clearPanelOverlap();
      queueAnchor();
    }
    function applySettings(value) {
      cancelActivity();
      clearAttention();
      settingsRevision++;
      const before = settings.value.roam;
      const wasFixed = fixed();
      settings.value = normalizeSettings(value);
      if (ready.value && wasFixed !== fixed() && motion.value !== "drag") {
        saveOnLand = true;
        if (fixed()) pinHere();
        else {
          fixedPosition = null;
          startFall();
        }
        return;
      }
      if (ready.value && !fixed() && settings.value.roam !== before && motion.value !== "drag") {
        settle();
        saveOnLand = true;
        startFall();
        return;
      }
      relayout();
      scheduleBehavior();
    }
    function onHostState(state) {
      if (editorPaused) {
        pendingHostState = state;
        return;
      }
      const before = hostState;
      hostState = state;
      if (!hostIdle() || !state.available || !state.motionAllowed || !state.pageVisible) cancelInteractionFeedback();
      available.value = state.available;
      const resized = !!before && (before.viewport.width !== state.viewport.width || before.viewport.height !== state.viewport.height || before.viewport.keyboardInset !== state.viewport.keyboardInset || before.isMobile !== state.isMobile);
      isMobile.value = state.isMobile;
      if (resized) {
        cancelActivity();
        clearAttention();
      }
      if (resized) refreshBottomFloor();
      const nextSustained = phasePose(state.phase);
      if (nextSustained !== sustained.value) {
        sustained.value = nextSustained;
        if (nextSustained) {
          settle();
          clearTimer("behavior");
          markActivity();
        } else scheduleBehavior();
      }
      if (!state.motionAllowed && before?.motionAllowed !== false) freezeMotion();
      if (state.motionAllowed && before?.motionAllowed === false) {
        if (motion.value === "peek") schedulePeekExit();
        else scheduleBehavior();
      }
      syncVisibility();
      syncSurfacePoll();
      if (resized) scheduleClearance(RESIZE_CLEAR_DELAY);
      if (ready.value) relayout();
    }
    function freezeMotion() {
      cancelActivity();
      stopLoop();
      clearTimer("behavior");
      clearTimer("peek");
      clearTimer("peek-pause");
      walkTarget = null;
      walkPhase.value = 0;
      pendingPeek = null;
      pendingStepOff = false;
      pendingShelter = false;
      blinking.value = false;
      if (motion.value === "peek" && peekEdge.value) {
        peekProgress.value = 1;
        peekTarget = 1;
        peekPhase.value = "look";
        peekRevealing.value = true;
        peekTiltProgress.value = 1;
        queueAnchor();
        return;
      }
      peekProgress.value = 0;
      peekTarget = 0;
      if (motion.value === "fall") land(false);
      else if (motion.value === "walk" || motion.value === "peek") {
        motion.value = "idle";
        queueAnchor();
      }
    }
    function syncVisibility() {
      animationActive.value = motionAllowed() && visible();
      if (!visible()) {
        cancelPointerGesture(!editorPaused);
        cancelInteractionFeedback();
      }
      if (editorPaused) {
        stopLoop();
        pauseSurfaceWatch();
        if (anchorFrame) window.cancelAnimationFrame(anchorFrame);
        anchorFrame = 0;
        return;
      }
      if (!visible()) {
        stopLoop();
        clearTimer("behavior");
        pauseSurfaceWatch();
        if (motion.value === "fall") land(false);
        requestSave(true);
        return;
      }
      if (surface && !surfaceObserver) {
        attachSurface(surface);
        checkSurface();
      }
      ensureLoop();
      if (motion.value === "idle" && !timers.has("behavior")) scheduleBehavior();
      if (!dozing.value && !timers.has("doze")) scheduleRest();
    }
    function onHostEvent(event) {
      if (editorPaused) return;
      cancelInteractionFeedback();
      markActivity();
      const next = eventPose(event.name);
      if (next) playTransient(next.pose, next.duration);
      else scheduleBehavior();
    }
    async function refreshPetSettings() {
      if (props.settingsOverride) return;
      const revision = ++settingsRevision;
      const loaded = await withLoadTimeout(
        loadSettings(props.api, props.pluginId, props.pet?.key || "ying"),
        startup.signal
      ).catch(() => settings.value);
      if (!disposed && revision === settingsRevision) applySettings(loaded);
    }
    function onSettingsEvent(event) {
      if (props.pluginId && event.source !== props.pluginId) return;
      const data = event.data;
      if (!data || typeof data !== "object" || data.key && data.key !== (props.pet?.key || "ying")) return;
      if (!ready.value && props.api && !props.settingsOverride) {
        void refreshPetSettings();
        return;
      }
      applySettings({ ...settings.value, ...data });
    }
    watch([() => props.pluginId, () => props.pet?.key], () => {
      cancelPointerGesture(false);
      cancelInteractionFeedback();
      activityPolicy.reset();
      markActivity();
      ownCalibration.value = builtinDefaultCalibration("ying");
      void refreshPetSettings();
      void refreshOwnCalibration();
      scheduleBehavior();
    });
    watch(
      () => props.artworkReady,
      (loaded) => {
        if (ownFrames) return;
        if (!loaded) {
          cancelActivity();
          clearAttention();
        } else scheduleBehavior();
      }
    );
    watch(
      () => props.previewRoot,
      () => {
        cancelPointerGesture(false);
        cancelInteractionFeedback();
        scheduleBehavior();
      }
    );
    watch(
      () => props.lookDirections,
      () => clearAttention()
    );
    let calibrationRevision = 0;
    async function refreshOwnCalibration() {
      const version = ++calibrationRevision;
      if (!ownFrames) return;
      if (props.pet?.key && props.pet.key !== "ying") {
        ownCalibration.value = builtinDefaultCalibration("ying");
        return;
      }
      emit("load-state", "loading");
      try {
        const value = await loadBuiltinCalibration(props.api, props.pluginId, "ying", startup.signal);
        if (disposed || version !== calibrationRevision) return;
        ownCalibration.value = value;
        emit("pack-ready", { ...YING_PACK, calibration: value });
        emit("load-state", "ready");
      } catch {
        if (disposed || version !== calibrationRevision) return;
        if (props.previewRoot) emit("load-state", "error");
      }
    }
    function pointerPosition(event) {
      const origin = props.previewRoot?.getBoundingClientRect();
      return { x: event.clientX - (origin?.left ?? 0), y: event.clientY - (origin?.top ?? 0) };
    }
    watch(
      () => props.settingsOverride,
      (value) => {
        if (value) applySettings(value);
      },
      { deep: true }
    );
    function onPointerDown(event) {
      if (event.button !== 0 || event.isPrimary === false || press || disposed || !ready.value || !visible()) return;
      suppressedPointer = null;
      cancelInteractionFeedback();
      markActivity();
      if (!activePeekEdge.value && hostIdle()) settle();
      clearTimer("behavior");
      press = {
        id: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        offsetX: activePeekEdge.value ? charWidth.value / 2 : pointerPosition(event).x - x.value,
        offsetY: activePeekEdge.value ? charHeight.value * 0.3 : pointerPosition(event).y - y.value,
        startedAt: Date.now(),
        dragging: false,
        longPressed: false,
        longPressCancelled: !!props.previewRoot,
        touchPreview: false,
        owner: props.pet
      };
      const current = press;
      if (event.pointerType === "touch")
        current.touchPreview = beginAttention({ x: event.clientX, y: event.clientY }, "touch");
      if (!props.previewRoot)
        setTimer("long-press", LONG_PRESS_MS, () => {
          if (press === current) recognizeLongPress(current);
        });
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
      window.addEventListener("pointercancel", onPointerCancel);
    }
    function recognizeLongPress(current) {
      if (current.dragging || current.longPressed || current.longPressCancelled || !visible()) return;
      clearAttention();
      current.longPressed = true;
      interactionMemory.record(interactionKey(), Date.now());
      playInteraction();
    }
    function onPointerMove(event) {
      if (!press || event.pointerId !== press.id) return;
      if (!press.dragging) {
        if (Math.hypot(event.clientX - press.startX, event.clientY - press.startY) < DRAG_THRESHOLD) return;
        press.dragging = true;
        cancelInteractionFeedback();
        settle();
        stopLoop();
        detachSurface();
        clearTimer("behavior");
        clearTimer("sit");
        clearTimer("clearance");
        clearTimer("peek");
        clearTimer("peek-pause");
        clearTimer("landing-peek");
        transient.value = null;
        peekProgress.value = 0;
        peekEdge.value = null;
        peekPhase.value = null;
        peekPinned = false;
        peekTarget = 0;
        sheltering = false;
        pendingShelter = false;
        hopVx = 0;
        hopTargetX = null;
        velocity = 0;
        fallTarget = null;
        motion.value = "drag";
        syncSurfacePoll();
        press.owner?.setInteracting?.(true);
      }
      event.preventDefault();
      const view = freeBounds(viewport(), ...sizePair());
      x.value = clamp(pointerPosition(event).x - press.offsetX, ...view.x);
      y.value = clamp(pointerPosition(event).y - press.offsetY, ...view.y);
      facingLeft.value = false;
      queueAnchor();
    }
    function releasePointer() {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerCancel);
    }
    function finishDrag(react = true, owner = props.pet) {
      owner?.setInteracting?.(false);
      if (react && !props.previewRoot) {
        const key = interactionKey();
        interactionMemory.record(key, Date.now());
        if (interactionAllowed()) pendingDropReaction = key;
      }
      droppedByUser = true;
      saveOnLand = true;
      x.value = clamp(x.value, ...xBounds(viewport(), charWidth.value));
      motion.value = "idle";
      syncSurfacePoll();
      const edge = fixed() || previewEdge.value ? null : dropPeekEdge({ x: x.value, y: y.value }, viewport(), size());
      const snap = Math.min(24, charHeight.value * 0.2);
      const nearby = !fixed() && roam() === "surfaces" ? landing(null, snap) : null;
      const onPlatform = !!nearby?.surface && Math.abs(nearby.y - y.value) <= snap;
      if (edge && !onPlatform) {
        pendingDropReaction = null;
        droppedByUser = false;
        saveOnLand = false;
        beginPeek(edge, true);
        requestSave();
        return;
      }
      startFall();
    }
    function onPointerUp(event) {
      if (!press || event.pointerId !== press.id) return;
      const current = press;
      if (Date.now() - current.startedAt >= LONG_PRESS_MS) recognizeLongPress(current);
      press = null;
      releasePointer();
      clearTimer("long-press");
      const held = current.longPressed || !props.previewRoot && Date.now() - current.startedAt >= LONG_PRESS_MS;
      if (!current.dragging && !held && current.touchPreview && attention.value === "touch" && attentionAllowed())
        interactionMemory.attend(interactionKey(), Date.now());
      if (current.dragging || held) suppressCompatibilityClick(current.id);
      if (current.dragging) finishDrag(true, current.owner);
      else scheduleBehavior();
    }
    function suppressCompatibilityClick(id) {
      suppressedPointer = { id, until: Date.now() + 700 };
    }
    function cancelPointerGesture(settleDrag = true) {
      clearTimer("long-press");
      cancelInteractionFeedback();
      const current = press;
      if (!current) return;
      press = null;
      releasePointer();
      suppressCompatibilityClick(current.id);
      if (current.dragging) {
        if (settleDrag && !disposed) finishDrag(false, current.owner);
        else {
          current.owner?.setInteracting?.(false);
          motion.value = "idle";
          saveOnLand = false;
        }
      } else scheduleBehavior();
    }
    function onPointerCancel(event) {
      if (!press || event.pointerId !== press.id) return;
      cancelPointerGesture();
    }
    function onWindowBlur() {
      cancelPointerGesture();
      cancelInteractionFeedback();
      scheduleBehavior();
    }
    function onActivate(event) {
      const pointerId = event.pointerId;
      const pointerClick = event.detail > 0 || typeof pointerId === "number" && pointerId >= 0;
      const compatibilityClick = suppressedPointer && Date.now() <= suppressedPointer.until && pointerClick && (pointerId === void 0 || pointerId === suppressedPointer.id);
      if (compatibilityClick) {
        suppressedPointer = null;
        return;
      }
      if (suppressedPointer && Date.now() > suppressedPointer.until) suppressedPointer = null;
      if (disposed || !ready.value || !visible()) return;
      cancelInteractionFeedback();
      markActivity();
      props.agent?.open?.();
      scheduleBehavior();
    }
    async function readStoredPosition() {
      try {
        const stored = await props.pet?.storage?.get?.();
        if (stored && typeof stored.xRatio === "number" && Number.isFinite(stored.xRatio)) return stored;
      } catch {
        console.warn("[AgentPets] position unavailable");
      }
      return null;
    }
    function restorePosition(stored) {
      const view = viewport();
      x.value = ratioToX(stored?.xRatio ?? DEFAULT_RATIO, xBounds(view, charWidth.value));
      const yRatio = typeof stored?.yRatio === "number" && Number.isFinite(stored.yRatio) ? stored.yRatio : 1;
      y.value = ratioToX(yRatio, [view.safeArea.top, ground()]);
      if (fixed()) {
        rememberFixedPosition();
        placeFixed();
        return;
      }
      if (isPeekEdge(stored?.peekEdge)) {
        const home = peekHome({ x: x.value, y: y.value }, view, size(), stored.peekEdge);
        if (stored.peekEdge === "bottom" || Math.abs(home.x - x.value) < 1 && Math.abs(home.y - y.value) < 1) {
          beginPeek(stored.peekEdge, true, true);
          return;
        }
      }
      if (roam() === "free") {
        land(false);
        return;
      }
      y.value = Math.max(view.safeArea.top, y.value - 4);
      fallTarget = landing();
      land(false);
    }
    function onVisibilityChange() {
      documentVisible = document.visibilityState !== "hidden";
      syncVisibility();
    }
    function onWindowResize() {
      if (!ready.value || props.previewRoot) return;
      cancelActivity();
      clearAttention();
      if (editorPaused) {
        pendingViewportResize = true;
        return;
      }
      refreshBottomFloor();
      relayout();
      scheduleClearance(RESIZE_CLEAR_DELAY);
      scheduleBehavior();
    }
    onMounted(async () => {
      if (!props.previewRoot) greeting.arm();
      if (!props.previewRoot)
        cleanups.push(
          onEditorPresence((active) => {
            editorPaused = active;
            if (active) {
              cancelPointerGesture(false);
              cancelInteractionFeedback();
              timers.pause();
            } else {
              const next = pendingHostState ?? hostState;
              pendingHostState = null;
              if (next) onHostState(next);
              if (pendingViewportResize) {
                pendingViewportResize = false;
                onWindowResize();
              }
              timers.resume();
            }
            syncVisibility();
            syncSurfacePoll();
          })
        );
      void refreshOwnCalibration();
      const agent = props.agent;
      if (agent?.subscribe) cleanups.push(agent.subscribe(onHostState));
      if (agent?.on) {
        for (const name of [
          "agent.panel.open",
          "agent.panel.close",
          "agent.thinking.start",
          "agent.thinking.end",
          "agent.tool.start",
          "agent.tool.end",
          "agent.awaiting",
          "agent.done",
          "agent.error",
          "agent.preview",
          "agent.bubble"
        ]) {
          cleanups.push(agent.on(name, onHostEvent));
        }
        cleanups.push(agent.on(SETTINGS_EVENT, onSettingsEvent));
        if (ownFrames)
          cleanups.push(
            agent.on(PACK_UPDATED_EVENT, (event) => {
              if (event.source === props.pluginId && event.data.key === "ying") void refreshOwnCalibration();
            })
          );
      }
      document.addEventListener("visibilitychange", onVisibilityChange);
      window.addEventListener("resize", onWindowResize);
      window.addEventListener("blur", onWindowBlur);
      cleanups.push(() => document.removeEventListener("visibilitychange", onVisibilityChange));
      cleanups.push(() => window.removeEventListener("resize", onWindowResize));
      cleanups.push(() => window.removeEventListener("blur", onWindowBlur));
      if (!props.previewRoot) {
        window.addEventListener("pointermove", onAttentionPointerMove, { passive: true });
        window.addEventListener("pointerout", onAttentionPointerOut, { passive: true });
        window.addEventListener("pointerdown", onPagePointerDown, { passive: true });
        const cancelGreeting = () => greeting.cancel();
        window.addEventListener("keydown", cancelGreeting);
        cleanups.push(() => {
          window.removeEventListener("pointermove", onAttentionPointerMove);
          window.removeEventListener("pointerout", onAttentionPointerOut);
          window.removeEventListener("pointerdown", onPagePointerDown);
          window.removeEventListener("keydown", cancelGreeting);
        });
      }
      const visual = window.visualViewport;
      if (visual && !props.previewRoot) {
        visual.addEventListener("resize", onWindowResize);
        visual.addEventListener("scroll", onWindowResize);
        cleanups.push(() => {
          visual.removeEventListener("resize", onWindowResize);
          visual.removeEventListener("scroll", onWindowResize);
        });
      }
      const revision = settingsRevision;
      const [loaded, stored] = await Promise.all([
        withLoadTimeout(
          Promise.resolve(props.settingsOverride ?? loadSettings(props.api, props.pluginId, props.pet?.key || "ying")),
          startup.signal
        ).catch(() => DEFAULT_SETTINGS),
        withLoadTimeout(readStoredPosition(), startup.signal).catch(() => null)
      ]);
      if (disposed) return;
      if (revision === settingsRevision) settings.value = normalizeSettings(props.settingsOverride ?? loaded);
      refreshBottomFloor();
      restorePosition(stored);
      ready.value = true;
      syncVisibility();
      syncSurfacePoll();
      reportAnchor();
      scheduleBlink();
      markActivity();
      scheduleBehavior();
    });
    onBeforeUnmount(() => {
      if (timers.has("save")) writePosition();
      disposed = true;
      activityPolicy.reset();
      if (press) cancelPointerGesture(false);
      clearAttention();
      clearReaction();
      pendingDropReaction = null;
      startup.abort();
      stopLoop();
      pauseSurfaceWatch();
      if (anchorFrame) window.cancelAnimationFrame(anchorFrame);
      anchorFrame = 0;
      timers.dispose();
      releasePointer();
      press = null;
      for (const cleanup of cleanups.splice(0)) cleanup();
      props.pet?.setBubbleAnchor?.(null);
    });
    return (_ctx, _cache) => {
      return _openBlock(), _createElementBlock("div", {
        ref_key: "rootEl",
        ref: rootEl,
        class: _normalizeClass(["agent-pet-ying", { "agent-pet-ying--contained": !!props.previewRoot }]),
        "data-pose": pose.value,
        "data-motion": motion.value,
        "data-reaction": reaction.value ?? void 0,
        "data-greeting": _unref(greeting).pending.value ? "pending" : _unref(greeting).phase.value ?? void 0,
        "data-greeting-round": _unref(greeting).round.value || void 0,
        "data-attention": attention.value ?? void 0,
        "data-gaze": gazeAction.value ?? void 0,
        "data-roam": settings.value.roam,
        "data-movement": settings.value.movement,
        "data-peek-edge": activePeekEdge.value ?? void 0,
        "data-peek-phase": previewEdge.value ? "look" : peekPhase.value ?? void 0
      }, [
        _withDirectives(_createElementVNode("button", {
          type: "button",
          class: "agent-pet-ying__character",
          style: _normalizeStyle(buttonStyle.value),
          "aria-label": label.value,
          onPointerdown: onPointerDown,
          onClick: onActivate,
          onDragstart: _cache[0] || (_cache[0] = _withModifiers(() => {
          }, ["prevent"]))
        }, [
          _createElementVNode("span", {
            class: "agent-pet-ying__clip",
            style: _normalizeStyle(clipStyle.value)
          }, [
            _createElementVNode("span", {
              class: "agent-pet-ying__artwork",
              style: _normalizeStyle(artworkStyle.value)
            }, [
              _renderSlot(_ctx.$slots, "default", {
                pose: pose.value,
                gazeAction: gazeAction.value,
                greetingRound: _unref(greeting).round.value,
                greetingComplete: _unref(greeting).frameComplete,
                facingLeft: facingLeft.value,
                motionActive: animationActive.value && (!activePeekEdge.value || settledPeek.value),
                peekEdge: activePeekEdge.value,
                peekFromLeft: drawing.value.fromLeft
              }, () => [
                _createElementVNode("span", {
                  class: _normalizeClass(["agent-pet-ying__frames", { "agent-pet-ying__frames--flip": facingLeft.value, "agent-pet-ying__frames--pending": !displayed.value }]),
                  "data-frame": displayed.value ?? void 0
                }, [
                  _createElementVNode("span", {
                    class: "agent-pet-ying__frame-crop",
                    style: _normalizeStyle(ownLayout.value.frame)
                  }, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(POSES), (name) => {
                      return _openBlock(), _createElementBlock("img", {
                        key: name,
                        class: _normalizeClass(["agent-pet-ying__frame", { "agent-pet-ying__frame--visible": name === displayed.value }]),
                        src: frameSrc.value[name],
                        "data-pose": name,
                        alt: "",
                        draggable: "false",
                        onLoad: ($event) => onFrameLoad(name, $event),
                        onError: ($event) => onFrameError(name)
                      }, null, 42, _hoisted_4);
                    }), 128))
                  ], 4),
                  __props.showCalibration ? (_openBlock(true), _createElementBlock(_Fragment, { key: 0 }, _renderList(ownGuides.value, (point) => {
                    return _openBlock(), _createElementBlock("span", {
                      key: point.key,
                      class: "agent-pet-ying__eye",
                      style: _normalizeStyle({ left: `${point.x * 100}%`, top: `${point.y * 100}%` })
                    }, null, 4);
                  }), 128)) : _createCommentVNode("", true)
                ], 10, _hoisted_3)
              ], true)
            ], 4)
          ], 4)
        ], 44, _hoisted_2), [
          [_vShow, ready.value]
        ])
      ], 10, _hoisted_1);
    };
  }
});

const AgentPet = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-6da1158e"]]);

export { supportsLookDirections as a, AgentPet as default, supportsRest as s };
