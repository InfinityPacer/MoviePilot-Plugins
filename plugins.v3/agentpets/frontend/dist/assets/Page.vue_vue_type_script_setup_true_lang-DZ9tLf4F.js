import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { A as AGENT_HOST_KEY } from './host-BuCMr8PM.js';
import { B as BUILTIN_PACK, a as BUILTIN_PACK_ID, H as HOST_ACTIONS, c as HOST_INTENTS } from './schema-CBvuTKe0.js';
import AgentPetSprite from './__federation_expose_AgentPetSprite-CPsTLCKC.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';
import { D as DEFAULT_SETTINGS, a as SCALE_RANGE, b as SPEED_RANGE, R as ROAM_MODES, S as SETTINGS_EVENT } from './settings-_v7SC99m.js';
import AgentPet from './__federation_expose_AgentPet-DsVUmVgt.js';

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
    onCall?.(call);
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

const {unref:_unref$2,openBlock:_openBlock$2,createBlock:_createBlock$2,normalizeClass:_normalizeClass,createElementVNode:_createElementVNode$1,toDisplayString:_toDisplayString$2,resolveComponent:_resolveComponent$2,createVNode:_createVNode$2,renderList:_renderList$1,Fragment:_Fragment$1,createElementBlock:_createElementBlock$1,createTextVNode:_createTextVNode$2,withCtx:_withCtx$2} = await importShared('vue');

