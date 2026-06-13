import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const {defineComponent:_defineComponent$b} = await importShared('vue');

const {renderList:_renderList$2,Fragment:_Fragment$7,openBlock:_openBlock$b,createElementBlock:_createElementBlock$8,resolveComponent:_resolveComponent$4,createBlock:_createBlock$5,withCtx:_withCtx$7} = await importShared('vue');

const _sfc_main$b = /* @__PURE__ */ _defineComponent$b({
  __name: "DomainNav",
  props: {
    items: {},
    modelValue: {}
  },
  emits: ["update:modelValue"],
  setup(__props, { emit: __emit }) {
    const emit = __emit;
    return (_ctx, _cache) => {
      const _component_VListItem = _resolveComponent$4("VListItem");
      const _component_VList = _resolveComponent$4("VList");
      return _openBlock$b(), _createBlock$5(_component_VList, {
        class: "domain-nav",
        density: "comfortable",
        nav: ""
      }, {
        default: _withCtx$7(() => [
          (_openBlock$b(true), _createElementBlock$8(_Fragment$7, null, _renderList$2(_ctx.items, (item) => {
            return _openBlock$b(), _createBlock$5(_component_VListItem, {
              key: item.key,
              active: item.key === _ctx.modelValue,
              "prepend-icon": item.icon,
              title: item.title,
              color: "primary",
              onClick: ($event) => emit("update:modelValue", item.key)
            }, null, 8, ["active", "prepend-icon", "title", "onClick"]);
          }), 128))
        ]),
        _: 1
      });
    };
  }
});

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const DomainNav = /* @__PURE__ */ _export_sfc(_sfc_main$b, [["__scopeId", "data-v-16908c5b"]]);

