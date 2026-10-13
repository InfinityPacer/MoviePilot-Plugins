const DEFAULT_CALIBRATION = {
  left: 0,
  top: 0,
  right: 1,
  bottom: 1,
  baseline: 1,
  offset_x: 0,
  offset_y: 0
};
function parseCalibration(raw) {
  if (raw == null) return { ...DEFAULT_CALIBRATION };
  if (typeof raw !== "object" || Array.isArray(raw)) throw new Error("显示校准字段无效");
  const value = { ...DEFAULT_CALIBRATION };
  for (const [key, item] of Object.entries(raw)) {
    const low = key.startsWith("offset_") ? -0.25 : 0;
    const high = key.startsWith("offset_") ? 0.25 : 1;
    if (!Object.hasOwn(value, key) || typeof item !== "number" || !Number.isFinite(item) || item < low || item > high)
      throw new Error(`显示校准 ${key} 超出范围`);
    value[key] = Math.round(item * 1e4) / 1e4;
  }
  if (value.right - value.left < 0.1 - 1e-6 || value.bottom - value.top < 0.1 - 1e-6)
    throw new Error("有效显示区域的宽高至少为原格子的 10%");
  if (value.baseline <= value.top || value.baseline > value.bottom) throw new Error("脚底基线必须在显示区域内");
  return value;
}
function sameCalibration(a, b) {
  return Object.keys(DEFAULT_CALIBRATION).every(
    (key) => (a?.[key] ?? DEFAULT_CALIBRATION[key]) === (b?.[key] ?? DEFAULT_CALIBRATION[key])
  );
}
function calibrationLayout(value, cellRatio) {
  const width = value.right - value.left;
  const height = value.bottom - value.top;
  return {
    aspectRatio: cellRatio * width / height,
    frame: {
      width: `${100 / width}%`,
      height: `${100 / height}%`,
      left: `${(-value.left + value.offset_x) / width * 100}%`,
      top: `${(-value.top + value.bottom - value.baseline + value.offset_y) / height * 100}%`
    }
  };
}

const id = "projector-cat";
const name = "放映猫";
const description = "戴红色贝雷帽的橘色卡通猫，传统美式卡通风格";
const sheet = "sheet.webp";
const grid = {
	cols: 4,
	rows: 2
};
const frames = {
	idle: 0,
	blink: 1,
	talk: 2,
	think: 3,
	jump: 4,
	wave: 5,
	sleep: 6,
	confused: 7
};
const actions = {
	idle: {
		frames: [
			"idle",
			"idle",
			"idle",
			"idle",
			"blink"
		],
		frame_ms: 700,
		loop: true
	},
	thinking: {
		frames: [
			"think",
			"think",
			"think",
			"blink"
		],
		frame_ms: 500,
		loop: true
	},
	speaking: {
		frames: [
			"talk",
			"idle"
		],
		frame_ms: 220,
		loop: true
	},
	notify: {
		frames: [
			"wave",
			"idle"
		],
		frame_ms: 320,
		loop: true
	},
	success: {
		frames: [
			"jump",
			"wave",
			"jump",
			"idle"
		],
		frame_ms: 260
	},
	warning: {
		frames: [
			"confused"
		]
	},
	error: {
		frames: [
			"confused",
			"blink",
			"confused"
		],
		frame_ms: 500
	},
	dragging: {
		frames: [
			"jump"
		]
	},
	docked: {
		frames: [
			"idle",
			"idle",
			"blink"
		],
		frame_ms: 900,
		loop: true
	},
	sleeping: {
		frames: [
			"sleep"
		]
	},
	reaction: {
		frames: [
			"wave",
			"idle"
		],
		frame_ms: 260
	},
	wave: {
		frames: [
			"wave",
			"idle",
			"wave",
			"idle"
		],
		frame_ms: 240
	},
	sit: {
		frames: [
			"sleep",
			"idle"
		],
		frame_ms: 600
	},
	"eye-roll": {
		frames: [
			"think",
			"confused",
			"idle"
		],
		frame_ms: 380
	},
	faint: {
		frames: [
			"confused",
			"sleep"
		],
		frame_ms: 600
	},
	"happy-jump": {
		frames: [
			"jump",
			"idle",
			"jump",
			"idle"
		],
		frame_ms: 220
	},
	sleep: {
		frames: [
			"sleep"
		],
		loop: true
	},
	stretch: {
		frames: [
			"wave",
			"jump",
			"idle"
		],
		frame_ms: 360
	},
	peek: {
		frames: [
			"blink",
			"idle",
			"blink"
		],
		frame_ms: 300
	},
	scan: {
		frames: [
			"think",
			"idle",
			"think"
		],
		frame_ms: 360
	},
	"spin-cheer": {
		frames: [
			"jump",
			"wave",
			"jump",
			"wave"
		],
		frame_ms: 200
	},
	shy: {
		frames: [
			"blink",
			"idle"
		],
		frame_ms: 400
	},
	confused: {
		frames: [
			"confused"
		]
	},
	nod: {
		frames: [
			"talk",
			"idle",
			"talk",
			"idle"
		],
		frame_ms: 200
	},
	wake: {
		frames: [
			"sleep",
			"blink",
			"idle"
		],
		frame_ms: 320
	}
};
const random_actions = [
	"wave",
	"happy-jump",
	"sleep",
	"peek",
	"nod",
	"eye-roll",
	"stretch",
	"scan"
];
const builtinPackJson = {
	id: id,
	name: name,
	description: description,
	sheet: sheet,
	grid: grid,
	frames: frames,
	actions: actions,
	random_actions: random_actions
};

