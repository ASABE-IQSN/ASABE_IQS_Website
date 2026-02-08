// --- Field binding system ---
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

// --- Chart initialization ---
let chart = null;
const MAX_POINTS = 10000;

function initChart() {
  const ctx = document.getElementById("liveChart");
  if (!ctx) return;

  chart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Speed (mph)",
          data: [],
          yAxisID: "ySpeed",
          borderColor: "rgb(96, 165, 250)",
          backgroundColor: "rgba(96, 165, 250, 0.5)",
          showLine: true,
          pointRadius: 2
        },
        {
          label: "Pressure (psi)",
          data: [],
          yAxisID: "yPressure",
          borderColor: "rgb(52, 211, 153)",
          backgroundColor: "rgba(52, 211, 153, 0.5)",
          showLine: true,
          pointRadius: 2
        },
        {
          label: "Power (hp)",
          data: [],
          yAxisID: "yPower",
          borderColor: "rgb(251, 191, 36)",
          backgroundColor: "rgba(251, 191, 36, 0.5)",
          showLine: true,
          pointRadius: 2
        }
      ]
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: true,
      scales: {
        x: {
          type: "linear",
          title: { text: "Elapsed Time (seconds)", display: true },
          ticks: { color: "rgba(255, 255, 255, 0.7)" },
          grid: { color: "rgba(255, 255, 255, 0.1)" }
        },
        ySpeed: {
          position: "left",
          title: { text: "Speed (mph)", display: true },
          ticks: { color: "rgb(96, 165, 250)" },
          grid: { color: "rgba(96, 165, 250, 0.1)" }
        },
        yPressure: {
          position: "right",
          title: { text: "Pressure (psi)", display: true },
          ticks: { color: "rgb(52, 211, 153)" },
          grid: { drawOnChartArea: false }
        },
        yPower: {
          position: "right",
          title: { text: "Power (hp)", display: true },
          ticks: { color: "rgb(251, 191, 36)" },
          grid: { drawOnChartArea: false }
        }
      },
      plugins: {
        legend: {
          labels: { color: "rgba(255, 255, 255, 0.8)" }
        }
      }
    }
  });
}

// --- Chart point management ---
function pushPoint(timestamp, speed, pressure, power) {
  if (!chart) return;

  chart.data.datasets[0].data.push({ x: timestamp, y: speed });
  chart.data.datasets[1].data.push({ x: timestamp, y: pressure });
  chart.data.datasets[2].data.push({ x: timestamp, y: power });

  // Circular buffer - remove oldest if over limit
  if (chart.data.datasets[0].data.length > MAX_POINTS) {
    chart.data.datasets.forEach((ds) => ds.data.shift());
  }

  chart.update("none");
}

// --- Up next rendering ---
const upNextListEl = document.getElementById("upNextList");
const upNextEmptyEl = document.getElementById("upNextEmpty");
const upNextCountEl = document.getElementById("upNextCount");

function renderUpNext(upNextArray) {
  if (!upNextListEl) return;

  const teams = Array.isArray(upNextArray) ? upNextArray : [];
  upNextListEl.innerHTML = "";

  if (teams.length === 0) {
    if (upNextEmptyEl) {
      upNextEmptyEl.style.display = "";
      upNextListEl.appendChild(upNextEmptyEl);
    } else {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No teams queued.";
      upNextListEl.appendChild(empty);
    }
    if (upNextCountEl) upNextCountEl.textContent = "0";
    return;
  }

  if (upNextEmptyEl) upNextEmptyEl.style.display = "none";
  if (upNextCountEl) upNextCountEl.textContent = String(teams.length);

  teams.forEach((team, idx) => {
    const teamName = team?.team_name ?? "Unknown";

    const item = document.createElement("div");
    item.className = "up-next-item";

    const position = document.createElement("div");
    position.className = "up-next-position";
    position.textContent = String(idx + 1);

    const name = document.createElement("div");
    name.className = "up-next-name";
    name.textContent = teamName;

    item.appendChild(position);
    item.appendChild(name);
    upNextListEl.appendChild(item);
  });
}

// --- Live state ---
let run_id = null;

// --- SSE connection and event listeners ---
function startSSE() {
  const es = new EventSource(window.IQS.apiUrl + "/api/stream");

  // Listen for dur_status event
  es.addEventListener("dur_status", (e) => {
    const s = JSON.parse(e.data);

    // Detect run change
    if (s.run_id !== run_id) {
      console.log("Run changed:", s.run_id);
      run_id = s.run_id;

      // Clear chart on new run
      if (chart) {
        chart.data.datasets.forEach((ds) => (ds.data.length = 0));
        chart.update("none");
      }
    }

    // Update status fields
    if (s.status !== undefined) {
      setField("status", s.status === 1 ? "Running" : "Stopped");
    }
    if (s.current_lap !== undefined) {
      setField("current_lap", s.current_lap);
    }
    if (s.total_laps !== undefined) {
      setField("total_laps", s.total_laps);
    }
    if (s.elapsed_time !== undefined) {
      setField("elapsed_time", s.elapsed_time, 1);
    }
  });

  // Listen for dur_info event
  es.addEventListener("dur_info", (e) => {
    const info = JSON.parse(e.data);

    setField("team_name", info.team_name || "Unknown");
    setField("team_number", info.team_number || "-");
    setField("tractor_name", info.tractor_name || "None");
    setField("event", info.event || "-");

    renderUpNext(info.up_next);
  });

  // Listen for dur_data event (continuous stream)
  es.addEventListener("dur_data", (e) => {
    const data = JSON.parse(e.data);

    const speed = Number(data.speed);
    const pressure = Number(data.pressure);
    const power = Number(data.power);
    const timestamp = Number(data.timestamp);

    if (![speed, pressure, power, timestamp].every(Number.isFinite)) {
      console.warn("BAD NUMBERS — not plotting", data);
      return;
    }

    // Update current value fields
    setField("speed", speed, 1);
    setField("pressure", pressure, 1);
    setField("power", power, 1);

    // Add to chart
    pushPoint(timestamp, speed, pressure, power);
  });

  es.onerror = (err) => {
    console.error("SSE error", err);
    // Browser auto-reconnects
  };
}

// --- Initialization ---
document.addEventListener("DOMContentLoaded", () => {
  initChart();
  startSSE();
});
