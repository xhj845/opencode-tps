import fs from "node:fs";
import path from "node:path";

const DIR = path.join(process.env.LOCALAPPDATA || process.env.TEMP || ".", "OpenChamberTps");
const EXE = String(process.execPath || "").toLowerCase();
const APP = EXE.includes("openchamber") ? "openchamber" : "opencode";
const STATE_FILE = path.join(DIR, `state-${APP}-${process.pid}.json`);
const HEARTBEAT_FILE = path.join(DIR, `heartbeat-${APP}-${process.pid}.json`);
const LOG_FILE = path.join(DIR, "plugin.log");
const WINDOW_MS = 1500;
const WRITE_MS = 120;
const KEEP_FINAL_MS = 6000;
const SESSION_TTL_MS = 120000;

const GLOBAL_KEY = Symbol.for("openchamber.tps.live.bridge");
const sessions = new Map();
const loadedAt = Date.now();
let timer = null;
let controller = null;
let lastWriteAt = 0;
let lastStateJson = "";
let instance = null;

function log(message) {
  try {
    if (fs.existsSync(LOG_FILE) && fs.statSync(LOG_FILE).size > 1024 * 1024) fs.truncateSync(LOG_FILE, 0);
    fs.appendFileSync(LOG_FILE, `${new Date().toISOString()} [${APP}/${process.pid}] ${message}\n`);
  } catch {}
}

function ensureDir() {
  try { fs.mkdirSync(DIR, { recursive: true }); } catch {}
}

