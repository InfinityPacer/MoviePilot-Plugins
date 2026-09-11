import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const ROOT = "plugin/ArchiveManager/";
function queryPath(endpoint, params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== void 0 && value !== "") query.set(key, String(value));
  }
  const suffix = query.toString();
  return `${ROOT}${endpoint}${suffix ? `?${suffix}` : ""}`;
}
async function getData(api, path, fallback) {
  if (!api) return fallback;
  try {
    const response = await api.get(path);
    if (response.success && response.data !== null) return response.data;
    throw new Error(response.message || "请求失败");
  } catch {
    console.warn(`[ArchiveManager] ${path} unavailable`);
    return fallback;
  }
}
async function postData(api, path, body) {
  if (!api) return null;
  try {
    const response = await api.post(path, body);
    if (response.success) return response.data;
    throw new Error(response.message || "请求失败");
  } catch {
    console.warn(`[ArchiveManager] ${path} failed`);
    return null;
  }
}
async function loadSummary(api) {
  if (!api) return null;
  try {
    const response = await api.get(`${ROOT}summary`);
    if (response.success && response.data) return response.data;
    throw new Error(response.message || "请求失败");
  } catch {
    console.warn("[ArchiveManager] summary unavailable");
    return null;
  }
}
function listBatches(api, params) {
  return getData(api, queryPath("batches", params), { items: [], total: 0 });
}
function loadBatch(api, batchId) {
  return getData(api, queryPath("batch", { batch_id: batchId }), null);
}
function listFiles(api, params) {
  return getData(api, queryPath("files", params), { items: [], directories: [], total: 0 });
}
function startPreview(api, task) {
  return postData(api, `${ROOT}preview`, { task });
}
function pollPreview(api, jobId) {
  return getData(api, queryPath("preview", { job_id: jobId }), null);
}
function runTask(api, taskId) {
  return postData(api, `${ROOT}run`, { task_id: taskId });
}
function stopTask(api, taskId) {
  return postData(api, `${ROOT}stop`, taskId ? { task_id: taskId } : {});
}
function retryBatch(api, batchId) {
  return postData(api, `${ROOT}retry`, { batch_id: batchId });
}
function repairBatch(api, batchId) {
  return postData(api, `${ROOT}repair`, { batch_id: batchId });
}

const taskDefaults = {
  id: "",
  name: "新建归档任务",
  batch_name_template: "{date}_{sequence}",
  archive_name_template: "{id}",
  archive_layout: "directory",
  enabled: false,
  source_dir: "",
  output_dir: "",
  manifest_dir: "",
  cron: "0 2 * * *",
  timezone: "",
  recursive: true,
  include_patterns: [],
  exclude_patterns: [],
  grouping: "directory_date",
  directory_depth: 1,
  time_grain: "day",
  max_files: 1e3,
  max_bytes: 4294967296,
  max_batches: 10,
  archive_age_days: 7,
  stability_seconds: 60,
  auto_continue: false,
  max_pending_archives: 1,
  max_pending_bytes: 0,
  min_free_bytes: 1073741824,
  format: "7z",
  compression: "normal",
  encryption: "none",
  encrypt_names: false,
  password: "",
  password_version: "1",
  verify: true,
  delete_source: false
};
const configDefaults = {
  enabled: false,
  notify: false,
  notify_events: ["failure"]};

