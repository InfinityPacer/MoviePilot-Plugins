function readViewport(state, browserBounds = true) {
  const base = state?.viewport ?? {
    width: window.innerWidth,
    height: window.innerHeight,
    keyboardInset: 0,
    safeArea: { top: 0, right: 0, bottom: 0, left: 0 }
  };
  if (!browserBounds) return base;
  const visual = window.visualViewport;
  const width = Math.min(base.width, window.innerWidth);
  const height = Math.min(base.height, window.innerHeight);
  const left = Math.max(base.safeArea.left, (visual?.offsetLeft ?? 0) + base.safeArea.left);
  const top = Math.max(base.safeArea.top, (visual?.offsetTop ?? 0) + base.safeArea.top);
  const right = Math.min(width, visual ? visual.offsetLeft + visual.width : width) - base.safeArea.right;
  const bottom = Math.min(base.height - base.keyboardInset, height, visual ? visual.offsetTop + visual.height : height) - base.safeArea.bottom;
  return {
    width,
    height,
    keyboardInset: 0,
    safeArea: { left, top, right: Math.max(0, width - right), bottom: Math.max(0, height - bottom) }
  };
}
function groundTop(viewport, charHeight) {
  const floor = viewport.height - viewport.safeArea.bottom - viewport.keyboardInset;
  return Math.max(viewport.safeArea.top, floor - charHeight);
}
function xBounds(viewport, charWidth) {
  const min = viewport.safeArea.left;
  const max = Math.max(min, viewport.width - viewport.safeArea.right - charWidth);
  return [min, max];
}
function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
function xToRatio(x, bounds) {
  const [min, max] = bounds;
  if (max <= min) return 0;
  return clamp((x - min) / (max - min), 0, 1);
}
function ratioToX(ratio, bounds) {
  const [min, max] = bounds;
  return min + clamp(ratio, 0, 1) * (max - min);
}
function blockedSpan(panel, standY, charWidth, charHeight = 0) {
  if (!panel || panel.width <= 0 || panel.height <= 0) return null;
  if (panel.y + panel.height <= standY) return null;
  if (charHeight > 0 && panel.y >= standY + charHeight) return null;
  return [panel.x - charWidth, panel.x + panel.width];
}
function isBlocked(x, span) {
  return !!span && x > span[0] && x < span[1];
}
function pickWalkTarget(random, current, bounds, span, minDistance = 40) {
  let [min, max] = bounds;
  if (span) {
    if (current <= span[0]) max = Math.min(max, span[0]);
    else if (current >= span[1]) min = Math.max(min, span[1]);
  }
  if (max - min < minDistance) return null;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const target = min + random() * (max - min);
    if (Math.abs(target - current) >= minDistance && !isBlocked(target, span)) return target;
  }
  return null;
}
function avoidPanel(position, panel, viewport, size) {
  if (!panel || intersectionArea({ ...position, ...size }, panel) === 0) return position;
  const bounds = freeBounds(viewport, size.width, size.height);
  const candidates = [
    { x: panel.x - size.width, y: position.y },
    { x: panel.x + panel.width, y: position.y },
    { x: position.x, y: panel.y - size.height },
    { x: position.x, y: panel.y + panel.height }
  ].map((point) => ({ x: clamp(point.x, ...bounds.x), y: clamp(point.y, ...bounds.y) })).filter((point) => intersectionArea({ ...point, ...size }, panel) === 0).sort((a, b) => Math.hypot(a.x - position.x, a.y - position.y) - Math.hypot(b.x - position.x, b.y - position.y));
  return candidates[0] ?? position;
}
function sameRect(a, b) {
  if (!a || !b) return a === b;
  return Math.round(a.x) === Math.round(b.x) && Math.round(a.y) === Math.round(b.y) && Math.round(a.width) === Math.round(b.width) && Math.round(a.height) === Math.round(b.height);
}
const MIN_SURFACE_WIDTH = 120;
function floorLine(viewport) {
  return viewport.height - viewport.safeArea.bottom - viewport.keyboardInset;
}
function standable(box, viewport, charHeight, panel) {
  if (box.right - box.left < MIN_SURFACE_WIDTH) return false;
  if (box.right <= viewport.safeArea.left || box.left >= viewport.width - viewport.safeArea.right) return false;
  if (box.top - charHeight < viewport.safeArea.top) return false;
  if (box.top >= floorLine(viewport)) return false;
  if (panel && box.left >= panel.x && box.right <= panel.x + panel.width && box.top >= panel.y && box.top <= panel.y + panel.height) {
    return false;
  }
  return true;
}
function findLanding(boxes, centerX, feetY) {
  let best = null;
  for (const box of boxes) {
    if (centerX < box.left || centerX > box.right || box.top < feetY - 2) continue;
    if (!best || box.top < best.top) best = box;
  }
  return best;
}
function computeLanding(mode, boxes, position, viewport, size, dropSnap = 0) {
  const ground = groundTop(viewport, size.height);
  if (mode === "free") return { y: clamp(position.y, viewport.safeArea.top, ground), surface: null };
  if (mode === "surfaces") {
    const centerX = position.x + size.width / 2;
    const feetY = position.y + size.height;
    const nearby = dropSnap > 0 ? boxes.filter((box) => centerX >= box.left && centerX <= box.right && Math.abs(box.top - feetY) <= dropSnap).sort((a, b) => Math.abs(a.top - feetY) - Math.abs(b.top - feetY))[0] : null;
    const surface = nearby ?? findLanding(boxes, centerX, feetY);
    if (surface) return { y: surface.top - size.height, surface };
  }
  return { y: ground, surface: null };
}
function surfaceXBounds(box, viewport, charWidth) {
  const [minX, maxX] = xBounds(viewport, charWidth);
  const min = Math.max(minX, box.left - charWidth / 2);
  const max = Math.min(maxX, box.right - charWidth / 2);
  return [min, Math.max(min, max)];
}
const SUPPORT_EPSILON = 1e-7;
function checkSupport(previous, next, centerX, viewport, charHeight, panel, charWidth = 0) {
  if (!next || !standable(next, viewport, charHeight, panel)) return { kind: "fall" };
  const dx = next.left - previous.left;
  const center = centerX + dx;
  const [minX, maxX] = xBounds(viewport, charWidth);
  if (center < next.left - SUPPORT_EPSILON || center > next.right + SUPPORT_EPSILON || center - charWidth / 2 < minX - SUPPORT_EPSILON || center - charWidth / 2 > maxX + SUPPORT_EPSILON)
    return { kind: "fall" };
  return { kind: "follow", dx, y: next.top - charHeight };
}
function freeBounds(viewport, charWidth, charHeight) {
  return { x: xBounds(viewport, charWidth), y: [viewport.safeArea.top, groundTop(viewport, charHeight)] };
}
function pickFreeTarget(random, current, bounds, minDistance = 60) {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const target = {
      x: bounds.x[0] + random() * (bounds.x[1] - bounds.x[0]),
      y: bounds.y[0] + random() * (bounds.y[1] - bounds.y[0])
    };
    if (Math.hypot(target.x - current.x, target.y - current.y) >= minDistance) return target;
  }
  return null;
}
const MOBILE_SCALE = 0.8;
function effectiveScale(scale, isMobile) {
  return isMobile ? scale * MOBILE_SCALE : scale;
}
function intersectionArea(a, b) {
  const width = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const height = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  return width > 0 && height > 0 ? width * height : 0;
}
const MAX_CLEAR_CANDIDATES = 12;
const CONTROL_COVER_RATIO = 0.1;
const CONTROL_HIDDEN_RATIO = 0.5;
function coversAny(rect, controls, bodyArea = rect.width * rect.height) {
  return controls.some((control) => {
    const overlap = intersectionArea(rect, control);
    if (overlap <= 0) return false;
    const controlArea = control.width * control.height;
    return overlap > bodyArea * CONTROL_COVER_RATIO || controlArea > 0 && overlap > controlArea * CONTROL_HIDDEN_RATIO;
  });
}
function pickClearX(current, bounds, isClear, step, maxCandidates = MAX_CLEAR_CANDIDATES) {
  const [min, max] = bounds;
  const stride = Math.max(8, step);
  const limit = Math.ceil((max - min) / stride) + 1;
  const tried = /* @__PURE__ */ new Set();
  for (let index = 1; index <= limit; index += 1) {
    for (const candidate of [current - index * stride, current + index * stride]) {
      const x = Math.round(clamp(candidate, min, max));
      if (Math.abs(x - current) < 1 || tried.has(x)) continue;
      if (tried.size >= maxCandidates) return null;
      tried.add(x);
      if (isClear(x)) return x;
    }
  }
  return null;
}
function nearestEdge(x, bounds) {
  return x - bounds[0] <= bounds[1] - x ? bounds[0] : bounds[1];
}
function hopVelocity(from, to, gravity, lift) {
  const apex = Math.min(from.y, to.y) - lift;
  const up = Math.sqrt(2 * gravity * (from.y - apex));
  const time = up / gravity + Math.sqrt(2 * (to.y - apex) / gravity);
  return { vx: (to.x - from.x) / time, vy: -up };
}

