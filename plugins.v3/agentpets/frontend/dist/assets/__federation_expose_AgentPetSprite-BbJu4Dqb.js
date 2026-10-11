import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { B as BUILTIN_PACK_ID, a as BUILTIN_PACK, b as builtinAsset, r as resolveAction, f as framePosition, v as validatePack, w as withCodexStageActions } from './schema-Jsrk9aRO.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {normalizeStyle:_normalizeStyle,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode} = await importShared('vue');

const _hoisted_1 = ["data-pack", "data-action", "data-frame"];
const {computed,onBeforeUnmount,onMounted,ref,watch} = await importShared('vue');
const PACK_LOAD_TIMEOUT = 5e3;
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
    strictPreview: { type: Boolean }
  },
  emits: ["appearance", "load-state"],
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
    const resolved = computed(() => resolveAction(pack.value, props.action, props.intent, props.thinking));
    const frame = computed(() => {
      const frames = resolved.value.action.frames;
      return frames[Math.min(frameIndex.value, frames.length - 1)] ?? "idle";
    });
    const frameStyle = computed(() => {
      const { cols, rows } = pack.value.grid;
      const position = framePosition(pack.value, frame.value);
      return {
        "--agent-pet-sprites-ratio": String(cellRatio.value),
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
      if (!props.motionActive || disposed) return;
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
    function measure(src) {
      const image = new Image();
      image.onload = () => {
        if (disposed || sheetSrc.value !== src || !image.naturalWidth) return;
        const { cols, rows } = pack.value.grid;
        cellRatio.value = image.naturalWidth / cols / (image.naturalHeight / rows);
      };
      image.src = src;
    }
    function withTimeout(promise, timeout) {
      return new Promise((resolve, reject) => {
        const id = window.setTimeout(() => reject(new Error("pack load timeout")), timeout);
        promise.then(
          (value) => {
            window.clearTimeout(id);
            resolve(value);
          },
          (error) => {
            window.clearTimeout(id);
            reject(error);
          }
        );
      });
    }
    async function loadPack(key) {
      if (key === BUILTIN_PACK_ID) return;
      if (!props.api?.get) {
        ready.value = !props.strictPreview;
        emit("load-state", "error");
        return;
      }
      emit("load-state", "loading");
      let failed = false;
      const instanceId = props.pluginId || "AgentPets";
      try {
        const response = await withTimeout(
          props.api.get(`plugin/${instanceId}/pack?key=${encodeURIComponent(key)}`),
          PACK_LOAD_TIMEOUT
        );
        const { pack: parsed } = validatePack(response?.data?.pack);
        if (!response?.success || !parsed || !response.data?.sheet_src) throw new Error(response?.message || "invalid pack");
        if (disposed) return;
        pack.value = props.pet?.mode === "stage" ? withCodexStageActions(parsed) : parsed;
        cellRatio.value = parsed.codex_version ? 192 / 208 : 1;
        sheetSrc.value = response.data.sheet_src;
      } catch {
        failed = true;
        console.warn(`[AgentPets] pack ${key} unavailable`);
      }
      if (!disposed) {
        ready.value = !failed || !props.strictPreview;
        emit("load-state", failed ? "error" : "ready");
      }
    }
    watch(
      () => [resolved.value.key, props.motionActive, pack.value],
      () => play()
    );
    watch(
      [ready, pack, cellRatio],
      () => {
        if (ready.value) emit("appearance", { name: pack.value.name, aspectRatio: cellRatio.value });
      },
      { immediate: true }
    );
    watch(sheetSrc, (src) => measure(src));
    watch(ready, (value) => {
      if (value) measure(sheetSrc.value);
    });
    onMounted(async () => {
      if (ready.value) {
        measure(sheetSrc.value);
        emit("load-state", "ready");
      }
      play();
      await loadPack(packKey);
    });
    onBeforeUnmount(() => {
      disposed = true;
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
          class: "agent-pet-sprites__frame",
          style: _normalizeStyle(frameStyle.value)
        }, null, 4)) : _createCommentVNode("", true)
      ], 8, _hoisted_1);
    };
  }
});

const AgentPetSprite = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-b85f496e"]]);

export { AgentPetSprite as default };
