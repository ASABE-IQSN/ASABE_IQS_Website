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

  // If you want to avoid hardcoding, you can inject this from Django as data-attr
  const STREAM_URL = "https://api.internationalquarterscale.com/api/stream";
  const es = new EventSource(STREAM_URL);

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

  es.onerror = (err) => {
    // Browser auto-reconnects; this fires frequently during reconnect
    console.warn("SSE error", err);
    setStatus("stale", "Reconnecting…");
  };
}

// --- boot ---
document.addEventListener("DOMContentLoaded", () => {
  initChart();
  startSSE();
  startStaleMonitor();
});
