// --- bind fields ---
const fields = {};
document.querySelectorAll("[data-field]").forEach((el) => {
  fields[el.dataset.field] = el;
});

function setField(key, value, digits = null) {
  const el = fields[key];
  if (!el) return;
  el.textContent =
    typeof value === "number" && digits !== null
      ? value.toFixed(digits)
      : String(value);
}

// --- status UI ---
const statusPill = document.getElementById("statusPill");
const statusText = document.getElementById("statusText");

function setStatus(mode, text) {
  // mode: "live" | "stale" | "neutral"
  statusPill.classList.remove("status-live", "status-stale");
  if (mode === "live") statusPill.classList.add("status-live");
  if (mode === "stale") statusPill.classList.add("status-stale");
  statusText.textContent = text;
}

// --- chart setup ---
const MAX_POINTS = 1200;
const canvas = document.getElementById("liveChart");
let chart = null;

function initChart() {
  if (!canvas) return;

  chart = new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Speed (ft/s)",
          data: [],
          yAxisID: "ySpeed",
          showLine: true,
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.25,
        },
        {
          label: "Force (lbf)",
          data: [],
          yAxisID: "yForce",
          showLine: true,
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.25,
        },
      ],
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      plugins: {
        legend: {
          labels: {
            color: "rgba(226,232,240,0.9)",
            boxWidth: 10,
            boxHeight: 10,
          },
        },
        tooltip: {
          enabled: false, // overlays tend to look cleaner without hover tooltips
        },
      },
      scales: {
        x: {
          type: "linear",
          title: { text: "Distance (ft)", display: true, color: "rgba(148,163,184,0.95)" },
          ticks: { color: "rgba(148,163,184,0.95)" },
          grid: { color: "rgba(148,163,184,0.12)" },
          bounds: "data",        // fit exactly to data range
          grace: "2%",
          min: 0,
        //   max: 100
        },
        ySpeed: {
          position: "left",
          title: { text: "Speed (ft/s)", display: true, color: "rgba(148,163,184,0.95)" },
          ticks: { color: "rgba(148,163,184,0.95)" },
          grid: { color: "rgba(148,163,184,0.12)" },
          bounds: "data",        // fit exactly to data range
          grace: "2%",
          min: 0,
        //   max: 7,
        },
        yForce: {
          position: "right",
          title: { text: "Force (lbf)", display: true, color: "rgba(148,163,184,0.95)" },
          ticks: { color: "rgba(148,163,184,0.95)" },
          grid: { drawOnChartArea: false, color: "rgba(148,163,184,0.12)" },
          bounds: "data",        // fit exactly to data range
          grace: "2%",
          min: 0,
        //   max: 1000,
        },
      },
    },
  });
}

function clearChart() {
  if (!chart) return;
  chart.data.datasets.forEach((ds) => (ds.data.length = 0));
  chart.update("none");
}

function pushPoint(distance, speed, force) {
  if (!chart) return;

  chart.data.datasets[0].data.push({ x: distance, y: speed });
  chart.data.datasets[1].data.push({ x: distance, y: force });

  if (chart.data.datasets[0].data.length > MAX_POINTS) {
    chart.data.datasets.forEach((ds) => ds.data.shift());
  }

  chart.update("none");
}

// --- live state ---
let pull_id = null;
let pull_active = false;

// Track last data time to show "stale" if stream stops updating
let lastDataMs = 0;
const STALE_AFTER_MS = 2500;

function startStaleMonitor() {
  setInterval(() => {
    if (!lastDataMs) return;
    const age = Date.now() - lastDataMs;
    if (age > STALE_AFTER_MS) {
      setStatus("stale", "Signal paused");
    }
  }, 500);
}

