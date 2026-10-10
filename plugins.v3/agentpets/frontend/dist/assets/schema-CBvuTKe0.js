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

export { BUILTIN_PACK as B, HOST_ACTIONS as H, BUILTIN_PACK_ID as a, builtinAsset as b, HOST_INTENTS as c, framePosition as f, resolveAction as r, validatePack as v };
