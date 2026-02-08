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

// --- up next render ---
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

// --- live state ---
let run_id = null;

// --- SSE hookup ---
function startSSE() {
  const es = new EventSource(window.IQS.apiUrl + "/api/stream");

  // Listen for man_status event
  es.addEventListener("man_status", (e) => {
    const s = JSON.parse(e.data);

    // Detect run change
    if (s.run_id !== run_id) {
      console.log("Run changed:", s.run_id);
      run_id = s.run_id;
    }

    // Update status field if present
    if (s.status !== undefined) {
      setField("status", s.status);
    }
  });

  // Listen for man_info event
  es.addEventListener("man_info", (e) => {
    const info = JSON.parse(e.data);

    setField("team_name", info.team_name || "Unknown");
    setField("team_number", info.team_number || "-");
    setField("tractor_name", info.tractor_name || "None");
    setField("event", info.event || "-");

    renderUpNext(info.up_next);
  });

  es.onerror = (err) => {
    console.error("SSE error", err);
    // Browser auto-reconnects
  };
}

// --- boot ---
document.addEventListener("DOMContentLoaded", () => {
  startSSE();
});