const completionGuardModeOptions = [
  { title: "关闭", value: "off" },
  { title: "严格", value: "strict" },
  { title: "平衡", value: "balanced" },
  { title: "宽松", value: "loose" }
];
const bestVersionTypeOptions = [
  { title: "关闭", value: "no" },
  { title: "全部", value: "all" },
  { title: "电影", value: "movie" },
  { title: "剧集", value: "tv" },
  { title: "剧集（分集下载）", value: "tv_episode" }
];
const bestVersionClearHistoryTypeOptions = [
  { title: "关闭", value: "no" },
  { title: "全部", value: "all" },
  { title: "电影", value: "movie" },
  { title: "剧集", value: "tv" }
];
const noDownloadActionOptions = [
  { title: "暂停电影订阅", value: "pause_movie" },
  { title: "暂停剧集订阅", value: "pause_tv" },
  { title: "完成电影订阅", value: "complete_movie" },
  { title: "完成剧集订阅", value: "complete_tv" },
  { title: "删除电影订阅", value: "delete_movie" },
  { title: "删除剧集订阅", value: "delete_tv" }
];
const minuteIntervalOptions = [
  { title: "5分钟", value: 5 },
  { title: "10分钟", value: 10 },
  { title: "15分钟", value: 15 },
  { title: "30分钟", value: 30 },
  { title: "60分钟", value: 60 },
  { title: "120分钟", value: 120 }
];
const commonIntervalOptions = [
  { title: "30分钟", value: 30 },
  { title: "60分钟", value: 60 },
  { title: "120分钟", value: 120 },
  { title: "240分钟", value: 240 }
];
const metaIntervalOptions = [
  { title: "1小时", value: 1 },
  { title: "3小时", value: 3 },
  { title: "6小时", value: 6 },
  { title: "12小时", value: 12 },
  { title: "24小时", value: 24 }
];
const fields = {
  enabled: {
    key: "enabled",
    kind: "switch",
    label: "启用插件",
    hint: "开启后插件将处于激活状态"
  },
  notify: {
    key: "notify",
    kind: "switch",
    label: "发送通知",
    hint: "是否在特定事件发生时发送通知"
  },
  reset_task: {
    key: "reset_task",
    kind: "switch",
    label: "重置数据",
    hint: "将重置所有待定/暂停/监控等任务数据，执行后自动复位"
  },
  onlyonce: {
    key: "onlyonce",
    kind: "switch",
    label: "立即运行一次",
    hint: "保存后立即运行一次全量巡检，执行后自动复位"
  },
  auto_check_interval_minutes: {
    key: "auto_check_interval_minutes",
    kind: "select",
    label: "通用巡检周期（分钟）",
    hint: "待定释放、无下载处理和删除记录清理的周期",
    options: commonIntervalOptions
  },
  download_check_interval_minutes: {
    key: "download_check_interval_minutes",
    kind: "select",
    label: "下载检查周期（分钟）",
    hint: "下载检查的周期，定时检查下载任务状态",
    options: minuteIntervalOptions
  },
  meta_check_interval_hours: {
    key: "meta_check_interval_hours",
    kind: "select",
    label: "元数据检查周期（小时）",
    hint: "元数据检查的周期，定时复核订阅元数据状态",
    options: metaIntervalOptions
  },
  best_version_cron: {
    key: "best_version_cron",
    kind: "cron",
    label: "洗版检查周期",
    hint: "洗版检查的周期，如 0 15 * * *"
  },
  download_monitor_enabled: {
    key: "download_monitor_enabled",
    kind: "switch",
    label: "下载超时自动删除",
    hint: "订阅下载超时将自动删除种子"
  },
  manual_delete_listen: {
    key: "manual_delete_listen",
    kind: "switch",
    label: "监听手动删除种子",
    hint: "监听用户手动删除的种子记录"
  },
  tracker_response_listen: {
    key: "tracker_response_listen",
    kind: "switch",
    label: "监听Tracker响应关键字",
    hint: "命中Tracker响应关键字时将自动删除种子"
  },
  open_tracker_dialog: {
    key: "open_tracker_dialog",
    kind: "switch",
    label: "打开Tracker配置窗口",
    hint: "自定义Tracker配置以实现更精准的种子匹配"
  },
  auto_search_when_delete: {
    key: "auto_search_when_delete",
    kind: "switch",
    label: "删除后触发搜索补全",
    hint: "种子删除后将自动触发搜索补全"
  },
  skip_deletion: {
    key: "skip_deletion",
    kind: "switch",
    label: "跳过种子删除记录",
    hint: "跳过最近删除的种子，避免再次下载"
  },
  download_timeout_minutes: {
    key: "download_timeout_minutes",
    kind: "number",
    label: "下载超时时间（分钟）",
    hint: "作为下载进度观察窗口，窗口内进度增长低于阈值时视为超时"
  },
  download_progress_threshold: {
    key: "download_progress_threshold",
    kind: "number",
    label: "下载超时进度阈值",
    hint: "超时窗口内下载进度增长低于N%时才删除"
  },
  download_retry_limit: {
    key: "download_retry_limit",
    kind: "number",
    label: "下载连续超时重试次数",
    hint: "连续低进度超时N次后保留种子并通知"
  },
  delete_record_retention_hours: {
    key: "delete_record_retention_hours",
    kind: "number",
    label: "种子删除记录保留（小时）",
    hint: "定时清理N小时前的种子删除记录"
  },
  delete_exclude_tags: {
    key: "delete_exclude_tags",
    kind: "text",
    label: "排除标签",
    hint: "需要排除的标签，多个标签用逗号分隔"
  },
  default_tracker_response: {
    key: "default_tracker_response",
    kind: "textarea",
    label: "Tracker响应关键字",
    hint: "每一行一个关键字，忽略大小写，支持正则表达式匹配"
  },
  pending_enhanced_enabled: {
    key: "pending_enhanced_enabled",
    kind: "switch",
    label: "自动待定剧集订阅",
    hint: "自动标记订阅剧集为待定状态，避免提前完成订阅"
  },
  pending_download_enabled: {
    key: "pending_download_enabled",
    kind: "switch",
    label: "自动待定下载中订阅",
    hint: "存在进行中下载时自动标记待定，避免提前完成订阅"
  },
  auto_tv_pending_days: {
    key: "auto_tv_pending_days",
    kind: "number",
    label: "剧集待定天数",
    hint: "当前日期小于上映日期加N天，则视为待定，为0时不处理"
  },
  auto_tv_pending_episodes: {
    key: "auto_tv_pending_episodes",
    kind: "number",
    label: "剧集待定集数",
    hint: "剧集数小于等于设置的集数，则视为待定，为0时不处理"
  },
  pending_use_volatility: {
    key: "pending_use_volatility",
    kind: "switch",
    label: "待定参考变更速率",
    hint: "待定判定参考剧集更新的变更速率信号"
  },
  pause_enhanced_enabled: {
    key: "pause_enhanced_enabled",
    kind: "switch",
    label: "自动暂停订阅",
    hint: "自动标记订阅为暂停状态，避免无意义的请求"
  },
  auto_pause_users: {
    key: "auto_pause_users",
    kind: "text",
    label: "自动暂停新增订阅的用户（逗号分隔）",
    hint: "名单内用户新增订阅时将自动暂停，多个用户用逗号分隔，为空时不启用"
  },
  airing_pause_days: {
    key: "airing_pause_days",
    kind: "number",
    label: "即将播出暂停天数",
    hint: "已存在最新播出集，且下集距当前日期大于N天，则视为暂停，为0时不处理"
  },
  tv_air_pause_days: {
    key: "tv_air_pause_days",
    kind: "number",
    label: "剧集上映暂停天数",
    hint: "当前日期小于开播日期减N天，则视为暂停，为0时不处理"
  },
  movie_air_pause_days: {
    key: "movie_air_pause_days",
    kind: "number",
    label: "电影上映暂停天数",
    hint: "当前日期小于上映日期减N天，则视为暂停，为0时不处理"
  },
  tv_no_download_days: {
    key: "tv_no_download_days",
    kind: "number",
    label: "剧集无下载处理天数",
    hint: "剧集上映后N天内无新的订阅下载，则按策略处理，为0时不处理"
  },
  movie_no_download_days: {
    key: "movie_no_download_days",
    kind: "number",
    label: "电影无下载处理天数",
    hint: "电影上映后N天内无新的订阅下载，则按策略处理，为0时不处理"
  },
  no_download_actions: {
    key: "no_download_actions",
    kind: "multi-select",
    label: "无下载处理策略",
    hint: "选择无下载时的处理策略",
    options: noDownloadActionOptions
  },
  best_version_type: {
    key: "best_version_type",
    kind: "select",
    label: "洗版类型",
    hint: "选择需要自动洗版的类型，关闭时不自动创建和巡检洗版订阅",
    options: bestVersionTypeOptions
  },
  best_version_episode_to_full: {
    key: "best_version_episode_to_full",
    kind: "switch",
    label: "分集转全集",
    hint: "订阅目标集数满足时，从分集洗版切换为全集洗版"
  },
  best_version_backfill_enabled: {
    key: "best_version_backfill_enabled",
    kind: "switch",
    label: "回填已存在集",
    hint: "新建或转洗版时将媒体库已有集标为顶档并跳过"
  },
  backfill_best_version_now: {
    key: "backfill_best_version_now",
    kind: "switch",
    label: "立即扫描存量并回填",
    hint: "保存后对存量洗版订阅执行一次回填，执行后自动复位"
  },
  best_version_clear_history_type: {
    key: "best_version_clear_history_type",
    kind: "select",
    label: "清理整理记录范围",
    hint: "洗版下载时清理整理记录和文件的范围（破坏性）",
    options: bestVersionClearHistoryTypeOptions
  },
  best_version_remaining_days: {
    key: "best_version_remaining_days",
    kind: "number",
    label: "洗版时限（天）",
    hint: "达到指定天数后自动终止洗版，有下载则按最新时间计算，为0时不限"
  },
  completion_guard_mode: {
    key: "completion_guard_mode",
    kind: "select",
    label: "完结守卫模式",
    hint: "选择完成前复核强度，默认使用平衡策略",
    options: completionGuardModeOptions
  },
  volatility_enabled: {
    key: "volatility_enabled",
    kind: "switch",
    label: "变更速率信号",
    hint: "总集数近期变化时视为不稳定"
  },
  volatility_window_days: {
    key: "volatility_window_days",
    kind: "number",
    label: "变更速率窗口（天）",
    hint: "统计总集数变化的天数，越长越保守"
  },
  cadence_enabled: {
    key: "cadence_enabled",
    kind: "switch",
    label: "播出节奏信号",
    hint: "按已播间隔判断等待期，不会直接判定完结"
  },
  cadence_multiplier: {
    key: "cadence_multiplier",
    kind: "number",
    label: "节奏窗口系数",
    hint: "放大预计等待时间，数值越大等待越久"
  },
  cadence_min_window_days: {
    key: "cadence_min_window_days",
    kind: "number",
    label: "节奏窗口下限（天）",
    hint: "预计等待时间不得少于设置天数"
  },
  cadence_min_episodes: {
    key: "cadence_min_episodes",
    kind: "number",
    label: "节奏参与最少集数",
    hint: "已播集数达到设置值后才计算播出间隔"
  },
  season_cooldown_days: {
    key: "season_cooldown_days",
    kind: "number",
    label: "季冷却期（天）",
    hint: "最后一集播出后继续观察的天数"
  },
  verify_enabled: {
    key: "verify_enabled",
    kind: "switch",
    label: "自动纠错",
    hint: "完成后检查集数，增加时自动重建订阅"
  },
  verify_interval_hours: {
    key: "verify_interval_hours",
    kind: "number",
    label: "自动纠错间隔（小时）",
    hint: "完成后重新检查集数的间隔"
  },
  verify_retention_days: {
    key: "verify_retention_days",
    kind: "number",
    label: "快照保留（天）",
    hint: "完成快照按设置天数保留并自动清理，默认180天"
  },
  timeout_release_enabled: {
    key: "timeout_release_enabled",
    kind: "switch",
    label: "待定超时释放",
    hint: "完成守卫待定（P）超期后释放，信号不稳定时重新计时"
  },
  timeout_release_days: {
    key: "timeout_release_days",
    kind: "number",
    label: "待定超时释放（天）",
    hint: "完成守卫待定（P）允许保留的最长天数"
  },
  timeout_cadence_acceleration: {
    key: "timeout_cadence_acceleration",
    kind: "switch",
    label: "按节奏加速释放",
    hint: "等待期结束时将待定期限缩短一半"
  }
};
const topSwitchFields = [
  { ...fields.enabled, md: 3 },
  { ...fields.notify, md: 3 },
  { ...fields.reset_task, md: 3 },
  { ...fields.onlyonce, md: 3 }
];
const periodFields = [
  { ...fields.auto_check_interval_minutes, md: 3 },
  { ...fields.download_check_interval_minutes, md: 3 },
  { ...fields.meta_check_interval_hours, md: 3 },
  { ...fields.best_version_cron, md: 3 }
];
[
  {
    title: "种子删除",
    subtitle: "管理下载超时、Tracker 关键字和删除记录跳过策略。",
    rows: [
      [
        { ...fields.download_monitor_enabled, md: 4 },
        { ...fields.manual_delete_listen, md: 4 },
        { ...fields.tracker_response_listen, md: 4 }
      ],
      [
        { ...fields.open_tracker_dialog, md: 4 },
        { ...fields.auto_search_when_delete, md: 4 },
        { ...fields.skip_deletion, md: 4 }
      ],
      [
        { ...fields.download_timeout_minutes, md: 4 },
        { ...fields.download_progress_threshold, md: 4 },
        { ...fields.download_retry_limit, md: 4 }
      ],
      [
        { ...fields.delete_record_retention_hours, md: 4 },
        { ...fields.delete_exclude_tags, md: 4 },
        { ...fields.default_tracker_response, md: 4 }
      ]
    ]
  },
  {
    title: "订阅待定",
    subtitle: "控制剧集和下载中的订阅进入待定状态的条件。",
    rows: [
      [
        { ...fields.pending_download_enabled, md: 4 },
        { ...fields.pending_enhanced_enabled, md: 4 },
        { ...fields.pending_use_volatility, md: 4 }
      ],
      [
        { ...fields.auto_tv_pending_days, md: 6 },
        { ...fields.auto_tv_pending_episodes, md: 6 }
      ]
    ]
  },
  {
    title: "订阅暂停",
    subtitle: "控制自动暂停、播出前等待和无下载处理动作。",
    rows: [
      [
        { ...fields.pause_enhanced_enabled, md: 4 },
        { ...fields.auto_pause_users, md: 8 }
      ],
      [
        { ...fields.movie_air_pause_days, md: 4 },
        { ...fields.tv_air_pause_days, md: 4 },
        { ...fields.airing_pause_days, md: 4 }
      ],
      [
        { ...fields.movie_no_download_days, md: 4 },
        { ...fields.tv_no_download_days, md: 4 },
        { ...fields.no_download_actions, md: 4 }
      ]
    ]
  },
  {
    title: "订阅洗版",
    subtitle: "控制自动洗版范围、转全集、回填和整理记录清理范围。",
    rows: [
      [
        { ...fields.best_version_type, md: 4 },
        { ...fields.best_version_clear_history_type, md: 4 },
        { ...fields.best_version_remaining_days, md: 4 }
      ],
      [
        { ...fields.best_version_episode_to_full, md: 4 },
        { ...fields.best_version_backfill_enabled, md: 4 },
        { ...fields.backfill_best_version_now, md: 4 }
      ]
    ]
  },
  {
    title: "完结信号",
    subtitle: "控制完成前复核、播出节奏、完成后纠错和待定释放策略。",
    rows: [
      [
        { ...fields.completion_guard_mode, md: 4 },
        { ...fields.volatility_enabled, md: 4 },
        { ...fields.cadence_enabled, md: 4 }
      ],
      [
        { ...fields.verify_enabled, md: 4 },
        { ...fields.timeout_release_enabled, md: 4 },
        { ...fields.timeout_cadence_acceleration, md: 4 }
      ],
      [
        { ...fields.volatility_window_days, md: 4 },
        { ...fields.cadence_multiplier, md: 4 },
        { ...fields.cadence_min_window_days, md: 4 }
      ],
      [
        { ...fields.cadence_min_episodes, md: 4 },
        { ...fields.season_cooldown_days, md: 4 },
        { ...fields.verify_interval_hours, md: 4 }
      ],
      [
        { ...fields.verify_retention_days, md: 4 },
        { ...fields.timeout_release_days, md: 4 }
      ]
    ]
  }
];

