// Colormask webapp UI. State lives here; selection math is in floodfill.js.
"use strict";

const TOL_PER_PIXEL = 1 / 300;   // drag-distance -> tolerance (tuning constant)
const MAX_TOL = 1.2;
const FLOOD_MAX_DIM = 512;       // flood buffer cap
const MAX_RULES = 32;            // must match protocol.MAX_RULES

const view = document.getElementById("view");
const overlay = document.getElementById("overlay");
const stage = document.getElementById("stage");
const banner = document.getElementById("banner");
const statusEl = document.getElementById("status");
const chipsEl = document.getElementById("chips");
const sendBtn = document.getElementById("send");

// Working state
let frameImg = null;         // full-res Image of the latest snapshot
let flood = null;            // {w, h, data} downscaled RGBA buffer
let gestures = [];           // {type, color:[r,g,b] 0..255, tol, region: Uint8Array|null}
let tool = "wand";
let drag = null;             // {sx, sy, seed:[r,g,b], startX, startY, preview}

function showBanner(msg) { banner.textContent = msg; banner.classList.remove("hidden"); }
function hideBanner() { banner.classList.add("hidden"); }
function setStatus(msg) { statusEl.textContent = msg; }

async function fetchFrame() {
  setStatus("fetching frame…");
  try {
    const resp = await fetch("/frame");
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || ("HTTP " + resp.status));
    }
    const blob = await resp.blob();
    const img = new Image();
    await new Promise((res, rej) => {
      img.onload = res; img.onerror = rej;
      img.src = URL.createObjectURL(blob);
    });
    frameImg = img;
    buildFloodBuffer();
    layout();
    redrawOverlay();
    hideBanner();
    setStatus(img.width + "×" + img.height);
  } catch (e) {
    showBanner("Frame fetch failed: " + e.message + " — is TD + the bridge up?");
    setStatus("");
  }
}

function buildFloodBuffer() {
  const scale = Math.min(1, FLOOD_MAX_DIM / Math.max(frameImg.width, frameImg.height));
  const w = Math.max(1, Math.round(frameImg.width * scale));
  const h = Math.max(1, Math.round(frameImg.height * scale));
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(frameImg, 0, 0, w, h);
  flood = { w, h, data: ctx.getImageData(0, 0, w, h).data };
}

function layout() {
  const scale = Math.min(stage.clientWidth / frameImg.width,
                         stage.clientHeight / frameImg.height);
  const dw = Math.round(frameImg.width * scale);
  const dh = Math.round(frameImg.height * scale);
  for (const c of [view, overlay]) {
    c.width = dw; c.height = dh;
    c.style.width = dw + "px"; c.style.height = dh + "px";
  }
  const ctx = view.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(frameImg, 0, 0, dw, dh);
}

// display coords -> flood buffer coords
function toFlood(ev) {
  const r = view.getBoundingClientRect();
  const x = Math.floor((ev.clientX - r.left) / r.width * flood.w);
  const y = Math.floor((ev.clientY - r.top) / r.height * flood.h);
  return [Math.max(0, Math.min(flood.w - 1, x)),
          Math.max(0, Math.min(flood.h - 1, y))];
}

function combinedMask(extra) {
  const m = new Uint8Array(flood.w * flood.h);
  const parts = gestures.map(g => g.region || liveMask(g)).concat(extra ? [extra] : []);
  for (const part of parts) {
    for (let i = 0; i < m.length; i++) if (part[i]) m[i] = 255;
  }
  return m;
}

// by-color gestures have no stored region; preview them live on this frame
function liveMask(g) {
  return byColorMask(flood.data, flood.w, flood.h, g.color, g.tol);
}

function redrawOverlay(previewMask) {
  const m = combinedMask(previewMask || null);
  const c = document.createElement("canvas");
  c.width = flood.w; c.height = flood.h;
  const ctx = c.getContext("2d");
  const id = ctx.createImageData(flood.w, flood.h);
  for (let i = 0; i < m.length; i++) {
    if (m[i]) {
      id.data[i * 4] = 255; id.data[i * 4 + 2] = 255; id.data[i * 4 + 3] = 140;
    }
  }
  ctx.putImageData(id, 0, 0);
  const octx = overlay.getContext("2d");
  octx.imageSmoothingEnabled = false;
  octx.clearRect(0, 0, overlay.width, overlay.height);
  octx.drawImage(c, 0, 0, overlay.width, overlay.height);
}

