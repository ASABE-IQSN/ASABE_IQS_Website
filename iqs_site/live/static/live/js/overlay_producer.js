"use strict";

// ── DOM refs ──────────────────────────────────────────────────────────
const sseStatus     = document.getElementById("sseStatus");
const activeTeamName = document.getElementById("activeTeamName");
const teamNameInline = document.getElementById("teamNameInline");
const responsesBody = document.getElementById("responsesBody");
const refreshBtn    = document.getElementById("refreshBtn");
const sentToast     = document.getElementById("sentToast");
const allOffBtn = document.getElementById("allOffBtn");

// Map of toggle key → checkbox element. Every overlay card is its own module
// and defaults OFF; the producer turns each one on individually.
const TOGGLES = {
  // Pull data cards
  pull_hud:     { el: document.getElementById("togglePullHud") },
  pull_chart:   { el: document.getElementById("togglePullChart") },
  load_toad:    { el: document.getElementById("toggleLoadToad") },
  // Durability data cards
  dur_hud:      { el: document.getElementById("toggleDurHud") },
  dur_chart:    { el: document.getElementById("toggleDurChart") },
  // Maneuverability data card
  man_hud:      { el: document.getElementById("toggleManHud") },
  // Common cards (shared across all events)
  tractor_card: { el: document.getElementById("toggleTractorCard") },
  up_next:      { el: document.getElementById("toggleUpNext") },
  reactions:    { el: document.getElementById("toggleReactions") },
  poll:         { el: document.getElementById("togglePoll") },
};

// ── State ─────────────────────────────────────────────────────────────
// The producer follows whichever activity a team is currently running.
// activeSource.type is "pull" | "dur" | "man"; id is the matching run id.
let activeSource    = { type: null, id: null };
let currentTeamName = null;
let toastTimer      = null;

// Query-param name the active-responses endpoint expects per activity type.
const SOURCE_PARAM = { pull: "pull_id", dur: "dur_run_id", man: "man_run_id" };

// ── CSRF ──────────────────────────────────────────────────────────────
function getCsrf() {
  return document.cookie.split("; ")
    .find(r => r.startsWith("csrftoken="))
    ?.split("=")[1] ?? "";
}

// ── SSE ───────────────────────────────────────────────────────────────
function startSSE() {
  const es = new EventSource(window.IQS.apiUrl + "/api/stream");

  // Status events identify the team's active run. Pull streams carry pull_id;
  // durability/maneuverability streams carry run_id. Whichever activity reports
  // a valid id most recently becomes the source we show responses for.
  function statusHandler(type, idField) {
    return (e) => {
      const s = JSON.parse(e.data);
      const newId = s[idField] ?? null;
      if (type !== activeSource.type || newId !== activeSource.id) {
        activeSource = { type: newId == null ? null : type, id: newId };
        fetchResponses();
      }
    };
  }

  es.addEventListener("status",      statusHandler("pull", "pull_id"));
  es.addEventListener("pull_status", statusHandler("pull", "pull_id"));
  es.addEventListener("dur_status",  statusHandler("dur",  "run_id"));
  es.addEventListener("man_status",  statusHandler("man",  "run_id"));

  // info events carry team name for the header display only
  function handleInfo(e) {
    const info = JSON.parse(e.data);
    currentTeamName = info.team_name ?? null;
    updateTeamHeader();
  }

  es.addEventListener("info",      handleInfo);
  es.addEventListener("pull_info", handleInfo);
  es.addEventListener("dur_info",  handleInfo);
  es.addEventListener("man_info",  handleInfo);

  es.addEventListener("overlay_toggle", (e) => {
    try {
      const state = JSON.parse(e.data) || {};
      syncToggleUI(state);
    } catch (_) {}
  });

  es.onopen = () => {
    sseStatus.textContent = "LIVE";
    sseStatus.classList.add("chip-live");
  };

  es.onerror = () => {
    sseStatus.textContent = "OFF";
    sseStatus.classList.remove("chip-live");
  };
}

