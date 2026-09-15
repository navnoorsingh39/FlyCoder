const $ = (id) => document.getElementById(id);

const ACTION_META = {
  DISPLAY_BLOCK: { label: "BLOCK", css: "display: block;" },
  DISPLAY_FLEX: { label: "FLEX", css: "display: flex;" },
  TEXT_ALIGN_CENTER: { label: "TEXT ALIGN", css: "text-align: center;" },
  MARGIN_AUTO: { label: "MARGIN AUTO", css: "margin: auto;" },
  JUSTIFY_CENTER: { label: "JUSTIFY CENTER", css: "justify-content: center;" },
  ALIGN_CENTER: { label: "ALIGN CENTER", css: "align-items: center;" },
  DELETE_LAST: { label: "DELETE", css: "/* delete last */" },
  RUN: { label: "RUN", css: "/* evaluate */" },
};

const KIND_COLOR = [
  [72, 84, 78],
  [110, 200, 212],
  [122, 168, 212],
  [155, 143, 212],
  [126, 232, 160],
  [212, 192, 122],
  [212, 138, 138],
];

const INITIAL_CSS = `.container {
  width: 100vw;
  height: 100vh;
}

.target {
  width: 120px;
  height: 120px;
  background: #8cff66;
}`;

const BAR_SENSORY = [
  ["lc10aL", "LC10a-L"],
  ["lc10aR", "LC10a-R"],
  ["lplc1R", "LPLC1-R"],
  ["lc4", "LC4"],
];
const BAR_DESC = [
  ["dna02R", "DNa02-R", "desc"],
  ["dna02L", "DNa02-L", "desc"],
  ["dnp01", "DNp01", "desc"],
  ["mdn", "MDN", "mdn"],
];

let S = null;
let last = null;
let activity = [];
let edgePulse = [];
let pulses = [];
let wave = 0;
let typeTimer = null;
let typedCss = INITIAL_CSS;
let wantCss = INITIAL_CSS;
let visCursor = 0;
let visCursorTo = 0;
let cursorAnim = null;
let lastPresentKind = "";
let lastBrainSteps = -1;
let lastEventId = -1;
let recording = true;
let screenshot = false;
let introBusy = false;
let flyView = null;
let cnsView = null;
let fps = 0;
let frames = 0;
let fpsT = 0;
let holdPreview = false;
let pendingCss = null;
let pendingEnv = null;

const canvas = $("brain");
const rctx = $("reward-chart").getContext("2d");

function fmt(n) {
  return Number(n).toLocaleString("en-US");
}
function pad2(n) {
  return String(n).padStart(2, "0");
}
function fmtElapsed(s) {
  const t = Math.max(0, Number(s) || 0);
  const m = Math.floor(t / 60);
  const sec = t - m * 60;
  return `${pad2(m)}:${sec.toFixed(1).padStart(4, "0")}`;
}
function pct(v) {
  return `${Math.round(Math.max(0, Math.min(1, v || 0)) * 100)}%`;
}

async function postControl(cmd, extra) {
  await fetch("/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd, ...(extra || {}) }),
  });
}

function setMode() {
  document.body.classList.toggle("recording", recording);
  document.body.classList.toggle("screenshot", screenshot);
  $("btn-record").classList.toggle("on", recording);
  if (flyView) flyView.recording = recording;
  if (cnsView) cnsView.recording = recording;
}

function highlightCss(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/(\.[a-zA-Z-]+)/g, '<span class="sel">$1</span>')
    .replace(/(display|justify-content|align-items|text-align|margin|width|height|background):/g, '<span class="kw">$1</span>:')
    .replace(/: ([^;\n]+);/g, ': <span class="val">$1</span>;');
}

function renderEditor(cssText, flashLine) {
  const lines = (cssText || INITIAL_CSS).replace(/\n$/, "").split("\n");
  $("gutter").textContent = lines.map((_, i) => String(i + 1)).join("\n");
  $("code").innerHTML = lines.map((line, i) => {
    const cls = flashLine != null && i === flashLine ? ' class="line flash"' : "";
    return `<span${cls}>${highlightCss(line) || " "}</span>`;
  }).join("\n");
}

