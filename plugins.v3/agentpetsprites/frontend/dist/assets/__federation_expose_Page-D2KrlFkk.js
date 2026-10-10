import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { a as BUILTIN_PACK, B as BUILTIN_PACK_ID, H as HOST_ACTIONS, c as HOST_INTENTS, _ as _export_sfc } from './_plugin-vue_export-helper-DWQfjxwI.js';
import AgentPet from './__federation_expose_AgentPet-ibQ1quXZ.js';

const AGENT_HOST_KEY = "moviepilot:agent";

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

const {defineComponent:_defineComponent} = await importShared('vue');

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,unref:_unref,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,normalizeClass:_normalizeClass,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');

const _hoisted_1 = { class: "agent-pet-sprites-page__layout" };
const _hoisted_2 = { class: "text-caption text-medium-emphasis mt-2" };
const _hoisted_3 = { class: "flex-grow-1" };
const _hoisted_4 = { class: "d-flex flex-wrap ga-4" };
const _hoisted_5 = { class: "d-flex flex-wrap ga-2" };
const _hoisted_6 = { class: "d-flex flex-wrap ga-2" };
const {computed,inject,onBeforeUnmount,onMounted,ref} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Page",
  props: {
    api: { default: null },
    pluginId: { default: "" }
  },
  emits: ["close", "switch"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const realHost = inject(AGENT_HOST_KEY, null);
    const instanceId = computed(() => props.pluginId || "AgentPetSprites");
    const packs = ref([{ id: BUILTIN_PACK_ID, name: BUILTIN_PACK.name }]);
    const selected = ref(BUILTIN_PACK_ID);
    const action = ref(null);
    const intent = ref("idle");
    const thinking = ref(false);
    const motionActive = ref(true);
    const large = ref(false);
    const status = ref({ action: "", frame: "" });
    const stageRef = ref(null);
    const host = createMockHost(instanceId.value);
    const pet = computed(() => createMockPet("renderer", selected.value));
    let actionTimer = 0;
    let statusTimer = 0;
    const events = [
      { label: "panel.open", run: () => playAction("wave") },
      { label: "panel.close", run: () => intent.value = "docked" },
      { label: "thinking.start", run: () => (thinking.value = true, intent.value = "thinking") },
      { label: "thinking.end", run: () => (thinking.value = false, intent.value = "idle") },
      { label: "tool.start", run: () => intent.value = "thinking" },
      { label: "tool.end", run: () => intent.value = thinking.value ? "thinking" : "idle" },
      { label: "awaiting", run: () => intent.value = "notify" },
      { label: "done", run: () => (thinking.value = false, intent.value = "success") },
      { label: "error", run: () => (thinking.value = false, intent.value = "error") },
      { label: "preview", run: () => intent.value = "speaking" },
      { label: "bubble", run: () => intent.value = "notify" }
    ];
    function playAction(name) {
      action.value = name;
      window.clearTimeout(actionTimer);
      actionTimer = window.setTimeout(() => action.value = null, 2400);
    }
    async function loadPacks() {
      if (!props.api?.get) return;
      try {
        const response = await props.api.get(`plugin/${instanceId.value}/packs`);
        if (response?.success && Array.isArray(response.data) && response.data.length) packs.value = response.data;
      } catch {
        console.warn("[AgentPetSprites] packs unavailable");
      }
    }
    onMounted(() => {
      loadPacks();
      statusTimer = window.setInterval(() => {
        const root = stageRef.value?.querySelector(".agent-pet-sprites");
        status.value = { action: root?.dataset.action ?? "", frame: root?.dataset.frame ?? "" };
      }, 150);
    });
    onBeforeUnmount(() => {
      window.clearTimeout(actionTimer);
      window.clearInterval(statusTimer);
      host.dispose();
    });
    return (_ctx, _cache) => {
      const _component_v_card_title = _resolveComponent("v-card-title");
      const _component_v_card_subtitle = _resolveComponent("v-card-subtitle");
      const _component_v_card_item = _resolveComponent("v-card-item");
      const _component_v_select = _resolveComponent("v-select");
      const _component_v_switch = _resolveComponent("v-switch");
      const _component_v_btn = _resolveComponent("v-btn");
      const _component_v_chip = _resolveComponent("v-chip");
      const _component_v_chip_group = _resolveComponent("v-chip-group");
      const _component_v_card_text = _resolveComponent("v-card-text");
      const _component_v_spacer = _resolveComponent("v-spacer");
      const _component_v_card_actions = _resolveComponent("v-card-actions");
      const _component_v_card = _resolveComponent("v-card");
      return _openBlock(), _createBlock(_component_v_card, {
        flat: "",
        class: "agent-pet-sprites-page"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_item, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_card_title, null, {
                default: _withCtx(() => [..._cache[7] || (_cache[7] = [
                  _createTextVNode("助手形象素材包 · 开发预览", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_card_subtitle, null, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(_unref(realHost) ? `主程序已提供助手宿主（Agent ${_unref(realHost).getState?.().available ? "已启用" : "未启用"}），预览使用页面内模拟对象` : "主程序未提供助手宿主，使用页面内模拟对象"), 1)
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              _createElementVNode("div", _hoisted_1, [
                _createElementVNode("div", null, [
                  _createElementVNode("div", {
                    ref_key: "stageRef",
                    ref: stageRef,
                    class: _normalizeClass(["agent-pet-sprites-page__stage", { "agent-pet-sprites-page__stage--large": large.value }])
                  }, [
                    (_openBlock(), _createBlock(AgentPet, {
                      key: selected.value,
                      agent: _unref(host),
                      pet: pet.value,
                      api: props.api,
                      "plugin-id": instanceId.value,
                      action: action.value,
                      intent: intent.value,
                      thinking: thinking.value,
                      "motion-active": motionActive.value
                    }, null, 8, ["agent", "pet", "api", "plugin-id", "action", "intent", "thinking", "motion-active"]))
                  ], 2),
                  _createElementVNode("div", _hoisted_2, " 播放：" + _toDisplayString(status.value.action || "—") + " · 帧：" + _toDisplayString(status.value.frame || "—"), 1)
                ]),
                _createElementVNode("div", _hoisted_3, [
                  _createVNode(_component_v_select, {
                    modelValue: selected.value,
                    "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => selected.value = $event),
                    items: packs.value,
                    "item-title": "name",
                    "item-value": "id",
                    label: "素材包",
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    class: "mb-3"
                  }, null, 8, ["modelValue", "items"]),
                  _createElementVNode("div", _hoisted_4, [
                    _createVNode(_component_v_switch, {
                      modelValue: motionActive.value,
                      "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => motionActive.value = $event),
                      label: "motionActive",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_switch, {
                      modelValue: thinking.value,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => thinking.value = $event),
                      label: "thinking",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_switch, {
                      modelValue: large.value,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => large.value = $event),
                      label: "放大预览框",
                      density: "compact",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ])
                ])
              ]),
              _cache[8] || (_cache[8] = _createElementVNode("div", { class: "text-subtitle-2 mt-4 mb-2" }, "宿主事件", -1)),
              _createElementVNode("div", _hoisted_5, [
                (_openBlock(), _createElementBlock(_Fragment, null, _renderList(events, (item) => {
                  return _createVNode(_component_v_btn, {
                    key: item.label,
                    size: "small",
                    variant: "tonal",
                    onClick: item.run
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(item.label), 1)
                    ]),
                    _: 2
                  }, 1032, ["onClick"]);
                }), 64))
              ]),
              _cache[9] || (_cache[9] = _createElementVNode("div", { class: "text-subtitle-2 mt-4 mb-2" }, "宿主动作", -1)),
              _createElementVNode("div", _hoisted_6, [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(HOST_ACTIONS), (name) => {
                  return _openBlock(), _createBlock(_component_v_btn, {
                    key: name,
                    size: "small",
                    variant: action.value === name ? "flat" : "tonal",
                    color: action.value === name ? "primary" : void 0,
                    onClick: ($event) => playAction(name)
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(name), 1)
                    ]),
                    _: 2
                  }, 1032, ["variant", "color", "onClick"]);
                }), 128))
              ]),
              _cache[10] || (_cache[10] = _createElementVNode("div", { class: "text-subtitle-2 mt-4 mb-2" }, "Intent", -1)),
              _createVNode(_component_v_chip_group, {
                modelValue: intent.value,
                "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => intent.value = $event),
                mandatory: "",
                "selected-class": "text-primary",
                column: ""
              }, {
                default: _withCtx(() => [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(HOST_INTENTS), (name) => {
                    return _openBlock(), _createBlock(_component_v_chip, {
                      key: name,
                      value: name,
                      size: "small",
                      variant: "outlined"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(name), 1)
                      ]),
                      _: 2
                    }, 1032, ["value"]);
                  }), 128))
                ]),
                _: 1
              }, 8, ["modelValue"])
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_actions, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[5] || (_cache[5] = ($event) => emit("switch"))
              }, {
                default: _withCtx(() => [..._cache[11] || (_cache[11] = [
                  _createTextVNode("设置", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[6] || (_cache[6] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [..._cache[12] || (_cache[12] = [
                  _createTextVNode("关闭", -1)
                ])]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      });
    };
  }
});

const Page = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-4692ee38"]]);

export { Page as default };