const HOST_ACTIONS = [
  "wave",
  "sit",
  "eye-roll",
  "faint",
  "disassemble",
  "happy-jump",
  "sleep",
  "stretch",
  "peek",
  "scan",
  "charge",
  "spin-cheer",
  "shy",
  "confused",
  "nod",
  "wake"
];
const HOST_INTENTS = [
  "idle",
  "thinking",
  "speaking",
  "notify",
  "success",
  "warning",
  "error",
  "dragging",
  "docked",
  "sleeping",
  "reaction"
];
const BUILTIN_PACK_ID = "projector-cat";
const DEFAULT_FRAME_MS = 160;
const CODEX_PET_LAYOUTS = [
  { version: "v1", width: 1536, height: 1872, rows: 9 },
  { version: "v2", width: 1536, height: 2288, rows: 11 }
];
const CODEX_ANIMATION_ROWS = [
  { id: "idle", count: 6 },
  { id: "running-right", count: 8 },
  { id: "running-left", count: 8 },
  { id: "waving", count: 4 },
  { id: "jumping", count: 5 },
  { id: "failed", count: 8 },
  { id: "waiting", count: 6 },
  { id: "running", count: 6 },
  { id: "review", count: 6 }
];
const CODEX_LOOK_DIRECTIONS = [
  "000",
  "022-5",
  "045",
  "067-5",
  "090",
  "112-5",
  "135",
  "157-5",
  "180",
  "202-5",
  "225",
  "247-5",
  "270",
  "292-5",
  "315",
  "337-5"
];
function codexPetId(value) {
  const slugChars = [];
  for (const character of value.toLowerCase()) {
    const code = character.charCodeAt(0);
    const allowed = code >= 48 && code <= 57 || code >= 97 && code <= 122 || character === "_" || character === "-";
    if (allowed) slugChars.push(character);
    else if (slugChars[slugChars.length - 1] !== "-") slugChars.push("-");
  }
  let start = 0;
  while (start < slugChars.length && slugChars[start] === "-") start += 1;
  let end = slugChars.length;
  while (end > start && slugChars[end - 1] === "-") end -= 1;
  return slugChars.slice(start, end).join("").slice(0, 32);
}
function buildCodexPetPack(filename, width, height, metadata) {
  const layout = CODEX_PET_LAYOUTS.find((item) => item.width === width && item.height === height);
  if (!layout) {
    throw new Error("只支持 Codex Pet v1（1536×1872）或 v2（1536×2288）精灵图");
  }
  const separatorIndex = Math.max(filename.lastIndexOf("/"), filename.lastIndexOf("\\"));
  const basename = filename.slice(separatorIndex + 1);
  const extensionIndex = basename.lastIndexOf(".");
  const stem = (extensionIndex > 0 ? basename.slice(0, extensionIndex) : basename).trim() || "Codex Pet";
  const displayName = metadata?.displayName?.trim() || stem;
  const id = codexPetId(metadata?.id?.trim() || "") || codexPetId(displayName) || codexPetId(stem) || "codex-pet";
  const frames = {};
  const rowFrames = {};
  CODEX_ANIMATION_ROWS.forEach((row, rowIndex) => {
    rowFrames[row.id] = Array.from({ length: row.count }, (_, column) => {
      const frame = row.id === "idle" && column === 0 ? "idle" : row.id + "-" + (column + 1);
      frames[frame] = rowIndex * 8 + column;
      return frame;
    });
  });
  const lookFrames = [];
  if (layout.version === "v2") {
    CODEX_LOOK_DIRECTIONS.forEach((direction, index) => {
      const frame = "look-" + direction;
      frames[frame] = (9 + Math.floor(index / 8)) * 8 + index % 8;
      lookFrames.push(frame);
    });
  }
  const action = (sequence, frame_ms = 160, loop = false) => ({
    frames: [...sequence],
    frame_ms,
    loop
  });
  const scanFrames = layout.version === "v2" ? [...lookFrames, lookFrames[0]] : rowFrames.review;
  const actions = {
    idle: action(rowFrames.idle, 360, true),
    "running-right": action(rowFrames["running-right"], 140, true),
    "running-left": action(rowFrames["running-left"], 140, true),
    waving: action(rowFrames.waving, 160),
    jumping: action(rowFrames.jumping, 160),
    failed: action(rowFrames.failed, 180),
    waiting: action(rowFrames.waiting, 220, true),
    running: action(rowFrames.running, 160, true),
    review: action(rowFrames.review, 180),
    wave: action(rowFrames.waving, 160),
    notify: action(rowFrames.waving, 160),
    "happy-jump": action(rowFrames.jumping, 160),
    success: action(rowFrames.jumping, 180),
    faint: action(rowFrames.failed, 180),
    error: action(rowFrames.failed, 180),
    thinking: action(rowFrames.waiting, 220, true),
    charge: action(rowFrames.running, 160, true),
    speaking: action(rowFrames.running, 160, true),
    warning: action(rowFrames.review, 180),
    "eye-roll": action(rowFrames.review, 180),
    scan: action(scanFrames, 140),
    ...Object.fromEntries(lookFrames.map((frame) => [frame, action([frame])]))
  };
  return {
    version: layout.version,
    pack: {
      id,
      codex_version: layout.version,
      name: displayName.slice(0, 40),
      description: metadata?.description?.trim().slice(0, 120) || "从 Codex Pet " + layout.version + " 精灵图导入",
      sheet: "",
      grid: { cols: 8, rows: layout.rows },
      frames,
      actions,
      random_actions: ["wave"]
    }
  };
}
const NAME = /^[a-z0-9_-]{1,32}$/;
function integer(value, field, low, high, errors) {
  if (typeof value !== "number" || !Number.isInteger(value) || value < low || value > high) {
    errors.push(`${field} 必须是 ${low} 到 ${high} 之间的整数`);
    return low;
  }
  return value;
}
function validatePack(raw) {
  const errors = [];
  let source = raw;
  if (typeof source === "string") {
    if (source.length > 64 * 1024) return { pack: null, errors: ["素材包 JSON 不能超过 64KB"] };
    try {
      source = JSON.parse(source);
    } catch (error) {
      return { pack: null, errors: [`素材包 JSON 解析失败：${error.message}`] };
    }
  }
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    return { pack: null, errors: ["素材包 JSON 顶层必须是对象"] };
  }
  const data = source;
  const id = data.id ?? "";
  if (id !== "" && (typeof id !== "string" || !NAME.test(id))) {
    errors.push("id 只能包含小写字母、数字、- 和 _，长度 1 到 32");
  }
  const name = typeof data.name === "string" ? data.name.trim() : "";
  if (!name || name.length > 40) errors.push("name 必须是 1 到 40 个字符");
  const grid = data.grid ?? {};
  const cols = integer(grid.cols, "grid.cols", 1, 16, errors);
  const rows = integer(grid.rows, "grid.rows", 1, 16, errors);
  const codexVersion = data.codex_version;
  if (codexVersion != null) {
    if (codexVersion !== "v1" && codexVersion !== "v2") errors.push("codex_version 只支持 v1 或 v2");
    else if (cols !== 8 || rows !== (codexVersion === "v1" ? 9 : 11)) {
      errors.push("codex_version 与网格不匹配，v1 为 8×9，v2 为 8×11");
    }
  }
  const frames = {};
  const rawFrames = data.frames;
  if (!rawFrames || typeof rawFrames !== "object" || Array.isArray(rawFrames)) {
    errors.push("frames 必须是帧名到格子索引的非空对象");
  } else {
    for (const [frame, index] of Object.entries(rawFrames)) {
      if (!NAME.test(frame)) errors.push(`帧名 ${frame} 只能包含小写字母、数字、- 和 _`);
      frames[frame] = integer(index, `frames.${frame}`, 0, cols * rows - 1, errors);
    }
    if (!("idle" in frames)) errors.push("frames 必须包含 idle 帧");
  }
  const actions = {};
  const rawActions = data.actions ?? {};
  if (typeof rawActions !== "object" || Array.isArray(rawActions)) errors.push("actions 必须是对象");
  else {
    for (const [key, value] of Object.entries(rawActions)) {
      const entry = Array.isArray(value) ? { frames: value } : value;
      const sequence = entry?.frames;
      if (!NAME.test(key)) errors.push(`动作名 ${key} 只能包含小写字母、数字、- 和 _`);
      if (!Array.isArray(sequence) || !sequence.length || sequence.length > 64) {
        errors.push(`actions.${key}.frames 必须是 1 到 64 个帧名`);
        continue;
      }
      const missing = sequence.filter((frame) => typeof frame !== "string" || !(frame in frames));
      if (missing.length) errors.push(`actions.${key} 引用了未定义的帧 ${missing.join(", ")}`);
      const frameMs = integer(entry?.frame_ms ?? DEFAULT_FRAME_MS, `actions.${key}.frame_ms`, 40, 5e3, errors);
      if (entry?.loop !== void 0 && typeof entry.loop !== "boolean") errors.push(`actions.${key}.loop 必须是布尔值`);
      actions[key] = { frames: sequence, frame_ms: frameMs, loop: entry?.loop === true };
    }
  }
  const randomActions = Array.isArray(data.random_actions) ? data.random_actions : [];
  if (data.random_actions !== void 0 && !Array.isArray(data.random_actions)) errors.push("random_actions 必须是列表");
  const unknown = randomActions.filter((item) => !HOST_ACTIONS.includes(item));
  if (unknown.length) errors.push(`random_actions 中 ${unknown.join(", ")} 不是宿主动作名`);
  for (const field of ["preview", "avatar"]) {
    const value = data[field];
    if (value === void 0 || value === null || value === "") continue;
    if (typeof value !== "string" || !/^(https?:\/\/\S+|data:image\/)/.test(value)) {
      errors.push(`${field} 只支持 http(s) 地址或 data:image URL`);
    }
  }
  const sheet = typeof data.sheet === "string" ? data.sheet : "";
  let calibration;
  try {
    calibration = parseCalibration(data.calibration);
  } catch (reason) {
    errors.push(reason.message);
  }
  if (errors.length) return { pack: null, errors };
  return {
    pack: {
      id: typeof id === "string" ? id : "",
      ...codexVersion === "v1" || codexVersion === "v2" ? { codex_version: codexVersion } : {},
      name,
      description: typeof data.description === "string" ? data.description.trim() : "",
      sheet,
      grid: { cols, rows },
      frames,
      actions,
      random_actions: [...new Set(randomActions)],
      calibration,
      preview: typeof data.preview === "string" ? data.preview : "",
      avatar: typeof data.avatar === "string" ? data.avatar : "",
      action_mappings: Object.fromEntries(
        Object.entries(data.action_mappings ?? {}).filter(
          (entry) => typeof entry[1] === "string"
        )
      )
    },
    errors
  };
}
function withCodexStageActions(pack) {
  const layout = CODEX_PET_LAYOUTS.find((item) => item.version === pack.codex_version);
  if (!layout) return pack;
  const defaults = buildCodexPetPack(pack.id, layout.width, layout.height).pack;
  const frames = { ...pack.frames };
  const actions = { ...pack.actions };
  const namesByIndex = new Map(Object.entries(frames).map(([name, index]) => [index, name]));
  function frameName(index) {
    const existing = namesByIndex.get(index);
    if (existing) return existing;
    let name = `codex-${index}`;
    for (let suffix = 1; name in frames; suffix += 1) name = `codex-${index}-${suffix}`;
    frames[name] = index;
    namesByIndex.set(index, name);
    return name;
  }
  for (const [key, action] of Object.entries(defaults.actions)) {
    if (actions[key]) continue;
    actions[key] = { ...action, frames: action.frames.map((name) => frameName(defaults.frames[name])) };
  }
  return { ...pack, frames, actions };
}
const BUILTIN_PACK = (() => {
  const { pack } = validatePack(builtinPackJson);
  if (!pack) throw new Error("builtin pack is invalid");
  return { ...pack, id: BUILTIN_PACK_ID };
})();
const ASSET_BASE = import.meta.url;
function builtinAsset(file, base = ASSET_BASE) {
  return new URL(`packs/${BUILTIN_PACK_ID}/${file}`, base).href;
}
function resolveAction(pack, action, intent, thinking, options = {}) {
  if (options.nativeAction && pack.actions[options.nativeAction])
    return { key: options.nativeAction, action: pack.actions[options.nativeAction] };
  const mappings = options.mappings ?? pack.action_mappings ?? {};
  const candidates = [
    options.mappingKey ? mappings[options.mappingKey] : null,
    action ? mappings[`action.${action}`] ?? action : null,
    intent ? mappings[`intent.${intent}`] ?? intent : null,
    thinking ? mappings["intent.thinking"] ?? "thinking" : null,
    "idle"
  ];
  for (const key of candidates) {
    if (key && pack.actions[key]) return { key, action: pack.actions[key] };
  }
  return { key: "idle", action: { frames: ["idle"], frame_ms: DEFAULT_FRAME_MS, loop: false } };
}
function framePosition(pack, frame) {
  const index = pack.frames[frame] ?? pack.frames.idle ?? 0;
  const { cols, rows } = pack.grid;
  const col = index % cols;
  const row = Math.floor(index / cols);
  return { x: cols > 1 ? col / (cols - 1) * 100 : 0, y: rows > 1 ? row / (rows - 1) * 100 : 0 };
}

