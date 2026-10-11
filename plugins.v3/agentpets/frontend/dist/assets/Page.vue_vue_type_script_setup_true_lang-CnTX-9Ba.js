import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { A as AGENT_HOST_KEY, s as sameSettings, H as HOST_UNSUPPORTED_MESSAGE, p as petImage, l as loadEditor, a as loadHostSelection, c as saveSettings } from './host-q6tYV7Ud.js';
import AgentPetSprite from './__federation_expose_AgentPetSprite-BbJu4Dqb.js';
import AgentPet from './__federation_expose_AgentPet-zjW_Xv2Q.js';
import { _ as _sfc_main$3 } from './AgentPetCodex.vue_vue_type_script_setup_true_lang-FwHhVtpM.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';
import { a as SCALE_RANGE, b as SPEED_RANGE, D as DEFAULT_SETTINGS, S as SETTINGS_EVENT } from './settings-CQFXVfMf.js';

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

const {createElementVNode:_createElementVNode$2,toDisplayString:_toDisplayString$2,resolveComponent:_resolveComponent$2,createVNode:_createVNode$2,Fragment:_Fragment,openBlock:_openBlock$2,createElementBlock:_createElementBlock$2,createCommentVNode:_createCommentVNode$2,unref:_unref$2,resolveDynamicComponent:_resolveDynamicComponent,createBlock:_createBlock$1,createTextVNode:_createTextVNode$2,withCtx:_withCtx$2} = await importShared('vue');