function flashChanged(prev, next) {
  const a = prev.split("\n");
  const b = next.split("\n");
  for (let i = 0; i < b.length; i++) {
    if (a[i] !== b[i]) return i;
  }
  return b.length - 1;
}

function typeCss(next, instant) {
  const prev = typedCss;
  wantCss = next || INITIAL_CSS;
  if (instant || !recording) {
    typedCss = wantCss;
    if (typeTimer) { clearTimeout(typeTimer); typeTimer = null; }
    renderEditor(typedCss, instant ? null : flashChanged(prev, wantCss));
    return;
  }
  if (typedCss === wantCss) return;
  if (typeTimer) return;
  const step = () => {
    if (wantCss.startsWith(typedCss)) typedCss = wantCss.slice(0, typedCss.length + 1);
    else typedCss = wantCss.slice(0, Math.max(0, typedCss.length - 1));
    renderEditor(typedCss, null);
    if (typedCss === wantCss) {
      typeTimer = null;
      renderEditor(typedCss, flashChanged(INITIAL_CSS, typedCss));
      return;
    }
    typeTimer = setTimeout(step, 25 + Math.floor(Math.random() * 21));
  };
  typeTimer = setTimeout(step, 20);
}

function walkCursor(from, to) {
  visCursorTo = to;
  if (visCursor === to) {
    if (cursorAnim) { clearTimeout(cursorAnim); cursorAnim = null; }
    return;
  }
  if (!recording) {
    visCursor = to;
    if (cursorAnim) { clearTimeout(cursorAnim); cursorAnim = null; }
    return;
  }
  if (cursorAnim) return;
  const n = 8;
  const stepOnce = () => {
    if (visCursor === visCursorTo) {
      cursorAnim = null;
      return;
    }
    const fwd = (visCursorTo - visCursor + n) % n;
    const back = (visCursor - visCursorTo + n) % n;
    visCursor = (visCursor + (fwd <= back ? 1 : -1) + n) % n;
    document.querySelectorAll("#palette .act").forEach((el) => {
      el.classList.toggle("on", Number(el.dataset.i) === visCursor);
    });
    cursorAnim = setTimeout(stepOnce, 120 + Math.floor(Math.random() * 61));
  };
  stepOnce();
}

function layout() {
  const wrap = $("brainwrap");
  if (!cnsView) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(80, wrap.clientWidth);
    const h = Math.max(80, wrap.clientHeight);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
  }
  const stageWrap = document.querySelector(".stage-wrap");
  if (stageWrap) {
    const s = Math.min(stageWrap.clientWidth / 1920, stageWrap.clientHeight / 1080);
    $("stage").style.transform = `scale(${s})`;
  }
  if (flyView) flyView.resize();
  if (cnsView) cnsView.resize();
}

function flushPendingVisuals() {
  if (window._pressTimer) { clearTimeout(window._pressTimer); window._pressTimer = null; }
  if (pendingEnv) applyPreview(pendingEnv);
  if (pendingCss) typeCss(pendingCss, !recording);
  holdPreview = false;
  pendingCss = null;
  pendingEnv = null;
}

function beginWingPress(d) {
  const action = (d.discrete && d.discrete.action) || d.last_action;
  const idx = d.cursor || 0;
  let kind = "press";
  if (action === "DELETE_LAST" || d.pulse === "reject") kind = "reject";
  else if (action === "RUN") kind = "run";
  holdPreview = true;
  pendingCss = d.env && d.env.css_text;
  pendingEnv = d.env;
  if (window._pressTimer) clearTimeout(window._pressTimer);
  window._pressTimer = setTimeout(() => {
    if (holdPreview) flushPendingVisuals();
  }, 700);
  if (flyView && flyView.playGesture) {
    flyView.playGesture(kind, idx, action, flushPendingVisuals);
  } else {
    flushPendingVisuals();
  }
}

