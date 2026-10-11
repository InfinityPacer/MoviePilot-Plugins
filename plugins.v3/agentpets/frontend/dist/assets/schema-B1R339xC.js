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
function buildCodexPetPack(filename, width, height) {
  const layout = CODEX_PET_LAYOUTS.find((item) => item.width === width && item.height === height);
  if (!layout) {
    throw new Error("只支持 Codex Pet v1（1536×1872）或 v2（1536×2288）精灵图");
  }
  const separatorIndex = Math.max(filename.lastIndexOf("/"), filename.lastIndexOf("\\"));
  const basename = filename.slice(separatorIndex + 1);
  const extensionIndex = basename.lastIndexOf(".");
  const stem = (extensionIndex > 0 ? basename.slice(0, extensionIndex) : basename).trim() || "Codex Pet";
  const slugChars = [];
  for (const character of stem.toLowerCase()) {
    const code = character.charCodeAt(0);
    const allowed = code >= 48 && code <= 57 || code >= 97 && code <= 122 || character === "_" || character === "-";
    if (allowed) slugChars.push(character);
    else if (slugChars[slugChars.length - 1] !== "-") slugChars.push("-");
  }
  let slugStart = 0;
  while (slugStart < slugChars.length && slugChars[slugStart] === "-") slugStart += 1;
  let slugEnd = slugChars.length;
  while (slugEnd > slugStart && slugChars[slugEnd - 1] === "-") slugEnd -= 1;
  const id = slugChars.slice(slugStart, slugEnd).join("").slice(0, 32) || "codex-pet";
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
    scan: action(scanFrames, 140)
  };
  return {
    version: layout.version,
    pack: {
      id,
      name: stem.slice(0, 40),
      description: "从 Codex Pet " + layout.version + " 精灵图导入",
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
  if (errors.length) return { pack: null, errors };
  return {
    pack: {
      id: typeof id === "string" ? id : "",
      name,
      description: typeof data.description === "string" ? data.description.trim() : "",
      sheet,
      grid: { cols, rows },
      frames,
      actions,
      random_actions: [...new Set(randomActions)]
    },
    errors
  };
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
function resolveAction(pack, action, intent, thinking) {
  const candidates = [action, intent, thinking ? "thinking" : null, "idle"];
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

export { BUILTIN_PACK_ID as B, HOST_ACTIONS as H, BUILTIN_PACK as a, builtinAsset as b, buildCodexPetPack as c, HOST_INTENTS as d, framePosition as f, resolveAction as r, validatePack as v };