const _hoisted_1$1 = { class: "agent-pet-sprites-page" };
const _hoisted_2$1 = { class: "agent-pet-sprites-page__layout" };
const _hoisted_3$1 = { class: "text-caption text-medium-emphasis mt-2" };
const _hoisted_4$1 = { class: "flex-grow-1" };
const _hoisted_5$1 = { class: "d-flex flex-wrap ga-4" };
const _hoisted_6$1 = { class: "d-flex flex-wrap ga-2" };
const _hoisted_7 = { class: "d-flex flex-wrap ga-2" };
const {computed: computed$1,onBeforeUnmount: onBeforeUnmount$1,onMounted,ref: ref$2} = await importShared('vue');
const _sfc_main$2 = /* @__PURE__ */ _defineComponent$2({
  __name: "SpritePreview",
  props: {
    api: { default: null },
    pluginId: { default: "" }
  },
  setup(__props) {
    const props = __props;
    const instanceId = computed$1(() => props.pluginId || "AgentPets");
    const packs = ref$2([{ id: BUILTIN_PACK_ID, name: BUILTIN_PACK.name }]);
    const selected = ref$2(BUILTIN_PACK_ID);
    const action = ref$2(null);
    const intent = ref$2("idle");
    const thinking = ref$2(false);
    const motionActive = ref$2(true);
    const large = ref$2(false);
    const status = ref$2({ action: "", frame: "" });
    const stageRef = ref$2(null);
    const host = createMockHost(instanceId.value);
    const pet = computed$1(() => createMockPet("renderer", selected.value));
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
        console.warn("[AgentPets] packs unavailable");
      }
    }
    onMounted(() => {
      loadPacks();
      statusTimer = window.setInterval(() => {
        const root = stageRef.value?.querySelector(".agent-pet-sprites");
        status.value = { action: root?.dataset.action ?? "", frame: root?.dataset.frame ?? "" };
      }, 150);
    });
    onBeforeUnmount$1(() => {
      window.clearTimeout(actionTimer);
      window.clearInterval(statusTimer);
      host.dispose();
    });
    return (_ctx, _cache) => {
      const _component_v_select = _resolveComponent$2("v-select");
      const _component_v_switch = _resolveComponent$2("v-switch");
      const _component_v_btn = _resolveComponent$2("v-btn");
      const _component_v_chip = _resolveComponent$2("v-chip");
      const _component_v_chip_group = _resolveComponent$2("v-chip-group");
      return _openBlock$2(), _createElementBlock$1("div", _hoisted_1$1, [
        _createElementVNode$1("div", _hoisted_2$1, [
          _createElementVNode$1("div", null, [
            _createElementVNode$1("div", {
              ref_key: "stageRef",
              ref: stageRef,
              class: _normalizeClass(["agent-pet-sprites-page__stage", { "agent-pet-sprites-page__stage--large": large.value }])
            }, [
              (_openBlock$2(), _createBlock$2(AgentPetSprite, {
                key: selected.value,
                agent: _unref$2(host),
                pet: pet.value,
                api: props.api,
                "plugin-id": instanceId.value,
                action: action.value,
                intent: intent.value,
                thinking: thinking.value,
                "motion-active": motionActive.value
              }, null, 8, ["agent", "pet", "api", "plugin-id", "action", "intent", "thinking", "motion-active"]))
            ], 2),
            _createElementVNode$1("div", _hoisted_3$1, " 播放：" + _toDisplayString$2(status.value.action || "—") + " · 帧：" + _toDisplayString$2(status.value.frame || "—"), 1)
          ]),
          _createElementVNode$1("div", _hoisted_4$1, [
            _createVNode$2(_component_v_select, {
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
            _createElementVNode$1("div", _hoisted_5$1, [
              _createVNode$2(_component_v_switch, {
                modelValue: motionActive.value,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => motionActive.value = $event),
                label: "motionActive",
                density: "compact",
                "hide-details": ""
              }, null, 8, ["modelValue"]),
              _createVNode$2(_component_v_switch, {
                modelValue: thinking.value,
                "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => thinking.value = $event),
                label: "thinking",
                density: "compact",
                "hide-details": ""
              }, null, 8, ["modelValue"]),
              _createVNode$2(_component_v_switch, {
                modelValue: large.value,
                "onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => large.value = $event),
                label: "放大预览框",
                density: "compact",
                "hide-details": ""
              }, null, 8, ["modelValue"])
            ])
          ])
        ]),
        _cache[5] || (_cache[5] = _createElementVNode$1("div", { class: "text-subtitle-2 mt-4 mb-2" }, "宿主事件", -1)),
        _createElementVNode$1("div", _hoisted_6$1, [
          (_openBlock$2(), _createElementBlock$1(_Fragment$1, null, _renderList$1(events, (item) => {
            return _createVNode$2(_component_v_btn, {
              key: item.label,
              size: "small",
              variant: "tonal",
              onClick: item.run
            }, {
              default: _withCtx$2(() => [
                _createTextVNode$2(_toDisplayString$2(item.label), 1)
              ]),
              _: 2
            }, 1032, ["onClick"]);
          }), 64))
        ]),
        _cache[6] || (_cache[6] = _createElementVNode$1("div", { class: "text-subtitle-2 mt-4 mb-2" }, "宿主动作", -1)),
        _createElementVNode$1("div", _hoisted_7, [
          (_openBlock$2(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(_unref$2(HOST_ACTIONS), (name) => {
            return _openBlock$2(), _createBlock$2(_component_v_btn, {
              key: name,
              size: "small",
              variant: action.value === name ? "flat" : "tonal",
              color: action.value === name ? "primary" : void 0,
              onClick: ($event) => playAction(name)
            }, {
              default: _withCtx$2(() => [
                _createTextVNode$2(_toDisplayString$2(name), 1)
              ]),
              _: 2
            }, 1032, ["variant", "color", "onClick"]);
          }), 128))
        ]),
        _cache[7] || (_cache[7] = _createElementVNode$1("div", { class: "text-subtitle-2 mt-4 mb-2" }, "Intent", -1)),
        _createVNode$2(_component_v_chip_group, {
          modelValue: intent.value,
          "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => intent.value = $event),
          mandatory: "",
          "selected-class": "text-primary",
          column: ""
        }, {
          default: _withCtx$2(() => [
            (_openBlock$2(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(_unref$2(HOST_INTENTS), (name) => {
              return _openBlock$2(), _createBlock$2(_component_v_chip, {
                key: name,
                value: name,
                size: "small",
                variant: "outlined"
              }, {
                default: _withCtx$2(() => [
                  _createTextVNode$2(_toDisplayString$2(name), 1)
                ]),
                _: 2
              }, 1032, ["value"]);
            }), 128))
          ]),
          _: 1
        }, 8, ["modelValue"])
      ]);
    };
  }
});

