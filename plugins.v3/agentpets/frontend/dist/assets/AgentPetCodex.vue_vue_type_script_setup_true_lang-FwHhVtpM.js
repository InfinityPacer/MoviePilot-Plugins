import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import AgentPetSprite from './__federation_expose_AgentPetSprite-BbJu4Dqb.js';
import AgentPet from './__federation_expose_AgentPet-zjW_Xv2Q.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {mergeProps:_mergeProps,createVNode:_createVNode,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');

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
    previewPose: {}
  },
  emits: ["load-state"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const appearance = ref({ name: "Codex Pet", aspectRatio: 192 / 208 });
    const POSE_ACTIONS = {
      wave: "wave",
      held: "thinking",
      fall: "jumping",
      jump: "jumping",
      talk: "speaking",
      think: "thinking",
      busy: "charge",
      victory: "success",
      confused: "error",
      alert: "warning",
      doze: "sleep"
    };
    function actionForPose(pose, facingLeft) {
      if (pose.startsWith("walk")) return facingLeft ? "running-left" : "running-right";
      return POSE_ACTIONS[pose] ?? "idle";
    }
    return (_ctx, _cache) => {
      return _openBlock(), _createBlock(AgentPet, _mergeProps(props, {
        "character-name": appearance.value.name,
        "aspect-ratio": appearance.value.aspectRatio
      }), {
        default: _withCtx(({ pose, facingLeft, motionActive }) => [
          _createVNode(AgentPetSprite, _mergeProps(props, {
            action: actionForPose(pose, facingLeft),
            "motion-active": motionActive,
            "strict-preview": !!props.previewRoot,
            onLoadState: _cache[0] || (_cache[0] = ($event) => emit("load-state", $event)),
            onAppearance: _cache[1] || (_cache[1] = ($event) => appearance.value = $event)
          }), null, 16, ["action", "motion-active", "strict-preview"])
        ]),
        _: 1
      }, 16, ["character-name", "aspect-ratio"]);
    };
  }
});

export { _sfc_main as _ };
