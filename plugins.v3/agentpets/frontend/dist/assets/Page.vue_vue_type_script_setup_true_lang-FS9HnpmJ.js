import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { u as unwrap, A as AGENT_HOST_KEY, H as HOST_UNSUPPORTED_MESSAGE, b as builtinAvatar, l as loadEditor, a as loadHostSelection, s as saveSharedSettings, c as savePetSettings, d as saveMappings, e as saveCalibration } from './host-KC_Y5wME.js';
import { L as LANDMARKS, a as calibrationPoint, D as DEFAULT_CALIBRATION, f as moveCalibrationPoint, d as suggestedLandmark, p as parseCalibration, _ as _export_sfc, o as mappingRows, A as ACTION_LABELS, q as nativeChoices, H as HOST_ACTIONS, t as HOST_INTENTS, s as stageAction, e as sameCalibration, l as sameMappings, P as PACK_UPDATED_EVENT } from './_plugin-vue_export-helper-DHgn0gTZ.js';
import { P as POSES, b as builtinDefaultCalibration } from './poses-ThlqHr1z.js';
import { N as DEFAULT_PEEK_ANGLES, O as normalizePeekAngle, n as normalizePeekAngles, Q as MIN_SURFACE_WIDTH, R as PEEK_PREVIEW_MAX_ANGLE, D as DEFAULT_SETTINGS, J as sharedOf, M as sameAppearance, K as sameShared, g as normalizeSettings, L as appearanceOf, T as SCALE_RANGE, U as SPEED_RANGE, S as SETTINGS_EVENT } from './settings-DtFgdyvj.js';
import AgentPetSprite from './__federation_expose_AgentPetSprite-BM3Cp9gi.js';
import AgentPet from './__federation_expose_AgentPet-DktZ4QJn.js';
import { _ as _sfc_main$5 } from './AgentPetCodex.vue_vue_type_script_setup_true_lang-D-4ChcWF.js';

const {defineComponent:_defineComponent$4} = await importShared('vue');

const {createElementVNode:_createElementVNode$4,resolveComponent:_resolveComponent$4,createVNode:_createVNode$4,createTextVNode:_createTextVNode$4,withCtx:_withCtx$4,openBlock:_openBlock$4,createBlock:_createBlock$3,createCommentVNode:_createCommentVNode$3,unref:_unref$4,renderList:_renderList$2,Fragment:_Fragment$3,createElementBlock:_createElementBlock$4,toDisplayString:_toDisplayString$4} = await importShared('vue');

