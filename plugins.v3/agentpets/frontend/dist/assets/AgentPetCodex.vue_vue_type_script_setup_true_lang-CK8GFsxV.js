import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { s as stageAction } from './mappings-jvCB_8v9.js';
import AgentPetSprite from './__federation_expose_AgentPetSprite-kB970YWT.js';
import AgentPet from './__federation_expose_AgentPet-vrHH2K_o.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,mergeProps:_mergeProps,createVNode:_createVNode,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');

const {ref} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "AgentPetCodex",
  props: {
    agent: { default: null },
    pet: { default: null },
    api: { default: null },
    pluginId: { default: "" },
    sourcePluginId: { default: "" },
    previewRoot: {},
    settingsOverride: {},
    previewMaxSize: {},
    previewPose: {},
    calibrationOverride: {},
    showCalibration: { type: Boolean },
    mappingsOverride: {},
    nativeAction: {},
    replay: {}
  },
  emits: ["load-state", "pack-ready"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const appearance = ref({ name: "Codex Pet", aspectRatio: 192 / 208 });
    return (_ctx, _cache) => {
      return _openBlock(), _createBlock(AgentPet, _mergeProps(props, {
        "character-name": appearance.value.name,
        "aspect-ratio": appearance.value.aspectRatio
      }), {
        default: _withCtx(({ pose, facingLeft, motionActive }) => [
          _createVNode(AgentPetSprite, _mergeProps(props, {
            action: _unref(stageAction)(pose, facingLeft).action,
            "mapping-key": _unref(stageAction)(pose, facingLeft).key,
            "motion-active": motionActive,
            "strict-preview": !!props.previewRoot,
            onLoadState: _cache[0] || (_cache[0] = ($event) => emit("load-state", $event)),
            onPackReady: _cache[1] || (_cache[1] = ($event) => emit("pack-ready", $event)),
            onAppearance: _cache[2] || (_cache[2] = ($event) => appearance.value = $event)
          }), null, 16, ["action", "mapping-key", "motion-active", "strict-preview"])
        ]),
        _: 1
      }, 16, ["character-name", "aspect-ratio"]);
    };
  }
});

export { _sfc_main as _ };