const {defineComponent:_defineComponent$a} = await importShared('vue');

const {resolveComponent:_resolveComponent$3,openBlock:_openBlock$a,createBlock:_createBlock$4} = await importShared('vue');

const {computed} = await importShared('vue');

const _sfc_main$a = /* @__PURE__ */ _defineComponent$a({
  __name: "FieldControl",
  props: {
    field: {},
    model: {}
  },
  setup(__props) {
    const props = __props;
    const fieldValue = computed({
      get() {
        return props.model[props.field.key];
      },
      set(value) {
        props.model[props.field.key] = value;
      }
    });
    const numberValue = computed({
      get() {
        return props.model[props.field.key];
      },
      set(value) {
        if (value === "" || value === null || value === void 0) {
          props.model[props.field.key] = null;
          return;
        }
        const next = Number(value);
        props.model[props.field.key] = Number.isNaN(next) ? null : next;
      }
    });
    const multiValue = computed({
      get() {
        const value = props.model[props.field.key];
        return Array.isArray(value) ? value.map((item) => String(item)) : [];
      },
      set(value) {
        props.model[props.field.key] = value;
      }
    });
    return (_ctx, _cache) => {
      const _component_VSwitch = _resolveComponent$3("VSwitch");
      const _component_VSelect = _resolveComponent$3("VSelect");
      const _component_VTextarea = _resolveComponent$3("VTextarea");
      const _component_VTextField = _resolveComponent$3("VTextField");
      return _ctx.field.kind === "switch" ? (_openBlock$a(), _createBlock$4(_component_VSwitch, {
        key: 0,
        modelValue: fieldValue.value,
        "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => fieldValue.value = $event),
        class: "field-control",
        color: "primary",
        label: _ctx.field.label,
        hint: _ctx.field.hint,
        "persistent-hint": ""
      }, null, 8, ["modelValue", "label", "hint"])) : _ctx.field.kind === "multi-select" ? (_openBlock$a(), _createBlock$4(_component_VSelect, {
        key: 1,
        modelValue: multiValue.value,
        "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => multiValue.value = $event),
        class: "field-control",
        items: _ctx.field.options ?? [],
        label: _ctx.field.label,
        hint: _ctx.field.hint,
        "item-title": "title",
        "item-value": "value",
        multiple: "",
        chips: "",
        clearable: "",
        "persistent-hint": ""
      }, null, 8, ["modelValue", "items", "label", "hint"])) : _ctx.field.kind === "select" ? (_openBlock$a(), _createBlock$4(_component_VSelect, {
        key: 2,
        modelValue: fieldValue.value,
        "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => fieldValue.value = $event),
        class: "field-control",
        items: _ctx.field.options ?? [],
        label: _ctx.field.label,
        hint: _ctx.field.hint,
        "item-title": "title",
        "item-value": "value",
        clearable: "",
        "persistent-hint": ""
      }, null, 8, ["modelValue", "items", "label", "hint"])) : _ctx.field.kind === "textarea" ? (_openBlock$a(), _createBlock$4(_component_VTextarea, {
        key: 3,
        modelValue: fieldValue.value,
        "onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => fieldValue.value = $event),
        class: "field-control",
        label: _ctx.field.label,
        hint: _ctx.field.hint,
        "auto-grow": "",
        rows: "4",
        "persistent-hint": ""
      }, null, 8, ["modelValue", "label", "hint"])) : _ctx.field.kind === "number" ? (_openBlock$a(), _createBlock$4(_component_VTextField, {
        key: 4,
        modelValue: numberValue.value,
        "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => numberValue.value = $event),
        class: "field-control",
        type: "number",
        label: _ctx.field.label,
        hint: _ctx.field.hint,
        "persistent-hint": ""
      }, null, 8, ["modelValue", "label", "hint"])) : (_openBlock$a(), _createBlock$4(_component_VTextField, {
        key: 5,
        modelValue: fieldValue.value,
        "onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => fieldValue.value = $event),
        class: "field-control",
        type: "text",
        label: _ctx.field.label,
        hint: _ctx.field.hint,
        "persistent-hint": ""
      }, null, 8, ["modelValue", "label", "hint"]));
    };
  }
});