// --- SSE hookup ---
function startSSE() {
  setStatus("neutral", "Connecting…");

  const es = new EventSource(window.IQS.apiUrl + "/api/stream");

  es.addEventListener("open", () => {
    setStatus("neutral", "Connected");
  });

  es.addEventListener("status", (e) => {
    const s = JSON.parse(e.data);

    // detect pull change
    if (s.pull_id !== pull_id) {
      pull_id = s.pull_id;
      clearChart();
    }

    pull_active = s.status === 1;

    // You can use this for UI messaging too
    if (pull_active) setStatus("live", "LIVE");
    else setStatus("neutral", "Standing by");
  });

  es.addEventListener("info", (e) => {
    const info = JSON.parse(e.data);

    setField("hook_name", info.hook_name ?? "—");
    setField("team_name", info.team_name ?? "—");
    setField("team_number", info.team_number ?? "");

    handleTractorInfo(info);
  });

  es.addEventListener("overlay_toggle", (e) => {
    try {
      applyOverlayToggle(JSON.parse(e.data) || {});
    } catch (_) {}
  });

  es.addEventListener("data", (e) => {
    const data = JSON.parse(e.data);

    const speed = Number(data.speed);
    const force = Number(data.force);
    const distance = Number(data.distance);

    if (![speed, force, distance].every(Number.isFinite)) return;

    lastDataMs = Date.now();
    if (pull_active) setStatus("live", "LIVE");

    // update page fields (telemetry speed is ft/s; HUD displays mph)
    setField("speed", speed * 0.681818, 1);
    setField("force", force, 0);
    setField("distance", distance, 1);

    pushPoint(distance, speed, force);
  });

  es.addEventListener("overlay_card", (e) => {
    const data = JSON.parse(e.data);
    showOverlayCard(data);
  });

  es.addEventListener("reactions", (e) => {
    const data = JSON.parse(e.data);
    updateReactionCounts(data);
  });

  es.addEventListener("poll", (e) => {
    const data = JSON.parse(e.data);
    updatePollCard(data);
  });

  es.addEventListener("load_toad", (e) => {
    const d = JSON.parse(e.data);
    const drivePressure = Number(d.drive_pressure);
    const speed = Number(d.speed);
    if (![drivePressure, speed].every(Number.isFinite)) return;

    // Visibility is controlled by the load_toad toggle; just update values.
    setField("lt_drive_pressure", drivePressure, 1);
    setField("lt_speed", speed, 1);
  });

  es.addEventListener("pull_schedule", (e) => {
    try {
      handlePullSchedule(JSON.parse(e.data) || {});
    } catch (_) {}
  });

  // ── Durability scene ──────────────────────────────────────────────
  es.addEventListener("dur_status", (e) => {
    try { handleDurStatus(JSON.parse(e.data) || {}); } catch (_) {}
  });
  es.addEventListener("dur_info", (e) => {
    try { handleDurInfo(JSON.parse(e.data) || {}); } catch (_) {}
  });
  es.addEventListener("dur_data", (e) => {
    try { handleDurData(JSON.parse(e.data) || {}); } catch (_) {}
  });
  es.addEventListener("dur_clock", (e) => {
    try { handleDurClock(JSON.parse(e.data) || {}); } catch (_) {}
  });

  // ── Maneuverability scene (HUD stub — no telemetry stream) ─────────
  es.addEventListener("man_status", (e) => {
    try { handleManStatus(JSON.parse(e.data) || {}); } catch (_) {}
  });
  es.addEventListener("man_info", (e) => {
    try { handleManInfo(JSON.parse(e.data) || {}); } catch (_) {}
  });

  es.onerror = (err) => {
    // Browser auto-reconnects; this fires frequently during reconnect
    console.warn("SSE error", err);
    setStatus("stale", "Reconnecting…");
  };
}

// --- overlay cards (GSAP) ---
const CARD_HOLD_S = 12;

// Stat card
const ocStatCard = document.getElementById("ocStatCard");
const ocBadge    = document.getElementById("ocBadge");
const ocTeam     = document.getElementById("ocTeam");
const ocQuestion = document.getElementById("ocQuestion");
const ocAnswer   = document.getElementById("ocAnswer");
const ocProgress = document.getElementById("ocProgress");

