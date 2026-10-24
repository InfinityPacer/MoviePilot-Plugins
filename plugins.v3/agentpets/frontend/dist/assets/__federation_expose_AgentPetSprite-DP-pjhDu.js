import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { L as LANDMARKS, c as calibrationPoint, a as suggestedLandmark, b as sameCalibration, m as moveCalibrationPoint, _ as _export_sfc, d as BUILTIN_PACK_ID, e as BUILTIN_PACK, f as builtinAsset, r as resolveAction, p as parseCalibration, g as calibrationForAction, B as BUILTIN_PACKS, h as calibrationEye, i as mirrorFace, j as calibrationLayout, k as framePosition, o as onEditorPresence, P as PACK_UPDATED_EVENT, v as validatePack, w as withCodexStageActions } from './_plugin-vue_export-helper-Cx9XzNqS.js';
import { u as useStartupGreeting, t as travelFrame, p as phaseFrame, g as greetingPlayback, Y as YING_PACK, f as frameUrl, l as loadBuiltinCalibration, w as withLoadTimeout, b as loadImage } from './playback-Ct5mtRW-.js';

const {defineComponent:_defineComponent$1} = await importShared('vue');

const {normalizeStyle:_normalizeStyle$1,createElementVNode:_createElementVNode$1,renderList:_renderList$1,Fragment:_Fragment$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,toDisplayString:_toDisplayString,withModifiers:_withModifiers,normalizeClass:_normalizeClass$1,createCommentVNode:_createCommentVNode$1} = await importShared('vue');

const _hoisted_1$1 = ["aria-label", "disabled", "data-landmark", "data-placed", "onPointerdown", "onKeydown"];
const _hoisted_2 = {
  key: 0,
  role: "status",
  class: "ap-landmarks__error"
};
const {computed: computed$1,onBeforeUnmount: onBeforeUnmount$1,ref: ref$1,watch: watch$1} = await importShared('vue');
const _sfc_main$1 = /* @__PURE__ */ _defineComponent$1({
  __name: "CalibrationMarkers",
  props: {
    modelValue: {},
    disabled: { type: Boolean },
    zoom: {}
  },
  emits: ["update:modelValue"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const root = ref$1(null);
    const error = ref$1("");
    const labels = { left_eye: "画面左眼", right_eye: "画面右眼", head_top: "头顶" };
    const markers = computed$1(
      () => LANDMARKS.map((key) => ({
        key,
        label: labels[key],
        placed: !!calibrationPoint(props.modelValue, key),
        point: calibrationPoint(props.modelValue, key) ?? suggestedLandmark(props.modelValue, key)
      }))
    );
    let drag = null;
    function place(key, x, y) {
      if (props.disabled) return;
      try {
        const next = moveCalibrationPoint(props.modelValue, key, { x, y });
        if (drag) drag.last = next;
        emit("update:modelValue", next);
        error.value = "";
      } catch (reason) {
        error.value = reason.message;
      }
    }
    function move(event) {
      if (!drag || event.pointerId !== drag.id) return;
      const rect = root.value?.getBoundingClientRect();
      if (!rect?.width || !rect.height) return;
      event.preventDefault();
      place(drag.key, (event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height);
    }
    function stop(rollback = false) {
      const current = drag;
      drag = null;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("blur", blur);
      if (current?.target.hasPointerCapture?.(current.id)) current.target.releasePointerCapture(current.id);
      if (rollback && current && sameCalibration(props.modelValue, current.last))
        emit("update:modelValue", current.original);
    }
    function finish(event) {
      if (drag?.id !== event.pointerId) return;
      move(event);
      stop();
    }
    function cancel(event) {
      if (drag?.id === event.pointerId) stop(true);
    }
    function blur() {
      stop();
    }
    function start(event, key) {
      if (props.disabled || event.button !== 0 || drag) return;
      const target = event.currentTarget;
      target.focus({ preventScroll: true });
      target.setPointerCapture?.(event.pointerId);
      drag = { id: event.pointerId, key, original: { ...props.modelValue }, last: props.modelValue, target };
      window.addEventListener("pointermove", move, { passive: false });
      window.addEventListener("pointerup", finish);
      window.addEventListener("pointercancel", cancel);
      window.addEventListener("blur", blur);
      move(event);
    }
    function keydown(event, key) {
      if (event.key === "Escape") {
        stop(true);
        return;
      }
      const directions = {
        ArrowLeft: [-1, 0],
        ArrowRight: [1, 0],
        ArrowUp: [0, -1],
        ArrowDown: [0, 1]
      };
      const direction = directions[event.key];
      if (!direction || props.disabled) return;
      event.preventDefault();
      const point = calibrationPoint(props.modelValue, key) ?? suggestedLandmark(props.modelValue, key);
      const step = event.shiftKey ? 0.01 : 25e-4;
      place(key, point.x + direction[0] * step, point.y + direction[1] * step);
    }
    watch$1(
      () => props.modelValue,
      (value) => {
        if (drag && !sameCalibration(value, drag.last)) stop();
      },
      { deep: true }
    );
    watch$1(
      () => props.disabled,
      (value) => {
        if (value) stop();
      }
    );
    onBeforeUnmount$1(() => stop());
    return (_ctx, _cache) => {
      return _openBlock$1(), _createElementBlock$1("div", {
        ref_key: "root",
        ref: root,
        class: "ap-landmarks",
        role: "group",
        "aria-label": "双眼与头顶拖拽校准",
        style: _normalizeStyle$1({ "--marker-scale": 1 / (__props.zoom || 1) })
      }, [
        _createElementVNode$1("span", {
          class: "ap-landmarks__top",
          style: _normalizeStyle$1({ top: `${markers.value[2].point.y * 100}%` }),
          "aria-hidden": "true"
        }, null, 4),
        (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(markers.value, (marker) => {
          return _openBlock$1(), _createElementBlock$1("button", {
            key: marker.key,
            type: "button",
            class: _normalizeClass$1(["ap-landmarks__point", [`ap-landmarks__point--${marker.key}`, { "ap-landmarks__point--pending": !marker.placed }]]),
            style: _normalizeStyle$1({ left: `${marker.point.x * 100}%`, top: `${marker.point.y * 100}%` }),
            "aria-label": `${marker.label}校准光圈${marker.placed ? "" : "（待标定）"}`,
            disabled: __props.disabled,
            "data-landmark": marker.key,
            "data-placed": marker.placed,
            onPointerdown: _withModifiers(($event) => start($event, marker.key), ["stop", "prevent"]),
            onClick: _cache[0] || (_cache[0] = _withModifiers(() => {
            }, ["stop"])),
            onKeydown: _withModifiers(($event) => keydown($event, marker.key), ["stop"])
          }, [
            _createElementVNode$1("span", null, _toDisplayString(marker.label), 1)
          ], 46, _hoisted_1$1);
        }), 128)),
        error.value ? (_openBlock$1(), _createElementBlock$1("span", _hoisted_2, _toDisplayString(error.value), 1)) : _createCommentVNode$1("", true)
      ], 4);
    };
  }
});

