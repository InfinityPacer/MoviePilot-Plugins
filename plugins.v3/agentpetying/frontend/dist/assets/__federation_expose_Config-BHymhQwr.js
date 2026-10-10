import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { A as AGENT_HOST_KEY } from './host-BuCMr8PM.js';
import { S as SETTINGS_EVENT, a as SCALE_RANGE, b as SPEED_RANGE, n as normalizeSettings, _ as _export_sfc } from './_plugin-vue_export-helper-_cxh9xlI.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,unref:_unref,toDisplayString:_toDisplayString,withCtx:_withCtx,createTextVNode:_createTextVNode,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');

const _hoisted_1 = { class: "agent-pet-ying-config__value" };
const _hoisted_2 = { class: "agent-pet-ying-config__value" };
const _hoisted_3 = { class: "text-caption text-medium-emphasis mt-3" };
const {inject,onBeforeUnmount,ref} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Config",
  props: {
    initialConfig: { default: null },
    pluginId: { default: "" }
  },
  emits: ["save", "close"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const agent = inject(AGENT_HOST_KEY, null);
    function normalizeConfig(value) {
      return { enabled: Boolean(value?.enabled), ...normalizeSettings(value) };
    }
    const saved = normalizeConfig(props.initialConfig);
    const config = ref({ ...saved });
    let committed = false;
    function preview() {
      agent?.emit?.(SETTINGS_EVENT, { ...normalizeSettings(config.value) });
    }
    function save() {
      committed = true;
      emit("save", { ...config.value, ...normalizeSettings(config.value) });
    }
    function reset() {
      config.value = { ...config.value, scale: 1, speed: 1 };
      preview();
    }
    onBeforeUnmount(() => {
      if (!committed) agent?.emit?.(SETTINGS_EVENT, { scale: saved.scale, speed: saved.speed });
    });
    return (_ctx, _cache) => {
      const _component_v_switch = _resolveComponent("v-switch");
      const _component_v_slider = _resolveComponent("v-slider");
      const _component_v_card_text = _resolveComponent("v-card-text");
      const _component_v_btn = _resolveComponent("v-btn");
      const _component_v_spacer = _resolveComponent("v-spacer");
      const _component_v_card_actions = _resolveComponent("v-card-actions");
      const _component_v_card = _resolveComponent("v-card");
      return _openBlock(), _createBlock(_component_v_card, {
        flat: "",
        class: "agent-pet-ying-config"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_switch, {
                modelValue: config.value.enabled,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => config.value.enabled = $event),
                label: "启用插件",
                color: "primary",
                "hide-details": "",
                class: "mb-4"
              }, null, 8, ["modelValue"]),
              _cache[4] || (_cache[4] = _createElementVNode("div", { class: "text-subtitle-2 mb-1" }, "角色大小", -1)),
              _createVNode(_component_v_slider, {
                modelValue: config.value.scale,
                "onUpdate:modelValue": [
                  _cache[1] || (_cache[1] = ($event) => config.value.scale = $event),
                  preview
                ],
                min: _unref(SCALE_RANGE)[0],
                max: _unref(SCALE_RANGE)[1],
                step: 0.05,
                color: "primary",
                "thumb-label": "",
                "hide-details": "",
                "aria-label": "角色大小"
              }, {
                append: _withCtx(() => [
                  _createElementVNode("span", _hoisted_1, _toDisplayString(config.value.scale.toFixed(2)) + "×", 1)
                ]),
                _: 1
              }, 8, ["modelValue", "min", "max"]),
              _cache[5] || (_cache[5] = _createElementVNode("div", { class: "text-subtitle-2 mt-4 mb-1" }, "移动速度", -1)),
              _createVNode(_component_v_slider, {
                modelValue: config.value.speed,
                "onUpdate:modelValue": [
                  _cache[2] || (_cache[2] = ($event) => config.value.speed = $event),
                  preview
                ],
                min: _unref(SPEED_RANGE)[0],
                max: _unref(SPEED_RANGE)[1],
                step: 0.05,
                color: "primary",
                "thumb-label": "",
                "hide-details": "",
                "aria-label": "移动速度"
              }, {
                append: _withCtx(() => [
                  _createElementVNode("span", _hoisted_2, _toDisplayString(config.value.speed.toFixed(2)) + "×", 1)
                ]),
                _: 1
              }, 8, ["modelValue", "min", "max"]),
              _createElementVNode("div", _hoisted_3, _toDisplayString(_unref(agent) ? "拖动滑块时，页面上正在运行的小映会实时变化；保存后对所有用户生效。" : "当前主程序不支持实时预览，保存后刷新页面生效。") + " 在个人设置的「助手形象」中选择小映后，她会出现在屏幕底部。 ", 1)
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_actions, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: reset
              }, {
                default: _withCtx(() => [..._cache[6] || (_cache[6] = [
                  _createTextVNode("恢复默认", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[3] || (_cache[3] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [..._cache[7] || (_cache[7] = [
                  _createTextVNode("关闭", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                color: "primary",
                variant: "flat",
                onClick: save
              }, {
                default: _withCtx(() => [..._cache[8] || (_cache[8] = [
                  _createTextVNode("保存", -1)
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

const Config = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-146fb22c"]]);

export { Config as default };