// Profile card
const ocProfileCard        = document.getElementById("ocProfileCard");
const ocProfilePhoto       = document.getElementById("ocProfilePhoto");
const ocProfilePhotoHolder = document.getElementById("ocProfilePhotoPlaceholder");
const ocProfileBadge       = document.getElementById("ocProfileBadge");
const ocProfileTeam        = document.getElementById("ocProfileTeam");
const ocProfileName        = document.getElementById("ocProfileName");
const ocProfileBio         = document.getElementById("ocProfileBio");
const ocProfileStats       = document.getElementById("ocProfileStats");
const ocProfileProgress    = document.getElementById("ocProfileProgress");

// Image card
const ocImageCard     = document.getElementById("ocImageCard");
const ocImagePhoto    = document.getElementById("ocImagePhoto");
const ocImageBadge    = document.getElementById("ocImageBadge");
const ocImageCaption  = document.getElementById("ocImageCaption");
const ocImageProgress = document.getElementById("ocImageProgress");

// Dynamic scene card
const ocSceneCard     = document.getElementById("ocSceneCard");
const ocSceneProgress = document.getElementById("ocSceneProgress");

let cardTimeline = null;
const ALL_CARDS = [ocStatCard, ocProfileCard, ocImageCard, ocSceneCard];

function _animateCard(wrap, progressEl, innerEls) {
  if (cardTimeline) cardTimeline.kill();
  // Hide all other cards first
  ALL_CARDS.forEach(c => { if (c !== wrap) gsap.set(c, { visibility: "hidden", opacity: 0 }); });

  gsap.set(progressEl, { scaleX: 1 });
  cardTimeline = gsap.timeline()
    .set(wrap, { visibility: "visible" })
    .fromTo(wrap,
      { y: 50, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.55, ease: "back.out(1.5)" }
    )
    .fromTo(innerEls,
      { y: 8, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.3, stagger: 0.06, ease: "power2.out" },
      "-=0.25"
    )
    .to(progressEl,
      { scaleX: 0, duration: CARD_HOLD_S, ease: "none" },
      "+=0.2"
    )
    .to(wrap,
      { y: 40, opacity: 0, duration: 0.4, ease: "power2.in" }
    )
    .set(wrap, { visibility: "hidden" });
}

function _showSceneCard(data) {
  const scene = data.scene_definition;
  if (!scene || !scene.elements || !scene.elements.length) return false;

  // Clear previous content (keep progress bar)
  Array.from(ocSceneCard.children).forEach(child => {
    if (child.id !== 'ocSceneProgress' && !child.classList.contains('oc-progress')) {
      child.remove();
    }
  });

  const cw = scene.canvas_width  || 460;
  const ch = scene.canvas_height || 260;

  ocSceneCard.style.width  = cw + 'px';
  ocSceneCard.style.height = ch + 'px';

  const fields = data.fields || {};
  // Also expose top-level fields
  const allFields = { team_name: data.team_name, form_name: data.form_name, ...fields };

  for (const el of scene.elements) {
    const div = document.createElement('div');
    div.style.position = 'absolute';
    div.style.left   = el.x + '%';
    div.style.top    = el.y + '%';
    div.style.width  = el.width + '%';
    div.style.height = el.height + '%';
    div.style.boxSizing = 'border-box';
    div.style.overflow = 'hidden';

    const s = el.style || {};
    div.style.background    = s.background || 'transparent';
    div.style.borderRadius  = (s.border_radius || 0) + 'px';
    div.style.border        = s.border || '';
    div.style.opacity       = s.opacity ?? 1;
    if (s.backdrop_filter)  div.style.backdropFilter = s.backdrop_filter;

    const value = el.binding ? (allFields[el.binding] || '') : (el.content || '');

    if (el.type === 'text') {
      const fsPx = (s.font_size || 2) / 100 * ch;
      div.style.fontSize   = fsPx + 'px';
      div.style.fontWeight = s.font_weight || 400;
      div.style.color      = s.color || '#ffffff';
      div.style.textAlign  = s.text_align || 'left';
      div.style.display    = 'flex';
      div.style.alignItems = 'center';
      div.style.padding    = '0 4px';
      div.style.lineHeight = '1.3';
      div.style.whiteSpace = 'nowrap';
      div.textContent = value;
    } else if (el.type === 'image' && value) {
      const img = document.createElement('img');
      img.src = value;
      img.style.cssText = `width:100%;height:100%;display:block;object-fit:${s.object_fit||'cover'};border-radius:${s.border_radius||0}px`;
      div.appendChild(img);
    }

    ocSceneCard.insertBefore(div, ocSceneCard.querySelector('.oc-progress'));
  }

  return true;
}

