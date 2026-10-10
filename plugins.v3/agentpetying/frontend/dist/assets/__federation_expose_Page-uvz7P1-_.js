import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { A as AGENT_HOST_KEY } from './host-BuCMr8PM.js';
import { D as DEFAULT_SETTINGS, a as SCALE_RANGE, b as SPEED_RANGE, S as SETTINGS_EVENT, _ as _export_sfc } from './_plugin-vue_export-helper-_cxh9xlI.js';
import AgentPet from './__federation_expose_AgentPet-DkrBxilP.js';

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

const {defineComponent:_defineComponent} = await importShared('vue');

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,unref:_unref,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock,normalizeStyle:_normalizeStyle,Teleport:_Teleport} = await importShared('vue');

const _hoisted_1 = { class: "d-flex flex-wrap ga-2 mb-4" };
const _hoisted_2 = { class: "d-flex flex-wrap ga-2 mb-4" };
const _hoisted_3 = { class: "d-flex flex-wrap ga-4 mb-2" };
const _hoisted_4 = { class: "text-caption text-medium-emphasis mt-4" };
const _hoisted_5 = { class: "agent-pet-ying-page__stage" };
const {computed,inject,onBeforeUnmount,ref} = await importShared('vue');
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
    const instanceId = computed(() => props.pluginId || "AgentPetYing");
    const running = ref(false);
    const anchor = ref(null);
    const interacting = ref(false);
    const bubbleText = ref("");
    const callLog = ref([]);
    const motionAllowed = ref(true);
    const pageVisible = ref(true);
    const available = ref(true);
    const panelShown = ref(false);
    const keyboardInset = ref(0);
    const scale = ref(DEFAULT_SETTINGS.scale);
    const speed = ref(DEFAULT_SETTINGS.speed);
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
      host.emit(SETTINGS_EVENT, { scale: scale.value, speed: speed.value });
    }
    onBeforeUnmount(() => {
      window.clearTimeout(bubbleTimer);
      running.value = false;
      host.dispose();
    });
    return (_ctx, _cache) => {
      const _component_v_card_title = _resolveComponent("v-card-title");
      const _component_v_card_subtitle = _resolveComponent("v-card-subtitle");
      const _component_v_card_item = _resolveComponent("v-card-item");
      const _component_v_btn = _resolveComponent("v-btn");
      const _component_v_switch = _resolveComponent("v-switch");
      const _component_v_slider = _resolveComponent("v-slider");
      const _component_v_card_text = _resolveComponent("v-card-text");
      const _component_v_spacer = _resolveComponent("v-spacer");
      const _component_v_card_actions = _resolveComponent("v-card-actions");
      const _component_v_card = _resolveComponent("v-card");
      return _openBlock(), _createBlock(_component_v_card, {
        flat: "",
        class: "agent-pet-ying-page"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_item, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_card_title, null, {
                default: _withCtx(() => [..._cache[9] || (_cache[9] = [
                  _createTextVNode("小映桌宠 · 开发预览", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_card_subtitle, null, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(_unref(realHost) ? `主程序已提供助手宿主（Agent ${_unref(realHost).getState?.().available ? "已启用" : "未启用"}），预览实例仍由页面内模拟对象驱动` : "主程序未提供助手宿主，使用页面内模拟对象"), 1)
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              _createElementVNode("div", _hoisted_1, [
                !running.value ? (_openBlock(), _createBlock(_component_v_btn, {
                  key: 0,
                  color: "primary",
                  variant: "flat",
                  onClick: start
                }, {
                  default: _withCtx(() => [..._cache[10] || (_cache[10] = [
                    _createTextVNode("放出预览小映", -1)
                  ])]),
                  _: 1
                })) : (_openBlock(), _createBlock(_component_v_btn, {
                  key: 1,
                  variant: "tonal",
                  onClick: stop
                }, {
                  default: _withCtx(() => [..._cache[11] || (_cache[11] = [
                    _createTextVNode("收起预览小映", -1)
                  ])]),
                  _: 1
                })),
                _unref(realHost) ? (_openBlock(), _createBlock(_component_v_btn, {
                  key: 2,
                  variant: "text",
                  onClick: _cache[0] || (_cache[0] = ($event) => _unref(realHost).open?.())
                }, {
                  default: _withCtx(() => [..._cache[12] || (_cache[12] = [
                    _createTextVNode("打开真实助手面板", -1)
                  ])]),
                  _: 1
                })) : _createCommentVNode("", true)
              ]),
              _cache[13] || (_cache[13] = _createElementVNode("div", { class: "text-subtitle-2 mb-2" }, "宿主事件", -1)),
              _createElementVNode("div", _hoisted_2, [
                (_openBlock(), _createElementBlock(_Fragment, null, _renderList(events, (item) => {
                  return _createVNode(_component_v_btn, {
                    key: item.label,
                    size: "small",
                    variant: "tonal",
                    disabled: !running.value,
                    onClick: item.run
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(item.label), 1)
                    ]),
                    _: 2
                  }, 1032, ["disabled", "onClick"]);
                }), 64))
              ]),
              _cache[14] || (_cache[14] = _createElementVNode("div", { class: "text-subtitle-2 mb-1" }, "宿主状态", -1)),
              _createElementVNode("div", _hoisted_3, [
                _createVNode(_component_v_switch, {
                  modelValue: motionAllowed.value,
                  "onUpdate:modelValue": [
                    _cache[1] || (_cache[1] = ($event) => motionAllowed.value = $event),
                    patchState
                  ],
                  label: "允许动画",
                  "hide-details": "",
                  density: "compact"
                }, null, 8, ["modelValue"]),
                _createVNode(_component_v_switch, {
                  modelValue: pageVisible.value,
                  "onUpdate:modelValue": [
                    _cache[2] || (_cache[2] = ($event) => pageVisible.value = $event),
                    patchState
                  ],
                  label: "页面可见",
                  "hide-details": "",
                  density: "compact"
                }, null, 8, ["modelValue"]),
                _createVNode(_component_v_switch, {
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
              _createVNode(_component_v_slider, {
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
              _createVNode(_component_v_slider, {
                modelValue: scale.value,
                "onUpdate:modelValue": [
                  _cache[5] || (_cache[5] = ($event) => scale.value = $event),
                  pushSettings
                ],
                min: _unref(SCALE_RANGE)[0],
                max: _unref(SCALE_RANGE)[1],
                step: 0.05,
                label: "角色大小",
                "thumb-label": "",
                "hide-details": "",
                class: "mb-2"
              }, null, 8, ["modelValue", "min", "max"]),
              _createVNode(_component_v_slider, {
                modelValue: speed.value,
                "onUpdate:modelValue": [
                  _cache[6] || (_cache[6] = ($event) => speed.value = $event),
                  pushSettings
                ],
                min: _unref(SPEED_RANGE)[0],
                max: _unref(SPEED_RANGE)[1],
                step: 0.05,
                label: "移动速度",
                "thumb-label": "",
                "hide-details": ""
              }, null, 8, ["modelValue", "min", "max"]),
              _createElementVNode("div", _hoisted_4, " 锚点：" + _toDisplayString(anchor.value ? `${Math.round(anchor.value.x)}, ${Math.round(anchor.value.y)} · ${Math.round(anchor.value.width)}×${Math.round(anchor.value.height)}` : "无") + " · 拖拽中：" + _toDisplayString(interacting.value ? "是" : "否") + " · 最近调用：" + _toDisplayString(callLog.value.join("，") || "无"), 1)
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_actions, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[7] || (_cache[7] = ($event) => emit("switch"))
              }, {
                default: _withCtx(() => [..._cache[15] || (_cache[15] = [
                  _createTextVNode("设置", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[8] || (_cache[8] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [..._cache[16] || (_cache[16] = [
                  _createTextVNode("关闭", -1)
                ])]),
                _: 1
              })
            ]),
            _: 1
          }),
          running.value ? (_openBlock(), _createBlock(_Teleport, {
            key: 0,
            to: "body"
          }, [
            _createElementVNode("div", _hoisted_5, [
              panelRect.value ? (_openBlock(), _createElementBlock("div", {
                key: 0,
                class: "agent-pet-ying-page__panel",
                style: _normalizeStyle({
                  left: `${panelRect.value.x}px`,
                  top: `${panelRect.value.y}px`,
                  width: `${panelRect.value.width}px`,
                  height: `${panelRect.value.height}px`
                })
              }, " 模拟面板 ", 4)) : _createCommentVNode("", true),
              _createVNode(AgentPet, {
                agent: _unref(host),
                pet: _unref(pet),
                api: props.api,
                "plugin-id": instanceId.value
              }, null, 8, ["agent", "pet", "api", "plugin-id"]),
              bubbleText.value && anchor.value ? (_openBlock(), _createElementBlock("div", {
                key: 1,
                class: "agent-pet-ying-page__bubble",
                style: _normalizeStyle(bubbleStyle.value)
              }, _toDisplayString(bubbleText.value), 5)) : _createCommentVNode("", true)
            ])
          ])) : _createCommentVNode("", true)
        ]),
        _: 1
      });
    };
  }
});

const Page = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-fbae7a09"]]);

export { Page as default };
