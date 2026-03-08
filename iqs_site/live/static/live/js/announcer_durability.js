"use strict";

// ── Field binding ──────────────────────────────────────────────────────
const fields = {};
document.querySelectorAll("[data-field]").forEach((el) => {
  fields[el.dataset.field] = el;
});

function setField(key, value) {
  if (!fields[key]) return;
  fields[key].textContent = value ?? "—";
}

// ── DOM refs ──────────────────────────────────────────────────────────
const sseStatus = document.getElementById("sseStatus");
const waitingMsg = document.getElementById("waitingMsg");
const mainContent = document.getElementById("mainContent");
const tractorPhoto = document.getElementById("tractorPhoto");
const tractorPhotoPlaceholder = document.getElementById("tractorPhotoPlaceholder");
const socialLinks = document.getElementById("socialLinks");
const formResponsesBody = document.getElementById("formResponsesBody");
const reportsBody = document.getElementById("reportsBody");
const classChip = fields["team_class"];

// ── State ─────────────────────────────────────────────────────────────
let currentRunId = null;

// ── SSE ───────────────────────────────────────────────────────────────
function startSSE() {
  const es = new EventSource(window.IQS.apiUrl + "/api/stream");

  es.addEventListener("dur_info", (e) => {
    const info = JSON.parse(e.data);
    setField("team_name", info.team_name);
    setField("team_number", info.team_number);
  });

  es.addEventListener("dur_status", (e) => {
    const s = JSON.parse(e.data);
    const id = s.run_id ?? null;
    if (id === currentRunId) return;
    currentRunId = id;
    fetchAnnouncerData(id);
  });

  // Also update laps in real time without a full re-fetch
  es.addEventListener("dur_status", (e) => {
    const s = JSON.parse(e.data);
    if (s.run_id === currentRunId && s.total_laps != null) {
      setField("total_laps", s.total_laps);
      setField("run_state", s.state || "—");
    }
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

// ── Fetch + render ────────────────────────────────────────────────────
async function fetchAnnouncerData(runId) {
  if (!runId) {
    waitingMsg.style.display = "";
    mainContent.style.display = "none";
    return;
  }
  try {
    const res = await fetch(`/api/v1/announcer/durability/${runId}/`);
    if (!res.ok) return;
    const data = await res.json();
    renderAll(data);
  } catch (_) {}
}

function renderAll(data) {
  waitingMsg.style.display = "none";
  mainContent.style.display = "";

  const team = data.team || {};
  const info = team.info || {};
  const tractor = data.tractor || {};
  const standing = data.event_standing || {};

  setField("team_name", team.team_name);
  setField("team_number", team.team_number);
  setField("team_number_id", team.team_number);
  setField("nickname", info.nickname);
  setField("bio", info.bio);

  if (classChip) {
    if (team.team_class) {
      classChip.textContent = team.team_class;
      classChip.style.display = "";
    } else {
      classChip.style.display = "none";
    }
  }

  setField("tractor_name", tractor.tractor_name);
  setField("tractor_year", tractor.year ? `(${tractor.year})` : "");
  renderPhoto(tractor.photo_url);

  setField("rank", standing.rank != null ? `#${standing.rank}` : "—");
  setField("total_score", standing.total_score ?? "—");

  setField("run_state", data.run_state || "—");
  setField("total_laps", data.total_laps ?? "—");

  renderSocialLinks(info);
  renderFormResponses(data.form_responses || []);
  renderReports(data.reports || []);
}

function renderPhoto(url) {
  if (!url) {
    tractorPhoto.style.display = "none";
    tractorPhotoPlaceholder.style.display = "";
    return;
  }
  const src = url.startsWith("http") ? url : `/media/${url}`;
  tractorPhoto.src = src;
  tractorPhoto.style.display = "";
  tractorPhotoPlaceholder.style.display = "none";
}

function renderSocialLinks(info) {
  socialLinks.innerHTML = "";
  if (info.instagram) {
    socialLinks.insertAdjacentHTML("beforeend",
      `<a href="${escHtml(info.instagram)}" target="_blank" rel="noopener">Instagram</a>`);
  }
  if (info.website) {
    socialLinks.insertAdjacentHTML("beforeend",
      `<a href="${escHtml(info.website)}" target="_blank" rel="noopener">Website</a>`);
  }
  if (info.youtube) {
    socialLinks.insertAdjacentHTML("beforeend",
      `<a href="${escHtml(info.youtube)}" target="_blank" rel="noopener">YouTube</a>`);
  }
}

function renderFormResponses(responses) {
  if (!responses.length) {
    formResponsesBody.innerHTML = '<div class="empty">No form responses submitted.</div>';
    return;
  }
  let html = "";
  for (const fr of responses) {
    html += `<div class="form-section">
      <div class="form-section-title">${escHtml(fr.form_name)}</div>`;
    for (const qa of fr.questions) {
      html += `<div class="qa-pair">
        <p class="qa-question">${escHtml(qa.question)}</p>
        <p class="qa-answer">${escHtml(qa.answer || "—")}</p>
      </div>`;
    }
    html += "</div>";
  }
  formResponsesBody.innerHTML = html;
}

function renderReports(reports) {
  if (!reports.length) {
    reportsBody.innerHTML = '<div class="empty">No reports uploaded.</div>';
    return;
  }
  let html = "";
  for (const r of reports) {
    html += `<div class="report-item">
      <a class="report-link" href="${escHtml(r.url)}" target="_blank" rel="noopener">
        &#128196; ${escHtml(r.label)}
      </a>
      <iframe class="report-embed" src="${escHtml(r.url)}" title="${escHtml(r.label)}"></iframe>
    </div>`;
  }
  reportsBody.innerHTML = html;
}

function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Boot ──────────────────────────────────────────────────────────────
startSSE();