function cleanupOld() {
  try {
    const now = Date.now();
    for (const name of fs.readdirSync(DIR)) {
      if (!/^(state|heartbeat)-/.test(name)) continue;
      const file = path.join(DIR, name);
      try {
        if (now - fs.statSync(file).mtimeMs > 24 * 60 * 60 * 1000) fs.unlinkSync(file);
      } catch {}
    }
  } catch {}
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function estimateTokens(text) {
  if (!text) return 0;
  let cjk = 0;
  let other = 0;
  let space = 0;
  for (const ch of String(text)) {
    const cp = ch.codePointAt(0);
    if (cp === 0x20 || cp === 0x0a || cp === 0x0d || cp === 0x09) {
      space += 1;
    } else if (
      (cp >= 0x3000 && cp <= 0x303f) ||
      (cp >= 0x3400 && cp <= 0x4dbf) ||
      (cp >= 0x4e00 && cp <= 0x9fff) ||
      (cp >= 0xf900 && cp <= 0xfaff) ||
      (cp >= 0xff00 && cp <= 0xffef)
    ) {
      cjk += 1;
    } else {
      other += 1;
    }
  }
  // Empirically ~1.7 Chinese chars/token and ~3.8 ASCII chars/token.
  return cjk * 0.6 + other / 3.8 + space / 12;
}

function sessionFor(id) {
  let s = sessions.get(id);
  if (!s) {
    s = {
      id,
      directory: "",
      modelID: "",
      variant: "",
      agent: "",
      status: "waiting",
      phase: "waiting",
      startedAt: 0,
      stepStartedAt: 0,
      firstTokenAt: 0,
      lastDeltaAt: 0,
      lastEventAt: Date.now(),
      textRaw: 0,
      reasoningRaw: 0,
      samples: [],
      scale: 1,
      exact: false,
      exactOutput: 0,
      exactReasoning: 0,
      finalAt: 0,
      toolStartedAt: 0,
      toolElapsedMs: 0,
      stepHadTool: false,
      tpsSmooth: 0,
      visibleSmooth: 0,
      turnOutput: 0,
      turnReasoning: 0,
    };
    sessions.set(id, s);
  }
  return s;
}

function resetStep(s, at) {
  s.textRaw = 0;
  s.reasoningRaw = 0;
  s.samples = [];
  s.exact = false;
  s.exactOutput = 0;
  s.exactReasoning = 0;
  s.finalAt = 0;
  s.firstTokenAt = 0;
  s.lastDeltaAt = 0;
  s.toolStartedAt = 0;
  s.toolElapsedMs = 0;
  s.stepHadTool = false;
  s.tpsSmooth = 0;
  s.visibleSmooth = 0;
  s.stepStartedAt = at || Date.now();
}

function addDelta(s, text, kind, at) {
  const raw = estimateTokens(text);
  if (raw <= 0) return;
  if (kind === "reasoning") {
    s.reasoningRaw += raw;
    s.phase = "thinking";
    s.status = "thinking";
  } else {
    s.textRaw += raw;
    s.phase = "streaming";
    s.status = "streaming";
  }
  if (!s.firstTokenAt) s.firstTokenAt = at;
  s.lastDeltaAt = at;
  s.samples.push({ t: at, raw, kind });
  if (s.samples.length > 500) s.samples.splice(0, s.samples.length - 500);
}

function calcRate(s, kind, now) {
  const cutoff = now - WINDOW_MS;
  let first = 0;
  let tokens = 0;
  for (const sample of s.samples) {
    if (sample.t < cutoff) continue;
    if (kind !== "all" && sample.kind !== kind) continue;
    if (!first) first = sample.t;
    tokens += sample.raw * s.scale;
  }
  if (!first || tokens <= 0) return 0;
  const span = Math.max(300, Math.min(WINDOW_MS, now - first));
  return tokens / (span / 1000);
}

function serializeSession(s, now) {
  const end = s.finalAt || now;
  const liveText = s.exact ? s.exactOutput : s.textRaw * s.scale;
  const liveReasoning = s.exact ? s.exactReasoning : s.reasoningRaw * s.scale;
  const total = liveText + liveReasoning;
  const rawRate = calcRate(s, "all", now);
  const rawVisible = calcRate(s, "text", now);
  const active = s.status !== "idle" && s.status !== "final";
  s.tpsSmooth = active ? (s.tpsSmooth ? s.tpsSmooth * 0.65 + rawRate * 0.35 : rawRate) : rawRate;
  s.visibleSmooth = active ? (s.visibleSmooth ? s.visibleSmooth * 0.65 + rawVisible * 0.35 : rawVisible) : rawVisible;
  const generationMs = s.lastDeltaAt > s.firstTokenAt ? s.lastDeltaAt - s.firstTokenAt : 0;
  const avgTps = s.exact && generationMs > 0 ? total / (generationMs / 1000) : (generationMs > 300 ? total / (generationMs / 1000) : 0);
  const avgVisibleTps = s.exact && generationMs > 0 ? s.exactOutput / (generationMs / 1000) : 0;
  return {
    id: s.id,
    app: APP,
    directory: s.directory || "",
    modelID: s.modelID,
    variant: s.variant,
    agent: s.agent,
    status: s.toolStartedAt ? "tool" : s.status,
    phase: s.phase,
    tps: Math.round(s.tpsSmooth * 10) / 10,
    visibleTps: Math.round(s.visibleSmooth * 10) / 10,
    avgTps: Math.round(avgTps * 10) / 10,
    avgVisibleTps: Math.round(avgVisibleTps * 10) / 10,
    ttftMs: s.firstTokenAt && s.stepStartedAt ? Math.max(0, s.firstTokenAt - s.stepStartedAt) : null,
    elapsedMs: Math.max(0, end - (s.stepStartedAt || s.startedAt || end)),
    toolElapsedMs: s.toolElapsedMs + (s.toolStartedAt ? Math.max(0, now - s.toolStartedAt) : 0),
    outputTokens: Math.max(0, Math.round(liveText)),
    reasoningTokens: Math.max(0, Math.round(liveReasoning)),
    totalTokens: Math.max(0, Math.round(total)),
    turnTokens: Math.round(s.turnOutput + s.turnReasoning + (s.exact ? 0 : total)),
    exact: s.exact,
    stepHadTool: s.stepHadTool,
    scale: Math.round(s.scale * 1000) / 1000,
    firstTokenAt: s.firstTokenAt || null,
    lastDeltaAt: s.lastDeltaAt || null,
    lastEventAt: s.lastEventAt,
    finalAt: s.finalAt || null,
  };
}

function buildPayload(now) {
  const list = [];
  for (const s of sessions.values()) {
    if (now - s.lastEventAt < SESSION_TTL_MS) list.push(s);
    else sessions.delete(s.id);
  }
  list.sort((a, b) => b.lastEventAt - a.lastEventAt);
  const states = list.slice(0, 12).map((s) => serializeSession(s, now));
  return {
    schemaVersion: 1,
    pluginVersion: "1.0.0",
    app: APP,
    pid: process.pid,
    loadedAt,
    updatedAt: now,
    state: states[0] || null,
    sessions: states,
  };
}

function writeState(now) {
  try {
    const payload = buildPayload(now || Date.now());
    const json = JSON.stringify(payload);
    if (json === lastStateJson) return;
    lastStateJson = json;
    lastWriteAt = Date.now();
    const tmp = `${STATE_FILE}.tmp`;
    fs.writeFileSync(tmp, json);
    try { fs.renameSync(tmp, STATE_FILE); } catch {
      try { fs.writeFileSync(STATE_FILE, json); } catch {}
      try { fs.unlinkSync(tmp); } catch {}
    }
  } catch (error) {
    log(`writeState failed: ${error?.message || error}`);
  }
}

function hasActive() {
  const now = Date.now();
  for (const s of sessions.values()) {
    if (now - s.lastEventAt > 60000) continue;
    if (s.status !== "idle") return true;
    if (s.finalAt && now - s.finalAt < KEEP_FINAL_MS) return true;
  }
  return false;
}

function handleEvent(event) {
  if (!event || typeof event.type !== "string" || !event.type.startsWith("session.")) return;
  const data = event.data || {};
  const id = typeof data.sessionID === "string" ? data.sessionID : null;
  if (!id) return;
  const s = sessionFor(id);
  const location = event.location || {};
  if (typeof location.directory === "string" && location.directory) s.directory = location.directory;
  const now = Date.now();
  const at = Number(event.created) && Number(event.created) > 0 ? Number(event.created) : now;
  s.lastEventAt = now;

  switch (event.type) {
    case "session.execution.started":
      s.startedAt = at;
      s.status = "waiting";
      s.phase = "waiting";
      break;
    case "session.step.started": {
      const model = data.model || {};
      s.modelID = model.id || model.modelID || s.modelID;
      s.variant = model.variant || s.variant;
      s.agent = data.agent || s.agent;
      const started = Number(data.started);
      resetStep(s, Number.isFinite(started) && started > 0 && started <= at + 5000 ? started : at);
      s.status = "thinking";
      s.phase = "thinking";
      break;
    }
    case "session.reasoning.delta":
      addDelta(s, data.delta, "reasoning", at);
      break;
    case "session.text.delta":
      addDelta(s, data.delta, "text", at);
      break;
    case "session.reasoning.started":
      s.phase = "thinking";
      if (s.status === "waiting") s.status = "thinking";
      break;
    case "session.text.started":
      s.phase = "streaming";
      if (s.status === "waiting") s.status = "thinking";
      break;
    case "session.tool.called":
      s.stepHadTool = true;
      s.status = "tool";
      s.phase = "tool";
      s.toolStartedAt = at;
      break;
    case "session.tool.success":
    case "session.tool.failed":
      if (s.toolStartedAt) {
        s.toolElapsedMs += Math.max(0, at - s.toolStartedAt);
        s.toolStartedAt = 0;
      }
      s.status = s.phase === "tool" ? "thinking" : s.phase || "thinking";
      break;
    case "session.step.ended": {
      const tokens = data.tokens || {};
      const exactOutput = Number(tokens.output) || 0;
      const exactReasoning = Number(tokens.reasoning) || 0;
      const exactTotal = exactOutput + exactReasoning;
      const rawTotal = s.textRaw + s.reasoningRaw;
      s.exact = true;
      s.exactOutput = exactOutput;
      s.exactReasoning = exactReasoning;
      s.turnOutput += exactOutput;
      s.turnReasoning += exactReasoning;
      if (!s.stepHadTool && data.finish !== "tool-calls" && exactTotal > 0 && rawTotal > 0) {
        s.scale = clamp(exactTotal / rawTotal, 0.5, 2);
      }
      s.status = data.finish === "tool-calls" ? "tool" : "final";
      s.phase = s.status;
      s.finalAt = data.finish === "tool-calls" ? 0 : now;
      break;
    }
    case "session.step.failed":
      s.status = "final";
      s.phase = "error";
      s.finalAt = now;
      break;
    case "session.usage.updated": {
      const tokens = data.tokens || {};
      if (!s.exact && (Number(tokens.output) || Number(tokens.reasoning))) {
        s.exactOutput = Number(tokens.output) || 0;
        s.exactReasoning = Number(tokens.reasoning) || 0;
      }
      break;
    }
    case "session.idle":
      s.status = "idle";
      s.phase = "idle";
      s.finalAt = s.finalAt || now;
      break;
    case "session.execution.succeeded":
    case "session.execution.failed":
    case "session.execution.interrupted":
      if (s.status !== "final" && s.status !== "idle") {
        s.status = "idle";
        s.phase = event.type.replace("session.execution.", "");
        s.finalAt = s.finalAt || now;
      }
      break;
    default:
      break;
  }
  // Deltas are frequent; let the 120ms timer coalesce them.
  if (event.type !== "session.text.delta" && event.type !== "session.reasoning.delta") {
    writeState(now);
  }
}

async function subscribe(ctx, signal) {
  try {
    for await (const event of ctx.event.subscribe({ signal })) {
      try { handleEvent(event); } catch (error) { log(`handleEvent failed: ${error?.message || error}`); }
    }
  } catch (error) {
    if (!signal?.aborted) log(`subscription ended: ${error?.message || error}`);
  }
}

export default {
  id: "tps-live-bridge",
  async setup(ctx) {
    // OpenCode may hot-reload plugins; keep exactly one live bridge per process.
    const previous = globalThis[GLOBAL_KEY];
    if (previous && typeof previous.dispose === "function") {
      try { previous.dispose(); } catch {}
    }

    ensureDir();
    cleanupOld();
    const controller = new AbortController();
    let disposed = false;

    const dispose = () => {
      if (disposed) return;
      disposed = true;
      try { controller.abort(); } catch {}
      try { clearInterval(localTimer); } catch {}
      // Only the current instance may remove the shared state files.
      if (globalThis[GLOBAL_KEY] === instance) {
        try { fs.unlinkSync(STATE_FILE); } catch {}
        try { fs.unlinkSync(HEARTBEAT_FILE); } catch {}
        try { delete globalThis[GLOBAL_KEY]; } catch {}
      }
    };

    try {
      fs.writeFileSync(HEARTBEAT_FILE, JSON.stringify({ app: APP, pid: process.pid, loadedAt, execPath: process.execPath }));
    } catch {}
    try { writeState(); } catch {}

    const localTimer = setInterval(() => {
      try {
        if (hasActive() || Date.now() - lastWriteAt > 5000) writeState();
      } catch (error) {
        log(`timer failed: ${error?.message || error}`);
      }
    }, WRITE_MS);
    // Keep the timer from holding the process open on its own.
    try { localTimer.unref?.(); } catch {}

    const instance = { dispose };
    globalThis[GLOBAL_KEY] = instance;
    subscribe(ctx, controller.signal).catch(() => {});
    log("setup");
    return dispose;
  },
};