function showOverlayCard(data) {
  const ageS = Date.now() / 1000 - (data.ts || 0);
  if (ageS > 30) return;

  // Try scene renderer first
  if (data.scene_definition && _showSceneCard(data)) {
    _animateCard(ocSceneCard, ocSceneProgress, [ocSceneCard]);
    return;
  }

  const layout = data.layout || "stat";

  if (layout === "profile") {
    _showProfileCard(data);
  } else if (layout === "image") {
    _showImageCard(data);
  } else {
    _showStatCard(data);
  }
}

function _showStatCard(data) {
  ocBadge.textContent    = data.form_name || "Form Response";
  ocTeam.textContent     = data.team_name || "";
  ocQuestion.textContent = data.question  || "";
  ocAnswer.textContent   = data.answer    || "";
  _animateCard(ocStatCard, ocProgress, [ocBadge, ocTeam, ocQuestion, ocAnswer]);
}

function _showProfileCard(data) {
  const f = data.fields || {};
  ocProfileBadge.textContent = data.form_name || "Profile";
  ocProfileTeam.textContent  = data.team_name || "";
  ocProfileName.textContent  = f.name || "";
  ocProfileBio.textContent   = f.bio  || "";

  // Photo
  if (f.photo) {
    ocProfilePhoto.src = f.photo;
    ocProfilePhoto.style.display = "";
    ocProfilePhotoHolder.style.display = "none";
  } else {
    ocProfilePhoto.style.display = "none";
    ocProfilePhotoHolder.style.display = "";
  }

  // Extra stat slots: any field that isn't photo/name/bio
  const RESERVED = new Set(["photo", "name", "bio"]);
  ocProfileStats.innerHTML = Object.entries(f)
    .filter(([k]) => !RESERVED.has(k))
    .map(([, v]) => `<div class="oc-profile-stat">${v}</div>`)
    .join("");

  _animateCard(ocProfileCard, ocProfileProgress,
    [ocProfileBadge, ocProfileTeam, ocProfileName, ocProfileBio, ocProfileStats]);
}

function _showImageCard(data) {
  const f = data.fields || {};
  const imgUrl = f.photo || data.image_url || "";
  ocImagePhoto.src         = imgUrl;
  ocImageBadge.textContent = data.form_name || "Photo";
  ocImageCaption.textContent = f.caption || data.answer || data.team_name || "";
  _animateCard(ocImageCard, ocImageProgress, [ocImageBadge, ocImageCaption]);
}

// --- reaction burst ---
let ocReactionBurst;
let reactionBurstTimeline = null;

