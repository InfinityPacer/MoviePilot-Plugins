import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { s as stageAction } from './_plugin-vue_export-helper-Cx9XzNqS.js';
import AgentPetSprite from './__federation_expose_AgentPetSprite-B9dYQXAG.js';
import AgentPet, { s as supportsRest, a as supportsLookDirections } from './__federation_expose_AgentPet-CkZhdBpy.js';
import { g as greetingPlayback } from './greeting-B7a9rq7Z.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,mergeProps:_mergeProps,createVNode:_createVNode,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');

const {computed,ref,shallowRef} = await importShared('vue');
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
    const artworkReady = ref(false);
    const loadedPack = shallowRef(null);
    const startupPlayback = computed(
      () => loadedPack.value ? greetingPlayback(loadedPack.value, props.mappingsOverride) : null
    );
    const restAvailable = computed(
      () => artworkReady.value && !!loadedPack.value && supportsRest(loadedPack.value, props.mappingsOverride)
    );
    function onPackReady(pack) {
      loadedPack.value = pack;
      lookDirections.value = supportsLookDirections(pack);
      emit("pack-ready", pack);
    }
    function onLoadState(state) {
      artworkReady.value = state === "ready";
      if (state !== "ready") lookDirections.value = false;
      emit("load-state", state);
    }
    return (_ctx, _cache) => {
      return _openBlock(), _createBlock(AgentPet, _mergeProps(props, {
        "character-name": appearance.value.name,
        "aspect-ratio": appearance.value.aspectRatio,
        "peek-eye": appearance.value.eye,
        "look-directions": lookDirections.value,
        "artwork-ready": artworkReady.value,
        "greeting-playback": startupPlayback.value,
        "rest-available": restAvailable.value
      }), {
        default: _withCtx(({ pose, facingLeft, motionActive, peekEdge, peekFromLeft, gazeAction, greetingRound, greetingComplete }) => [
          _createVNode(AgentPetSprite, _mergeProps(props, {
            action: _unref(stageAction)(pose, facingLeft, !!peekEdge).action,
            "mapping-key": _unref(stageAction)(pose, facingLeft, !!peekEdge).key,
            "native-action": peekEdge ? void 0 : gazeAction ?? props.nativeAction,
            "motion-active": motionActive,
            replay: (props.replay ?? 0) + greetingRound,
            "mirror-x": __props.pet?.key === "builtin-chibiterasu" && !!peekEdge && peekFromLeft,
            "strict-preview": !!props.previewRoot,
            onLoadState,
            onPackReady,
            onAppearance: _cache[0] || (_cache[0] = ($event) => appearance.value = $event),
            onCycleComplete: ($event) => greetingComplete($event - (props.replay ?? 0))
          }), null, 16, ["action", "mapping-key", "native-action", "motion-active", "replay", "mirror-x", "strict-preview", "onCycleComplete"])
        ]),
        _: 1
      }, 16, ["character-name", "aspect-ratio", "peek-eye", "look-directions", "artwork-ready", "greeting-playback", "rest-available"]);
    };
  }
});

export { _sfc_main as _ };