const PEEK_EDGES = ["bottom", "left", "right"];
const PEEK_TOUCH_SIZE = 48;
const PEEK_TUCK = 1.06;
const PEEK_TILT = 35;
const DEFAULT_PEEK_ANGLES = { bottom: 0, left: PEEK_TILT, right: PEEK_TILT };
const PEEK_PREVIEW_MAX_ANGLE = 45;
const PEEK_BOTTOM_INSET = 8;
const PEEK_TILT_SECONDS = 0.35;
const PEEK_RISE_SECONDS = 1.6;
function normalizePeekAngle(value, fallback = PEEK_TILT) {
  return typeof value === "number" && Number.isFinite(value) ? clamp(value, 0, PEEK_PREVIEW_MAX_ANGLE) : fallback;
}
function normalizePeekAngles(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    bottom: normalizePeekAngle(source.bottom, DEFAULT_PEEK_ANGLES.bottom),
    left: normalizePeekAngle(source.left),
    right: normalizePeekAngle(source.right)
  };
}
function isPeekEdge(value) {
  return PEEK_EDGES.some((edge) => edge === value);
}
function peekHome(position, view, size, edge = "bottom") {
  const range = freeBounds(view, size.width, size.height);
  return {
    x: edge === "left" ? range.x[0] : edge === "right" ? range.x[1] : clamp(position.x, ...range.x),
    y: edge === "bottom" ? range.y[1] : clamp(position.y, Math.max(range.y[0], range.y[1] - size.height), range.y[1])
  };
}
function dropPeekEdge(position, view, size) {
  const range = freeBounds(view, size.width, size.height);
  const threshold = Math.min(20, Math.min(size.width, size.height) * 0.18);
  const left = Math.abs(position.x - range.x[0]);
  const right = Math.abs(position.x - range.x[1]);
  const side = Math.min(left, right);
  const bottom = Math.abs(range.y[1] - position.y);
  if (side > threshold) return null;
  if (bottom <= threshold && bottom <= side) return "bottom";
  if (position.y < Math.max(range.y[0], range.y[1] - size.height) || position.y > range.y[1] + threshold) return null;
  return left <= right ? "left" : "right";
}
function viewRect(view) {
  return {
    x: view.safeArea.left,
    y: view.safeArea.top,
    width: Math.max(1, view.width - view.safeArea.left - view.safeArea.right),
    height: Math.max(1, floorLine(view) - view.safeArea.top)
  };
}
function intersect(rect, view) {
  const x = clamp(rect.x, view.x, view.x + view.width);
  const y = clamp(rect.y, view.y, view.y + view.height);
  return {
    x,
    y,
    width: Math.max(0, Math.min(rect.x + rect.width, view.x + view.width) - x),
    height: Math.max(0, Math.min(rect.y + rect.height, view.y + view.height) - y)
  };
}
function touchRect(visible, view) {
  const width = Math.min(view.width, Math.max(PEEK_TOUCH_SIZE, visible.width));
  const height = Math.min(view.height, Math.max(PEEK_TOUCH_SIZE, visible.height));
  return {
    x: clamp(visible.x + visible.width / 2 - width / 2, view.x, view.x + view.width - width),
    y: clamp(visible.y + visible.height / 2 - height / 2, view.y, view.y + view.height - height),
    width,
    height
  };
}
function peekPanelShift(rect, panel, view, edge = "bottom") {
  const bounds = viewRect(view);
  const horizontal = edge === "bottom";
  const start = horizontal ? rect.x : rect.y;
  const length = horizontal ? rect.width : rect.height;
  const min = horizontal ? bounds.x : Math.max(bounds.y, bounds.y + bounds.height - length * 2);
  const max = (horizontal ? bounds.x + bounds.width : bounds.y + bounds.height) - length;
  const panelStart = horizontal ? panel.x : panel.y;
  const panelEnd = panelStart + (horizontal ? panel.width : panel.height);
  const target = [panelStart - length - 0.01, panelEnd + 0.01].filter((value) => value >= min && value <= max).sort((a, b) => Math.abs(a - start) - Math.abs(b - start))[0];
  if (target === void 0) return null;
  return horizontal ? { x: target - start, y: 0 } : { x: 0, y: target - start };
}
function peekLayout(position, size, view, edge, progress, eye, revealing = true, bottomTilt = 1, angle = DEFAULT_PEEK_ANGLES[edge ?? "bottom"]) {
  const normal = { ...position, ...size };
  if (!edge) return { fromLeft: false, visible: normal, hit: normal, artwork: { ...normal, rotation: 0 }, eye: null };
  const bounds = viewRect(view);
  const horizontal = edge === "bottom";
  const anchor = eye ?? { x: 0.5, y: 0.45 };
  const amount = clamp(progress, 0, PEEK_TUCK);
  const rise = clamp((PEEK_TUCK - amount) / (PEEK_TUCK - 1), 0, 1);
  const eased = rise * rise * (3 - 2 * rise);
  const turn = clamp(bottomTilt, 0, 1);
  const poseAmount = (horizontal ? turn * turn * (3 - 2 * turn) : eased) * Math.min(1, amount);
  const onLeft = edge === "left" || horizontal && position.x + size.width / 2 <= bounds.x + bounds.width / 2;
  const side = (onLeft ? 1 : -1) * (horizontal ? -1 : 1);
  const tilt = revealing ? normalizePeekAngle(angle, DEFAULT_PEEK_ANGLES[edge]) * poseAmount : 0;
  const rotation = tilt === 0 ? 0 : side * tilt;
  const radians = rotation * Math.PI / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const scale = Math.min(
    1,
    horizontal ? bounds.width / (Math.abs(cos) * size.width + Math.abs(sin) * size.height) : bounds.height / (Math.abs(sin) * size.width + Math.abs(cos) * size.height)
  );
  const width = size.width * scale;
  const height = size.height * scale;
  const local = { x: (anchor.x - 0.5) * width, y: (anchor.y - 0.5) * height };
  const offset = { x: local.x * cos - local.y * sin, y: local.x * sin + local.y * cos };
  const project = (point) => ({
    x: (point.x - 0.5) * width * cos - (point.y - 0.5) * height * sin,
    y: (point.x - 0.5) * width * sin + (point.y - 0.5) * height * cos
  });
  const eyes = eye?.eyes?.map(project);
  const headTop = eye?.headTop ? project(eye.headTop) : null;
  const rotatedWidth = Math.abs(cos) * width + Math.abs(sin) * height;
  const rotatedHeight = Math.abs(sin) * width + Math.abs(cos) * height;
  const center = { x: position.x + size.width / 2, y: position.y + size.height / 2 };
  if (horizontal) {
    center.x = clamp(center.x, bounds.x + rotatedWidth / 2, bounds.x + bounds.width - rotatedWidth / 2);
    if (revealing) {
      const inset = Math.min(bounds.width / 2, width * 0.25 + 4);
      const eyeX = clamp(
        position.x + (onLeft ? inset : size.width - inset),
        bounds.x + inset,
        bounds.x + bounds.width - inset
      );
      let headCenter = eyeX - offset.x;
      if (eyes && headTop) {
        const padding = Math.max(4, Math.abs(eye.eyes[1].x - eye.eyes[0].x) * width / 2);
        const xs = [headTop.x, ...eyes.map((point) => point.x)];
        const corner = clamp(position.x + (onLeft ? 0 : size.width), bounds.x, bounds.x + bounds.width);
        const clearance = Math.min(padding + PEEK_BOTTOM_INSET, (bounds.width - Math.max(...xs) + Math.min(...xs)) / 2);
        headCenter = clamp(
          onLeft ? corner + clearance - Math.min(...xs) : corner - clearance - Math.max(...xs),
          bounds.x + clearance - Math.min(...xs),
          bounds.x + bounds.width - clearance - Math.max(...xs)
        );
      } else {
        headCenter += onLeft ? PEEK_BOTTOM_INSET : -PEEK_BOTTOM_INSET;
      }
      center.x += (headCenter - center.x) * poseAmount;
    }
  } else center.y = clamp(center.y, bounds.y + rotatedHeight / 2, bounds.y + bounds.height - rotatedHeight / 2);
  const axis = horizontal ? "y" : "x";
  const outward = edge === "left" ? -1 : 1;
  const boundary = horizontal ? bounds.y + bounds.height : edge === "left" ? bounds.x : bounds.x + bounds.width;
  const hidden = boundary + outward * ((horizontal ? rotatedHeight : rotatedWidth) / 2 + 4);
  const eyePadding = Math.max(2, height * 0.025);
  const upright = horizontal && tilt === 0;
  let looking = boundary + outward * (upright && eye ? -eyePadding : Math.max(1, height * 0.01)) - offset[axis];
  if (eyes) {
    const selected = [...eyes].sort((a, b) => outward * (a[axis] - b[axis]))[0];
    const separation = Math.abs(eyes[0][axis] - eyes[1][axis]);
    const clearance = upright ? eyePadding : Math.min(eyePadding, separation * 0.45);
    looking = boundary - outward * clearance - selected[axis];
  }
  if (!revealing) center[axis] += (hidden - center[axis]) * (amount / PEEK_TUCK);
  else if (amount > 1) center[axis] = hidden + (looking - hidden) * eased;
  else center[axis] += (looking - center[axis]) * amount;
  const visible = intersect(
    { x: center.x - rotatedWidth / 2, y: center.y - rotatedHeight / 2, width: rotatedWidth, height: rotatedHeight },
    bounds
  );
  return {
    fromLeft: onLeft,
    visible,
    hit: touchRect(visible, bounds),
    artwork: { x: center.x - width / 2, y: center.y - height / 2, width, height, rotation },
    eye: eye ? { x: center.x + offset.x, y: center.y + offset.y } : null
  };
}

