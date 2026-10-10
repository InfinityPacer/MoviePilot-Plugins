import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { v as validatePack, B as BUILTIN_PACK_ID, b as builtinAsset, _ as _export_sfc } from './_plugin-vue_export-helper-DWQfjxwI.js';

const {defineComponent:_defineComponent} = await importShared('vue');

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock,withCtx:_withCtx,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,createSlots:_createSlots,unref:_unref} = await importShared('vue');

const _hoisted_1 = { class: "d-flex align-center mt-3" };
const _hoisted_2 = { class: "text-caption text-medium-emphasis" };
const {computed,inject,onMounted,ref} = await importShared('vue');
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
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
    const toast = inject("moviepilot:toast", null);
    const confirm = inject("moviepilot:confirm", null);
    const instanceId = computed(() => props.pluginId || "AgentPetSprites");
    const enabled = ref(Boolean(props.initialConfig?.enabled));
    const packs = ref([]);
    const loading = ref(false);
    const submitting = ref(false);
    const packText = ref("");
    const imageMode = ref("upload");
    const imageFile = ref(null);
    const fileModel = ref([]);
    const imageError = ref("");
    const serverError = ref("");
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
        console.warn("[AgentPetSprites] packs unavailable");
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
    function save() {
      emit("save", { enabled: enabled.value });
    }
    onMounted(refresh);
    return (_ctx, _cache) => {
      const _component_v_switch = _resolveComponent("v-switch");
      const _component_v_progress_linear = _resolveComponent("v-progress-linear");
      const _component_v_img = _resolveComponent("v-img");
      const _component_v_icon = _resolveComponent("v-icon");
      const _component_v_avatar = _resolveComponent("v-avatar");
      const _component_v_list_item_title = _resolveComponent("v-list-item-title");
      const _component_v_list_item_subtitle = _resolveComponent("v-list-item-subtitle");
      const _component_v_btn = _resolveComponent("v-btn");
      const _component_v_list_item = _resolveComponent("v-list-item");
      const _component_v_list = _resolveComponent("v-list");
      const _component_v_textarea = _resolveComponent("v-textarea");
      const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
      const _component_v_file_input = _resolveComponent("v-file-input");
      const _component_v_alert = _resolveComponent("v-alert");
      const _component_v_spacer = _resolveComponent("v-spacer");
      const _component_v_card_text = _resolveComponent("v-card-text");
      const _component_v_card_actions = _resolveComponent("v-card-actions");
      const _component_v_card = _resolveComponent("v-card");
      return _openBlock(), _createBlock(_component_v_card, {
        flat: "",
        class: "agent-pet-sprites-config"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_switch, {
                modelValue: enabled.value,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => enabled.value = $event),
                label: "启用插件",
                color: "primary",
                "hide-details": "",
                class: "mb-4"
              }, null, 8, ["modelValue"]),
              _cache[8] || (_cache[8] = _createElementVNode("div", { class: "text-subtitle-1 mb-2" }, "素材包", -1)),
              loading.value ? (_openBlock(), _createBlock(_component_v_progress_linear, {
                key: 0,
                indeterminate: "",
                class: "mb-2"
              })) : _createCommentVNode("", true),
              _createVNode(_component_v_list, {
                density: "comfortable",
                class: "mb-6",
                border: "",
                rounded: ""
              }, {
                default: _withCtx(() => [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(packs.value, (pack) => {
                    return _openBlock(), _createBlock(_component_v_list_item, {
                      key: pack.id
                    }, _createSlots({
                      prepend: _withCtx(() => [
                        _createVNode(_component_v_avatar, {
                          rounded: "lg",
                          size: "48",
                          class: "agent-pet-sprites-config__thumb"
                        }, {
                          default: _withCtx(() => [
                            previewSrc(pack) ? (_openBlock(), _createBlock(_component_v_img, {
                              key: 0,
                              src: previewSrc(pack),
                              alt: pack.name
                            }, null, 8, ["src", "alt"])) : (_openBlock(), _createBlock(_component_v_icon, {
                              key: 1,
                              icon: "mdi-image-outline"
                            }))
                          ]),
                          _: 2
                        }, 1024)
                      ]),
                      default: _withCtx(() => [
                        _createVNode(_component_v_list_item_title, null, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(pack.name), 1)
                          ]),
                          _: 2
                        }, 1024),
                        _createVNode(_component_v_list_item_subtitle, null, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(pack.id) + " · " + _toDisplayString(pack.builtin ? "内置" : pack.source === "upload" ? "已上传" : "远程图片") + " · " + _toDisplayString(pack.frame_count) + " 帧 · " + _toDisplayString(pack.action_count) + " 个动作 ", 1)
                          ]),
                          _: 2
                        }, 1024)
                      ]),
                      _: 2
                    }, [
                      !pack.builtin ? {
                        name: "append",
                        fn: _withCtx(() => [
                          _createVNode(_component_v_btn, {
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
                  !packs.value.length && !loading.value ? (_openBlock(), _createBlock(_component_v_list_item, { key: 0 }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_list_item_title, { class: "text-medium-emphasis" }, {
                        default: _withCtx(() => [
                          _createTextVNode(_toDisplayString(props.api ? "暂无素材包" : "当前环境无法读取素材包"), 1)
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })) : _createCommentVNode("", true)
                ]),
                _: 1
              }),
              _cache[9] || (_cache[9] = _createElementVNode("div", { class: "text-subtitle-1 mb-2" }, "添加素材包", -1)),
              _createVNode(_component_v_textarea, {
                modelValue: packText.value,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => packText.value = $event),
                label: "素材包 JSON",
                placeholder: _unref(EXAMPLE),
                rows: "8",
                "auto-grow": "",
                variant: "outlined",
                class: "agent-pet-sprites-config__json",
                "persistent-placeholder": "",
                "hide-details": "auto"
              }, null, 8, ["modelValue", "placeholder"]),
              _createVNode(_component_v_btn_toggle, {
                modelValue: imageMode.value,
                "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => imageMode.value = $event),
                mandatory: "",
                density: "comfortable",
                variant: "outlined",
                class: "my-3",
                divided: ""
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_btn, { value: "upload" }, {
                    default: _withCtx(() => [..._cache[5] || (_cache[5] = [
                      _createTextVNode("上传精灵图", -1)
                    ])]),
                    _: 1
                  }),
                  _createVNode(_component_v_btn, { value: "url" }, {
                    default: _withCtx(() => [..._cache[6] || (_cache[6] = [
                      _createTextVNode("使用 JSON 中的图片 URL", -1)
                    ])]),
                    _: 1
                  })
                ]),
                _: 1
              }, 8, ["modelValue"]),
              imageMode.value === "upload" ? (_openBlock(), _createBlock(_component_v_file_input, {
                key: 1,
                modelValue: fileModel.value,
                "onUpdate:modelValue": [
                  _cache[3] || (_cache[3] = ($event) => fileModel.value = $event),
                  onImage
                ],
                label: "精灵图（PNG、WebP、GIF、JPEG，不超过 4MB）",
                accept: "image/png,image/webp,image/gif,image/jpeg",
                variant: "outlined",
                "prepend-icon": "mdi-image-outline",
                "error-messages": imageError.value ? [imageError.value] : [],
                "hide-details": "auto"
              }, null, 8, ["modelValue", "error-messages"])) : _createCommentVNode("", true),
              clientErrors.value.length || serverError.value ? (_openBlock(), _createBlock(_component_v_alert, {
                key: 2,
                type: "error",
                variant: "tonal",
                density: "compact",
                class: "mt-3"
              }, {
                default: _withCtx(() => [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList([...clientErrors.value, ...serverError.value ? [serverError.value] : []], (error) => {
                    return _openBlock(), _createElementBlock("div", { key: error }, _toDisplayString(error), 1);
                  }), 128))
                ]),
                _: 1
              })) : _createCommentVNode("", true),
              _createElementVNode("div", _hoisted_1, [
                _createElementVNode("span", _hoisted_2, " 格式说明见插件 README；内置素材包 ID " + _toDisplayString(_unref(BUILTIN_PACK_ID)) + " 不可占用。 ", 1),
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  color: "primary",
                  variant: "tonal",
                  loading: submitting.value,
                  disabled: !canSubmit.value,
                  onClick: addPack
                }, {
                  default: _withCtx(() => [..._cache[7] || (_cache[7] = [
                    _createTextVNode(" 校验并添加 ", -1)
                  ])]),
                  _: 1
                }, 8, ["loading", "disabled"])
              ])
            ]),
            _: 1
          }),
          _createVNode(_component_v_card_actions, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_btn, {
                variant: "text",
                onClick: _cache[4] || (_cache[4] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [..._cache[10] || (_cache[10] = [
                  _createTextVNode("关闭", -1)
                ])]),
                _: 1
              }),
              _createVNode(_component_v_btn, {
                color: "primary",
                variant: "flat",
                onClick: save
              }, {
                default: _withCtx(() => [..._cache[11] || (_cache[11] = [
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

const Config = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-4ec33170"]]);

export { Config as default };