function updateReactionCounts(data) {
  if (!data || !data.counts) return;

  const counts = data.counts;
  const emojiMap = { fire: "rc-fire", clap: "rc-clap", wow: "rc-wow", tractor: "rc-tractor" };
  Object.entries(emojiMap).forEach(([emoji, id]) => {
    const el = document.getElementById(id);
    if (el && counts[emoji] !== undefined) {
      el.textContent = counts[emoji];
    }
  });

  if (!ocReactionBurst) return;
  // Only burst when the producer has enabled reactions.
  if (!reactionsEnabled) {
    if (reactionBurstTimeline) reactionBurstTimeline.kill();
    gsap.set(ocReactionBurst, { opacity: 0 });
    return;
  }
  if (reactionBurstTimeline) reactionBurstTimeline.kill();
  reactionBurstTimeline = gsap.timeline()
    .set(ocReactionBurst, { opacity: 0 })
    .to(ocReactionBurst, { opacity: 1, duration: 0.4, ease: "power2.out" })
    .to(ocReactionBurst, { opacity: 0, duration: 0.5, ease: "power2.in" }, "+=4");
}

// --- poll card ---
let ocPollCard, ocPollQuestion, ocPollOptions;
let pollCardTimeline = null;

function updatePollCard(data) {
  if (!ocPollCard) return;

  // Suppress entirely when the producer hasn't enabled the poll card.
  if (!pollEnabled) {
    if (pollCardTimeline) pollCardTimeline.kill();
    gsap.set(ocPollCard, { opacity: 0, visibility: "hidden" });
    return;
  }

  if (data.status === "closed") {
    if (pollCardTimeline) pollCardTimeline.kill();
    gsap.to(ocPollCard, {
      opacity: 0,
      y: 20,
      duration: 0.4,
      ease: "power2.in",
      onComplete: () => gsap.set(ocPollCard, { visibility: "hidden" }),
    });
    return;
  }

  if (!data.question || !data.options) return;

  ocPollQuestion.textContent = data.question;
  ocPollOptions.innerHTML = data.options.map(opt => `
    <div class="poll-option-row">
      <div class="poll-option-label">
        <span>${opt.text}</span>
        <span>${opt.votes} (${opt.pct}%)</span>
      </div>
      <div class="poll-bar-track">
        <div class="poll-bar-fill" style="width:${opt.pct}%"></div>
      </div>
    </div>
  `).join("");

  if (pollCardTimeline) pollCardTimeline.kill();
  pollCardTimeline = gsap.timeline()
    .set(ocPollCard, { visibility: "visible" })
    .fromTo(ocPollCard,
      { opacity: 0, y: 20 },
      { opacity: 1, y: 0, duration: 0.5, ease: "back.out(1.5)" }
    );
}

// --- tractor card ---
const ocTractorCard       = document.getElementById("ocTractorCard");
const tcPhoto             = document.getElementById("tcPhoto");
const tcPhotoPlaceholder  = document.getElementById("tcPhotoPlaceholder");
const tcName              = document.getElementById("tcName");
const tcSub               = document.getElementById("tcSub");
const tcBio               = document.getElementById("tcBio");

let tractorEnabled  = false;
let activeTractorId = null;
let latestInfo      = null;

// Static (non-animated) data cards: shown/hidden by toggling `card-off`,
// keyed by their toggle name. Every card is OFF unless explicitly enabled.
const STATIC_CARD_IDS = {
  pull_hud:   "pullHud",
  pull_chart: "pullChartCard",
  load_toad:  "loadToadCard",
  dur_hud:    "durHud",
  dur_chart:  "durChartCard",
  man_hud:    "manHud",
};

// Enable flags for the animated / event-driven common cards.
let reactionsEnabled = false;
let pollEnabled      = false;

function applyOverlayToggle(state) {
  state = state || {};

  // Static data cards — OFF unless the producer turned them on.
  for (const [key, id] of Object.entries(STATIC_CARD_IDS)) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("card-off", state[key] !== true);
  }

  // Animated common cards keep their own .show mechanism via refreshers.
  tractorEnabled = state.tractor_card === true;
  refreshTractorCard();
  upNextEnabled = state.up_next === true;
  refreshUpNextCard();

  // Reaction burst — hide immediately when disabled.
  reactionsEnabled = state.reactions === true;
  if (!reactionsEnabled && ocReactionBurst) {
    if (reactionBurstTimeline) reactionBurstTimeline.kill();
    gsap.set(ocReactionBurst, { opacity: 0 });
  }

  // Poll card — hide immediately when disabled.
  pollEnabled = state.poll === true;
  if (!pollEnabled && ocPollCard) {
    if (pollCardTimeline) pollCardTimeline.kill();
    gsap.set(ocPollCard, { opacity: 0, visibility: "hidden" });
  }
}