const FieldControl = /* @__PURE__ */ _export_sfc(_sfc_main$a, [["__scopeId", "data-v-5dc481a4"]]);

const {defineComponent:_defineComponent$9} = await importShared('vue');

const {resolveComponent:_resolveComponent$2,openBlock:_openBlock$9,createBlock:_createBlock$3} = await importShared('vue');

const _sfc_main$9 = /* @__PURE__ */ _defineComponent$9({
  __name: "RiskAlert",
  props: {
    type: { default: "warning" },
    text: {}
  },
  setup(__props) {
    return (_ctx, _cache) => {
      const _component_VAlert = _resolveComponent$2("VAlert");
      return _openBlock$9(), _createBlock$3(_component_VAlert, {
        class: "risk-alert",
        type: _ctx.type,
        text: _ctx.text,
        variant: "tonal",
        density: "comfortable"
      }, null, 8, ["type", "text"]);
    };
  }
});

const RiskAlert = /* @__PURE__ */ _export_sfc(_sfc_main$9, [["__scopeId", "data-v-3a69a1e4"]]);

const {defineComponent:_defineComponent$8} = await importShared('vue');

const {unref:_unref$6,renderList:_renderList$1,Fragment:_Fragment$6,openBlock:_openBlock$8,createElementBlock:_createElementBlock$7,createBlock:_createBlock$2,createVNode:_createVNode$6} = await importShared('vue');