const _hoisted_1$4 = { class: "ap-calibration" };
const _hoisted_2$4 = { class: "d-flex align-center ga-2 mb-2" };
const _hoisted_3$4 = { class: "ap-calibration__fields" };
const _hoisted_4$3 = {
  key: 1,
  class: "text-caption text-medium-emphasis mb-2"
};
const _hoisted_5$3 = {
  key: 2,
  class: "ap-calibration__fields"
};
const _hoisted_6$2 = { class: "d-flex align-center ga-2 mt-3" };
const _hoisted_7$2 = { class: "ap-calibration__fields" };
const {computed: computed$4,onBeforeUnmount: onBeforeUnmount$2,ref: ref$3} = await importShared('vue');
const _sfc_main$4 = /* @__PURE__ */ _defineComponent$4({
  __name: "CalibrationControls",
  props: {
    modelValue: {},
    packId: {},
    api: {},
    pluginId: {},
    disabled: { type: Boolean },
    codex: { type: Boolean },
    defaultValue: {}
  },
  emits: ["update:modelValue"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const busy = ref$3(false);
    const error = ref$3("");
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
    const disabled = computed$4(() => props.disabled || busy.value);
    const eyeEnabled = computed$4(() => props.modelValue.eye_x != null && props.modelValue.eye_y != null);
    const eyeFields = [
      { key: "eye_x", title: "双眼中心横坐标" },
      { key: "eye_y", title: "眼线纵坐标" }
    ];
    const landmarkLabels = { left_eye: "画面左眼", right_eye: "画面右眼", head_top: "头顶" };
    const landmarkFields = LANDMARKS.flatMap(
      (point) => ["x", "y"].map((axis) => ({
        point,
        axis,
        key: `${point}_${axis}`,
        title: `${landmarkLabels[point]}${axis === "x" ? "横" : "纵"}坐标`
      }))
    );
    const placed = computed$4(() => LANDMARKS.filter((key) => calibrationPoint(props.modelValue, key)).length);
    function updateLandmark(key, axis, percent) {
      try {
        const current = calibrationPoint(props.modelValue, key) ? props.modelValue : moveCalibrationPoint(props.modelValue, key, suggestedLandmark(props.modelValue, key));
        emit("update:modelValue", parseCalibration({ ...current, [`${key}_${axis}`]: percent / 100 }));
        error.value = "";
      } catch (reason) {
        error.value = reason.message;
      }
    }
    function clearLandmarks() {
      emit(
        "update:modelValue",
        parseCalibration({ ...props.modelValue, ...Object.fromEntries(landmarkFields.map((field) => [field.key, null])) })
      );
    }
    function toggleEye(enabled) {
      const value = props.modelValue;
      try {
        emit(
          "update:modelValue",
          parseCalibration({
            ...value,
            eye_x: enabled ? value.left + (value.right - value.left) * 0.5 - value.offset_x : null,
            eye_y: enabled ? value.top + (value.bottom - value.top) * 0.35 - value.bottom + value.baseline - value.offset_y : null
          })
        );
        error.value = "";
      } catch (reason) {
        error.value = reason.message;
      }
    }
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
        const suggested = parseCalibration(unwrap(response));
        emit(
          "update:modelValue",
          parseCalibration({
            ...suggested,
            eye_x: props.modelValue.eye_x,
            eye_y: props.modelValue.eye_y,
            ...Object.fromEntries(landmarkFields.map((field) => [field.key, props.modelValue[field.key]]))
          })
        );
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
      const _component_v_switch = _resolveComponent$4("v-switch");
      const _component_v_alert = _resolveComponent$4("v-alert");
      return _openBlock$4(), _createElementBlock$4("section", _hoisted_1$4, [
        _createElementVNode$4("div", _hoisted_2$4, [
          _cache[4] || (_cache[4] = _createElementVNode$4("strong", null, "显示校准", -1)),
          _createVNode$4(_component_v_spacer),
          !__props.defaultValue ? (_openBlock$4(), _createBlock$3(_component_v_btn, {
            key: 0,
            size: "small",
            variant: "text",
            loading: busy.value,
            disabled: disabled.value,
            onClick: suggest
          }, {
            default: _withCtx$4(() => [..._cache[2] || (_cache[2] = [
              _createTextVNode$4("识别建议", -1)
            ])]),
            _: 1
          }, 8, ["loading", "disabled"])) : _createCommentVNode$3("", true),
          _createVNode$4(_component_v_btn, {
            size: "small",
            variant: "text",
            disabled: disabled.value,
            onClick: _cache[0] || (_cache[0] = ($event) => emit("update:modelValue", { ...__props.defaultValue ?? _unref$4(DEFAULT_CALIBRATION) }))
          }, {
            default: _withCtx$4(() => [..._cache[3] || (_cache[3] = [
              _createTextVNode$4("恢复默认", -1)
            ])]),
            _: 1
          }, 8, ["disabled"])
        ]),
        _cache[7] || (_cache[7] = _createElementVNode$4("p", { class: "text-caption text-medium-emphasis" }, " 坐标为原图单格百分比，所有帧共用。虚线框为显示与拖拽范围，底线为站立线；原图保留，框外内容不显示。点击底部「保存调整」生效，「撤销」放弃草稿。 ", -1)),
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
        !__props.codex ? (_openBlock$4(), _createBlock$3(_component_v_switch, {
          key: 0,
          class: "mt-3",
          label: "校准偷窥眼位",
          "model-value": eyeEnabled.value,
          disabled: disabled.value,
          density: "compact",
          "hide-details": "",
          "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => toggleEye(!!$event))
        }, null, 8, ["model-value", "disabled"])) : _createCommentVNode$3("", true),
        !__props.codex ? (_openBlock$4(), _createElementBlock$4("p", _hoisted_4$3, " 标记正面偷窥首帧的双眼中点，再选择底边或下角侧边试览微调；倾斜后只露一只眼。未校准时先安全露头，不保证露眼精度。 ")) : _createCommentVNode$3("", true),
        eyeEnabled.value && !__props.codex ? (_openBlock$4(), _createElementBlock$4("div", _hoisted_5$3, [
          (_openBlock$4(), _createElementBlock$4(_Fragment$3, null, _renderList$2(eyeFields, (field) => {
            return _createVNode$4(_component_v_text_field, {
              key: field.key,
              label: field.title,
              "model-value": Math.round((__props.modelValue[field.key] ?? 0) * 1e4) / 100,
              type: "number",
              suffix: "%",
              step: 0.5,
              min: 0,
              max: 100,
              density: "compact",
              variant: "outlined",
              "hide-details": "",
              disabled: disabled.value,
              "onUpdate:modelValue": ($event) => update(field.key, Number($event))
            }, null, 8, ["label", "model-value", "disabled", "onUpdate:modelValue"]);
          }), 64))
        ])) : _createCommentVNode$3("", true),
        __props.codex ? (_openBlock$4(), _createElementBlock$4(_Fragment$3, { key: 3 }, [
          _createElementVNode$4("div", _hoisted_6$2, [
            _createElementVNode$4("strong", null, "双眼与头顶 · " + _toDisplayString$4(placed.value) + "/3", 1),
            _createVNode$4(_component_v_spacer),
            _createVNode$4(_component_v_btn, {
              size: "small",
              variant: "text",
              disabled: disabled.value || !placed.value,
              onClick: clearLandmarks
            }, {
              default: _withCtx$4(() => [..._cache[5] || (_cache[5] = [
                _createTextVNode$4("清除三点", -1)
              ])]),
              _: 1
            }, 8, ["disabled"])
          ]),
          _cache[6] || (_cache[6] = _createElementVNode$4("p", { class: "text-caption text-medium-emphasis mb-2" }, " 在完整形象中拖动光圈到两只瞳孔中心和实际头顶；左右以画面为准。虚线圈仅为待标定位置，不会自动保存。 双眼都标定后用于单眼偷看定位，头顶用于露头边界；未标定时仍沿用旧中点。方向键可微调，Esc 取消本次拖动。 ", -1)),
          _createElementVNode$4("div", _hoisted_7$2, [
            (_openBlock$4(true), _createElementBlock$4(_Fragment$3, null, _renderList$2(_unref$4(landmarkFields), (field) => {
              return _openBlock$4(), _createBlock$3(_component_v_text_field, {
                key: field.key,
                label: field.title,
                "model-value": __props.modelValue[field.key] == null ? "" : Math.round(__props.modelValue[field.key] * 1e4) / 100,
                type: "number",
                suffix: "%",
                step: 0.1,
                min: 0,
                max: 100,
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                disabled: disabled.value,
                "onUpdate:modelValue": ($event) => updateLandmark(field.point, field.axis, Number($event))
              }, null, 8, ["label", "model-value", "disabled", "onUpdate:modelValue"]);
            }), 128))
          ])
        ], 64)) : _createCommentVNode$3("", true),
        error.value ? (_openBlock$4(), _createBlock$3(_component_v_alert, {
          key: 4,
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

const CalibrationControls = /* @__PURE__ */ _export_sfc(_sfc_main$4, [["__scopeId", "data-v-03ebae90"]]);

const {defineComponent:_defineComponent$3} = await importShared('vue');

const {toDisplayString:_toDisplayString$3,createElementVNode:_createElementVNode$3,resolveComponent:_resolveComponent$3,createVNode:_createVNode$3,createTextVNode:_createTextVNode$3,withCtx:_withCtx$3,renderList:_renderList$1,Fragment:_Fragment$2,openBlock:_openBlock$3,createElementBlock:_createElementBlock$3,unref:_unref$3,createBlock:_createBlock$2} = await importShared('vue');

const _hoisted_1$3 = { class: "ap-mappings" };
const _hoisted_2$3 = { class: "ap-inline mb-2" };
const _hoisted_3$3 = { class: "ap-section-title mb-0" };
const {computed: computed$3} = await importShared('vue');
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
    const rows = computed$3(() => mappingRows(props.mode));
    const groups = computed$3(() => [...new Set(rows.value.map((row) => row.group))]);
    const animations = computed$3(
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

const ActionMappingEditor = /* @__PURE__ */ _export_sfc(_sfc_main$3, [["__scopeId", "data-v-6c330988"]]);

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

const {createElementVNode:_createElementVNode$2,toDisplayString:_toDisplayString$2,createTextVNode:_createTextVNode$2,resolveComponent:_resolveComponent$2,withCtx:_withCtx$2,createVNode:_createVNode$2,openBlock:_openBlock$2,createElementBlock:_createElementBlock$2,createCommentVNode:_createCommentVNode$2,unref:_unref$2,normalizeStyle:_normalizeStyle,Fragment:_Fragment$1,createBlock:_createBlock$1,resolveDynamicComponent:_resolveDynamicComponent,normalizeClass:_normalizeClass,mergeProps:_mergeProps,renderSlot:_renderSlot,vShow:_vShow,withDirectives:_withDirectives,renderList:_renderList} = await importShared('vue');

const _hoisted_1$2 = { class: "ap-preview__viewer" };
const _hoisted_2$2 = { class: "ap-preview__header" };
const _hoisted_3$2 = {
  key: 0,
  class: "ap-preview__mode"
};
const _hoisted_4$2 = ["data-roam"];
const _hoisted_5$2 = {
  key: 3,
  class: "ap-preview__entry"
};
const _hoisted_6$1 = {
  key: 5,
  class: "ap-preview__hint"
};
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
const _hoisted_11$1 = {
  key: 1,
  class: "ap-inline"
};
const _hoisted_12$1 = { class: "ap-preview__editor" };
const _hoisted_13$1 = { class: "ap-preview__scroll" };
const _hoisted_14$1 = { class: "ap-preview__panel" };
const _hoisted_15$1 = { class: "ap-preview__library" };
const _hoisted_16$1 = { class: "ap-inline mb-2" };
const _hoisted_17$1 = { class: "ap-preview__choices" };
const _hoisted_18$1 = { class: "ap-muted mb-0" };
const _hoisted_19$1 = {
  key: 2,
  class: "ap-preview__angle"
};
const _hoisted_20$1 = { class: "ap-inline" };
const _hoisted_21$1 = { "aria-live": "polite" };
const _hoisted_22$1 = {
  key: 4,
  class: "ap-preview__panel ap-muted"
};
const _hoisted_23$1 = {
  key: 1,
  class: "ap-preview__panel ap-muted"
};
const {computed: computed$2,onBeforeUnmount: onBeforeUnmount$1,onMounted,ref: ref$2,shallowRef,watch: watch$1} = await importShared('vue');
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
  emits: ["error", "pack-ready", "mappings", "calibration", "settings"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const loadedPack = ref$2(null);
    const replay = ref$2(0);
    const original = ref$2(false);
    const editorTab = ref$2(props.initialTab);
    const calibrationEdge = ref$2(null);
    const showGuides = ref$2(true);
    const defaultCalibrationAngle = computed$2(() => DEFAULT_PEEK_ANGLES[calibrationEdge.value ?? "bottom"]);
    const calibrationAngle = computed$2({
      get: () => normalizePeekAngles(props.settings.peek_angles)[calibrationEdge.value ?? "bottom"],
      set: (value) => {
        if (!calibrationEdge.value || props.disabled) return;
        emit("settings", {
          ...props.settings,
          peek_angles: {
            ...normalizePeekAngles(props.settings.peek_angles),
            [calibrationEdge.value]: normalizePeekAngle(value, defaultCalibrationAngle.value)
          }
        });
      }
    });
    const calibrationZoom = ref$2(1);
    const calibrating = computed$2(
      () => editorTab.value === "calibration" && props.pet.mode === "stage" && !!loadedPack.value && !!props.calibration
    );
    const editingLandmarks = computed$2(() => calibrating.value && !calibrationEdge.value && !!props.calibration);
    const peekChoices = [
      { title: "完整形象", value: null },
      { title: "底边偷看试览", value: "bottom" },
      { title: "左下侧边试览", value: "left" },
      { title: "右下侧边试览", value: "right" }
    ];
    const activePeekEdge = computed$2(
      () => props.pet.mode === "stage" && editorTab.value === "calibration" ? calibrationEdge.value : null
    );
    const expanded = ref$2(false);
    const previewMode = ref$2("debug");
    const testingPlatforms = computed$2(
      () => !calibrating.value && props.pet.mode === "stage" && previewMode.value === "movement" && props.settings.roam === "surfaces"
    );
    const platformsAvailable = ref$2(true);
    const previewSettings = computed$2(
      () => previewMode.value === "debug" || calibrating.value ? { ...props.settings, movement: "fixed", roam: "free" } : props.settings
    );
    const previewMaxSize = ref$2({ width: 280, height: 220 });
    const playing = ref$2("自主动作");
    const previewGroup = ref$2(props.pet.key === "ying" ? "poses" : "native");
    function onPackReady(pack) {
      loadedPack.value = pack;
      emit("pack-ready", pack);
    }
    const failed = ref$2(false);
    function onLoadState(state) {
      failed.value = state === "error";
      emit("error", failed.value);
    }
    const canvas = ref$2(null);
    const mounted = ref$2(false);
    const paused = ref$2(false);
    const playbackStatus = computed$2(() => {
      if (activePeekEdge.value) {
        const label = peekChoices.find((choice) => choice.value === activePeekEdge.value).title;
        return `${label} · 锁定偷看首帧`;
      }
      return calibrating.value ? "校准中：锁定偷看首帧" : `${paused.value ? "已暂停" : "正在播放"}：${playing.value}`;
    });
    const action = ref$2("auto");
    const positionVersion = ref$2(0);
    const host = createMockHost(props.pluginId);
    function newContext() {
      const pet = createMockPet(props.pet.mode, props.pet.key);
      if (previewMode.value === "debug") void pet.storage?.set?.({ roam: "free", xRatio: 0.5, yRatio: 0.5 });
      return pet;
    }
    const context = shallowRef(newContext());
    const comparisonContext = computed$2(() => createMockPet("renderer", props.pet.key));
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
    const animations = computed$2(() => loadedPack.value ? nativeChoices(loadedPack.value) : []);
    const choices = computed$2(() => {
      if (previewGroup.value === "poses") return POSES.map((value) => ({ value: `pose:${value}`, title: poseLabels[value] }));
      if (previewGroup.value === "actions")
        return HOST_ACTIONS.map((value) => ({ value: `action:${value}`, title: ACTION_LABELS[value] }));
      if (previewGroup.value === "intents")
        return HOST_INTENTS.map((value) => ({ value: `intent:${value}`, title: ACTION_LABELS[value] }));
      if (previewGroup.value === "directions")
        return Object.keys(loadedPack.value?.actions ?? {}).filter((key) => key.startsWith("look-")).map((key) => ({ value: `native:${key}`, title: key.slice(5).replace("-", ".") + "°" }));
      return animations.value.map((item) => ({ value: `native:${item.value}`, title: item.title }));
    });
    const nativeAction = computed$2(() => action.value.startsWith("native:") ? action.value.slice(7) : void 0);
    const rendererAction = computed$2(() => action.value.startsWith("action:") ? action.value.slice(7) : null);
    const rendererIntent = computed$2(() => action.value.startsWith("intent:") ? action.value.slice(7) : "idle");
    const previewPose = computed$2(
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
    const stageComponent = computed$2(() => props.pet.key === "ying" ? AgentPet : _sfc_main$5);
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const reducedMotion = ref$2(mediaQuery.matches);
    let observer;
    function resize() {
      if (!canvas.value) return;
      const { width, height } = canvas.value.getBoundingClientRect();
      platformsAvailable.value = width * 0.9 >= MIN_SURFACE_WIDTH;
      const maxHeight = testingPlatforms.value && platformsAvailable.value ? Math.min(height - 40, height * 0.55 - 16) : height - 40;
      previewMaxSize.value = { width: Math.max(1, width - 32), height: Math.max(1, maxHeight) };
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
      host.patch({
        motionAllowed: !calibrating.value && !paused.value && !reducedMotion.value,
        reducedMotion: reducedMotion.value
      });
    }
    function updateAction() {
      host.patch({ phase: action.value === "auto" ? "idle" : "thinking", thinking: false, panelOpen: false });
    }
    watch$1(previewGroup, () => choose("auto"));
    watch$1(testingPlatforms, resize);
    watch$1([() => props.pet.mode, () => props.pet.key, positionVersion, previewMode], () => {
      context.value = newContext();
    });
    watch$1(paused, updateMotion);
    watch$1(calibrating, updateMotion);
    watch$1([() => props.pet.key, () => props.pluginId], () => {
      showGuides.value = true;
    });
    watch$1(
      () => props.pet.key,
      () => {
        onLoadState("loading");
        loadedPack.value = null;
        previewGroup.value = props.pet.key === "ying" ? "poses" : "native";
        action.value = "auto";
        playing.value = "自主动作";
        original.value = false;
        calibrationEdge.value = null;
        calibrationZoom.value = 1;
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
      const _component_v_tooltip = _resolveComponent$2("v-tooltip");
      const _component_v_switch = _resolveComponent$2("v-switch");
      const _component_v_tab = _resolveComponent$2("v-tab");
      const _component_v_tabs = _resolveComponent$2("v-tabs");
      const _component_v_spacer = _resolveComponent$2("v-spacer");
      const _component_v_select = _resolveComponent$2("v-select");
      const _component_v_slider = _resolveComponent$2("v-slider");
      return _openBlock$2(), _createElementBlock$2("section", {
        class: _normalizeClass(["ap-preview", { "ap-preview--expanded": expanded.value }]),
        "aria-label": "Pet 实时预览"
      }, [
        _createElementVNode$2("div", _hoisted_1$2, [
          _createElementVNode$2("header", _hoisted_2$2, [
            _cache[17] || (_cache[17] = _createElementVNode$2("div", { class: "ap-inline" }, [
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
          __props.pet.mode === "stage" && !calibrating.value ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_3$2, [
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
                  default: _withCtx$2(() => [..._cache[18] || (_cache[18] = [
                    _createTextVNode$2("动作调试", -1)
                  ])]),
                  _: 1
                }),
                _createVNode$2(_component_v_btn, {
                  value: "movement",
                  size: "small"
                }, {
                  default: _withCtx$2(() => [..._cache[19] || (_cache[19] = [
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
              class: _normalizeClass(["ap-preview__canvas", { "ap-preview__canvas--debug": previewMode.value === "debug" || calibrating.value }]),
              "data-roam": previewSettings.value.roam
            }, [
              testingPlatforms.value && platformsAvailable.value ? (_openBlock$2(), _createElementBlock$2(_Fragment$1, { key: 0 }, [
                _createElementVNode$2("div", {
                  class: "v-sheet ap-preview__surface ap-preview__surface--left",
                  style: _normalizeStyle({ minWidth: `${_unref$2(MIN_SURFACE_WIDTH)}px` })
                }, [..._cache[20] || (_cache[20] = [
                  _createElementVNode$2("span", null, "小平台", -1)
                ])], 4),
                _createElementVNode$2("div", {
                  class: "v-sheet ap-preview__surface ap-preview__surface--right",
                  style: _normalizeStyle({ minWidth: `${_unref$2(MIN_SURFACE_WIDTH)}px` })
                }, [..._cache[21] || (_cache[21] = [
                  _createElementVNode$2("span", null, "休息台", -1)
                ])], 4)
              ], 64)) : _createCommentVNode$2("", true),
              _cache[23] || (_cache[23] = _createElementVNode$2("div", {
                class: "ap-preview__floor",
                "aria-hidden": "true"
              }, null, -1)),
              mounted.value && editingLandmarks.value ? (_openBlock$2(), _createElementBlock$2("div", {
                key: 1,
                class: "ap-preview__calibration-entry",
                style: _normalizeStyle({ transform: `scale(${calibrationZoom.value})` })
              }, [
                (_openBlock$2(), _createBlock$1(AgentPetSprite, {
                  key: `${__props.pluginId}:${__props.pet.key}:landmarks`,
                  agent: _unref$2(host),
                  pet: context.value,
                  api: __props.api,
                  "plugin-id": __props.pluginId,
                  action: "peek",
                  "mapping-key": "stage.peek",
                  "mappings-override": __props.mappings,
                  "calibration-override": __props.calibration,
                  "motion-active": false,
                  "show-calibration": showGuides.value,
                  "edit-calibration": showGuides.value,
                  "calibration-disabled": __props.disabled,
                  "calibration-zoom": calibrationZoom.value,
                  "strict-preview": "",
                  onPackReady,
                  onLoadState,
                  onCalibrationChange: _cache[2] || (_cache[2] = ($event) => emit("calibration", $event))
                }, null, 8, ["agent", "pet", "api", "plugin-id", "mappings-override", "calibration-override", "show-calibration", "edit-calibration", "calibration-disabled", "calibration-zoom"]))
              ], 4)) : mounted.value && __props.pet.mode === "stage" ? (_openBlock$2(), _createBlock$1(_resolveDynamicComponent(stageComponent.value), {
                key: `${__props.pluginId}:${__props.pet.key}:${positionVersion.value}:${previewMode.value}`,
                agent: _unref$2(host),
                pet: context.value,
                api: __props.api,
                "plugin-id": __props.pluginId,
                "preview-root": canvas.value,
                "preview-max-size": previewMaxSize.value,
                "settings-override": previewSettings.value,
                "preview-pose": previewPose.value,
                "preview-peek-edge": activePeekEdge.value,
                "native-action": calibrating.value ? void 0 : nativeAction.value,
                "mappings-override": __props.mappings,
                "calibration-override": __props.calibration,
                "show-calibration": editorTab.value === "calibration" && !!__props.calibration && showGuides.value,
                replay: replay.value,
                onPackReady,
                onLoadState
              }, null, 40, ["agent", "pet", "api", "plugin-id", "preview-root", "preview-max-size", "settings-override", "preview-pose", "preview-peek-edge", "native-action", "mappings-override", "calibration-override", "show-calibration", "replay"])) : mounted.value ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_5$2, [
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
                  "show-calibration": editorTab.value === "calibration" && !!__props.calibration && showGuides.value,
                  replay: replay.value,
                  "motion-active": !paused.value && !reducedMotion.value,
                  "strict-preview": "",
                  onPackReady,
                  onLoadState
                }, null, 8, ["agent", "pet", "api", "plugin-id", "action", "intent", "native-action", "mappings-override", "calibration-override", "show-calibration", "replay", "motion-active"]))
              ])) : _createCommentVNode$2("", true),
              failed.value ? (_openBlock$2(), _createBlock$1(_component_v_alert, {
                key: 4,
                type: "error",
                variant: "tonal",
                density: "compact",
                class: "ap-preview__error"
              }, {
                default: _withCtx$2(() => [..._cache[22] || (_cache[22] = [
                  _createTextVNode$2("此 Pet 加载失败，请点击重置重试。", -1)
                ])]),
                _: 1
              })) : _createCommentVNode$2("", true),
              !activePeekEdge.value ? (_openBlock$2(), _createElementBlock$2("span", _hoisted_6$1, _toDisplayString$2(editingLandmarks.value ? showGuides.value ? "拖动光圈标定 · 只改草稿 · 保存后生效" : "光圈已隐藏 · 显示后可继续标定" : original.value ? "当前校准" : previewMode.value === "debug" ? "居中播放 · 不会自行走开" : testingPlatforms.value ? platformsAvailable.value ? "拖到平台上方松手 · 测试站立" : "预览过窄，请放大后测试平台" : "拖动 Pet · 测试移动与跳跃"), 1)) : _createCommentVNode$2("", true)
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
                  "motion-active": !calibrating.value && !paused.value && !reducedMotion.value,
                  "strict-preview": ""
                }, null, 8, ["agent", "pet", "api", "plugin-id", "action", "mapping-key", "intent", "native-action", "mappings-override", "calibration-override", "replay", "motion-active"])
              ]),
              _cache[24] || (_cache[24] = _createElementVNode$2("span", { class: "ap-preview__hint" }, "原始显示", -1))
            ])) : _createCommentVNode$2("", true)
          ], 2),
          _createElementVNode$2("div", _hoisted_9$1, [
            _createElementVNode$2("span", _hoisted_10$1, _toDisplayString$2(playbackStatus.value), 1),
            editingLandmarks.value ? (_openBlock$2(), _createBlock$1(_component_v_btn, {
              key: 0,
              size: "small",
              variant: "text",
              onClick: _cache[3] || (_cache[3] = ($event) => calibrationZoom.value = calibrationZoom.value === 1 ? 2 : 1)
            }, {
              default: _withCtx$2(() => [
                _createTextVNode$2(_toDisplayString$2(calibrationZoom.value === 1 ? "放大头部" : "全身标定"), 1)
              ]),
              _: 1
            })) : _createCommentVNode$2("", true),
            !calibrating.value ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_11$1, [
              _createVNode$2(_component_v_btn, {
                icon: paused.value ? "mdi-play" : "mdi-pause",
                "aria-label": paused.value ? "播放预览" : "暂停预览",
                size: "small",
                variant: "text",
                onClick: _cache[4] || (_cache[4] = ($event) => paused.value = !paused.value)
              }, null, 8, ["icon", "aria-label"]),
              _createVNode$2(_component_v_tooltip, {
                text: "重播当前动作",
                location: "top"
              }, {
                activator: _withCtx$2(({ props: tooltipProps }) => [
                  _createVNode$2(_component_v_btn, _mergeProps(tooltipProps, {
                    icon: "mdi-replay",
                    "aria-label": "重播当前动作",
                    size: "small",
                    variant: "text",
                    onClick: _cache[5] || (_cache[5] = ($event) => replay.value++)
                  }), null, 16)
                ]),
                _: 1
              }),
              _createVNode$2(_component_v_tooltip, {
                text: "重置预览位置，保留当前调整",
                location: "top"
              }, {
                activator: _withCtx$2(({ props: tooltipProps }) => [
                  _createVNode$2(_component_v_btn, _mergeProps(tooltipProps, {
                    icon: "mdi-restore",
                    "aria-label": "重置预览位置",
                    size: "small",
                    variant: "text",
                    onClick: _cache[6] || (_cache[6] = ($event) => positionVersion.value++)
                  }), null, 16)
                ]),
                _: 1
              })
            ])) : _createCommentVNode$2("", true)
          ]),
          loadedPack.value ? (_openBlock$2(), _createBlock$1(_component_v_switch, {
            key: 1,
            modelValue: original.value,
            "onUpdate:modelValue": _cache[7] || (_cache[7] = ($event) => original.value = $event),
            label: "对照原始显示",
            density: "compact",
            "hide-details": "",
            class: "ap-preview__comparison"
          }, null, 8, ["modelValue"])) : _createCommentVNode$2("", true)
        ]),
        _createElementVNode$2("div", _hoisted_12$1, [
          _createVNode$2(_component_v_tabs, {
            modelValue: editorTab.value,
            "onUpdate:modelValue": _cache[8] || (_cache[8] = ($event) => editorTab.value = $event),
            density: "compact",
            color: "primary",
            class: "ap-preview__tabs"
          }, {
            default: _withCtx$2(() => [
              _createVNode$2(_component_v_tab, { value: "activity" }, {
                default: _withCtx$2(() => [..._cache[25] || (_cache[25] = [
                  _createTextVNode$2("活动", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_tab, { value: "animations" }, {
                default: _withCtx$2(() => [..._cache[26] || (_cache[26] = [
                  _createTextVNode$2("动作试播", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_tab, { value: "calibration" }, {
                default: _withCtx$2(() => [..._cache[27] || (_cache[27] = [
                  _createTextVNode$2("校准", -1)
                ])]),
                _: 1
              }),
              _createVNode$2(_component_v_tab, { value: "mappings" }, {
                default: _withCtx$2(() => [..._cache[28] || (_cache[28] = [
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
                _cache[29] || (_cache[29] = _createElementVNode$2("p", { class: "ap-muted" }, "活动设置在详情页中调整，预览不会自动保存。", -1))
              ], true)
            ], 512), [
              [_vShow, editorTab.value === "activity"]
            ]),
            _withDirectives(_createElementVNode$2("div", _hoisted_15$1, [
              _createElementVNode$2("div", _hoisted_16$1, [
                _cache[31] || (_cache[31] = _createElementVNode$2("strong", null, "完整动作预览", -1)),
                _createVNode$2(_component_v_spacer),
                _createVNode$2(_component_v_btn, {
                  size: "small",
                  variant: action.value === "auto" ? "tonal" : "text",
                  onClick: _cache[9] || (_cache[9] = ($event) => choose("auto"))
                }, {
                  default: _withCtx$2(() => [..._cache[30] || (_cache[30] = [
                    _createTextVNode$2("自主动作", -1)
                  ])]),
                  _: 1
                }, 8, ["variant"])
              ]),
              _createVNode$2(_component_v_tabs, {
                modelValue: previewGroup.value,
                "onUpdate:modelValue": _cache[10] || (_cache[10] = ($event) => previewGroup.value = $event),
                density: "compact",
                color: "primary"
              }, {
                default: _withCtx$2(() => [
                  __props.pet.key !== "ying" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 0,
                    value: "native"
                  }, {
                    default: _withCtx$2(() => [..._cache[32] || (_cache[32] = [
                      _createTextVNode$2("原生动画", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true),
                  loadedPack.value?.codex_version === "v2" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 1,
                    value: "directions"
                  }, {
                    default: _withCtx$2(() => [..._cache[33] || (_cache[33] = [
                      _createTextVNode$2("视线方向", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true),
                  __props.pet.mode === "stage" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 2,
                    value: "poses"
                  }, {
                    default: _withCtx$2(() => [..._cache[34] || (_cache[34] = [
                      _createTextVNode$2("活动姿态", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true),
                  __props.pet.mode === "stage" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 3,
                    value: "events"
                  }, {
                    default: _withCtx$2(() => [..._cache[35] || (_cache[35] = [
                      _createTextVNode$2("MP 事件", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true),
                  __props.pet.mode === "renderer" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 4,
                    value: "actions"
                  }, {
                    default: _withCtx$2(() => [..._cache[36] || (_cache[36] = [
                      _createTextVNode$2("MP 动作", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode$2("", true),
                  __props.pet.mode === "renderer" ? (_openBlock$2(), _createBlock$1(_component_v_tab, {
                    key: 5,
                    value: "intents"
                  }, {
                    default: _withCtx$2(() => [..._cache[37] || (_cache[37] = [
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
              _createElementVNode$2("p", _hoisted_18$1, _toDisplayString$2(previewGroup.value === "native" || previewGroup.value === "directions" ? "直接播放素材原始动画，不受动作映射影响。" : "按当前映射预览；运动测试中可拖动 Pet。"), 1)
            ], 512), [
              [_vShow, editorTab.value === "animations"]
            ]),
            _withDirectives(_createElementVNode$2("div", null, [
              loadedPack.value && __props.calibration ? (_openBlock$2(), _createBlock$1(_component_v_switch, {
                key: 0,
                modelValue: showGuides.value,
                "onUpdate:modelValue": _cache[11] || (_cache[11] = ($event) => showGuides.value = $event),
                label: "显示校准光圈",
                density: "compact",
                "hide-details": "",
                class: "ap-preview__panel"
              }, null, 8, ["modelValue"])) : _createCommentVNode$2("", true),
              __props.pet.mode === "stage" ? (_openBlock$2(), _createBlock$1(_component_v_select, {
                key: 1,
                modelValue: calibrationEdge.value,
                "onUpdate:modelValue": _cache[12] || (_cache[12] = ($event) => calibrationEdge.value = $event),
                class: "ap-preview__panel",
                label: "贴边试览",
                items: peekChoices,
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                disabled: __props.disabled
              }, null, 8, ["modelValue", "disabled"])) : _createCommentVNode$2("", true),
              activePeekEdge.value ? (_openBlock$2(), _createElementBlock$2("div", _hoisted_19$1, [
                _createElementVNode$2("div", _hoisted_20$1, [
                  _cache[39] || (_cache[39] = _createElementVNode$2("strong", null, "偷看角度", -1)),
                  _createVNode$2(_component_v_spacer),
                  _createElementVNode$2("output", _hoisted_21$1, _toDisplayString$2(calibrationAngle.value) + "°", 1),
                  _createVNode$2(_component_v_btn, {
                    size: "x-small",
                    variant: "text",
                    "aria-label": "恢复默认偷看角度",
                    disabled: __props.disabled || calibrationAngle.value === defaultCalibrationAngle.value,
                    onClick: _cache[13] || (_cache[13] = ($event) => calibrationAngle.value = defaultCalibrationAngle.value)
                  }, {
                    default: _withCtx$2(() => [..._cache[38] || (_cache[38] = [
                      _createTextVNode$2("重置", -1)
                    ])]),
                    _: 1
                  }, 8, ["disabled"])
                ]),
                _createVNode$2(_component_v_slider, {
                  modelValue: calibrationAngle.value,
                  "onUpdate:modelValue": _cache[14] || (_cache[14] = ($event) => calibrationAngle.value = $event),
                  "aria-label": "偷看试览角度",
                  min: 0,
                  max: _unref$2(PEEK_PREVIEW_MAX_ANGLE),
                  step: 1,
                  disabled: __props.disabled,
                  density: "compact",
                  "hide-details": ""
                }, null, 8, ["modelValue", "max", "disabled"]),
                _cache[40] || (_cache[40] = _createElementVNode$2("p", { class: "ap-muted" }, "当前 Pet 按方向独立保存；点击底部「保存调整」后，正式偷看也会使用此角度。", -1))
              ])) : _createCommentVNode$2("", true),
              loadedPack.value && __props.calibration ? (_openBlock$2(), _createBlock$1(CalibrationControls, {
                key: __props.pet.key,
                "model-value": __props.calibration,
                "pack-id": __props.pet.key,
                api: __props.api,
                "plugin-id": __props.pluginId,
                disabled: __props.disabled,
                codex: __props.pet.mode === "stage",
                "default-value": __props.pet.builtin ? _unref$2(builtinDefaultCalibration)(__props.pet.key) : void 0,
                "onUpdate:modelValue": _cache[15] || (_cache[15] = ($event) => emit("calibration", $event))
              }, null, 8, ["model-value", "pack-id", "api", "plugin-id", "disabled", "codex", "default-value"])) : (_openBlock$2(), _createElementBlock$2("p", _hoisted_22$1, "素材加载后可调整显示区域与脚底基线。"))
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
                "onUpdate:modelValue": _cache[16] || (_cache[16] = ($event) => emit("mappings", $event)),
                onPreview: playNative
              }, null, 8, ["pack", "mode", "model-value", "disabled"])) : (_openBlock$2(), _createElementBlock$2("p", _hoisted_23$1, "此形象使用内置动作，无需设置动作映射。"))
            ], 512), [
              [_vShow, editorTab.value === "mappings"]
            ])
          ])
        ])
      ], 2);
    };
  }
});

const PetPreview = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-804ae9f3"]]);

const {computed: computed$1,ref: ref$1} = await importShared('vue');
function usePetSettings(selectedKey) {
  const defaults = ref$1({ ...DEFAULT_SETTINGS });
  const drafts = ref$1({});
  const saved = ref$1({});
  const conflicts = ref$1({});
  const sharedDraft = ref$1(sharedOf(DEFAULT_SETTINGS));
  const sharedSaved = ref$1(sharedOf(DEFAULT_SETTINGS));
  const sharedConflict = ref$1(null);
  const dirtyKeys = computed$1(
    () => Object.keys(drafts.value).filter((key) => !sameAppearance(drafts.value[key], saved.value[key]))
  );
  const sharedDirty = computed$1(() => !sameShared(sharedDraft.value, sharedSaved.value));
  const dirty = computed$1(() => sharedDirty.value || dirtyKeys.value.length > 0);
  const conflictKeys = computed$1(() => Object.keys(conflicts.value));
  const hasConflict = computed$1(() => !!sharedConflict.value || conflictKeys.value.length > 0);
  const draft = computed$1({
    get: () => ({ ...defaults.value, ...sharedDraft.value, ...drafts.value[selectedKey.value] }),
    set: (value) => {
      const normalized = normalizeSettings(value);
      if (Object.hasOwn(saved.value, selectedKey.value)) drafts.value[selectedKey.value] = appearanceOf(normalized);
      sharedDraft.value = sharedOf(normalized);
    }
  });
  function receive(snapshot, reset = false) {
    defaults.value = { ...snapshot.settings };
    const latestShared = sharedOf(snapshot.settings);
    if (!reset && sharedDirty.value) {
      sharedConflict.value = sameShared(latestShared, sharedSaved.value) ? null : latestShared;
    } else {
      sharedSaved.value = latestShared;
      sharedDraft.value = { ...latestShared };
      sharedConflict.value = null;
    }
    const keys = snapshot.pets.filter((pet) => pet.mode === "stage").map((pet) => pet.key);
    for (const values of [drafts, saved, conflicts]) {
      for (const key of Object.keys(values.value)) if (!keys.includes(key)) delete values.value[key];
    }
    for (const key of keys) {
      const latest = appearanceOf(normalizeSettings({ ...snapshot.settings, ...snapshot.pet_settings?.[key] }));
      const baseline = saved.value[key];
      if (!reset && baseline && !sameAppearance(drafts.value[key], baseline)) {
        if (!sameAppearance(latest, baseline)) conflicts.value[key] = latest;
        else delete conflicts.value[key];
      } else {
        saved.value[key] = latest;
        drafts.value[key] = appearanceOf(latest);
        delete conflicts.value[key];
      }
    }
  }
  function restore() {
    saved.value = { ...saved.value, ...conflicts.value };
    drafts.value = Object.fromEntries(Object.entries(saved.value).map(([key, value]) => [key, appearanceOf(value)]));
    conflicts.value = {};
    if (sharedConflict.value) sharedSaved.value = sharedConflict.value;
    sharedDraft.value = { ...sharedSaved.value };
    sharedConflict.value = null;
  }
  function clear() {
    drafts.value = {};
    saved.value = {};
    conflicts.value = {};
    defaults.value = { ...DEFAULT_SETTINGS };
    sharedSaved.value = sharedOf(DEFAULT_SETTINGS);
    sharedDraft.value = sharedOf(DEFAULT_SETTINGS);
    sharedConflict.value = null;
  }
  return {
    draft,
    drafts,
    saved,
    dirtyKeys,
    sharedDraft,
    sharedSaved,
    sharedDirty,
    dirty,
    conflictKeys,
    hasConflict,
    receive,
    restore,
    clear
  };
}

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
      emit("update:modelValue", {
        ...DEFAULT_SETTINGS,
        ...props.modelValue.peek_angles ? { peek_angles: props.modelValue.peek_angles } : {}
      });
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
          props.livePreview ? (_openBlock$1(), _createElementBlock$1("span", _hoisted_5$1, _toDisplayString$1(props.previewOnly ? "仅在预览区试调。大小与速度按当前 Pet 独立保存；活动方式与范围仍共享，对所有用户生效。" : "大小与速度属于当前 Pet；活动方式与范围共享，保存后对所有用户生效。"), 1)) : _createCommentVNode$1("", true),
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

const StageSettings = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-d8af671a"]]);

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,createBlock:_createBlock,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,isRef:_isRef} = await importShared('vue');

const _hoisted_1 = {
  class: "ap-page",
  "data-agentpets-editor": ""
};
const _hoisted_2 = { class: "ap-header" };
const _hoisted_3 = { class: "ap-brand" };
const _hoisted_4 = ["src"];
const _hoisted_5 = {
  key: 1,
  class: "ap-brand__avatar d-flex align-center justify-center",
  "aria-hidden": "true"
};
const _hoisted_6 = { class: "ap-header__actions" };
const _hoisted_7 = { class: "ap-page__content" };
const _hoisted_8 = { class: "ap-page__notices" };
const _hoisted_9 = {
  key: 0,
  class: "ap-empty"
};
const _hoisted_10 = {
  key: 1,
  class: "ap-editor-grid"
};
const _hoisted_11 = { class: "ap-page__selector" };
const _hoisted_12 = { class: "ap-muted" };
const _hoisted_13 = {
  key: 0,
  class: "ap-muted mb-3"
};
const _hoisted_14 = { class: "ap-control-panel" };
const _hoisted_15 = { class: "ap-section-title" };
const _hoisted_16 = {
  key: 1,
  class: "ap-muted mb-0"
};
const _hoisted_17 = { class: "ap-control-panel" };
const _hoisted_18 = {
  key: 2,
  class: "ap-empty"
};
const _hoisted_19 = {
  key: 1,
  class: "ap-muted"
};
const _hoisted_20 = { class: "ap-footer" };
const _hoisted_21 = {
  key: 0,
  class: "ap-change"
};
const _hoisted_22 = {
  key: 1,
  class: "ap-muted"
};
const _hoisted_23 = { class: "ap-footer__actions" };
const {computed,inject,onBeforeUnmount,ref,watch} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Page",
  props: {
    api: { default: null },
    pluginId: { default: "" },
    sourcePluginId: { default: "" },
    show_switch: { type: Boolean, default: true }
  },
  emits: ["close", "switch", "layout"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    emit("layout", { maxWidth: "72rem" });
    const agent = inject(AGENT_HOST_KEY, null);
    const snapshot = ref(null);
    const avatar = builtinAvatar("ying");
    const avatarFailed = ref(false);
    const selection = ref(null);
    const selectedKey = ref("");
    const activity = usePetSettings(selectedKey);
    const draft = activity.draft;
    const settingsConflict = activity.hasConflict;
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
      const latestCalibration = parseCalibration(pack.calibration);
      const savedCalibration = calibrationSaved.value[key];
      if (savedCalibration && !sameCalibration(calibrationDrafts.value[key], savedCalibration)) {
        if (!sameCalibration(latestCalibration, savedCalibration)) calibrationConflicts.value[key] = latestCalibration;
        else delete calibrationConflicts.value[key];
      } else {
        calibrationSaved.value[key] = latestCalibration;
        calibrationDrafts.value[key] = { ...latestCalibration };
        delete calibrationConflicts.value[key];
      }
      if (!pack.codex_version || currentPet.value?.builtin) return;
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
      () => activity.dirty.value || mappingDirtyKeys.value.length > 0 || calibrationDirtyKeys.value.length > 0
    );
    const changedNames = computed(
      () => [
        activity.dirtyKeys.value.length ? `${activity.dirtyKeys.value.length} 只 Pet 的独立设置` : "",
        activity.sharedDirty.value ? "共享活动方式与范围" : "",
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
        activity.receive(editor.value, reset);
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
        activity.clear();
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
      activity.restore();
      mappingDrafts.value = Object.fromEntries(
        Object.entries(mappingSaved.value).map(([key, value]) => [key, { ...value }])
      );
      feedback.value = "";
    }
    async function save() {
      if (blocked.value || conflictingNames.value.length || activity.hasConflict.value || !props.api || !currentPet.value)
        return;
      const api = props.api;
      const id = props.pluginId;
      const shared = activity.sharedDirty.value ? {
        values: { ...activity.sharedDraft.value },
        expected: { ...activity.sharedSaved.value }
      } : null;
      const appearances = activity.dirtyKeys.value.map((key) => ({
        key,
        values: { ...activity.drafts.value[key] },
        expected: { ...activity.saved.value[key] }
      }));
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
        if (shared) {
          const result = await saveSharedSettings(api, id, shared.values, shared.expected);
          if (!current()) return;
          activity.sharedSaved.value = { ...result };
          agent?.emit?.(SETTINGS_EVENT, { ...result });
        }
        for (const item of appearances) {
          if (!current()) return;
          const result = await savePetSettings(api, id, item.key, item.values, item.expected);
          if (!current()) return;
          activity.saved.value[item.key] = { ...result };
          agent?.emit?.(SETTINGS_EVENT, { key: item.key, ...result, peek_angles: normalizePeekAngles(result.peek_angles) });
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
      const _component_v_btn = _resolveComponent("v-btn");
      const _component_v_alert = _resolveComponent("v-alert");
      const _component_v_progress_circular = _resolveComponent("v-progress-circular");
      const _component_v_select = _resolveComponent("v-select");
      return _openBlock(), _createElementBlock("section", _hoisted_1, [
        _createElementVNode("header", _hoisted_2, [
          _createElementVNode("div", _hoisted_3, [
            !avatarFailed.value ? (_openBlock(), _createElementBlock("img", {
              key: 0,
              src: _unref(avatar),
              alt: "",
              class: "ap-brand__avatar",
              onError: _cache[0] || (_cache[0] = ($event) => avatarFailed.value = true)
            }, null, 40, _hoisted_4)) : (_openBlock(), _createElementBlock("span", _hoisted_5, [
              _createVNode(_component_v_icon, {
                icon: "mdi-paw-outline",
                color: "primary",
                size: "28"
              })
            ])),
            _cache[10] || (_cache[10] = _createElementVNode("div", null, [
              _createElementVNode("div", { class: "ap-eyebrow" }, "MoviePilot / 调整与预览"),
              _createElementVNode("h1", null, "助手形象")
            ], -1))
          ]),
          _createElementVNode("div", _hoisted_6, [
            _createVNode(_component_v_btn, {
              icon: "mdi-refresh",
              "aria-label": "刷新形象列表",
              variant: "text",
              size: "small",
              loading: loading.value,
              disabled: busy.value,
              onClick: _cache[1] || (_cache[1] = ($event) => refresh())
            }, null, 8, ["loading", "disabled"]),
            __props.show_switch ? (_openBlock(), _createBlock(_component_v_btn, {
              key: 0,
              icon: "mdi-cog-outline",
              "aria-label": "打开插件配置",
              variant: "text",
              size: "small",
              disabled: busy.value,
              onClick: _cache[2] || (_cache[2] = ($event) => emit("switch"))
            }, null, 8, ["disabled"])) : _createCommentVNode("", true),
            _createVNode(_component_v_btn, {
              icon: "mdi-close",
              "aria-label": "关闭详情页",
              variant: "text",
              size: "small",
              disabled: busy.value,
              onClick: _cache[3] || (_cache[3] = ($event) => emit("close"))
            }, null, 8, ["disabled"])
          ])
        ]),
        _createElementVNode("div", _hoisted_7, [
          _createElementVNode("div", _hoisted_8, [
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
            _unref(settingsConflict) ? (_openBlock(), _createBlock(_component_v_alert, {
              key: 3,
              type: "warning",
              variant: "tonal",
              density: "compact",
              class: "ap-result"
            }, {
              default: _withCtx(() => [..._cache[11] || (_cache[11] = [
                _createTextVNode(" 大小、速度、偷看角度或共享活动设置已在其他页面更改。已保留草稿；请点击「撤销」载入最新值后重新调整。 ", -1)
              ])]),
              _: 1
            })) : _createCommentVNode("", true),
            conflictingNames.value.length ? (_openBlock(), _createBlock(_component_v_alert, {
              key: 4,
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
              key: 5,
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
          loading.value && !snapshot.value ? (_openBlock(), _createElementBlock("div", _hoisted_9, [
            _createVNode(_component_v_progress_circular, {
              indeterminate: "",
              color: "primary"
            }),
            _cache[12] || (_cache[12] = _createElementVNode("span", { class: "ap-muted" }, "正在准备你的 Pet…", -1))
          ])) : snapshot.value && currentPet.value ? (_openBlock(), _createElementBlock("div", _hoisted_10, [
            _createElementVNode("div", _hoisted_11, [
              _createVNode(_component_v_select, {
                modelValue: selectedKey.value,
                "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => selectedKey.value = $event),
                items: snapshot.value.pets,
                "item-title": "name",
                "item-value": "key",
                label: "预览形象",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                disabled: blocked.value
              }, null, 8, ["modelValue", "items", "disabled"]),
              _createElementVNode("span", _hoisted_12, _toDisplayString(currentPet.value.mode === "stage" ? "自由活动的角色" : "助手入口的形象") + " · " + _toDisplayString(currentPet.value.builtin ? "内置" : "已导入"), 1)
            ]),
            (_openBlock(), _createBlock(PetPreview, {
              key: `${props.pluginId}:${previewVersion.value}`,
              pet: currentPet.value,
              settings: _unref(draft),
              api: props.api,
              "plugin-id": props.pluginId,
              mappings: mappingDrafts.value[selectedKey.value],
              calibration: calibrationDrafts.value[selectedKey.value],
              disabled: blocked.value,
              "initial-tab": "activity",
              onPackReady,
              onMappings: _cache[6] || (_cache[6] = ($event) => mappingDrafts.value[selectedKey.value] = $event),
              onCalibration: _cache[7] || (_cache[7] = ($event) => calibrationDrafts.value[selectedKey.value] = $event),
              onSettings: _cache[8] || (_cache[8] = ($event) => draft.value = $event)
            }, {
              activity: _withCtx(() => [
                currentPet.value.description ? (_openBlock(), _createElementBlock("p", _hoisted_13, _toDisplayString(currentPet.value.description), 1)) : _createCommentVNode("", true),
                _createElementVNode("section", _hoisted_14, [
                  _createElementVNode("h2", _hoisted_15, _toDisplayString(currentPet.value.mode === "stage" ? "活动调整" : "入口外观"), 1),
                  currentPet.value.mode === "stage" ? (_openBlock(), _createBlock(StageSettings, {
                    key: 0,
                    modelValue: _unref(draft),
                    "onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => _isRef(draft) ? draft.value = $event : null),
                    "live-preview": true,
                    disabled: blocked.value,
                    "preview-only": true
                  }, null, 8, ["modelValue", "disabled"])) : (_openBlock(), _createElementBlock("p", _hoisted_16, " 此 Pet 显示在助手入口，位置与拖拽由 MP 控制。可在预览区切换动作，在 MP 设置中选择使用。 "))
                ]),
                _createElementVNode("section", _hoisted_17, [
                  _cache[14] || (_cache[14] = _createElementVNode("h2", { class: "ap-section-title" }, "在 MP 中使用", -1)),
                  _cache[15] || (_cache[15] = _createElementVNode("div", { class: "ap-muted" }, "当前系统默认", -1)),
                  _createElementVNode("strong", null, _toDisplayString(defaultName.value), 1),
                  _cache[16] || (_cache[16] = _createElementVNode("p", { class: "ap-muted mt-3 mb-0" }, "保存调整后，在「设定 → 系统 → 智能助手配置 → 助手形象」中选择 Pet。", -1)),
                  !snapshot.value.enabled ? (_openBlock(), _createBlock(_component_v_alert, {
                    key: 0,
                    type: "info",
                    variant: "tonal",
                    density: "compact",
                    class: "mt-3"
                  }, {
                    default: _withCtx(() => [..._cache[13] || (_cache[13] = [
                      _createTextVNode("先在配置页启用插件，形象才会出现在 MP 的可选列表中。", -1)
                    ])]),
                    _: 1
                  })) : _createCommentVNode("", true)
                ])
              ]),
              _: 1
            }, 8, ["pet", "settings", "api", "plugin-id", "mappings", "calibration", "disabled"]))
          ])) : !loading.value ? (_openBlock(), _createElementBlock("div", _hoisted_18, [
            _createVNode(_component_v_icon, {
              icon: "mdi-paw-outline",
              size: "44",
              color: "primary"
            }),
            _createElementVNode("strong", null, _toDisplayString(error.value ? "Pet 暂时未能加载" : "还没有可预览的 Pet"), 1),
            error.value || __props.show_switch ? (_openBlock(), _createBlock(_component_v_btn, {
              key: 0,
              variant: "tonal",
              color: "primary",
              onClick: _cache[9] || (_cache[9] = ($event) => error.value ? refresh() : emit("switch"))
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(error.value ? "重新加载" : "前往素材管理"), 1)
              ]),
              _: 1
            })) : (_openBlock(), _createElementBlock("p", _hoisted_19, "请从「插件 → 助手形象 → 设置」打开素材管理。"))
          ])) : _createCommentVNode("", true)
        ]),
        _createElementVNode("footer", _hoisted_20, [
          dirty.value ? (_openBlock(), _createElementBlock("span", _hoisted_21, [
            _createVNode(_component_v_icon, {
              icon: "mdi-circle",
              size: "7"
            }),
            _createTextVNode("未保存 · " + _toDisplayString(changedNames.value.join("、")), 1)
          ])) : (_openBlock(), _createElementBlock("span", _hoisted_22, "预览中的调整不会自动保存")),
          _createElementVNode("div", _hoisted_23, [
            _createVNode(_component_v_btn, {
              variant: "text",
              disabled: blocked.value || !dirty.value && !conflictingNames.value.length && !_unref(settingsConflict),
              onClick: restore
            }, {
              default: _withCtx(() => [..._cache[17] || (_cache[17] = [
                _createTextVNode("撤销", -1)
              ])]),
              _: 1
            }, 8, ["disabled"]),
            _createVNode(_component_v_btn, {
              variant: "flat",
              color: "primary",
              "prepend-icon": "mdi-content-save-outline",
              disabled: blocked.value || !dirty.value || conflictingNames.value.length > 0 || _unref(settingsConflict),
              loading: busy.value,
              onClick: save
            }, {
              default: _withCtx(() => [..._cache[18] || (_cache[18] = [
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