// --- up next card ---
const ocUpNextCard = document.getElementById("ocUpNextCard");
const unList       = document.getElementById("unList");
let upNextEnabled = false;
let latestSchedule = null;

function handlePullSchedule(payload) {
  latestSchedule = payload;
  refreshUpNextCard();
}

function _fmtEta(epoch) {
  if (!epoch) return "—";
  const d = new Date(epoch * 1000);
  let h = d.getHours();
  const m = d.getMinutes().toString().padStart(2, "0");
  const am = h < 12 ? "AM" : "PM";
  h = h % 12 || 12;
  return `${h}:${m} ${am}`;
}

function refreshUpNextCard() {
  if (!ocUpNextCard) return;
  if (!upNextEnabled) {
    ocUpNextCard.classList.remove("show");
    return;
  }

  const pulls = (latestSchedule && Array.isArray(latestSchedule.pulls))
    ? latestSchedule.pulls : [];

  const upcoming = pulls
    .filter(p => p.state === "SCHEDULED")
    .sort((a, b) => (a.run_order ?? 0) - (b.run_order ?? 0))
    .slice(0, 5);

  if (!upcoming.length) {
    unList.innerHTML = '<div class="un-empty">No upcoming pulls</div>';
  } else {
    unList.innerHTML = upcoming.map(p => `
      <div class="un-row">
        <div class="un-order">#${p.run_order ?? "?"}</div>
        <div class="un-team">${escapeHtml(p.team_name || `Team ${p.team_number || p.team_id || ""}`)}</div>
        <div class="un-time">${_fmtEta(p.expected_start_time)}</div>
      </div>
    `).join("");
  }

  ocUpNextCard.classList.add("show");
}

function handleTractorInfo(info) {
  latestInfo = info;
  refreshTractorCard();
}

function refreshTractorCard() {
  if (!ocTractorCard) return;
  const tractorId = latestInfo?.tractor_id ?? null;

  if (!tractorEnabled || !tractorId) {
    ocTractorCard.classList.remove("show");
    activeTractorId = null;
    return;
  }

  if (tractorId === activeTractorId) {
    ocTractorCard.classList.add("show");
    return;
  }
  activeTractorId = tractorId;
  loadTractor(tractorId, latestInfo);
}

