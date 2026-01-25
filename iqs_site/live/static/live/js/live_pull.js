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

// --- chart setup ---
const MAX_POINTS = 10000;
const ctx = document.getElementById("liveChart");

let chart = null;

function initChart() {
  if (!ctx) return;

  chart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Speed (ft/s)",
          data: [],
          yAxisID: "ySpeed",
        },
        {
          label: "Force (lbf)",
          data: [],
          yAxisID: "yForce",
        },
      ],
    },
    options: {
      animation: false,
      responsive: true,
      scales: {
        x: { type: "linear", title: { text: "Distance (ft)", display: true } },
        ySpeed: {
          position: "left",
          title: { text: "Speed (ft/s)", display: true },
        },
        yForce: {
          position: "right",
          title: { text: "Force (lbf)", display: true },
          grid: { drawOnChartArea: false },
        },
      },
    },
  });
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

// --- SSE hookup ---
function startSSE() {
  const es = new EventSource(window.IQS.apiUrl+"/api/stream");

  es.addEventListener("status", (e) => {
    const s = JSON.parse(e.data);

    // detect pull changehttps://api.internationalquarterscale.com
    if (s.pull_id !== pull_id) {
      console.log("Pull changed:", s.pull_id);
      pull_id = s.pull_id;

      // clear chart on new pull
      if (chart) {
        chart.data.datasets.forEach((ds) => (ds.data.length = 0));
        chart.update("none");
      }
    }

    pull_active = s.status === 1;
  });

  es.addEventListener("info", (e) => {
    const info = JSON.parse(e.data);

    setField("hook_name", info.hook_name);
    setField("team_name", info.team_name);
    setField("team_number", info.team_number);
  });

  es.addEventListener("data", (e) => {
    // if (!pull_active) return;

    const data = JSON.parse(e.data);

    const speed = Number(data.speed);
    const force = Number(data.force);
    const distance = Number(data.distance);

    if (![speed, force, distance].every(Number.isFinite)) {
      console.warn("BAD NUMBERS — not plotting", data);
      return;
    }

    // update page fields
    setField("speed", speed, 1);
    setField("force", force, 0);
    setField("distance", distance, 1);

    pushPoint(distance, speed, force);
  });

  es.onerror = (err) => {
    console.error("SSE error", err);
    // Browser auto-reconnects; no manual retry needed
  };
}

// --- boot ---
document.addEventListener("DOMContentLoaded", () => {
  initChart();
  startSSE();
});