function applyPreview(env) {
  const c = $("preview-container");
  const t = $("preview-target");
  c.style.display = "block";
  t.style.position = "absolute";
  t.style.left = `${env.target_x || 0}px`;
  t.style.top = `${env.target_y || 0}px`;
  t.style.width = `${env.target_w || 120}px`;
  t.style.height = `${env.target_h || 120}px`;
  t.style.background = (env.target && env.target.background) || "#8cff66";
  t.classList.toggle("glow", !!env.centered);
  const xOk = !!env.x_centered;
  const yOk = !!env.y_centered;
  $("cx").classList.toggle("on", xOk);
  $("cy").classList.toggle("on", yOk);
  const hx = env.horizontal_error || 0;
  const hy = env.vertical_error || 0;
  const ox = $("off-x");
  const oy = $("off-y");
  ox.className = xOk ? "ok" : "";
  oy.className = yOk ? "ok" : "";
  ox.textContent = xOk ? "X  ✓ CENTERED" : `X OFFSET  ${hx >= 0 ? "+" : ""}${Math.round(hx)} px`;
  oy.textContent = yOk ? "Y  ✓ CENTERED" : `Y OFFSET  ${hy >= 0 ? "+" : ""}${Math.round(hy)} px`;
}

function setStatus(d) {
  const el = $("status");
  const label = el.querySelector("span");
  el.classList.remove("online", "error");
  if (d.load_error) {
    el.classList.add("error");
    label.textContent = "CONNECTOME ERROR";
  } else if (d.ready) {
    el.classList.add("online");
    label.textContent = d.finished ? "EXPERIMENT COMPLETE" : (d.sim_finished ? "TARGET CENTERED" : "ONLINE");
  } else {
    label.textContent = "CONNECTOME LOADING";
  }
  $("btn-start").disabled = !d.ready || d.running || d.finished || introBusy;
  $("btn-pause").disabled = !d.ready || !d.running;
  $("btn-reset").disabled = !d.ready;
  document.querySelectorAll(".speed-btn").forEach((b) => {
    b.classList.toggle("on", Number(b.dataset.speed) === d.speed);
  });
}

function renderStages(stage) {
  document.querySelectorAll("#stages span").forEach((el) => {
    el.classList.toggle("on", el.dataset.stage === stage);
  });
}

function renderPalette(d) {
  const box = $("palette");
  if (!box.dataset.ready && d.actions) {
    box.innerHTML = d.actions.map((a, i) => {
      const m = ACTION_META[a] || { label: a, css: "" };
      return `<div class="act" data-i="${i}" data-a="${a}"><span>${m.label}</span><small>${m.css}</small></div>`;
    }).join("");
    box.dataset.ready = "1";
  }
  box.querySelectorAll(".act").forEach((el) => {
    const i = Number(el.dataset.i);
    el.classList.toggle("on", i === visCursor);
    el.classList.toggle("commit", d.present_kind === "COMMIT" && i === visCursor);
    el.classList.toggle("reject", (d.pulse === "reject" || d.control_mode === "REJECTING") && el.dataset.a === "DELETE_LAST");
  });
}

function renderLog(events) {
  const log = $("log");
  const rows = (events || []).slice(0, 22).slice().reverse();
  log.innerHTML = rows.map((e) => {
    const kind = (e.kind || "").replace(/</g, "");
    const msg = String(e.msg || "").replace(/</g, "&lt;");
    return `<li><span class="t">${e.t || ""}</span><span class="k ${kind}">${kind}</span><span>${msg}</span></li>`;
  }).join("");
  log.scrollTop = log.scrollHeight;
}

function renderReward(d) {
  const r = (d.env && d.env.reward) || 0;
  $("reward-now").textContent = `${r >= 0 ? "+" : ""}${Number(r).toFixed(3)}`;
  $("reward-now").parentElement.classList.toggle("neg", r < 0);
  const hist = d.reward_history || [];
  const w = $("reward-chart").width;
  const h = $("reward-chart").height;
  rctx.clearRect(0, 0, w, h);
  rctx.strokeStyle = "#24302b";
  rctx.beginPath();
  rctx.moveTo(0, h / 2);
  rctx.lineTo(w, h / 2);
  rctx.stroke();
  if (!hist.length) return;
  const max = Math.max(0.2, ...hist.map((x) => Math.abs(x)));
  const dx = w / Math.max(hist.length - 1, 1);
  rctx.beginPath();
  hist.forEach((v, i) => {
    const x = i * dx;
    const y = h / 2 - (v / max) * (h * 0.42);
    if (i === 0) rctx.moveTo(x, y);
    else rctx.lineTo(x, y);
  });
  rctx.strokeStyle = "#8ef0ad";
  rctx.lineWidth = 1.5;
  rctx.stroke();
}