async function loadTractor(tractorId, infoFallback) {
  try {
    const res = await fetch(`/api/v1/tractors/${tractorId}/`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const detail = await res.json();
    if (tractorId !== activeTractorId || !tractorEnabled) return;
    renderTractor(detail, infoFallback);
  } catch (err) {
    console.warn("Failed to load tractor", tractorId, err);
    if (tractorId !== activeTractorId || !tractorEnabled) return;
    tcName.textContent = infoFallback?.tractor_name || "Unnamed Tractor";
    tcSub.innerHTML = "";
    tcBio.textContent = "";
    tcPhoto.style.display = "none";
    tcPhotoPlaceholder.style.display = "";
    ocTractorCard.classList.add("show");
  }
}

function renderTractor(detail, infoFallback) {
  const info = detail.info || {};
  const displayName = info.nickname || detail.tractor_name ||
                      infoFallback?.tractor_name || "Unnamed Tractor";
  tcName.textContent = displayName;

  const subParts = [];
  if (detail.tractor_name && info.nickname) subParts.push(detail.tractor_name);
  if (detail.year) subParts.push(detail.year);
  if (detail.original_team && detail.original_team.team_name) {
    subParts.push(`Built by ${detail.original_team.team_name}`);
  }
  tcSub.innerHTML = subParts
    .map((p) => `<span>${escapeHtml(p)}</span>`)
    .join('<span class="tc-dot">•</span>');

  tcBio.textContent = info.bio || "";

  const photoUrl = detail.primary_photo_url || "";
  if (photoUrl) {
    tcPhoto.src = photoUrl;
    tcPhoto.style.display = "";
    tcPhotoPlaceholder.style.display = "none";
  } else {
    tcPhoto.style.display = "none";
    tcPhotoPlaceholder.style.display = "";
  }

  ocTractorCard.classList.add("show");
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// =====================================================================
// Durability scene
// =====================================================================
const durFields = {};
const durStatusPill = document.getElementById("durStatusPill");
const durStatusText = document.getElementById("durStatusText");
let durChart = null;
let durRunId = null;
const DUR_MAX_POINTS = 10000;

function bindDurFields() {
  document.querySelectorAll("[data-dur]").forEach((el) => {
    durFields[el.dataset.dur] = el;
  });
}

function setDurField(key, value, digits = null) {
  const el = durFields[key];
  if (!el) return;
  el.textContent =
    typeof value === "number" && digits !== null ? value.toFixed(digits) : String(value);
}

function setDurStatus(mode, text) {
  if (!durStatusPill) return;
  durStatusPill.classList.remove("status-live", "status-stale");
  if (mode === "live") durStatusPill.classList.add("status-live");
  if (mode === "stale") durStatusPill.classList.add("status-stale");
  if (durStatusText) durStatusText.textContent = text;
}

function initDurChart() {
  const ctx = document.getElementById("durChart");
  if (!ctx) return;
  durChart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        { label: "Speed (mph)", data: [], yAxisID: "ySpeed",
          borderColor: "rgb(96,165,250)", showLine: true, pointRadius: 0, borderWidth: 2 },
        { label: "Pressure (psi)", data: [], yAxisID: "yPressure",
          borderColor: "rgb(52,211,153)", showLine: true, pointRadius: 0, borderWidth: 2 },
        { label: "Power (hp)", data: [], yAxisID: "yPower",
          borderColor: "rgb(251,191,36)", showLine: true, pointRadius: 0, borderWidth: 2 },
      ],
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      plugins: {
        legend: { labels: { color: "rgba(226,232,240,0.9)", boxWidth: 10, boxHeight: 10 } },
        tooltip: { enabled: false },
      },
      scales: {
        x: { type: "linear", min: 0,
          title: { text: "Elapsed Time (s)", display: true, color: "rgba(148,163,184,0.95)" },
          ticks: { color: "rgba(148,163,184,0.95)" }, grid: { color: "rgba(148,163,184,0.12)" } },
        ySpeed: { position: "left", min: 0,
          title: { text: "Speed (mph)", display: true, color: "rgb(96,165,250)" },
          ticks: { color: "rgb(96,165,250)" }, grid: { color: "rgba(96,165,250,0.1)" } },
        yPressure: { position: "right", min: 0,
          title: { text: "Pressure (psi)", display: true, color: "rgb(52,211,153)" },
          ticks: { color: "rgb(52,211,153)" }, grid: { drawOnChartArea: false } },
        yPower: { position: "right", min: 0,
          title: { text: "Power (hp)", display: true, color: "rgb(251,191,36)" },
          ticks: { color: "rgb(251,191,36)" }, grid: { drawOnChartArea: false } },
      },
    },
  });
}

function clearDurChart() {
  if (!durChart) return;
  durChart.data.datasets.forEach((ds) => (ds.data.length = 0));
  durChart.update("none");
}