const CalibrationMarkers = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-0a765626"]]);

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,normalizeStyle:_normalizeStyle,createElementVNode:_createElementVNode,withDirectives:_withDirectives,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock,renderList:_renderList,Fragment:_Fragment,normalizeClass:_normalizeClass} = await importShared('vue');

const _hoisted_1 = ["aria-hidden", "data-pack", "data-action", "data-greeting", "data-greeting-round", "data-frame", "data-mirrored"];
const {computed,onBeforeUnmount,onMounted,ref,shallowRef,watch} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "AgentPetSprite",
  props: {
    agent: { default: null },
    pet: { default: null },
    api: { default: null },
    pluginId: { default: "" },
    sourcePluginId: { default: "" },
    action: { default: null },
    intent: { default: "idle" },
    thinking: { type: Boolean, default: false },
    motionActive: { type: Boolean, default: true },
    mirrorX: { type: Boolean },
    strictPreview: { type: Boolean },
    calibrationOverride: {},
    showCalibration: { type: Boolean },
    editCalibration: { type: Boolean },
    calibrationDisabled: { type: Boolean },
    calibrationZoom: {},
    mappingsOverride: {},
    mappingKey: {},
    nativeAction: {},
    replay: {},
    walkTravel: {},
    framePhase: {},
    playbackRound: {},
    singleCycle: { type: Boolean }
  },
  emits: ["appearance", "calibration-change", "load-state", "pack-ready", "cycle-complete", "action-complete"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const packKey = props.pet?.key || BUILTIN_PACK_ID;
    const pack = ref(BUILTIN_PACK);
    const sheetSrc = ref(builtinAsset("sheet.webp"));
    const ready = ref(packKey === BUILTIN_PACK_ID);
    const cellRatio = ref(1);
    const frameIndex = ref(0);
    let timer = 0;
    let disposed = false;
    let loadVersion = 0;
    let loadController = null;
    let sheetRevision = "";
    let unsubscribe;
    const rendererLoaded = ref(false);
    const editorPaused = ref(false);
    const documentVisible = ref(typeof document === "undefined" || document.visibilityState !== "hidden");
    const hostState = shallowRef(null);
    const greetingCleanups = [];
    const greeting = useStartupGreeting({
      allowed: () => !disposed && props.pet?.mode === "renderer" && !props.strictPreview && !props.editCalibration && !editorPaused.value && props.motionActive && !props.thinking && !props.nativeAction && documentVisible.value && (!props.action || ["idle", "stand", "docked"].includes(props.action)) && props.intent === "idle" && (hostState.value ? hostState.value.available && hostState.value.pageVisible && hostState.value.motionAllowed && hostState.value.phase === "idle" && !hostState.value.thinking : !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches),
      ready: () => rendererLoaded.value,
      stable: () => `${pack.value.id}:${cellRatio.value}:${props.mirrorX}:${JSON.stringify(props.calibrationOverride ?? pack.value.calibration)}`,
      playback: () => greetingPlayback(pack.value, props.mappingsOverride, false)
    });
    const resolved = computed(
      () => resolveAction(
        pack.value,
        greeting.phase.value === "wave" ? "wave" : greeting.phase.value === "pause" ? "idle" : props.action,
        props.intent,
        props.thinking,
        {
          mappings: props.mappingsOverride,
          mappingKey: greeting.phase.value ? void 0 : props.mappingKey,
          nativeAction: props.nativeAction
        }
      )
    );
    watch([() => props.pluginId, () => props.pet?.key, () => props.pet?.mode], () => greeting.cancel());
    const externallyDriven = computed(() => Number.isFinite(props.walkTravel) || Number.isFinite(props.framePhase));
    const frame = computed(() => {
      const frames = resolved.value.action.frames;
      const index = !props.motionActive ? 0 : Number.isFinite(props.walkTravel) ? travelFrame(resolved.value.action, props.walkTravel) : Number.isFinite(props.framePhase) ? phaseFrame(resolved.value.action, props.framePhase) : frameIndex.value;
      return frames[Math.min(index, frames.length - 1)] ?? "idle";
    });
    const baseCalibration = computed(() => parseCalibration(props.calibrationOverride ?? pack.value.calibration));
    const calibration = computed(
      () => calibrationForAction(
        baseCalibration.value,
        pack.value.action_baselines,
        resolved.value.key,
        BUILTIN_PACKS[pack.value.id]?.calibration?.baseline
      )
    );
    const eye = computed(() => {
      const face = calibrationEye(calibration.value);
      return props.mirrorX ? mirrorFace(face) : face;
    });
    const guidePoints = computed(
      () => LANDMARKS.flatMap((key) => {
        const point = calibrationPoint(calibration.value, key);
        return point ? [{ key, ...point, x: props.mirrorX ? 1 - point.x : point.x }] : [];
      })
    );
    const layout = computed(() => calibrationLayout(calibration.value, cellRatio.value));
    const sheetStyle = computed(() => ({
      "background-image": `url(${JSON.stringify(sheetSrc.value)})`,
      "background-size": `${pack.value.grid.cols * 100}% ${pack.value.grid.rows * 100}%`
    }));
    const vSpriteSheet = {
      mounted: (el, { value }) => {
        for (const [key, next] of Object.entries(value)) el.style.setProperty(key, next);
      },
      updated: (el, { value, oldValue }) => {
        for (const [key, next] of Object.entries(value)) if (next !== oldValue?.[key]) el.style.setProperty(key, next);
      }
    };
    const frameStyle = computed(() => {
      const position = framePosition(pack.value, frame.value);
      return {
        ...layout.value.frame,
        backgroundPosition: `${position.x}% ${position.y}%`
      };
    });
    function stop() {
      if (timer) window.clearTimeout(timer);
      timer = 0;
    }
    function play() {
      stop();
      frameIndex.value = 0;
      if (!props.motionActive || !ready.value || disposed || externallyDriven.value) return;
      const { frames, frame_ms: frameMs, frame_durations: durations, loop } = resolved.value.action;
      const greetingRound = greeting.round.value;
      const replay = props.replay ?? 0;
      const playbackRound = props.playbackRound ?? 0;
      const singleCycle = props.singleCycle || playbackRound > 0;
      if (frames.length < 2) return;
      const advance = () => {
        const next = frameIndex.value + 1;
        if (next >= frames.length) {
          greeting.frameComplete(greetingRound);
          emit("cycle-complete", replay);
          if (playbackRound) emit("action-complete", playbackRound);
        }
        if (next >= frames.length && (!loop || singleCycle)) {
          timer = 0;
          return;
        }
        frameIndex.value = next % frames.length;
        timer = window.setTimeout(advance, durations?.[frameIndex.value] ?? frameMs);
      };
      timer = window.setTimeout(advance, durations?.[0] ?? frameMs);
    }
    async function loadPack(key) {
      rendererLoaded.value = false;
      loadController?.abort();
      const controller = new AbortController();
      loadController = controller;
      const signal = controller.signal;
      const version = ++loadVersion;
      const current = () => !disposed && version === loadVersion && !signal.aborted;
      emit("load-state", "loading");
      try {
        const builtin = key === "ying" || Object.hasOwn(BUILTIN_PACKS, key);
        let nextPack = key === "ying" ? YING_PACK : builtin ? BUILTIN_PACKS[key] : BUILTIN_PACK;
        let nextSheet = key === "ying" ? frameUrl("idle") : builtinAsset(nextPack.sheet || "sheet.webp", void 0, builtin ? key : BUILTIN_PACK_ID);
        let nextRevision = "";
        if (builtin) {
          try {
            nextPack = { ...nextPack, calibration: await loadBuiltinCalibration(props.api, props.pluginId, key, signal) };
          } catch {
            if (props.strictPreview && props.api?.get) throw new Error("内置校准读取失败");
          }
        } else {
          if (!props.api?.get) throw new Error("pack API unavailable");
          const instanceId = props.pluginId || "AgentPets";
          const known = ready.value && pack.value.id === key ? sheetRevision : "";
          const response = await withLoadTimeout(
            props.api.get(
              `plugin/${instanceId}/pack?key=${encodeURIComponent(key)}${known ? `&known_sheet=${encodeURIComponent(known)}` : ""}`
            ),
            signal
          );
          const { pack: parsed } = validatePack(response?.data?.pack);
          if (!response?.success || !parsed || !response.data?.sheet_src && (!known || response.data?.sheet_revision !== known))
            throw new Error(response?.message || "invalid pack");
          nextPack = props.pet?.mode === "stage" ? withCodexStageActions(parsed) : parsed;
          nextSheet = response.data.sheet_src || sheetSrc.value;
          nextRevision = response.data.sheet_revision || "";
        }
        const reuseImage = !!nextRevision && nextRevision === sheetRevision && ready.value && nextSheet === sheetSrc.value && nextPack.grid.cols === pack.value.grid.cols && nextPack.grid.rows === pack.value.grid.rows;
        const dimensions = reuseImage ? null : await loadImage(nextSheet, signal);
        if (!current()) return;
        pack.value = nextPack;
        sheetSrc.value = nextSheet;
        sheetRevision = nextRevision;
        if (dimensions) cellRatio.value = dimensions.width / nextPack.grid.cols / (dimensions.height / nextPack.grid.rows);
        ready.value = true;
        rendererLoaded.value = true;
        emit("pack-ready", nextPack);
        emit("load-state", "ready");
      } catch {
        if (!current()) return;
        greeting.cancel();
        console.warn(`[AgentPets] pack ${key} unavailable`);
        ready.value = false;
        sheetRevision = "";
        emit("load-state", "error");
        if (props.strictPreview || key === BUILTIN_PACK_ID) return;
        try {
          const src = builtinAsset("sheet.webp");
          const dimensions = await loadImage(src, signal);
          if (!current()) return;
          pack.value = BUILTIN_PACK;
          sheetSrc.value = src;
          cellRatio.value = dimensions.width / BUILTIN_PACK.grid.cols / (dimensions.height / BUILTIN_PACK.grid.rows);
          ready.value = true;
        } catch {
        }
      }
    }
    watch(
      () => [
        resolved.value.key,
        props.motionActive,
        ready.value,
        pack.value,
        props.replay,
        greeting.round.value,
        props.playbackRound,
        props.singleCycle,
        externallyDriven.value
      ],
      () => play()
    );
    watch(
      [ready, pack, cellRatio, calibration, () => props.mirrorX],
      () => {
        if (ready.value)
          emit("appearance", { name: pack.value.name, aspectRatio: layout.value.aspectRatio, eye: eye.value });
      },
      { immediate: true }
    );
    onMounted(async () => {
      if (props.pet?.mode === "renderer" && !props.strictPreview && !props.editCalibration) {
        greetingCleanups.push(
          onEditorPresence((active) => {
            editorPaused.value = active;
          })
        );
        if (props.agent?.subscribe)
          greetingCleanups.push(
            props.agent.subscribe((state) => {
              hostState.value = state;
            })
          );
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
          const release = props.agent?.on(name, () => greeting.cancel());
          if (release) greetingCleanups.push(release);
        }
        const cancel = () => greeting.cancel();
        const visibility = () => {
          documentVisible.value = document.visibilityState !== "hidden";
        };
        window.addEventListener("pointerdown", cancel, { passive: true });
        window.addEventListener("keydown", cancel);
        window.addEventListener("blur", cancel);
        document.addEventListener("visibilitychange", visibility);
        greetingCleanups.push(() => {
          window.removeEventListener("pointerdown", cancel);
          window.removeEventListener("keydown", cancel);
          window.removeEventListener("blur", cancel);
          document.removeEventListener("visibilitychange", visibility);
        });
        greeting.arm();
      }
      if (!props.strictPreview)
        unsubscribe = props.agent?.on(PACK_UPDATED_EVENT, (event) => {
          if (event.source === props.pluginId && event.data.key === packKey) void loadPack(packKey);
        });
      play();
      await loadPack(packKey);
    });
    onBeforeUnmount(() => {
      disposed = true;
      loadVersion++;
      loadController?.abort();
      unsubscribe?.();
      for (const cleanup of greetingCleanups.splice(0)) cleanup();
      stop();
    });
    return (_ctx, _cache) => {
      return _openBlock(), _createElementBlock("div", {
        class: _normalizeClass(["agent-pet-sprites", { "agent-pet-sprites--stage": __props.pet?.mode === "stage" }]),
        "aria-hidden": __props.editCalibration ? void 0 : true,
        "data-pack": ready.value ? pack.value.id : void 0,
        "data-action": resolved.value.key,
        "data-greeting": _unref(greeting).pending.value ? "pending" : _unref(greeting).phase.value ?? void 0,
        "data-greeting-round": _unref(greeting).round.value || void 0,
        "data-frame": frame.value,
        "data-mirrored": !!__props.mirrorX
      }, [
        ready.value ? (_openBlock(), _createElementBlock("div", {
          key: 0,
          class: _normalizeClass(["agent-pet-sprites__viewport", { "agent-pet-sprites__viewport--guides": __props.showCalibration }]),
          style: _normalizeStyle({ "--agent-pet-sprites-ratio": String(layout.value.aspectRatio) })
        }, [
          _createElementVNode("div", {
            class: "agent-pet-sprites__crop",
            style: _normalizeStyle(__props.mirrorX ? { transform: "scaleX(-1)" } : void 0)
          }, [
            _withDirectives(_createElementVNode("div", {
              class: "agent-pet-sprites__frame",
              style: _normalizeStyle(frameStyle.value)
            }, null, 4), [
              [vSpriteSheet, sheetStyle.value]
            ])
          ], 4),
          __props.editCalibration && (pack.value.codex_version || __props.pet?.mode === "stage") ? (_openBlock(), _createBlock(CalibrationMarkers, {
            key: 0,
            "model-value": calibration.value,
            disabled: __props.calibrationDisabled,
            zoom: __props.calibrationZoom,
            "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => emit("calibration-change", { ...$event, baseline: baseCalibration.value.baseline }))
          }, null, 8, ["model-value", "disabled", "zoom"])) : _createCommentVNode("", true),
          __props.showCalibration && eye.value && !__props.editCalibration ? (_openBlock(), _createElementBlock("span", {
            key: 1,
            class: "agent-pet-sprites__eye",
            style: _normalizeStyle({ left: `${eye.value.x * 100}%`, top: `${eye.value.y * 100}%` })
          }, null, 4)) : _createCommentVNode("", true),
          __props.showCalibration && !__props.editCalibration ? (_openBlock(true), _createElementBlock(_Fragment, { key: 2 }, _renderList(guidePoints.value, (point) => {
            return _openBlock(), _createElementBlock("span", {
              key: point.key,
              class: "agent-pet-sprites__eye",
              style: _normalizeStyle({ left: `${point.x * 100}%`, top: `${point.y * 100}%` })
            }, null, 4);
          }), 128)) : _createCommentVNode("", true)
        ], 6)) : _createCommentVNode("", true)
      ], 10, _hoisted_1);
    };
  }
});

const AgentPetSprite = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-02495848"]]);

export { AgentPetSprite as default };