const SpritePreview = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-a89095dc"]]);

const {defineComponent:_defineComponent$1} = await importShared('vue');

const {createTextVNode:_createTextVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,openBlock:_openBlock$1,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode,unref:_unref$1,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString$1,createVNode:_createVNode$1,normalizeStyle:_normalizeStyle,Teleport:_Teleport} = await importShared('vue');

const _hoisted_1 = { class: "agent-pet-ying-page" };
const _hoisted_2 = { class: "d-flex flex-wrap ga-2 mb-4" };
const _hoisted_3 = { class: "d-flex flex-wrap ga-2 mb-4" };
const _hoisted_4 = { class: "d-flex flex-wrap ga-4 mb-2" };
const _hoisted_5 = { class: "text-caption text-medium-emphasis mt-4" };
const _hoisted_6 = { class: "agent-pet-ying-page__stage" };
const {computed,inject: inject$1,onBeforeUnmount,ref: ref$1} = await importShared('vue');
const _sfc_main$1 = /* @__PURE__ */ _defineComponent$1({
  __name: "StagePreview",
  props: {
    api: { default: null },
    pluginId: { default: "" }
  },
  setup(__props) {
    const props = __props;
    const realHost = inject$1(AGENT_HOST_KEY, null);
    const instanceId = computed(() => props.pluginId || "AgentPets");
    const running = ref$1(false);
    const anchor = ref$1(null);
    const interacting = ref$1(false);
    const bubbleText = ref$1("");
    const callLog = ref$1([]);
    const motionAllowed = ref$1(true);
    const pageVisible = ref$1(true);
    const available = ref$1(true);
    const panelShown = ref$1(false);
    const keyboardInset = ref$1(0);
    const scale = ref$1(DEFAULT_SETTINGS.scale);
    const speed = ref$1(DEFAULT_SETTINGS.speed);
    const roam = ref$1(DEFAULT_SETTINGS.roam);
    let host = createMockHost(instanceId.value, (call) => {
      callLog.value = [call, ...callLog.value].slice(0, 8);
    });
    let pet = createPet();
    let bubbleTimer = 0;
    function createPet() {
      return createMockPet("stage", "ying", {
        onAnchor: (rect) => anchor.value = rect,
        onInteracting: (value) => interacting.value = value
      });
    }
    const panelRect = computed(() => {
      if (!panelShown.value) return null;
      const width = Math.min(380, window.innerWidth - 32);
      const height = Math.round(window.innerHeight * 0.6);
      return { x: window.innerWidth - width - 16, y: window.innerHeight - height - 16, width, height };
    });
    const bubbleStyle = computed(() => {
      if (!anchor.value) return { display: "none" };
      const left = Math.min(Math.max(8, anchor.value.x + anchor.value.width / 2 - 110), window.innerWidth - 228);
      return { left: `${left}px`, top: `${Math.max(8, anchor.value.y - 64)}px` };
    });
    function start() {
      host.dispose();
      host = createMockHost(instanceId.value, (call) => {
        callLog.value = [call, ...callLog.value].slice(0, 8);
      });
      pet = createPet();
      host.patch({ motionAllowed: motionAllowed.value, pageVisible: pageVisible.value, available: available.value });
      running.value = true;
    }
    function stop() {
      running.value = false;
      anchor.value = null;
    }
    function say(text) {
      bubbleText.value = text;
      window.clearTimeout(bubbleTimer);
      bubbleTimer = window.setTimeout(() => bubbleText.value = "", 2400);
    }
    const events = [
      {
        label: "panel.open",
        run: () => {
          panelShown.value = true;
          host.patch({ panelOpen: true, panelRect: panelRect.value });
          host.fire("agent.panel.open");
        }
      },
      {
        label: "panel.close",
        run: () => {
          panelShown.value = false;
          host.patch({ panelOpen: false, panelRect: null });
          host.fire("agent.panel.close");
        }
      },
      {
        label: "thinking.start",
        run: () => {
          host.patch({ thinking: true, phase: "thinking" });
          host.fire("agent.thinking.start");
        }
      },
      {
        label: "thinking.end",
        run: () => {
          host.patch({ thinking: false, phase: "idle" });
          host.fire("agent.thinking.end");
        }
      },
      {
        label: "tool.start",
        run: () => {
          host.patch({ phase: "tool", toolName: "search_media" });
          host.fire("agent.tool.start", { name: "search_media" });
        }
      },
      {
        label: "tool.end",
        run: () => {
          host.patch({ phase: "thinking", toolName: null });
          host.fire("agent.tool.end", { name: "search_media" });
        }
      },
      {
        label: "awaiting",
        run: () => {
          host.patch({ phase: "awaiting", thinking: false });
          host.fire("agent.awaiting");
        }
      },
      {
        label: "done",
        run: () => {
          host.patch({ phase: "done", thinking: false });
          host.fire("agent.done", { message: "已完成" });
          say("搞定啦");
        }
      },
      {
        label: "error",
        run: () => {
          host.patch({ phase: "error", thinking: false });
          host.fire("agent.error", { message: "出错了" });
          say("好像出错了");
        }
      },
      {
        label: "preview",
        run: () => {
          host.fire("agent.preview", { text: "正在为你查找影片…" });
          say("正在为你查找影片…");
        }
      },
      {
        label: "bubble",
        run: () => {
          host.fire("agent.bubble", { id: "demo", kind: "notification", variant: "info", text: "订阅已更新" });
          say("订阅已更新");
        }
      }
    ];
    function patchState() {
      host.patch({
        motionAllowed: motionAllowed.value,
        reducedMotion: !motionAllowed.value,
        pageVisible: pageVisible.value,
        available: available.value,
        viewport: { ...host.getState().viewport, keyboardInset: keyboardInset.value }
      });
    }
    function pushSettings() {
      host.emit(SETTINGS_EVENT, { scale: scale.value, speed: speed.value, roam: roam.value });
    }
    onBeforeUnmount(() => {
      window.clearTimeout(bubbleTimer);
      running.value = false;
      host.dispose();
    });
    return (_ctx, _cache) => {
      const _component_v_btn = _resolveComponent$1("v-btn");
      const _component_v_switch = _resolveComponent$1("v-switch");
      const _component_v_slider = _resolveComponent$1("v-slider");
      const _component_v_btn_toggle = _resolveComponent$1("v-btn-toggle");
      return _openBlock$1(), _createElementBlock("div", _hoisted_1, [
        _createElementVNode("div", _hoisted_2, [
          !running.value ? (_openBlock$1(), _createBlock$1(_component_v_btn, {
            key: 0,
            color: "primary",
            variant: "flat",
            onClick: start
          }, {
            default: _withCtx$1(() => [..._cache[8] || (_cache[8] = [
              _createTextVNode$1("放出预览小映", -1)
            ])]),
            _: 1
          })) : (_openBlock$1(), _createBlock$1(_component_v_btn, {
            key: 1,
            variant: "tonal",
            onClick: stop
          }, {
            default: _withCtx$1(() => [..._cache[9] || (_cache[9] = [
              _createTextVNode$1("收起预览小映", -1)
            ])]),
            _: 1
          })),
          _unref$1(realHost) ? (_openBlock$1(), _createBlock$1(_component_v_btn, {
            key: 2,
            variant: "text",
            onClick: _cache[0] || (_cache[0] = ($event) => _unref$1(realHost).open?.())
          }, {
            default: _withCtx$1(() => [..._cache[10] || (_cache[10] = [
              _createTextVNode$1("打开真实助手面板", -1)
            ])]),
            _: 1
          })) : _createCommentVNode("", true)
        ]),
        _cache[11] || (_cache[11] = _createElementVNode("div", { class: "text-subtitle-2 mb-2" }, "宿主事件", -1)),
        _createElementVNode("div", _hoisted_3, [
          (_openBlock$1(), _createElementBlock(_Fragment, null, _renderList(events, (item) => {
            return _createVNode$1(_component_v_btn, {
              key: item.label,
              size: "small",
              variant: "tonal",
              disabled: !running.value,
              onClick: item.run
            }, {
              default: _withCtx$1(() => [
                _createTextVNode$1(_toDisplayString$1(item.label), 1)
              ]),
              _: 2
            }, 1032, ["disabled", "onClick"]);
          }), 64))
        ]),
        _cache[12] || (_cache[12] = _createElementVNode("div", { class: "text-subtitle-2 mb-1" }, "宿主状态", -1)),
        _createElementVNode("div", _hoisted_4, [
          _createVNode$1(_component_v_switch, {
            modelValue: motionAllowed.value,
            "onUpdate:modelValue": [
              _cache[1] || (_cache[1] = ($event) => motionAllowed.value = $event),
              patchState
            ],
            label: "允许动画",
            "hide-details": "",
            density: "compact"
          }, null, 8, ["modelValue"]),
          _createVNode$1(_component_v_switch, {
            modelValue: pageVisible.value,
            "onUpdate:modelValue": [
              _cache[2] || (_cache[2] = ($event) => pageVisible.value = $event),
              patchState
            ],
            label: "页面可见",
            "hide-details": "",
            density: "compact"
          }, null, 8, ["modelValue"]),
          _createVNode$1(_component_v_switch, {
            modelValue: available.value,
            "onUpdate:modelValue": [
              _cache[3] || (_cache[3] = ($event) => available.value = $event),
              patchState
            ],
            label: "Agent 可用",
            "hide-details": "",
            density: "compact"
          }, null, 8, ["modelValue"])
        ]),
        _createVNode$1(_component_v_slider, {
          modelValue: keyboardInset.value,
          "onUpdate:modelValue": [
            _cache[4] || (_cache[4] = ($event) => keyboardInset.value = $event),
            patchState
          ],
          min: 0,
          max: 320,
          step: 10,
          label: "键盘高度",
          "thumb-label": "",
          "hide-details": "",
          class: "mb-2"
        }, null, 8, ["modelValue"]),
        _createVNode$1(_component_v_slider, {
          modelValue: scale.value,
          "onUpdate:modelValue": [
            _cache[5] || (_cache[5] = ($event) => scale.value = $event),
            pushSettings
          ],
          min: _unref$1(SCALE_RANGE)[0],
          max: _unref$1(SCALE_RANGE)[1],
          step: 0.05,
          label: "角色大小",
          "thumb-label": "",
          "hide-details": "",
          class: "mb-2"
        }, null, 8, ["modelValue", "min", "max"]),
        _createVNode$1(_component_v_slider, {
          modelValue: speed.value,
          "onUpdate:modelValue": [
            _cache[6] || (_cache[6] = ($event) => speed.value = $event),
            pushSettings
          ],
          min: _unref$1(SPEED_RANGE)[0],
          max: _unref$1(SPEED_RANGE)[1],
          step: 0.05,
          label: "移动速度",
          "thumb-label": "",
          "hide-details": ""
        }, null, 8, ["modelValue", "min", "max"]),
        _createVNode$1(_component_v_btn_toggle, {
          modelValue: roam.value,
          "onUpdate:modelValue": [
            _cache[7] || (_cache[7] = ($event) => roam.value = $event),
            pushSettings
          ],
          mandatory: "",
          density: "comfortable",
          variant: "outlined",
          divided: "",
          class: "mt-3"
        }, {
          default: _withCtx$1(() => [
            (_openBlock$1(true), _createElementBlock(_Fragment, null, _renderList(_unref$1(ROAM_MODES), (mode) => {
              return _openBlock$1(), _createBlock$1(_component_v_btn, {
                key: mode,
                value: mode,
                size: "small"
              }, {
                default: _withCtx$1(() => [
                  _createTextVNode$1(_toDisplayString$1(mode), 1)
                ]),
                _: 2
              }, 1032, ["value"]);
            }), 128))
          ]),
          _: 1
        }, 8, ["modelValue"]),
        _createElementVNode("div", _hoisted_5, " 锚点：" + _toDisplayString$1(anchor.value ? `${Math.round(anchor.value.x)}, ${Math.round(anchor.value.y)} · ${Math.round(anchor.value.width)}×${Math.round(anchor.value.height)}` : "无") + " · 拖拽中：" + _toDisplayString$1(interacting.value ? "是" : "否") + " · 最近调用：" + _toDisplayString$1(callLog.value.join("，") || "无"), 1),
        running.value ? (_openBlock$1(), _createBlock$1(_Teleport, {
          key: 0,
          to: "body"
        }, [
          _createElementVNode("div", _hoisted_6, [
            panelRect.value ? (_openBlock$1(), _createElementBlock("div", {
              key: 0,
              class: "agent-pet-ying-page__panel",
              style: _normalizeStyle({
                left: `${panelRect.value.x}px`,
                top: `${panelRect.value.y}px`,
                width: `${panelRect.value.width}px`,
                height: `${panelRect.value.height}px`
              })
            }, " 模拟面板 ", 4)) : _createCommentVNode("", true),
            _createVNode$1(AgentPet, {
              agent: _unref$1(host),
              pet: _unref$1(pet),
              api: props.api,
              "plugin-id": instanceId.value
            }, null, 8, ["agent", "pet", "api", "plugin-id"]),
            bubbleText.value && anchor.value ? (_openBlock$1(), _createElementBlock("div", {
              key: 1,
              class: "agent-pet-ying-page__bubble",
              style: _normalizeStyle(bubbleStyle.value)
            }, _toDisplayString$1(bubbleText.value), 5)) : _createCommentVNode("", true)
          ])
        ])) : _createCommentVNode("", true)
      ]);
    };
  }
});

