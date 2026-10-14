import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { u as unwrap, A as AGENT_HOST_KEY, s as sameSettings, H as HOST_UNSUPPORTED_MESSAGE, l as loadEditor, a as loadHostSelection, b as saveSettings, c as saveMappings, d as saveCalibration } from './host-hLuo8bCd.js';
import { D as DEFAULT_CALIBRATION, p as parseCalibration, m as mappingRows, A as ACTION_LABELS, n as nativeChoices, H as HOST_ACTIONS, h as HOST_INTENTS, s as stageAction, b as sameCalibration, a as sameMappings, P as PACK_UPDATED_EVENT } from './mappings-wSixMRjX.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';
import AgentPet, { P as POSES } from './__federation_expose_AgentPet-CiU2Nd0s.js';
import AgentPetSprite from './__federation_expose_AgentPetSprite-00TQt6P7.js';
import { _ as _sfc_main$5 } from './AgentPetCodex.vue_vue_type_script_setup_true_lang-CMwl71eP.js';
import { a as SCALE_RANGE, b as SPEED_RANGE, D as DEFAULT_SETTINGS, S as SETTINGS_EVENT } from './settings-tnFA6UQD.js';

const {defineComponent:_defineComponent$4} = await importShared('vue');

const {createElementVNode:_createElementVNode$4,resolveComponent:_resolveComponent$4,createVNode:_createVNode$4,createTextVNode:_createTextVNode$4,withCtx:_withCtx$4,unref:_unref$4,renderList:_renderList$2,Fragment:_Fragment$3,openBlock:_openBlock$4,createElementBlock:_createElementBlock$4,toDisplayString:_toDisplayString$4,createBlock:_createBlock$3,createCommentVNode:_createCommentVNode$3} = await importShared('vue');

const _hoisted_1$4 = { class: "ap-calibration" };
const _hoisted_2$4 = { class: "d-flex align-center ga-2 mb-2" };
const _hoisted_3$4 = { class: "ap-calibration__fields" };
const {computed: computed$3,onBeforeUnmount: onBeforeUnmount$2,ref: ref$2} = await importShared('vue');
const _sfc_main$4 = /* @__PURE__ */ _defineComponent$4({
  __name: "CalibrationControls",
  props: {
    modelValue: {},
    packId: {},
    api: {},
    pluginId: {},
    disabled: { type: Boolean }
  },
  emits: ["update:modelValue"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const busy = ref$2(false);
    const error = ref$2("");
    let alive = true;
    onBeforeUnmount$2(() => {
      alive = false;
    });
    const fields = [
      { key: "left", title: "左边界", min: 0, max: 90 },
      { key: "right", title: "右边界", min: 10, max: 100 },
      { key: "top", title: "上边界", min: 0, max: 90 },
      { key: "bottom", title: "下边界", min: 10, max: 100 },
      { key: "baseline", title: "脚底基线", min: 1, max: 100 },
      { key: "offset_x", title: "水平偏移", min: -25, max: 25 },
      { key: "offset_y", title: "垂直偏移", min: -25, max: 25 }
    ];
    const disabled = computed$3(() => props.disabled || busy.value);
    function update(key, percent) {
      try {
        const next = { ...props.modelValue, [key]: Number(percent) / 100 };
        if (key === "bottom") next.baseline = Math.min(next.baseline, next.bottom);
        error.value = "";
        emit("update:modelValue", parseCalibration(next));
      } catch (reason) {
        error.value = reason.message;
      }
    }
    async function suggest() {
      if (!props.api || busy.value) return;
      const id = props.packId;
      const instance = props.pluginId;
      const baseline = JSON.stringify(props.modelValue);
      busy.value = true;
      error.value = "";
      try {
        const response = await props.api.get(`plugin/${instance}/packs/calibration/suggest?key=${encodeURIComponent(id)}`);
        if (!alive || id !== props.packId || instance !== props.pluginId || baseline !== JSON.stringify(props.modelValue))
          return;
        emit("update:modelValue", parseCalibration(unwrap(response)));
      } catch (reason) {
        if (alive && id === props.packId && instance === props.pluginId) error.value = reason.message;
      } finally {
        if (alive) busy.value = false;
      }
    }
    return (_ctx, _cache) => {
      const _component_v_spacer = _resolveComponent$4("v-spacer");
      const _component_v_btn = _resolveComponent$4("v-btn");
      const _component_v_text_field = _resolveComponent$4("v-text-field");
      const _component_v_alert = _resolveComponent$4("v-alert");
      return _openBlock$4(), _createElementBlock$4("section", _hoisted_1$4, [
        _createElementVNode$4("div", _hoisted_2$4, [
          _cache[3] || (_cache[3] = _createElementVNode$4("strong", null, "显示校准", -1)),
          _createVNode$4(_component_v_spacer),
          _createVNode$4(_component_v_btn, {
            size: "small",
            variant: "text",
            loading: busy.value,
            disabled: disabled.value,
            onClick: suggest
          }, {
            default: _withCtx$4(() => [..._cache[1] || (_cache[1] = [
              _createTextVNode$4("识别建议", -1)
            ])]),
            _: 1
          }, 8, ["loading", "disabled"]),
          _createVNode$4(_component_v_btn, {
            size: "small",
            variant: "text",
            disabled: disabled.value,
            onClick: _cache[0] || (_cache[0] = ($event) => emit("update:modelValue", { ..._unref$4(DEFAULT_CALIBRATION) }))
          }, {
            default: _withCtx$4(() => [..._cache[2] || (_cache[2] = [
              _createTextVNode$4("恢复默认", -1)
            ])]),
            _: 1
          }, 8, ["disabled"])
        ]),
        _cache[4] || (_cache[4] = _createElementVNode$4("p", { class: "text-caption text-medium-emphasis" }, " 坐标为原图单格百分比，所有帧共用。虚线框为显示与拖拽范围，底线为站立线；原图保留，框外内容不显示。点击底部「保存调整」生效，「撤销」放弃草稿。 ", -1)),
        _createElementVNode$4("div", _hoisted_3$4, [
          (_openBlock$4(), _createElementBlock$4(_Fragment$3, null, _renderList$2(fields, (field) => {
            return _createVNode$4(_component_v_text_field, {
              key: field.key,
              label: field.title,
              "model-value": Math.round(__props.modelValue[field.key] * 1e4) / 100,
              type: "number",
              suffix: "%",
              step: 1,
              min: field.min,
              max: field.max,
              density: "compact",
              variant: "outlined",
              "hide-details": "",
              disabled: disabled.value,
              "onUpdate:modelValue": ($event) => update(field.key, Number($event))
            }, null, 8, ["label", "model-value", "min", "max", "disabled", "onUpdate:modelValue"]);
          }), 64))
        ]),
        error.value ? (_openBlock$4(), _createBlock$3(_component_v_alert, {
          key: 0,
          type: "warning",
          variant: "tonal",
          density: "compact",
          class: "mt-2"
        }, {
          default: _withCtx$4(() => [
            _createTextVNode$4(_toDisplayString$4(error.value), 1)
          ]),
          _: 1
        })) : _createCommentVNode$3("", true)
      ]);
    };
  }
});

const CalibrationControls = /* @__PURE__ */ _export_sfc(_sfc_main$4, [["__scopeId", "data-v-b5ba2de4"]]);

const {defineComponent:_defineComponent$3} = await importShared('vue');

const {toDisplayString:_toDisplayString$3,createElementVNode:_createElementVNode$3,resolveComponent:_resolveComponent$3,createVNode:_createVNode$3,createTextVNode:_createTextVNode$3,withCtx:_withCtx$3,renderList:_renderList$1,Fragment:_Fragment$2,openBlock:_openBlock$3,createElementBlock:_createElementBlock$3,unref:_unref$3,createBlock:_createBlock$2} = await importShared('vue');