function renderBars(d) {
  const sn = d.sensory_norm || {};
  const dn = d.descending_norm || {};
  const host = $("ctrl-bars");
  const rows = [
    ...BAR_SENSORY.map(([k, lab]) => ({ k, lab, v: sn[k] || 0, cls: "" })),
    ...BAR_DESC.map(([k, lab, cls]) => ({ k, lab, v: dn[k] || 0, cls })),
  ];
  if (!host.dataset.ready) {
    host.innerHTML = rows.map((r) =>
      `<div class="bar-row ${r.cls}" data-k="${r.k}"><label>${r.lab}</label><div class="track"><i></i></div><b>0%</b></div>`
    ).join("");
    host.dataset.ready = "1";
  }
  host.querySelectorAll(".bar-row").forEach((el) => {
    const k = el.dataset.k;
    const row = rows.find((r) => r.k === k);
    const v = row ? row.v : 0;
    el.querySelector("i").style.width = pct(v);
    el.querySelector("b").textContent = pct(v);
  });
}

function renderHud(d) {
  const sn = d.sensory_norm || {};
  const dn = d.descending_norm || {};
  const fill = (id, items) => {
    const el = $(id);
    el.innerHTML = items.map(([k, lab, src]) => {
      const v = (src[k] || 0);
      return `<li><span>${lab}</span><span class="bar"><i style="width:${pct(v)}"></i></span><span>${(src[k] == null ? "—" : Number(src[k]).toFixed(2))}</span></li>`;
    }).join("");
  };
  fill("hud-sensory", [
    ["lc10aL", "LC10a-L", sn], ["lc10aR", "LC10a-R", sn],
    ["lplc1R", "LPLC1-R", sn], ["lc4", "LC4", sn],
  ]);
  fill("hud-desc", [
    ["dna02L", "DNa02-L", dn], ["dna02R", "DNa02-R", dn],
    ["dnp01", "DNp01", dn], ["dng100", "DNg100", dn], ["mdn", "MDN", dn],
  ]);
}

function renderTimeline(items) {
  const el = $("timeline");
  const rows = items || [];
  el.innerHTML = rows.slice(-8).map((it, i, arr) => {
    const latest = i === arr.length - 1 ? " latest" : "";
    const sign = it.reward >= 0 ? "+" : "";
    return `<li class="${latest}">${pad2(it.n)} ${it.label} ${sign}${Number(it.reward).toFixed(2)}</li>`;
  }).join("");
}

function visualInput(d) {
  const env = d.env || {};
  const hx = env.horizontal_error || 0;
  const hy = env.vertical_error || 0;
  const bits = [];
  if (hx < -2) bits.push("LEFT");
  else if (hx > 2) bits.push("RIGHT");
  if (hy < -2) bits.push("ABOVE");
  else if (hy > 2) bits.push("BELOW");
  if (!bits.length) return "VISUAL INPUT  CENTERED";
  return `VISUAL INPUT  TARGET ${bits.join(" + ")}`;
}

function renderFinish(d) {
  const banner = $("success-banner");
  const ov = $("overlay");
  banner.hidden = !d.success_banner;
  if (d.success_banner) {
    const r = (d.finish && d.finish.final_reward) || d.cumulative_reward || 0;
    banner.textContent = `TARGET CENTERED · REWARD ${r >= 0 ? "+" : ""}${Number(r).toFixed(3)}`;
  }
  const show = !!d.show_overlay;
  ov.hidden = !show;
  ov.setAttribute("aria-hidden", show ? "false" : "true");
  if (!show) return;
  const f = d.finish || {};
  $("fin-attempts").textContent = fmt(f.attempts ?? d.attempts ?? 0);
  $("fin-steps").textContent = fmt(f.brain_steps ?? d.brain_steps ?? 0);
  $("fin-time").textContent = fmtElapsed(f.elapsed ?? d.elapsed ?? 0);
}