const DIALOGUE_MODES = ["off", "interaction", "occasional"];
const DIALOGUE_VOICES = ["default", "neutral", "lively", "wry"];
const DIALOGUE_INTERVAL_MS = 15e3;
const AUTONOMOUS_DIALOGUE_INTERVAL_MS = 75e3;
const DIALOGUE_DURATION_MS = 4e3;
function defaultDialogue(key) {
  return { mode: key === "ying" ? "interaction" : "off", voice: key === "ying" ? "default" : "neutral" };
}
function parseDialogue(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return void 0;
  const source = value;
  const validVoice = DIALOGUE_VOICES.includes(source.voice);
  return {
    mode: DIALOGUE_MODES.includes(source.mode) && validVoice ? source.mode : "off",
    voice: validVoice ? source.voice : "neutral"
  };
}
const DIALOGUE_LINES = {
  neutral: {
    greeting: ["你好，我在这里。", "来了，又见面了。", "今天也请多关照。"],
    poke: ["在呢，我听见了。", "嗯，找我有事吗？", "收到，慢慢来。"],
    tease: ["知道啦，不用再提醒。", "我还在这里呢。", "好啦，我在听。"],
    drop: ["落稳了，换个地方看看。", "这里也不错。", "好了，就在这里。"],
    wake: ["刚刚歇了一会儿。", "醒了，继续啦。", "嗯，我回来了。"],
    hop: ["上来了，歇一下。", "站高一点看看。", "这里也能站稳。"]
  },
  lively: {
    greeting: ["来啦，今天也一起玩！", "嘿，又见面啦！", "你好呀，我在这里！"],
    poke: ["嘿嘿，被你找到啦！", "我在呢，什么事呀？", "收到，精神满满！"],
    tease: ["好啦好啦，有点痒！", "听见啦，不用连着戳！", "嘿嘿，我还在呢！"],
    drop: ["到啦，这里不错！", "换个地方，出发！", "稳稳落地啦！"],
    wake: ["醒啦，继续玩！", "小憩结束，精神回来啦！", "刚刚眯了一下！"],
    hop: ["跳上来啦！", "这个高度刚刚好！", "稳稳站住啦！"]
  },
  wry: {
    greeting: ["来了？我可没在等你。", "今天也在，顺便而已。", "你好，别闹就行。"],
    poke: ["知道了，别连着戳。", "我在，不用确认这么多次。", "听见了，有事直说。"],
    tease: ["再戳也不会变出第二个我。", "好啦，已经收到。", "这点耐心我还是有的。"],
    drop: ["站稳了，这次还不错。", "行吧，就在这里。", "换好了，轻一点就更好了。"],
    wake: ["只是歇一下，别想太多。", "醒了，没耽误事。", "休息结束，继续。"],
    hop: ["上来了，这点高度而已。", "站得住，问题不大。", "换个位置罢了。"]
  }
};