// ── Team header ────────────────────────────────────────────────────────
function updateTeamHeader() {
  activeTeamName.textContent = currentTeamName ?? "—";
  teamNameInline.textContent = currentTeamName ?? "current team";
}

// ── Fetch responses ────────────────────────────────────────────────────
async function fetchResponses() {
  const param = SOURCE_PARAM[activeSource.type];
  if (!param || !activeSource.id) {
    responsesBody.innerHTML = '<div class="empty">No active run.</div>';
    return;
  }
  responsesBody.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const res = await fetch(`/api/v1/overlay/active-responses/?${param}=${activeSource.id}`);
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();

    if (data.team) {
      currentTeamName = data.team.team_name;
      updateTeamHeader();
    }

    renderAll(data);
  } catch (_) {
    responsesBody.innerHTML = '<div class="empty">Failed to load responses.</div>';
  }
}

// ── Render everything ─────────────────────────────────────────────────
function renderAll(data) {
  const individual = data.individual_responses || [];
  const groups     = data.layout_groups || [];

  if (!individual.length && !groups.length) {
    responsesBody.innerHTML = '<div class="empty">No form responses for this team.</div>';
    return;
  }

  const list = document.createElement("div");
  list.className = "response-list";

  // Layout group cards (multi-field combined)
  for (const g of groups) {
    const card = document.createElement("div");
    card.className = "response-card response-card--layout";
    const fieldRows = Object.entries(g.fields)
      .map(([role, val]) => {
        const isImg = /\.(jpg|jpeg|png|gif|webp)(\?|$)/i.test(val) || val.startsWith("http") && val.includes("/media/");
        return isImg
          ? `<div class="layout-field"><span class="layout-role">${escHtml(role)}</span><img src="${escHtml(val)}" style="max-height:80px;border-radius:6px;margin-top:4px;display:block;"></div>`
          : `<div class="layout-field"><span class="layout-role">${escHtml(role)}</span><span class="layout-val">${escHtml(val)}</span></div>`;
      }).join("");

    // Reference-only fields (e.g. which events the driver is running). Shown
    // here to help the operator but never sent to the on-air overlay.
    const infoEntries = Object.entries(g.info || {});
    const infoHtml = infoEntries.length
      ? `<div class="layout-info" style="margin-top:.5rem;padding-top:.5rem;border-top:1px dashed rgba(148,163,184,.35);">
           <div class="layout-info-note" style="font-size:.7rem;text-transform:uppercase;letter-spacing:.04em;color:#94a3b8;margin-bottom:.25rem;">Reference only · not shown on overlay</div>
           ${infoEntries.map(([role, val]) =>
             `<div class="layout-field"><span class="layout-role">${escHtml(role)}</span><span class="layout-val">${escHtml(val)}</span></div>`
           ).join("")}
         </div>`
      : "";

    card.innerHTML = `
      <div class="response-card-body">
        <div class="response-badge">${escHtml(g.form_name)} &mdash; ${escHtml(g.layout_name)}</div>
        <div class="response-question" style="margin-bottom:.5rem;">${escHtml(g.group_name)}</div>
        <div class="layout-fields">${fieldRows}</div>
        ${infoHtml}
      </div>
      <button class="send-btn" title="Send layout to overlay">Send</button>
    `;
    const btn = card.querySelector(".send-btn");
    btn.addEventListener("click", () => sendLayoutCard(g, btn));
    list.appendChild(card);
  }

  // Individual Q&A / image cards
  for (const r of individual) {
    const card = document.createElement("div");
    card.className = "response-card";
    const answerHtml = r.image_url
      ? `<img src="${escHtml(r.image_url)}" style="max-height:80px;border-radius:6px;margin-top:4px;display:block;">`
      : `<p class="response-answer">${escHtml(r.answer)}</p>`;

    card.innerHTML = `
      <div class="response-card-body">
        <div class="response-badge">${escHtml(r.form_name)}</div>
        <p class="response-question">${escHtml(r.question)}</p>
        ${answerHtml}
      </div>
      <button class="send-btn" title="Send to overlay">Send</button>
    `;
    const btn = card.querySelector(".send-btn");
    btn.addEventListener("click", () => sendIndividualCard(r, btn));
    list.appendChild(card);
  }

  responsesBody.innerHTML = "";
  responsesBody.appendChild(list);
}

