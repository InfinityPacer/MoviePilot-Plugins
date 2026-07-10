import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');

const _hoisted_1 = { class: "sae-config-shell" };
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Config",
  props: {
    initialConfig: {},
    api: {}
  },
  emits: ["save", "close", "switch"],
  setup(__props) {
    return (_ctx, _cache) => {
      const _component_VAlert = _resolveComponent("VAlert");
      return _openBlock(), _createElementBlock("section", _hoisted_1, [
        _createVNode(_component_VAlert, {
          type: "info",
          variant: "tonal"
        }, {
          default: _withCtx(() => [..._cache[0] || (_cache[0] = [
            _createTextVNode("订阅助手（增强版）配置页正在加载。", -1)
          ])]),
          _: 1
        })
      ]);
    };
  }
});

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const Config = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-b7e5ca69"]]);

export { Config as default };