function appearanceOf(value) {
  const angles = normalizePeekAngles(value.peek_angles);
  const dialogue = parseDialogue(value.dialogue);
  return {
    scale: value.scale,
    speed: value.speed,
    ...PEEK_EDGES.some((edge) => angles[edge] !== DEFAULT_PEEK_ANGLES[edge]) ? { peek_angles: angles } : {},
    ...dialogue ? { dialogue } : {}
  };
}
function sharedOf(value) {
  return { roam: value.roam, movement: value.movement ?? "auto" };
}
function sameAppearance(a, b) {
  const left = normalizePeekAngles(a.peek_angles);
  const right = normalizePeekAngles(b.peek_angles);
  return a.scale === b.scale && a.speed === b.speed && PEEK_EDGES.every((edge) => left[edge] === right[edge]) && JSON.stringify(parseDialogue(a.dialogue)) === JSON.stringify(parseDialogue(b.dialogue));
}
function sameShared(a, b) {
  return a.roam === b.roam && a.movement === b.movement;
}
const SCALE_RANGE = [0.6, 1.6];
const SPEED_RANGE = [0.5, 2];
const ROAM_MODES = ["surfaces", "floor", "free"];
const DEFAULT_SETTINGS = { scale: 1, speed: 1, roam: "surfaces", movement: "auto" };
const SETTINGS_EVENT = "agentpets.settings";
function bounded(value, range, fallback) {
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.round(Math.min(Math.max(number, range[0]), range[1]) * 100) / 100;
}
function normalizeSettings(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    movement: source.movement === "fixed" ? "fixed" : "auto",
    ...appearanceOf({
      scale: bounded(source.scale, SCALE_RANGE, DEFAULT_SETTINGS.scale),
      speed: bounded(source.speed, SPEED_RANGE, DEFAULT_SETTINGS.speed),
      peek_angles: normalizePeekAngles(source.peek_angles),
      dialogue: parseDialogue(source.dialogue)
    }),
    roam: ROAM_MODES.includes(source.roam) ? source.roam : DEFAULT_SETTINGS.roam
  };
}
async function loadSettings(api, pluginId, key = "ying", confirmed) {
  if (!api?.get || !pluginId) return { ...DEFAULT_SETTINGS };
  try {
    const response = await api.get(`plugin/${pluginId}/settings?key=${encodeURIComponent(key)}`);
    if (response?.success && response.data && typeof response.data === "object" && !Array.isArray(response.data)) {
      const value = normalizeSettings(response.data);
      confirmed?.();
      return value;
    }
  } catch {
    console.warn("[AgentPets] settings unavailable");
  }
  return { ...DEFAULT_SETTINGS };
}