const _hoisted_1$3 = { class: "ap-mappings" };
const _hoisted_2$3 = { class: "ap-inline mb-2" };
const _hoisted_3$3 = { class: "ap-section-title mb-0" };
const {computed: computed$2} = await importShared('vue');
const _sfc_main$3 = /* @__PURE__ */ _defineComponent$3({
  __name: "ActionMappings",
  props: {
    pack: {},
    mode: {},
    modelValue: {},
    disabled: { type: Boolean }
  },
  emits: ["update:modelValue", "preview"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const rows = computed$2(() => mappingRows(props.mode));
    const groups = computed$2(() => [...new Set(rows.value.map((row) => row.group))]);
    const animations = computed$2(
      () => Object.keys(props.pack.actions).map((value) => ({
        value,
        title: ACTION_LABELS[value] ? `${ACTION_LABELS[value]} · ${value}` : value
      }))
    );
    function set(key, value) {
      const next = { ...props.modelValue };
      if (value) next[key] = value;
      else delete next[key];
      emit("update:modelValue", next);
    }
    function defaultAction(action) {
      return props.pack.actions[action] ? action : "idle";
    }
    return (_ctx, _cache) => {
      const _component_v_spacer = _resolveComponent$3("v-spacer");
      const _component_v_btn = _resolveComponent$3("v-btn");
      const _component_v_select = _resolveComponent$3("v-select");
      const _component_v_expansion_panel_text = _resolveComponent$3("v-expansion-panel-text");
      const _component_v_expansion_panel = _resolveComponent$3("v-expansion-panel");
      const _component_v_expansion_panels = _resolveComponent$3("v-expansion-panels");
      return _openBlock$3(), _createElementBlock$3("section", _hoisted_1$3, [
        _createElementVNode$3("div", _hoisted_2$3, [
          _createElementVNode$3("h2", _hoisted_3$3, "动作映射 · " + _toDisplayString$3(__props.pack.name), 1),
          _createVNode$3(_component_v_spacer),
          _createVNode$3(_component_v_btn, {
            size: "small",
            variant: "text",
            disabled: __props.disabled || !Object.keys(__props.modelValue).length,
            onClick: _cache[0] || (_cache[0] = ($event) => emit("update:modelValue", {}))
          }, {
            default: _withCtx$3(() => [..._cache[1] || (_cache[1] = [
              _createTextVNode$3("恢复全部默认", -1)
            ])]),
            _: 1
          }, 8, ["disabled"])
        ]),
        _cache[2] || (_cache[2] = _createElementVNode$3("p", { class: "ap-muted" }, "选择触发时播放的动画。留空使用原有映射，修改后可试播，点击底部「保存调整」保存。", -1)),
        _createVNode$3(_component_v_expansion_panels, {
          variant: "accordion",
          multiple: ""
        }, {
          default: _withCtx$3(() => [
            (_openBlock$3(true), _createElementBlock$3(_Fragment$2, null, _renderList$1(groups.value, (group) => {
              return _openBlock$3(), _createBlock$2(_component_v_expansion_panel, {
                key: group,
                title: group
              }, {
                default: _withCtx$3(() => [
                  _createVNode$3(_component_v_expansion_panel_text, null, {
                    default: _withCtx$3(() => [
                      (_openBlock$3(true), _createElementBlock$3(_Fragment$2, null, _renderList$1(rows.value.filter((item) => item.group === group), (row) => {
                        return _openBlock$3(), _createElementBlock$3("div", {
                          key: row.key,
                          class: "ap-mappings__row"
                        }, [
                          _createVNode$3(_component_v_select, {
                            "model-value": __props.modelValue[row.key] ?? null,
                            items: animations.value,
                            label: row.label,
                            placeholder: `默认：${_unref$3(ACTION_LABELS)[defaultAction(row.action)] ?? defaultAction(row.action)}`,
                            hint: !__props.pack.actions[row.action] && !__props.modelValue[row.key] ? "素材没有专用动画，默认使用待机" : void 0,
                            "persistent-placeholder": "",
                            "persistent-hint": "",
                            clearable: "",
                            density: "compact",
                            variant: "outlined",
                            disabled: __props.disabled,
                            "onUpdate:modelValue": ($event) => set(row.key, $event)
                          }, null, 8, ["model-value", "items", "label", "placeholder", "hint", "disabled", "onUpdate:modelValue"]),
                          _createVNode$3(_component_v_btn, {
                            icon: "mdi-play-outline",
                            "aria-label": `试播${row.label}`,
                            variant: "text",
                            size: "small",
                            disabled: __props.disabled,
                            onClick: ($event) => emit("preview", __props.modelValue[row.key] ?? defaultAction(row.action), row.label)
                          }, null, 8, ["aria-label", "disabled", "onClick"])
                        ]);
                      }), 128))
                    ]),
                    _: 2
                  }, 1024)
                ]),
                _: 2
              }, 1032, ["title"]);
            }), 128))
          ]),
          _: 1
        })
      ]);
    };
  }
});

const ActionMappingEditor = /* @__PURE__ */ _export_sfc(_sfc_main$3, [["__scopeId", "data-v-62c74c1b"]]);

function windowViewport() {
  return {
    width: window.innerWidth,
    height: window.innerHeight,
    keyboardInset: 0,
    safeArea: { top: 0, right: 0, bottom: 0, left: 0 }
  };
}
function createMockHost(pluginId, onCall) {
  let state = {
    available: true,
    panelOpen: false,
    thinking: false,
    phase: "idle",
    toolName: null,
    pageVisible: true,
    motionAllowed: true,
    reducedMotion: false,
    theme: "light",
    isMobile: window.innerWidth < 600,
    viewport: windowViewport(),
    panelRect: null
  };
  const listeners = /* @__PURE__ */ new Set();
  const handlers = /* @__PURE__ */ new Map();
  const calls = [];
  function record(call) {
    calls.unshift(call);
    calls.splice(20);
  }
  function dispatch(name, source, data = {}) {
    const payload = { name, source, data, at: Date.now() };
    for (const handler of handlers.get(name) ?? []) handler(payload);
  }
  function patch(partial) {
    state = { ...state, ...partial };
    for (const listener of listeners) listener(state);
  }
  const onResize = () => patch({ viewport: { ...state.viewport, width: window.innerWidth, height: window.innerHeight } });
  window.addEventListener("resize", onResize);
  return {
    version: 1,
    calls,
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      listener(state);
      return () => listeners.delete(listener);
    },
    open(options) {
      record(options?.draft ? `open(draft=${options.draft})` : "open()");
      if (!state.available) return;
      if (!state.panelOpen) {
        patch({ panelOpen: true });
        dispatch("agent.panel.open", "host");
      }
    },
    close() {
      record("close()");
      if (state.panelOpen) {
        patch({ panelOpen: false, panelRect: null });
        dispatch("agent.panel.close", "host");
      }
    },
    on(name, handler) {
      const set = handlers.get(name) ?? /* @__PURE__ */ new Set();
      set.add(handler);
      handlers.set(name, set);
      return () => set.delete(handler);
    },
    emit(name, data) {
      if (name.startsWith("agent.")) return;
      dispatch(name, pluginId, data ?? {});
    },
    patch,
    fire(name, data) {
      dispatch(name, "host", data ?? {});
    },
    dispose() {
      window.removeEventListener("resize", onResize);
      listeners.clear();
      handlers.clear();
    }
  };
}
function createMockPet(mode, key, hooks = {}) {
  let stored = null;
  return {
    mode,
    key,
    setBubbleAnchor: (rect) => hooks.onAnchor?.(rect),
    setInteracting: (value) => hooks.onInteracting?.(value),
    storage: {
      get: async () => stored,
      set: async (value) => {
        if (JSON.stringify(value ?? null).length > 16 * 1024) throw new Error("storage value exceeds 16KB");
        stored = value;
      }
    }
  };
}

const {defineComponent:_defineComponent$2} = await importShared('vue');

const {createElementVNode:_createElementVNode$2,toDisplayString:_toDisplayString$2,createTextVNode:_createTextVNode$2,resolveComponent:_resolveComponent$2,withCtx:_withCtx$2,createVNode:_createVNode$2,openBlock:_openBlock$2,createElementBlock:_createElementBlock$2,createCommentVNode:_createCommentVNode$2,Fragment:_Fragment$1,unref:_unref$2,resolveDynamicComponent:_resolveDynamicComponent,createBlock:_createBlock$1,normalizeClass:_normalizeClass,renderSlot:_renderSlot,vShow:_vShow,withDirectives:_withDirectives,renderList:_renderList} = await importShared('vue');

