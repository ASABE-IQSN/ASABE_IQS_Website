"use strict";

// ── DOM refs ──────────────────────────────────────────────────────────
const sseStatus     = document.getElementById("sseStatus");
const activeTeamName = document.getElementById("activeTeamName");
const teamNameInline = document.getElementById("teamNameInline");
const responsesBody = document.getElementById("responsesBody");
const refreshBtn    = document.getElementById("refreshBtn");
const sentToast     = document.getElementById("sentToast");
const toggleTractorCard = document.getElementById("toggleTractorCard");
const toggleUpNext      = document.getElementById("toggleUpNext");

// ── State ─────────────────────────────────────────────────────────────
let currentPullId   = null;
let currentTeamName = null;
let toastTimer      = null;

// ── CSRF ──────────────────────────────────────────────────────────────
function getCsrf() {
  return document.cookie.split("; ")
    .find(r => r.startsWith("csrftoken="))
    ?.split("=")[1] ?? "";
}

// ── SSE ───────────────────────────────────────────────────────────────
function startSSE() {
  const es = new EventSource(window.IQS.apiUrl + "/api/stream");

  // status and pull_status both carry pull_id
  function handleStatus(e) {
    const s = JSON.parse(e.data);
    const newPullId = s.pull_id ?? null;
    if (newPullId !== currentPullId) {
      currentPullId = newPullId;
      fetchResponses();
    }
  }

  es.addEventListener("status", handleStatus);
  es.addEventListener("pull_status", handleStatus);

  // info events carry team name for the header display only
  function handleInfo(e) {
    const info = JSON.parse(e.data);
    currentTeamName = info.team_name ?? null;
    updateTeamHeader();
  }

  es.addEventListener("info", handleInfo);
  es.addEventListener("pull_info", handleInfo);

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
  if (!currentPullId) {
    responsesBody.innerHTML = '<div class="empty">No active pull.</div>';
    return;
  }
  responsesBody.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const res = await fetch(`/api/v1/overlay/active-responses/?pull_id=${currentPullId}`);
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

    card.innerHTML = `
      <div class="response-card-body">
        <div class="response-badge">${escHtml(g.form_name)} &mdash; ${escHtml(g.layout_name)}</div>
        <div class="response-question" style="margin-bottom:.5rem;">${escHtml(g.group_name)}</div>
        <div class="layout-fields">${fieldRows}</div>
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
  if (toggleTractorCard) toggleTractorCard.checked = !!state.tractor_card;
  if (toggleUpNext)      toggleUpNext.checked      = !!state.up_next;
  suppressToggleEvents = false;
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
    if (key === "tractor_card" && toggleTractorCard) toggleTractorCard.checked = !value;
    if (key === "up_next"      && toggleUpNext)      toggleUpNext.checked      = !value;
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

if (toggleTractorCard) {
  toggleTractorCard.addEventListener("change", () => {
    if (suppressToggleEvents) return;
    sendToggle("tractor_card", toggleTractorCard.checked);
  });
}

if (toggleUpNext) {
  toggleUpNext.addEventListener("change", () => {
    if (suppressToggleEvents) return;
    sendToggle("up_next", toggleUpNext.checked);
  });
}

// ── Boot ──────────────────────────────────────────────────────────────
refreshBtn.addEventListener("click", fetchResponses);
startSSE();
loadToggleState();
