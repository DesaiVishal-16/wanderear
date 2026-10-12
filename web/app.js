/* WanderEar web app: no build step, no dependencies. */

const $ = (sel) => document.querySelector(sel);
const api = {
  status: "/api/status",
  postcards: "/api/postcards",
  analyze: "/api/analyze",
  search: "/api/search",
  media: (name) => `/media/${encodeURIComponent(name)}`,
};

let serverMode = false;

/* ------------------------------------------------------------------ helpers */
const baseName = (p) => (p ? String(p).split(/[\\/]/).pop() : "");

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function toast(message, kind = "info") {
  const t = el("div", `toast ${kind}`, message);
  document.body.appendChild(t);
  setTimeout(() => t.classList.add("show"), 10);
  setTimeout(() => {
    t.classList.remove("show");
    setTimeout(() => t.remove(), 300);
  }, 3200);
}

function setBusy(on, message = "") {
  const hint = $("#hint");
  if (!hint) return;
  hint.textContent = message;
  hint.classList.toggle("busy", on);
  document.body.classList.toggle("busy", on);
}

/* -------------------------------------------------------------- rendering */
function renderCard(card, { prepend = false } = {}) {
  const node = $("#card-template").content.firstElementChild.cloneNode(true);
  const ctx = card.context || {};
  const pc = card.postcard || {};

  node.querySelector(".title").textContent = pc.title || "Untitled moment";
  node.querySelector(".story").textContent = pc.body || "";

  const img = node.querySelector(".spectrogram");
  const spec = baseName(card.spectrogram_path);
  if (spec) {
    img.src = api.media(spec);
    img.alt = "spectrogram of the recording";
  } else {
    img.remove();
  }

  const audio = baseName(card.audio_path);
  const audioEl = node.querySelector("audio");
  if (audio) {
    audioEl.src = api.media(audio);
  } else {
    audioEl.remove();
  }

  const chips = node.querySelector(".chips");
  (card.labels || []).forEach((lab) => {
    const chip = el("span", "chip", `${lab.name} ${(lab.confidence * 100).toFixed(0)}%`);
    chips.appendChild(chip);
  });

  node.querySelector(".meta").textContent =
    [ctx.local_time, ctx.season, card.classifier, pc.narrator]
      .filter(Boolean)
      .join(" · ");

  const similar = node.querySelector(".similar-btn");
  if (serverMode && card.id) {
    similar.addEventListener("click", () => findSimilar(card.id, pc.title));
  } else {
    similar.remove();
  }

  if (prepend) {
    $("#cards").prepend(node);
    node.classList.add("fresh");
  } else {
    $("#cards").appendChild(node);
  }
  $("#empty").hidden = true;
  updateCount();
  return node;
}

function renderFeed(cards) {
  const wrap = $("#cards");
  wrap.replaceChildren();
  // newest first
  [...cards].reverse().forEach((c) => renderCard(c));
  updateCount();
}

function updateCount() {
  const n = $("#cards").querySelectorAll(".card").length;
  $("#count").textContent = n ? `${n} moment${n === 1 ? "" : "s"}` : "";
  $("#empty").hidden = n > 0;
}

/* ---------------------------------------------------------------- capture */
async function loadFeed() {
  try {
    const res = await fetch(api.postcards);
    const data = await res.json();
    renderFeed(Array.isArray(data) ? data : []);
  } catch (err) {
    // static hosting fallback: postcards.json
    try {
      const res = await fetch("postcards.json");
      renderFeed(res.ok ? await res.json() : []);
    } catch {
      renderFeed([]);
    }
  }
}

async function probeServer() {
  try {
    const res = await fetch(api.status);
    if (!res.ok) throw new Error("no server");
    await res.json();
    serverMode = true;
  } catch {
    serverMode = false;
    setAnalyzeEnabled(false);
    $("#hint").textContent =
      "Recording and analyzing need the local server. Run: python web/server.py";
  }
}

function setAnalyzeEnabled(on) {
  for (const id of ["#record", "#upload-btn"]) {
    const b = $(id);
    if (b) b.disabled = !on;
  }
}

async function sendForAnalysis(blob, name) {
  const classifier = $("#classifier").value;
  const narrator = $("#narrator").value;
  const url = `${api.analyze}?name=${encodeURIComponent(name)}` +
    `&classifier=${encodeURIComponent(classifier)}&narrator=${encodeURIComponent(narrator)}`;
  setBusy(true, "Listening to the world…");
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": blob.type || "application/octet-stream" },
    body: blob,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `analyze failed (${res.status})`);
  return data;
}