function ingestSpikes(d) {
  if (!activity.length && S && S.vis) {
    activity = new Float32Array(S.vis.x.length);
    edgePulse = new Float32Array((S.vis.edges || []).length);
  }
  const steps = d.brain_steps || 0;
  const fresh = steps !== lastBrainSteps;
  if (fresh) {
    lastBrainSteps = steps;
    const spikes = d.vis_spikes || [];
    const hit = new Set();
    for (const i of spikes) {
      if (i >= 0 && i < activity.length) {
        activity[i] = Math.min(1, activity[i] + 0.7);
        hit.add(i);
      }
    }
    if (S && S.vis && S.vis.edges) {
      S.vis.edges.forEach((e, ei) => {
        if (hit.has(e[0]) || hit.has(e[1])) edgePulse[ei] = 1;
      });
    }
  }
  const drive = d.drive || {};
  if (S && S.vis) {
    const boost = (kind, amt) => {
      if (amt <= 0.02) return;
      for (let i = 0; i < S.vis.kind.length; i++) {
        if (S.vis.kind[i] === kind) activity[i] = Math.max(activity[i], amt * 0.7);
      }
    };
    boost(1, Math.max(drive.lc10aL || 0, drive.lc10aR || 0));
    boost(2, Math.max(drive.lplc1L || 0, drive.lplc1R || 0));
    boost(3, Math.max(drive.lc4L || 0, drive.ERROR_MAGNITUDE || 0));
    if (d.present_kind === "READOUT" || d.present_kind === "CURSOR_MOVE") boost(4, 0.85);
    if (d.present_kind === "COMMIT") {
      if (d.pulse === "reject") boost(6, 1);
      else boost(5, 1);
    }
  }
}