function pushDurPoint(t, speed, pressure, power) {
  if (!durChart) return;
  durChart.data.datasets[0].data.push({ x: t, y: speed });
  durChart.data.datasets[1].data.push({ x: t, y: pressure });
  durChart.data.datasets[2].data.push({ x: t, y: power });
  if (durChart.data.datasets[0].data.length > DUR_MAX_POINTS) {
    durChart.data.datasets.forEach((ds) => ds.data.shift());
  }
  durChart.update("none");
}

function handleDurStatus(s) {
  if (s.run_id !== undefined && s.run_id !== durRunId) {
    durRunId = s.run_id;
    clearDurChart();
  }
  if (s.status !== undefined) {
    setDurStatus(s.status === 1 ? "live" : "neutral", s.status === 1 ? "RUNNING" : "Standing by");
  }
  if (s.current_lap !== undefined) setDurField("current_lap", s.current_lap);
  if (s.total_laps !== undefined) setDurField("total_laps", s.total_laps);
  if (s.elapsed_time !== undefined) setDurField("elapsed_time", Number(s.elapsed_time), 1);
}

function handleDurInfo(info) {
  setDurField("team_name", info.team_name || "—");
  setDurField("team_number", info.team_number ? "#" + info.team_number : "");
  setDurField("tractor_name", info.tractor_name || "—");
}

function handleDurData(data) {
  const speed = Number(data.speed);
  const pressure = Number(data.pressure);
  const power = Number(data.power);
  const t = Number(data.timestamp);
  if (![speed, pressure, power, t].every(Number.isFinite)) return;
  setDurField("speed", speed, 1);
  setDurField("pressure", pressure, 1);
  setDurField("power", power, 1);
  pushDurPoint(t, speed, pressure, power);
}

function fmtClock(seconds) {
  const s = Math.max(0, Math.round(Number(seconds)));
  const m = Math.floor(s / 60);
  return m + ":" + String(s % 60).padStart(2, "0");
}

function handleDurClock(clock) {
  if (clock.lap_count !== undefined && Number.isFinite(Number(clock.lap_count))) {
    setDurField("current_lap", Number(clock.lap_count));
  }
  if (clock.time_remaining !== undefined && Number.isFinite(Number(clock.time_remaining))) {
    setDurField("time_remaining", fmtClock(clock.time_remaining));
  }
}

// =====================================================================
// Maneuverability scene (HUD stub — man:info / man:status only, no chart)
// =====================================================================
const manFields = {};
const manStatusPill = document.getElementById("manStatusPill");
const manStatusText = document.getElementById("manStatusText");

function bindManFields() {
  document.querySelectorAll("[data-man]").forEach((el) => {
    manFields[el.dataset.man] = el;
  });
}

function setManField(key, value) {
  const el = manFields[key];
  if (el) el.textContent = String(value);
}

function setManStatus(mode, text) {
  if (!manStatusPill) return;
  manStatusPill.classList.remove("status-live", "status-stale");
  if (mode === "live") manStatusPill.classList.add("status-live");
  if (mode === "stale") manStatusPill.classList.add("status-stale");
  if (manStatusText) manStatusText.textContent = text;
}

function handleManStatus(s) {
  if (s.status !== undefined) {
    setManStatus(s.status === 1 ? "live" : "neutral", s.status === 1 ? "RUNNING" : "Standing by");
  }
}

function handleManInfo(info) {
  setManField("team_name", info.team_name || "—");
  setManField("team_number", info.team_number ? "#" + info.team_number : "");
  setManField("tractor_name", info.tractor_name || "—");
  if (info.event !== undefined && info.event !== null) setManField("event", info.event);
}

// --- boot ---
document.addEventListener("DOMContentLoaded", () => {
  ocReactionBurst = document.getElementById("ocReactionBurst");
  ocPollCard      = document.getElementById("ocPollCard");
  ocPollQuestion  = document.getElementById("ocPollQuestion");
  ocPollOptions   = document.getElementById("ocPollOptions");
  initChart();
  bindDurFields();
  initDurChart();
  bindManFields();
  startSSE();
  startStaleMonitor();
});
