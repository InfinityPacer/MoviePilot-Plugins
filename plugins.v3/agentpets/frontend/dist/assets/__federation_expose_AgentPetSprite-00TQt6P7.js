import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { B as BUILTIN_PACK_ID, c as BUILTIN_PACK, d as builtinAsset, r as resolveAction, p as parseCalibration, e as calibrationLayout, f as framePosition, P as PACK_UPDATED_EVENT, v as validatePack, w as withCodexStageActions } from './mappings-wSixMRjX.js';
import { w as withLoadTimeout, l as loadImage } from './loading-BHLkYAXO.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {normalizeStyle:_normalizeStyle,createElementVNode:_createElementVNode,normalizeClass:_normalizeClass,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode} = await importShared('vue');

const _hoisted_1 = ["data-pack", "data-action", "data-frame"];
const {computed,onBeforeUnmount,onMounted,ref,watch} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "AgentPetSprite",
  props: {
    agent: { default: null },
    pet: { default: null },
    api: { default: null },
    pluginId: { default: "" },
    sourcePluginId: { default: "" },
    action: { default: null },
    intent: { default: "idle" },
    thinking: { type: Boolean, default: false },
    motionActive: { type: Boolean, default: true },
    strictPreview: { type: Boolean },
    calibrationOverride: {},
    showCalibration: { type: Boolean },
    mappingsOverride: {},
    mappingKey: {},
    nativeAction: {},
    replay: {}
  },
  emits: ["appearance", "load-state", "pack-ready"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const packKey = props.pet?.key || BUILTIN_PACK_ID;
    const pack = ref(BUILTIN_PACK);
    const sheetSrc = ref(builtinAsset("sheet.webp"));
    const ready = ref(packKey === BUILTIN_PACK_ID);
    const cellRatio = ref(1);
    const frameIndex = ref(0);
    let timer = 0;
    let disposed = false;
    let loadVersion = 0;
    let loadController = null;
    let unsubscribe;
    const resolved = computed(
      () => resolveAction(pack.value, props.action, props.intent, props.thinking, {
        mappings: props.mappingsOverride,
        mappingKey: props.mappingKey,
        nativeAction: props.nativeAction
      })
    );
    const frame = computed(() => {
      const frames = resolved.value.action.frames;
      return frames[Math.min(frameIndex.value, frames.length - 1)] ?? "idle";
    });
    const calibration = computed(() => parseCalibration(props.calibrationOverride ?? pack.value.calibration));
    const layout = computed(() => calibrationLayout(calibration.value, cellRatio.value));
    const frameStyle = computed(() => {
      const { cols, rows } = pack.value.grid;
      const position = framePosition(pack.value, frame.value);
      return {
        ...layout.value.frame,
        backgroundImage: `url(${JSON.stringify(sheetSrc.value)})`,
        backgroundSize: `${cols * 100}% ${rows * 100}%`,
        backgroundPosition: `${position.x}% ${position.y}%`
      };
    });
    function stop() {
      if (timer) window.clearTimeout(timer);
      timer = 0;
    }
    function play() {
      stop();
      frameIndex.value = 0;
      if (!props.motionActive || !ready.value || disposed) return;
      const { frames, frame_ms: frameMs, loop } = resolved.value.action;
      if (frames.length < 2) return;
      const advance = () => {
        const next = frameIndex.value + 1;
        if (next >= frames.length && !loop) {
          timer = 0;
          return;
        }
        frameIndex.value = next % frames.length;
        timer = window.setTimeout(advance, frameMs);
      };
      timer = window.setTimeout(advance, frameMs);
    }
    async function loadPack(key) {
      loadController?.abort();
      const controller = new AbortController();
      loadController = controller;
      const signal = controller.signal;
      const version = ++loadVersion;
      const current = () => !disposed && version === loadVersion && !signal.aborted;
      emit("load-state", "loading");
      try {
        let nextPack = BUILTIN_PACK;
        let nextSheet = builtinAsset("sheet.webp");
        if (key !== BUILTIN_PACK_ID) {
          if (!props.api?.get) throw new Error("pack API unavailable");
          const instanceId = props.pluginId || "AgentPets";
          const response = await withLoadTimeout(
            props.api.get(`plugin/${instanceId}/pack?key=${encodeURIComponent(key)}`),
            signal
          );
          const { pack: parsed } = validatePack(response?.data?.pack);
          if (!response?.success || !parsed || !response.data?.sheet_src)
            throw new Error(response?.message || "invalid pack");
          nextPack = props.pet?.mode === "stage" ? withCodexStageActions(parsed) : parsed;
          nextSheet = response.data.sheet_src;
        }
        const dimensions = await loadImage(nextSheet, signal);
        if (!current()) return;
        pack.value = nextPack;
        sheetSrc.value = nextSheet;
        cellRatio.value = dimensions.width / nextPack.grid.cols / (dimensions.height / nextPack.grid.rows);
        ready.value = true;
        emit("pack-ready", nextPack);
        emit("load-state", "ready");
      } catch {
        if (!current()) return;
        console.warn(`[AgentPets] pack ${key} unavailable`);
        ready.value = false;
        emit("load-state", "error");
        if (props.strictPreview || key === BUILTIN_PACK_ID) return;
        try {
          const src = builtinAsset("sheet.webp");
          const dimensions = await loadImage(src, signal);
          if (!current()) return;
          pack.value = BUILTIN_PACK;
          sheetSrc.value = src;
          cellRatio.value = dimensions.width / BUILTIN_PACK.grid.cols / (dimensions.height / BUILTIN_PACK.grid.rows);
          ready.value = true;
        } catch {
        }
      }
    }
    watch(
      () => [resolved.value.key, props.motionActive, ready.value, pack.value, props.replay],
      () => play()
    );
    watch(
      [ready, pack, cellRatio, calibration],
      () => {
        if (ready.value) emit("appearance", { name: pack.value.name, aspectRatio: layout.value.aspectRatio });
      },
      { immediate: true }
    );
    onMounted(async () => {
      if (!props.strictPreview)
        unsubscribe = props.agent?.on(PACK_UPDATED_EVENT, (event) => {
          if (event.source === props.pluginId && event.data.key === packKey) void loadPack(packKey);
        });
      play();
      await loadPack(packKey);
    });
    onBeforeUnmount(() => {
      disposed = true;
      loadVersion++;
      loadController?.abort();
      unsubscribe?.();
      stop();
    });
    return (_ctx, _cache) => {
      return _openBlock(), _createElementBlock("div", {
        class: "agent-pet-sprites",
        "aria-hidden": "true",
        "data-pack": ready.value ? pack.value.id : void 0,
        "data-action": resolved.value.key,
        "data-frame": frame.value
      }, [
        ready.value ? (_openBlock(), _createElementBlock("div", {
          key: 0,
          class: _normalizeClass(["agent-pet-sprites__viewport", { "agent-pet-sprites__viewport--guides": __props.showCalibration }]),
          style: _normalizeStyle({ "--agent-pet-sprites-ratio": String(layout.value.aspectRatio) })
        }, [
          _createElementVNode("div", {
            class: "agent-pet-sprites__frame",
            style: _normalizeStyle(frameStyle.value)
          }, null, 4)
        ], 6)) : _createCommentVNode("", true)
      ], 8, _hoisted_1);
    };
  }
});

const AgentPetSprite = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-007b4c85"]]);

export { AgentPetSprite as default };
