import Config, { n as normalizeArchiveConfig, _ as _export_sfc } from './__federation_expose_Config-DyKOn8Z8.js';
import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createBlock:_createBlock,Fragment:_Fragment} = await importShared('vue');

const _hoisted_1 = { class: "archive-page" };
const _hoisted_2 = {
  key: 0,
  class: "archive-page__state"
};
const {onMounted,ref} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Page",
  props: {
    api: {}
  },
  emits: ["close", "layout"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const config = ref(null);
    const loading = ref(true);
    const errorMessage = ref("");
    const saving = ref(false);
    function isApiResponse(value) {
      return typeof value === "object" && value !== null && "success" in value && typeof value.success === "boolean" && "data" in value;
    }
    function responseData(value) {
      return isApiResponse(value) ? value.data : value;
    }
    async function loadConfig() {
      loading.value = config.value === null;
      errorMessage.value = "";
      if (!props.api) {
        config.value = null;
        errorMessage.value = "宿主 API 不可用，无法读取归档配置。";
        loading.value = false;
        return;
      }
      try {
        const response = await props.api.get("plugin/ArchiveManager");
        const data = responseData(response);
        if (data === null || data === void 0 || isApiResponse(response) && !response.success) {
          throw new Error(isApiResponse(response) ? response.message || "归档配置读取失败" : "归档配置读取失败");
        }
        config.value = normalizeArchiveConfig(data);
      } catch {
        config.value = null;
        errorMessage.value = "归档配置读取失败，请稍后重试。";
      } finally {
        loading.value = false;
      }
    }
    async function saveConfig(next) {
      if (!props.api || saving.value) return;
      saving.value = true;
      errorMessage.value = "";
      try {
        const response = await props.api.put("plugin/ArchiveManager", next);
        if (isApiResponse(response) && !response.success) {
          throw new Error(response.message || "归档配置保存失败");
        }
        await loadConfig();
      } catch {
        errorMessage.value = "归档配置保存失败，请稍后重试。";
      } finally {
        saving.value = false;
      }
    }
    function handleLayout(layout) {
      emit("layout", layout);
    }
    onMounted(() => {
      void loadConfig();
    });
    return (_ctx, _cache) => {
      const _component_VProgressCircular = _resolveComponent("VProgressCircular");
      const _component_VBtn = _resolveComponent("VBtn");
      const _component_VAlert = _resolveComponent("VAlert");
      return _openBlock(), _createElementBlock("section", _hoisted_1, [
        loading.value ? (_openBlock(), _createElementBlock("div", _hoisted_2, [
          _createVNode(_component_VProgressCircular, {
            color: "primary",
            indeterminate: "",
            size: "28",
            width: "2"
          }),
          _cache[1] || (_cache[1] = _createElementVNode("span", null, "正在读取归档配置…", -1))
        ])) : errorMessage.value && !config.value ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 1,
          class: "archive-page__error",
          type: "error",
          variant: "tonal"
        }, {
          append: _withCtx(() => [
            _createVNode(_component_VBtn, {
              size: "small",
              variant: "text",
              onClick: loadConfig
            }, {
              default: _withCtx(() => _cache[2] || (_cache[2] = [
                _createTextVNode("重试")
              ])),
              _: 1
            })
          ]),
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(errorMessage.value) + " ", 1)
          ]),
          _: 1
        })) : config.value ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
          errorMessage.value ? (_openBlock(), _createBlock(_component_VAlert, {
            key: 0,
            class: "archive-page__error",
            type: "error",
            variant: "tonal"
          }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(errorMessage.value), 1)
            ]),
            _: 1
          })) : _createCommentVNode("", true),
          _createVNode(Config, {
            api: _ctx.api,
            "initial-config": config.value,
            onClose: _cache[0] || (_cache[0] = ($event) => emit("close")),
            onLayout: handleLayout,
            onSave: saveConfig
          }, null, 8, ["api", "initial-config"])
        ], 64)) : _createCommentVNode("", true)
      ]);
    };
  }
});

const Page = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-f3a0025c"]]);

export { Page as default };
