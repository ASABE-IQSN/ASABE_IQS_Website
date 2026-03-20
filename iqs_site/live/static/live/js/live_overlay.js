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
      setField("pull_id", pull_id ?? "—");
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
  });

  es.addEventListener("data", (e) => {
    const data = JSON.parse(e.data);

    const speed = Number(data.speed);
    const force = Number(data.force);
    const distance = Number(data.distance);

    if (![speed, force, distance].every(Number.isFinite)) return;

    lastDataMs = Date.now();
    if (pull_active) setStatus("live", "LIVE");

    // update page fields
    setField("speed", speed, 1);
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

// --- boot ---
document.addEventListener("DOMContentLoaded", () => {
  ocReactionBurst = document.getElementById("ocReactionBurst");
  ocPollCard      = document.getElementById("ocPollCard");
  ocPollQuestion  = document.getElementById("ocPollQuestion");
  ocPollOptions   = document.getElementById("ocPollOptions");
  initChart();
  startSSE();
  startStaleMonitor();
});