const _hoisted_1$8 = { class: "global-controls" };
const _sfc_main$8 = /* @__PURE__ */ _defineComponent$8({
  __name: "GlobalControls",
  props: {
    model: {}
  },
  setup(__props) {
    return (_ctx, _cache) => {
      return _openBlock$8(), _createElementBlock$7("div", _hoisted_1$8, [
        (_openBlock$8(true), _createElementBlock$7(_Fragment$6, null, _renderList$1(_unref$6(topSwitchFields), (field) => {
          return _openBlock$8(), _createBlock$2(FieldControl, {
            key: field.key,
            field,
            model: _ctx.model
          }, null, 8, ["field", "model"]);
        }), 128)),
        _createVNode$6(RiskAlert, { text: "重置数据会清空待定、暂停、监控等任务数据；保存后执行并自动复位。" })
      ]);
    };
  }
});

const GlobalControls = /* @__PURE__ */ _export_sfc(_sfc_main$8, [["__scopeId", "data-v-f0523ceb"]]);

const {defineComponent:_defineComponent$7} = await importShared('vue');

const {toDisplayString:_toDisplayString,createElementVNode:_createElementVNode$7,openBlock:_openBlock$7,createElementBlock:_createElementBlock$6,createCommentVNode:_createCommentVNode,renderSlot:_renderSlot} = await importShared('vue');

const _hoisted_1$7 = { class: "section-panel" };
const _hoisted_2$6 = { class: "section-header" };
const _hoisted_3$3 = { class: "text-subtitle-1 font-weight-medium" };
const _hoisted_4$2 = {
  key: 0,
  class: "text-body-2 text-medium-emphasis"
};
const _hoisted_5$1 = { class: "section-content" };
const _sfc_main$7 = /* @__PURE__ */ _defineComponent$7({
  __name: "SectionPanel",
  props: {
    title: {},
    subtitle: {}
  },
  setup(__props) {
    return (_ctx, _cache) => {
      return _openBlock$7(), _createElementBlock$6("section", _hoisted_1$7, [
        _createElementVNode$7("header", _hoisted_2$6, [
          _createElementVNode$7("div", _hoisted_3$3, _toDisplayString(_ctx.title), 1),
          _ctx.subtitle ? (_openBlock$7(), _createElementBlock$6("div", _hoisted_4$2, _toDisplayString(_ctx.subtitle), 1)) : _createCommentVNode("", true)
        ]),
        _createElementVNode$7("div", _hoisted_5$1, [
          _renderSlot(_ctx.$slots, "default", {}, void 0, true)
        ])
      ]);
    };
  }
});

const SectionPanel = /* @__PURE__ */ _export_sfc(_sfc_main$7, [["__scopeId", "data-v-85a79c0f"]]);

const {defineComponent:_defineComponent$6} = await importShared('vue');

const {unref:_unref$5,renderList:_renderList,Fragment:_Fragment$5,openBlock:_openBlock$6,createElementBlock:_createElementBlock$5,createBlock:_createBlock$1,createElementVNode:_createElementVNode$6,withCtx:_withCtx$6} = await importShared('vue');

const _hoisted_1$6 = { class: "runtime-plan" };
const _sfc_main$6 = /* @__PURE__ */ _defineComponent$6({
  __name: "RuntimePlan",
  props: {
    model: {}
  },
  setup(__props) {
    return (_ctx, _cache) => {
      return _openBlock$6(), _createBlock$1(SectionPanel, {
        title: "运行计划",
        subtitle: "这些周期控制插件定时检查频率，与具体业务策略分开配置。"
      }, {
        default: _withCtx$6(() => [
          _createElementVNode$6("div", _hoisted_1$6, [
            (_openBlock$6(true), _createElementBlock$5(_Fragment$5, null, _renderList(_unref$5(periodFields), (field) => {
              return _openBlock$6(), _createBlock$1(FieldControl, {
                key: field.key,
                field,
                model: _ctx.model
              }, null, 8, ["field", "model"]);
            }), 128))
          ])
        ]),
        _: 1
      });
    };
  }
});

const RuntimePlan = /* @__PURE__ */ _export_sfc(_sfc_main$6, [["__scopeId", "data-v-e39e4cfe"]]);

const {defineComponent:_defineComponent$5} = await importShared('vue');

const {unref:_unref$4,createVNode:_createVNode$5,withCtx:_withCtx$5,createElementVNode:_createElementVNode$5,Fragment:_Fragment$4,openBlock:_openBlock$5,createElementBlock:_createElementBlock$4} = await importShared('vue');

