import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { D as DEFAULT_SETTINGS, S as SETTINGS_EVENT, l as loadSettings, n as normalizeSettings } from './settings-_v7SC99m.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

function readViewport(state) {
  if (state?.viewport) return state.viewport;
  return {
    width: window.innerWidth,
    height: window.innerHeight,
    keyboardInset: 0,
    safeArea: { top: 0, right: 0, bottom: 0, left: 0 }
  };
}
function groundTop(viewport, charHeight) {
  const floor = viewport.height - viewport.safeArea.bottom - viewport.keyboardInset;
  return Math.max(viewport.safeArea.top, floor - charHeight);
}
function xBounds(viewport, charWidth) {
  const min = viewport.safeArea.left;
  const max = Math.max(min, viewport.width - viewport.safeArea.right - charWidth);
  return [min, max];
}
function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
function xToRatio(x, bounds) {
  const [min, max] = bounds;
  if (max <= min) return 0;
  return clamp((x - min) / (max - min), 0, 1);
}
function ratioToX(ratio, bounds) {
  const [min, max] = bounds;
  return min + clamp(ratio, 0, 1) * (max - min);
}
function blockedSpan(panel, standY, charWidth, charHeight = 0) {
  if (!panel || panel.width <= 0 || panel.height <= 0) return null;
  if (panel.y + panel.height <= standY) return null;
  if (charHeight > 0 && panel.y >= standY + charHeight) return null;
  return [panel.x - charWidth, panel.x + panel.width];
}
function isBlocked(x, span) {
  return !!span && x > span[0] && x < span[1];
}
function pickWalkTarget(random, current, bounds, span, minDistance = 40) {
  let [min, max] = bounds;
  if (span) {
    if (current <= span[0]) max = Math.min(max, span[0]);
    else if (current >= span[1]) min = Math.max(min, span[1]);
  }
  if (max - min < minDistance) return null;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const target = min + random() * (max - min);
    if (Math.abs(target - current) >= minDistance && !isBlocked(target, span)) return target;
  }
  return null;
}
function escapeSpan(x, span, bounds) {
  if (!isBlocked(x, span) || !span) return x;
  const left = span[0];
  const right = span[1];
  const preferLeft = x - left < right - x;
  if (preferLeft && left >= bounds[0]) return left;
  if (right <= bounds[1]) return right;
  return left >= bounds[0] ? left : x;
}
function sameRect(a, b) {
  if (!a || !b) return a === b;
  return Math.round(a.x) === Math.round(b.x) && Math.round(a.y) === Math.round(b.y) && Math.round(a.width) === Math.round(b.width) && Math.round(a.height) === Math.round(b.height);
}
const MIN_SURFACE_WIDTH = 120;
function floorLine(viewport) {
  return viewport.height - viewport.safeArea.bottom - viewport.keyboardInset;
}
function standable(box, viewport, charHeight, panel) {
  if (box.right - box.left < MIN_SURFACE_WIDTH) return false;
  if (box.top - charHeight < viewport.safeArea.top) return false;
  if (box.top >= floorLine(viewport)) return false;
  if (panel && box.left >= panel.x && box.right <= panel.x + panel.width && box.top >= panel.y && box.top <= panel.y + panel.height) {
    return false;
  }
  return true;
}
function findLanding(boxes, centerX, feetY) {
  let best = null;
  for (const box of boxes) {
    if (centerX < box.left || centerX > box.right || box.top < feetY - 2) continue;
    if (!best || box.top < best.top) best = box;
  }
  return best;
}
function computeLanding(mode, boxes, position, viewport, size) {
  const ground = groundTop(viewport, size.height);
  if (mode === "free") return { y: clamp(position.y, viewport.safeArea.top, ground), surface: null };
  if (mode === "surfaces") {
    const surface = findLanding(boxes, position.x + size.width / 2, position.y + size.height);
    if (surface) return { y: surface.top - size.height, surface };
  }
  return { y: ground, surface: null };
}
function surfaceXBounds(box, viewport, charWidth) {
  const [minX, maxX] = xBounds(viewport, charWidth);
  const min = Math.max(minX, box.left - charWidth / 2);
  const max = Math.min(maxX, box.right - charWidth / 2);
  return [min, Math.max(min, max)];
}
function checkSupport(previous, next, centerX, viewport, charHeight, panel) {
  if (!next || !standable(next, viewport, charHeight, panel)) return { kind: "fall" };
  const dx = next.left - previous.left;
  const center = centerX + dx;
  if (center < next.left || center > next.right) return { kind: "fall" };
  return { kind: "follow", dx, y: next.top - charHeight };
}
function freeBounds(viewport, charWidth, charHeight) {
  return { x: xBounds(viewport, charWidth), y: [viewport.safeArea.top, groundTop(viewport, charHeight)] };
}
function pickFreeTarget(random, current, bounds, minDistance = 60) {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const target = {
      x: bounds.x[0] + random() * (bounds.x[1] - bounds.x[0]),
      y: bounds.y[0] + random() * (bounds.y[1] - bounds.y[0])
    };
    if (Math.hypot(target.x - current.x, target.y - current.y) >= minDistance) return target;
  }
  return null;
}
const MOBILE_SCALE = 0.8;
function effectiveScale(scale, isMobile) {
  return isMobile ? scale * MOBILE_SCALE : scale;
}
function intersectionArea(a, b) {
  const width = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const height = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  return width > 0 && height > 0 ? width * height : 0;
}
const MAX_CLEAR_CANDIDATES = 12;
const CONTROL_COVER_RATIO = 0.1;
const CONTROL_HIDDEN_RATIO = 0.5;
function coversAny(rect, controls, bodyArea = rect.width * rect.height) {
  return controls.some((control) => {
    const overlap = intersectionArea(rect, control);
    if (overlap <= 0) return false;
    const controlArea = control.width * control.height;
    return overlap > bodyArea * CONTROL_COVER_RATIO || controlArea > 0 && overlap > controlArea * CONTROL_HIDDEN_RATIO;
  });
}
function pickClearX(current, bounds, isClear, step, maxCandidates = MAX_CLEAR_CANDIDATES) {
  const [min, max] = bounds;
  const stride = Math.max(8, step);
  const limit = Math.ceil((max - min) / stride) + 1;
  const tried = /* @__PURE__ */ new Set();
  for (let index = 1; index <= limit; index += 1) {
    for (const candidate of [current - index * stride, current + index * stride]) {
      const x = Math.round(clamp(candidate, min, max));
      if (Math.abs(x - current) < 1 || tried.has(x)) continue;
      if (tried.size >= maxCandidates) return null;
      tried.add(x);
      if (isClear(x)) return x;
    }
  }
  return null;
}
const SHELTER_DEPTHS = [0.5, 0.65, 0.8, 0.92];
function pickShelterDepth(isClear) {
  return SHELTER_DEPTHS.find((depth) => isClear(depth)) ?? SHELTER_DEPTHS[SHELTER_DEPTHS.length - 1];
}
function nearestEdge(x, bounds) {
  return x - bounds[0] <= bounds[1] - x ? bounds[0] : bounds[1];
}
function hopVelocity(from, to, gravity, lift) {
  const apex = Math.min(from.y, to.y) - lift;
  const up = Math.sqrt(2 * gravity * (from.y - apex));
  const time = up / gravity + Math.sqrt(2 * (to.y - apex) / gravity);
  return { vx: (to.x - from.x) / time, vy: -up };
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

const SURFACE_SELECTOR = '.v-card, .v-sheet, .v-overlay__content, [role="dialog"]';
const MAX_SURFACE_CANDIDATES = 400;
function measureSurface(el) {
  if (!el.isConnected) return null;
  const rect = el.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;
  return { left: rect.left, top: rect.top, right: rect.right };
}
function surfaceVisible(el) {
  const style = window.getComputedStyle(el);
  return style.pointerEvents !== "none" && style.visibility !== "hidden" && style.display !== "none";
}
function surfaceUnobstructed(el, box, layer, viewportWidth) {
  if (typeof document.elementsFromPoint !== "function") return true;
  const left = Math.max(box.left, 0);
  const right = Math.min(box.right, viewportWidth);
  if (right <= left) return false;
  const hit = document.elementsFromPoint((left + right) / 2, box.top + 2).find((item) => !layer?.contains(item));
  return !!hit && (hit === el || el.contains(hit));
}
function querySurfaces(layer, viewport, charHeight, panel) {
  const floor = floorLine(viewport);
  const candidates = [];
  for (const el of Array.from(document.querySelectorAll(SURFACE_SELECTOR))) {
    const box = measureSurface(el);
    if (!box || box.right <= 0 || box.left >= viewport.width || box.top >= floor) continue;
    if (!standable(box, viewport, charHeight, panel)) continue;
    if (layer && (layer.contains(el) || el.contains(layer))) continue;
    candidates.push({ ...box, el });
    if (candidates.length >= MAX_SURFACE_CANDIDATES) break;
  }
  return candidates.filter(
    (candidate) => surfaceVisible(candidate.el) && surfaceUnobstructed(candidate.el, candidate, layer, viewport.width)
  );
}
const NEARBY_SURFACE_ROWS = 4;
function surfacesNear(layer, viewport, charHeight, panel, columns) {
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
      const box = measureSurface(el);
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
function coversControlAt(rect, layer, viewport, standingOn, bodyArea = rect.width * rect.height) {
  for (const control of eachControlUnder(rect, layer, viewport, standingOn)) {
    if (coversAny(rect, [control], bodyArea)) return true;
  }
  return false;
}
function* eachControlUnder(rect, layer, viewport, standingOn) {
  if (typeof document.elementsFromPoint !== "function") return;
  const viewportArea = viewport.width * viewport.height;
  const seen = /* @__PURE__ */ new Set();
  for (const point of samplePoints(rect)) {
    if (point.x < 0 || point.y < 0 || point.x >= viewport.width || point.y >= viewport.height) continue;
    const hit = document.elementsFromPoint(point.x, point.y).find((item) => !layer?.contains(item));
    const control = hit?.closest(CONTROL_SELECTOR);
    if (!control || seen.has(control)) continue;
    seen.add(control);
    if (layer && control.contains(layer)) continue;
    if (standingOn && (control === standingOn || control.contains(standingOn))) continue;
    const box = control.getBoundingClientRect();
    if (box.width * box.height > viewportArea / 2) continue;
    yield { x: box.left, y: box.top, width: box.width, height: box.height };
  }
}

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,normalizeClass:_normalizeClass,createElementVNode:_createElementVNode,vShow:_vShow,withModifiers:_withModifiers,normalizeStyle:_normalizeStyle,withDirectives:_withDirectives} = await importShared('vue');

const _hoisted_1 = ["data-pose", "data-motion", "data-roam"];
const _hoisted_2 = ["aria-label"];
const _hoisted_3 = ["data-frame"];
const _hoisted_4 = ["src", "data-pose", "onLoad", "onError"];
const {computed,onBeforeUnmount,onMounted,ref,watch} = await importShared('vue');
const BASE_HEIGHT = 120;
const BASE_WALK_SPEED = 70;
const FREE_SPEED_RATIO = 0.6;
const GRAVITY = 2600;
const DRAG_THRESHOLD = 6;
const SIT_DURATION = 900;
const DOZE_AFTER = 9e4;
const PEEK_RATIO = 0.5;
const PEEK_SPEED = 160;
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
    sourcePluginId: { default: "" }
  },
  setup(__props) {
    const props = __props;
    const rootEl = ref(null);
    const settings = ref({ ...DEFAULT_SETTINGS });
    const aspect = ref(198 / 240);
    const x = ref(0);
    const y = ref(0);
    const sink = ref(0);
    const facingLeft = ref(false);
    const motion = ref("idle");
    const walkPhase = ref(0);
    const transient = ref(null);
    const sustained = ref(null);
    const dozing = ref(false);
    const blinking = ref(false);
    const ready = ref(false);
    const rising = ref(false);
    const available = ref(true);
    const isMobile = ref(false);
    let hostState = null;
    let documentVisible = typeof document === "undefined" || document.visibilityState !== "hidden";
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
    let sheltering = false;
    let pendingShelter = null;
    let hopVx = 0;
    let hopTargetX = null;
    let lastSaved = "";
    let lastSaveAt = 0;
    let saveOnLand = false;
    let suppressClick = false;
    let pendingPeek = false;
    let pendingStepOff = false;
    let surface = null;
    let surfaceFrame = 0;
    let surfaceObserver = null;
    let surfacePoll = 0;
    let standPollTicks = 0;
    let disposed = false;
    let droppedByUser = false;
    let initialPlacement = true;
    let press = null;
    const timers = /* @__PURE__ */ new Map();
    const cleanups = [];
    const charHeight = computed(() => BASE_HEIGHT * effectiveScale(settings.value.scale, isMobile.value));
    const charWidth = computed(() => charHeight.value * aspect.value);
    const pose = computed(
      () => resolvePose({
        motion: motion.value,
        walkPhase: walkPhase.value,
        transient: transient.value,
        sustained: sustained.value,
        dozing: dozing.value,
        blinking: blinking.value,
        rising: rising.value
      })
    );
    const label = computed(() => available.value ? "打开助手（小映）" : "小映（助手未启用）");
    const frameStatus = ref(
      Object.fromEntries(POSES.map((name) => [name, "pending"]))
    );
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
          aspect.value = image.naturalWidth / image.naturalHeight;
          relayout();
        }
      }
      if (name === pose.value) displayed.value = name;
    }
    function onFrameError(name) {
      frameStatus.value[name] = "error";
      failedAt.set(name, Date.now());
      if (displayed.value === name) displayed.value = null;
      syncDisplayed();
    }
    const buttonStyle = computed(() => ({
      width: `${charWidth.value}px`,
      height: `${charHeight.value}px`,
      transform: `translate3d(${x.value}px, ${y.value + sink.value}px, 0)`,
      clipPath: sink.value > 0 ? `inset(0 0 ${sink.value}px 0)` : void 0
    }));
    function setTimer(name, delay, callback) {
      clearTimer(name);
      timers.set(
        name,
        window.setTimeout(() => {
          timers.delete(name);
          callback();
        }, delay)
      );
    }
    function clearTimer(name) {
      const id = timers.get(name);
      if (id !== void 0) window.clearTimeout(id);
      timers.delete(name);
    }
    function randomBetween(min, max) {
      return min + Math.random() * (max - min);
    }
    function roam() {
      return settings.value.roam;
    }
    function viewport() {
      return readViewport(hostState);
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
      return documentVisible && (hostState?.pageVisible ?? true);
    }
    function onGround() {
      return motion.value !== "drag" && motion.value !== "fall";
    }
    function onFloor() {
      return roam() !== "free" && !surface;
    }
    function currentRect() {
      return { x: x.value, y: y.value + sink.value, width: charWidth.value, height: charHeight.value - sink.value };
    }
    function reportAnchor() {
      anchorFrame = 0;
      if (disposed || !ready.value) return;
      const rect = currentRect();
      if (sameRect(rect, lastAnchor)) return;
      lastAnchor = rect;
      props.pet?.setBubbleAnchor?.(rect);
    }
    function queueAnchor() {
      if (anchorFrame || rafId) return;
      anchorFrame = window.requestAnimationFrame(reportAnchor);
    }
    function needsLoop() {
      if (motion.value === "walk" || motion.value === "fall") return true;
      return motion.value === "peek" && sink.value !== peekTarget;
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
      reportAnchor();
      if (needsLoop() && visible()) rafId = window.requestAnimationFrame(tick);
    }
    function stepWalk(dt) {
      if (!walkTarget) {
        finishWalk();
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
        finishWalk();
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
      const target = fallTarget?.y ?? ground();
      velocity += GRAVITY * dt;
      y.value += velocity * dt;
      x.value += hopVx * dt;
      rising.value = velocity < 0;
      if (velocity < 0 || y.value < target) return;
      y.value = target;
      if (!bounced && velocity > 500) {
        bounced = true;
        velocity = -velocity * 0.22;
        return;
      }
      land(true);
    }
    function stepPeek(dt) {
      const step = PEEK_SPEED * dt;
      sink.value = sink.value < peekTarget ? Math.min(peekTarget, sink.value + step) : Math.max(peekTarget, sink.value - step);
      if (sink.value === 0 && peekTarget === 0) {
        motion.value = "idle";
        scheduleBehavior();
      }
    }
    function startWalk(targetX, targetY = null) {
      walkTarget = { x: targetX, y: targetY };
      walkDistance = 0;
      facingLeft.value = targetX < x.value;
      motion.value = "walk";
      ensureLoop();
    }
    function finishWalk() {
      walkTarget = null;
      walkPhase.value = 0;
      if (motion.value === "walk") motion.value = "idle";
      const peek = pendingPeek;
      const stepOff = pendingStepOff;
      pendingPeek = false;
      pendingStepOff = false;
      if (pendingShelter !== null) {
        const depth = pendingShelter;
        pendingShelter = null;
        beginShelter(depth, false);
        return;
      }
      scheduleClearance(0);
      if (stepOff && surface) stepOffEdge();
      else if (peek) beginPeek();
      else scheduleBehavior();
    }
    function beginPeek() {
      if (!motionAllowed() || !onFloor()) return;
      facingLeft.value = x.value > (bounds()[0] + bounds()[1]) / 2;
      motion.value = "peek";
      peekTarget = Math.round(charHeight.value * PEEK_RATIO);
      ensureLoop();
      setTimer("peek", randomBetween(4e3, 7e3), endPeek);
    }
    function endPeek() {
      clearTimer("peek");
      if (motion.value !== "peek") return;
      peekTarget = 0;
      if (!motionAllowed()) {
        sink.value = 0;
        motion.value = "idle";
        queueAnchor();
      }
      ensureLoop();
      scheduleBehavior();
    }
    function settle() {
      if (motion.value === "walk") {
        walkTarget = null;
        walkPhase.value = 0;
        motion.value = "idle";
      }
      if (motion.value === "peek" && !sheltering) {
        clearTimer("peek");
        peekTarget = 0;
        if (motionAllowed() && visible()) ensureLoop();
        else {
          sink.value = 0;
          motion.value = "idle";
        }
      }
      pendingPeek = false;
      pendingStepOff = false;
      pendingShelter = null;
    }
    function calm() {
      return motion.value === "idle" && !transient.value && !sustained.value && !dozing.value && motionAllowed() && visible();
    }
    function scheduleBehavior() {
      clearTimer("behavior");
      if (!calm()) return;
      setTimer("behavior", randomBetween(6e3, 14e3), () => {
        if (!calm()) return;
        if (roam() === "free") {
          const target2 = pickFreeTarget(Math.random, { x: x.value, y: y.value }, freeBounds(viewport(), ...sizePair()));
          if (target2) startWalk(target2.x, target2.y);
          else scheduleBehavior();
          return;
        }
        const [min, max] = bounds();
        const roll = Math.random();
        if (roll < 0.25) {
          const side = Math.random() < 0.5 ? min : max;
          const span = panelSpan();
          if (isBlocked(side, span)) {
            scheduleBehavior();
            return;
          }
          if (surface) pendingStepOff = Math.random() < 0.5;
          else pendingPeek = true;
          if (Math.abs(side - x.value) < 1) finishWalk();
          else startWalk(side);
          return;
        }
        const target = roll < 0.85 ? pickWalkTarget(Math.random, x.value, [min, max], panelSpan()) : null;
        if (target === null) scheduleBehavior();
        else startWalk(target);
      });
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
      x.value = clamp(x.value + direction * charWidth.value * 0.6, range[0], range[1]);
      startFall(left.el);
    }
    function scheduleBlink() {
      setTimer("blink", randomBetween(2500, 6e3), () => {
        if (motionAllowed() && visible() && pose.value === "idle") {
          blinking.value = true;
          setTimer("blink-end", 140, () => {
            blinking.value = false;
          });
        }
        scheduleBlink();
      });
    }
    function markActivity() {
      if (dozing.value) {
        dozing.value = false;
        scheduleBehavior();
      }
      setTimer("doze", DOZE_AFTER, () => {
        if (!onGround()) return;
        settle();
        dozing.value = true;
        clearTimer("behavior");
      });
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
    function landing(exclude = null) {
      const view = viewport();
      const boxes = roam() === "surfaces" ? querySurfaces(rootEl.value, view, charHeight.value, hostState?.panelRect ?? null).filter(
        (box) => box.el !== exclude
      ) : [];
      return computeLanding(roam(), boxes, { x: x.value, y: y.value }, view, size());
    }
    function startFall(exclude = null) {
      detachSurface();
      if (roam() === "free") {
        const view = freeBounds(viewport(), ...sizePair());
        x.value = clamp(x.value, ...view.x);
        y.value = clamp(y.value, ...view.y);
        land(false);
        return;
      }
      fallTarget = landing(exclude);
      if (!motionAllowed() || !visible() || y.value >= fallTarget.y) {
        land(false);
        return;
      }
      hopVx = 0;
      hopTargetX = null;
      motion.value = "fall";
      velocity = 0;
      bounced = false;
      ensureLoop();
    }
    function land(animated) {
      velocity = 0;
      rising.value = false;
      sink.value = 0;
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
      if (animated) {
        motion.value = "sit";
        setTimer("sit", SIT_DURATION, () => {
          if (motion.value === "sit") motion.value = "idle";
          scheduleBehavior();
        });
      } else {
        motion.value = "idle";
        scheduleBehavior();
      }
      if (saveOnLand) {
        saveOnLand = false;
        requestSave();
      }
      queueAnchor();
      if (pendingShelter !== null) {
        const depth = pendingShelter;
        pendingShelter = null;
        clearTimer("sit");
        beginShelter(depth, !animated);
        return;
      }
      const delay = droppedByUser ? DROP_CLEAR_DELAY : 0;
      droppedByUser = false;
      scheduleClearance(animated ? Math.max(delay, SIT_DURATION + 50) : delay);
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
        surfaceObserver.observe(document.body, { subtree: true, childList: true, attributes: true });
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
      const box = measureSurface(current.el);
      const result = checkSupport(
        current,
        box && surfaceVisible(current.el) ? box : null,
        x.value + charWidth.value / 2,
        viewport(),
        charHeight.value,
        hostState?.panelRect ?? null
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
    function rectAt(left, top, depth = 0) {
      const hidden = Math.round(charHeight.value * depth);
      return { x: left, y: top + hidden, width: charWidth.value, height: charHeight.value - hidden };
    }
    function checkClearance() {
      if (disposed || !ready.value || !visible()) return;
      if (sheltering) {
        recheckShelter();
        return;
      }
      if (motion.value !== "idle") return;
      const instant = initialPlacement || !motionAllowed();
      initialPlacement = false;
      const view = viewport();
      const body = charWidth.value * charHeight.value;
      const covers = (rect, standingOn2) => coversControlAt(rect, rootEl.value, view, standingOn2, body);
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
      goShelter(covers, instant);
    }
    function findOtherSurface(covers) {
      if (roam() !== "surfaces" && !surface) return null;
      const view = viewport();
      const options = [];
      if (surface) options.push({ y: ground(), bounds: xBounds(view, charWidth.value), surface: null });
      if (roam() === "surfaces") {
        const columns = [x.value + charWidth.value / 2, view.width * 0.25, view.width * 0.75];
        for (const box of surfacesNear(rootEl.value, view, charHeight.value, hostState?.panelRect ?? null, columns)) {
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
    function goShelter(covers, instant) {
      const edge = nearestEdge(x.value, xBounds(viewport(), charWidth.value));
      const floorY = ground();
      const depth = pickShelterDepth((level) => !covers(rectAt(edge, floorY, level), null));
      pendingShelter = depth;
      if (instant || Math.abs(edge - x.value) < 1 && Math.abs(floorY - y.value) < 1 && !surface) {
        pendingShelter = null;
        detachSurface();
        x.value = edge;
        y.value = floorY;
        beginShelter(depth, true);
        return;
      }
      moveTo(edge, floorY, null, false);
    }
    function beginShelter(depth, instant) {
      sheltering = true;
      motion.value = "peek";
      facingLeft.value = x.value > (xBounds(viewport(), charWidth.value)[0] + xBounds(viewport(), charWidth.value)[1]) / 2;
      peekTarget = Math.round(charHeight.value * depth);
      if (instant || !motionAllowed()) {
        sink.value = peekTarget;
        queueAnchor();
      } else ensureLoop();
      syncSurfacePoll();
    }
    function recheckShelter() {
      const view = viewport();
      const body = charWidth.value * charHeight.value;
      const covers = (depth2) => coversControlAt(rectAt(x.value, ground(), depth2), rootEl.value, view, null, body);
      if (!covers(0)) {
        sheltering = false;
        peekTarget = 0;
        if (motionAllowed()) ensureLoop();
        else {
          sink.value = 0;
          motion.value = "idle";
          queueAnchor();
          scheduleBehavior();
        }
        return;
      }
      const current = peekTarget / charHeight.value;
      if (!covers(current)) return;
      const depth = pickShelterDepth((level) => level > current && !covers(level));
      if (depth <= current) return;
      peekTarget = Math.round(charHeight.value * depth);
      if (motionAllowed()) ensureLoop();
      else {
        sink.value = peekTarget;
        queueAnchor();
      }
    }
    function moveTo(targetX, targetY, target, instant) {
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
      detachSurface();
      const { vx, vy } = hopVelocity(
        { x: x.value, y: y.value },
        { x: targetX, y: targetY },
        GRAVITY,
        charHeight.value * HOP_LIFT_RATIO
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
      const value = { roam: roam(), xRatio, yRatio };
      const key = JSON.stringify(value);
      if (key === lastSaved) return;
      lastSaved = key;
      lastSaveAt = Date.now();
      props.pet?.storage?.set?.(value)?.catch?.(() => console.warn("[AgentPets] position not saved"));
    }
    function relayout() {
      if (motion.value === "drag" || motion.value === "fall") {
        x.value = clamp(x.value, 0, Math.max(0, viewport().width - charWidth.value));
        y.value = clamp(y.value, 0, ground());
        queueAnchor();
        return;
      }
      if (roam() === "free") {
        const view = freeBounds(viewport(), ...sizePair());
        x.value = clamp(x.value, ...view.x);
        y.value = clamp(y.value, ...view.y);
        queueAnchor();
        return;
      }
      if (surface) {
        checkSurface();
        if (!surface) return;
      } else y.value = ground();
      const range = bounds();
      x.value = clamp(x.value, range[0], range[1]);
      const span = panelSpan();
      if (!sheltering && isBlocked(x.value, span)) {
        const escaped = escapeSpan(x.value, span, range);
        settle();
        if (motionAllowed() && visible() && Math.abs(escaped - x.value) > 1) startWalk(escaped);
        else x.value = escaped;
      }
      queueAnchor();
    }
    function applySettings(value) {
      const before = settings.value.roam;
      settings.value = normalizeSettings(value);
      if (ready.value && settings.value.roam !== before && motion.value !== "drag") {
        settle();
        saveOnLand = true;
        startFall();
        return;
      }
      relayout();
    }
    function onHostState(state) {
      const before = hostState;
      hostState = state;
      available.value = state.available;
      const resized = !!before && (before.viewport.width !== state.viewport.width || before.viewport.height !== state.viewport.height || before.viewport.keyboardInset !== state.viewport.keyboardInset || before.isMobile !== state.isMobile);
      isMobile.value = state.isMobile;
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
      if (state.motionAllowed && before?.motionAllowed === false) scheduleBehavior();
      syncVisibility();
      syncSurfacePoll();
      if (resized) scheduleClearance(RESIZE_CLEAR_DELAY);
      if (ready.value) relayout();
    }
    function freezeMotion() {
      stopLoop();
      clearTimer("behavior");
      clearTimer("peek");
      walkTarget = null;
      walkPhase.value = 0;
      pendingPeek = false;
      pendingStepOff = false;
      pendingShelter = null;
      blinking.value = false;
      if (sheltering) {
        sink.value = peekTarget;
        queueAnchor();
        return;
      }
      sink.value = 0;
      peekTarget = 0;
      if (motion.value === "fall") land(false);
      else if (motion.value === "walk" || motion.value === "peek") {
        motion.value = "idle";
        queueAnchor();
      }
    }
    function syncVisibility() {
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
    }
    function onHostEvent(event) {
      markActivity();
      const next = eventPose(event.name);
      if (next) playTransient(next.pose, next.duration);
    }
    function onSettingsEvent(event) {
      if (props.pluginId && event.source !== props.pluginId) return;
      applySettings(event.data);
    }
    function onPointerDown(event) {
      if (event.button !== 0 || press) return;
      markActivity();
      press = {
        id: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        offsetX: event.clientX - x.value,
        offsetY: event.clientY - (y.value + sink.value),
        dragging: false
      };
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
      window.addEventListener("pointercancel", onPointerCancel);
    }
    function onPointerMove(event) {
      if (!press || event.pointerId !== press.id) return;
      if (!press.dragging) {
        if (Math.hypot(event.clientX - press.startX, event.clientY - press.startY) < DRAG_THRESHOLD) return;
        press.dragging = true;
        settle();
        stopLoop();
        detachSurface();
        clearTimer("behavior");
        clearTimer("sit");
        clearTimer("clearance");
        transient.value = null;
        sink.value = 0;
        peekTarget = 0;
        sheltering = false;
        pendingShelter = null;
        hopVx = 0;
        hopTargetX = null;
        velocity = 0;
        fallTarget = null;
        motion.value = "drag";
        syncSurfacePoll();
        props.pet?.setInteracting?.(true);
      }
      event.preventDefault();
      const view = viewport();
      x.value = clamp(event.clientX - press.offsetX, 0, Math.max(0, view.width - charWidth.value));
      y.value = clamp(event.clientY - press.offsetY, 0, ground());
      facingLeft.value = false;
      queueAnchor();
    }
    function releasePointer() {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerCancel);
    }
    function finishDrag() {
      props.pet?.setInteracting?.(false);
      droppedByUser = true;
      saveOnLand = true;
      x.value = clamp(x.value, ...xBounds(viewport(), charWidth.value));
      motion.value = "idle";
      syncSurfacePoll();
      startFall();
    }
    function onPointerUp(event) {
      if (!press || event.pointerId !== press.id) return;
      const dragged = press.dragging;
      press = null;
      releasePointer();
      if (!dragged) return;
      suppressClick = true;
      window.setTimeout(() => {
        suppressClick = false;
      }, 0);
      finishDrag();
    }
    function onPointerCancel(event) {
      if (!press || event.pointerId !== press.id) return;
      const dragged = press.dragging;
      press = null;
      releasePointer();
      if (dragged) finishDrag();
    }
    function onActivate() {
      if (suppressClick) {
        suppressClick = false;
        return;
      }
      markActivity();
      props.agent?.open?.();
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
      if (!hostState || surface) relayout();
      if (!hostState) scheduleClearance(RESIZE_CLEAR_DELAY);
    }
    onMounted(async () => {
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
      }
      document.addEventListener("visibilitychange", onVisibilityChange);
      window.addEventListener("resize", onWindowResize);
      cleanups.push(() => document.removeEventListener("visibilitychange", onVisibilityChange));
      cleanups.push(() => window.removeEventListener("resize", onWindowResize));
      const [loaded, stored] = await Promise.all([loadSettings(props.api, props.pluginId), readStoredPosition()]);
      if (disposed) return;
      settings.value = loaded;
      restorePosition(stored);
      ready.value = true;
      syncSurfacePoll();
      reportAnchor();
      scheduleBlink();
      markActivity();
      scheduleBehavior();
    });
    onBeforeUnmount(() => {
      if (timers.has("save")) writePosition();
      disposed = true;
      stopLoop();
      pauseSurfaceWatch();
      if (anchorFrame) window.cancelAnimationFrame(anchorFrame);
      anchorFrame = 0;
      for (const id of timers.values()) window.clearTimeout(id);
      timers.clear();
      releasePointer();
      if (press?.dragging) props.pet?.setInteracting?.(false);
      press = null;
      for (const cleanup of cleanups.splice(0)) cleanup();
      props.pet?.setBubbleAnchor?.(null);
    });
    return (_ctx, _cache) => {
      return _openBlock(), _createElementBlock("div", {
        ref_key: "rootEl",
        ref: rootEl,
        class: "agent-pet-ying",
        "data-pose": pose.value,
        "data-motion": motion.value,
        "data-roam": settings.value.roam
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
            class: _normalizeClass(["agent-pet-ying__frames", { "agent-pet-ying__frames--flip": facingLeft.value, "agent-pet-ying__frames--pending": !displayed.value }]),
            "data-frame": displayed.value ?? void 0
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
          ], 10, _hoisted_3)
        ], 44, _hoisted_2), [
          [_vShow, ready.value]
        ])
      ], 8, _hoisted_1);
    };
  }
});

const AgentPet = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-6be633d5"]]);

export { AgentPet as default };