const _hoisted_1$2 = { class: "ap-preview__viewer" };
const _hoisted_2$2 = { class: "ap-preview__header" };
const _hoisted_3$2 = {
  key: 0,
  class: "ap-preview__mode"
};
const _hoisted_4$2 = ["data-roam"];
const _hoisted_5$2 = {
  key: 2,
  class: "ap-preview__entry"
};
const _hoisted_6$1 = { class: "ap-preview__hint" };
const _hoisted_7$1 = {
  key: 0,
  class: "ap-preview__original",
  "aria-label": "原始显示对照"
};
const _hoisted_8$1 = { class: "ap-preview__entry" };
const _hoisted_9$1 = { class: "ap-preview__playback" };
const _hoisted_10$1 = {
  class: "ap-preview__playing",
  role: "status"
};
const _hoisted_11$1 = { class: "ap-inline" };
const _hoisted_12$1 = { class: "ap-preview__editor" };
const _hoisted_13$1 = { class: "ap-preview__scroll" };
const _hoisted_14$1 = { class: "ap-preview__panel" };
const _hoisted_15$1 = { class: "ap-preview__library" };
const _hoisted_16$1 = { class: "ap-inline mb-2" };
const _hoisted_17$1 = { class: "ap-preview__choices" };
const _hoisted_18 = { class: "ap-muted mb-0" };
const _hoisted_19 = {
  key: 1,
  class: "ap-preview__panel ap-muted"
};
const _hoisted_20 = {
  key: 1,
  class: "ap-preview__panel ap-muted"
};
const {computed: computed$1,onBeforeUnmount: onBeforeUnmount$1,onMounted,ref: ref$1,shallowRef,watch: watch$1} = await importShared('vue');
const _sfc_main$2 = /* @__PURE__ */ _defineComponent$2({
  __name: "PetPreview",
  props: {
    pet: {},
    settings: {},
    api: {},
    pluginId: {},
    calibration: {},
    mappings: {},
    disabled: { type: Boolean },
    initialTab: { default: "animations" }
  },
  emits: ["error", "pack-ready", "mappings", "calibration"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const loadedPack = ref$1(null);
    const replay = ref$1(0);
    const original = ref$1(false);
    const editorTab = ref$1(props.initialTab);
    const expanded = ref$1(false);
    const previewMode = ref$1("debug");
    const previewSettings = computed$1(
      () => previewMode.value === "debug" ? { ...props.settings, movement: "fixed", roam: "free" } : props.settings
    );
    const previewMaxSize = ref$1({ width: 280, height: 220 });
    const playing = ref$1("自主动作");
    const previewGroup = ref$1(props.pet.key === "ying" ? "poses" : "native");
    function onPackReady(pack) {
      loadedPack.value = pack;
      emit("pack-ready", pack);
    }
    const failed = ref$1(false);
    function onLoadState(state) {
      failed.value = state === "error";
      emit("error", failed.value);
    }
    const canvas = ref$1(null);
    const mounted = ref$1(false);
    const paused = ref$1(false);
    const action = ref$1("auto");
    const positionVersion = ref$1(0);
    const host = createMockHost(props.pluginId);
    function newContext() {
      const pet = createMockPet(props.pet.mode, props.pet.key);
      if (previewMode.value === "debug") void pet.storage?.set?.({ roam: "free", xRatio: 0.5, yRatio: 0.5 });
      return pet;
    }
    const context = shallowRef(newContext());
    const comparisonContext = computed$1(() => createMockPet("renderer", props.pet.key));
    const poseLabels = {
      idle: "待机",
      blink: "眨眼",
      talk: "说话",
      think: "思考",
      jump: "跳起",
      wave: "招手",
      held: "被拖起",
      fall: "下落",
      sit: "坐下",
      walk1: "行走第1帧",
      walk2: "行走第2帧",
      walk3: "行走第3帧",
      walk4: "行走第4帧",
      doze: "打盹",
      confused: "疑惑",
      alert: "提醒",
      victory: "开心",
      busy: "执行工具"
    };
    const animations = computed$1(() => loadedPack.value ? nativeChoices(loadedPack.value) : []);
    const choices = computed$1(() => {
      if (previewGroup.value === "poses") return POSES.map((value) => ({ value: `pose:${value}`, title: poseLabels[value] }));
      if (previewGroup.value === "actions")
        return HOST_ACTIONS.map((value) => ({ value: `action:${value}`, title: ACTION_LABELS[value] }));
      if (previewGroup.value === "intents")
        return HOST_INTENTS.map((value) => ({ value: `intent:${value}`, title: ACTION_LABELS[value] }));
      if (previewGroup.value === "directions")
        return Object.keys(loadedPack.value?.actions ?? {}).filter((key) => key.startsWith("look-")).map((key) => ({ value: `native:${key}`, title: key.slice(5).replace("-", ".") + "°" }));
      return animations.value.map((item) => ({ value: `native:${item.value}`, title: item.title }));
    });
    const nativeAction = computed$1(() => action.value.startsWith("native:") ? action.value.slice(7) : void 0);
    const rendererAction = computed$1(() => action.value.startsWith("action:") ? action.value.slice(7) : null);
    const rendererIntent = computed$1(() => action.value.startsWith("intent:") ? action.value.slice(7) : "idle");
    const previewPose = computed$1(
      () => nativeAction.value ? "idle" : action.value.startsWith("pose:") ? action.value.slice(5) : void 0
    );
    const events = [
      ["panel.open", "打开助手"],
      ["panel.close", "关闭助手"],
      ["thinking.start", "开始思考"],
      ["thinking.end", "结束思考"],
      ["tool.start", "开始执行工具"],
      ["tool.end", "工具结束"],
      ["awaiting", "等待用户"],
      ["done", "任务完成"],
      ["error", "任务出错"],
      ["preview", "回复预览"],
      ["bubble", "通知气泡"]
    ];
    function playNative(name, trigger) {
      choose(`native:${name}`);
      if (trigger) playing.value = `${trigger} → ${ACTION_LABELS[name] ?? name}`;
    }
    function choose(value) {
      action.value = value;
      playing.value = value === "auto" ? "自主动作" : choices.value.find((item) => item.value === value)?.title ?? value.slice(value.indexOf(":") + 1);
      updateAction();
      replay.value++;
    }
    function fireHost(name) {
      action.value = "auto";
      playing.value = events.find((item) => item[0] === name)?.[1] ?? name;
      replay.value++;
      const phase = name === "thinking.start" ? "thinking" : name === "tool.start" ? "tool" : name === "awaiting" ? "awaiting" : name === "done" ? "done" : name === "error" ? "error" : "idle";
      host.patch({ phase, thinking: phase === "thinking", panelOpen: name === "panel.open" });
      host.fire(`agent.${name}`, { name: "preview_tool", text: "预览消息" });
    }
    const stageComponent = computed$1(() => props.pet.key === "ying" ? AgentPet : _sfc_main$5);
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const reducedMotion = ref$1(mediaQuery.matches);
    let observer;
    function resize() {
      if (!canvas.value) return;
      const { width, height } = canvas.value.getBoundingClientRect();
      previewMaxSize.value = { width: Math.max(1, width - 32), height: Math.max(1, height - 40) };
      host.patch({
        isMobile: window.innerWidth < 600,
        viewport: {
          width: Math.max(1, width),
          height: Math.max(1, height),
          keyboardInset: 0,
          safeArea: { top: 12, right: 16, bottom: 16, left: 16 }
        }
      });
    }
    function updateMotion() {
      reducedMotion.value = mediaQuery.matches;
      host.patch({ motionAllowed: !paused.value && !reducedMotion.value, reducedMotion: reducedMotion.value });
    }
    function updateAction() {
      host.patch({ phase: action.value === "auto" ? "idle" : "thinking", thinking: false, panelOpen: false });
    }
    watch$1(previewGroup, () => choose("auto"));
    watch$1([() => props.pet.mode, () => props.pet.key, positionVersion, previewMode], () => {
      context.value = newContext();
    });
    watch$1(paused, updateMotion);
    watch$1(
      () => props.pet.key,
      () => {
        onLoadState("loading");
        loadedPack.value = null;
        previewGroup.value = props.pet.key === "ying" ? "poses" : "native";
        action.value = "auto";
        playing.value = "自主动作";
        original.value = false;
        updateAction();
      }
    );
    onMounted(() => {
      resize();
      updateMotion();
      observer = new ResizeObserver(resize);
      if (canvas.value) observer.observe(canvas.value);
      window.addEventListener("resize", resize);
      mediaQuery.addEventListener("change", updateMotion);
      mounted.value = true;
    });
    onBeforeUnmount$1(() => {
      observer?.disconnect();
      window.removeEventListener("resize", resize);
      mediaQuery.removeEventListener("change", updateMotion);
      host.dispose();
    });
    return (_ctx, _cache) => {
      const _component_v_btn = _resolveComponent$2("v-btn");
      const _component_v_btn_toggle = _resolveComponent$2("v-btn-toggle");
      const _component_v_alert = _resolveComponent$2("v-alert");
      const _component_v_switch = _resolveComponent$2("v-switch");
      const _component_v_tab = _resolveComponent$2("v-tab");
      const _component_v_tabs = _resolveComponent$2("v-tabs");
      const _component_v_spacer = _resolveComponent$2("v-spacer");
      return _openBlock$2(), _createElementBlock$2("section", {
        class: _normalizeClass(["ap-preview", { "ap-preview--expanded": expanded.value }]),
        "aria-label": "Pet 实时预览"
      }, [
        _createElementVNode$2("div", _hoisted_1$2, [
          _createElementVNode$2("header", _hoisted_2$2, [
            _cache[11] || (_cache[11] = _createElementVNode$2("div", { class: "ap-inline" }, [
              _createElementVNode$2("span", { class: "ap-live-dot" }),
              _createElementVNode$2("strong", null, "实时预览")
            ], -1)),
            _createVNode$2(_component_v_btn, {
              size: "small",
              variant: "text",
              "aria-pressed": expanded.value,
              onClick: _cache[0] || (_cache[0] = ($event) => expanded.value = !expanded.value)
            }, {
              default: _withCtx$2(() => [
                _createTextVNode$2(_toDisplayString$2(expanded.value ? "收起预览" : "放大预览"), 1)
              ]),
              _: 1
            }, 8, ["aria-pressed"])
          ]),
          __props.pet.mode === "stage" ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_3$2, [
            _createVNode$2(_component_v_btn_toggle, {
              modelValue: previewMode.value,
              "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => previewMode.value = $event),
              mandatory: "",
              divided: "",
              density: "compact",
              color: "primary",
              variant: "outlined",
              "aria-label": "预览模式"
            }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_btn, {
                  value: "debug",
                  size: "small"
                }, {
                  default: _withCtx$2(() => [..._cache[12] || (_cache[12] = [
                    _createTextVNode$2("动作调试", -1)
                  ])]),
                  _: 1
                }),
                _createVNode$2(_component_v_btn, {
                  value: "movement",
                  size: "small"
                }, {
                  default: _withCtx$2(() => [..._cache[13] || (_cache[13] = [
                    _createTextVNode$2("运动测试", -1)
                  ])]),
                  _: 1
                })
              ]),
              _: 1
            }, 8, ["modelValue"])
          ])) : _createCommentVNode$2("", true),
          _createElementVNode$2("div", {
            class: _normalizeClass(["ap-preview__canvases", { "ap-preview__canvases--compare": original.value }])
          }, [
            _createElementVNode$2("div", {
              ref_key: "canvas",
              ref: canvas,
              class: _normalizeClass(["ap-preview__canvas", { "ap-preview__canvas--debug": previewMode.value === "debug" }]),
              "data-roam": previewSettings.value.roam
            }, [
              __props.pet.mode === "stage" && previewMode.value === "movement" && __props.settings.roam === "surfaces" ? (_openBlock$2(), _createElementBlock$2(_Fragment$1, { key: 0 }, [
                _cache[14] || (_cache[14] = _createElementVNode$2("div", { class: "v-sheet ap-preview__surface ap-preview__surface--left" }, [
                  _createElementVNode$2("span", null, "小平台")
                ], -1)),
                _cache[15] || (_cache[15] = _createElementVNode$2("div", { class: "v-sheet ap-preview__surface ap-preview__surface--right" }, [
                  _createElementVNode$2("span", null, "休息台")
                ], -1))
              ], 64)) : _createCommentVNode$2("", true),
              _cache[17] || (_cache[17] = _createElementVNode$2("div", {
                class: "ap-preview__floor",
                "aria-hidden": "true"
              }, null, -1)),
              mounted.value && __props.pet.mode === "stage" ? (_openBlock$2(), _createBlock$1(_resolveDynamicComponent(stageComponent.value), {
                key: `${__props.pluginId}:${__props.pet.key}:${positionVersion.value}:${previewMode.value}`,
                agent: _unref$2(host),
                pet: context.value,
                api: __props.api,
                "plugin-id": __props.pluginId,
                "preview-root": canvas.value,
                "preview-max-size": previewMaxSize.value,
                "settings-override": previewSettings.value,
                "preview-pose": previewPose.value,
                "native-action": nativeAction.value,
                "mappings-override": __props.mappings,
                "calibration-override": __props.calibration,
                "show-calibration": editorTab.value === "calibration" && !!__props.calibration,
                replay: replay.value,
                onPackReady,
                onLoadState
              }, null, 40, ["agent", "pet", "api", "plugin-id", "preview-root", "preview-max-size", "settings-override", "preview-pose", "native-action", "mappings-override", "calibration-override", "show-calibration", "replay"])) : mounted.value ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_5$2, [
                (_openBlock$2(), _createBlock$1(AgentPetSprite, {
                  key: `${__props.pluginId}:${__props.pet.key}:${positionVersion.value}`,
                  agent: _unref$2(host),
                  pet: context.value,
                  api: __props.api,
                  "plugin-id": __props.pluginId,
                  action: rendererAction.value,
                  intent: rendererIntent.value,
                  "native-action": nativeAction.value,
                  "mappings-override": __props.mappings,
                  "calibration-override": __props.calibration,
                  "show-calibration": editorTab.value === "calibration" && !!__props.calibration,
                  replay: replay.value,
                  "motion-active": !paused.value && !reducedMotion.value,
                  "strict-preview": "",
                  onPackReady,
                  onLoadState
                }, null, 8, ["agent", "pet", "api", "plugin-id", "action", "intent", "native-action", "mappings-override", "calibration-override", "show-calibration", "replay", "motion-active"]))
              ])) : _createCommentVNode$2("", true),
              failed.value ? (_openBlock$2(), _createBlock$1(_component_v_alert, {
                key: 3,
                type: "error",
                variant: "tonal",
                density: "compact",
                class: "ap-preview__error"
              }, {
                default: _withCtx$2(() => [..._cache[16] || (_cache[16] = [
                  _createTextVNode$2("此 Pet 加载失败，请点击重置重试。", -1)
                ])]),
                _: 1
              })) : _createCommentVNode$2("", true),
              _createElementVNode$2("span", _hoisted_6$1, _toDisplayString$2(original.value ? "当前校准" : previewMode.value === "debug" ? "居中播放 · 不会自行走开" : "拖动 Pet · 测试移动与跳跃"), 1)
            ], 10, _hoisted_4$2),
            original.value && loadedPack.value ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_7$1, [
              _createElementVNode$2("div", _hoisted_8$1, [
                _createVNode$2(AgentPetSprite, {
                  agent: _unref$2(host),
                  pet: comparisonContext.value,
                  api: __props.api,
                  "plugin-id": __props.pluginId,
                  action: previewPose.value ? _unref$2(stageAction)(previewPose.value, false).action : rendererAction.value,
                  "mapping-key": previewPose.value ? _unref$2(stageAction)(previewPose.value, false).key : void 0,
                  intent: rendererIntent.value,
                  "native-action": nativeAction.value,
                  "mappings-override": __props.mappings,
                  "calibration-override": _unref$2(DEFAULT_CALIBRATION),
                  replay: replay.value,
                  "motion-active": !paused.value && !reducedMotion.value,
                  "strict-preview": ""
                }, null, 8, ["agent", "pet", "api", "plugin-id", "action", "mapping-key", "intent", "native-action", "mappings-override", "calibration-override", "replay", "motion-active"])
              ]),
              _cache[18] || (_cache[18] = _createElementVNode$2("span", { class: "ap-preview__hint" }, "原始显示", -1))
            ])) : _createCommentVNode$2("", true)
          ], 2),
          _createElementVNode$2("div", _hoisted_9$1, [
            _createElementVNode$2("span", _hoisted_10$1, _toDisplayString$2(paused.value ? "已暂停" : "正在播放") + "：" + _toDisplayString$2(playing.value), 1),
            _createElementVNode$2("div", _hoisted_11$1, [
              _createVNode$2(_component_v_btn, {
                icon: paused.value ? "mdi-play" : "mdi-pause",
                "aria-label": paused.value ? "播放预览" : "暂停预览",
                size: "small",
                variant: "text",
                onClick: _cache[2] || (_cache[2] = ($event) => paused.value = !paused.value)
              }, null, 8, ["icon", "aria-label"]),
              _createVNode$2(_component_v_btn, {
                icon: "mdi-replay",
                "aria-label": "重播当前动作",
                size: "small",
                variant: "text",
                onClick: _cache[3] || (_cache[3] = ($event) => replay.value++)
              }),
              _createVNode$2(_component_v_btn, {
                icon: "mdi-restore",
                "aria-label": "重置预览位置",
                size: "small",
                variant: "text",
                onClick: _cache[4] || (_cache[4] = ($event) => positionVersion.value++)
              })
            ])
          ]),
          loadedPack.value && !__props.pet.builtin ? (_openBlock$2(), _createBlock$1(_component_v_switch, {
            key: 1,
            modelValue: original.value,
            "onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => original.value = $event),
            label: "对照原始显示",
            density: "compact",
            "hide-details": "",
            class: "ap-preview__comparison"
          }, null, 8, ["modelValue"])) : _createCommentVNode$2("", true)
        ]),
        _createElementVNode$2("div", _hoisted_12$1, [
          _createVNode$2(_component_v_tabs, {
            modelValue: editorTab.value,
            "onUpdate:modelValue": _cache[6] || (_cache[6] = ($event) => editorTab.value = $event),
            density: "compact",
            color: "primary",
            class: "ap-preview__tabs"
          }, {
            default: _withCtx$2(() => [
              _createVNode$2(_component_v_tab, { value: "activity" }, {
                default: _withCtx$2(() => [..._cache[19] || (_cache[19] = [
                  _createTextVNode$2("活动", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_tab, { value: "animations" }, {
                default: _withCtx$2(() => [..._cache[20] || (_cache[20] = [
                  _createTextVNode$2("动作试播", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_tab, { value: "calibration" }, {
                default: _withCtx$2(() => [..._cache[21] || (_cache[21] = [
                  _createTextVNode$2("校准", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_tab, { value: "mappings" }, {
                default: _withCtx$2(() => [..._cache[22] || (_cache[22] = [
                  _createTextVNode$2("映射", -1)
                ])]),
                _: 1
              })
            ]),
            _: 1
          }, 8, ["modelValue"]),
          _createElementVNode$2("div", _hoisted_13$1, [
            _withDirectives(_createElementVNode$2("div", _hoisted_14$1, [
              _renderSlot(_ctx.$slots, "activity", {}, () => [
                _cache[23] || (_cache[23] = _createElementVNode$2("p", { class: "ap-muted" }, "活动设置在详情页中调整，预览不会自动保存。", -1))
              ], true)
            ], 512), [
              [_vShow, editorTab.value === "activity"]
            ]),
            _withDirectives(_createElementVNode$2("div", _hoisted_15$1, [
              _createElementVNode$2("div", _hoisted_16$1, [
                _cache[25] || (_cache[25] = _createElementVNode$2("strong", null, "完整动作预览", -1)),
                _createVNode$2(_component_v_spacer),
                _createVNode$2(_component_v_btn, {
                  size: "small",
                  variant: action.value === "auto" ? "tonal" : "text",
                  onClick: _cache[7] || (_cache[7] = ($event) => choose("auto"))
                }, {
                  default: _withCtx$2(() => [..._cache[24] || (_cache[24] = [
                    _createTextVNode$2("自主动作", -1)
                  ])]),
                  _: 1
                }, 8, ["variant"])
              ]),
              _createVNode$2(_component_v_tabs, {
                modelValue: previewGroup.value,
                "onUpdate:modelValue": _cache[8] || (_cache[8] = ($event) => previewGroup.value = $event),
                density: "compact",
                color: "primary"
              }, {
                default: _withCtx$2(() => [
                  __props.pet.key !== "ying" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 0,
                    value: "native"
                  }, {
                    default: _withCtx$2(() => [..._cache[26] || (_cache[26] = [
                      _createTextVNode$2("原生动画", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true),
                  loadedPack.value?.codex_version === "v2" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 1,
                    value: "directions"
                  }, {
                    default: _withCtx$2(() => [..._cache[27] || (_cache[27] = [
                      _createTextVNode$2("视线方向", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true),
                  __props.pet.mode === "stage" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 2,
                    value: "poses"
                  }, {
                    default: _withCtx$2(() => [..._cache[28] || (_cache[28] = [
                      _createTextVNode$2("活动姿态", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true),
                  __props.pet.mode === "stage" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 3,
                    value: "events"
                  }, {
                    default: _withCtx$2(() => [..._cache[29] || (_cache[29] = [
                      _createTextVNode$2("MP 事件", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true),
                  __props.pet.mode === "renderer" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 4,
                    value: "actions"
                  }, {
                    default: _withCtx$2(() => [..._cache[30] || (_cache[30] = [
                      _createTextVNode$2("MP 动作", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true),
                  __props.pet.mode === "renderer" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 5,
                    value: "intents"
                  }, {
                    default: _withCtx$2(() => [..._cache[31] || (_cache[31] = [
                      _createTextVNode$2("入口状态", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true)
                ]),
                _: 1
              }, 8, ["modelValue"]),
              _createElementVNode$2("div", _hoisted_17$1, [
                previewGroup.value === "events" ? (_openBlock$2(), _createElementBlock$2(_Fragment$1, { key: 0 }, _renderList(events, ([key, label]) => {
                  return _createVNode$2(_component_v_btn, {
                    key,
                    size: "small",
                    variant: "tonal",
                    onClick: ($event) => fireHost(key)
                  }, {
                    default: _withCtx$2(() => [
                      _createTextVNode$2(_toDisplayString$2(label), 1)
                    ]),
                    _: 2
                  }, 1032, ["onClick"]);
                }), 64)) : (_openBlock$2(true), _createElementBlock$2(_Fragment$1, { key: 1 }, _renderList(choices.value, (item) => {
                  return _openBlock$2(), _createBlock$1(_component_v_btn, {
                    key: item.value,
                    size: "small",
                    variant: action.value === item.value ? "flat" : "tonal",
                    color: action.value === item.value ? "primary" : void 0,
                    disabled: failed.value,
                    onClick: ($event) => choose(item.value)
                  }, {
                    default: _withCtx$2(() => [
                      _createTextVNode$2(_toDisplayString$2(item.title), 1)
                    ]),
                    _: 2
                  }, 1032, ["variant", "color", "disabled", "onClick"]);
                }), 128))
              ]),
              _createElementVNode$2("p", _hoisted_18, _toDisplayString$2(previewGroup.value === "native" || previewGroup.value === "directions" ? "直接播放素材原始动画，不受动作映射影响。" : "按当前映射预览；运动测试中可拖动 Pet。"), 1)
            ], 512), [
              [_vShow, editorTab.value === "animations"]
            ]),
            _withDirectives(_createElementVNode$2("div", null, [
              loadedPack.value && !__props.pet.builtin && __props.calibration ? (_openBlock$2(), _createBlock$1(CalibrationControls, {
                key: __props.pet.key,
                "model-value": __props.calibration,
                "pack-id": __props.pet.key,
                api: __props.api,
                "plugin-id": __props.pluginId,
                disabled: __props.disabled,
                "onUpdate:modelValue": _cache[9] || (_cache[9] = ($event) => emit("calibration", $event))
              }, null, 8, ["model-value", "pack-id", "api", "plugin-id", "disabled"])) : (_openBlock$2(), _createElementBlock$2("p", _hoisted_19, _toDisplayString$2(__props.pet.builtin ? "内置形象无需显示校准。" : "素材加载后可调整显示区域与脚底基线。"), 1))
            ], 512), [
              [_vShow, editorTab.value === "calibration"]
            ]),
            _withDirectives(_createElementVNode$2("div", null, [
              loadedPack.value?.codex_version && !__props.pet.builtin ? (_openBlock$2(), _createBlock$1(ActionMappingEditor, {
                key: 0,
                pack: loadedPack.value,
                mode: __props.pet.mode,
                "model-value": __props.mappings ?? loadedPack.value.action_mappings ?? {},
                disabled: __props.disabled,
                "onUpdate:modelValue": _cache[10] || (_cache[10] = ($event) => emit("mappings", $event)),
                onPreview: playNative
              }, null, 8, ["pack", "mode", "model-value", "disabled"])) : (_openBlock$2(), _createElementBlock$2("p", _hoisted_20, "此形象使用内置动作，无需设置动作映射。"))
            ], 512), [
              [_vShow, editorTab.value === "mappings"]
            ])
          ])
        ])
      ], 2);
    };
  }
});

const PetPreview = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-fe37dfdf"]]);

const {defineComponent:_defineComponent$1} = await importShared('vue');

const {resolveComponent:_resolveComponent$1,createVNode:_createVNode$1,createElementVNode:_createElementVNode$1,unref:_unref$1,toDisplayString:_toDisplayString$1,withCtx:_withCtx$1,Fragment:_Fragment,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,createCommentVNode:_createCommentVNode$1,createTextVNode:_createTextVNode$1} = await importShared('vue');

const _hoisted_1$1 = { class: "agent-pets-stage-settings" };
const _hoisted_2$1 = { class: "agent-pets-stage-settings__value" };
const _hoisted_3$1 = { class: "agent-pets-stage-settings__value" };
const _hoisted_4$1 = { class: "d-flex align-start flex-column ga-2 mt-3" };
const _hoisted_5$1 = {
  key: 0,
  class: "text-caption text-medium-emphasis"
};
const _sfc_main$1 = /* @__PURE__ */ _defineComponent$1({
  __name: "StageSettings",
  props: {
    modelValue: {},
    livePreview: { type: Boolean },
    disabled: { type: Boolean },
    previewOnly: { type: Boolean }
  },
  emits: ["update:modelValue"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const ROAM_OPTIONS = [
      { value: "surfaces", title: "站在页面元素上", hint: "落到卡片、对话框等元素的上边，元素移动或消失时跟着走或掉下来" },
      { value: "floor", title: "只在底边", hint: "始终站在屏幕底边" },
      { value: "free", title: "自由活动", hint: "没有重力，空闲时在屏幕内慢慢游走" }
    ];
    function update(patch) {
      emit("update:modelValue", { ...props.modelValue, ...patch });
    }
    function reset() {
      emit("update:modelValue", { ...DEFAULT_SETTINGS });
    }
    return (_ctx, _cache) => {
      const _component_v_select = _resolveComponent$1("v-select");
      const _component_v_slider = _resolveComponent$1("v-slider");
      const _component_v_spacer = _resolveComponent$1("v-spacer");
      const _component_v_btn = _resolveComponent$1("v-btn");
      return _openBlock$1(), _createElementBlock$1("div", _hoisted_1$1, [
        _createVNode$1(_component_v_select, {
          "model-value": props.modelValue.movement ?? "auto",
          items: [
            { title: "自主活动", value: "auto" },
            { title: "固定位置", value: "fixed" }
          ],
          label: "活动方式",
          variant: "outlined",
          density: "compact",
          disabled: props.disabled,
          hint: props.modelValue.movement === "fixed" ? "拖到哪里就停在哪里；保留会话动作，仅在超出可见区域时限位。" : "按活动范围散步、下落和避让控件。",
          "persistent-hint": "",
          class: "mb-4",
          "onUpdate:modelValue": _cache[0] || (_cache[0] = (value) => update({ movement: value }))
        }, null, 8, ["model-value", "disabled", "hint"]),
        _cache[6] || (_cache[6] = _createElementVNode$1("div", { class: "text-subtitle-2 mb-1" }, "角色大小", -1)),
        _createVNode$1(_component_v_slider, {
          "model-value": props.modelValue.scale,
          min: _unref$1(SCALE_RANGE)[0],
          max: _unref$1(SCALE_RANGE)[1],
          step: 0.05,
          color: "primary",
          "thumb-label": "",
          disabled: props.disabled,
          "hide-details": "",
          "aria-label": "角色大小",
          "onUpdate:modelValue": _cache[1] || (_cache[1] = (value) => update({ scale: Number(value) }))
        }, {
          append: _withCtx$1(() => [
            _createElementVNode$1("span", _hoisted_2$1, _toDisplayString$1(props.modelValue.scale.toFixed(2)) + "×", 1)
          ]),
          _: 1
        }, 8, ["model-value", "min", "max", "disabled"]),
        props.modelValue.movement !== "fixed" ? (_openBlock$1(), _createElementBlock$1(_Fragment, { key: 0 }, [
          _cache[4] || (_cache[4] = _createElementVNode$1("div", { class: "text-subtitle-2 mt-4 mb-1" }, "移动速度", -1)),
          _createVNode$1(_component_v_slider, {
            "model-value": props.modelValue.speed,
            min: _unref$1(SPEED_RANGE)[0],
            max: _unref$1(SPEED_RANGE)[1],
            step: 0.05,
            color: "primary",
            "thumb-label": "",
            disabled: props.disabled,
            "hide-details": "",
            "aria-label": "移动速度",
            "onUpdate:modelValue": _cache[2] || (_cache[2] = (value) => update({ speed: Number(value) }))
          }, {
            append: _withCtx$1(() => [
              _createElementVNode$1("span", _hoisted_3$1, _toDisplayString$1(props.modelValue.speed.toFixed(2)) + "×", 1)
            ]),
            _: 1
          }, 8, ["model-value", "min", "max", "disabled"]),
          _createVNode$1(_component_v_select, {
            "model-value": props.modelValue.roam,
            items: ROAM_OPTIONS,
            "item-title": "title",
            "item-value": "value",
            label: "活动范围",
            variant: "outlined",
            density: "compact",
            disabled: props.disabled,
            class: "mt-5",
            hint: ROAM_OPTIONS.find((option) => option.value === props.modelValue.roam)?.hint,
            "persistent-hint": "",
            "onUpdate:modelValue": _cache[3] || (_cache[3] = (value) => update({ roam: value }))
          }, null, 8, ["model-value", "disabled", "hint"])
        ], 64)) : _createCommentVNode$1("", true),
        _createElementVNode$1("div", _hoisted_4$1, [
          props.livePreview ? (_openBlock$1(), _createElementBlock$1("span", _hoisted_5$1, _toDisplayString$1(props.previewOnly ? "仅在预览区试调。小映与 Codex Pet 共用活动设置，保存后对所有用户生效。" : "调整时页面上正在运行的小映或 Codex Pet 会实时变化，保存后对所有用户生效。"), 1)) : _createCommentVNode$1("", true),
          _createVNode$1(_component_v_spacer),
          _createVNode$1(_component_v_btn, {
            variant: "text",
            size: "small",
            disabled: props.disabled,
            onClick: reset
          }, {
            default: _withCtx$1(() => [..._cache[5] || (_cache[5] = [
              _createTextVNode$1("恢复默认", -1)
            ])]),
            _: 1
          }, 8, ["disabled"])
        ])
      ]);
    };
  }
});

const StageSettings = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-5f171cc3"]]);

const {defineComponent:_defineComponent} = await importShared('vue');

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,unref:_unref,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementVNode:_createElementVNode,createElementBlock:_createElementBlock} = await importShared('vue');

const _hoisted_1 = { class: "ap-page" };
const _hoisted_2 = { class: "ap-page__content" };
const _hoisted_3 = { class: "ap-page__notices" };
const _hoisted_4 = {
  key: 0,
  class: "ap-empty"
};
const _hoisted_5 = {
  key: 1,
  class: "ap-editor-grid"
};
const _hoisted_6 = { class: "ap-page__selector" };
const _hoisted_7 = { class: "ap-muted" };
const _hoisted_8 = {
  key: 0,
  class: "ap-muted mb-3"
};
const _hoisted_9 = { class: "ap-control-panel" };
const _hoisted_10 = { class: "ap-section-title" };
const _hoisted_11 = {
  key: 1,
  class: "ap-muted mb-0"
};
const _hoisted_12 = { class: "ap-control-panel" };
const _hoisted_13 = {
  key: 2,
  class: "ap-empty"
};
const _hoisted_14 = { class: "ap-footer" };
const _hoisted_15 = {
  key: 0,
  class: "ap-change"
};
const _hoisted_16 = {
  key: 1,
  class: "ap-muted"
};
const _hoisted_17 = { class: "ap-footer__actions" };
const {computed,inject,onBeforeUnmount,ref,watch} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Page",
  props: {
    api: { default: null },
    pluginId: { default: "" },
    sourcePluginId: { default: "" }
  },
  emits: ["close", "switch", "layout"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    emit("layout", { maxWidth: "68rem" });
    const agent = inject(AGENT_HOST_KEY, null);
    const snapshot = ref(null);
    const selection = ref(null);
    const selectedKey = ref("");
    const draft = ref({ ...DEFAULT_SETTINGS });
    const saved = ref({ ...DEFAULT_SETTINGS });
    const loading = ref(false);
    const busy = ref(false);
    const error = ref("");
    const hostError = ref("");
    const feedback = ref("");
    const feedbackType = ref("success");
    const currentPet = computed(() => snapshot.value?.pets.find((pet) => pet.key === selectedKey.value) ?? null);
    const previewVersion = ref(0);
    const calibrationDrafts = ref({});
    const calibrationSaved = ref({});
    const calibrationConflicts = ref({});
    const calibrationDirtyKeys = computed(
      () => Object.keys(calibrationDrafts.value).filter(
        (key) => !sameCalibration(calibrationDrafts.value[key], calibrationSaved.value[key])
      )
    );
    const mappingDrafts = ref({});
    const mappingSaved = ref({});
    const mappingConflicts = ref({});
    const conflictingNames = computed(
      () => [.../* @__PURE__ */ new Set([...Object.keys(mappingConflicts.value), ...Object.keys(calibrationConflicts.value)])].map(
        (key) => snapshot.value?.pets.find((pet) => pet.key === key)?.name ?? key
      )
    );
    const mappingDirtyKeys = computed(
      () => Object.keys(mappingDrafts.value).filter(
        (key) => !sameMappings(mappingDrafts.value[key], mappingSaved.value[key] ?? {})
      )
    );
    function onPackReady(pack) {
      const key = selectedKey.value;
      if (!currentPet.value?.builtin) {
        const latest2 = parseCalibration(pack.calibration);
        const baseline2 = calibrationSaved.value[key];
        if (baseline2 && !sameCalibration(calibrationDrafts.value[key], baseline2)) {
          if (!sameCalibration(latest2, baseline2)) calibrationConflicts.value[key] = latest2;
          else delete calibrationConflicts.value[key];
        } else {
          calibrationSaved.value[key] = latest2;
          calibrationDrafts.value[key] = { ...latest2 };
          delete calibrationConflicts.value[key];
        }
      }
      if (!pack.codex_version) return;
      const latest = { ...pack.action_mappings };
      const baseline = mappingSaved.value[key];
      const preserve = baseline && !sameMappings(mappingDrafts.value[key] ?? {}, baseline);
      if (preserve) {
        if (!sameMappings(latest, baseline)) mappingConflicts.value[key] = latest;
        else delete mappingConflicts.value[key];
        return;
      }
      delete mappingConflicts.value[key];
      mappingSaved.value[key] = latest;
      mappingDrafts.value[key] = { ...latest };
    }
    const dirty = computed(
      () => !sameSettings(draft.value, saved.value) || mappingDirtyKeys.value.length > 0 || calibrationDirtyKeys.value.length > 0
    );
    const changedNames = computed(
      () => [
        draft.value.scale !== saved.value.scale ? "大小" : "",
        draft.value.speed !== saved.value.speed ? "速度" : "",
        draft.value.roam !== saved.value.roam ? "活动范围" : "",
        draft.value.movement !== saved.value.movement ? "活动方式" : "",
        mappingDirtyKeys.value.length ? `${mappingDirtyKeys.value.length} 只 Pet 的动作映射` : "",
        calibrationDirtyKeys.value.length ? `${calibrationDirtyKeys.value.length} 只 Pet 的显示校准` : ""
      ].filter(Boolean)
    );
    const blocked = computed(() => loading.value || busy.value || !props.api || !currentPet.value || !!error.value);
    const defaultName = computed(() => {
      if (!selection.value) return "暂不可读";
      if (!selection.value.defaultId) return "内置机器人";
      return snapshot.value?.pets.find((pet) => `${props.pluginId}:${pet.key}` === selection.value?.defaultId)?.name ?? "其他插件形象";
    });
    let disposed = false;
    let requestVersion = 0;
    let operationVersion = 0;
    async function refresh(reset = false) {
      if (busy.value) return;
      const version = ++requestVersion;
      const id = props.pluginId;
      loading.value = true;
      error.value = "";
      hostError.value = "";
      const results = await Promise.allSettled([
        loadEditor(props.api, id),
        props.api ? loadHostSelection(props.api) : Promise.reject(new Error("页面连接尚未就绪"))
      ]);
      if (disposed || version !== requestVersion || id !== props.pluginId) return;
      const [editor, host] = results;
      if (host.status === "fulfilled") selection.value = host.value;
      else {
        selection.value = null;
        hostError.value = "当前系统默认形象暂不可读，仍可预览和保存调整。";
      }
      if (editor.status === "fulfilled") {
        const preserveDraft = !reset && dirty.value;
        snapshot.value = editor.value;
        for (const values of [calibrationDrafts, calibrationSaved, calibrationConflicts]) {
          for (const key of Object.keys(values.value))
            if (!editor.value.pets.some((pet) => pet.key === key)) delete values.value[key];
        }
        for (const key of Object.keys(mappingDrafts.value)) {
          if (!editor.value.pets.some((pet) => pet.key === key)) {
            delete mappingDrafts.value[key];
            delete mappingSaved.value[key];
            delete mappingConflicts.value[key];
          }
        }
        previewVersion.value++;
        saved.value = { ...editor.value.settings };
        if (!preserveDraft) draft.value = { ...saved.value };
        if (!editor.value.pets.some((pet) => pet.key === selectedKey.value)) {
          selectedKey.value = editor.value.pets.find((pet) => `${id}:${pet.key}` === selection.value?.defaultId)?.key ?? editor.value.pets[0]?.key ?? "";
        }
      } else error.value = "无法读取 Pet 与活动设置，请刷新重试。";
      loading.value = false;
    }
    watch(
      () => props.pluginId,
      () => {
        operationVersion++;
        busy.value = false;
        snapshot.value = null;
        selection.value = null;
        selectedKey.value = "";
        calibrationDrafts.value = {};
        calibrationSaved.value = {};
        calibrationConflicts.value = {};
        mappingDrafts.value = {};
        mappingSaved.value = {};
        mappingConflicts.value = {};
        feedback.value = "";
        void refresh(true);
      },
      { immediate: true }
    );
    onBeforeUnmount(() => {
      disposed = true;
      requestVersion++;
      operationVersion++;
    });
    function restore() {
      calibrationSaved.value = { ...calibrationSaved.value, ...calibrationConflicts.value };
      calibrationConflicts.value = {};
      calibrationDrafts.value = Object.fromEntries(
        Object.entries(calibrationSaved.value).map(([key, value]) => [key, { ...value }])
      );
      mappingSaved.value = { ...mappingSaved.value, ...mappingConflicts.value };
      mappingConflicts.value = {};
      draft.value = { ...saved.value };
      mappingDrafts.value = Object.fromEntries(
        Object.entries(mappingSaved.value).map(([key, value]) => [key, { ...value }])
      );
      feedback.value = "";
    }
    async function save() {
      if (blocked.value || conflictingNames.value.length || !props.api || !currentPet.value) return;
      const api = props.api;
      const id = props.pluginId;
      const values = { ...draft.value };
      const mappings = mappingDirtyKeys.value.map((key) => ({
        key,
        values: { ...mappingDrafts.value[key] },
        expected: { ...mappingSaved.value[key] }
      }));
      const calibrations = calibrationDirtyKeys.value.map((key) => ({
        key,
        value: { ...calibrationDrafts.value[key] },
        expected: { ...calibrationSaved.value[key] }
      }));
      const version = ++operationVersion;
      const current = () => !disposed && version === operationVersion && id === props.pluginId;
      busy.value = true;
      feedback.value = "";
      try {
        if (!sameSettings(values, saved.value)) {
          const result = await saveSettings(api, id, values);
          if (!current()) return;
          saved.value = { ...result };
          agent?.emit?.(SETTINGS_EVENT, { ...result });
        }
        for (const item of mappings) {
          if (!current()) return;
          const result = await saveMappings(api, id, item.key, item.values, item.expected);
          if (!current()) return;
          mappingSaved.value[item.key] = { ...result };
          agent?.emit?.(PACK_UPDATED_EVENT, { key: item.key });
        }
        for (const item of calibrations) {
          if (!current()) return;
          const result = await saveCalibration(api, id, item.key, item.value, item.expected);
          if (!current()) return;
          calibrationSaved.value[item.key] = result;
          agent?.emit?.(PACK_UPDATED_EVENT, { key: item.key });
        }
        feedbackType.value = "success";
        feedback.value = agent ? "调整已保存，并已通知当前页面更新。" : "调整已保存。";
      } catch (reason) {
        if (!current()) return;
        feedbackType.value = "error";
        feedback.value = reason instanceof Error ? reason.message : "操作未完成，请重试";
      } finally {
        if (current()) busy.value = false;
      }
    }
    return (_ctx, _cache) => {
      const _component_v_icon = _resolveComponent("v-icon");
      const _component_v_toolbar_title = _resolveComponent("v-toolbar-title");
      const _component_v_btn = _resolveComponent("v-btn");
      const _component_v_toolbar = _resolveComponent("v-toolbar");
      const _component_v_alert = _resolveComponent("v-alert");
      const _component_v_progress_circular = _resolveComponent("v-progress-circular");
      const _component_v_select = _resolveComponent("v-select");
      return _openBlock(), _createElementBlock("section", _hoisted_1, [
        _createVNode(_component_v_toolbar, {
          class: "ap-page__toolbar",
          color: "transparent",
          density: "compact",
          flat: ""
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, {
              icon: "mdi-paw-outline",
              color: "primary",
              class: "mr-3"
            }),
            _createVNode(_component_v_toolbar_title, { class: "text-subtitle-1 font-weight-bold" }, {
              default: _withCtx(() => [..._cache[8] || (_cache[8] = [
                _createTextVNode("助手形象 · 调整与预览", -1)
              ])]),
              _: 1
            }),
            _createVNode(_component_v_btn, {
              icon: "mdi-refresh",
              "aria-label": "刷新形象列表",
              variant: "text",
              loading: loading.value,
              disabled: busy.value,
              onClick: _cache[0] || (_cache[0] = ($event) => refresh())
            }, null, 8, ["loading", "disabled"]),
            _createVNode(_component_v_btn, {
              icon: "mdi-cog-outline",
              "aria-label": "打开插件配置",
              variant: "text",
              disabled: busy.value,
              onClick: _cache[1] || (_cache[1] = ($event) => emit("switch"))
            }, null, 8, ["disabled"]),
            _createVNode(_component_v_btn, {
              icon: "mdi-close",
              "aria-label": "关闭详情页",
              variant: "text",
              disabled: busy.value,
              onClick: _cache[2] || (_cache[2] = ($event) => emit("close"))
            }, null, 8, ["disabled"])
          ]),
          _: 1
        }),
        _createElementVNode("div", _hoisted_2, [
          _createElementVNode("div", _hoisted_3, [
            !_unref(agent) ? (_openBlock(), _createBlock(_component_v_alert, {
              key: 0,
              type: "warning",
              variant: "tonal",
              density: "compact",
              class: "ap-result"
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(_unref(HOST_UNSUPPORTED_MESSAGE)), 1)
              ]),
              _: 1
            })) : _createCommentVNode("", true),
            error.value ? (_openBlock(), _createBlock(_component_v_alert, {
              key: 1,
              type: "error",
              variant: "tonal",
              density: "compact",
              class: "ap-result"
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(error.value), 1)
              ]),
              _: 1
            })) : _createCommentVNode("", true),
            hostError.value ? (_openBlock(), _createBlock(_component_v_alert, {
              key: 2,
              type: "warning",
              variant: "tonal",
              density: "compact",
              class: "ap-result"
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(hostError.value), 1)
              ]),
              _: 1
            })) : _createCommentVNode("", true),
            conflictingNames.value.length ? (_openBlock(), _createBlock(_component_v_alert, {
              key: 3,
              type: "warning",
              variant: "tonal",
              density: "compact",
              class: "ap-result"
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(conflictingNames.value.join("、")) + " 的素材调整已在其他页面更改。已保留你的草稿；请点击「撤销」载入最新值后重新调整。 ", 1)
              ]),
              _: 1
            })) : _createCommentVNode("", true),
            feedback.value ? (_openBlock(), _createBlock(_component_v_alert, {
              key: 4,
              type: feedbackType.value,
              variant: "tonal",
              density: "compact",
              class: "ap-result",
              role: "status"
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(feedback.value), 1)
              ]),
              _: 1
            }, 8, ["type"])) : _createCommentVNode("", true)
          ]),
          loading.value && !snapshot.value ? (_openBlock(), _createElementBlock("div", _hoisted_4, [
            _createVNode(_component_v_progress_circular, {
              indeterminate: "",
              color: "primary"
            }),
            _cache[9] || (_cache[9] = _createElementVNode("span", { class: "ap-muted" }, "正在准备你的 Pet…", -1))
          ])) : snapshot.value && currentPet.value ? (_openBlock(), _createElementBlock("div", _hoisted_5, [
            _createElementVNode("div", _hoisted_6, [
              _createVNode(_component_v_select, {
                modelValue: selectedKey.value,
                "onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => selectedKey.value = $event),
                items: snapshot.value.pets,
                "item-title": "name",
                "item-value": "key",
                label: "预览形象",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                disabled: blocked.value
              }, null, 8, ["modelValue", "items", "disabled"]),
              _createElementVNode("span", _hoisted_7, _toDisplayString(currentPet.value.mode === "stage" ? "自由活动的角色" : "助手入口的形象") + " · " + _toDisplayString(currentPet.value.builtin ? "内置" : "已导入"), 1)
            ]),
            (_openBlock(), _createBlock(PetPreview, {
              key: `${props.pluginId}:${previewVersion.value}`,
              pet: currentPet.value,
              settings: draft.value,
              api: props.api,
              "plugin-id": props.pluginId,
              mappings: mappingDrafts.value[selectedKey.value],
              calibration: calibrationDrafts.value[selectedKey.value],
              disabled: blocked.value,
              "initial-tab": "activity",
              onPackReady,
              onMappings: _cache[5] || (_cache[5] = ($event) => mappingDrafts.value[selectedKey.value] = $event),
              onCalibration: _cache[6] || (_cache[6] = ($event) => calibrationDrafts.value[selectedKey.value] = $event)
            }, {
              activity: _withCtx(() => [
                currentPet.value.description ? (_openBlock(), _createElementBlock("p", _hoisted_8, _toDisplayString(currentPet.value.description), 1)) : _createCommentVNode("", true),
                _createElementVNode("section", _hoisted_9, [
                  _createElementVNode("h2", _hoisted_10, _toDisplayString(currentPet.value.mode === "stage" ? "活动调整" : "入口外观"), 1),
                  currentPet.value.mode === "stage" ? (_openBlock(), _createBlock(StageSettings, {
                    key: 0,
                    modelValue: draft.value,
                    "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => draft.value = $event),
                    "live-preview": true,
                    disabled: blocked.value,
                    "preview-only": true
                  }, null, 8, ["modelValue", "disabled"])) : (_openBlock(), _createElementBlock("p", _hoisted_11, " 此 Pet 显示在助手入口，位置与拖拽由 MP 控制。可在预览区切换动作，在 MP 设置中选择使用。 "))
                ]),
                _createElementVNode("section", _hoisted_12, [
                  _cache[11] || (_cache[11] = _createElementVNode("h2", { class: "ap-section-title" }, "在 MP 中使用", -1)),
                  _cache[12] || (_cache[12] = _createElementVNode("div", { class: "ap-muted" }, "当前系统默认", -1)),
                  _createElementVNode("strong", null, _toDisplayString(defaultName.value), 1),
                  _cache[13] || (_cache[13] = _createElementVNode("p", { class: "ap-muted mt-3 mb-0" }, "保存调整后，在「设定 → 系统 → 智能助手配置 → 助手形象」中选择 Pet。", -1)),
                  !snapshot.value.enabled ? (_openBlock(), _createBlock(_component_v_alert, {
                    key: 0,
                    type: "info",
                    variant: "tonal",
                    density: "compact",
                    class: "mt-3"
                  }, {
                    default: _withCtx(() => [..._cache[10] || (_cache[10] = [
                      _createTextVNode("先在配置页启用插件，形象才会出现在 MP 的可选列表中。", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode("", true)
                ])
              ]),
              _: 1
            }, 8, ["pet", "settings", "api", "plugin-id", "mappings", "calibration", "disabled"]))
          ])) : !loading.value ? (_openBlock(), _createElementBlock("div", _hoisted_13, [
            _createVNode(_component_v_icon, {
              icon: "mdi-paw-outline",
              size: "44",
              color: "primary"
            }),
            _createElementVNode("strong", null, _toDisplayString(error.value ? "Pet 暂时未能加载" : "还没有可预览的 Pet"), 1),
            _createVNode(_component_v_btn, {
              variant: "tonal",
              color: "primary",
              onClick: _cache[7] || (_cache[7] = ($event) => error.value ? refresh() : emit("switch"))
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(error.value ? "重新加载" : "前往素材管理"), 1)
              ]),
              _: 1
            })
          ])) : _createCommentVNode("", true)
        ]),
        _createElementVNode("footer", _hoisted_14, [
          dirty.value ? (_openBlock(), _createElementBlock("span", _hoisted_15, [
            _createVNode(_component_v_icon, {
              icon: "mdi-circle",
              size: "7"
            }),
            _createTextVNode("未保存 · " + _toDisplayString(changedNames.value.join("、")), 1)
          ])) : (_openBlock(), _createElementBlock("span", _hoisted_16, "预览中的调整不会自动保存")),
          _createElementVNode("div", _hoisted_17, [
            _createVNode(_component_v_btn, {
              variant: "text",
              disabled: blocked.value || !dirty.value && !conflictingNames.value.length,
              onClick: restore
            }, {
              default: _withCtx(() => [..._cache[14] || (_cache[14] = [
                _createTextVNode("撤销", -1)
              ])]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode(_component_v_btn, {
              variant: "flat",
              color: "primary",
              "prepend-icon": "mdi-content-save-outline",
              disabled: blocked.value || !dirty.value || conflictingNames.value.length > 0,
              loading: busy.value,
              onClick: save
            }, {
              default: _withCtx(() => [..._cache[15] || (_cache[15] = [
                _createTextVNode("保存调整", -1)
              ])]),
              _: 1
            }, 8, ["disabled", "loading"])
          ])
        ])
      ]);
    };
  }
});

export { _sfc_main as _ };
