import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { s as stageAction } from './_plugin-vue_export-helper-DQ595t25.js';
import AgentPetSprite from './__federation_expose_AgentPetSprite-DFMVwLR5.js';
import AgentPet, { s as supportsLookDirections } from './__federation_expose_AgentPet-DoWO5VWt.js';

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
    previewPeekEdge: {},
    previewPeekAngle: {},
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
    const appearance = ref({
      name: "Codex Pet",
      aspectRatio: 192 / 208,
      eye: null
    });
    const lookDirections = ref(false);
    function onPackReady(pack) {
      lookDirections.value = supportsLookDirections(pack);
      emit("pack-ready", pack);
    }
    function onLoadState(state) {
      if (state !== "ready") lookDirections.value = false;
      emit("load-state", state);
    }
    return (_ctx, _cache) => {
      return _openBlock(), _createBlock(AgentPet, _mergeProps(props, {
        "character-name": appearance.value.name,
        "aspect-ratio": appearance.value.aspectRatio,
        "peek-eye": appearance.value.eye,
        "look-directions": lookDirections.value
      }), {
        default: _withCtx(({ pose, facingLeft, motionActive, peekEdge, peekFromLeft, gazeAction }) => [
          _createVNode(AgentPetSprite, _mergeProps(props, {
            action: _unref(stageAction)(pose, facingLeft, !!peekEdge).action,
            "mapping-key": _unref(stageAction)(pose, facingLeft, !!peekEdge).key,
            "native-action": peekEdge ? void 0 : gazeAction ?? props.nativeAction,
            "motion-active": motionActive,
            "mirror-x": __props.pet?.key === "builtin-chibiterasu" && !!peekEdge && peekFromLeft,
            "strict-preview": !!props.previewRoot,
            onLoadState,
            onPackReady,
            onAppearance: _cache[0] || (_cache[0] = ($event) => appearance.value = $event)
          }), null, 16, ["action", "mapping-key", "native-action", "motion-active", "mirror-x", "strict-preview"])
        ]),
        _: 1
      }, 16, ["character-name", "aspect-ratio", "peek-eye", "look-directions"]);
    };
  }
});

export { _sfc_main as _ };
