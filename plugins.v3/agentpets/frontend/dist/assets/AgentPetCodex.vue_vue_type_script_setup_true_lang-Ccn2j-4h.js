import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { s as stageAction } from './_plugin-vue_export-helper-Cx9XzNqS.js';
import AgentPetSprite from './__federation_expose_AgentPetSprite-DP-pjhDu.js';
import AgentPet, { b as builtinRhythm, s as supportsRest, a as supportsLookDirections } from './__federation_expose_AgentPet-CFcOc0a3.js';
import { g as greetingPlayback, s as stageCycleDuration, a as airborneFramePhase, r as resolveStageAction } from './playback-Ct5mtRW-.js';

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
    const rhythm = computed(
      () => loadedPack.value && !props.previewRoot && !props.nativeAction ? builtinRhythm(loadedPack.value, props.mappingsOverride) : null
    );
    const startupPlayback = computed(
      () => loadedPack.value ? greetingPlayback(loadedPack.value, props.mappingsOverride) : null
    );
    const restAvailable = computed(
      () => artworkReady.value && !!loadedPack.value && supportsRest(loadedPack.value, props.mappingsOverride)
    );
    const actionPlayback = computed(
      () => loadedPack.value ? Object.fromEntries(
        ["wave", "jump", "talk", "victory", "confused", "sit"].map((pose) => [
          pose,
          stageCycleDuration(loadedPack.value, pose, props.mappingsOverride)
        ])
      ) : {}
    );
    function spriteAction(pose, facingLeft, peeking) {
      return loadedPack.value ? resolveStageAction(loadedPack.value, pose, facingLeft, peeking, props.mappingsOverride) : { key: stageAction(pose, facingLeft, peeking).action, requested: stageAction(pose, facingLeft, peeking).action };
    }
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
        "rest-available": restAvailable.value,
        "action-playback": actionPlayback.value,
        rhythm: rhythm.value
      }), {
        default: _withCtx(({
          pose,
          facingLeft,
          motionActive,
          peekEdge,
          peekFromLeft,
          gazeAction,
          rhythmAction,
          greetingRound,
          greetingComplete,
          walkTravel,
          airProgress,
          playbackRound,
          playbackComplete
        }) => [
          _createVNode(AgentPetSprite, _mergeProps(props, {
            action: spriteAction(pose, facingLeft, !!peekEdge).requested,
            "mapping-key": _unref(stageAction)(pose, facingLeft, !!peekEdge).key,
            "native-action": peekEdge ? void 0 : gazeAction ?? props.nativeAction ?? rhythmAction,
            "motion-active": motionActive,
            replay: (props.replay ?? 0) + greetingRound,
            "walk-travel": !peekEdge && !props.nativeAction && pose.startsWith("walk") ? walkTravel : void 0,
            "frame-phase": !peekEdge && !props.nativeAction ? _unref(airborneFramePhase)(spriteAction(pose, facingLeft, false).key, pose, airProgress) : void 0,
            "playback-round": playbackRound,
            "single-cycle": pose === "sit" && !!actionPlayback.value.sit,
            "mirror-x": __props.pet?.key === "builtin-chibiterasu" && !!peekEdge && peekFromLeft,
            "strict-preview": !!props.previewRoot,
            onLoadState,
            onPackReady,
            onAppearance: _cache[0] || (_cache[0] = ($event) => appearance.value = $event),
            onCycleComplete: ($event) => greetingComplete($event - (props.replay ?? 0)),
            onActionComplete: ($event) => playbackComplete($event)
          }), null, 16, ["action", "mapping-key", "native-action", "motion-active", "replay", "walk-travel", "frame-phase", "playback-round", "single-cycle", "mirror-x", "strict-preview", "onCycleComplete", "onActionComplete"])
        ]),
        _: 1
      }, 16, ["character-name", "aspect-ratio", "peek-eye", "look-directions", "artwork-ready", "greeting-playback", "rest-available", "action-playback", "rhythm"]);
    };
  }
});

export { _sfc_main as _ };