function renderChips() {
  chipsEl.innerHTML = "";
  gestures.forEach(g => {
    const chip = document.createElement("span");
    chip.className = "chip";
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = `rgb(${g.color[0]},${g.color[1]},${g.color[2]})`;
    chip.append(sw, `${g.type} tol ${g.tol.toFixed(2)}`);
    chipsEl.appendChild(chip);
  });
  sendBtn.disabled = false;
}

view.addEventListener("mousedown", ev => {
  if (!flood) return;
  if (gestures.length >= MAX_RULES) {
    showBanner(`Rule cap reached (${MAX_RULES}) — SEND or Ctrl+Z first.`);
    return;
  }
  const [sx, sy] = toFlood(ev);
  const i = (sy * flood.w + sx) * 4;
  drag = { sx, sy, seed: [flood.data[i], flood.data[i + 1], flood.data[i + 2]],
           startX: ev.clientX, startY: ev.clientY, preview: null, tol: 0 };
  updateDrag(ev);
});

window.addEventListener("mousemove", ev => { if (drag) updateDrag(ev); });

function updateDrag(ev) {
  const dist = Math.hypot(ev.clientX - drag.startX, ev.clientY - drag.startY);
  drag.tol = Math.min(MAX_TOL, dist * TOL_PER_PIXEL);
  drag.preview = tool === "wand"
    ? floodFill(flood.data, flood.w, flood.h, drag.sx, drag.sy, drag.tol)
    : byColorMask(flood.data, flood.w, flood.h, drag.seed, drag.tol);
  setStatus(`${tool} tol ${drag.tol.toFixed(2)}`);
  redrawOverlay(drag.preview);
}

window.addEventListener("mouseup", () => {
  if (!drag) return;
  gestures.push({ type: tool, color: drag.seed, tol: drag.tol,
                  region: tool === "wand" ? drag.preview : null });
  drag = null;
  renderChips();
  redrawOverlay();
});

window.addEventListener("keydown", ev => {
  if (ev.key === "z" && (ev.ctrlKey || ev.metaKey)) {
    ev.preventDefault();
    gestures.pop();
    renderChips();
    redrawOverlay();
  } else if (ev.key === "r" || ev.key === "R") {
    fetchFrame();
  }
});

document.getElementById("tool-wand").addEventListener("click", () => setTool("wand"));
document.getElementById("tool-bycolor").addEventListener("click", () => setTool("bycolor"));
function setTool(t) {
  tool = t;
  document.getElementById("tool-wand").classList.toggle("active", t === "wand");
  document.getElementById("tool-bycolor").classList.toggle("active", t === "bycolor");
}

document.getElementById("refresh").addEventListener("click", fetchFrame);

sendBtn.addEventListener("click", async () => {
  if (!flood) return;
  // combined stencil = union of wand regions only (by-color rules are frame-wide)
  const stencil = new Uint8Array(flood.w * flood.h);
  for (const g of gestures) {
    if (g.region) for (let i = 0; i < stencil.length; i++) {
      if (g.region[i]) stencil[i] = 255;
    }
  }
  // Build binary string in chunks to avoid argument limit
  let bin = "";
  for (let i = 0; i < stencil.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, stencil.subarray(i, i + 0x8000));
  }
  const payload = {
    rules: gestures.map(g => ({
      type: g.type,
      color: g.color.map(c => Math.round(c / 255 * 10000) / 10000),
      tol: Math.round(g.tol * 10000) / 10000,
    })),
    stencil: { w: flood.w, h: flood.h,
               data: btoa(bin) },
  };
  sendBtn.disabled = true;
  setStatus("sending…");
  try {
    const resp = await fetch("/send", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const obj = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(obj.error || ("HTTP " + resp.status));
    gestures = [];
    renderChips();
    redrawOverlay();
    hideBanner();
    setStatus(`sent ${obj.rules} rule(s) — mask is live in TD`);
  } catch (e) {
    showBanner("SEND failed: " + e.message);
    setStatus("");
  } finally {
    sendBtn.disabled = false;
  }
});

window.addEventListener("resize", () => { if (frameImg) { layout(); redrawOverlay(); } });

fetchFrame();