/* --------------------------------------------------------------- recording */
let mediaRecorder = null;
let chunks = [];
let timerId = null;
let startedAt = 0;

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const type = mediaRecorder.mimeType || "audio/webm";
      const blob = new Blob(chunks, { type });
      const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
      try {
        const card = await sendForAnalysis(blob, `recording.${ext}`);
        renderCard(card, { prepend: true });
        toast("Postcard created", "ok");
      } catch (err) {
        toast(err.message, "err");
      } finally {
        setBusy(false);
      }
    };
    mediaRecorder.start();
    startedAt = performance.now();
    $("#recorder").hidden = false;
    $("#record").classList.add("recording");
    $("#record-label").textContent = "Stop";
    tick();
    timerId = setInterval(tick, 100);
    setBusy(false);
  } catch (err) {
    toast("Microphone unavailable: " + err.message, "err");
  }
}

function tick() {
  $("#timer").textContent = ((performance.now() - startedAt) / 1000).toFixed(1) + "s";
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
  clearInterval(timerId);
  $("#recorder").hidden = true;
  $("#record").classList.remove("recording");
  $("#record-label").textContent = "Record";
}

/* ----------------------------------------------------------------- search */
async function findSimilar(id) {
  try {
    const res = await fetch(`${api.search}?like=${encodeURIComponent(id)}&limit=5`);
    if (!res.ok) throw new Error("search failed");
    const results = await res.json();
    showSimilar(results, id);
  } catch (err) {
    toast(err.message, "err");
  }
}

function showSimilar(results, selfId) {
  const box = $("#similar");
  const list = $("#similar-list");
  list.replaceChildren();
  results.forEach((r) => {
    const card = r.postcard || {};
    const li = el("li");
    const pct = Math.round((r.score ?? 0) * 100);
    li.appendChild(el("span", "score", `${pct}%`));
    li.appendChild(el("span", "sim-title", card.postcard?.title || card.id || "?"));
    if (card.id === selfId) li.classList.add("self");
    li.addEventListener("click", () => {
      const match = [...document.querySelectorAll(".card")].find(
        (c) => c.querySelector(".title")?.textContent === (card.postcard?.title || "\u0000")
      );
      if (match) {
        match.scrollIntoView({ behavior: "smooth", block: "center" });
        match.classList.add("flash");
        setTimeout(() => match.classList.remove("flash"), 1200);
      }
    });
    list.appendChild(li);
  });
  box.hidden = false;
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ------------------------------------------------- custom dropdown selects */
function closeAllSelects() {
  document.querySelectorAll("[data-select].is-open").forEach((wrap) => {
    wrap.classList.remove("is-open");
    wrap.querySelector(".select-trigger").setAttribute("aria-expanded", "false");
    wrap.querySelector(".select-menu").hidden = true;
  });
}

function initSelects() {
  document.querySelectorAll("[data-select]").forEach((wrap) => {
    const native = wrap.querySelector("select");
    const trigger = wrap.querySelector(".select-trigger");
    const valueEl = wrap.querySelector(".select-value");
    const menu = wrap.querySelector(".select-menu");

    for (const opt of native.options) {
      const li = document.createElement("li");
      li.className = "select-option";
      li.dataset.value = opt.value;
      li.textContent = opt.textContent;
      li.setAttribute("role", "option");
      li.addEventListener("click", () => {
        native.value = opt.value;
        native.dispatchEvent(new Event("change", { bubbles: true }));
        closeAllSelects();
        trigger.focus();
      });
      menu.appendChild(li);
    }

    const sync = () => {
      const selected = native.selectedOptions[0];
      valueEl.textContent = selected ? selected.textContent : "";
      menu.querySelectorAll(".select-option").forEach((li) => {
        const on = li.dataset.value === native.value;
        li.classList.toggle("is-selected", on);
        li.setAttribute("aria-selected", on ? "true" : "false");
      });
    };
    native.addEventListener("change", sync);

    trigger.addEventListener("click", () => {
      const isOpen = wrap.classList.contains("is-open");
      closeAllSelects();
      if (isOpen) return;
      wrap.classList.add("is-open");
      trigger.setAttribute("aria-expanded", "true");
      menu.hidden = false;
    });

    trigger.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      if (wrap.classList.contains("is-open")) return;
      closeAllSelects();
      wrap.classList.add("is-open");
      trigger.setAttribute("aria-expanded", "true");
      menu.hidden = false;
    });

    sync();
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-select]")) closeAllSelects();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAllSelects();
  });
}

/* -------------------------------------------------------------------- wire */
function wire() {
  $("#record").addEventListener("click", () => {
    if (mediaRecorder && mediaRecorder.state === "recording") stopRecording();
    else startRecording();
  });

  $("#upload-btn").addEventListener("click", () => $("#file").click());
  $("#file").addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const card = await sendForAnalysis(file, file.name);
      renderCard(card, { prepend: true });
      toast("Postcard created", "ok");
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setBusy(false);
    }
  });

  $("#similar-close").addEventListener("click", () => ($("#similar").hidden = true));

  const settings = $("#settings");
  $("#settings-btn").addEventListener("click", () => settings.showModal());
  settings.addEventListener("click", (e) => {
    if (e.target === settings) settings.close();
  });
}

initSelects();
wire();
probeServer().then(loadFeed);