const _hoisted_1$5 = { class: "tab-grid tab-grid--two" };
const _hoisted_2$5 = { class: "tab-grid tab-grid--two" };
const _sfc_main$5 = /* @__PURE__ */ _defineComponent$5({
  __name: "BestVersionTab",
  props: {
    model: {}
  },
  setup(__props) {
    return (_ctx, _cache) => {
      return _openBlock$5(), _createElementBlock$4(_Fragment$4, null, [
        _createVNode$5(SectionPanel, {
          title: "洗版范围",
          subtitle: "洗版是否启用由洗版类型决定，关闭时不创建和巡检洗版订阅。"
        }, {
          default: _withCtx$5(() => [
            _createVNode$5(FieldControl, {
              field: _unref$4(fields).best_version_type,
              model: _ctx.model
            }, null, 8, ["field", "model"])
          ]),
          _: 1
        }),
        _createVNode$5(SectionPanel, { title: "时限与转换" }, {
          default: _withCtx$5(() => [
            _createElementVNode$5("div", _hoisted_1$5, [
              _createVNode$5(FieldControl, {
                field: _unref$4(fields).best_version_remaining_days,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$5(FieldControl, {
                field: _unref$4(fields).best_version_episode_to_full,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$5(SectionPanel, { title: "存量回填" }, {
          default: _withCtx$5(() => [
            _createElementVNode$5("div", _hoisted_2$5, [
              _createVNode$5(FieldControl, {
                field: _unref$4(fields).best_version_backfill_enabled,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$5(FieldControl, {
                field: _unref$4(fields).backfill_best_version_now,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$5(SectionPanel, { title: "整理记录清理" }, {
          default: _withCtx$5(() => [
            _createVNode$5(FieldControl, {
              field: _unref$4(fields).best_version_clear_history_type,
              model: _ctx.model
            }, null, 8, ["field", "model"]),
            _createVNode$5(RiskAlert, {
              type: "error",
              text: "清理整理记录和文件属于破坏性能力，应先确认媒体库与下载器路径关系。"
            })
          ]),
          _: 1
        })
      ], 64);
    };
  }
});

const BestVersionTab = /* @__PURE__ */ _export_sfc(_sfc_main$5, [["__scopeId", "data-v-c422bd12"]]);

const {defineComponent:_defineComponent$4} = await importShared('vue');

const {unref:_unref$3,createVNode:_createVNode$4,withCtx:_withCtx$4,createElementVNode:_createElementVNode$4,resolveComponent:_resolveComponent$1,Fragment:_Fragment$3,openBlock:_openBlock$4,createElementBlock:_createElementBlock$3} = await importShared('vue');

const _hoisted_1$4 = { class: "tab-grid tab-grid--three" };
const _hoisted_2$4 = { class: "tab-grid tab-grid--three" };
const _hoisted_3$2 = { class: "tab-grid tab-grid--three" };
const _hoisted_4$1 = { class: "tab-grid tab-grid--two" };
const _sfc_main$4 = /* @__PURE__ */ _defineComponent$4({
  __name: "CompletionSignalTab",
  props: {
    model: {}
  },
  setup(__props) {
    return (_ctx, _cache) => {
      const _component_VExpansionPanelText = _resolveComponent$1("VExpansionPanelText");
      const _component_VExpansionPanel = _resolveComponent$1("VExpansionPanel");
      const _component_VExpansionPanels = _resolveComponent$1("VExpansionPanels");
      return _openBlock$4(), _createElementBlock$3(_Fragment$3, null, [
        _createVNode$4(SectionPanel, {
          title: "守卫策略总览",
          subtitle: "选择完成前复核强度。平衡模式适合作为默认策略。"
        }, {
          default: _withCtx$4(() => [
            _createVNode$4(FieldControl, {
              field: _unref$3(fields).completion_guard_mode,
              model: _ctx.model
            }, null, 8, ["field", "model"])
          ]),
          _: 1
        }),
        _createVNode$4(SectionPanel, {
          title: "信号来源",
          subtitle: "变更速率判断总集数稳定性；播出节奏用于估算等待期。"
        }, {
          default: _withCtx$4(() => [
            _createElementVNode$4("div", _hoisted_1$4, [
              _createVNode$4(FieldControl, {
                field: _unref$3(fields).volatility_enabled,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$4(FieldControl, {
                field: _unref$3(fields).cadence_enabled,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$4(FieldControl, {
                field: _unref$3(fields).season_cooldown_days,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$4(SectionPanel, {
          title: "待定释放",
          subtitle: "完成守卫待定不会无限保留；信号不稳定时重新计时。"
        }, {
          default: _withCtx$4(() => [
            _createElementVNode$4("div", _hoisted_2$4, [
              _createVNode$4(FieldControl, {
                field: _unref$3(fields).timeout_release_enabled,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$4(FieldControl, {
                field: _unref$3(fields).timeout_release_days,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$4(FieldControl, {
                field: _unref$3(fields).timeout_cadence_acceleration,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$4(SectionPanel, {
          title: "完成后纠错",
          subtitle: "完成后复查 TMDB 集数，检测到增集时自动重建订阅。"
        }, {
          default: _withCtx$4(() => [
            _createElementVNode$4("div", _hoisted_3$2, [
              _createVNode$4(FieldControl, {
                field: _unref$3(fields).verify_enabled,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$4(FieldControl, {
                field: _unref$3(fields).verify_interval_hours,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$4(FieldControl, {
                field: _unref$3(fields).verify_retention_days,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$4(_component_VExpansionPanels, { variant: "accordion" }, {
          default: _withCtx$4(() => [
            _createVNode$4(_component_VExpansionPanel, { title: "高级信号参数" }, {
              default: _withCtx$4(() => [
                _createVNode$4(_component_VExpansionPanelText, null, {
                  default: _withCtx$4(() => [
                    _createElementVNode$4("div", _hoisted_4$1, [
                      _createVNode$4(FieldControl, {
                        field: _unref$3(fields).volatility_window_days,
                        model: _ctx.model
                      }, null, 8, ["field", "model"]),
                      _createVNode$4(FieldControl, {
                        field: _unref$3(fields).cadence_multiplier,
                        model: _ctx.model
                      }, null, 8, ["field", "model"]),
                      _createVNode$4(FieldControl, {
                        field: _unref$3(fields).cadence_min_window_days,
                        model: _ctx.model
                      }, null, 8, ["field", "model"]),
                      _createVNode$4(FieldControl, {
                        field: _unref$3(fields).cadence_min_episodes,
                        model: _ctx.model
                      }, null, 8, ["field", "model"])
                    ])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ], 64);
    };
  }
});

const CompletionSignalTab = /* @__PURE__ */ _export_sfc(_sfc_main$4, [["__scopeId", "data-v-6f19b0b3"]]);

const {defineComponent:_defineComponent$3} = await importShared('vue');

const {unref:_unref$2,createVNode:_createVNode$3,createElementVNode:_createElementVNode$3,withCtx:_withCtx$3,Fragment:_Fragment$2,openBlock:_openBlock$3,createElementBlock:_createElementBlock$2} = await importShared('vue');

const _hoisted_1$3 = { class: "tab-grid tab-grid--three" };
const _hoisted_2$3 = { class: "tab-grid tab-grid--two" };
const _hoisted_3$1 = { class: "tab-grid tab-grid--three" };
const _hoisted_4 = { class: "tab-grid tab-grid--two" };
const _hoisted_5 = { class: "tab-grid tab-grid--two" };
const _sfc_main$3 = /* @__PURE__ */ _defineComponent$3({
  __name: "DeleteTab",
  props: {
    model: {}
  },
  setup(__props) {
    return (_ctx, _cache) => {
      return _openBlock$3(), _createElementBlock$2(_Fragment$2, null, [
        _createVNode$3(SectionPanel, {
          title: "删除入口",
          subtitle: "分别控制下载超时、手动删除和 Tracker 响应三类触发来源。"
        }, {
          default: _withCtx$3(() => [
            _createElementVNode$3("div", _hoisted_1$3, [
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).download_monitor_enabled,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).manual_delete_listen,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).tracker_response_listen,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$3(SectionPanel, {
          title: "删除后动作",
          subtitle: "删除后补搜与跳过删除指纹共同减少坏种重复命中。"
        }, {
          default: _withCtx$3(() => [
            _createElementVNode$3("div", _hoisted_2$3, [
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).auto_search_when_delete,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).skip_deletion,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$3(SectionPanel, { title: "下载进度观察窗口" }, {
          default: _withCtx$3(() => [
            _createElementVNode$3("div", _hoisted_3$1, [
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).download_timeout_minutes,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).download_progress_threshold,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).download_retry_limit,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$3(SectionPanel, { title: "记录与排除" }, {
          default: _withCtx$3(() => [
            _createElementVNode$3("div", _hoisted_4, [
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).delete_record_retention_hours,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).delete_exclude_tags,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$3(SectionPanel, { title: "Tracker 关键字" }, {
          default: _withCtx$3(() => [
            _createElementVNode$3("div", _hoisted_5, [
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).open_tracker_dialog,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$3(FieldControl, {
                field: _unref$2(fields).default_tracker_response,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ]),
            _createVNode$3(RiskAlert, { text: "命中 Tracker 关键字会触发自动删种，请仅填写明确代表无效种子的响应。" })
          ]),
          _: 1
        })
      ], 64);
    };
  }
});

const DeleteTab = /* @__PURE__ */ _export_sfc(_sfc_main$3, [["__scopeId", "data-v-67403f11"]]);

const {defineComponent:_defineComponent$2} = await importShared('vue');

const {unref:_unref$1,createVNode:_createVNode$2,createElementVNode:_createElementVNode$2,withCtx:_withCtx$2,Fragment:_Fragment$1,openBlock:_openBlock$2,createElementBlock:_createElementBlock$1} = await importShared('vue');

const _hoisted_1$2 = { class: "tab-grid tab-grid--two" };
const _hoisted_2$2 = { class: "tab-grid tab-grid--three" };
const _hoisted_3 = { class: "tab-grid tab-grid--three" };
const _sfc_main$2 = /* @__PURE__ */ _defineComponent$2({
  __name: "PauseTab",
  props: {
    model: {}
  },
  setup(__props) {
    return (_ctx, _cache) => {
      return _openBlock$2(), _createElementBlock$1(_Fragment$1, null, [
        _createVNode$2(SectionPanel, {
          title: "暂停入口",
          subtitle: "控制新增订阅自动暂停，以及名单内用户新增订阅的暂停策略。"
        }, {
          default: _withCtx$2(() => [
            _createElementVNode$2("div", _hoisted_1$2, [
              _createVNode$2(FieldControl, {
                field: _unref$1(fields).pause_enhanced_enabled,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$2(FieldControl, {
                field: _unref$1(fields).auto_pause_users,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$2(SectionPanel, { title: "开播前暂停" }, {
          default: _withCtx$2(() => [
            _createElementVNode$2("div", _hoisted_2$2, [
              _createVNode$2(FieldControl, {
                field: _unref$1(fields).movie_air_pause_days,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$2(FieldControl, {
                field: _unref$1(fields).tv_air_pause_days,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$2(FieldControl, {
                field: _unref$1(fields).airing_pause_days,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$2(SectionPanel, {
          title: "无下载处理",
          subtitle: "媒体上映后长时间没有下载时，按选择的策略调整订阅。"
        }, {
          default: _withCtx$2(() => [
            _createElementVNode$2("div", _hoisted_3, [
              _createVNode$2(FieldControl, {
                field: _unref$1(fields).movie_no_download_days,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$2(FieldControl, {
                field: _unref$1(fields).tv_no_download_days,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$2(FieldControl, {
                field: _unref$1(fields).no_download_actions,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ]),
            _createVNode$2(RiskAlert, { text: "无下载处理中的删除订阅属于高风险策略，请只在确认不再需要该订阅时启用。" })
          ]),
          _: 1
        })
      ], 64);
    };
  }
});

const PauseTab = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-4835d07d"]]);

const {defineComponent:_defineComponent$1} = await importShared('vue');

const {unref:_unref,createVNode:_createVNode$1,createElementVNode:_createElementVNode$1,withCtx:_withCtx$1,Fragment:_Fragment,openBlock:_openBlock$1,createElementBlock:_createElementBlock} = await importShared('vue');

const _hoisted_1$1 = { class: "tab-grid tab-grid--two" };
const _hoisted_2$1 = { class: "tab-grid tab-grid--two" };
const _sfc_main$1 = /* @__PURE__ */ _defineComponent$1({
  __name: "PendingTab",
  props: {
    model: {}
  },
  setup(__props) {
    return (_ctx, _cache) => {
      return _openBlock$1(), _createElementBlock(_Fragment, null, [
        _createVNode$1(SectionPanel, {
          title: "待定入口",
          subtitle: "下载未完成或剧集仍处于播出早期时，避免订阅提前完成。"
        }, {
          default: _withCtx$1(() => [
            _createElementVNode$1("div", _hoisted_1$1, [
              _createVNode$1(FieldControl, {
                field: _unref(fields).pending_download_enabled,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$1(FieldControl, {
                field: _unref(fields).pending_enhanced_enabled,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$1(SectionPanel, {
          title: "播出待定阈值",
          subtitle: "天数和集数任一规则命中时可进入待定；0 表示对应规则不参与。"
        }, {
          default: _withCtx$1(() => [
            _createElementVNode$1("div", _hoisted_2$1, [
              _createVNode$1(FieldControl, {
                field: _unref(fields).auto_tv_pending_days,
                model: _ctx.model
              }, null, 8, ["field", "model"]),
              _createVNode$1(FieldControl, {
                field: _unref(fields).auto_tv_pending_episodes,
                model: _ctx.model
              }, null, 8, ["field", "model"])
            ])
          ]),
          _: 1
        }),
        _createVNode$1(SectionPanel, { title: "信号辅助" }, {
          default: _withCtx$1(() => [
            _createVNode$1(FieldControl, {
              field: _unref(fields).pending_use_volatility,
              model: _ctx.model
            }, null, 8, ["field", "model"])
          ]),
          _: 1
        })
      ], 64);
    };
  }
});

const PendingTab = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-34b13fb8"]]);

const {defineComponent:_defineComponent} = await importShared('vue');

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createTextVNode:_createTextVNode} = await importShared('vue');

const _hoisted_1 = { class: "config-domains" };
const _hoisted_2 = { class: "domain-content" };
const {reactive,ref,watch} = await importShared('vue');
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Config",
  props: {
    initialConfig: { default: () => ({}) }
  },
  emits: ["save", "close"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const config = reactive({});
    const activeDomain = ref("delete");
    const domains = [
      { key: "delete", title: "种子删除", icon: "mdi-delete-clock" },
      { key: "pending", title: "订阅待定", icon: "mdi-timer-sand" },
      { key: "pause", title: "订阅暂停", icon: "mdi-pause-circle-outline" },
      { key: "best-version", title: "订阅洗版", icon: "mdi-auto-fix" },
      { key: "completion", title: "完结信号", icon: "mdi-shield-check-outline" }
    ];
    function syncConfig(nextConfig) {
      Object.keys(config).forEach((key) => {
        delete config[key];
      });
      Object.assign(config, nextConfig);
    }
    function saveConfig() {
      emit("save", { ...config });
    }
    watch(
      () => props.initialConfig,
      (nextConfig) => syncConfig(nextConfig ?? {}),
      { immediate: true, deep: true }
    );
    return (_ctx, _cache) => {
      const _component_VSpacer = _resolveComponent("VSpacer");
      const _component_VBtn = _resolveComponent("VBtn");
      const _component_VCardTitle = _resolveComponent("VCardTitle");
      const _component_VDivider = _resolveComponent("VDivider");
      const _component_VAlert = _resolveComponent("VAlert");
      const _component_VCardText = _resolveComponent("VCardText");
      const _component_VCardActions = _resolveComponent("VCardActions");
      const _component_VCard = _resolveComponent("VCard");
      return _openBlock(), _createBlock(_component_VCard, {
        class: "subscribe-assistant-config",
        flat: ""
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardTitle, { class: "config-title" }, {
            default: _withCtx(() => [
              _cache[3] || (_cache[3] = _createElementVNode("div", null, [
                _createElementVNode("div", { class: "text-h6 font-weight-medium" }, "订阅助手（增强版）"),
                _createElementVNode("div", { class: "text-body-2 text-medium-emphasis" }, "按业务域组织配置，保存后由插件运行时读取同一套配置键。")
              ], -1)),
              _createVNode(_component_VSpacer),
              _createVNode(_component_VBtn, {
                icon: "mdi-close",
                variant: "text",
                density: "comfortable",
                "aria-label": "关闭",
                onClick: _cache[0] || (_cache[0] = ($event) => emit("close"))
              })
            ]),
            _: 1
          }),
          _createVNode(_component_VDivider),
          _createVNode(_component_VCardText, { class: "config-content" }, {
            default: _withCtx(() => [
              _createVNode(_component_VAlert, {
                type: "warning",
                variant: "tonal",
                title: "BETA 功能",
                text: "本插件仍处于测试阶段，可能调整订阅状态、洗版记录、下载任务和媒体文件。"
              }),
              _createVNode(GlobalControls, {
                model: config,
                class: "mt-6"
              }, null, 8, ["model"]),
              _createVNode(RuntimePlan, {
                model: config,
                class: "mt-4"
              }, null, 8, ["model"]),
              _createElementVNode("div", _hoisted_1, [
                _createVNode(DomainNav, {
                  modelValue: activeDomain.value,
                  "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => activeDomain.value = $event),
                  items: domains
                }, null, 8, ["modelValue"]),
                _createElementVNode("main", _hoisted_2, [
                  activeDomain.value === "delete" ? (_openBlock(), _createBlock(DeleteTab, {
                    key: 0,
                    model: config
                  }, null, 8, ["model"])) : activeDomain.value === "pending" ? (_openBlock(), _createBlock(PendingTab, {
                    key: 1,
                    model: config
                  }, null, 8, ["model"])) : activeDomain.value === "pause" ? (_openBlock(), _createBlock(PauseTab, {
                    key: 2,
                    model: config
                  }, null, 8, ["model"])) : activeDomain.value === "best-version" ? (_openBlock(), _createBlock(BestVersionTab, {
                    key: 3,
                    model: config
                  }, null, 8, ["model"])) : (_openBlock(), _createBlock(CompletionSignalTab, {
                    key: 4,
                    model: config
                  }, null, 8, ["model"]))
                ])
              ])
            ]),
            _: 1
          }),
          _createVNode(_component_VDivider),
          _createVNode(_component_VCardActions, { class: "config-actions" }, {
            default: _withCtx(() => [
              _createVNode(_component_VSpacer),
              _createVNode(_component_VBtn, {
                variant: "text",
                onClick: _cache[2] || (_cache[2] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => _cache[4] || (_cache[4] = [
                  _createTextVNode("取消")
                ])),
                _: 1
              }),
              _createVNode(_component_VBtn, {
                color: "primary",
                variant: "flat",
                "prepend-icon": "mdi-content-save",
                onClick: saveConfig
              }, {
                default: _withCtx(() => _cache[5] || (_cache[5] = [
                  _createTextVNode(" 保存 ")
                ])),
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

const Config = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-54b62d79"]]);

export { Config as default };