const _hoisted_1$2 = {
  class: "ap-preview",
  "aria-label": "Pet 实时预览"
};
const _hoisted_2$2 = { class: "ap-preview__header" };
const _hoisted_3$2 = { class: "ap-inline" };
const _hoisted_4$2 = { class: "ap-muted" };
const _hoisted_5$2 = { class: "ap-inline" };
const _hoisted_6$1 = ["data-roam"];
const _hoisted_7$1 = {
  class: "ap-preview__watermark",
  "aria-hidden": "true"
};
const _hoisted_8$1 = {
  key: 2,
  class: "ap-preview__entry"
};
const _hoisted_9$1 = { class: "ap-preview__hint" };
const _hoisted_10$1 = { class: "ap-preview__actions" };
const {computed: computed$1,onBeforeUnmount: onBeforeUnmount$1,onMounted,ref: ref$1,shallowRef,watch: watch$1} = await importShared('vue');
const _sfc_main$2 = /* @__PURE__ */ _defineComponent$2({
  __name: "PetPreview",
  props: {
    pet: {},
    settings: {},
    api: {},
    pluginId: {}
  },
  emits: ["error"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
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
    const context = shallowRef(createMockPet(props.pet.mode, props.pet.key));
    const actions = {
      auto: "idle",
      wave: "wave",
      thinking: "thinking",
      speaking: "speaking",
      happy: "happy-jump"
    };
    const poses = { wave: "wave", thinking: "think", speaking: "talk", happy: "victory" };
    const rendererAction = computed$1(() => actions[action.value] ?? "idle");
    const previewPose = computed$1(() => poses[action.value]);
    const stageComponent = computed$1(() => props.pet.key === "ying" ? AgentPet : _sfc_main$3);
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const reducedMotion = ref$1(mediaQuery.matches);
    let observer;
    function resize() {
      if (!canvas.value) return;
      const { width, height } = canvas.value.getBoundingClientRect();
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
      host.patch({ phase: action.value === "auto" ? "idle" : "thinking" });
      if (action.value === "wave") host.fire("agent.panel.open");
      if (action.value === "happy") host.fire("agent.done");
      if (action.value === "speaking") host.fire("agent.preview");
    }
    watch$1([() => props.pet.mode, () => props.pet.key, positionVersion], () => {
      context.value = createMockPet(props.pet.mode, props.pet.key);
    });
    watch$1(paused, updateMotion);
    watch$1(action, updateAction);
    watch$1(
      () => props.pet.key,
      () => {
        onLoadState("loading");
        action.value = "auto";
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
      const _component_v_icon = _resolveComponent$2("v-icon");
      const _component_v_alert = _resolveComponent$2("v-alert");
      const _component_v_btn_toggle = _resolveComponent$2("v-btn-toggle");
      return _openBlock$2(), _createElementBlock$2("section", _hoisted_1$2, [
        _createElementVNode$2("header", _hoisted_2$2, [
          _createElementVNode$2("div", _hoisted_3$2, [
            _cache[3] || (_cache[3] = _createElementVNode$2("span", { class: "ap-live-dot" }, null, -1)),
            _cache[4] || (_cache[4] = _createElementVNode$2("strong", null, "实时预览", -1)),
            _createElementVNode$2("span", _hoisted_4$2, _toDisplayString$2(__props.pet.name), 1)
          ]),
          _createElementVNode$2("div", _hoisted_5$2, [
            _createVNode$2(_component_v_btn, {
              icon: paused.value ? "mdi-play" : "mdi-pause",
              "aria-label": paused.value ? "播放预览" : "暂停预览",
              size: "small",
              variant: "text",
              onClick: _cache[0] || (_cache[0] = ($event) => paused.value = !paused.value)
            }, null, 8, ["icon", "aria-label"]),
            _createVNode$2(_component_v_btn, {
              icon: "mdi-restore",
              "aria-label": "重置预览位置",
              size: "small",
              variant: "text",
              onClick: _cache[1] || (_cache[1] = ($event) => positionVersion.value++)
            })
          ])
        ]),
        _createElementVNode$2("div", {
          ref_key: "canvas",
          ref: canvas,
          class: "ap-preview__canvas",
          "data-roam": __props.settings.roam
        }, [
          _createElementVNode$2("div", _hoisted_7$1, [
            _createVNode$2(_component_v_icon, {
              icon: "mdi-paw-outline",
              size: "40"
            }),
            _cache[5] || (_cache[5] = _createElementVNode$2("span", null, "你的 Pet，在这里活动", -1))
          ]),
          __props.pet.mode === "stage" && __props.settings.roam === "surfaces" ? (_openBlock$2(), _createElementBlock$2(_Fragment, { key: 0 }, [
            _cache[6] || (_cache[6] = _createElementVNode$2("div", { class: "v-sheet ap-preview__surface ap-preview__surface--left" }, [
              _createElementVNode$2("span", null, "小平台")
            ], -1)),
            _cache[7] || (_cache[7] = _createElementVNode$2("div", { class: "v-sheet ap-preview__surface ap-preview__surface--right" }, [
              _createElementVNode$2("span", null, "休息台")
            ], -1))
          ], 64)) : _createCommentVNode$2("", true),
          _cache[9] || (_cache[9] = _createElementVNode$2("div", {
            class: "ap-preview__floor",
            "aria-hidden": "true"
          }, null, -1)),
          mounted.value && __props.pet.mode === "stage" ? (_openBlock$2(), _createBlock$1(_resolveDynamicComponent(stageComponent.value), {
            key: `${__props.pluginId}:${__props.pet.key}:${positionVersion.value}`,
            agent: _unref$2(host),
            pet: context.value,
            api: __props.api,
            "plugin-id": __props.pluginId,
            "preview-root": canvas.value,
            "settings-override": __props.settings,
            "preview-pose": previewPose.value,
            onLoadState
          }, null, 40, ["agent", "pet", "api", "plugin-id", "preview-root", "settings-override", "preview-pose"])) : mounted.value ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_8$1, [
            (_openBlock$2(), _createBlock$1(AgentPetSprite, {
              key: `${__props.pluginId}:${__props.pet.key}:${positionVersion.value}`,
              agent: _unref$2(host),
              pet: context.value,
              api: __props.api,
              "plugin-id": __props.pluginId,
              action: rendererAction.value,
              "motion-active": !paused.value && !reducedMotion.value,
              "strict-preview": "",
              onLoadState
            }, null, 8, ["agent", "pet", "api", "plugin-id", "action", "motion-active"]))
          ])) : _createCommentVNode$2("", true),
          failed.value ? (_openBlock$2(), _createBlock$1(_component_v_alert, {
            key: 3,
            type: "error",
            variant: "tonal",
            density: "compact",
            class: "ap-preview__error"
          }, {
            default: _withCtx$2(() => [..._cache[8] || (_cache[8] = [
              _createTextVNode$2("此 Pet 加载失败，请点击右上角重置重试。", -1)
            ])]),
            _: 1
          })) : _createCommentVNode$2("", true),
          _createElementVNode$2("span", _hoisted_9$1, _toDisplayString$2(__props.pet.mode === "stage" ? "拖动 Pet 试试 · 调整会即时显示" : "助手入口外观 · 试试下方动作"), 1)
        ], 8, _hoisted_6$1),
        _createElementVNode$2("footer", _hoisted_10$1, [
          _cache[15] || (_cache[15] = _createElementVNode$2("span", { class: "ap-muted" }, "预览动作", -1)),
          _createVNode$2(_component_v_btn_toggle, {
            modelValue: action.value,
            "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => action.value = $event),
            mandatory: "",
            density: "compact",
            variant: "text",
            color: "primary",
            class: "ap-preview__toggle"
          }, {
            default: _withCtx$2(() => [
              _createVNode$2(_component_v_btn, {
                value: "auto",
                size: "small"
              }, {
                default: _withCtx$2(() => [..._cache[10] || (_cache[10] = [
                  _createTextVNode$2("自主活动", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_btn, {
                value: "wave",
                size: "small"
              }, {
                default: _withCtx$2(() => [..._cache[11] || (_cache[11] = [
                  _createTextVNode$2("招手", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_btn, {
                value: "thinking",
                size: "small"
              }, {
                default: _withCtx$2(() => [..._cache[12] || (_cache[12] = [
                  _createTextVNode$2("思考", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_btn, {
                value: "speaking",
                size: "small"
              }, {
                default: _withCtx$2(() => [..._cache[13] || (_cache[13] = [
                  _createTextVNode$2("说话", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_btn, {
                value: "happy",
                size: "small"
              }, {
                default: _withCtx$2(() => [..._cache[14] || (_cache[14] = [
                  _createTextVNode$2("开心", -1)
                ])]),
                _: 1
              })
            ]),
            _: 1
          }, 8, ["modelValue"])
        ])
      ]);
    };
  }
});

const PetPreview = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-3c5112ac"]]);

const {defineComponent:_defineComponent$1} = await importShared('vue');

const {createElementVNode:_createElementVNode$1,unref:_unref$1,toDisplayString:_toDisplayString$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,createCommentVNode:_createCommentVNode$1,createTextVNode:_createTextVNode$1} = await importShared('vue');

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
      { value: "free", title: "自由停放", hint: "没有重力，放在哪里停在哪里，空闲时在屏幕内慢慢游走" }
    ];
    function update(patch) {
      emit("update:modelValue", { ...props.modelValue, ...patch });
    }
    function reset() {
      emit("update:modelValue", { ...DEFAULT_SETTINGS });
    }
    return (_ctx, _cache) => {
      const _component_v_slider = _resolveComponent$1("v-slider");
      const _component_v_select = _resolveComponent$1("v-select");
      const _component_v_spacer = _resolveComponent$1("v-spacer");
      const _component_v_btn = _resolveComponent$1("v-btn");
      return _openBlock$1(), _createElementBlock$1("div", _hoisted_1$1, [
        _cache[4] || (_cache[4] = _createElementVNode$1("div", { class: "text-subtitle-2 mb-1" }, "角色大小", -1)),
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
          "onUpdate:modelValue": _cache[0] || (_cache[0] = (value) => update({ scale: Number(value) }))
        }, {
          append: _withCtx$1(() => [
            _createElementVNode$1("span", _hoisted_2$1, _toDisplayString$1(props.modelValue.scale.toFixed(2)) + "×", 1)
          ]),
          _: 1
        }, 8, ["model-value", "min", "max", "disabled"]),
        _cache[5] || (_cache[5] = _createElementVNode$1("div", { class: "text-subtitle-2 mt-4 mb-1" }, "移动速度", -1)),
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
          "onUpdate:modelValue": _cache[1] || (_cache[1] = (value) => update({ speed: Number(value) }))
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
          "onUpdate:modelValue": _cache[2] || (_cache[2] = (value) => update({ roam: value }))
        }, null, 8, ["model-value", "disabled", "hint"]),
        _createElementVNode$1("div", _hoisted_4$1, [
          props.livePreview ? (_openBlock$1(), _createElementBlock$1("span", _hoisted_5$1, _toDisplayString$1(props.previewOnly ? "仅在预览区试调。小映与 Codex Pet 共用活动设置，保存后对所有用户生效。" : "调整时页面上正在运行的小映或 Codex Pet 会实时变化，保存后对所有用户生效。"), 1)) : _createCommentVNode$1("", true),
          _createVNode$1(_component_v_spacer),
          _createVNode$1(_component_v_btn, {
            variant: "text",
            size: "small",
            disabled: props.disabled,
            onClick: reset
          }, {
            default: _withCtx$1(() => [..._cache[3] || (_cache[3] = [
              _createTextVNode$1("恢复默认", -1)
            ])]),
            _: 1
          }, 8, ["disabled"])
        ])
      ]);
    };
  }
});

const StageSettings = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-e8d7b7fa"]]);

const {defineComponent:_defineComponent} = await importShared('vue');

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,unref:_unref,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementVNode:_createElementVNode,createElementBlock:_createElementBlock} = await importShared('vue');

const _hoisted_1 = { class: "ap-page" };
const _hoisted_2 = { class: "ap-page__content" };
const _hoisted_3 = {
  key: 4,
  class: "ap-empty"
};
const _hoisted_4 = {
  key: 5,
  class: "ap-editor-grid"
};
const _hoisted_5 = { class: "ap-controls" };
const _hoisted_6 = { class: "ap-control-panel" };
const _hoisted_7 = { class: "ap-pet-identity" };
const _hoisted_8 = ["src", "alt"];
const _hoisted_9 = { class: "ap-muted" };
const _hoisted_10 = {
  key: 0,
  class: "ap-muted mt-3 mb-0"
};
const _hoisted_11 = { class: "ap-control-panel" };
const _hoisted_12 = { class: "ap-section-title" };
const _hoisted_13 = {
  key: 1,
  class: "ap-muted mb-0"
};
const _hoisted_14 = { class: "ap-control-panel" };
const _hoisted_15 = {
  key: 6,
  class: "ap-empty"
};
const _hoisted_16 = { class: "ap-footer" };
const _hoisted_17 = {
  key: 0,
  class: "ap-change"
};
const _hoisted_18 = {
  key: 1,
  class: "ap-muted"
};
const _hoisted_19 = { class: "ap-footer__actions" };
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
    emit("layout", { maxWidth: "76rem" });
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
    const dirty = computed(() => !sameSettings(draft.value, saved.value));
    const changedNames = computed(
      () => [
        draft.value.scale !== saved.value.scale ? "大小" : "",
        draft.value.speed !== saved.value.speed ? "速度" : "",
        draft.value.roam !== saved.value.roam ? "活动范围" : ""
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
      draft.value = { ...saved.value };
      feedback.value = "";
    }
    async function save() {
      if (blocked.value || !props.api || !currentPet.value) return;
      const api = props.api;
      const id = props.pluginId;
      const values = { ...draft.value };
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
        feedbackType.value = "success";
        feedback.value = agent ? "活动调整已保存，并已通知当前页面更新。" : "活动调整已保存。";
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
              default: _withCtx(() => [..._cache[6] || (_cache[6] = [
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
          feedback.value ? (_openBlock(), _createBlock(_component_v_alert, {
            key: 3,
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
          }, 8, ["type"])) : _createCommentVNode("", true),
          loading.value && !snapshot.value ? (_openBlock(), _createElementBlock("div", _hoisted_3, [
            _createVNode(_component_v_progress_circular, {
              indeterminate: "",
              color: "primary"
            }),
            _cache[7] || (_cache[7] = _createElementVNode("span", { class: "ap-muted" }, "正在准备你的 Pet…", -1))
          ])) : snapshot.value && currentPet.value ? (_openBlock(), _createElementBlock("div", _hoisted_4, [
            _createElementVNode("aside", _hoisted_5, [
              _createElementVNode("section", _hoisted_6, [
                _cache[8] || (_cache[8] = _createElementVNode("h2", { class: "ap-section-title" }, "选择 Pet", -1)),
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
                _createElementVNode("div", _hoisted_7, [
                  _unref(petImage)(currentPet.value) ? (_openBlock(), _createElementBlock("img", {
                    key: 0,
                    src: _unref(petImage)(currentPet.value),
                    alt: currentPet.value.name
                  }, null, 8, _hoisted_8)) : _createCommentVNode("", true),
                  _createElementVNode("div", null, [
                    _createElementVNode("strong", null, _toDisplayString(currentPet.value.name), 1),
                    _createElementVNode("div", _hoisted_9, _toDisplayString(currentPet.value.mode === "stage" ? "自由活动的角色" : "助手入口的形象") + " · " + _toDisplayString(currentPet.value.builtin ? "内置" : "已导入"), 1)
                  ])
                ]),
                currentPet.value.description ? (_openBlock(), _createElementBlock("p", _hoisted_10, _toDisplayString(currentPet.value.description), 1)) : _createCommentVNode("", true)
              ]),
              _createElementVNode("section", _hoisted_11, [
                _createElementVNode("h2", _hoisted_12, _toDisplayString(currentPet.value.mode === "stage" ? "活动调整" : "入口外观"), 1),
                currentPet.value.mode === "stage" ? (_openBlock(), _createBlock(StageSettings, {
                  key: 0,
                  modelValue: draft.value,
                  "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => draft.value = $event),
                  "live-preview": true,
                  disabled: blocked.value,
                  "preview-only": true
                }, null, 8, ["modelValue", "disabled"])) : (_openBlock(), _createElementBlock("p", _hoisted_13, " 此 Pet 显示在助手入口，位置与拖拽由 MP 控制。可在预览区切换动作，在 MP 设置中选择使用。 "))
              ]),
              _createElementVNode("section", _hoisted_14, [
                _cache[10] || (_cache[10] = _createElementVNode("h2", { class: "ap-section-title" }, "在 MP 中使用", -1)),
                _cache[11] || (_cache[11] = _createElementVNode("div", { class: "ap-muted" }, "当前系统默认", -1)),
                _createElementVNode("strong", null, _toDisplayString(defaultName.value), 1),
                _cache[12] || (_cache[12] = _createElementVNode("p", { class: "ap-muted mt-3 mb-0" }, "保存调整后，在「设定 → 系统 → 智能助手配置 → 助手形象」中选择 Pet。", -1)),
                !snapshot.value.enabled ? (_openBlock(), _createBlock(_component_v_alert, {
                  key: 0,
                  type: "info",
                  variant: "tonal",
                  density: "compact",
                  class: "mt-3"
                }, {
                  default: _withCtx(() => [..._cache[9] || (_cache[9] = [
                    _createTextVNode("先在配置页启用插件，形象才会出现在 MP 的可选列表中。", -1)
                  ])]),
                  _: 1
                })) : _createCommentVNode("", true)
              ])
            ]),
            (_openBlock(), _createBlock(PetPreview, {
              key: props.pluginId,
              pet: currentPet.value,
              settings: draft.value,
              api: props.api,
              "plugin-id": props.pluginId
            }, null, 8, ["pet", "settings", "api", "plugin-id"]))
          ])) : !loading.value ? (_openBlock(), _createElementBlock("div", _hoisted_15, [
            _createVNode(_component_v_icon, {
              icon: "mdi-paw-outline",
              size: "44",
              color: "primary"
            }),
            _createElementVNode("strong", null, _toDisplayString(error.value ? "Pet 暂时未能加载" : "还没有可预览的 Pet"), 1),
            _createVNode(_component_v_btn, {
              variant: "tonal",
              color: "primary",
              onClick: _cache[5] || (_cache[5] = ($event) => error.value ? refresh() : emit("switch"))
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(error.value ? "重新加载" : "前往素材管理"), 1)
              ]),
              _: 1
            })
          ])) : _createCommentVNode("", true)
        ]),
        _createElementVNode("footer", _hoisted_16, [
          dirty.value ? (_openBlock(), _createElementBlock("span", _hoisted_17, [
            _createVNode(_component_v_icon, {
              icon: "mdi-circle",
              size: "7"
            }),
            _createTextVNode("未保存 · " + _toDisplayString(changedNames.value.join("、")), 1)
          ])) : (_openBlock(), _createElementBlock("span", _hoisted_18, "预览中的调整不会自动保存")),
          _createElementVNode("div", _hoisted_19, [
            _createVNode(_component_v_btn, {
              variant: "text",
              disabled: blocked.value || !dirty.value,
              onClick: restore
            }, {
              default: _withCtx(() => [..._cache[13] || (_cache[13] = [
                _createTextVNode("撤销", -1)
              ])]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode(_component_v_btn, {
              variant: "flat",
              color: "primary",
              "prepend-icon": "mdi-content-save-outline",
              disabled: blocked.value || !dirty.value,
              loading: busy.value,
              onClick: save
            }, {
              default: _withCtx(() => [..._cache[14] || (_cache[14] = [
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