function ingest(d) {
  last = d;
  ingestSpikes(d);
  if (d.pulse && S && S.labels && d.present_kind !== lastPresentKind) {
    const map = { stimulus: "lc10a", commit: "commit", reject: "reject", reward: "loom", success: "commit" };
    const lab = S.labels.find((x) => x.id === map[d.pulse]) || S.labels[0];
    if (lab) pulses.push({ x: lab.x, y: lab.y, r: 8, life: 1 });
  }
  if (d.present_kind === "SUCCESS") wave = Math.max(wave, 1);
  lastPresentKind = d.present_kind || "";

  const ev = d.discrete;
  if (ev && ev.id !== lastEventId) {
    lastEventId = ev.id;
    if (ev.kind === "CURSOR") walkCursor(ev.from_index != null ? ev.from_index : visCursor, ev.to_index);
    else walkCursor(d.cursor_from != null ? d.cursor_from : visCursor, d.cursor || 0);
    if (ev.kind === "ACTION_COMMITTED") beginWingPress(d);
    if (ev.kind === "SUCCESS" && flyView && flyView.playGesture) flyView.playGesture("flutter", d.cursor || 0, d.last_action);
  } else {
    walkCursor(d.cursor_from != null ? d.cursor_from : visCursor, d.cursor || 0);
  }

  setStatus(d);
  renderStages(d.stage);
  $("stat-neurons").textContent = fmt(d.neurons || 166700);
  $("stat-conn").textContent = fmt(d.connections || 25582938);
  $("stat-active").textContent = d.ready ? fmt(d.active || 0) : "—";
  $("stat-step").textContent = d.ready ? fmt(d.brain_steps || 0) : "—";
  $("stat-cns").textContent = d.malecns || "MaleCNS v1.0";
  $("stat-w").textContent = d.weights || "FROZEN";
  $("hdr-center").textContent = `${fmt(d.neurons || 166700)} NEURONS TRYING TO CENTER A DIV`;
  $("stat-attempt").textContent = pad2(d.attempts || 0);
  $("stat-bsteps").textContent = fmt(d.brain_steps || 0);
  $("stat-elapsed").textContent = fmtElapsed(recording ? (d.present_elapsed ?? d.elapsed) : d.elapsed);
  $("stat-best").textContent = d.best_error != null ? `${Math.round(d.best_error)} px` : "—";
  if (S && S.vis) $("vis-count").textContent = `${fmt(S.vis.x.length)} somata · ${fmt((S.vis.edges || []).length)} synapses · ${fps | 0} fps`;

  const mode = d.control_mode || (d.control && d.control.mode) || "SCANNING";
  $("ctrl-mode").textContent = mode;
  $("fly-mode").textContent = mode;
  $("input-line").textContent = visualInput(d);
  $("flow-hint").classList.toggle("on", d.present_kind === "PROPAGATE" || d.present_kind === "READOUT");
  if (cnsView) cnsView.ingest(d, activity, edgePulse);

  renderPalette(d);
  renderLog(d.events);
  renderReward(d);
  renderBars(d);
  renderHud(d);
  renderTimeline(d.timeline);
  const box = $("reward-box");
  if (box) {
    box.classList.toggle("flash-pos", d.present_kind === "REWARD" && d.env && d.env.reward > 0);
    box.classList.toggle("flash-neg", d.present_kind === "REWARD" && d.env && d.env.reward < 0);
  }
  const note = $("layout-note");
  if (note) {
    note.hidden = !d.layout_note;
    if (d.layout_note) note.textContent = d.layout_note;
  }
  const evn = $("eval-note");
  if (evn) {
    evn.hidden = !d.eval_note;
    evn.textContent = d.eval_note || "";
  }
  const commitLine = $("commit-line");
  const committing = d.present_kind === "COMMIT" || d.control_mode === "COMMITTING";
  commitLine.hidden = !committing;
  commitLine.textContent = d.pulse === "reject"
    ? "REJECT SIGNAL  MDN"
    : `COMMIT SIGNAL  DNp01 / DNg100  →  ${(d.last_action || d.highlighted || "")}`;

  const badge = $("neural-badge");
  if (d.present_kind === "COMMIT" && d.last_action) {
    badge.hidden = false;
    badge.textContent = `NEURAL COMMIT  ${d.last_action}`;
  } else if (d.present_kind === "ACTION" && d.last_action) {
    badge.hidden = false;
    badge.textContent = `EXECUTING → ${d.last_action}`;
  } else if (d.present_kind !== "ACTION") {
    badge.hidden = true;
  }

  if (d.env) {
    if (holdPreview) {
      pendingEnv = d.env;
      pendingCss = d.env.css_text || pendingCss;
    } else {
      applyPreview(d.env);
      const css = d.env.css_text || INITIAL_CSS;
      typeCss(css, !recording || d.present_kind !== "ACTION");
    }
  }
  $("fly-cursor-label").textContent = `● FLY CONTROL  ${(d.highlighted || "").replace(/_/g, " ")}`;
  renderFinish(d);
  if (flyView) flyView.applyState(d, recording);
}

function decayActivity() {
  if (!activity.length) return;
  const running = last && last.running;
  const decay = running ? 0.985 : (last && last.finished ? 0.992 : 0.94);
  for (let i = 0; i < activity.length; i++) activity[i] *= decay;
  for (let i = 0; i < edgePulse.length; i++) edgePulse[i] *= 0.96;
}

function placeLabels() {
  const host = $("region-labels");
  if (!host || !S || !S.labels) return;
  host.innerHTML = "";
}

function tick(now) {
  frames += 1;
  if (!fpsT) fpsT = now;
  if (now - fpsT > 500) {
    fps = frames * 1000 / (now - fpsT);
    frames = 0;
    fpsT = now;
  }
  decayActivity();
  if (cnsView) cnsView.tick(now);
  if (flyView) flyView.tick(now);
  requestAnimationFrame(tick);
}

const INTRO = (d) => [
  `LOADING MALECNS CONNECTOME`,
  `${fmt(d.neurons || 166700)} neurons`,
  `CONNECTOME READY`,
  `MAPPING SENSORY CHANNELS`,
  `LC10a / LPLC1 / LC4 / LPLC2`,
  `MAPPING DESCENDING READOUT`,
  `DNa02 / DNp01 / DNg100 / MDN`,
  `3D EMBODIED VISUALIZATION`,
  `OBJECTIVE  CENTER THE DIV`,
  `EXPERIMENT START`,
];