export { AUTONOMOUS_DIALOGUE_INTERVAL_MS as A, sameRect as B, checkSupport as C, DIALOGUE_INTERVAL_MS as D, pickClearX as E, surfaceXBounds as F, blockedSpan as G, nearestEdge as H, hopVelocity as I, xToRatio as J, loadSettings as K, isPeekEdge as L, intersectionArea as M, peekPanelShift as N, computeLanding as O, dropPeekEdge as P, PEEK_TILT_SECONDS as Q, PEEK_TUCK as R, SETTINGS_EVENT as S, PEEK_RISE_SECONDS as T, DEFAULT_PEEK_ANGLES as U, normalizePeekAngle as V, MIN_SURFACE_WIDTH as W, PEEK_PREVIEW_MAX_ANGLE as X, SCALE_RANGE as Y, SPEED_RANGE as Z, sameShared as a, appearanceOf as b, normalizePeekAngles as c, defaultDialogue as d, sameAppearance as e, pickWalkTarget as f, floorLine as g, standable as h, isBlocked as i, coversAny as j, DIALOGUE_LINES as k, DIALOGUE_DURATION_MS as l, DEFAULT_SETTINGS as m, normalizeSettings as n, effectiveScale as o, pickFreeTarget as p, peekHome as q, peekLayout as r, sharedOf as s, readViewport as t, freeBounds as u, clamp as v, ratioToX as w, avoidPanel as x, groundTop as y, xBounds as z };