// ── Send helpers ──────────────────────────────────────────────────────
async function sendIndividualCard(response, btn) {
  await _postCard({
    layout:    response.image_url ? "image" : "stat",
    question:  response.question,
    answer:    response.answer,
    image_url: response.image_url || "",
    form_name: response.form_name,
    team_name: currentTeamName ?? "",
  }, btn);
}

async function sendLayoutCard(group, btn) {
  await _postCard({
    layout:      group.layout_type,
    layout_name: group.layout_name,
    layout_id:   group.layout_id,
    group_name:  group.group_name,
    fields:      group.fields,
    form_name:   group.form_name,
    team_name:   currentTeamName ?? "",
  }, btn);
}

async function _postCard(payload, btn) {
  btn.disabled = true;
  btn.textContent = "Sending…";
  try {
    const res = await fetch("/api/v1/overlay/card/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrf() },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(res.status);
    btn.textContent = "Sent ✓";
    btn.classList.add("sent");
    showToast();
    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = "Send";
      btn.classList.remove("sent");
    }, 3000);
  } catch (_) {
    btn.disabled = false;
    btn.textContent = "Error – retry";
  }
}

// ── Toast ─────────────────────────────────────────────────────────────
function showToast() {
  clearTimeout(toastTimer);
  sentToast.classList.add("show");
  toastTimer = setTimeout(() => sentToast.classList.remove("show"), 2500);
}

// ── Escape HTML ───────────────────────────────────────────────────────
function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Overlay toggles ───────────────────────────────────────────────────
let suppressToggleEvents = false;

function syncToggleUI(state) {
  suppressToggleEvents = true;
  for (const [key, cfg] of Object.entries(TOGGLES)) {
    if (cfg.el) cfg.el.checked = state[key] === true;
  }
  suppressToggleEvents = false;
}

async function allOff() {
  // Build a bulk state object turning every known card off.
  const offState = {};
  for (const key of Object.keys(TOGGLES)) offState[key] = false;
  try {
    const res = await fetch("/api/v1/overlay/toggle/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrf() },
      body: JSON.stringify({ state: offState }),
    });
    if (!res.ok) throw new Error(res.status);
    syncToggleUI(await res.json());
  } catch (err) {
    console.warn("All Off failed", err);
  }
}

async function sendToggle(key, value) {
  try {
    const res = await fetch("/api/v1/overlay/toggle/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrf() },
      body: JSON.stringify({ key, value }),
    });
    if (!res.ok) throw new Error(res.status);
    const state = await res.json();
    syncToggleUI(state);
  } catch (err) {
    console.warn("Toggle failed", err);
    suppressToggleEvents = true;
    const cfg = TOGGLES[key];
    if (cfg && cfg.el) cfg.el.checked = !value; // roll back
    suppressToggleEvents = false;
  }
}

async function loadToggleState() {
  try {
    const res = await fetch("/api/v1/overlay/toggle/");
    if (!res.ok) return;
    syncToggleUI(await res.json());
  } catch (_) {}
}

for (const [key, cfg] of Object.entries(TOGGLES)) {
  if (!cfg.el) continue;
  cfg.el.addEventListener("change", () => {
    if (suppressToggleEvents) return;
    sendToggle(key, cfg.el.checked);
  });
}

// ── Boot ──────────────────────────────────────────────────────────────
refreshBtn.addEventListener("click", fetchResponses);
if (allOffBtn) allOffBtn.addEventListener("click", allOff);
startSSE();
loadToggleState();