async function playIntro(d) {
  introBusy = true;
  setStatus(d || last || {});
  const box = $("intro");
  const ol = $("intro-lines");
  const lines = INTRO(d || last || {});
  ol.innerHTML = lines.map((t) => `<li>${t}</li>`).join("");
  box.hidden = false;
  const items = [...ol.children];
  for (let i = 0; i < items.length; i++) {
    items.forEach((el, j) => {
      el.classList.toggle("on", j === i);
      el.classList.toggle("done", j < i);
    });
    await new Promise((r) => setTimeout(r, i === items.length - 1 ? 380 : 200));
  }
  items.forEach((el) => el.classList.add("done"));
  await new Promise((r) => setTimeout(r, 220));
  box.hidden = true;
  introBusy = false;
}

async function onStart() {
  if (!last || !last.ready || last.running || last.finished || introBusy) return;
  await playIntro(last);
  await postControl("start");
}

function bind() {
  $("btn-start").onclick = onStart;
  $("btn-pause").onclick = () => postControl("pause");
  $("btn-reset").onclick = () => {
    screenshot = false;
    setMode();
    postControl("reset");
    typedCss = INITIAL_CSS;
    wantCss = INITIAL_CSS;
    visCursor = 0;
    lastBrainSteps = -1;
    lastEventId = -1;
    holdPreview = false;
    pendingCss = null;
    pendingEnv = null;
    if (window._pressTimer) { clearTimeout(window._pressTimer); window._pressTimer = null; }
    if (typeTimer) { clearTimeout(typeTimer); typeTimer = null; }
    if (cursorAnim) { clearTimeout(cursorAnim); cursorAnim = null; }
    renderEditor(INITIAL_CSS);
    if (flyView) flyView.resetPose();
  };
  document.querySelectorAll(".speed-btn").forEach((b) => {
    b.onclick = () => postControl("speed", { value: Number(b.dataset.speed) });
  });
  $("btn-record").onclick = async () => {
    recording = !recording;
    setMode();
    await postControl("cinematic", { value: recording });
  };
  $("btn-about").onclick = () => $("about").showModal();
  addEventListener("keydown", (e) => {
    if (e.target && ["INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
    if (e.key === "Escape") {
      if ($("about").open) return;
      e.preventDefault();
      $("btn-reset").click();
      return;
    }
    if (e.key === "r" || e.key === "R") {
      e.preventDefault();
      $("btn-record").click();
    }
    if (e.key === "s" || e.key === "S") {
      if (last && (last.show_overlay || last.finished)) {
        screenshot = !screenshot;
        setMode();
      }
    }
    if (e.key === " ") {
      e.preventDefault();
      if (last && last.running) postControl("pause");
      else onStart();
    }
  });
}

async function loadStatic() {
  for (let i = 0; i < 600; i++) {
    try {
      const res = await fetch("/static.json");
      if (res.ok) {
        S = await res.json();
        if (!S.vis && S.x) S.vis = { x: S.x, y: S.y, kind: S.x.map(() => 0), edges: [] };
        activity = new Float32Array((S.vis && S.vis.x.length) || 0);
        edgePulse = new Float32Array(((S.vis && S.vis.edges) || []).length);
        if (cnsView) cnsView.load(S);
        if (S.vis) $("vis-count").textContent = `${fmt(S.vis.x.length)} somata · ${fmt((S.vis.edges || []).length)} synapses`;
        return;
      }
    } catch (_) { /* still loading */ }
    await new Promise((r) => setTimeout(r, 400));
  }
}

async function init() {
  bind();
  setMode();
  postControl("cinematic", { value: recording });
  addEventListener("resize", layout);
  renderEditor(INITIAL_CSS);
  try {
    cnsView = new CNSView(canvas);
    cnsView.recording = recording;
  } catch (err) {
    console.warn("spatial connectome unavailable", err);
  }
  try {
    flyView = new FlyView($("fly3d"));
  } catch (err) {
    console.warn("3D fly unavailable", err);
  }
  layout();
  const es = new EventSource("/events");
  es.onmessage = (e) => {
    const d = JSON.parse(e.data);
    if (!S && d.ready) loadStatic();
    ingest(d);
    window.last = last;
  };
  es.onerror = () => {};
  await loadStatic();
  layout();
  requestAnimationFrame(tick);
}

init();