const PACK_UPDATED_EVENT = "agentpets.pack.updated";
const ACTION_LABELS = {
  idle: "待机",
  wave: "招手",
  sit: "坐下",
  "eye-roll": "翻白眼",
  faint: "晕倒",
  disassemble: "散架",
  "happy-jump": "开心跳跃",
  sleep: "睡眠",
  stretch: "伸懒腰",
  peek: "探头",
  scan: "扫视",
  charge: "蓄力",
  "spin-cheer": "旋转欢呼",
  shy: "害羞",
  confused: "疑惑",
  nod: "点头",
  wake: "醒来",
  thinking: "思考",
  speaking: "说话",
  notify: "通知",
  success: "成功",
  warning: "警告",
  error: "错误",
  dragging: "拖动",
  docked: "贴边",
  sleeping: "睡眠状态",
  reaction: "反应",
  "running-right": "向右跑",
  "running-left": "向左跑",
  waving: "原生招手",
  jumping: "原生跳跃",
  failed: "失败反应",
  waiting: "等待",
  running: "工作",
  review: "审阅"
};
const STAGE_ACTIONS = {
  idle: { label: "待机", action: "idle", group: "日常" },
  blink: { label: "眨眼", action: "idle", group: "日常" },
  wave: { label: "打开助手／招手", action: "wave", group: "会话" },
  talk: { label: "说话／气泡", action: "speaking", group: "会话" },
  think: { label: "思考", action: "thinking", group: "会话" },
  busy: { label: "执行工具", action: "charge", group: "会话" },
  alert: { label: "等待用户", action: "warning", group: "会话" },
  victory: { label: "完成", action: "success", group: "会话" },
  confused: { label: "出错", action: "error", group: "会话" },
  doze: { label: "打盹", action: "sleep", group: "日常" },
  held: { label: "被拖起", action: "thinking", group: "移动交互" },
  fall: { label: "下落", action: "jumping", group: "移动交互" },
  jump: { label: "跳起", action: "jumping", group: "移动交互" },
  sit: { label: "落地坐下", action: "idle", group: "移动交互" },
  "walk-left": { label: "向左行走", action: "running-left", group: "移动交互" },
  "walk-right": { label: "向右行走", action: "running-right", group: "移动交互" }
};
const NATIVE_ACTIONS = [
  "idle",
  "running-right",
  "running-left",
  "waving",
  "jumping",
  "failed",
  "waiting",
  "running",
  "review"
];
function stageAction(pose, facingLeft) {
  const key = pose.startsWith("walk") ? facingLeft ? "walk-left" : "walk-right" : pose;
  return { key: `stage.${key}`, action: STAGE_ACTIONS[key]?.action ?? "idle" };
}
function nativeChoices(pack) {
  const keys = pack.codex_version ? NATIVE_ACTIONS.filter((key) => pack.actions[key]) : [];
  const signature = (key) => pack.actions[key].frames.map((frame) => pack.frames[frame]).join(",");
  const seen = new Set(keys.map(signature));
  for (const key of Object.keys(pack.actions)) {
    if (key.startsWith("look-") || keys.includes(key)) continue;
    const sequence = signature(key);
    if (pack.codex_version && seen.has(sequence)) continue;
    keys.push(key);
    seen.add(sequence);
  }
  return keys.map((value) => ({ value, title: `${ACTION_LABELS[value] ?? value} · ${value}` }));
}
function mappingRows(mode) {
  if (mode === "stage") return Object.entries(STAGE_ACTIONS).map(([key, value]) => ({ key: `stage.${key}`, ...value }));
  return [
    ...HOST_ACTIONS.map((action) => ({
      key: `action.${action}`,
      action,
      label: ACTION_LABELS[action],
      group: "入口动作"
    })),
    ...HOST_INTENTS.map((action) => ({
      key: `intent.${action}`,
      action,
      label: ACTION_LABELS[action],
      group: "入口状态"
    }))
  ];
}
function sameMappings(a, b) {
  return Object.keys(a).length === Object.keys(b).length && Object.entries(a).every(([key, value]) => b[key] === value);
}

export { ACTION_LABELS as A, BUILTIN_PACK_ID as B, DEFAULT_CALIBRATION as D, HOST_ACTIONS as H, PACK_UPDATED_EVENT as P, sameMappings as a, sameCalibration as b, BUILTIN_PACK as c, builtinAsset as d, calibrationLayout as e, framePosition as f, buildCodexPetPack as g, HOST_INTENTS as h, mappingRows as m, nativeChoices as n, parseCalibration as p, resolveAction as r, stageAction as s, validatePack as v, withCodexStageActions as w };