const StagePreview = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-94f40276"]]);

const {defineComponent:_defineComponent} = await importShared('vue');

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,unref:_unref,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');

const {inject,ref} = await importShared('vue');
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
    const tab = ref("stage");
    return (_ctx, _cache) => {
      const _component_v_card_title = _resolveComponent("v-card-title");
      const _component_v_card_subtitle = _resolveComponent("v-card-subtitle");
      const _component_v_card_item = _resolveComponent("v-card-item");
      const _component_v_tab = _resolveComponent("v-tab");
      const _component_v_tabs = _resolveComponent("v-tabs");
      const _component_v_card_text = _resolveComponent("v-card-text");
      const _component_v_spacer = _resolveComponent("v-spacer");
      const _component_v_btn = _resolveComponent("v-btn");
      const _component_v_card_actions = _resolveComponent("v-card-actions");
      const _component_v_card = _resolveComponent("v-card");
      return _openBlock(), _createBlock(_component_v_card, {
        flat: "",
        class: "agent-pets-page"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_item, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_card_title, null, {
                default: _withCtx(() => [..._cache[3] || (_cache[3] = [
                  _createTextVNode("助手形象 · 开发预览", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_card_subtitle, null, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(_unref(realHost) ? `主程序已提供助手宿主（Agent ${_unref(realHost).getState?.().available ? "已启用" : "未启用"}），预览实例由页面内模拟对象驱动` : "主程序未提供助手宿主，使用页面内模拟对象"), 1)
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode(_component_v_tabs, {
            modelValue: tab.value,
            "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => tab.value = $event),
            class: "px-4"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_tab, { value: "stage" }, {
                default: _withCtx(() => [..._cache[4] || (_cache[4] = [
                  _createTextVNode("小映（全屏角色）", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_tab, { value: "sprites" }, {
                default: _withCtx(() => [..._cache[5] || (_cache[5] = [
                  _createTextVNode("素材包（入口外观）", -1)
                ])]),
                _: 1
              })
            ]),
            _: 1
          }, 8, ["modelValue"]),
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              tab.value === "stage" ? (_openBlock(), _createBlock(StagePreview, {
                key: 0,
                api: props.api,
                "plugin-id": props.pluginId
              }, null, 8, ["api", "plugin-id"])) : (_openBlock(), _createBlock(SpritePreview, {
                key: 1,
                api: props.api,
                "plugin-id": props.pluginId
              }, null, 8, ["api", "plugin-id"]))
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_actions, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[1] || (_cache[1] = ($event) => emit("switch"))
              }, {
                default: _withCtx(() => [..._cache[6] || (_cache[6] = [
                  _createTextVNode("设置", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[2] || (_cache[2] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [..._cache[7] || (_cache[7] = [
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

export { _sfc_main as _ };
