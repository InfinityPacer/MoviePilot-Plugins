import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { A as AGENT_HOST_KEY, H as HOST_UNSUPPORTED_MESSAGE } from './host-CDE6kQPw.js';
import { v as validatePack, B as BUILTIN_PACK_ID, b as builtinAsset } from './schema-7sDr2_vp.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';
import { a as SCALE_RANGE, b as SPEED_RANGE, D as DEFAULT_SETTINGS, n as normalizeSettings, S as SETTINGS_EVENT } from './settings-_v7SC99m.js';

const {defineComponent:_defineComponent$2} = await importShared('vue');

const {createElementVNode:_createElementVNode$2,resolveComponent:_resolveComponent$2,openBlock:_openBlock$2,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$2,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock$1,withCtx:_withCtx$2,createVNode:_createVNode$2,toDisplayString:_toDisplayString$2,createTextVNode:_createTextVNode$2,createSlots:_createSlots,unref:_unref$2} = await importShared('vue');

const _hoisted_1$1 = { class: "agent-pet-sprites-config" };
const _hoisted_2$1 = { class: "d-flex align-center mt-3" };
const _hoisted_3$1 = { class: "text-caption text-medium-emphasis" };
const {computed,inject: inject$1,onMounted,ref: ref$1} = await importShared('vue');
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const _sfc_main$2 = /* @__PURE__ */ _defineComponent$2({
  __name: "PackManager",
  props: {
    api: { default: null },
    pluginId: { default: "" }
  },
  setup(__props) {
    const props = __props;
    const IMAGE_TYPES = ["image/png", "image/webp", "image/gif", "image/jpeg"];
    const EXAMPLE = JSON.stringify(
      {
        id: "my-pet",
        name: "我的形象",
        sheet: "https://example.com/sheet.png",
        grid: { cols: 4, rows: 2 },
        frames: { idle: 0, blink: 1, talk: 2, think: 3 },
        actions: {
          idle: { frames: ["idle", "idle", "blink"], frame_ms: 600, loop: true },
          thinking: { frames: ["think"], loop: true },
          speaking: ["talk", "idle"]
        },
        random_actions: ["wave"]
      },
      null,
      2
    );
    const toast = inject$1("moviepilot:toast", null);
    const confirm = inject$1("moviepilot:confirm", null);
    const instanceId = computed(() => props.pluginId || "AgentPets");
    const packs = ref$1([]);
    const loading = ref$1(false);
    const submitting = ref$1(false);
    const packText = ref$1("");
    const imageMode = ref$1("upload");
    const imageFile = ref$1(null);
    const fileModel = ref$1([]);
    const imageError = ref$1("");
    const serverError = ref$1("");
    const validation = computed(() => packText.value.trim() ? validatePack(packText.value) : null);
    const clientErrors = computed(() => {
      const errors = [...validation.value?.errors ?? []];
      if (imageMode.value === "url" && validation.value?.pack && !/^https?:\/\/\S+$/.test(validation.value.pack.sheet)) {
        errors.push("填写 URL 方式时，JSON 的 sheet 必须是 http(s) 图片地址");
      }
      return errors;
    });
    const canSubmit = computed(
      () => !!validation.value?.pack && !clientErrors.value.length && !submitting.value && (imageMode.value === "url" || !!imageFile.value && !imageError.value)
    );
    function previewSrc(pack) {
      if (pack.builtin) return builtinAsset("preview.png");
      return pack.preview;
    }
    function notify(kind, message) {
      toast?.[kind]?.(message);
    }
    async function refresh() {
      if (!props.api?.get) return;
      loading.value = true;
      try {
        const response = await props.api.get(`plugin/${instanceId.value}/packs`);
        if (response?.success && Array.isArray(response.data)) packs.value = response.data;
      } catch {
        console.warn("[AgentPets] packs unavailable");
      } finally {
        loading.value = false;
      }
    }
    function onImage(value) {
      const file = Array.isArray(value) ? value[0] ?? null : value ?? null;
      imageFile.value = file;
      imageError.value = "";
      if (!file) return;
      if (!IMAGE_TYPES.includes(file.type)) imageError.value = "只支持 PNG、WebP、GIF 或 JPEG";
      else if (file.size > MAX_IMAGE_BYTES) imageError.value = "精灵图不能超过 4MB";
    }
    function readDataUrl(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
    }
    async function addPack() {
      if (!canSubmit.value || !props.api?.post) return;
      submitting.value = true;
      serverError.value = "";
      try {
        const image = imageMode.value === "upload" && imageFile.value ? await readDataUrl(imageFile.value) : null;
        const response = await props.api.post(`plugin/${instanceId.value}/packs`, {
          pack: packText.value,
          image
        });
        if (!response?.success) {
          serverError.value = response?.message || "添加失败";
          return;
        }
        notify("success", `已添加素材包 ${response.data?.name ?? ""}`);
        packText.value = "";
        imageFile.value = null;
        fileModel.value = [];
        await refresh();
      } catch {
        serverError.value = "添加失败，请检查网络或稍后重试";
      } finally {
        submitting.value = false;
      }
    }
    async function removePack(pack) {
      if (!props.api?.post) return;
      const accepted = confirm ? await confirm({
        type: "warn",
        title: "删除素材包",
        content: `删除「${pack.name}」后，选择它的用户会回到内置机器人。`
      }) : window.confirm(`删除素材包「${pack.name}」？`);
      if (!accepted) return;
      const response = await props.api.post(`plugin/${instanceId.value}/packs/delete`, { id: pack.id });
      if (response?.success) {
        notify("success", `已删除素材包 ${pack.name}`);
        await refresh();
      } else notify("error", response?.message || "删除失败");
    }
    onMounted(refresh);
    return (_ctx, _cache) => {
      const _component_v_progress_linear = _resolveComponent$2("v-progress-linear");
      const _component_v_img = _resolveComponent$2("v-img");
      const _component_v_icon = _resolveComponent$2("v-icon");
      const _component_v_avatar = _resolveComponent$2("v-avatar");
      const _component_v_list_item_title = _resolveComponent$2("v-list-item-title");
      const _component_v_list_item_subtitle = _resolveComponent$2("v-list-item-subtitle");
      const _component_v_btn = _resolveComponent$2("v-btn");
      const _component_v_list_item = _resolveComponent$2("v-list-item");
      const _component_v_list = _resolveComponent$2("v-list");
      const _component_v_textarea = _resolveComponent$2("v-textarea");
      const _component_v_btn_toggle = _resolveComponent$2("v-btn-toggle");
      const _component_v_file_input = _resolveComponent$2("v-file-input");
      const _component_v_alert = _resolveComponent$2("v-alert");
      const _component_v_spacer = _resolveComponent$2("v-spacer");
      return _openBlock$2(), _createElementBlock$1("div", _hoisted_1$1, [
        _cache[6] || (_cache[6] = _createElementVNode$2("div", { class: "text-subtitle-2 mb-2" }, "已有素材包", -1)),
        loading.value ? (_openBlock$2(), _createBlock$1(_component_v_progress_linear, {
          key: 0,
          indeterminate: "",
          class: "mb-2"
        })) : _createCommentVNode$2("", true),
        _createVNode$2(_component_v_list, {
          density: "comfortable",
          class: "mb-6",
          border: "",
          rounded: ""
        }, {
          default: _withCtx$2(() => [
            (_openBlock$2(true), _createElementBlock$1(_Fragment, null, _renderList(packs.value, (pack) => {
              return _openBlock$2(), _createBlock$1(_component_v_list_item, {
                key: pack.id
              }, _createSlots({
                prepend: _withCtx$2(() => [
                  _createVNode$2(_component_v_avatar, {
                    rounded: "lg",
                    size: "48",
                    class: "agent-pet-sprites-config__thumb"
                  }, {
                    default: _withCtx$2(() => [
                      previewSrc(pack) ? (_openBlock$2(), _createBlock$1(_component_v_img, {
                        key: 0,
                        src: previewSrc(pack),
                        alt: pack.name
                      }, null, 8, ["src", "alt"])) : (_openBlock$2(), _createBlock$1(_component_v_icon, {
                        key: 1,
                        icon: "mdi-image-outline"
                      }))
                    ]),
                    _: 2
                  }, 1024)
                ]),
                default: _withCtx$2(() => [
                  _createVNode$2(_component_v_list_item_title, null, {
                    default: _withCtx$2(() => [
                      _createTextVNode$2(_toDisplayString$2(pack.name), 1)
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode$2(_component_v_list_item_subtitle, null, {
                    default: _withCtx$2(() => [
                      _createTextVNode$2(_toDisplayString$2(pack.id) + " · " + _toDisplayString$2(pack.builtin ? "内置" : pack.source === "upload" ? "已上传" : "远程图片") + " · " + _toDisplayString$2(pack.frame_count) + " 帧 · " + _toDisplayString$2(pack.action_count) + " 个动作 ", 1)
                    ]),
                    _: 2
                  }, 1024)
                ]),
                _: 2
              }, [
                !pack.builtin ? {
                  name: "append",
                  fn: _withCtx$2(() => [
                    _createVNode$2(_component_v_btn, {
                      icon: "mdi-delete-outline",
                      variant: "text",
                      "aria-label": `删除 ${pack.name}`,
                      onClick: ($event) => removePack(pack)
                    }, null, 8, ["aria-label", "onClick"])
                  ]),
                  key: "0"
                } : void 0
              ]), 1024);
            }), 128)),
            !packs.value.length && !loading.value ? (_openBlock$2(), _createBlock$1(_component_v_list_item, { key: 0 }, {
              default: _withCtx$2(() => [
                _createVNode$2(_component_v_list_item_title, { class: "text-medium-emphasis" }, {
                  default: _withCtx$2(() => [
                    _createTextVNode$2(_toDisplayString$2(props.api ? "暂无素材包" : "当前环境无法读取素材包"), 1)
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })) : _createCommentVNode$2("", true)
          ]),
          _: 1
        }),
        _cache[7] || (_cache[7] = _createElementVNode$2("div", { class: "text-subtitle-2 mb-2" }, "添加素材包", -1)),
        _createVNode$2(_component_v_textarea, {
          modelValue: packText.value,
          "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => packText.value = $event),
          label: "素材包 JSON",
          placeholder: _unref$2(EXAMPLE),
          rows: "8",
          "auto-grow": "",
          variant: "outlined",
          class: "agent-pet-sprites-config__json",
          "persistent-placeholder": "",
          "hide-details": "auto"
        }, null, 8, ["modelValue", "placeholder"]),
        _createVNode$2(_component_v_btn_toggle, {
          modelValue: imageMode.value,
          "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => imageMode.value = $event),
          mandatory: "",
          density: "comfortable",
          variant: "outlined",
          class: "my-3",
          divided: ""
        }, {
          default: _withCtx$2(() => [
            _createVNode$2(_component_v_btn, { value: "upload" }, {
              default: _withCtx$2(() => [..._cache[3] || (_cache[3] = [
                _createTextVNode$2("上传精灵图", -1)
              ])]),
              _: 1
            }),
            _createVNode$2(_component_v_btn, { value: "url" }, {
              default: _withCtx$2(() => [..._cache[4] || (_cache[4] = [
                _createTextVNode$2("使用 JSON 中的图片 URL", -1)
              ])]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"]),
        imageMode.value === "upload" ? (_openBlock$2(), _createBlock$1(_component_v_file_input, {
          key: 1,
          modelValue: fileModel.value,
          "onUpdate:modelValue": [
            _cache[2] || (_cache[2] = ($event) => fileModel.value = $event),
            onImage
          ],
          label: "精灵图（PNG、WebP、GIF、JPEG，不超过 4MB）",
          accept: "image/png,image/webp,image/gif,image/jpeg",
          variant: "outlined",
          "prepend-icon": "mdi-image-outline",
          "error-messages": imageError.value ? [imageError.value] : [],
          "hide-details": "auto"
        }, null, 8, ["modelValue", "error-messages"])) : _createCommentVNode$2("", true),
        clientErrors.value.length || serverError.value ? (_openBlock$2(), _createBlock$1(_component_v_alert, {
          key: 2,
          type: "error",
          variant: "tonal",
          density: "compact",
          class: "mt-3"
        }, {
          default: _withCtx$2(() => [
            (_openBlock$2(true), _createElementBlock$1(_Fragment, null, _renderList([...clientErrors.value, ...serverError.value ? [serverError.value] : []], (error) => {
              return _openBlock$2(), _createElementBlock$1("div", { key: error }, _toDisplayString$2(error), 1);
            }), 128))
          ]),
          _: 1
        })) : _createCommentVNode$2("", true),
        _createElementVNode$2("div", _hoisted_2$1, [
          _createElementVNode$2("span", _hoisted_3$1, " 格式说明见插件 README；ID " + _toDisplayString$2(_unref$2(BUILTIN_PACK_ID)) + " 和 ying 留给内置形象。 ", 1),
          _createVNode$2(_component_v_spacer),
          _createVNode$2(_component_v_btn, {
            color: "primary",
            variant: "tonal",
            loading: submitting.value,
            disabled: !canSubmit.value,
            onClick: addPack
          }, {
            default: _withCtx$2(() => [..._cache[5] || (_cache[5] = [
              _createTextVNode$2(" 校验并添加 ", -1)
            ])]),
            _: 1
          }, 8, ["loading", "disabled"])
        ])
      ]);
    };
  }
});

const PackManager = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-c522eb2b"]]);

const {defineComponent:_defineComponent$1} = await importShared('vue');

const {createElementVNode:_createElementVNode$1,unref:_unref$1,toDisplayString:_toDisplayString$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode$1,createTextVNode:_createTextVNode$1} = await importShared('vue');

const _hoisted_1 = { class: "agent-pets-stage-settings" };
const _hoisted_2 = { class: "agent-pets-stage-settings__value" };
const _hoisted_3 = { class: "agent-pets-stage-settings__value" };
const _hoisted_4 = { class: "d-flex align-center mt-3" };
const _hoisted_5 = {
  key: 0,
  class: "text-caption text-medium-emphasis"
};
const _sfc_main$1 = /* @__PURE__ */ _defineComponent$1({
  __name: "StageSettings",
  props: {
    modelValue: {},
    livePreview: { type: Boolean }
  },
  emits: ["update:modelValue"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const ROAM_OPTIONS = [
      { value: "surfaces", title: "站在页面元素上", hint: "落到卡片、对话框等元素的上边，元素移动或消失时跟着走或掉下来" },
      { value: "floor", title: "只在底边", hint: "始终站在屏幕底边" },
      { value: "free", title: "自由停放", hint: "没有重力，放在哪里停在哪里，空闲时在屏幕内慢慢游走" }
    ];
    function update(patch) {
      emit("update:modelValue", { ...props.modelValue, ...patch });
    }
    function reset() {
      emit("update:modelValue", { ...DEFAULT_SETTINGS });
    }
    return (_ctx, _cache) => {
      const _component_v_slider = _resolveComponent$1("v-slider");
      const _component_v_select = _resolveComponent$1("v-select");
      const _component_v_spacer = _resolveComponent$1("v-spacer");
      const _component_v_btn = _resolveComponent$1("v-btn");
      return _openBlock$1(), _createElementBlock("div", _hoisted_1, [
        _cache[4] || (_cache[4] = _createElementVNode$1("div", { class: "text-subtitle-2 mb-1" }, "角色大小", -1)),
        _createVNode$1(_component_v_slider, {
          "model-value": props.modelValue.scale,
          min: _unref$1(SCALE_RANGE)[0],
          max: _unref$1(SCALE_RANGE)[1],
          step: 0.05,
          color: "primary",
          "thumb-label": "",
          "hide-details": "",
          "aria-label": "角色大小",
          "onUpdate:modelValue": _cache[0] || (_cache[0] = (value) => update({ scale: Number(value) }))
        }, {
          append: _withCtx$1(() => [
            _createElementVNode$1("span", _hoisted_2, _toDisplayString$1(props.modelValue.scale.toFixed(2)) + "×", 1)
          ]),
          _: 1
        }, 8, ["model-value", "min", "max"]),
        _cache[5] || (_cache[5] = _createElementVNode$1("div", { class: "text-subtitle-2 mt-4 mb-1" }, "移动速度", -1)),
        _createVNode$1(_component_v_slider, {
          "model-value": props.modelValue.speed,
          min: _unref$1(SPEED_RANGE)[0],
          max: _unref$1(SPEED_RANGE)[1],
          step: 0.05,
          color: "primary",
          "thumb-label": "",
          "hide-details": "",
          "aria-label": "移动速度",
          "onUpdate:modelValue": _cache[1] || (_cache[1] = (value) => update({ speed: Number(value) }))
        }, {
          append: _withCtx$1(() => [
            _createElementVNode$1("span", _hoisted_3, _toDisplayString$1(props.modelValue.speed.toFixed(2)) + "×", 1)
          ]),
          _: 1
        }, 8, ["model-value", "min", "max"]),
        _createVNode$1(_component_v_select, {
          "model-value": props.modelValue.roam,
          items: ROAM_OPTIONS,
          "item-title": "title",
          "item-value": "value",
          label: "活动范围",
          variant: "outlined",
          density: "comfortable",
          class: "mt-5",
          hint: ROAM_OPTIONS.find((option) => option.value === props.modelValue.roam)?.hint,
          "persistent-hint": "",
          "onUpdate:modelValue": _cache[2] || (_cache[2] = (value) => update({ roam: value }))
        }, null, 8, ["model-value", "hint"]),
        _createElementVNode$1("div", _hoisted_4, [
          props.livePreview ? (_openBlock$1(), _createElementBlock("span", _hoisted_5, " 调整时页面上正在运行的小映会实时变化，保存后对所有用户生效。 ")) : _createCommentVNode$1("", true),
          _createVNode$1(_component_v_spacer),
          _createVNode$1(_component_v_btn, {
            variant: "text",
            size: "small",
            onClick: reset
          }, {
            default: _withCtx$1(() => [..._cache[3] || (_cache[3] = [
              _createTextVNode$1("恢复默认", -1)
            ])]),
            _: 1
          })
        ])
      ]);
    };
  }
});

const StageSettings = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-a7e3100d"]]);

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createVNode:_createVNode,createElementVNode:_createElementVNode} = await importShared('vue');

const {inject,onBeforeUnmount,ref,watch} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Config",
  props: {
    initialConfig: { default: null },
    api: { default: null },
    pluginId: { default: "" }
  },
  emits: ["save", "close"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const agent = inject(AGENT_HOST_KEY, null);
    const saved = normalizeSettings(props.initialConfig);
    const enabled = ref(Boolean(props.initialConfig?.enabled));
    const stage = ref({ ...saved });
    let committed = false;
    watch(stage, (value) => agent?.emit?.(SETTINGS_EVENT, { ...value }), { deep: true });
    function save() {
      committed = true;
      emit("save", { enabled: enabled.value, ...normalizeSettings(stage.value) });
    }
    onBeforeUnmount(() => {
      if (!committed) agent?.emit?.(SETTINGS_EVENT, { ...saved });
    });
    return (_ctx, _cache) => {
      const _component_v_alert = _resolveComponent("v-alert");
      const _component_v_switch = _resolveComponent("v-switch");
      const _component_v_divider = _resolveComponent("v-divider");
      const _component_v_card_text = _resolveComponent("v-card-text");
      const _component_v_spacer = _resolveComponent("v-spacer");
      const _component_v_btn = _resolveComponent("v-btn");
      const _component_v_card_actions = _resolveComponent("v-card-actions");
      const _component_v_card = _resolveComponent("v-card");
      return _openBlock(), _createBlock(_component_v_card, {
        flat: "",
        class: "agent-pets-config"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              !_unref(agent) ? (_openBlock(), _createBlock(_component_v_alert, {
                key: 0,
                type: "warning",
                variant: "tonal",
                density: "compact",
                class: "mb-4"
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(_unref(HOST_UNSUPPORTED_MESSAGE)), 1)
                ]),
                _: 1
              })) : _createCommentVNode("", true),
              _createVNode(_component_v_switch, {
                modelValue: enabled.value,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => enabled.value = $event),
                label: "启用插件",
                color: "primary",
                "hide-details": "",
                class: "mb-2"
              }, null, 8, ["modelValue"]),
              _cache[3] || (_cache[3] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mb-6" }, " 启用后，小映和每个素材包都会出现在个人设置的「助手形象」里，由用户自行选择。 ", -1)),
              _cache[4] || (_cache[4] = _createElementVNode("div", { class: "text-subtitle-1 mb-1" }, "小映（全屏角色）", -1)),
              _cache[5] || (_cache[5] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mb-4" }, "在整个页面上活动，可拖拽、站在页面元素上、散步和探头。", -1)),
              _createVNode(StageSettings, {
                modelValue: stage.value,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => stage.value = $event),
                "live-preview": !!_unref(agent)
              }, null, 8, ["modelValue", "live-preview"]),
              _createVNode(_component_v_divider, { class: "my-6" }),
              _cache[6] || (_cache[6] = _createElementVNode("div", { class: "text-subtitle-1 mb-1" }, "素材包（入口外观）", -1)),
              _cache[7] || (_cache[7] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mb-4" }, " 替换右下角助手入口的画面，拖拽和气泡仍由主程序负责。每个素材包都是一个可选形象。 ", -1)),
              _createVNode(PackManager, {
                api: props.api,
                "plugin-id": props.pluginId
              }, null, 8, ["api", "plugin-id"])
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_actions, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[2] || (_cache[2] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [..._cache[8] || (_cache[8] = [
                  _createTextVNode("关闭", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                color: "primary",
                variant: "flat",
                onClick: save
              }, {
                default: _withCtx(() => [..._cache[9] || (_cache[9] = [
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

export { _sfc_main as _ };
