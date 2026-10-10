import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { D as DEFAULT_SETTINGS, S as SETTINGS_EVENT, l as loadSettings, n as normalizeSettings, _ as _export_sfc } from './_plugin-vue_export-helper-_cxh9xlI.js';

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
function blockedSpan(panel, ground, charWidth) {
  if (!panel || panel.width <= 0 || panel.height <= 0) return null;
  if (panel.y + panel.height <= ground) return null;
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
  if (input.motion === "walk") return input.walkPhase ? "walk2" : "walk1";
  if (input.dozing) return "doze";
  if (input.blinking) return "blink";
  return "idle";
}

const {defineComponent:_defineComponent} = await importShared('vue');

const {normalizeClass:_normalizeClass,createElementVNode:_createElementVNode,vShow:_vShow,withModifiers:_withModifiers,normalizeStyle:_normalizeStyle,withDirectives:_withDirectives,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');

const _hoisted_1 = ["data-pose", "data-motion"];
const _hoisted_2 = ["aria-label"];
const _hoisted_3 = ["src"];
const {computed,onBeforeUnmount,onMounted,ref} = await importShared('vue');
const BASE_HEIGHT = 120;
const BASE_WALK_SPEED = 70;
const BASE_STEP_INTERVAL = 0.2;
const GRAVITY = 2600;
const DRAG_THRESHOLD = 6;
const SIT_DURATION = 900;
const DOZE_AFTER = 9e4;
const PEEK_RATIO = 0.5;
const PEEK_SPEED = 160;
const DEFAULT_RATIO = 0.88;
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
    let hostState = null;
    let documentVisible = typeof document === "undefined" || document.visibilityState !== "hidden";
    let rafId = 0;
    let lastFrame = 0;
    let anchorFrame = 0;
    let lastAnchor = null;
    let walkTarget = null;
    let walkClock = 0;
    let velocity = 0;
    let bounced = false;
    let peekTarget = 0;
    let lastSavedRatio = -1;
    let suppressClick = false;
    let pendingPeek = false;
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
    const available = ref(true);
    const label = computed(() => available.value ? "打开助手（小映）" : "小映（助手未启用）");
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
    function viewport() {
      return readViewport(hostState);
    }
    function ground() {
      return groundTop(viewport(), charHeight.value);
    }
    function bounds() {
      return xBounds(viewport(), charWidth.value);
    }
    function panelSpan() {
      return blockedSpan(hostState?.panelRect ?? null, ground(), charWidth.value);
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
      if (walkTarget === null) {
        finishWalk();
        return;
      }
      const direction = Math.sign(walkTarget - x.value);
      const next = x.value + direction * BASE_WALK_SPEED * settings.value.speed * dt;
      if (isBlocked(next, panelSpan())) {
        finishWalk();
        return;
      }
      walkClock += dt;
      walkPhase.value = Math.floor(walkClock / (BASE_STEP_INTERVAL / settings.value.speed)) % 2;
      const arrived = direction === 0 || (direction > 0 ? next >= walkTarget : next <= walkTarget);
      x.value = arrived ? walkTarget : next;
      if (arrived) finishWalk();
    }
    function stepFall(dt) {
      velocity += GRAVITY * dt;
      y.value += velocity * dt;
      rising.value = velocity < 0;
      const floor = ground();
      if (y.value < floor) return;
      y.value = floor;
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
    function startWalk(target) {
      walkTarget = target;
      walkClock = 0;
      facingLeft.value = target < x.value;
      motion.value = "walk";
      ensureLoop();
    }
    function finishWalk() {
      walkTarget = null;
      walkPhase.value = 0;
      if (motion.value === "walk") motion.value = "idle";
      const after = pendingPeek;
      pendingPeek = false;
      if (after) beginPeek();
      else scheduleBehavior();
      savePosition();
    }
    function beginPeek() {
      if (!motionAllowed()) return;
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
    }
    function calm() {
      return motion.value === "idle" && !transient.value && !sustained.value && !dozing.value && motionAllowed() && visible();
    }
    function scheduleBehavior() {
      clearTimer("behavior");
      if (!calm()) return;
      setTimer("behavior", randomBetween(6e3, 14e3), () => {
        if (!calm()) return;
        const [min, max] = bounds();
        const roll = Math.random();
        if (roll < 0.22) {
          const side = Math.random() < 0.5 ? min : max;
          const span = panelSpan();
          if (isBlocked(side, span) || Math.abs(side - x.value) < 1) {
            if (!isBlocked(side, span)) beginPeek();
            else scheduleBehavior();
            return;
          }
          pendingPeek = true;
          startWalk(side);
          return;
        }
        const target = roll < 0.85 ? pickWalkTarget(Math.random, x.value, [min, max], panelSpan()) : null;
        if (target === null) scheduleBehavior();
        else startWalk(target);
      });
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
    function land(animated) {
      velocity = 0;
      rising.value = false;
      y.value = ground();
      sink.value = 0;
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
    function savePosition() {
      const ratio = Math.round(xToRatio(x.value, bounds()) * 1e3) / 1e3;
      if (Math.abs(ratio - lastSavedRatio) < 5e-3) return;
      lastSavedRatio = ratio;
      const value = { xRatio: ratio };
      props.pet?.storage?.set?.(value)?.catch?.(() => console.warn("[AgentPetYing] position not saved"));
    }
    function relayout() {
      const range = bounds();
      if (motion.value === "drag") {
        x.value = clamp(x.value, 0, Math.max(0, viewport().width - charWidth.value));
        y.value = clamp(y.value, 0, ground());
        queueAnchor();
        return;
      }
      x.value = clamp(x.value, range[0], range[1]);
      if (onGround()) y.value = ground();
      const span = panelSpan();
      if (onGround() && isBlocked(x.value, span)) {
        const escaped = escapeSpan(x.value, span, range);
        settle();
        if (motionAllowed() && visible() && Math.abs(escaped - x.value) > 1) startWalk(escaped);
        else x.value = escaped;
      }
      queueAnchor();
    }
    function applySettings(value) {
      settings.value = normalizeSettings(value);
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
      relayout();
    }
    function freezeMotion() {
      stopLoop();
      clearTimer("behavior");
      clearTimer("peek");
      walkTarget = null;
      walkPhase.value = 0;
      pendingPeek = false;
      sink.value = 0;
      peekTarget = 0;
      blinking.value = false;
      if (motion.value === "walk" || motion.value === "peek" || motion.value === "fall") land(false);
    }
    function syncVisibility() {
      if (!visible()) {
        stopLoop();
        clearTimer("behavior");
        if (motion.value === "fall") land(false);
        return;
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
        clearTimer("behavior");
        clearTimer("sit");
        transient.value = null;
        sink.value = 0;
        peekTarget = 0;
        velocity = 0;
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
      x.value = clamp(x.value, ...bounds());
      if (motionAllowed() && visible()) {
        motion.value = "fall";
        velocity = 0;
        bounced = false;
        ensureLoop();
      } else land(false);
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
    async function restorePosition() {
      let ratio = DEFAULT_RATIO;
      try {
        const stored = await props.pet?.storage?.get?.();
        if (stored && typeof stored.xRatio === "number" && Number.isFinite(stored.xRatio)) ratio = stored.xRatio;
      } catch {
        console.warn("[AgentPetYing] position unavailable");
      }
      if (disposed) return;
      lastSavedRatio = ratio;
      x.value = ratioToX(ratio, bounds());
      y.value = ground();
    }
    function onVisibilityChange() {
      documentVisible = document.visibilityState !== "hidden";
      syncVisibility();
    }
    function onWindowResize() {
      if (!hostState) relayout();
    }
    onMounted(async () => {
      preloadFrames();
      const agent = props.agent;
      if (agent?.subscribe) cleanups.push(agent.subscribe(onHostState));
      else hostState = null;
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
      const [loaded] = await Promise.all([loadSettings(props.api, props.pluginId), restorePosition()]);
      if (disposed) return;
      settings.value = loaded;
      relayout();
      ready.value = true;
      reportAnchor();
      scheduleBlink();
      markActivity();
      scheduleBehavior();
    });
    onBeforeUnmount(() => {
      disposed = true;
      stopLoop();
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
        class: "agent-pet-ying",
        "data-pose": pose.value,
        "data-motion": motion.value
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
            class: _normalizeClass(["agent-pet-ying__frame", { "agent-pet-ying__frame--flip": facingLeft.value }]),
            src: src.value,
            alt: "",
            draggable: "false"
          }, null, 10, _hoisted_3)
        ], 44, _hoisted_2), [
          [_vShow, ready.value]
        ])
      ], 8, _hoisted_1);
    };
  }
});

const AgentPet = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-d7774533"]]);

export { AgentPet as default };
