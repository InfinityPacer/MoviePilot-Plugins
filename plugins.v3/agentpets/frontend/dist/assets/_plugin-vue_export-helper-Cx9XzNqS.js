import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const LANDMARKS = ["left_eye", "right_eye", "head_top"];
const DEFAULT_CALIBRATION = {
  left: 0,
  top: 0,
  right: 1,
  bottom: 1,
  baseline: 1,
  offset_x: 0,
  offset_y: 0,
  eye_x: null,
  eye_y: null,
  left_eye_x: null,
  left_eye_y: null,
  right_eye_x: null,
  right_eye_y: null,
  head_top_x: null,
  head_top_y: null
};
function parseCalibration(raw) {
  if (raw == null) return { ...DEFAULT_CALIBRATION };
  if (typeof raw !== "object" || Array.isArray(raw)) throw new Error("显示校准字段无效");
  const value = { ...DEFAULT_CALIBRATION };
  for (const [key, item] of Object.entries(raw)) {
    if (Object.hasOwn(value, key) && value[key] === null && item === null) continue;
    const low = key.startsWith("offset_") ? -0.25 : 0;
    const high = key.startsWith("offset_") ? 0.25 : 1;
    if (!Object.hasOwn(value, key) || typeof item !== "number" || !Number.isFinite(item) || item < low || item > high)
      throw new Error(`显示校准 ${key} 超出范围`);
    value[key] = Math.round(item * 1e4) / 1e4;
  }
  if (value.right - value.left < 0.1 - 1e-6 || value.bottom - value.top < 0.1 - 1e-6)
    throw new Error("有效显示区域的宽高至少为原格子的 10%");
  if (value.baseline <= value.top || value.baseline > value.bottom) throw new Error("脚底基线必须在显示区域内");
  for (const key of ["eye", ...LANDMARKS]) {
    if (value[`${key}_x`] === null !== (value[`${key}_y`] === null)) throw new Error("校准点需要同时设置横纵坐标");
    const point = calibrationPoint(value, key);
    if (point && (point.x < -1e-8 || point.x > 1 + 1e-8 || point.y < -1e-8 || point.y > 1 + 1e-8))
      throw new Error("校准点必须在最终显示区域内");
  }
  if (value.left_eye_x != null && value.right_eye_x != null && value.left_eye_x >= value.right_eye_x)
    throw new Error("画面左眼必须位于画面右眼左侧");
  if (value.head_top_y != null && [value.left_eye_y, value.right_eye_y].some((y) => y != null && value.head_top_y >= y))
    throw new Error("头顶必须位于双眼上方");
  return value;
}
function calibrationPoint(value, key) {
  const x = value[`${key}_x`], y = value[`${key}_y`];
  if (x == null || y == null) return null;
  return {
    x: (x - value.left + value.offset_x) / (value.right - value.left),
    y: (y - value.top + value.bottom - value.baseline + value.offset_y) / (value.bottom - value.top)
  };
}
function calibrationEye(value) {
  const left = calibrationPoint(value, "left_eye"), right = calibrationPoint(value, "right_eye");
  if (!left || !right) return calibrationPoint(value, "eye");
  const headTop = calibrationPoint(value, "head_top");
  return { x: (left.x + right.x) / 2, y: (left.y + right.y) / 2, eyes: [left, right], ...headTop ? { headTop } : {} };
}
function mirrorFace(face) {
  if (!face) return null;
  const mirror = (point) => ({ x: 1 - point.x, y: point.y });
  return {
    ...mirror(face),
    ...face.eyes ? { eyes: [mirror(face.eyes[1]), mirror(face.eyes[0])] } : {},
    ...face.headTop ? { headTop: mirror(face.headTop) } : {}
  };
}
function suggestedLandmark(value, key) {
  const center = calibrationPoint(value, "eye") ?? { x: 0.5, y: 0.35 };
  return {
    x: Math.max(0.05, Math.min(0.95, center.x + (key === "left_eye" ? -0.1 : key === "right_eye" ? 0.1 : 0))),
    y: Math.max(0.02, Math.min(0.95, center.y - (key === "head_top" ? 0.2 : 0)))
  };
}
function moveCalibrationPoint(value, key, point) {
  const clamp = (n, low, high) => {
    if (low > high) throw new Error("当前显示框无法容纳校准点，请先调整显示范围");
    return Math.min(high, Math.max(low, n));
  };
  const minX = Math.max(
    0,
    value.left - value.offset_x,
    key === "right_eye" && value.left_eye_x != null ? value.left_eye_x + 1e-4 : 0
  );
  const maxX = Math.min(
    1,
    value.right - value.offset_x,
    key === "left_eye" && value.right_eye_x != null ? value.right_eye_x - 1e-4 : 1
  );
  const minY = Math.max(
    0,
    value.top - value.bottom + value.baseline - value.offset_y,
    key !== "head_top" && value.head_top_y != null ? value.head_top_y + 1e-4 : 0
  );
  const maxY = Math.min(
    1,
    value.baseline - value.offset_y,
    ...key === "head_top" ? [value.left_eye_y, value.right_eye_y].filter((y) => y != null).map((y) => y - 1e-4) : []
  );
  return parseCalibration({
    ...value,
    [`${key}_x`]: clamp(value.left - value.offset_x + point.x * (value.right - value.left), minX, maxX),
    [`${key}_y`]: clamp(
      value.top - value.bottom + value.baseline - value.offset_y + point.y * (value.bottom - value.top),
      minY,
      maxY
    )
  });
}
function sameCalibration(a, b) {
  return Object.keys(DEFAULT_CALIBRATION).every(
    (key) => (a?.[key] ?? DEFAULT_CALIBRATION[key]) === (b?.[key] ?? DEFAULT_CALIBRATION[key])
  );
}
function calibrationForAction(value, baselines, action, referenceBaseline = value.baseline) {
  const baseline = baselines && Object.hasOwn(baselines, action) ? baselines[action] : void 0;
  if (baseline === void 0) return value;
  const adjusted = Math.max(value.top + 1e-4, Math.min(value.bottom, value.baseline + baseline - referenceBaseline));
  return { ...value, baseline: Math.round(adjusted * 1e4) / 1e4 };
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

const id$4 = "projector-cat";
const name$4 = "放映猫";
const description$4 = "戴红色贝雷帽的橘色卡通猫，传统美式卡通风格";
const sheet$4 = "sheet.webp";
const grid$4 = {
	cols: 4,
	rows: 2
};
const frames$4 = {
	idle: 0,
	blink: 1,
	talk: 2,
	think: 3,
	jump: 4,
	wave: 5,
	sleep: 6,
	confused: 7
};
const actions$4 = {
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
const random_actions$4 = [
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
	id: id$4,
	name: name$4,
	description: description$4,
	sheet: sheet$4,
	grid: grid$4,
	frames: frames$4,
	actions: actions$4,
	random_actions: random_actions$4
};

const id$3 = "builtin-chibiterasu";
const name$3 = "小天照";
const description$3 = "shine lock专属";
const sheet$3 = "sheet.webp";
const grid$3 = {
	cols: 8,
	rows: 10
};
const frames$3 = {
	"frame-000": 0,
	"frame-001": 1,
	"frame-002": 2,
	"frame-003": 3,
	"frame-004": 4,
	"frame-005": 5,
	"frame-006": 6,
	"frame-007": 7,
	"frame-008": 8,
	"frame-009": 9,
	"frame-010": 10,
	"frame-011": 11,
	"frame-012": 12,
	"frame-013": 13,
	"frame-014": 14,
	"frame-015": 15,
	"frame-016": 16,
	"frame-017": 17,
	"frame-018": 18,
	"frame-019": 19,
	"frame-020": 20,
	"frame-021": 21,
	"frame-022": 22,
	"frame-023": 23,
	"frame-024": 24,
	"frame-025": 25,
	"frame-026": 26,
	"frame-027": 27,
	"frame-028": 28,
	"frame-029": 29,
	"frame-030": 30,
	"frame-031": 31,
	"frame-032": 32,
	"frame-033": 33,
	"frame-034": 34,
	"frame-035": 35,
	"frame-036": 36,
	"frame-037": 37,
	"frame-038": 38,
	"frame-039": 39,
	"frame-040": 40,
	"frame-041": 41,
	"frame-042": 42,
	"frame-043": 43,
	"frame-044": 44,
	"frame-045": 45,
	"frame-046": 46,
	"frame-047": 47,
	"frame-048": 48,
	"frame-049": 49,
	"frame-050": 50,
	"frame-051": 51,
	"frame-052": 52,
	"frame-053": 53,
	"frame-054": 54,
	"frame-055": 55,
	"frame-056": 56,
	"frame-057": 57,
	"frame-058": 58,
	"frame-059": 59,
	"frame-060": 60,
	"frame-061": 61,
	"frame-062": 62,
	"frame-063": 63,
	"frame-064": 64,
	"frame-065": 65,
	"frame-066": 66,
	"frame-067": 67,
	"frame-068": 68,
	"frame-069": 69,
	"frame-070": 70,
	"frame-071": 71,
	"frame-072": 72,
	"frame-073": 73,
	"frame-074": 74,
	"frame-075": 75,
	"frame-076": 76,
	"frame-077": 77,
	"frame-078": 78,
	idle: 0
};
const actions$3 = {
	stand: {
		frames: [
			"frame-000",
			"frame-000"
		],
		frame_ms: 4125,
		loop: true
	},
	walk: {
		frames: [
			"frame-000",
			"frame-001",
			"frame-000",
			"frame-002"
		],
		frame_ms: 198,
		loop: true
	},
	run: {
		frames: [
			"frame-003",
			"frame-004",
			"frame-005"
		],
		frame_ms: 165,
		loop: true,
		frame_durations: [
			165,
			99,
			99
		]
	},
	dash: {
		frames: [
			"frame-006",
			"frame-004",
			"frame-005"
		],
		frame_ms: 165,
		loop: true,
		frame_durations: [
			165,
			99,
			99
		]
	},
	sit: {
		frames: [
			"frame-007",
			"frame-007"
		],
		frame_ms: 4125,
		loop: true
	},
	"relaxed-sit": {
		frames: [
			"frame-008",
			"frame-008"
		],
		frame_ms: 4125,
		loop: true
	},
	"sit-feet-down": {
		frames: [
			"frame-009",
			"frame-009"
		],
		frame_ms: 4125,
		loop: true
	},
	"dangle-feet": {
		frames: [
			"frame-010",
			"frame-011",
			"frame-010",
			"frame-012"
		],
		frame_ms: 825,
		loop: true
	},
	"look-up": {
		frames: [
			"frame-013",
			"frame-013"
		],
		frame_ms: 4125,
		loop: true
	},
	think: {
		frames: [
			"frame-013",
			"frame-013"
		],
		frame_ms: 4125,
		loop: true
	},
	lie: {
		frames: [
			"frame-014",
			"frame-014"
		],
		frame_ms: 4125,
		loop: true
	},
	crawl: {
		frames: [
			"frame-015",
			"frame-015",
			"frame-016",
			"frame-016",
			"frame-016"
		],
		frame_ms: 924,
		loop: true,
		frame_durations: [
			924,
			132,
			132,
			132,
			792
		]
	},
	jump: {
		frames: [
			"frame-017",
			"frame-017"
		],
		frame_ms: 4125,
		loop: true
	},
	fall: {
		frames: [
			"frame-018",
			"frame-018"
		],
		frame_ms: 4125,
		loop: true
	},
	bounce: {
		frames: [
			"frame-019",
			"frame-020"
		],
		frame_ms: 132,
		loop: true
	},
	"hold-wall": {
		frames: [
			"frame-021",
			"frame-021"
		],
		frame_ms: 4125,
		loop: true
	},
	"climb-wall-up": {
		frames: [
			"frame-022",
			"frame-022",
			"frame-023",
			"frame-024",
			"frame-024",
			"frame-024",
			"frame-023",
			"frame-022"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			132,
			132,
			528,
			132,
			132,
			132
		]
	},
	"climb-wall-down": {
		frames: [
			"frame-022",
			"frame-022",
			"frame-023",
			"frame-024",
			"frame-024",
			"frame-024",
			"frame-023",
			"frame-022"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			132,
			132,
			528,
			132,
			132,
			132
		]
	},
	"hold-ceiling": {
		frames: [
			"frame-025",
			"frame-025"
		],
		frame_ms: 4125,
		loop: true
	},
	"crawl-ceiling": {
		frames: [
			"frame-026",
			"frame-027",
			"frame-028",
			"frame-029",
			"frame-030",
			"frame-029",
			"frame-031",
			"frame-032",
			"frame-026"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			40,
			66,
			132,
			99,
			66,
			165,
			132
		]
	},
	drag: {
		frames: [
			"frame-033",
			"frame-034",
			"frame-035",
			"frame-036",
			"frame-037"
		],
		frame_ms: 165,
		loop: true
	},
	resist: {
		frames: [
			"frame-038",
			"frame-039",
			"frame-038",
			"frame-039",
			"frame-035"
		],
		frame_ms: 165,
		loop: true,
		frame_durations: [
			165,
			165,
			165,
			165,
			1650
		]
	},
	"pull-out": {
		frames: [
			"frame-000",
			"frame-040",
			"frame-041",
			"frame-042",
			"frame-041",
			"frame-042",
			"frame-043"
		],
		frame_ms: 528,
		loop: false,
		frame_durations: [
			528,
			990,
			660,
			660,
			330,
			330,
			1320
		]
	},
	surprise: {
		frames: [
			"frame-000",
			"frame-040",
			"frame-041",
			"frame-042",
			"frame-043"
		],
		frame_ms: 528,
		loop: false,
		frame_durations: [
			528,
			990,
			660,
			660,
			1320
		]
	},
	split: {
		frames: [
			"frame-044",
			"frame-045",
			"frame-046",
			"frame-047",
			"frame-048",
			"frame-049",
			"frame-050",
			"frame-051",
			"frame-052",
			"frame-053",
			"frame-054",
			"frame-055"
		],
		frame_ms: 594,
		loop: false,
		frame_durations: [
			594,
			396,
			396,
			396,
			396,
			396,
			396,
			396,
			594,
			495,
			330,
			990
		]
	},
	cheer: {
		frames: [
			"frame-044",
			"frame-045",
			"frame-046",
			"frame-047",
			"frame-048"
		],
		frame_ms: 594,
		loop: false,
		frame_durations: [
			594,
			396,
			396,
			396,
			594
		]
	},
	"spin-celebrate": {
		frames: [
			"frame-045",
			"frame-046",
			"frame-047",
			"frame-048",
			"frame-050",
			"frame-051",
			"frame-052",
			"frame-055"
		],
		frame_ms: 396,
		loop: false,
		frame_durations: [
			396,
			396,
			396,
			396,
			396,
			396,
			594,
			990
		]
	},
	idle: {
		frames: [
			"frame-000",
			"frame-000"
		],
		frame_ms: 4125,
		loop: true
	},
	follow: {
		frames: [
			"frame-006",
			"frame-004",
			"frame-005"
		],
		frame_ms: 165,
		loop: true,
		frame_durations: [
			165,
			99,
			99
		]
	},
	land: {
		frames: [
			"frame-019",
			"frame-020"
		],
		frame_ms: 132,
		loop: true
	},
	sleep: {
		frames: [
			"frame-014",
			"frame-014"
		],
		frame_ms: 4125,
		loop: true
	},
	"grab-wall": {
		frames: [
			"frame-021",
			"frame-021"
		],
		frame_ms: 4125,
		loop: true
	},
	"climb-wall": {
		frames: [
			"frame-022",
			"frame-022",
			"frame-023",
			"frame-024",
			"frame-024",
			"frame-024",
			"frame-023",
			"frame-022"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			132,
			132,
			528,
			132,
			132,
			132
		]
	},
	"running-left": {
		frames: [
			"frame-000",
			"frame-001",
			"frame-000",
			"frame-002"
		],
		frame_ms: 198,
		loop: true
	},
	"running-right": {
		frames: [
			"frame-056",
			"frame-057",
			"frame-056",
			"frame-058"
		],
		frame_ms: 198,
		loop: true
	},
	peek: {
		frames: [
			"frame-000"
		],
		frame_ms: 160,
		loop: false
	}
};
const random_actions$3 = [
];
const action_mappings$3 = {
	"stage.idle": "idle",
	"stage.blink": "idle",
	"stage.wave": "cheer",
	"stage.talk": "cheer",
	"stage.think": "think",
	"stage.busy": "think",
	"stage.alert": "surprise",
	"stage.victory": "spin-celebrate",
	"stage.confused": "surprise",
	"stage.doze": "sleep",
	"stage.held": "drag",
	"stage.fall": "fall",
	"stage.jump": "jump",
	"stage.sit": "land",
	"stage.peek": "peek",
	"stage.walk-left": "running-left",
	"stage.walk-right": "running-right"
};
const calibration$3 = {
	left: 0,
	top: 0,
	right: 1,
	bottom: 1,
	baseline: 0.9928057553956835,
	offset_x: 0,
	offset_y: 0,
	left_eye_x: 0.2625,
	left_eye_y: 0.4245,
	right_eye_x: 0.4375,
	right_eye_y: 0.4245,
	head_top_x: 0.4188,
	head_top_y: 0.1439
};
const chibiterasuPackJson = {
	id: id$3,
	name: name$3,
	description: description$3,
	sheet: sheet$3,
	grid: grid$3,
	frames: frames$3,
	actions: actions$3,
	random_actions: random_actions$3,
	action_mappings: action_mappings$3,
	calibration: calibration$3
};

const id$2 = "builtin-nailong";
const name$2 = "奶龙";
const description$2 = "shine lock专属";
const sheet$2 = "sheet.webp";
const grid$2 = {
	cols: 8,
	rows: 6
};
const frames$2 = {
	"frame-000": 0,
	"frame-001": 1,
	"frame-002": 2,
	"frame-003": 3,
	"frame-004": 4,
	"frame-005": 5,
	"frame-006": 6,
	"frame-007": 7,
	"frame-008": 8,
	"frame-009": 9,
	"frame-010": 10,
	"frame-011": 11,
	"frame-012": 12,
	"frame-013": 13,
	"frame-014": 14,
	"frame-015": 15,
	"frame-016": 16,
	"frame-017": 17,
	"frame-018": 18,
	"frame-019": 19,
	"frame-020": 20,
	"frame-021": 21,
	"frame-022": 22,
	"frame-023": 23,
	"frame-024": 24,
	"frame-025": 25,
	"frame-026": 26,
	"frame-027": 27,
	"frame-028": 28,
	"frame-029": 29,
	"frame-030": 30,
	"frame-031": 31,
	"frame-032": 32,
	"frame-033": 33,
	"frame-034": 34,
	"frame-035": 35,
	"frame-036": 36,
	"frame-037": 37,
	"frame-038": 38,
	"frame-039": 39,
	"frame-040": 40,
	"frame-041": 41,
	"frame-042": 42,
	"frame-043": 43,
	"frame-044": 44,
	"frame-045": 45,
	"frame-046": 46,
	"frame-047": 47,
	idle: 0
};
const actions$2 = {
	stand: {
		frames: [
			"frame-000",
			"frame-001",
			"frame-002",
			"frame-003"
		],
		frame_ms: 792,
		loop: true,
		frame_durations: [
			792,
			396,
			594,
			792
		]
	},
	walk: {
		frames: [
			"frame-004",
			"frame-005",
			"frame-006",
			"frame-007"
		],
		frame_ms: 198,
		loop: true
	},
	run: {
		frames: [
			"frame-008",
			"frame-009",
			"frame-010",
			"frame-011"
		],
		frame_ms: 132,
		loop: true
	},
	dash: {
		frames: [
			"frame-012",
			"frame-013",
			"frame-014",
			"frame-015"
		],
		frame_ms: 99,
		loop: true
	},
	sit: {
		frames: [
			"frame-000",
			"frame-000"
		],
		frame_ms: 4125,
		loop: true
	},
	"relaxed-sit": {
		frames: [
			"frame-000",
			"frame-000"
		],
		frame_ms: 4125,
		loop: true
	},
	"sit-feet-down": {
		frames: [
			"frame-003",
			"frame-003"
		],
		frame_ms: 4125,
		loop: true
	},
	"dangle-feet": {
		frames: [
			"frame-000",
			"frame-001",
			"frame-000",
			"frame-016"
		],
		frame_ms: 825,
		loop: true
	},
	"look-up": {
		frames: [
			"frame-002",
			"frame-002"
		],
		frame_ms: 4125,
		loop: true
	},
	think: {
		frames: [
			"frame-002",
			"frame-002"
		],
		frame_ms: 4125,
		loop: true
	},
	lie: {
		frames: [
			"frame-017",
			"frame-018",
			"frame-019",
			"frame-016"
		],
		frame_ms: 990,
		loop: true
	},
	crawl: {
		frames: [
			"frame-018",
			"frame-018",
			"frame-019",
			"frame-019",
			"frame-019"
		],
		frame_ms: 924,
		loop: true,
		frame_durations: [
			924,
			132,
			132,
			132,
			792
		]
	},
	jump: {
		frames: [
			"frame-020",
			"frame-021",
			"frame-022",
			"frame-023"
		],
		frame_ms: 165,
		loop: true,
		frame_durations: [
			165,
			165,
			198,
			165
		]
	},
	fall: {
		frames: [
			"frame-023",
			"frame-023"
		],
		frame_ms: 264,
		loop: true
	},
	bounce: {
		frames: [
			"frame-023",
			"frame-000"
		],
		frame_ms: 132,
		loop: true
	},
	"hold-wall": {
		frames: [
			"frame-024",
			"frame-025"
		],
		frame_ms: 2970,
		loop: true
	},
	"climb-wall-up": {
		frames: [
			"frame-026",
			"frame-026",
			"frame-025",
			"frame-024",
			"frame-024",
			"frame-024",
			"frame-025",
			"frame-026"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			132,
			132,
			528,
			132,
			132,
			132
		]
	},
	"climb-wall-down": {
		frames: [
			"frame-026",
			"frame-026",
			"frame-025",
			"frame-024",
			"frame-024",
			"frame-024",
			"frame-025",
			"frame-026"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			132,
			132,
			528,
			132,
			132,
			132
		]
	},
	"hold-ceiling": {
		frames: [
			"frame-024",
			"frame-024"
		],
		frame_ms: 4125,
		loop: true
	},
	"crawl-ceiling": {
		frames: [
			"frame-027",
			"frame-026",
			"frame-028",
			"frame-029",
			"frame-030",
			"frame-029",
			"frame-031",
			"frame-025",
			"frame-027"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			40,
			66,
			132,
			99,
			66,
			165,
			132
		]
	},
	drag: {
		frames: [
			"frame-032",
			"frame-033",
			"frame-034",
			"frame-035",
			"frame-035"
		],
		frame_ms: 165,
		loop: true
	},
	resist: {
		frames: [
			"frame-033",
			"frame-034",
			"frame-033",
			"frame-034",
			"frame-034"
		],
		frame_ms: 165,
		loop: true,
		frame_durations: [
			165,
			165,
			165,
			165,
			1650
		]
	},
	"pull-out": {
		frames: [
			"frame-000",
			"frame-036",
			"frame-037",
			"frame-038",
			"frame-037",
			"frame-038",
			"frame-039"
		],
		frame_ms: 528,
		loop: false,
		frame_durations: [
			528,
			990,
			660,
			660,
			330,
			330,
			1320
		]
	},
	surprise: {
		frames: [
			"frame-000",
			"frame-036",
			"frame-037",
			"frame-038",
			"frame-039"
		],
		frame_ms: 528,
		loop: false,
		frame_durations: [
			528,
			990,
			660,
			660,
			1320
		]
	},
	split: {
		frames: [
			"frame-001",
			"frame-021",
			"frame-022",
			"frame-026",
			"frame-003",
			"frame-021",
			"frame-022",
			"frame-026",
			"frame-025",
			"frame-001",
			"frame-002",
			"frame-003"
		],
		frame_ms: 594,
		loop: false,
		frame_durations: [
			594,
			396,
			396,
			396,
			396,
			396,
			396,
			396,
			594,
			495,
			330,
			990
		]
	},
	cheer: {
		frames: [
			"frame-001",
			"frame-021",
			"frame-022",
			"frame-026",
			"frame-003"
		],
		frame_ms: 594,
		loop: false,
		frame_durations: [
			594,
			396,
			396,
			396,
			594
		]
	},
	"spin-celebrate": {
		frames: [
			"frame-021",
			"frame-022",
			"frame-026",
			"frame-003",
			"frame-022",
			"frame-026",
			"frame-025",
			"frame-003"
		],
		frame_ms: 396,
		loop: false,
		frame_durations: [
			396,
			396,
			396,
			396,
			396,
			396,
			594,
			990
		]
	},
	idle: {
		frames: [
			"frame-000",
			"frame-001",
			"frame-002",
			"frame-003"
		],
		frame_ms: 792,
		loop: true,
		frame_durations: [
			792,
			396,
			594,
			792
		]
	},
	follow: {
		frames: [
			"frame-012",
			"frame-013",
			"frame-014",
			"frame-015"
		],
		frame_ms: 99,
		loop: true
	},
	land: {
		frames: [
			"frame-023",
			"frame-000"
		],
		frame_ms: 132,
		loop: true
	},
	sleep: {
		frames: [
			"frame-017",
			"frame-018",
			"frame-019",
			"frame-016"
		],
		frame_ms: 990,
		loop: true
	},
	"grab-wall": {
		frames: [
			"frame-024",
			"frame-025"
		],
		frame_ms: 2970,
		loop: true
	},
	"climb-wall": {
		frames: [
			"frame-026",
			"frame-026",
			"frame-025",
			"frame-024",
			"frame-024",
			"frame-024",
			"frame-025",
			"frame-026"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			132,
			132,
			528,
			132,
			132,
			132
		]
	},
	"running-left": {
		frames: [
			"frame-004",
			"frame-005",
			"frame-006",
			"frame-007"
		],
		frame_ms: 198,
		loop: true
	},
	"running-right": {
		frames: [
			"frame-040",
			"frame-041",
			"frame-042",
			"frame-043"
		],
		frame_ms: 198,
		loop: true
	},
	peek: {
		frames: [
			"frame-000",
			"frame-001"
		],
		frame_ms: 140,
		frame_durations: [
			3200,
			140
		],
		loop: true
	}
};
const random_actions$2 = [
];
const action_mappings$2 = {
	"stage.idle": "idle",
	"stage.blink": "idle",
	"stage.wave": "cheer",
	"stage.talk": "cheer",
	"stage.think": "think",
	"stage.busy": "think",
	"stage.alert": "surprise",
	"stage.victory": "spin-celebrate",
	"stage.confused": "surprise",
	"stage.doze": "sleep",
	"stage.held": "drag",
	"stage.fall": "fall",
	"stage.jump": "jump",
	"stage.sit": "land",
	"stage.peek": "peek",
	"stage.walk-left": "running-left",
	"stage.walk-right": "running-right"
};
const calibration$2 = {
	left: 0,
	top: 0,
	right: 1,
	bottom: 1,
	baseline: 1,
	offset_x: 0,
	offset_y: 0,
	left_eye_x: 0.4583,
	left_eye_y: 0.3961,
	right_eye_x: 0.5979,
	right_eye_y: 0.3961,
	head_top_x: 0.5771,
	head_top_y: 0.1739
};
const action_baselines$1 = {
	stand: 0.8986,
	walk: 0.9179,
	run: 0.9179,
	dash: 0.9179,
	sit: 0.8986,
	"relaxed-sit": 0.8986,
	"look-up": 0.8986,
	think: 0.8986,
	lie: 0.7802,
	crawl: 0.7802,
	bounce: 0.8986,
	"pull-out": 0.8986,
	surprise: 0.8986,
	split: 0.8986,
	cheer: 0.8986,
	"spin-celebrate": 0.8986,
	idle: 0.8986,
	follow: 0.9179,
	land: 0.8986,
	sleep: 0.7802,
	peek: 0.8986,
	"running-left": 0.9179,
	"running-right": 0.9179
};
const nailongPackJson = {
	id: id$2,
	name: name$2,
	description: description$2,
	sheet: sheet$2,
	grid: grid$2,
	frames: frames$2,
	actions: actions$2,
	random_actions: random_actions$2,
	action_mappings: action_mappings$2,
	calibration: calibration$2,
	action_baselines: action_baselines$1
};

const id$1 = "builtin-kurisu";
const name$1 = "克里斯蒂娜助手";
const description$1 = "shine lock专属";
const sheet$1 = "sheet.webp";
const grid$1 = {
	cols: 8,
	rows: 8
};
const frames$1 = {
	"frame-000": 0,
	"frame-001": 1,
	"frame-002": 2,
	"frame-003": 3,
	"frame-004": 4,
	"frame-005": 5,
	"frame-006": 6,
	"frame-007": 7,
	"frame-008": 8,
	"frame-009": 9,
	"frame-010": 10,
	"frame-011": 11,
	"frame-012": 12,
	"frame-013": 13,
	"frame-014": 14,
	"frame-015": 15,
	"frame-016": 16,
	"frame-017": 17,
	"frame-018": 18,
	"frame-019": 19,
	"frame-020": 20,
	"frame-021": 21,
	"frame-022": 22,
	"frame-023": 23,
	"frame-024": 24,
	"frame-025": 25,
	"frame-026": 26,
	"frame-027": 27,
	"frame-028": 28,
	"frame-029": 29,
	"frame-030": 30,
	"frame-031": 31,
	"frame-032": 32,
	"frame-033": 33,
	"frame-034": 34,
	"frame-035": 35,
	"frame-036": 36,
	"frame-037": 37,
	"frame-038": 38,
	"frame-039": 39,
	"frame-040": 40,
	"frame-041": 41,
	"frame-042": 42,
	"frame-043": 43,
	"frame-044": 44,
	"frame-045": 45,
	"frame-046": 46,
	"frame-047": 47,
	"frame-048": 48,
	"frame-049": 49,
	"frame-050": 50,
	"frame-051": 51,
	"frame-052": 52,
	"frame-053": 53,
	"frame-054": 54,
	"frame-055": 55,
	"frame-056": 56,
	"frame-057": 57,
	"frame-058": 58,
	"frame-059": 59,
	"frame-060": 60,
	idle: 0
};
const actions$1 = {
	stand: {
		frames: [
			"frame-000",
			"frame-001",
			"frame-002",
			"frame-003"
		],
		frame_ms: 792,
		loop: true,
		frame_durations: [
			792,
			396,
			594,
			792
		]
	},
	walk: {
		frames: [
			"frame-004",
			"frame-005",
			"frame-006",
			"frame-007"
		],
		frame_ms: 231,
		loop: true
	},
	run: {
		frames: [
			"frame-008",
			"frame-009",
			"frame-010",
			"frame-011"
		],
		frame_ms: 132,
		loop: true
	},
	dash: {
		frames: [
			"frame-012",
			"frame-013",
			"frame-014",
			"frame-015"
		],
		frame_ms: 99,
		loop: true
	},
	sit: {
		frames: [
			"frame-016",
			"frame-016"
		],
		frame_ms: 4125,
		loop: true
	},
	"relaxed-sit": {
		frames: [
			"frame-016",
			"frame-016"
		],
		frame_ms: 4125,
		loop: true
	},
	"sit-feet-down": {
		frames: [
			"frame-017",
			"frame-017"
		],
		frame_ms: 4125,
		loop: true
	},
	"dangle-feet": {
		frames: [
			"frame-000",
			"frame-001",
			"frame-000",
			"frame-018"
		],
		frame_ms: 825,
		loop: true
	},
	"look-up": {
		frames: [
			"frame-016",
			"frame-017",
			"frame-019",
			"frame-020"
		],
		frame_ms: 924,
		loop: true,
		frame_durations: [
			924,
			924,
			924,
			1122
		]
	},
	think: {
		frames: [
			"frame-016",
			"frame-017",
			"frame-019",
			"frame-020"
		],
		frame_ms: 924,
		loop: true,
		frame_durations: [
			924,
			924,
			924,
			1122
		]
	},
	lie: {
		frames: [
			"frame-021",
			"frame-022",
			"frame-023",
			"frame-018"
		],
		frame_ms: 990,
		loop: true
	},
	crawl: {
		frames: [
			"frame-022",
			"frame-022",
			"frame-023",
			"frame-023",
			"frame-023"
		],
		frame_ms: 924,
		loop: true,
		frame_durations: [
			924,
			132,
			132,
			132,
			792
		]
	},
	jump: {
		frames: [
			"frame-024",
			"frame-025",
			"frame-026",
			"frame-027"
		],
		frame_ms: 198,
		loop: true
	},
	fall: {
		frames: [
			"frame-028",
			"frame-029",
			"frame-030"
		],
		frame_ms: 264,
		loop: true
	},
	bounce: {
		frames: [
			"frame-029",
			"frame-030",
			"frame-030",
			"frame-031"
		],
		frame_ms: 165,
		loop: true,
		frame_durations: [
			165,
			165,
			165,
			264
		]
	},
	"hold-wall": {
		frames: [
			"frame-032",
			"frame-032"
		],
		frame_ms: 4125,
		loop: true
	},
	"climb-wall-up": {
		frames: [
			"frame-033",
			"frame-033",
			"frame-034",
			"frame-035",
			"frame-035",
			"frame-035",
			"frame-034",
			"frame-033"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			132,
			132,
			528,
			132,
			132,
			132
		]
	},
	"climb-wall-down": {
		frames: [
			"frame-033",
			"frame-033",
			"frame-034",
			"frame-035",
			"frame-035",
			"frame-035",
			"frame-034",
			"frame-033"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			132,
			132,
			528,
			132,
			132,
			132
		]
	},
	"hold-ceiling": {
		frames: [
			"frame-035",
			"frame-035"
		],
		frame_ms: 4125,
		loop: true
	},
	"crawl-ceiling": {
		frames: [
			"frame-032",
			"frame-034",
			"frame-036",
			"frame-037",
			"frame-038",
			"frame-037",
			"frame-039",
			"frame-034",
			"frame-032"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			40,
			66,
			132,
			99,
			66,
			165,
			132
		]
	},
	drag: {
		frames: [
			"frame-040",
			"frame-041",
			"frame-042",
			"frame-043",
			"frame-044"
		],
		frame_ms: 165,
		loop: true
	},
	resist: {
		frames: [
			"frame-041",
			"frame-042",
			"frame-041",
			"frame-042",
			"frame-042"
		],
		frame_ms: 165,
		loop: true,
		frame_durations: [
			165,
			165,
			165,
			165,
			1650
		]
	},
	"pull-out": {
		frames: [
			"frame-024",
			"frame-025",
			"frame-026",
			"frame-027",
			"frame-031"
		],
		frame_ms: 462,
		loop: false,
		frame_durations: [
			462,
			462,
			462,
			462,
			924
		]
	},
	surprise: {
		frames: [
			"frame-024",
			"frame-025",
			"frame-026",
			"frame-027",
			"frame-031"
		],
		frame_ms: 462,
		loop: false,
		frame_durations: [
			462,
			462,
			462,
			462,
			924
		]
	},
	split: {
		frames: [
			"frame-045",
			"frame-046",
			"frame-047",
			"frame-048",
			"frame-049",
			"frame-050",
			"frame-051",
			"frame-052",
			"frame-053",
			"frame-054",
			"frame-055",
			"frame-048",
			"frame-056"
		],
		frame_ms: 330,
		loop: false,
		frame_durations: [
			330,
			330,
			330,
			396,
			396,
			396,
			396,
			396,
			396,
			396,
			396,
			594,
			594
		]
	},
	cheer: {
		frames: [
			"frame-045",
			"frame-046",
			"frame-047",
			"frame-048"
		],
		frame_ms: 396,
		loop: false,
		frame_durations: [
			396,
			396,
			396,
			594
		]
	},
	"spin-celebrate": {
		frames: [
			"frame-049",
			"frame-050",
			"frame-051",
			"frame-052",
			"frame-053",
			"frame-054",
			"frame-055",
			"frame-056"
		],
		frame_ms: 396,
		loop: false,
		frame_durations: [
			396,
			396,
			396,
			396,
			396,
			396,
			594,
			594
		]
	},
	idle: {
		frames: [
			"frame-000",
			"frame-001",
			"frame-002",
			"frame-003"
		],
		frame_ms: 792,
		loop: true,
		frame_durations: [
			792,
			396,
			594,
			792
		]
	},
	follow: {
		frames: [
			"frame-012",
			"frame-013",
			"frame-014",
			"frame-015"
		],
		frame_ms: 99,
		loop: true
	},
	land: {
		frames: [
			"frame-029",
			"frame-030",
			"frame-030",
			"frame-031"
		],
		frame_ms: 165,
		loop: true,
		frame_durations: [
			165,
			165,
			165,
			264
		]
	},
	sleep: {
		frames: [
			"frame-021",
			"frame-022",
			"frame-023",
			"frame-018"
		],
		frame_ms: 990,
		loop: true
	},
	"grab-wall": {
		frames: [
			"frame-032",
			"frame-032"
		],
		frame_ms: 4125,
		loop: true
	},
	"climb-wall": {
		frames: [
			"frame-033",
			"frame-033",
			"frame-034",
			"frame-035",
			"frame-035",
			"frame-035",
			"frame-034",
			"frame-033"
		],
		frame_ms: 528,
		loop: true,
		frame_durations: [
			528,
			132,
			132,
			132,
			528,
			132,
			132,
			132
		]
	},
	"running-left": {
		frames: [
			"frame-004",
			"frame-005",
			"frame-006",
			"frame-007"
		],
		frame_ms: 231,
		loop: true
	},
	"running-right": {
		frames: [
			"frame-057",
			"frame-058",
			"frame-059",
			"frame-060"
		],
		frame_ms: 231,
		loop: true
	},
	peek: {
		frames: [
			"frame-000",
			"frame-001"
		],
		frame_ms: 140,
		frame_durations: [
			3200,
			140
		],
		loop: true
	}
};
const random_actions$1 = [
];
const action_mappings$1 = {
	"stage.idle": "idle",
	"stage.blink": "idle",
	"stage.wave": "cheer",
	"stage.talk": "cheer",
	"stage.think": "think",
	"stage.busy": "think",
	"stage.alert": "surprise",
	"stage.victory": "spin-celebrate",
	"stage.confused": "surprise",
	"stage.doze": "sleep",
	"stage.held": "drag",
	"stage.fall": "fall",
	"stage.jump": "jump",
	"stage.sit": "land",
	"stage.peek": "peek",
	"stage.walk-left": "running-left",
	"stage.walk-right": "running-right"
};
const calibration$1 = {
	left: 0,
	top: 0,
	right: 1,
	bottom: 1,
	baseline: 1,
	offset_x: 0,
	offset_y: 0,
	left_eye_x: 0.4219,
	left_eye_y: 0.3841,
	right_eye_x: 0.5573,
	right_eye_y: 0.3841,
	head_top_x: 0.4948,
	head_top_y: 0.1401
};
const action_baselines = {
	stand: 0.9348,
	walk: 0.9348,
	run: 0.9348,
	dash: 0.9348,
	sit: 0.8357,
	"relaxed-sit": 0.8357,
	"look-up": 0.8357,
	think: 0.8357,
	lie: 0.6908,
	crawl: 0.686,
	bounce: 0.9348,
	"pull-out": 0.9324,
	surprise: 0.9324,
	split: 0.9662,
	cheer: 0.9203,
	"spin-celebrate": 0.9662,
	idle: 0.9348,
	follow: 0.9348,
	land: 0.9348,
	sleep: 0.6908,
	peek: 0.9348,
	"running-left": 0.9348,
	"running-right": 0.9348
};
const kurisuPackJson = {
	id: id$1,
	name: name$1,
	description: description$1,
	sheet: sheet$1,
	grid: grid$1,
	frames: frames$1,
	actions: actions$1,
	random_actions: random_actions$1,
	action_mappings: action_mappings$1,
	calibration: calibration$1,
	action_baselines: action_baselines
};

const id = "builtin-kurisu-z256";
const name = "克里斯蒂娜（z256专属）";
const description = "z256专属";
const grid = {
	cols: 8,
	rows: 11
};
const frames = {
	idle: 0,
	"idle-1": 1,
	blink: 2,
	"idle-2": 3,
	"idle-3": 4,
	"idle-4": 5,
	"wave-ready": 24,
	"wave-1": 25,
	"wave-2": 26,
	"wave-3": 27,
	"cheer-ready": 32,
	"cheer-1": 33,
	"cheer-2": 34,
	"cheer-3": 35,
	"cheer-4": 36,
	confused: 41,
	skeptical: 42,
	thinking: 43,
	facepalm: 44,
	sleep: 46,
	"gesture-1": 50,
	"gesture-2": 51,
	"gesture-3": 52
};
const actions = {
	idle: {
		frames: [
			"idle",
			"idle-1",
			"blink",
			"idle-2",
			"idle-3",
			"idle-4"
		],
		frame_ms: 700,
		loop: true
	},
	thinking: {
		frames: [
			"thinking"
		],
		frame_ms: 160,
		loop: false
	},
	wave: {
		frames: [
			"wave-ready",
			"wave-1",
			"wave-2",
			"wave-3",
			"wave-2",
			"wave-1",
			"wave-ready"
		],
		frame_ms: 220,
		loop: false
	},
	"happy-jump": {
		frames: [
			"cheer-ready",
			"cheer-1",
			"cheer-2",
			"cheer-3",
			"cheer-4"
		],
		frame_ms: 220,
		loop: false
	},
	success: {
		frames: [
			"cheer-ready",
			"cheer-1",
			"cheer-2",
			"cheer-3",
			"cheer-4"
		],
		frame_ms: 220,
		loop: false
	},
	confused: {
		frames: [
			"confused"
		],
		frame_ms: 160,
		loop: false
	},
	warning: {
		frames: [
			"skeptical"
		],
		frame_ms: 160,
		loop: false
	},
	error: {
		frames: [
			"facepalm"
		],
		frame_ms: 160,
		loop: false
	},
	sleep: {
		frames: [
			"sleep"
		],
		frame_ms: 160,
		loop: false
	},
	scan: {
		frames: [
			"gesture-1",
			"gesture-2",
			"gesture-3"
		],
		frame_ms: 320,
		loop: true
	},
	peek: {
		frames: [
			"idle",
			"blink"
		],
		frame_ms: 140,
		frame_durations: [
			3200,
			140
		],
		loop: true
	}
};
const random_actions = [
	"wave",
	"happy-jump"
];
const action_mappings = {
};
const calibration = {
	left: 0.1042,
	top: 0.0192,
	right: 0.8958,
	bottom: 0.9808,
	baseline: 0.9808,
	offset_x: 0,
	offset_y: 0,
	eye_x: 0.51,
	eye_y: 0.205,
	left_eye_x: 0.4158,
	left_eye_y: 0.2355,
	right_eye_x: 0.5211,
	right_eye_y: 0.218,
	head_top_x: 0.4769,
	head_top_y: 0.0192
};
const codex_version = "v2";
const sheet = "sheet.webp";
const z256KurisuPackJson = {
	id: id,
	name: name,
	description: description,
	grid: grid,
	frames: frames,
	actions: actions,
	random_actions: random_actions,
	action_mappings: action_mappings,
	calibration: calibration,
	codex_version: codex_version,
	sheet: sheet
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
    peek: action([rowFrames.idle[0]]),
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
      const durations = entry?.frame_durations;
      if (durations !== void 0 && durations !== null) {
        if (!Array.isArray(durations) || durations.length !== sequence.length)
          errors.push(`actions.${key}.frame_durations 必须与帧序列等长`);
        else
          actions[key].frame_durations = durations.map(
            (value2) => integer(value2, `actions.${key}.frame_durations`, 40, 5e3, errors)
          );
      }
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
  const actionBaselines = {};
  try {
    calibration = parseCalibration(data.calibration);
    if (data.action_baselines !== void 0) {
      if (!["builtin-chibiterasu", "builtin-nailong", "builtin-kurisu"].includes(String(id)))
        throw new Error("action_baselines 仅供内置逐帧形象使用");
      if (!data.action_baselines || typeof data.action_baselines !== "object" || Array.isArray(data.action_baselines))
        throw new Error("action_baselines 必须是动作名到基线的对象");
      for (const [action, baseline] of Object.entries(data.action_baselines)) {
        if (!Object.hasOwn(actions, action)) throw new Error("action_baselines 引用了未定义的动作");
        actionBaselines[action] = parseCalibration({ ...calibration, baseline }).baseline;
      }
    }
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
      ...data.action_baselines !== void 0 ? { action_baselines: actionBaselines } : {},
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
  const oldPeek = actions.peek;
  const oldPeekIndices = layout.version === "v2" ? [72, 84] : [64];
  const legacyPeek = oldPeek?.frames.length === 1 && oldPeekIndices.includes(frames[oldPeek.frames[0]]) && oldPeek.frame_ms === 160 && !oldPeek.loop && !Object.values(pack.action_mappings ?? {}).includes("peek");
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
    if (actions[key] && !(key === "peek" && legacyPeek)) continue;
    actions[key] = { ...action, frames: action.frames.map((name) => frameName(defaults.frames[name])) };
  }
  return { ...pack, frames, actions };
}
const builtinSources = {
  [BUILTIN_PACK_ID]: builtinPackJson,
  "builtin-chibiterasu": chibiterasuPackJson,
  "builtin-nailong": nailongPackJson,
  "builtin-kurisu": kurisuPackJson,
  "builtin-kurisu-z256": z256KurisuPackJson
};
const BUILTIN_PACKS = Object.fromEntries(
  Object.entries(builtinSources).map(([id, source]) => {
    const { pack } = validatePack(source);
    if (!pack) throw new Error(`Invalid built-in pack: ${id}`);
    return [id, withCodexStageActions({ ...pack, id })];
  })
);
const BUILTIN_PACK = BUILTIN_PACKS[BUILTIN_PACK_ID];
const ASSET_BASE = import.meta.url;
function builtinAsset(file, base = ASSET_BASE, key = BUILTIN_PACK_ID) {
  if (!Object.hasOwn(BUILTIN_PACKS, key)) throw new Error("Unknown built-in pack");
  return new URL(`packs/${key}/${file}`, base).href;
}
function resolveAction(pack, action, intent, thinking, options = {}) {
  if (options.nativeAction && pack.actions[options.nativeAction])
    return { key: options.nativeAction, action: pack.actions[options.nativeAction] };
  const mappings = options.mappings ?? pack.action_mappings ?? {};
  const candidates = [
    options.mappingKey ? mappings[options.mappingKey] : null,
    action ? mappings[`action.${action}`] ?? action : null,
    action === "peek" ? "idle" : null,
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
  stand: "站立",
  walk: "行走",
  run: "奔跑",
  dash: "冲刺",
  follow: "跟随姿态",
  "relaxed-sit": "放松坐下",
  "sit-feet-down": "垂腿坐下",
  "dangle-feet": "晃腿",
  "look-up": "抬头",
  think: "思考",
  lie: "躺下",
  crawl: "匍匐",
  jump: "跳跃",
  fall: "下落",
  land: "落地",
  bounce: "弹跳",
  "hold-wall": "挂墙姿态",
  "grab-wall": "抓墙姿态",
  "climb-wall": "爬墙姿态",
  "climb-wall-up": "向上攀爬",
  "climb-wall-down": "向下攀爬",
  "hold-ceiling": "悬挂姿态",
  "crawl-ceiling": "爬顶姿态",
  drag: "被拖起",
  resist: "挣扎",
  "pull-out": "拔起",
  surprise: "惊讶",
  split: "分身姿态",
  cheer: "欢呼",
  "spin-celebrate": "旋转庆祝",
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
  peek: { label: "底角露眼", action: "peek", group: "移动交互" },
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
function stageAction(pose, facingLeft, peeking = false) {
  const key = peeking ? "peek" : pose.startsWith("walk") ? facingLeft ? "walk-left" : "walk-right" : pose;
  return { key: `stage.${key}`, action: STAGE_ACTIONS[key]?.action ?? "idle" };
}
function nativeChoices(pack) {
  const keys = pack.codex_version ? NATIVE_ACTIONS.filter((key) => pack.actions[key]) : [];
  const signature = (key) => pack.actions[key].frames.map((frame) => pack.frames[frame]).join(",");
  const seen = new Set(keys.map(signature));
  for (const key of Object.keys(pack.actions)) {
    if (key.startsWith("look-") || keys.includes(key)) continue;
    const peekFrame = pack.actions.idle?.frames[0];
    if (pack.codex_version && key === "peek" && pack.actions[key].frames.length === 1 && peekFrame && pack.frames[pack.actions[key].frames[0]] === pack.frames[peekFrame])
      continue;
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

const {onBeforeUnmount,onMounted} = await importShared('vue');

const editors = /* @__PURE__ */ new Set();
const listeners = /* @__PURE__ */ new Set();
function registerEditor() {
  const token = Symbol();
  editors.add(token);
  if (editors.size === 1) for (const listener of listeners) listener(true);
  return () => {
    if (editors.delete(token) && !editors.size) for (const listener of listeners) listener(false);
  };
}
function useEditorPresence() {
  let release;
  onMounted(() => {
    release = registerEditor();
  });
  onBeforeUnmount(() => release?.());
}
function onEditorPresence(listener) {
  listeners.add(listener);
  listener(editors.size > 0);
  return () => {
    listeners.delete(listener);
  };
}

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

export { ACTION_LABELS as A, BUILTIN_PACKS as B, DEFAULT_CALIBRATION as D, HOST_ACTIONS as H, LANDMARKS as L, PACK_UPDATED_EVENT as P, _export_sfc as _, suggestedLandmark as a, sameCalibration as b, calibrationPoint as c, BUILTIN_PACK_ID as d, BUILTIN_PACK as e, builtinAsset as f, calibrationForAction as g, calibrationEye as h, mirrorFace as i, calibrationLayout as j, framePosition as k, sameMappings as l, moveCalibrationPoint as m, buildCodexPetPack as n, onEditorPresence as o, parseCalibration as p, mappingRows as q, resolveAction as r, stageAction as s, nativeChoices as t, useEditorPresence as u, validatePack as v, withCodexStageActions as w, HOST_INTENTS as x };