function isRecord(value) {
  return typeof value === "object" && value !== null;
}
function toBoolean(value, fallback) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "1", "yes", "on"].includes(normalized)) return true;
    if (["false", "0", "no", "off", ""].includes(normalized)) return false;
  }
  return fallback;
}
function toStringValue(value, fallback) {
  return typeof value === "string" ? value : fallback;
}
function toFiniteNumber(value, fallback, minimum = 0) {
  const parsed = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
  return Number.isFinite(parsed) ? Math.max(minimum, parsed) : fallback;
}
function toStringArray(value) {
  const source = Array.isArray(value) ? value : typeof value === "string" ? value.split(/\r?\n|,/) : [];
  return source.map((item) => String(item).trim()).filter(Boolean);
}
function makeId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `archive-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function createArchiveTask(value = {}) {
  const source = isRecord(value) ? value : {};
  const password = toStringValue(source.password, taskDefaults.password);
  const task = {
    ...taskDefaults,
    id: toStringValue(source.id, "") || makeId(),
    name: toStringValue(source.name, taskDefaults.name),
    batch_name_template: toStringValue(source.batch_name_template, taskDefaults.batch_name_template),
    archive_name_template: toStringValue(source.archive_name_template, taskDefaults.archive_name_template),
    archive_layout: source.archive_layout === "flat" ? "flat" : "directory",
    enabled: toBoolean(source.enabled, taskDefaults.enabled),
    source_dir: toStringValue(source.source_dir, taskDefaults.source_dir),
    output_dir: toStringValue(source.output_dir, taskDefaults.output_dir),
    manifest_dir: toStringValue(source.manifest_dir, taskDefaults.manifest_dir),
    cron: toStringValue(source.cron, taskDefaults.cron),
    timezone: toStringValue(source.timezone, taskDefaults.timezone),
    recursive: toBoolean(source.recursive, taskDefaults.recursive),
    include_patterns: toStringArray(source.include_patterns),
    exclude_patterns: toStringArray(source.exclude_patterns),
    grouping: ["none", "directory", "date", "directory_date"].includes(source.grouping) ? source.grouping : taskDefaults.grouping,
    directory_depth: toFiniteNumber(source.directory_depth, taskDefaults.directory_depth, 1),
    time_grain: ["hour", "day", "month"].includes(source.time_grain) ? source.time_grain : taskDefaults.time_grain,
    max_files: toFiniteNumber(source.max_files, taskDefaults.max_files),
    max_bytes: toFiniteNumber(source.max_bytes, taskDefaults.max_bytes),
    max_batches: toFiniteNumber(source.max_batches, taskDefaults.max_batches),
    archive_age_days: toFiniteNumber(source.archive_age_days, taskDefaults.archive_age_days),
    stability_seconds: toFiniteNumber(source.stability_seconds, taskDefaults.stability_seconds),
    auto_continue: toBoolean(source.auto_continue, taskDefaults.auto_continue),
    max_pending_archives: toFiniteNumber(source.max_pending_archives, taskDefaults.max_pending_archives),
    max_pending_bytes: toFiniteNumber(source.max_pending_bytes, taskDefaults.max_pending_bytes),
    min_free_bytes: toFiniteNumber(source.min_free_bytes, taskDefaults.min_free_bytes),
    format: source.format === "zip" ? "zip" : taskDefaults.format,
    compression: ["store", "fast", "normal", "high"].includes(source.compression) ? source.compression : taskDefaults.compression,
    encryption: source.encryption === "aes256" ? "aes256" : taskDefaults.encryption,
    encrypt_names: toBoolean(source.encrypt_names, taskDefaults.encrypt_names),
    password,
    password_version: toStringValue(source.password_version, taskDefaults.password_version),
    verify: toBoolean(source.verify, taskDefaults.verify),
    delete_source: toBoolean(source.delete_source, taskDefaults.delete_source)
  };
  if (source.password_set !== void 0 || password.length > 0)
    task.password_set = toBoolean(source.password_set, password.length > 0);
  if (task.delete_source) task.verify = true;
  if (task.format === "zip") task.encrypt_names = false;
  return task;
}
function normalizeArchiveConfig(value) {
  const source = isRecord(value) ? value : {};
  const tasks = Array.isArray(source.tasks) ? source.tasks.map(createArchiveTask) : [];
  const notifyEvents = toStringArray(source.notify_events).filter(
    (event) => ["success", "failure", "other"].includes(event)
  );
  return {
    enabled: toBoolean(source.enabled, configDefaults.enabled),
    notify: toBoolean(source.notify, configDefaults.notify),
    notify_events: source.notify_events === void 0 ? [...configDefaults.notify_events] : notifyEvents,
    tasks
  };
}
function cloneTask(task) {
  return {
    ...task,
    include_patterns: [...task.include_patterns],
    exclude_patterns: [...task.exclude_patterns]
  };
}

const archiveLogo = "data:image/png;base64,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";

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock,normalizeClass:_normalizeClass,withModifiers:_withModifiers,withKeys:_withKeys} = await importShared('vue');

const _hoisted_1 = { class: "archive-config" };
const _hoisted_2 = { class: "archive-header" };
const _hoisted_3 = { class: "archive-header__brand" };
const _hoisted_4 = ["src"];
const _hoisted_5 = { class: "archive-header__identity" };
const _hoisted_6 = { class: "archive-header__crumbs" };
const _hoisted_7 = { class: "archive-header__title-row" };
const _hoisted_8 = { class: "archive-header__actions" };
const _hoisted_9 = { class: "archive-body" };
const _hoisted_10 = { class: "archive-workspace" };
const _hoisted_11 = { class: "archive-nav" };
const _hoisted_12 = { class: "archive-nav__help" };
const _hoisted_13 = { class: "archive-main" };
const _hoisted_14 = { class: "archive-main__heading" };
const _hoisted_15 = { class: "archive-main__title" };
const _hoisted_16 = { class: "archive-main__heading-actions" };
const _hoisted_17 = {
  key: 0,
  class: "archive-view archive-overview"
};
const _hoisted_18 = {
  class: "archive-metrics",
  "aria-label": "归档统计"
};
const _hoisted_19 = { class: "archive-metric" };
const _hoisted_20 = { class: "archive-metric" };
const _hoisted_21 = { class: "archive-metric" };
const _hoisted_22 = { class: "archive-metric" };
const _hoisted_23 = { class: "archive-metric" };
const _hoisted_24 = {
  key: 0,
  class: "archive-inline-state"
};
const _hoisted_25 = {
  key: 1,
  class: "archive-inline-state archive-inline-state--error"
};
const _hoisted_26 = {
  key: 2,
  class: "archive-running"
};
const _hoisted_27 = { class: "archive-running__copy" };
const _hoisted_28 = { key: 0 };
const _hoisted_29 = { key: 1 };
const _hoisted_30 = {
  key: 3,
  class: "archive-section archive-progress"
};
const _hoisted_31 = { class: "archive-section__header" };
const _hoisted_32 = { class: "archive-progress__list" };
const _hoisted_33 = { class: "archive-progress__identity" };
const _hoisted_34 = { class: "archive-progress__detail" };
const _hoisted_35 = { class: "archive-progress__capacity" };
const _hoisted_36 = { class: "archive-section archive-overview-controls" };
const _hoisted_37 = { class: "archive-form-grid archive-form-grid--three" };
const _hoisted_38 = {
  key: 0,
  class: "archive-section archive-task-list"
};
const _hoisted_39 = { class: "archive-section__header" };
const _hoisted_40 = {
  key: 0,
  class: "archive-empty"
};
const _hoisted_41 = {
  key: 1,
  class: "archive-section archive-task-detail"
};
const _hoisted_42 = { class: "archive-section__header" };
const _hoisted_43 = { class: "archive-section__actions" };
const _hoisted_44 = { class: "archive-detail-grid" };
const _hoisted_45 = { class: "archive-detail-flags" };
const _hoisted_46 = { class: "archive-detail-actions" };
const _hoisted_47 = {
  key: 2,
  class: "archive-section archive-editor"
};
const _hoisted_48 = { class: "archive-section__header" };
const _hoisted_49 = { class: "archive-editor__group" };
const _hoisted_50 = { class: "archive-form-grid archive-form-grid--two" };
const _hoisted_51 = { class: "archive-editor__group" };
const _hoisted_52 = { class: "archive-form-grid" };
const _hoisted_53 = { class: "archive-editor__group" };
const _hoisted_54 = { class: "archive-form-grid archive-form-grid--two" };
const _hoisted_55 = { class: "archive-naming-preview" };
const _hoisted_56 = { class: "archive-editor__group" };
const _hoisted_57 = { class: "archive-form-grid archive-form-grid--two" };
const _hoisted_58 = { class: "archive-editor__group" };
const _hoisted_59 = { class: "archive-form-grid archive-form-grid--three" };
const _hoisted_60 = { class: "archive-editor__group" };
const _hoisted_61 = { class: "archive-form-grid archive-form-grid--three" };
const _hoisted_62 = { class: "archive-editor__group" };
const _hoisted_63 = { class: "archive-form-grid archive-form-grid--three" };
const _hoisted_64 = { class: "archive-editor__group" };
const _hoisted_65 = { class: "archive-form-grid archive-form-grid--two" };
const _hoisted_66 = { class: "archive-editor__actions" };
const _hoisted_67 = {
  key: 1,
  class: "archive-view archive-table-view"
};
const _hoisted_68 = { class: "archive-filter-bar" };
const _hoisted_69 = {
  key: 0,
  class: "archive-inline-state"
};
const _hoisted_70 = {
  key: 1,
  class: "archive-empty archive-empty--table"
};
const _hoisted_71 = {
  key: 2,
  class: "archive-table-wrap"
};
const _hoisted_72 = { class: "archive-table" };
const _hoisted_73 = ["onClick"];
const _hoisted_74 = { class: "archive-id" };
const _hoisted_75 = { class: "archive-table__numeric" };
const _hoisted_76 = { class: "archive-table__numeric" };
const _hoisted_77 = { class: "sr-only" };
const _hoisted_78 = {
  key: 3,
  class: "archive-pagination"
};
const _hoisted_79 = {
  key: 2,
  class: "archive-view archive-table-view"
};
const _hoisted_80 = {
  key: 0,
  class: "archive-empty archive-empty--table"
};
const _hoisted_81 = {
  key: 1,
  class: "archive-empty archive-empty--table"
};
const _hoisted_82 = { class: "archive-filter-bar" };
const _hoisted_83 = {
  "aria-label": "文件目录",
  class: "archive-breadcrumbs"
};
const _hoisted_84 = {
  key: 0,
  class: "archive-inline-state"
};
const _hoisted_85 = {
  key: 1,
  class: "archive-empty archive-empty--table"
};
const _hoisted_86 = {
  key: 2,
  class: "archive-files-browser"
};
const _hoisted_87 = {
  key: 0,
  class: "archive-directory-list"
};
const _hoisted_88 = ["onClick"];
const _hoisted_89 = { class: "archive-table-wrap" };
const _hoisted_90 = { class: "archive-table" };
const _hoisted_91 = { class: "archive-table__numeric" };
const _hoisted_92 = {
  key: 3,
  class: "archive-pagination"
};
const _hoisted_93 = {
  key: 0,
  class: "archive-mobile-save-dock"
};
const _hoisted_94 = {
  "aria-live": "polite",
  class: "archive-mobile-save-dock__state"
};
const _hoisted_95 = {
  key: 0,
  class: "archive-dialog-state"
};
const _hoisted_96 = {
  key: 1,
  class: "archive-dialog-state archive-dialog-state--error"
};
const _hoisted_97 = { class: "archive-preview-metrics" };
const _hoisted_98 = { class: "archive-table-wrap" };
const _hoisted_99 = { class: "archive-table" };
const _hoisted_100 = { class: "archive-table__numeric" };
const _hoisted_101 = { class: "archive-table__numeric" };
const _hoisted_102 = { key: 1 };
const _hoisted_103 = {
  key: 0,
  class: "archive-dialog-state"
};
const _hoisted_104 = { class: "archive-batch-summary" };
const _hoisted_105 = { class: "archive-paths" };
const _hoisted_106 = {
  key: 2,
  class: "archive-table-wrap"
};
const _hoisted_107 = { class: "archive-table" };
const _hoisted_108 = { class: "archive-table__numeric" };
const _hoisted_109 = {
  key: 3,
  class: "archive-cleanup"
};
const _hoisted_110 = { class: "archive-cleanup-grid" };
const {computed,getCurrentInstance,inject,onBeforeUnmount,onMounted,ref,watch} = await importShared('vue');
const README_URL = "https://github.com/InfinityPacer/MoviePilot-Plugins/blob/main/plugins.v3/archivemanager/README.md";
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Config",
  props: {
    initialConfig: {},
    api: {}
  },
  emits: ["save", "close", "layout"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    emit("layout", { maxWidth: "68rem" });
    const instance = getCurrentInstance();
    const locale = computed(() => String(instance?.appContext.config.globalProperties.$i18n?.locale ?? "zh-CN"));
    const hostToast = inject("moviepilot:toast", null);
    const hostConfirm = inject("moviepilot:confirm", null);
    const draft = ref(normalizeArchiveConfig(props.initialConfig));
    const original = ref(normalizeArchiveConfig(props.initialConfig));
    const activeView = ref("overview");
    const activeTaskId = ref(draft.value.tasks[0]?.id ?? "");
    const editorOpen = ref(false);
    const editingTaskId = ref(null);
    const taskEditor = ref(createArchiveTask());
    const includePatternsText = ref("");
    const excludePatternsText = ref("");
    const minFreeGiB = ref(1);
    const mobileNavOpen = ref(false);
    const compatibilityOpen = ref(false);
    const compatibilityReason = ref("format");
    const pendingFormat = ref(null);
    const summary = ref(null);
    const summaryState = ref("loading");
    const notice = ref(null);
    const operationBusy = ref(false);
    const operationMessage = ref("");
    const previewOpen = ref(false);
    const previewJobId = ref("");
    const previewState = ref("idle");
    const previewResult = ref(null);
    const previewMessage = ref("");
    const batchTaskFilter = ref(activeTaskId.value);
    const batchStatusFilter = ref("");
    const batchPage = ref(1);
    const batchPageSize = ref(30);
    const batchData = ref({ items: [], total: 0 });
    const batchLoading = ref(false);
    const batchDialogOpen = ref(false);
    const selectedBatch = ref(null);
    const batchDetailLoading = ref(false);
    const fileTaskFilter = ref(activeTaskId.value);
    const fileDirectory = ref("");
    const fileQuery = ref("");
    const fileStatus = ref("");
    const filePage = ref(1);
    const filePageSize = ref(30);
    const fileData = ref({ items: [], directories: [], total: 0 });
    const fileLoading = ref(false);
    let previewTimer;
    let operationTimer;
    let summaryRequestToken = 0;
    let batchRequestToken = 0;
    let fileRequestToken = 0;
    let disposed = false;
    const tasksById = computed(() => new Map(draft.value.tasks.map((task) => [task.id, task])));
    const selectedTask = computed(() => tasksById.value.get(activeTaskId.value) ?? draft.value.tasks[0] ?? null);
    const hasFileTaskSelection = computed(() => Boolean(fileTaskFilter.value && tasksById.value.has(fileTaskFilter.value)));
    const isDirty = computed(() => JSON.stringify(draft.value) !== JSON.stringify(original.value));
    const summaryValue = computed(
      () => summary.value ?? {
        archived_files: 0,
        archive_count: 0,
        source_bytes: 0,
        archive_bytes: 0,
        deleted_files: 0,
        failed_batches: 0,
        pending_files: 0,
        running: null,
        queued: [],
        config_error: "",
        last_error: null,
        tasks: []
      }
    );
    const lastErrorMessage = computed(() => {
      const error = summaryValue.value.last_error;
      return typeof error === "string" ? error : error?.message || "";
    });
    const queuedTaskNames = computed(
      () => summaryValue.value.queued.map((taskId) => tasksById.value.get(taskId)?.name ?? taskId).filter(Boolean)
    );
    const batchPageCount = computed(() => Math.max(1, Math.ceil(batchData.value.total / batchPageSize.value)));
    const filePageCount = computed(() => Math.max(1, Math.ceil(fileData.value.total / filePageSize.value)));
    const breadcrumbs = computed(() => {
      const parts = fileDirectory.value.split("/").filter(Boolean);
      return [
        { title: "根目录", path: "" },
        ...parts.map((part, index) => ({ title: part, path: parts.slice(0, index + 1).join("/") }))
      ];
    });
    const taskEditorTitle = computed(() => editingTaskId.value ? "编辑归档任务" : "新增归档任务");
    const taskEditorHasSavedPassword = computed(() => Boolean(taskEditor.value.password_set));
    const namingExamples = computed(() => {
      const values = {
        task_name: taskEditor.value.name || "归档任务",
        date: "20260911",
        time: "040020",
        id: "7f3a9c",
        sequence: "0001"
      };
      const render = (template, fallback) => {
        const source = template.trim() || fallback;
        const rendered = source.replace(/\{([^{}]+)\}/g, (match, field) => {
          if (field.startsWith("%")) {
            return field.replace(
              /%Y|%y|%m|%d|%H|%I|%M|%S/g,
              (token) => ({ "%Y": "2026", "%y": "26", "%m": "09", "%d": "11", "%H": "04", "%I": "04", "%M": "00", "%S": "20" })[token] || token
            );
          }
          return field in values ? values[field] : match;
        });
        return rendered.trim() || fallback;
      };
      const archiveStem = render(taskEditor.value.archive_name_template, values.id);
      return {
        batch: render(taskEditor.value.batch_name_template, `${values.date}_${values.sequence}`),
        archive: `${archiveStem}.${taskEditor.value.format}`
      };
    });
    const viewLabels = {
      overview: { title: "概览", icon: "mdi-view-dashboard-outline", summary: "任务、运行状态和归档策略" },
      tasks: { title: "任务", icon: "mdi-format-list-checks", summary: "管理归档任务、命名和执行策略" },
      batches: { title: "批次", icon: "mdi-package-variant-closed", summary: "查看归档批次、清理和校验结果" },
      files: { title: "文件", icon: "mdi-file-search-outline", summary: "按目录和状态检索归档文件" }
    };
    const batchStatusOptions = [
      { title: "全部状态", value: "" },
      { title: "构建中", value: "building" },
      { title: "校验中", value: "verifying" },
      { title: "发布中", value: "publishing" },
      { title: "待补全清单", value: "manifest_pending" },
      { title: "已完成", value: "completed" },
      { title: "清理中", value: "cleaning" },
      { title: "清理失败", value: "cleanup_failed" },
      { title: "失败", value: "failed" },
      { title: "已取消", value: "cancelled" },
      { title: "已中断", value: "interrupted" },
      { title: "已替代", value: "superseded" }
    ];
    const groupingOptions = [
      { title: "不分组", value: "none" },
      { title: "按目录", value: "directory" },
      { title: "按日期", value: "date" },
      { title: "目录 + 日期", value: "directory_date" }
    ];
    const timeGrainOptions = [
      { title: "小时", value: "hour" },
      { title: "天", value: "day" },
      { title: "月", value: "month" }
    ];
    const formatOptions = [
      { title: "7z", value: "7z" },
      { title: "ZIP", value: "zip" }
    ];
    const compressionOptions = [
      { title: "存储（不压缩）", value: "store" },
      { title: "快速", value: "fast" },
      { title: "标准", value: "normal" },
      { title: "高压缩", value: "high" }
    ];
    const encryptionOptions = [
      { title: "不加密", value: "none" },
      { title: "AES-256", value: "aes256" }
    ];
    const notificationEventOptions = [
      { title: "归档成功", value: "success" },
      { title: "归档失败", value: "failure" },
      { title: "其他", value: "other" }
    ];
    function setNotice(text, type = "info") {
      const notify = hostToast?.[type] ?? hostToast?.info ?? (typeof hostToast === "function" ? hostToast : void 0);
      if (notify) {
        try {
          void notify(text);
          notice.value = null;
          return;
        } catch {
        }
      }
      notice.value = { text, type };
    }
    function ensureSelection() {
      if (!draft.value.tasks.some((task) => task.id === activeTaskId.value))
        activeTaskId.value = draft.value.tasks[0]?.id ?? "";
      if (!draft.value.tasks.some((task) => task.id === batchTaskFilter.value)) batchTaskFilter.value = activeTaskId.value;
      if (!draft.value.tasks.some((task) => task.id === fileTaskFilter.value)) fileTaskFilter.value = activeTaskId.value;
    }
    function selectTask(taskId) {
      activeTaskId.value = taskId;
      batchTaskFilter.value = taskId;
      fileTaskFilter.value = taskId;
    }
    function selectMobileView(view) {
      activeView.value = view;
      mobileNavOpen.value = false;
    }
    function openTaskEditor(task) {
      const next = cloneTask(task ?? createArchiveTask());
      taskEditor.value = next;
      editingTaskId.value = task?.id ?? null;
      includePatternsText.value = next.include_patterns.join("\n");
      excludePatternsText.value = next.exclude_patterns.join("\n");
      minFreeGiB.value = Number((next.min_free_bytes / 1024 ** 3).toFixed(2));
      editorOpen.value = true;
    }
    function parsePatterns(value) {
      return value.split(/\r?\n|,/).map((pattern) => pattern.trim()).filter(Boolean);
    }
    function prepareEditorTask() {
      const task = cloneTask(taskEditor.value);
      task.include_patterns = parsePatterns(includePatternsText.value);
      task.exclude_patterns = parsePatterns(excludePatternsText.value);
      task.min_free_bytes = Math.max(0, Number(minFreeGiB.value) || 0) * 1024 ** 3;
      if (task.delete_source) task.verify = true;
      if (task.format === "zip") task.encrypt_names = false;
      if (task.password.length > 0) task.password_set = true;
      return task;
    }
    function saveTaskEditor() {
      const task = prepareEditorTask();
      const index = draft.value.tasks.findIndex((item) => item.id === task.id);
      if (index >= 0) draft.value.tasks.splice(index, 1, task);
      else draft.value.tasks.push(task);
      selectTask(task.id);
      editorOpen.value = false;
      setNotice("任务已更新，保存配置后才会生效。", "success");
    }
    function cancelTaskEditor() {
      editorOpen.value = false;
    }
    async function removeTask(task) {
      let confirmed = false;
      if (hostConfirm) {
        try {
          confirmed = await hostConfirm({
            type: "error",
            title: "删除归档任务",
            content: `确定删除任务“${task.name}”吗？保存后该任务将不再执行。`,
            confirmText: "删除任务",
            cancelText: "取消"
          });
        } catch {
          confirmed = false;
        }
      }
      if (!confirmed) return;
      draft.value.tasks = draft.value.tasks.filter((item) => item.id !== task.id);
      ensureSelection();
      setNotice("任务已从配置草稿移除。", "success");
    }
    function handleDeleteSource(value) {
      taskEditor.value.delete_source = value === true;
      if (taskEditor.value.delete_source) {
        taskEditor.value.verify = true;
        setNotice("删除源文件已启用，归档校验已强制开启。", "warning");
      }
    }
    function handleVerify(value) {
      if (taskEditor.value.delete_source && value !== true) {
        taskEditor.value.verify = true;
        setNotice("删除源文件必须启用归档校验。", "warning");
        return;
      }
      taskEditor.value.verify = value === true;
    }
    function requestFormat(value) {
      const format = value === "zip" ? "zip" : "7z";
      if (format === "zip" && taskEditor.value.encrypt_names) {
        pendingFormat.value = format;
        compatibilityReason.value = "format";
        compatibilityOpen.value = true;
        return;
      }
      taskEditor.value.format = format;
    }
    function requestEncryptNames(value) {
      if (value === true && taskEditor.value.format === "zip") {
        compatibilityReason.value = "encrypt_names";
        pendingFormat.value = null;
        compatibilityOpen.value = true;
        return;
      }
      taskEditor.value.encrypt_names = value === true;
    }
    function acceptCompatibilityChange() {
      if (compatibilityReason.value === "format" && pendingFormat.value) {
        taskEditor.value.format = pendingFormat.value;
        taskEditor.value.encrypt_names = false;
      } else {
        taskEditor.value.format = "7z";
        taskEditor.value.encrypt_names = true;
      }
      compatibilityOpen.value = false;
      pendingFormat.value = null;
    }
    function cancelCompatibilityChange() {
      compatibilityOpen.value = false;
      pendingFormat.value = null;
    }
    function handleEncryption(value) {
      taskEditor.value.encryption = value === "aes256" ? "aes256" : "none";
      if (taskEditor.value.encryption === "aes256" && taskEditor.value.format === "7z" && !taskEditor.value.encrypt_names) {
        taskEditor.value.encrypt_names = true;
      }
    }
    function saveConfig() {
      const payload = normalizeArchiveConfig(draft.value);
      draft.value = payload;
      original.value = normalizeArchiveConfig(payload);
      emit("save", normalizeArchiveConfig(payload));
      setNotice("配置已提交给宿主保存。", "success");
    }
    function formatNumber(value) {
      return new Intl.NumberFormat(locale.value.startsWith("en") ? "en-US" : "zh-CN").format(value || 0);
    }
    function formatBytes(value) {
      if (!Number.isFinite(value) || value <= 0) return "0 B";
      const units = ["B", "KB", "MB", "GB", "TB"];
      const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
      return `${(value / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
    }
    function formatDate(value) {
      if (!value) return "-";
      const timestamp = new Date(value);
      return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString(locale.value.startsWith("en") ? "en-US" : "zh-CN");
    }
    function statusLabel(status) {
      const normalized = status || "pending";
      return batchStatusOptions.find((item) => item.value === normalized)?.title ?? ({
        pending: "待处理",
        archived: "已归档",
        retained: "已归档，源文件保留",
        deleting: "清理中",
        deleted: "已删除源文件",
        failed: "失败",
        missing: "源文件已缺失",
        changed: "源文件已变化",
        superseded: "已替代"
      }[normalized] || normalized);
    }
    function statusColor(status) {
      const normalized = status || "pending";
      if (["completed", "archived", "retained", "deleted"].includes(normalized)) return "success";
      if (["failed", "cleanup_failed", "missing", "changed"].includes(normalized)) return "error";
      if (["cancelled", "interrupted", "superseded"].includes(normalized)) return "warning";
      return "primary";
    }
    function batchFileStatus(file, batch) {
      const recordedStatus = file.status || batch.cleanup?.[file.relative_path];
      if (recordedStatus) return recordedStatus;
      if (batch.status === "completed") return "archived";
      return batch.status || "pending";
    }
    function phaseLabel(phase) {
      return {
        history: "历史队列",
        incremental: "新增文件",
        waiting_capacity: "等待空间",
        waiting_retry: "等待重试",
        idle: "空闲",
        stopped: "已停止"
      }[phase] || phase;
    }
    function progressLabel(progress) {
      if (progress.phase === "history") {
        return `历史 ${formatNumber(progress.history_archived)} / ${formatNumber(progress.history_total)}，剩余 ${formatNumber(progress.history_remaining)}`;
      }
      if (progress.phase === "waiting_capacity") return progress.reason || "等待外部工具移走归档成品";
      if (progress.phase === "waiting_retry") return progress.reason || "存在失败批次，等待重试后继续";
      return progress.reason || `积压 ${formatNumber(progress.pending_archives)} 批 · ${formatBytes(progress.pending_bytes)}`;
    }
    async function refreshSummary() {
      const requestToken = ++summaryRequestToken;
      const payload = await loadSummary(props.api);
      if (disposed || requestToken !== summaryRequestToken) return;
      summary.value = payload;
      summaryState.value = payload ? "available" : "unavailable";
    }
    function clearOperationPolling() {
      if (operationTimer) clearInterval(operationTimer);
      operationTimer = void 0;
      operationBusy.value = false;
      operationMessage.value = "";
    }
    function startOperationPolling() {
      clearOperationPolling();
      operationBusy.value = true;
      let attempts = 0;
      operationTimer = setInterval(() => {
        attempts += 1;
        void refreshSummary();
        if (activeView.value === "batches") void loadBatchPage();
        if (attempts >= 40 || !summary.value?.running && (summary.value?.queued.length ?? 0) === 0)
          clearOperationPolling();
      }, 2500);
    }
    async function executeRun(taskId = activeTaskId.value) {
      if (!taskId) {
        setNotice("请先选择一个归档任务。", "warning");
        return;
      }
      operationMessage.value = "正在提交归档任务…";
      const result = await runTask(props.api, taskId);
      if (!result) {
        setNotice("归档任务提交失败，请检查插件状态。", "error");
        operationMessage.value = "";
        return;
      }
      setNotice(result.queued ? "归档任务已加入队列。" : "归档任务已启动。", "success");
      operationMessage.value = "归档任务运行中…";
      await refreshSummary();
      startOperationPolling();
    }
    async function executeStop() {
      operationMessage.value = "正在请求停止…";
      const result = await stopTask(props.api, summary.value?.running?.task_id);
      if (!result) {
        setNotice("停止请求失败，请稍后重试。", "error");
        operationMessage.value = "";
        return;
      }
      setNotice("已发送停止请求，正在等待运行状态收敛。", "warning");
      await refreshSummary();
      startOperationPolling();
    }
    async function executeBatchAction(action, batch) {
      operationMessage.value = action === "retry" ? "正在重新构建批次…" : "正在补全清单…";
      const result = action === "retry" ? await retryBatch(props.api, batch.id) : await repairBatch(props.api, batch.id);
      if (!result) {
        setNotice(action === "retry" ? "批次重试失败。" : "清单补全失败。", "error");
        operationMessage.value = "";
        return;
      }
      setNotice(action === "retry" ? "批次已加入重试队列。" : "清单补全已加入队列。", "success");
      batchDialogOpen.value = false;
      await refreshSummary();
      startOperationPolling();
    }
    async function startPreviewForTask(task) {
      previewOpen.value = true;
      previewState.value = "running";
      previewResult.value = null;
      previewMessage.value = "正在扫描源目录…";
      const result = await startPreview(props.api, task);
      if (!result?.job_id) {
        previewState.value = "failed";
        previewMessage.value = "预览任务提交失败，请检查目录和插件状态。";
        return;
      }
      previewJobId.value = result.job_id;
      await pollPreviewJob(result.job_id);
    }
    async function pollPreviewJob(jobId) {
      const startedAt = Date.now();
      const poll = async () => {
        if (disposed || !previewOpen.value || Date.now() - startedAt > 12e4) {
          if (!disposed && previewState.value === "running") {
            previewState.value = "failed";
            previewMessage.value = "预览等待超时，请稍后重试。";
          }
          return;
        }
        const result = await pollPreview(props.api, jobId);
        if (result?.status === "complete") {
          previewState.value = "complete";
          previewResult.value = result.data;
          previewMessage.value = result.message || "预览完成。";
          return;
        }
        if (result?.status === "failed") {
          previewState.value = "failed";
          previewMessage.value = result.message || "预览失败。";
          return;
        }
        previewMessage.value = result?.message || "正在扫描源目录…";
        previewTimer = setTimeout(() => void poll(), 1200);
      };
      await poll();
    }
    async function loadBatchPage() {
      const requestToken = ++batchRequestToken;
      batchLoading.value = true;
      try {
        const result = await listBatches(props.api, {
          task_id: batchTaskFilter.value || void 0,
          page: batchPage.value,
          page_size: batchPageSize.value,
          status: batchStatusFilter.value || void 0
        });
        if (!disposed && requestToken === batchRequestToken && activeView.value === "batches") batchData.value = result;
      } finally {
        if (requestToken === batchRequestToken) batchLoading.value = false;
      }
    }
    async function openBatch(batch) {
      batchDialogOpen.value = true;
      selectedBatch.value = batch;
      batchDetailLoading.value = true;
      selectedBatch.value = await loadBatch(props.api, batch.id) ?? batch;
      batchDetailLoading.value = false;
    }
    async function loadFilePage() {
      const requestToken = ++fileRequestToken;
      if (!hasFileTaskSelection.value) {
        fileData.value = { items: [], directories: [], total: 0 };
        fileLoading.value = false;
        return;
      }
      fileLoading.value = true;
      try {
        const result = await listFiles(props.api, {
          task_id: fileTaskFilter.value || void 0,
          directory: fileDirectory.value,
          query: fileQuery.value.trim() || void 0,
          status: fileStatus.value || void 0,
          page: filePage.value,
          page_size: filePageSize.value
        });
        if (!disposed && requestToken === fileRequestToken && activeView.value === "files") fileData.value = result;
      } finally {
        if (requestToken === fileRequestToken) fileLoading.value = false;
      }
    }
    function submitFileSearch() {
      if (filePage.value !== 1) {
        filePage.value = 1;
        return;
      }
      void loadFilePage();
    }
    function navigateDirectory(path) {
      fileDirectory.value = path;
      filePage.value = 1;
    }
    function closePreview() {
      previewOpen.value = false;
      if (previewTimer) clearTimeout(previewTimer);
      previewTimer = void 0;
    }
    watch(
      () => props.initialConfig,
      (value) => {
        const normalized = normalizeArchiveConfig(value);
        draft.value = normalized;
        original.value = normalizeArchiveConfig(normalized);
        ensureSelection();
      },
      { deep: true }
    );
    watch([activeView, batchTaskFilter, batchStatusFilter, batchPage, batchPageSize], ([view]) => {
      if (view === "batches") void loadBatchPage();
    });
    watch([activeView, fileTaskFilter, fileDirectory, fileStatus, filePage, filePageSize], ([view]) => {
      if (view === "files") void loadFilePage();
    });
    watch(
      () => draft.value.tasks.map((task) => task.id),
      () => ensureSelection()
    );
    onMounted(() => {
      void refreshSummary();
    });
    onBeforeUnmount(() => {
      disposed = true;
      if (previewTimer) clearTimeout(previewTimer);
      clearOperationPolling();
    });
    return (_ctx, _cache) => {
      const _component_VIcon = _resolveComponent("VIcon");
      const _component_VChip = _resolveComponent("VChip");
      const _component_VBtn = _resolveComponent("VBtn");
      const _component_VAlert = _resolveComponent("VAlert");
      const _component_VListItem = _resolveComponent("VListItem");
      const _component_VList = _resolveComponent("VList");
      const _component_VTooltip = _resolveComponent("VTooltip");
      const _component_VProgressCircular = _resolveComponent("VProgressCircular");
      const _component_VSwitch = _resolveComponent("VSwitch");
      const _component_VSelect = _resolveComponent("VSelect");
      const _component_VTextField = _resolveComponent("VTextField");
      const _component_VTextarea = _resolveComponent("VTextarea");
      const _component_VSpacer = _resolveComponent("VSpacer");
      const _component_VPagination = _resolveComponent("VPagination");
      const _component_VCardTitle = _resolveComponent("VCardTitle");
      const _component_VCard = _resolveComponent("VCard");
      const _component_VBottomSheet = _resolveComponent("VBottomSheet");
      const _component_VCardText = _resolveComponent("VCardText");
      const _component_VCardActions = _resolveComponent("VCardActions");
      const _component_VDialog = _resolveComponent("VDialog");
      return _openBlock(), _createElementBlock("section", _hoisted_1, [
        _createElementVNode("form", {
          onSubmit: _withModifiers(saveConfig, ["prevent"])
        }, [
          _createElementVNode("header", _hoisted_2, [
            _createElementVNode("div", _hoisted_3, [
              _createElementVNode("img", {
                src: _unref(archiveLogo),
                alt: "",
                class: "archive-header__logo"
              }, null, 8, _hoisted_4),
              _createElementVNode("div", _hoisted_5, [
                _createElementVNode("div", _hoisted_6, [
                  _cache[58] || (_cache[58] = _createElementVNode("span", null, "MoviePilot", -1)),
                  _createVNode(_component_VIcon, {
                    icon: "mdi-chevron-right",
                    size: "14"
                  }),
                  _cache[59] || (_cache[59] = _createElementVNode("span", null, "插件", -1))
                ]),
                _createElementVNode("div", _hoisted_7, [
                  _cache[61] || (_cache[61] = _createElementVNode("h1", null, "压缩归档", -1)),
                  _createVNode(_component_VChip, {
                    color: "primary",
                    size: "x-small",
                    variant: "tonal"
                  }, {
                    default: _withCtx(() => _cache[60] || (_cache[60] = [
                      _createTextVNode("BETA")
                    ])),
                    _: 1
                  })
                ])
              ])
            ]),
            _createElementVNode("div", _hoisted_8, [
              _createVNode(_component_VBtn, {
                class: "archive-header__run",
                disabled: !activeTaskId.value || operationBusy.value,
                "prepend-icon": "mdi-play",
                type: "button",
                variant: "tonal",
                onClick: _cache[0] || (_cache[0] = ($event) => executeRun())
              }, {
                default: _withCtx(() => _cache[62] || (_cache[62] = [
                  _createTextVNode(" 运行一次 ")
                ])),
                _: 1
              }, 8, ["disabled"]),
              _createVNode(_component_VBtn, {
                class: "archive-header__save",
                color: "primary",
                disabled: !isDirty.value,
                "prepend-icon": "mdi-content-save",
                type: "submit"
              }, {
                default: _withCtx(() => _cache[63] || (_cache[63] = [
                  _createTextVNode(" 保存修改 ")
                ])),
                _: 1
              }, 8, ["disabled"]),
              _createVNode(_component_VBtn, {
                class: "archive-header__close-action",
                "prepend-icon": "mdi-close",
                variant: "outlined",
                onClick: _cache[1] || (_cache[1] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => _cache[64] || (_cache[64] = [
                  _createTextVNode(" 关闭 ")
                ])),
                _: 1
              }),
              _createVNode(_component_VBtn, {
                "aria-label": "关闭",
                class: "archive-header__close-icon",
                icon: "",
                size: "small",
                variant: "text",
                onClick: _cache[2] || (_cache[2] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_VIcon, { icon: "mdi-close" })
                ]),
                _: 1
              })
            ])
          ]),
          _createElementVNode("div", _hoisted_9, [
            notice.value ? (_openBlock(), _createBlock(_component_VAlert, {
              key: 0,
              type: notice.value.type,
              closable: "",
              density: "compact",
              variant: "tonal",
              "onClick:close": _cache[3] || (_cache[3] = ($event) => notice.value = null)
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(notice.value.text), 1)
              ]),
              _: 1
            }, 8, ["type"])) : _createCommentVNode("", true),
            summaryValue.value.config_error ? (_openBlock(), _createBlock(_component_VAlert, {
              key: 1,
              class: "archive-alert",
              type: "error",
              variant: "tonal"
            }, {
              default: _withCtx(() => [
                _cache[65] || (_cache[65] = _createElementVNode("strong", null, "配置不可运行", -1)),
                _createElementVNode("span", null, _toDisplayString(summaryValue.value.config_error), 1)
              ]),
              _: 1
            })) : _createCommentVNode("", true),
            lastErrorMessage.value ? (_openBlock(), _createBlock(_component_VAlert, {
              key: 2,
              class: "archive-alert",
              type: "warning",
              variant: "tonal"
            }, {
              default: _withCtx(() => [
                _cache[66] || (_cache[66] = _createElementVNode("strong", null, "最近一次运行失败", -1)),
                _createElementVNode("span", null, _toDisplayString(lastErrorMessage.value), 1)
              ]),
              _: 1
            })) : _createCommentVNode("", true),
            _createElementVNode("div", _hoisted_10, [
              _createElementVNode("aside", _hoisted_11, [
                _cache[70] || (_cache[70] = _createElementVNode("div", { class: "archive-nav__heading" }, "工作区", -1)),
                _createVNode(_component_VList, {
                  class: "archive-nav__list",
                  density: "compact",
                  nav: ""
                }, {
                  default: _withCtx(() => [
                    (_openBlock(), _createElementBlock(_Fragment, null, _renderList(viewLabels, (view, key) => {
                      return _createVNode(_component_VListItem, {
                        key,
                        active: activeView.value === key,
                        "prepend-icon": view.icon,
                        title: view.title,
                        color: "primary",
                        rounded: "lg",
                        onClick: ($event) => activeView.value = key
                      }, null, 8, ["active", "prepend-icon", "title", "onClick"]);
                    }), 64))
                  ]),
                  _: 1
                }),
                _createElementVNode("section", _hoisted_12, [
                  _cache[68] || (_cache[68] = _createElementVNode("strong", { class: "archive-nav__help-title" }, "关于插件", -1)),
                  _cache[69] || (_cache[69] = _createElementVNode("p", null, "文件压缩归档，支持独立清单、校验和可选加密。", -1)),
                  _createVNode(_component_VBtn, {
                    href: README_URL,
                    "append-icon": "mdi-open-in-new",
                    class: "archive-nav__help-link",
                    color: "primary",
                    rel: "noopener noreferrer",
                    size: "small",
                    target: "_blank",
                    variant: "text"
                  }, {
                    default: _withCtx(() => _cache[67] || (_cache[67] = [
                      _createTextVNode(" 查看文档 ")
                    ])),
                    _: 1
                  })
                ])
              ]),
              _createElementVNode("main", _hoisted_13, [
                _createElementVNode("div", _hoisted_14, [
                  _createElementVNode("div", null, [
                    _createElementVNode("div", _hoisted_15, [
                      _createVNode(_component_VIcon, {
                        icon: viewLabels[activeView.value].icon,
                        color: "primary",
                        size: "21"
                      }, null, 8, ["icon"]),
                      _createElementVNode("h2", null, _toDisplayString(viewLabels[activeView.value].title), 1)
                    ]),
                    _createElementVNode("p", null, _toDisplayString(viewLabels[activeView.value].summary), 1)
                  ]),
                  _createElementVNode("div", _hoisted_16, [
                    _createVNode(_component_VBtn, {
                      "aria-label": "切换工作区",
                      class: "archive-mobile-nav",
                      icon: "",
                      size: "small",
                      variant: "tonal",
                      onClick: _cache[4] || (_cache[4] = ($event) => mobileNavOpen.value = true)
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VIcon, { icon: "mdi-view-list-outline" }),
                        _createVNode(_component_VTooltip, {
                          activator: "parent",
                          text: "切换工作区"
                        })
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_VBtn, {
                      "aria-label": "刷新当前数据",
                      icon: "",
                      size: "small",
                      variant: "text",
                      onClick: _cache[5] || (_cache[5] = ($event) => activeView.value === "batches" ? loadBatchPage() : activeView.value === "files" ? loadFilePage() : refreshSummary())
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VIcon, { icon: "mdi-refresh" }),
                        _createVNode(_component_VTooltip, {
                          activator: "parent",
                          text: "刷新当前数据"
                        })
                      ]),
                      _: 1
                    })
                  ])
                ]),
                activeView.value === "overview" || activeView.value === "tasks" ? (_openBlock(), _createElementBlock("section", _hoisted_17, [
                  activeView.value === "overview" ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                    _createElementVNode("div", _hoisted_18, [
                      _createElementVNode("div", _hoisted_19, [
                        _createVNode(_component_VIcon, { icon: "mdi-file-check-outline" }),
                        _cache[71] || (_cache[71] = _createElementVNode("span", null, "已归档文件", -1)),
                        _createElementVNode("strong", null, _toDisplayString(formatNumber(summaryValue.value.archived_files)), 1)
                      ]),
                      _createElementVNode("div", _hoisted_20, [
                        _createVNode(_component_VIcon, { icon: "mdi-package-variant-closed" }),
                        _cache[72] || (_cache[72] = _createElementVNode("span", null, "归档批次", -1)),
                        _createElementVNode("strong", null, _toDisplayString(formatNumber(summaryValue.value.archive_count)), 1)
                      ]),
                      _createElementVNode("div", _hoisted_21, [
                        _createVNode(_component_VIcon, { icon: "mdi-database-arrow-down-outline" }),
                        _cache[73] || (_cache[73] = _createElementVNode("span", null, "源文件体积", -1)),
                        _createElementVNode("strong", null, _toDisplayString(formatBytes(summaryValue.value.source_bytes)), 1)
                      ]),
                      _createElementVNode("div", _hoisted_22, [
                        _createVNode(_component_VIcon, { icon: "mdi-archive-arrow-down-outline" }),
                        _cache[74] || (_cache[74] = _createElementVNode("span", null, "归档体积", -1)),
                        _createElementVNode("strong", null, _toDisplayString(formatBytes(summaryValue.value.archive_bytes)), 1)
                      ]),
                      _createElementVNode("div", _hoisted_23, [
                        _createVNode(_component_VIcon, { icon: "mdi-delete-outline" }),
                        _cache[75] || (_cache[75] = _createElementVNode("span", null, "已删除源文件", -1)),
                        _createElementVNode("strong", null, _toDisplayString(formatNumber(summaryValue.value.deleted_files)), 1)
                      ]),
                      _createElementVNode("div", {
                        class: _normalizeClass(["archive-metric", { "archive-metric--warning": summaryValue.value.failed_batches > 0 }])
                      }, [
                        _createVNode(_component_VIcon, { icon: "mdi-alert-circle-outline" }),
                        _cache[76] || (_cache[76] = _createElementVNode("span", null, "失败批次", -1)),
                        _createElementVNode("strong", null, _toDisplayString(formatNumber(summaryValue.value.failed_batches)), 1)
                      ], 2)
                    ]),
                    summaryState.value === "loading" ? (_openBlock(), _createElementBlock("div", _hoisted_24, [
                      _createVNode(_component_VProgressCircular, {
                        color: "primary",
                        indeterminate: "",
                        size: "18",
                        width: "2"
                      }),
                      _cache[77] || (_cache[77] = _createTextVNode(" 正在读取运行概况… "))
                    ])) : summaryState.value === "unavailable" ? (_openBlock(), _createElementBlock("div", _hoisted_25, [
                      _createVNode(_component_VIcon, { icon: "mdi-cloud-alert-outline" }),
                      _cache[78] || (_cache[78] = _createTextVNode("运行概况暂不可用，配置编辑仍可继续。 "))
                    ])) : _createCommentVNode("", true),
                    summaryValue.value.running || queuedTaskNames.value.length ? (_openBlock(), _createElementBlock("div", _hoisted_26, [
                      _createElementVNode("div", _hoisted_27, [
                        _createVNode(_component_VProgressCircular, {
                          color: "primary",
                          indeterminate: "",
                          size: "20",
                          width: "2"
                        }),
                        _createElementVNode("div", null, [
                          _createElementVNode("strong", null, _toDisplayString(operationMessage.value || "归档任务正在运行"), 1),
                          summaryValue.value.running ? (_openBlock(), _createElementBlock("span", _hoisted_28, _toDisplayString(tasksById.value.get(summaryValue.value.running.task_id)?.name || summaryValue.value.running.task_id) + " · " + _toDisplayString(summaryValue.value.running.phase), 1)) : (_openBlock(), _createElementBlock("span", _hoisted_29, "排队任务：" + _toDisplayString(queuedTaskNames.value.join("、")), 1))
                        ])
                      ]),
                      _createVNode(_component_VBtn, {
                        color: "warning",
                        disabled: !summaryValue.value.running,
                        "prepend-icon": "mdi-stop",
                        variant: "tonal",
                        onClick: executeStop
                      }, {
                        default: _withCtx(() => _cache[79] || (_cache[79] = [
                          _createTextVNode("停止")
                        ])),
                        _: 1
                      }, 8, ["disabled"])
                    ])) : _createCommentVNode("", true),
                    summaryValue.value.tasks.length ? (_openBlock(), _createElementBlock("section", _hoisted_30, [
                      _createElementVNode("div", _hoisted_31, [
                        _cache[80] || (_cache[80] = _createElementVNode("div", null, [
                          _createElementVNode("h3", null, "任务队列进度"),
                          _createElementVNode("p", null, "历史快照优先完成；空间不足时等待外部工具移走已发布成品。")
                        ], -1)),
                        _createVNode(_component_VChip, {
                          color: "primary",
                          size: "small",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(summaryValue.value.tasks.filter((task) => task.active).length) + " 个活动任务", 1)
                          ]),
                          _: 1
                        })
                      ]),
                      _createElementVNode("div", _hoisted_32, [
                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(summaryValue.value.tasks, (progress) => {
                          return _openBlock(), _createElementBlock("div", {
                            key: progress.task_id,
                            class: "archive-progress__row"
                          }, [
                            _createElementVNode("div", _hoisted_33, [
                              _createVNode(_component_VIcon, {
                                color: progress.active ? "primary" : "disabled",
                                icon: progress.active ? "mdi-progress-clock" : "mdi-check-circle-outline"
                              }, null, 8, ["color", "icon"]),
                              _createElementVNode("strong", null, _toDisplayString(tasksById.value.get(progress.task_id)?.name || progress.task_id), 1)
                            ]),
                            _createVNode(_component_VChip, {
                              color: progress.phase === "waiting_capacity" || progress.phase === "waiting_retry" ? "warning" : progress.active ? "primary" : "default",
                              size: "small",
                              variant: "tonal"
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(phaseLabel(progress.phase)), 1)
                              ]),
                              _: 2
                            }, 1032, ["color"]),
                            _createElementVNode("span", _hoisted_34, _toDisplayString(progressLabel(progress)), 1),
                            _createElementVNode("span", _hoisted_35, [
                              _createTextVNode("积压 " + _toDisplayString(formatNumber(progress.pending_archives)) + " 批 · " + _toDisplayString(formatBytes(progress.pending_bytes)), 1),
                              _cache[81] || (_cache[81] = _createElementVNode("br", null, null, -1)),
                              _createTextVNode("可用空间 " + _toDisplayString(formatBytes(progress.free_bytes)), 1)
                            ])
                          ]);
                        }), 128))
                      ])
                    ])) : _createCommentVNode("", true),
                    _createElementVNode("section", _hoisted_36, [
                      _cache[82] || (_cache[82] = _createElementVNode("div", { class: "archive-section__header" }, [
                        _createElementVNode("div", null, [
                          _createElementVNode("h3", null, "运行设置"),
                          _createElementVNode("p", null, "控制归档服务是否启用，以及哪些事件发送宿主通知。")
                        ])
                      ], -1)),
                      _createElementVNode("div", _hoisted_37, [
                        _createVNode(_component_VSwitch, {
                          modelValue: draft.value.enabled,
                          "onUpdate:modelValue": _cache[6] || (_cache[6] = ($event) => draft.value.enabled = $event),
                          "aria-label": "启用",
                          color: "primary",
                          density: "compact",
                          "hide-details": "",
                          label: "启用"
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_VSwitch, {
                          modelValue: draft.value.notify,
                          "onUpdate:modelValue": _cache[7] || (_cache[7] = ($event) => draft.value.notify = $event),
                          "aria-label": "发送通知",
                          color: "primary",
                          density: "compact",
                          "hide-details": "",
                          label: "发送通知"
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_VSelect, {
                          "aria-label": "通知事件",
                          modelValue: draft.value.notify_events,
                          "onUpdate:modelValue": _cache[8] || (_cache[8] = ($event) => draft.value.notify_events = $event),
                          items: notificationEventOptions,
                          chips: "",
                          "closable-chips": "",
                          "hide-details": "",
                          "item-title": "title",
                          "item-value": "value",
                          label: "通知事件",
                          multiple: "",
                          variant: "outlined"
                        }, null, 8, ["modelValue"])
                      ])
                    ])
                  ], 64)) : _createCommentVNode("", true),
                  activeView.value === "tasks" ? (_openBlock(), _createElementBlock("div", {
                    key: 1,
                    class: _normalizeClass(["archive-task-layout", { "archive-task-layout--editing": editorOpen.value }])
                  }, [
                    !editorOpen.value ? (_openBlock(), _createElementBlock("section", _hoisted_38, [
                      _createElementVNode("div", _hoisted_39, [
                        _createElementVNode("div", null, [
                          _cache[83] || (_cache[83] = _createElementVNode("h3", null, "归档任务", -1)),
                          _createElementVNode("p", null, _toDisplayString(draft.value.tasks.length) + " 个任务，点击任务查看详情。", 1)
                        ]),
                        _createVNode(_component_VBtn, {
                          "aria-label": "新增归档任务",
                          icon: "",
                          size: "small",
                          variant: "tonal",
                          onClick: _cache[9] || (_cache[9] = ($event) => openTaskEditor())
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VIcon, { icon: "mdi-plus" })
                          ]),
                          _: 1
                        })
                      ]),
                      draft.value.tasks.length === 0 ? (_openBlock(), _createElementBlock("div", _hoisted_40, [
                        _createVNode(_component_VIcon, {
                          icon: "mdi-archive-off-outline",
                          size: "34"
                        }),
                        _cache[85] || (_cache[85] = _createElementVNode("strong", null, "还没有归档任务", -1)),
                        _cache[86] || (_cache[86] = _createElementVNode("span", null, "创建任务后可预览文件并手动运行。", -1)),
                        _createVNode(_component_VBtn, {
                          color: "primary",
                          "prepend-icon": "mdi-plus",
                          variant: "tonal",
                          onClick: _cache[10] || (_cache[10] = ($event) => openTaskEditor())
                        }, {
                          default: _withCtx(() => _cache[84] || (_cache[84] = [
                            _createTextVNode("创建第一个任务")
                          ])),
                          _: 1
                        })
                      ])) : (_openBlock(), _createBlock(_component_VList, {
                        key: 1,
                        class: "archive-task-list__items",
                        lines: "two",
                        nav: ""
                      }, {
                        default: _withCtx(() => [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(draft.value.tasks, (task) => {
                            return _openBlock(), _createBlock(_component_VListItem, {
                              key: task.id,
                              active: activeTaskId.value === task.id,
                              title: task.name || "未命名任务",
                              subtitle: `${task.source_dir || "未设置源目录"} · ${task.format.toUpperCase()}`,
                              color: "primary",
                              rounded: "lg",
                              onClick: ($event) => selectTask(task.id)
                            }, {
                              prepend: _withCtx(() => [
                                _createVNode(_component_VIcon, {
                                  color: task.enabled ? "success" : "disabled",
                                  icon: task.enabled ? "mdi-check-circle-outline" : "mdi-pause-circle-outline"
                                }, null, 8, ["color", "icon"])
                              ]),
                              append: _withCtx(() => [
                                _createVNode(_component_VChip, {
                                  color: task.enabled ? "success" : "default",
                                  size: "x-small",
                                  variant: "tonal"
                                }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(task.enabled ? "启用" : "停用"), 1)
                                  ]),
                                  _: 2
                                }, 1032, ["color"])
                              ]),
                              _: 2
                            }, 1032, ["active", "title", "subtitle", "onClick"]);
                          }), 128))
                        ]),
                        _: 1
                      }))
                    ])) : _createCommentVNode("", true),
                    selectedTask.value && !editorOpen.value ? (_openBlock(), _createElementBlock("section", _hoisted_41, [
                      _createElementVNode("div", _hoisted_42, [
                        _createElementVNode("div", null, [
                          _createElementVNode("h3", null, _toDisplayString(selectedTask.value.name), 1),
                          _createElementVNode("p", null, _toDisplayString(selectedTask.value.source_dir || "尚未设置源目录"), 1)
                        ]),
                        _createElementVNode("div", _hoisted_43, [
                          _createVNode(_component_VBtn, {
                            "aria-label": "编辑归档任务",
                            color: "primary",
                            icon: "",
                            size: "small",
                            variant: "tonal",
                            onClick: _cache[11] || (_cache[11] = ($event) => openTaskEditor(selectedTask.value))
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_VIcon, { icon: "mdi-pencil-outline" }),
                              _createVNode(_component_VTooltip, {
                                activator: "parent",
                                text: "编辑任务"
                              })
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_VBtn, {
                            "aria-label": "删除归档任务",
                            color: "error",
                            icon: "",
                            size: "small",
                            variant: "text",
                            onClick: _cache[12] || (_cache[12] = ($event) => removeTask(selectedTask.value))
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_VIcon, { icon: "mdi-delete-outline" }),
                              _createVNode(_component_VTooltip, {
                                activator: "parent",
                                text: "删除任务"
                              })
                            ]),
                            _: 1
                          })
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_44, [
                        _createElementVNode("div", null, [
                          _cache[87] || (_cache[87] = _createElementVNode("span", null, "调度", -1)),
                          _createElementVNode("strong", null, _toDisplayString(selectedTask.value.cron), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[88] || (_cache[88] = _createElementVNode("span", null, "输出目录", -1)),
                          _createElementVNode("strong", null, _toDisplayString(selectedTask.value.output_dir || "-"), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[89] || (_cache[89] = _createElementVNode("span", null, "清单目录", -1)),
                          _createElementVNode("strong", null, _toDisplayString(selectedTask.value.manifest_dir || "与归档目录相同"), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[90] || (_cache[90] = _createElementVNode("span", null, "分组方式", -1)),
                          _createElementVNode("strong", null, _toDisplayString(groupingOptions.find((item) => item.value === selectedTask.value.grouping)?.title), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[91] || (_cache[91] = _createElementVNode("span", null, "文件限制", -1)),
                          _createElementVNode("strong", null, _toDisplayString(selectedTask.value.max_files ? `${formatNumber(selectedTask.value.max_files)} 个` : "不限数量") + " · " + _toDisplayString(selectedTask.value.max_bytes ? formatBytes(selectedTask.value.max_bytes) : "不限体积"), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[92] || (_cache[92] = _createElementVNode("span", null, "归档策略", -1)),
                          _createElementVNode("strong", null, _toDisplayString(selectedTask.value.format.toUpperCase()) + " · " + _toDisplayString(selectedTask.value.encryption === "aes256" ? "AES-256" : "不加密"), 1)
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_45, [
                        _createVNode(_component_VChip, {
                          size: "small",
                          color: selectedTask.value.verify ? "success" : "warning",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode("校验 " + _toDisplayString(selectedTask.value.verify ? "开启" : "关闭"), 1)
                          ]),
                          _: 1
                        }, 8, ["color"]),
                        _createVNode(_component_VChip, {
                          size: "small",
                          color: selectedTask.value.delete_source ? "error" : "default",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode("源文件 " + _toDisplayString(selectedTask.value.delete_source ? "归档后删除" : "保留"), 1)
                          ]),
                          _: 1
                        }, 8, ["color"]),
                        selectedTask.value.password_set ? (_openBlock(), _createBlock(_component_VChip, {
                          key: 0,
                          size: "small",
                          color: "primary",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => _cache[93] || (_cache[93] = [
                            _createTextVNode("密码已保存")
                          ])),
                          _: 1
                        })) : _createCommentVNode("", true)
                      ]),
                      _createElementVNode("div", _hoisted_46, [
                        _createVNode(_component_VBtn, {
                          "prepend-icon": "mdi-eye-outline",
                          variant: "tonal",
                          onClick: _cache[13] || (_cache[13] = ($event) => startPreviewForTask(selectedTask.value))
                        }, {
                          default: _withCtx(() => _cache[94] || (_cache[94] = [
                            _createTextVNode("预览文件")
                          ])),
                          _: 1
                        }),
                        _createVNode(_component_VBtn, {
                          color: "primary",
                          "prepend-icon": "mdi-play",
                          type: "button",
                          variant: "flat",
                          onClick: _cache[14] || (_cache[14] = ($event) => executeRun(selectedTask.value.id))
                        }, {
                          default: _withCtx(() => _cache[95] || (_cache[95] = [
                            _createTextVNode("运行一次")
                          ])),
                          _: 1
                        })
                      ])
                    ])) : editorOpen.value ? (_openBlock(), _createElementBlock("section", _hoisted_47, [
                      _createElementVNode("div", _hoisted_48, [
                        _createElementVNode("div", null, [
                          _createElementVNode("h3", null, _toDisplayString(taskEditorTitle.value), 1),
                          _cache[96] || (_cache[96] = _createElementVNode("p", null, "保存任务后，再点击页面顶部“保存修改”提交完整配置。", -1))
                        ]),
                        _createVNode(_component_VBtn, {
                          "aria-label": "取消编辑",
                          icon: "",
                          size: "small",
                          variant: "text",
                          onClick: cancelTaskEditor
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VIcon, { icon: "mdi-close" })
                          ]),
                          _: 1
                        })
                      ]),
                      _createElementVNode("div", _hoisted_49, [
                        _cache[97] || (_cache[97] = _createElementVNode("h4", null, "基础信息", -1)),
                        _createElementVNode("div", _hoisted_50, [
                          _createVNode(_component_VTextField, {
                            "aria-label": "任务名称",
                            modelValue: taskEditor.value.name,
                            "onUpdate:modelValue": _cache[15] || (_cache[15] = ($event) => taskEditor.value.name = $event),
                            label: "任务名称",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VSwitch, {
                            modelValue: taskEditor.value.enabled,
                            "onUpdate:modelValue": _cache[16] || (_cache[16] = ($event) => taskEditor.value.enabled = $event),
                            color: "primary",
                            density: "compact",
                            "hide-details": "",
                            label: "启用任务"
                          }, null, 8, ["modelValue"])
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_51, [
                        _cache[98] || (_cache[98] = _createElementVNode("h4", null, "目录与调度", -1)),
                        _createElementVNode("div", _hoisted_52, [
                          _createVNode(_component_VTextField, {
                            "aria-label": "源目录",
                            modelValue: taskEditor.value.source_dir,
                            "onUpdate:modelValue": _cache[17] || (_cache[17] = ($event) => taskEditor.value.source_dir = $event),
                            label: "源目录",
                            "prepend-inner-icon": "mdi-folder-open-outline",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "归档输出目录",
                            modelValue: taskEditor.value.output_dir,
                            "onUpdate:modelValue": _cache[18] || (_cache[18] = ($event) => taskEditor.value.output_dir = $event),
                            label: "归档输出目录",
                            "prepend-inner-icon": "mdi-archive-outline",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "清单目录（可选）",
                            modelValue: taskEditor.value.manifest_dir,
                            "onUpdate:modelValue": _cache[19] || (_cache[19] = ($event) => taskEditor.value.manifest_dir = $event),
                            hint: "留空时使用归档输出目录。",
                            label: "清单目录（可选）",
                            "persistent-hint": "",
                            "prepend-inner-icon": "mdi-file-document-outline",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "Cron 调度",
                            modelValue: taskEditor.value.cron,
                            "onUpdate:modelValue": _cache[20] || (_cache[20] = ($event) => taskEditor.value.cron = $event),
                            hint: "例如：0 2 * * *",
                            label: "Cron 调度",
                            "persistent-hint": "",
                            "prepend-inner-icon": "mdi-clock-outline",
                            variant: "outlined"
                          }, null, 8, ["modelValue"])
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_53, [
                        _cache[102] || (_cache[102] = _createElementVNode("h4", null, "命名规则", -1)),
                        _createElementVNode("div", _hoisted_54, [
                          _createVNode(_component_VSelect, {
                            "aria-label": "批次目录布局",
                            class: "archive-layout-select",
                            modelValue: taskEditor.value.archive_layout,
                            "onUpdate:modelValue": _cache[21] || (_cache[21] = ($event) => taskEditor.value.archive_layout = $event),
                            items: [
                              { title: "按目录（来源目录 / 批次名称）", value: "directory" },
                              { title: "扁平（来源目录_批次名称）", value: "flat" }
                            ],
                            hint: "按目录：来源目录/批次名称；扁平：来源目录_批次名称。",
                            "item-title": "title",
                            "item-value": "value",
                            label: "批次目录布局",
                            "persistent-hint": "",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "批次名称模板",
                            modelValue: taskEditor.value.batch_name_template,
                            "onUpdate:modelValue": _cache[22] || (_cache[22] = ($event) => taskEditor.value.batch_name_template = $event),
                            hint: "用于实际批次目录名，例如 20260911_0001；创建后固定，改模板只影响新批次。",
                            label: "批次名称模板",
                            "persistent-hint": "",
                            "prepend-inner-icon": "mdi-label-outline",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "归档包名称模板",
                            modelValue: taskEditor.value.archive_name_template,
                            "onUpdate:modelValue": _cache[23] || (_cache[23] = ($event) => taskEditor.value.archive_name_template = $event),
                            hint: "用于实际生成的 .7z/.zip 文件名。",
                            label: "归档包名称模板",
                            "persistent-hint": "",
                            "prepend-inner-icon": "mdi-file-certificate-outline",
                            variant: "outlined"
                          }, null, 8, ["modelValue"])
                        ]),
                        _createVNode(_component_VAlert, {
                          density: "compact",
                          type: "info",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => _cache[99] || (_cache[99] = [
                            _createTextVNode(" 基础变量："),
                            _createElementVNode("code", null, "{date}", -1),
                            _createTextVNode("="),
                            _createElementVNode("code", null, "20260911", -1),
                            _createTextVNode("、"),
                            _createElementVNode("code", null, "{time}", -1),
                            _createTextVNode("="),
                            _createElementVNode("code", null, "040020", -1),
                            _createTextVNode("、 "),
                            _createElementVNode("code", null, "{id}", -1),
                            _createTextVNode("="),
                            _createElementVNode("code", null, "7f3a9c", -1),
                            _createTextVNode("、"),
                            _createElementVNode("code", null, "{sequence}", -1),
                            _createTextVNode("="),
                            _createElementVNode("code", null, "0001", -1),
                            _createTextVNode("；也支持 strftime， 例如 "),
                            _createElementVNode("code", null, "{%Y%m%d_%H%M%S}", -1),
                            _createTextVNode("。 ")
                          ])),
                          _: 1
                        }),
                        _createElementVNode("div", _hoisted_55, [
                          _cache[100] || (_cache[100] = _createElementVNode("span", null, "示例", -1)),
                          _createElementVNode("code", null, "批次：" + _toDisplayString(namingExamples.value.batch), 1),
                          _createElementVNode("code", null, "归档包：" + _toDisplayString(namingExamples.value.archive), 1)
                        ]),
                        _createVNode(_component_VAlert, {
                          density: "compact",
                          type: "info",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => _cache[101] || (_cache[101] = [
                            _createTextVNode(" 外层归档包名会对存储端可见；需要隐藏文件名时，请使用 7z AES-256 并开启加密文件名。 ")
                          ])),
                          _: 1
                        })
                      ]),
                      _createElementVNode("div", _hoisted_56, [
                        _cache[103] || (_cache[103] = _createElementVNode("h4", null, "文件筛选", -1)),
                        _createElementVNode("div", _hoisted_57, [
                          _createVNode(_component_VSwitch, {
                            modelValue: taskEditor.value.recursive,
                            "onUpdate:modelValue": _cache[24] || (_cache[24] = ($event) => taskEditor.value.recursive = $event),
                            color: "primary",
                            density: "compact",
                            "hide-details": "",
                            label: "递归扫描子目录"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "目录深度",
                            modelValue: taskEditor.value.directory_depth,
                            "onUpdate:modelValue": _cache[25] || (_cache[25] = ($event) => taskEditor.value.directory_depth = $event),
                            modelModifiers: { number: true },
                            hint: "按目录分组时使用。",
                            label: "目录深度",
                            min: "1",
                            "persistent-hint": "",
                            type: "number",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextarea, {
                            "aria-label": "包含模式",
                            modelValue: includePatternsText.value,
                            "onUpdate:modelValue": _cache[26] || (_cache[26] = ($event) => includePatternsText.value = $event),
                            hint: "每行一个 glob，留空表示不限制。",
                            label: "包含模式",
                            "persistent-hint": "",
                            rows: "3",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextarea, {
                            "aria-label": "排除模式",
                            modelValue: excludePatternsText.value,
                            "onUpdate:modelValue": _cache[27] || (_cache[27] = ($event) => excludePatternsText.value = $event),
                            hint: "每行一个 glob。",
                            label: "排除模式",
                            "persistent-hint": "",
                            rows: "3",
                            variant: "outlined"
                          }, null, 8, ["modelValue"])
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_58, [
                        _cache[104] || (_cache[104] = _createElementVNode("h4", null, "批次策略", -1)),
                        _createElementVNode("div", _hoisted_59, [
                          _createVNode(_component_VSelect, {
                            "aria-label": "分组方式",
                            modelValue: taskEditor.value.grouping,
                            "onUpdate:modelValue": _cache[28] || (_cache[28] = ($event) => taskEditor.value.grouping = $event),
                            items: groupingOptions,
                            "item-title": "title",
                            "item-value": "value",
                            label: "分组方式",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VSelect, {
                            "aria-label": "时间粒度",
                            modelValue: taskEditor.value.time_grain,
                            "onUpdate:modelValue": _cache[29] || (_cache[29] = ($event) => taskEditor.value.time_grain = $event),
                            items: timeGrainOptions,
                            "item-title": "title",
                            "item-value": "value",
                            label: "时间粒度",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "最多批次",
                            modelValue: taskEditor.value.max_batches,
                            "onUpdate:modelValue": _cache[30] || (_cache[30] = ($event) => taskEditor.value.max_batches = $event),
                            modelModifiers: { number: true },
                            label: "最多批次",
                            min: "1",
                            type: "number",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "每批最多文件",
                            modelValue: taskEditor.value.max_files,
                            "onUpdate:modelValue": _cache[31] || (_cache[31] = ($event) => taskEditor.value.max_files = $event),
                            modelModifiers: { number: true },
                            hint: "0 表示不限。",
                            label: "每批最多文件",
                            min: "0",
                            "persistent-hint": "",
                            type: "number",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "每批最大体积",
                            modelValue: taskEditor.value.max_bytes,
                            "onUpdate:modelValue": _cache[32] || (_cache[32] = ($event) => taskEditor.value.max_bytes = $event),
                            modelModifiers: { number: true },
                            hint: "0 表示不限，单位字节。",
                            label: "每批最大体积",
                            min: "0",
                            "persistent-hint": "",
                            type: "number",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "归档多少天之前的文件",
                            modelValue: taskEditor.value.archive_age_days,
                            "onUpdate:modelValue": _cache[33] || (_cache[33] = ($event) => taskEditor.value.archive_age_days = $event),
                            modelModifiers: { number: true },
                            hint: "按文件修改时间筛选，0 表示不限制。",
                            label: "归档多少天之前的文件",
                            min: "0",
                            "persistent-hint": "",
                            type: "number",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "稳定时间（秒）",
                            modelValue: taskEditor.value.stability_seconds,
                            "onUpdate:modelValue": _cache[34] || (_cache[34] = ($event) => taskEditor.value.stability_seconds = $event),
                            modelModifiers: { number: true },
                            label: "稳定时间（秒）",
                            min: "1",
                            type: "number",
                            variant: "outlined"
                          }, null, 8, ["modelValue"])
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_60, [
                        _cache[106] || (_cache[106] = _createElementVNode("h4", null, "续跑与空间", -1)),
                        _createElementVNode("div", _hoisted_61, [
                          _createVNode(_component_VSwitch, {
                            modelValue: taskEditor.value.auto_continue,
                            "onUpdate:modelValue": _cache[35] || (_cache[35] = ($event) => taskEditor.value.auto_continue = $event),
                            color: "primary",
                            density: "compact",
                            "hide-details": "",
                            label: "自动分批续跑"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "本地成品最多批次",
                            modelValue: taskEditor.value.max_pending_archives,
                            "onUpdate:modelValue": _cache[36] || (_cache[36] = ($event) => taskEditor.value.max_pending_archives = $event),
                            modelModifiers: { number: true },
                            hint: "0 表示不限。",
                            label: "本地成品最多批次",
                            min: "0",
                            "persistent-hint": "",
                            type: "number",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "本地成品最大体积",
                            modelValue: taskEditor.value.max_pending_bytes,
                            "onUpdate:modelValue": _cache[37] || (_cache[37] = ($event) => taskEditor.value.max_pending_bytes = $event),
                            modelModifiers: { number: true },
                            hint: "0 表示不限，单位字节。",
                            label: "本地成品最大体积",
                            min: "0",
                            "persistent-hint": "",
                            type: "number",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "预留磁盘空间",
                            modelValue: minFreeGiB.value,
                            "onUpdate:modelValue": _cache[38] || (_cache[38] = ($event) => minFreeGiB.value = $event),
                            modelModifiers: { number: true },
                            hint: "归档后必须保留的空间，0 表示不预留。",
                            label: "预留磁盘空间",
                            min: "0",
                            "persistent-hint": "",
                            step: "0.1",
                            suffix: "GiB",
                            type: "number",
                            variant: "outlined"
                          }, null, 8, ["modelValue"])
                        ]),
                        _createVNode(_component_VAlert, {
                          density: "compact",
                          type: "info",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => _cache[105] || (_cache[105] = [
                            _createTextVNode("插件只负责本地归档，不上传、不删除成品；自动续跑会在空间或成品积压达到限制时每 60 秒重新检测。")
                          ])),
                          _: 1
                        })
                      ]),
                      _createElementVNode("div", _hoisted_62, [
                        _cache[107] || (_cache[107] = _createElementVNode("h4", null, "压缩与安全", -1)),
                        _createElementVNode("div", _hoisted_63, [
                          _createVNode(_component_VSelect, {
                            "aria-label": "归档格式",
                            "model-value": taskEditor.value.format,
                            items: formatOptions,
                            "item-title": "title",
                            "item-value": "value",
                            label: "归档格式",
                            variant: "outlined",
                            "onUpdate:modelValue": requestFormat
                          }, null, 8, ["model-value"]),
                          _createVNode(_component_VSelect, {
                            "aria-label": "压缩级别",
                            modelValue: taskEditor.value.compression,
                            "onUpdate:modelValue": _cache[39] || (_cache[39] = ($event) => taskEditor.value.compression = $event),
                            items: compressionOptions,
                            "item-title": "title",
                            "item-value": "value",
                            label: "压缩级别",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VSelect, {
                            "aria-label": "加密方式",
                            "model-value": taskEditor.value.encryption,
                            items: encryptionOptions,
                            "item-title": "title",
                            "item-value": "value",
                            label: "加密方式",
                            variant: "outlined",
                            "onUpdate:modelValue": handleEncryption
                          }, null, 8, ["model-value"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "密码（可选）",
                            modelValue: taskEditor.value.password,
                            "onUpdate:modelValue": _cache[40] || (_cache[40] = ($event) => taskEditor.value.password = $event),
                            autocomplete: "new-password",
                            hint: taskEditorHasSavedPassword.value ? "已保存密码不会回显；输入新值可覆盖。" : "密码只写入，不会回显。",
                            label: "密码（可选）",
                            "persistent-hint": "",
                            type: "password",
                            variant: "outlined"
                          }, null, 8, ["modelValue", "hint"]),
                          _createVNode(_component_VTextField, {
                            "aria-label": "密码版本",
                            modelValue: taskEditor.value.password_version,
                            "onUpdate:modelValue": _cache[41] || (_cache[41] = ($event) => taskEditor.value.password_version = $event),
                            label: "密码版本",
                            variant: "outlined"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_VSwitch, {
                            "model-value": taskEditor.value.encrypt_names,
                            color: "primary",
                            disabled: taskEditor.value.encryption !== "aes256",
                            density: "compact",
                            "hide-details": "",
                            label: "加密文件名（7z）",
                            "onUpdate:modelValue": requestEncryptNames
                          }, null, 8, ["model-value", "disabled"])
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_64, [
                        _cache[109] || (_cache[109] = _createElementVNode("h4", null, "完成行为", -1)),
                        _createElementVNode("div", _hoisted_65, [
                          _createVNode(_component_VSwitch, {
                            "model-value": taskEditor.value.verify,
                            color: "primary",
                            disabled: taskEditor.value.delete_source,
                            density: "compact",
                            "hide-details": "",
                            label: "归档后校验",
                            "onUpdate:modelValue": handleVerify
                          }, null, 8, ["model-value", "disabled"]),
                          _createVNode(_component_VSwitch, {
                            "model-value": taskEditor.value.delete_source,
                            color: "error",
                            density: "compact",
                            "hide-details": "",
                            label: "校验通过后删除源文件",
                            "onUpdate:modelValue": handleDeleteSource
                          }, null, 8, ["model-value"])
                        ]),
                        taskEditor.value.delete_source ? (_openBlock(), _createBlock(_component_VAlert, {
                          key: 0,
                          class: "archive-editor__warning",
                          density: "compact",
                          type: "warning",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => _cache[108] || (_cache[108] = [
                            _createTextVNode("启用删除源文件后，后端会强制执行校验；校验失败不会删除源文件。")
                          ])),
                          _: 1
                        })) : _createCommentVNode("", true)
                      ]),
                      _createElementVNode("div", _hoisted_66, [
                        _createVNode(_component_VBtn, {
                          "prepend-icon": "mdi-eye-outline",
                          variant: "tonal",
                          onClick: _cache[42] || (_cache[42] = ($event) => startPreviewForTask(prepareEditorTask()))
                        }, {
                          default: _withCtx(() => _cache[110] || (_cache[110] = [
                            _createTextVNode("预览文件")
                          ])),
                          _: 1
                        }),
                        _createVNode(_component_VSpacer),
                        _createVNode(_component_VBtn, {
                          variant: "text",
                          onClick: cancelTaskEditor
                        }, {
                          default: _withCtx(() => _cache[111] || (_cache[111] = [
                            _createTextVNode("取消")
                          ])),
                          _: 1
                        }),
                        _createVNode(_component_VBtn, {
                          color: "primary",
                          "prepend-icon": "mdi-check",
                          variant: "flat",
                          onClick: saveTaskEditor
                        }, {
                          default: _withCtx(() => _cache[112] || (_cache[112] = [
                            _createTextVNode("保存任务")
                          ])),
                          _: 1
                        })
                      ])
                    ])) : _createCommentVNode("", true)
                  ], 2)) : _createCommentVNode("", true)
                ])) : activeView.value === "batches" ? (_openBlock(), _createElementBlock("section", _hoisted_67, [
                  _createElementVNode("div", _hoisted_68, [
                    _createVNode(_component_VSelect, {
                      "aria-label": "批次任务",
                      modelValue: batchTaskFilter.value,
                      "onUpdate:modelValue": _cache[43] || (_cache[43] = ($event) => batchTaskFilter.value = $event),
                      items: [
                        { title: "全部任务", value: "" },
                        ...draft.value.tasks.map((task) => ({ title: task.name, value: task.id }))
                      ],
                      "item-title": "title",
                      "item-value": "value",
                      label: "任务",
                      variant: "outlined"
                    }, null, 8, ["modelValue", "items"]),
                    _createVNode(_component_VSelect, {
                      "aria-label": "批次状态",
                      modelValue: batchStatusFilter.value,
                      "onUpdate:modelValue": _cache[44] || (_cache[44] = ($event) => batchStatusFilter.value = $event),
                      items: batchStatusOptions,
                      "item-title": "title",
                      "item-value": "value",
                      label: "状态",
                      variant: "outlined"
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_VSpacer)
                  ]),
                  batchLoading.value ? (_openBlock(), _createElementBlock("div", _hoisted_69, [
                    _createVNode(_component_VProgressCircular, {
                      color: "primary",
                      indeterminate: "",
                      size: "18",
                      width: "2"
                    }),
                    _cache[113] || (_cache[113] = _createTextVNode("正在读取批次… "))
                  ])) : batchData.value.items.length === 0 ? (_openBlock(), _createElementBlock("div", _hoisted_70, [
                    _createVNode(_component_VIcon, {
                      icon: "mdi-package-variant-remove",
                      size: "34"
                    }),
                    _cache[114] || (_cache[114] = _createElementVNode("strong", null, "没有符合条件的批次", -1)),
                    _cache[115] || (_cache[115] = _createElementVNode("span", null, "任务运行后，批次详情会显示在这里。", -1))
                  ])) : (_openBlock(), _createElementBlock("div", _hoisted_71, [
                    _createElementVNode("table", _hoisted_72, [
                      _cache[116] || (_cache[116] = _createElementVNode("thead", null, [
                        _createElementVNode("tr", null, [
                          _createElementVNode("th", null, "批次"),
                          _createElementVNode("th", null, "任务"),
                          _createElementVNode("th", null, "状态"),
                          _createElementVNode("th", null, "创建时间"),
                          _createElementVNode("th", { class: "archive-table__numeric" }, "文件"),
                          _createElementVNode("th", { class: "archive-table__numeric" }, "归档体积"),
                          _createElementVNode("th", null, "校验"),
                          _createElementVNode("th")
                        ])
                      ], -1)),
                      _createElementVNode("tbody", null, [
                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(batchData.value.items, (batch) => {
                          return _openBlock(), _createElementBlock("tr", {
                            key: batch.id,
                            onClick: ($event) => openBatch(batch)
                          }, [
                            _createElementVNode("td", null, [
                              _createElementVNode("strong", null, _toDisplayString(batch.batch_name || batch.id), 1),
                              _createElementVNode("small", _hoisted_74, "ID：" + _toDisplayString(batch.id), 1),
                              _createElementVNode("small", null, _toDisplayString(batch.archive_name || batch.archive_path || "暂无归档路径"), 1)
                            ]),
                            _createElementVNode("td", null, _toDisplayString(batch.task_name), 1),
                            _createElementVNode("td", null, [
                              _createVNode(_component_VChip, {
                                color: statusColor(batch.status),
                                size: "small",
                                variant: "tonal"
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(statusLabel(batch.status)), 1),
                                  batch.superseded ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                    _createTextVNode(" · 已替代")
                                  ], 64)) : _createCommentVNode("", true)
                                ]),
                                _: 2
                              }, 1032, ["color"])
                            ]),
                            _createElementVNode("td", null, _toDisplayString(formatDate(batch.created_at)), 1),
                            _createElementVNode("td", _hoisted_75, _toDisplayString(formatNumber(batch.file_count)), 1),
                            _createElementVNode("td", _hoisted_76, _toDisplayString(formatBytes(batch.archive_size)), 1),
                            _createElementVNode("td", null, [
                              _createVNode(_component_VIcon, {
                                color: batch.verified ? "success" : "warning",
                                icon: batch.verified ? "mdi-check-circle-outline" : "mdi-help-circle-outline"
                              }, null, 8, ["color", "icon"]),
                              _createElementVNode("span", _hoisted_77, _toDisplayString(batch.verified ? "已校验" : "未校验"), 1)
                            ]),
                            _createElementVNode("td", null, [
                              _createVNode(_component_VBtn, {
                                "aria-label": "查看批次详情",
                                icon: "",
                                size: "small",
                                variant: "text",
                                onClick: _withModifiers(($event) => openBatch(batch), ["stop"])
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_VIcon, { icon: "mdi-chevron-right" })
                                ]),
                                _: 2
                              }, 1032, ["onClick"])
                            ])
                          ], 8, _hoisted_73);
                        }), 128))
                      ])
                    ])
                  ])),
                  batchData.value.total > 0 ? (_openBlock(), _createElementBlock("div", _hoisted_78, [
                    _createElementVNode("span", null, "共 " + _toDisplayString(formatNumber(batchData.value.total)) + " 个批次", 1),
                    _createVNode(_component_VPagination, {
                      modelValue: batchPage.value,
                      "onUpdate:modelValue": _cache[45] || (_cache[45] = ($event) => batchPage.value = $event),
                      length: batchPageCount.value,
                      density: "compact",
                      "total-visible": 5
                    }, null, 8, ["modelValue", "length"])
                  ])) : _createCommentVNode("", true)
                ])) : (_openBlock(), _createElementBlock("section", _hoisted_79, [
                  !draft.value.tasks.length ? (_openBlock(), _createElementBlock("div", _hoisted_80, [
                    _createVNode(_component_VIcon, {
                      icon: "mdi-archive-off-outline",
                      size: "34"
                    }),
                    _cache[117] || (_cache[117] = _createElementVNode("strong", null, "暂无归档任务", -1)),
                    _cache[118] || (_cache[118] = _createElementVNode("span", null, "创建归档任务后，才能查询已归档文件。", -1))
                  ])) : !hasFileTaskSelection.value ? (_openBlock(), _createElementBlock("div", _hoisted_81, [
                    _createVNode(_component_VIcon, {
                      icon: "mdi-format-list-checks",
                      size: "34"
                    }),
                    _cache[119] || (_cache[119] = _createElementVNode("strong", null, "请选择归档任务", -1)),
                    _cache[120] || (_cache[120] = _createElementVNode("span", null, "选择任务后，可以按目录、状态或相对路径查询文件。", -1))
                  ])) : (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                    _createElementVNode("div", _hoisted_82, [
                      _createVNode(_component_VSelect, {
                        "aria-label": "文件任务",
                        clearable: "",
                        modelValue: fileTaskFilter.value,
                        "onUpdate:modelValue": _cache[46] || (_cache[46] = ($event) => fileTaskFilter.value = $event),
                        items: draft.value.tasks.map((task) => ({ title: task.name, value: task.id })),
                        "item-title": "title",
                        "item-value": "value",
                        label: "任务",
                        variant: "outlined"
                      }, null, 8, ["modelValue", "items"]),
                      _createVNode(_component_VTextField, {
                        modelValue: fileQuery.value,
                        "onUpdate:modelValue": _cache[47] || (_cache[47] = ($event) => fileQuery.value = $event),
                        clearable: "",
                        label: "搜索相对路径",
                        "prepend-inner-icon": "mdi-magnify",
                        variant: "outlined",
                        onKeyup: _withKeys(submitFileSearch, ["enter"])
                      }, null, 8, ["modelValue"]),
                      _createVNode(_component_VSelect, {
                        "aria-label": "文件状态",
                        modelValue: fileStatus.value,
                        "onUpdate:modelValue": _cache[48] || (_cache[48] = ($event) => fileStatus.value = $event),
                        clearable: "",
                        items: [
                          { title: "待处理", value: "pending" },
                          { title: "已归档", value: "archived" },
                          { title: "失败", value: "failed" },
                          { title: "已删除", value: "deleted" }
                        ],
                        "item-title": "title",
                        "item-value": "value",
                        label: "文件状态",
                        variant: "outlined"
                      }, null, 8, ["modelValue"]),
                      _createVNode(_component_VBtn, {
                        "aria-label": "搜索文件",
                        icon: "",
                        variant: "tonal",
                        onClick: submitFileSearch
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_VIcon, { icon: "mdi-magnify" })
                        ]),
                        _: 1
                      })
                    ]),
                    _createElementVNode("nav", _hoisted_83, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(breadcrumbs.value, (crumb) => {
                        return _openBlock(), _createBlock(_component_VBtn, {
                          key: crumb.path || "root",
                          size: "small",
                          variant: "text",
                          onClick: ($event) => navigateDirectory(crumb.path)
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(crumb.title), 1)
                          ]),
                          _: 2
                        }, 1032, ["onClick"]);
                      }), 128))
                    ]),
                    fileLoading.value ? (_openBlock(), _createElementBlock("div", _hoisted_84, [
                      _createVNode(_component_VProgressCircular, {
                        color: "primary",
                        indeterminate: "",
                        size: "18",
                        width: "2"
                      }),
                      _cache[121] || (_cache[121] = _createTextVNode("正在读取文件… "))
                    ])) : fileData.value.items.length === 0 && fileData.value.directories.length === 0 ? (_openBlock(), _createElementBlock("div", _hoisted_85, [
                      _createVNode(_component_VIcon, {
                        icon: "mdi-file-search-outline",
                        size: "34"
                      }),
                      _cache[122] || (_cache[122] = _createElementVNode("strong", null, "没有找到文件", -1)),
                      _cache[123] || (_cache[123] = _createElementVNode("span", null, "调整任务、目录或搜索条件后重试。", -1))
                    ])) : (_openBlock(), _createElementBlock("div", _hoisted_86, [
                      fileData.value.directories.length ? (_openBlock(), _createElementBlock("div", _hoisted_87, [
                        _cache[124] || (_cache[124] = _createElementVNode("div", { class: "archive-directory-list__heading" }, "子目录", -1)),
                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(fileData.value.directories, (directory) => {
                          return _openBlock(), _createElementBlock("button", {
                            key: directory.path,
                            class: "archive-directory",
                            type: "button",
                            onClick: ($event) => navigateDirectory(directory.path)
                          }, [
                            _createVNode(_component_VIcon, { icon: "mdi-folder-outline" }),
                            _createElementVNode("span", null, _toDisplayString(directory.name), 1),
                            _createVNode(_component_VIcon, {
                              icon: "mdi-chevron-right",
                              size: "18"
                            })
                          ], 8, _hoisted_88);
                        }), 128))
                      ])) : _createCommentVNode("", true),
                      _createElementVNode("div", _hoisted_89, [
                        _createElementVNode("table", _hoisted_90, [
                          _cache[125] || (_cache[125] = _createElementVNode("thead", null, [
                            _createElementVNode("tr", null, [
                              _createElementVNode("th", null, "相对路径"),
                              _createElementVNode("th", { class: "archive-table__numeric" }, "大小"),
                              _createElementVNode("th", null, "修改时间"),
                              _createElementVNode("th", null, "状态"),
                              _createElementVNode("th", null, "批次"),
                              _createElementVNode("th", null, "SHA-256")
                            ])
                          ], -1)),
                          _createElementVNode("tbody", null, [
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(fileData.value.items, (file) => {
                              return _openBlock(), _createElementBlock("tr", {
                                key: `${file.batch_id}:${file.relative_path}`
                              }, [
                                _createElementVNode("td", null, [
                                  _createElementVNode("strong", null, _toDisplayString(file.relative_path), 1)
                                ]),
                                _createElementVNode("td", _hoisted_91, _toDisplayString(formatBytes(file.size)), 1),
                                _createElementVNode("td", null, _toDisplayString(file.mtime_ns ? formatDate(new Date(file.mtime_ns / 1e6).toISOString()) : "-"), 1),
                                _createElementVNode("td", null, [
                                  _createVNode(_component_VChip, {
                                    color: statusColor(file.status),
                                    size: "small",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode(_toDisplayString(statusLabel(file.status)), 1)
                                    ]),
                                    _: 2
                                  }, 1032, ["color"])
                                ]),
                                _createElementVNode("td", null, _toDisplayString(file.batch_id ? file.batch_id.slice(0, 12) : "-"), 1),
                                _createElementVNode("td", null, [
                                  _createElementVNode("code", null, _toDisplayString(file.sha256 ? file.sha256.slice(0, 16) : "-"), 1)
                                ])
                              ]);
                            }), 128))
                          ])
                        ])
                      ])
                    ])),
                    fileData.value.total > 0 ? (_openBlock(), _createElementBlock("div", _hoisted_92, [
                      _createElementVNode("span", null, "共 " + _toDisplayString(formatNumber(fileData.value.total)) + " 个文件", 1),
                      _createVNode(_component_VPagination, {
                        modelValue: filePage.value,
                        "onUpdate:modelValue": _cache[49] || (_cache[49] = ($event) => filePage.value = $event),
                        length: filePageCount.value,
                        density: "compact",
                        "total-visible": 5
                      }, null, 8, ["modelValue", "length"])
                    ])) : _createCommentVNode("", true)
                  ], 64))
                ]))
              ])
            ])
          ]),
          isDirty.value ? (_openBlock(), _createElementBlock("div", _hoisted_93, [
            _createElementVNode("span", _hoisted_94, [
              _createVNode(_component_VIcon, {
                color: "warning",
                icon: "mdi-circle",
                size: "8"
              }),
              _cache[126] || (_cache[126] = _createTextVNode("有未保存修改"))
            ]),
            _createVNode(_component_VSpacer),
            _createVNode(_component_VBtn, {
              class: "archive-mobile-save-dock__save",
              color: "primary",
              disabled: !isDirty.value,
              type: "submit",
              variant: "flat"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VIcon, {
                  icon: "mdi-content-save",
                  start: ""
                }),
                _cache[127] || (_cache[127] = _createTextVNode("保存修改"))
              ]),
              _: 1
            }, 8, ["disabled"])
          ])) : _createCommentVNode("", true)
        ], 32),
        _createVNode(_component_VBottomSheet, {
          modelValue: mobileNavOpen.value,
          "onUpdate:modelValue": _cache[50] || (_cache[50] = ($event) => mobileNavOpen.value = $event)
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VCard, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCardTitle, null, {
                  default: _withCtx(() => _cache[128] || (_cache[128] = [
                    _createTextVNode("切换工作区")
                  ])),
                  _: 1
                }),
                _createVNode(_component_VList, {
                  lines: "two",
                  nav: ""
                }, {
                  default: _withCtx(() => [
                    (_openBlock(), _createElementBlock(_Fragment, null, _renderList(viewLabels, (view, key) => {
                      return _createVNode(_component_VListItem, {
                        key,
                        active: activeView.value === key,
                        "prepend-icon": view.icon,
                        subtitle: view.summary,
                        title: view.title,
                        color: "primary",
                        onClick: ($event) => selectMobileView(key)
                      }, {
                        append: _withCtx(() => [
                          activeView.value === key ? (_openBlock(), _createBlock(_component_VIcon, {
                            key: 0,
                            icon: "mdi-check"
                          })) : _createCommentVNode("", true)
                        ]),
                        _: 2
                      }, 1032, ["active", "prepend-icon", "subtitle", "title", "onClick"]);
                    }), 64))
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"]),
        _createVNode(_component_VDialog, {
          modelValue: compatibilityOpen.value,
          "onUpdate:modelValue": _cache[51] || (_cache[51] = ($event) => compatibilityOpen.value = $event),
          "max-width": "480",
          width: "calc(100% - 24px)"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VCard, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCardTitle, null, {
                  default: _withCtx(() => _cache[129] || (_cache[129] = [
                    _createTextVNode("格式兼容性确认")
                  ])),
                  _: 1
                }),
                compatibilityReason.value === "format" ? (_openBlock(), _createBlock(_component_VCardText, { key: 0 }, {
                  default: _withCtx(() => _cache[130] || (_cache[130] = [
                    _createTextVNode("ZIP 不支持加密文件名。切换为 ZIP 会关闭“加密文件名”，是否继续？")
                  ])),
                  _: 1
                })) : (_openBlock(), _createBlock(_component_VCardText, { key: 1 }, {
                  default: _withCtx(() => _cache[131] || (_cache[131] = [
                    _createTextVNode("ZIP 不支持加密文件名。要启用此选项，需要切换到 7z，是否继续？")
                  ])),
                  _: 1
                })),
                _createVNode(_component_VCardActions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSpacer),
                    _createVNode(_component_VBtn, {
                      variant: "text",
                      onClick: cancelCompatibilityChange
                    }, {
                      default: _withCtx(() => _cache[132] || (_cache[132] = [
                        _createTextVNode("取消")
                      ])),
                      _: 1
                    }),
                    _createVNode(_component_VBtn, {
                      color: "primary",
                      variant: "flat",
                      onClick: acceptCompatibilityChange
                    }, {
                      default: _withCtx(() => _cache[133] || (_cache[133] = [
                        _createTextVNode("确认切换")
                      ])),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"]),
        _createVNode(_component_VDialog, {
          modelValue: previewOpen.value,
          "onUpdate:modelValue": _cache[52] || (_cache[52] = ($event) => previewOpen.value = $event),
          "max-width": "760",
          scrollable: "",
          width: "calc(100% - 24px)"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VCard, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCardTitle, { class: "archive-dialog__title" }, {
                  default: _withCtx(() => [
                    _cache[134] || (_cache[134] = _createElementVNode("span", null, "文件预览", -1)),
                    _createVNode(_component_VBtn, {
                      "aria-label": "关闭文件预览",
                      icon: "",
                      size: "small",
                      variant: "text",
                      onClick: closePreview
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VIcon, { icon: "mdi-close" })
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardText, null, {
                  default: _withCtx(() => [
                    previewState.value === "running" ? (_openBlock(), _createElementBlock("div", _hoisted_95, [
                      _createVNode(_component_VProgressCircular, {
                        color: "primary",
                        indeterminate: "",
                        size: "28",
                        width: "3"
                      }),
                      _createElementVNode("strong", null, _toDisplayString(previewMessage.value), 1),
                      _cache[135] || (_cache[135] = _createElementVNode("span", null, "扫描过程不会写入归档，也不会删除源文件。", -1))
                    ])) : previewState.value === "failed" ? (_openBlock(), _createElementBlock("div", _hoisted_96, [
                      _createVNode(_component_VIcon, {
                        color: "error",
                        icon: "mdi-alert-circle-outline",
                        size: "30"
                      }),
                      _createElementVNode("strong", null, _toDisplayString(previewMessage.value), 1),
                      _cache[136] || (_cache[136] = _createElementVNode("span", null, "请检查目录、权限和筛选条件。", -1))
                    ])) : previewResult.value ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                      _createElementVNode("div", _hoisted_97, [
                        _createElementVNode("div", null, [
                          _cache[137] || (_cache[137] = _createElementVNode("span", null, "文件数", -1)),
                          _createElementVNode("strong", null, _toDisplayString(formatNumber(previewResult.value.file_count)), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[138] || (_cache[138] = _createElementVNode("span", null, "总大小", -1)),
                          _createElementVNode("strong", null, _toDisplayString(formatBytes(previewResult.value.total_bytes)), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[139] || (_cache[139] = _createElementVNode("span", null, "预计批次", -1)),
                          _createElementVNode("strong", null, _toDisplayString(formatNumber(previewResult.value.batch_count)), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[140] || (_cache[140] = _createElementVNode("span", null, "跳过文件", -1)),
                          _createElementVNode("strong", null, _toDisplayString(formatNumber(previewResult.value.skipped_count)), 1)
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_98, [
                        _createElementVNode("table", _hoisted_99, [
                          _cache[142] || (_cache[142] = _createElementVNode("thead", null, [
                            _createElementVNode("tr", null, [
                              _createElementVNode("th", null, "分组"),
                              _createElementVNode("th", { class: "archive-table__numeric" }, "文件数"),
                              _createElementVNode("th", { class: "archive-table__numeric" }, "大小"),
                              _createElementVNode("th", null, "限制")
                            ])
                          ], -1)),
                          _createElementVNode("tbody", null, [
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(previewResult.value.batches, (batch) => {
                              return _openBlock(), _createElementBlock("tr", {
                                key: batch.group
                              }, [
                                _createElementVNode("td", null, _toDisplayString(batch.group), 1),
                                _createElementVNode("td", _hoisted_100, _toDisplayString(formatNumber(batch.file_count)), 1),
                                _createElementVNode("td", _hoisted_101, _toDisplayString(formatBytes(batch.total_bytes)), 1),
                                _createElementVNode("td", null, [
                                  batch.oversized ? (_openBlock(), _createBlock(_component_VChip, {
                                    key: 0,
                                    color: "warning",
                                    size: "small",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx(() => _cache[141] || (_cache[141] = [
                                      _createTextVNode("超出限制")
                                    ])),
                                    _: 1
                                  })) : (_openBlock(), _createElementBlock("span", _hoisted_102, "正常"))
                                ])
                              ]);
                            }), 128))
                          ])
                        ])
                      ])
                    ], 64)) : _createCommentVNode("", true)
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardActions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSpacer),
                    _createVNode(_component_VBtn, {
                      variant: "text",
                      onClick: closePreview
                    }, {
                      default: _withCtx(() => _cache[143] || (_cache[143] = [
                        _createTextVNode("关闭")
                      ])),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"]),
        _createVNode(_component_VDialog, {
          modelValue: batchDialogOpen.value,
          "onUpdate:modelValue": _cache[57] || (_cache[57] = ($event) => batchDialogOpen.value = $event),
          "max-width": "980",
          scrollable: "",
          width: "calc(100% - 24px)"
        }, {
          default: _withCtx(() => [
            selectedBatch.value ? (_openBlock(), _createBlock(_component_VCard, { key: 0 }, {
              default: _withCtx(() => [
                _createVNode(_component_VCardTitle, { class: "archive-dialog__title" }, {
                  default: _withCtx(() => [
                    _createElementVNode("div", null, [
                      _createElementVNode("span", null, _toDisplayString(selectedBatch.value.batch_name || "批次详情"), 1),
                      _createElementVNode("small", null, "ID：" + _toDisplayString(selectedBatch.value.id), 1)
                    ]),
                    _createVNode(_component_VBtn, {
                      "aria-label": "关闭批次详情",
                      icon: "",
                      size: "small",
                      variant: "text",
                      onClick: _cache[53] || (_cache[53] = ($event) => batchDialogOpen.value = false)
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VIcon, { icon: "mdi-close" })
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardText, null, {
                  default: _withCtx(() => [
                    batchDetailLoading.value ? (_openBlock(), _createElementBlock("div", _hoisted_103, [
                      _createVNode(_component_VProgressCircular, {
                        color: "primary",
                        indeterminate: "",
                        size: "24",
                        width: "2"
                      }),
                      _cache[144] || (_cache[144] = _createTextVNode("正在读取批次详情… "))
                    ])) : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                      selectedBatch.value.superseded ? (_openBlock(), _createBlock(_component_VAlert, {
                        key: 0,
                        type: "info",
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => _cache[145] || (_cache[145] = [
                          _createTextVNode("该批次已被源文件的新版本替代，仅保留作审计记录，不能重试。")
                        ])),
                        _: 1
                      })) : _createCommentVNode("", true),
                      _createElementVNode("div", _hoisted_104, [
                        _createElementVNode("div", null, [
                          _cache[146] || (_cache[146] = _createElementVNode("span", null, "状态", -1)),
                          _createVNode(_component_VChip, {
                            color: statusColor(selectedBatch.value.status),
                            size: "small",
                            variant: "tonal"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(statusLabel(selectedBatch.value.status)), 1)
                            ]),
                            _: 1
                          }, 8, ["color"])
                        ]),
                        _createElementVNode("div", null, [
                          _cache[147] || (_cache[147] = _createElementVNode("span", null, "任务", -1)),
                          _createElementVNode("strong", null, _toDisplayString(selectedBatch.value.task_name), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[148] || (_cache[148] = _createElementVNode("span", null, "批次名称", -1)),
                          _createElementVNode("strong", null, _toDisplayString(selectedBatch.value.batch_name || selectedBatch.value.id), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[149] || (_cache[149] = _createElementVNode("span", null, "源文件", -1)),
                          _createElementVNode("strong", null, _toDisplayString(formatNumber(selectedBatch.value.file_count)) + " · " + _toDisplayString(formatBytes(selectedBatch.value.source_bytes)), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[150] || (_cache[150] = _createElementVNode("span", null, "归档文件", -1)),
                          _createElementVNode("strong", null, _toDisplayString(formatBytes(selectedBatch.value.archive_size)), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[151] || (_cache[151] = _createElementVNode("span", null, "本地成品", -1)),
                          _createVNode(_component_VChip, {
                            color: selectedBatch.value.archive_available ? "success" : "warning",
                            size: "small",
                            variant: "tonal"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(selectedBatch.value.archive_available ? "可用" : "已不在本地"), 1)
                            ]),
                            _: 1
                          }, 8, ["color"])
                        ]),
                        _createElementVNode("div", null, [
                          _cache[152] || (_cache[152] = _createElementVNode("span", null, "校验", -1)),
                          _createElementVNode("strong", null, _toDisplayString(selectedBatch.value.verified ? "已通过" : "未通过或未执行"), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[153] || (_cache[153] = _createElementVNode("span", null, "清单", -1)),
                          _createElementVNode("strong", null, _toDisplayString(selectedBatch.value.manifest_available ? "可用" : "待补全"), 1)
                        ])
                      ]),
                      selectedBatch.value.error ? (_openBlock(), _createBlock(_component_VAlert, {
                        key: 1,
                        type: "error",
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(_toDisplayString(selectedBatch.value.error), 1)
                        ]),
                        _: 1
                      })) : _createCommentVNode("", true),
                      _createElementVNode("div", _hoisted_105, [
                        _createElementVNode("div", null, [
                          _cache[154] || (_cache[154] = _createElementVNode("span", null, "归档路径", -1)),
                          _createElementVNode("code", null, _toDisplayString(selectedBatch.value.archive_path || "-"), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[155] || (_cache[155] = _createElementVNode("span", null, "清单路径", -1)),
                          _createElementVNode("code", null, _toDisplayString(selectedBatch.value.manifest_path || "-"), 1)
                        ]),
                        _createElementVNode("div", null, [
                          _cache[156] || (_cache[156] = _createElementVNode("span", null, "SHA-256", -1)),
                          _createElementVNode("code", null, _toDisplayString(selectedBatch.value.archive_sha256 || "-"), 1)
                        ])
                      ]),
                      selectedBatch.value.files?.length ? (_openBlock(), _createElementBlock("div", _hoisted_106, [
                        _createElementVNode("table", _hoisted_107, [
                          _cache[157] || (_cache[157] = _createElementVNode("thead", null, [
                            _createElementVNode("tr", null, [
                              _createElementVNode("th", null, "文件"),
                              _createElementVNode("th", { class: "archive-table__numeric" }, "大小"),
                              _createElementVNode("th", null, "状态"),
                              _createElementVNode("th", null, "SHA-256")
                            ])
                          ], -1)),
                          _createElementVNode("tbody", null, [
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(selectedBatch.value.files, (file) => {
                              return _openBlock(), _createElementBlock("tr", {
                                key: file.relative_path
                              }, [
                                _createElementVNode("td", null, _toDisplayString(file.relative_path), 1),
                                _createElementVNode("td", _hoisted_108, _toDisplayString(formatBytes(file.size)), 1),
                                _createElementVNode("td", null, [
                                  _createVNode(_component_VChip, {
                                    color: statusColor(batchFileStatus(file, selectedBatch.value)),
                                    size: "small",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode(_toDisplayString(statusLabel(batchFileStatus(file, selectedBatch.value))), 1)
                                    ]),
                                    _: 2
                                  }, 1032, ["color"])
                                ]),
                                _createElementVNode("td", null, [
                                  _createElementVNode("code", null, _toDisplayString(file.sha256 || "-"), 1)
                                ])
                              ]);
                            }), 128))
                          ])
                        ])
                      ])) : _createCommentVNode("", true),
                      Object.keys(selectedBatch.value.cleanup || {}).length ? (_openBlock(), _createElementBlock("div", _hoisted_109, [
                        _cache[158] || (_cache[158] = _createElementVNode("h4", null, "清理结果", -1)),
                        _createElementVNode("div", _hoisted_110, [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(selectedBatch.value.cleanup, (status, path) => {
                            return _openBlock(), _createElementBlock("div", { key: path }, [
                              _createElementVNode("span", null, _toDisplayString(path), 1),
                              _createVNode(_component_VChip, {
                                color: statusColor(status),
                                size: "small",
                                variant: "tonal"
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(statusLabel(status)), 1)
                                ]),
                                _: 2
                              }, 1032, ["color"])
                            ]);
                          }), 128))
                        ])
                      ])) : _createCommentVNode("", true)
                    ], 64))
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardActions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSpacer),
                    selectedBatch.value.status === "manifest_pending" || !selectedBatch.value.manifest_available ? (_openBlock(), _createBlock(_component_VBtn, {
                      key: 0,
                      color: "primary",
                      "prepend-icon": "mdi-file-document-refresh-outline",
                      variant: "tonal",
                      onClick: _cache[54] || (_cache[54] = ($event) => executeBatchAction("repair", selectedBatch.value))
                    }, {
                      default: _withCtx(() => _cache[159] || (_cache[159] = [
                        _createTextVNode("补全清单")
                      ])),
                      _: 1
                    })) : _createCommentVNode("", true),
                    !selectedBatch.value.superseded && selectedBatch.value.status !== "superseded" && ["failed", "cleanup_failed", "cancelled", "interrupted"].includes(selectedBatch.value.status) ? (_openBlock(), _createBlock(_component_VBtn, {
                      key: 1,
                      color: "primary",
                      "prepend-icon": "mdi-replay",
                      variant: "flat",
                      onClick: _cache[55] || (_cache[55] = ($event) => executeBatchAction("retry", selectedBatch.value))
                    }, {
                      default: _withCtx(() => _cache[160] || (_cache[160] = [
                        _createTextVNode("重试批次")
                      ])),
                      _: 1
                    })) : _createCommentVNode("", true),
                    _createVNode(_component_VBtn, {
                      variant: "text",
                      onClick: _cache[56] || (_cache[56] = ($event) => batchDialogOpen.value = false)
                    }, {
                      default: _withCtx(() => _cache[161] || (_cache[161] = [
                        _createTextVNode("关闭")
                      ])),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })) : _createCommentVNode("", true)
          ]),
          _: 1
        }, 8, ["modelValue"])
      ]);
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

const Config = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-68effe21"]]);

export { _export_sfc as _, Config as default, normalizeArchiveConfig as n };
