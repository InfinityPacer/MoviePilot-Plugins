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
  const result = [];
  const elements = document.querySelectorAll(SURFACE_SELECTOR);
  const count = Math.min(elements.length, MAX_SURFACE_CANDIDATES);
  for (let index = 0; index < count; index += 1) {
    const el = elements[index];
    if (layer && (layer.contains(el) || el.contains(layer))) continue;
    const box = measureSurface(el);
    if (!box || !standable(box, viewport, charHeight, panel) || !surfaceVisible(el)) continue;
    if (!surfaceUnobstructed(el, box, layer, viewport.width)) continue;
    result.push({ ...box, el });
  }
  return result;
}

const {defineComponent:_defineComponent} = await importShared('vue');

const {normalizeClass:_normalizeClass,createElementVNode:_createElementVNode,vShow:_vShow,withModifiers:_withModifiers,normalizeStyle:_normalizeStyle,withDirectives:_withDirectives,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');

const _hoisted_1 = ["data-pose", "data-motion", "data-roam"];
const _hoisted_2 = ["aria-label"];
const _hoisted_3 = ["src"];
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
const DEFAULT_RATIO = 0.88;
const SURFACE_CHECK_INTERVAL = 500;
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
    let lastSaved = "";
    let suppressClick = false;
    let pendingPeek = false;
    let pendingStepOff = false;
    let surface = null;
    let surfaceFrame = 0;
    let surfaceObserver = null;
    let surfacePoll = 0;
    let disposed = false;
    let press = null;
    const timers = /* @__PURE__ */ new Map();
    const cleanups = [];
    const charHeight = computed(() => BASE_HEIGHT * settings.value.scale);
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
    const src = computed(() => frameUrl(pose.value));
    const label = computed(() => available.value ? "打开助手（小映）" : "小映（助手未启用）");
    const shownSrc = ref("");
    const hasFrame = ref(false);
    let lastGoodSrc = "";
    const failedAt = /* @__PURE__ */ new Map();
    function pickFrame(next) {
      const failed = failedAt.get(next);
      if (failed !== void 0 && Date.now() - failed < FRAME_RETRY_AFTER) return;
      shownSrc.value = next;
    }
    watch(src, pickFrame, { immediate: true });
    function onFrameLoad() {
      lastGoodSrc = shownSrc.value;
      failedAt.delete(shownSrc.value);
      hasFrame.value = true;
    }
    function onFrameError() {
      failedAt.set(shownSrc.value, Date.now());
      if (lastGoodSrc && lastGoodSrc !== shownSrc.value) shownSrc.value = lastGoodSrc;
      else hasFrame.value = false;
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
      const speed = BASE_WALK_SPEED * settings.value.speed * settings.value.scale * (roam() === "free" ? FREE_SPEED_RATIO : 1);
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
      rising.value = velocity < 0;
      if (y.value < target) return;
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
      savePosition();
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
        savePosition();
      }
      if (motion.value === "peek") {
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
      motion.value = "fall";
      velocity = 0;
      bounced = false;
      ensureLoop();
    }
    function land(animated) {
      velocity = 0;
      rising.value = false;
      sink.value = 0;
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
      savePosition();
      queueAnchor();
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
      const wanted = !!surface && !!surfaceObserver && visible() && motionAllowed();
      if (wanted && !surfacePoll) surfacePoll = window.setInterval(checkSurface, SURFACE_CHECK_INTERVAL);
      if (!wanted && surfacePoll) {
        window.clearInterval(surfacePoll);
        surfacePoll = 0;
      }
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
    function savePosition() {
      const view = viewport();
      const xRatio = Math.round(xToRatio(x.value, xBounds(view, charWidth.value)) * 1e3) / 1e3;
      const yRatio = Math.round(xToRatio(y.value, [view.safeArea.top, ground()]) * 1e3) / 1e3;
      const value = { roam: roam(), xRatio, yRatio };
      const key = JSON.stringify(value);
      if (key === lastSaved) return;
      lastSaved = key;
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
      if (isBlocked(x.value, span)) {
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
        startFall();
        return;
      }
      relayout();
    }
    function onHostState(state) {
      const before = hostState;
      hostState = state;
      available.value = state.available;
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
      sink.value = 0;
      peekTarget = 0;
      blinking.value = false;
      if (motion.value === "fall") land(false);
      else if (motion.value === "walk" || motion.value === "peek") {
        motion.value = "idle";
        savePosition();
        queueAnchor();
      }
    }
    function syncVisibility() {
      if (!visible()) {
        stopLoop();
        clearTimer("behavior");
        pauseSurfaceWatch();
        if (motion.value === "fall") land(false);
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
        transient.value = null;
        sink.value = 0;
        peekTarget = 0;
        velocity = 0;
        fallTarget = null;
        motion.value = "drag";
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
      x.value = clamp(x.value, ...xBounds(viewport(), charWidth.value));
      motion.value = "idle";
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
    function preloadFrames() {
      for (const name of POSES) {
        const image = new Image();
        image.src = frameUrl(name);
        if (name === "idle") {
          image.onload = () => {
            if (image.naturalWidth && image.naturalHeight) {
              aspect.value = image.naturalWidth / image.naturalHeight;
              relayout();
            }
          };
        }
      }
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
    }
    onMounted(async () => {
      preloadFrames();
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
      reportAnchor();
      scheduleBlink();
      markActivity();
      scheduleBehavior();
    });
    onBeforeUnmount(() => {
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
          _createElementVNode("img", {
            class: _normalizeClass(["agent-pet-ying__frame", { "agent-pet-ying__frame--flip": facingLeft.value, "agent-pet-ying__frame--pending": !hasFrame.value }]),
            src: shownSrc.value,
            alt: "",
            draggable: "false",
            onLoad: onFrameLoad,
            onError: onFrameError
          }, null, 42, _hoisted_3)
        ], 44, _hoisted_2), [
          [_vShow, ready.value]
        ])
      ], 8, _hoisted_1);
    };
  }
});

const AgentPet = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-2fd17dde"]]);

export { AgentPet as default };
