(function () {
  const apiBase = (window.IQS && window.IQS.apiUrl) || "";

  const $ = (id) => document.getElementById(id);
  const escapeHtml = (s) =>
    String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  function stateBadge(state) {
    if (state === "RUNNING") return '<span class="badge badge-green">Running</span>';
    if (state === "COMPLETED") return '<span class="badge badge-gray">Completed</span>';
    const label = state ? state[0] + state.slice(1).toLowerCase() : "";
    return `<span class="badge badge-yellow">${escapeHtml(label)}</span>`;
  }

  function percentBadge(p) {
    if (p === 100) return '<span class="badge badge-green">100%</span>';
    if (p >= 50) return `<span class="badge badge-yellow">${p}%</span>`;
    return `<span class="badge badge-red">${p}%</span>`;
  }

  function emptyRow(colspan, label) {
    return `<tr class="empty-row"><td colspan="${colspan}">${label}</td></tr>`;
  }

  function setLastUpdated() {
    const el = $("last-updated-text");
    if (!el) return;
    const d = new Date();
    el.textContent = d.toTimeString().slice(0, 8);
  }

  function renderLeaderboard(data) {
    const tbody = $("pulls-tbody");
    if (tbody) {
      if (!data.leaderboard || data.leaderboard.length === 0) {
        tbody.innerHTML = emptyRow(5, "No completed pulls yet.");
      } else {
        tbody.innerHTML = data.leaderboard
          .map(
            (r, i) =>
              `<tr><td>${i + 1}</td><td>${escapeHtml(r.team_name)}</td><td>${escapeHtml(
                r.hook_name
              )}</td><td>${r.distance == null ? "" : r.distance}</td><td>${escapeHtml(
                r.team_class
              )}</td></tr>`
          )
          .join("");
      }
    }
    const badge = $("live-badge");
    const subtitle = $("pulls-subtitle");
    if (data.current_pull) {
      if (badge) badge.style.display = "";
      if (subtitle)
        subtitle.textContent =
          "Now: " + data.current_pull.team_name + " on " + data.current_pull.hook_name;
    } else {
      if (badge) badge.style.display = "none";
      if (subtitle) subtitle.textContent = "Top by distance";
    }
  }

  function renderRuns(data) {
    const m = $("maneuver-tbody");
    if (m) {
      if (!data.maneuverability || data.maneuverability.length === 0) {
        m.innerHTML = emptyRow(3, "No maneuverability runs yet.");
      } else {
        m.innerHTML = data.maneuverability
          .map(
            (r) =>
              `<tr${r.state === "RUNNING" ? ' class="highlight"' : ""}><td>${
                r.run_order
              }</td><td>${escapeHtml(r.team_name)}</td><td>${stateBadge(r.state)}</td></tr>`
          )
          .join("");
      }
    }
    const d = $("durability-tbody");
    if (d) {
      if (!data.durability || data.durability.length === 0) {
        d.innerHTML = emptyRow(4, "No durability runs yet.");
      } else {
        d.innerHTML = data.durability
          .map(
            (r) =>
              `<tr${r.state === "RUNNING" ? ' class="highlight"' : ""}><td>${
                r.run_order
              }</td><td>${escapeHtml(r.team_name)}</td><td>${
                r.total_laps == null ? "–" : r.total_laps
              }</td><td>${stateBadge(r.state)}</td></tr>`
          )
          .join("");
      }
    }
  }

  function renderTech(data) {
    const t = $("tech-tbody");
    if (!t) return;
    if (!data.tech_status || data.tech_status.length === 0) {
      t.innerHTML = emptyRow(3, "No tech inspection data yet.");
      return;
    }
    t.innerHTML = data.tech_status
      .map(
        (r) =>
          `<tr><td>${escapeHtml(r.team_name)}</td><td>${escapeHtml(
            r.team_number
          )}</td><td>${percentBadge(r.percent)}</td></tr>`
      )
      .join("");
  }

  function makeDebouncedFetcher(url, render) {
    let timer = null;
    return function () {
      if (timer) clearTimeout(timer);
      timer = setTimeout(async () => {
        timer = null;
        try {
          const res = await fetch(url, { credentials: "same-origin" });
          if (!res.ok) return;
          const data = await res.json();
          render(data);
          setLastUpdated();
        } catch (e) {
          console.warn("live landing fetch failed:", e);
        }
      }, 400);
    };
  }

  const refreshLeaderboard = makeDebouncedFetcher("/live/api/leaderboard.json", renderLeaderboard);
  const refreshRuns = makeDebouncedFetcher("/live/api/runs.json", renderRuns);
  const refreshTech = makeDebouncedFetcher("/live/api/techin.json", renderTech);

  document.addEventListener("DOMContentLoaded", () => {
    if (!apiBase) return;
    const es = new EventSource(apiBase + "/api/stream");

    es.addEventListener("status", refreshLeaderboard);
    es.addEventListener("info", refreshLeaderboard);

    es.addEventListener("man_status", refreshRuns);
    es.addEventListener("dur_status", refreshRuns);

    es.onerror = (err) => {
      console.warn("live landing SSE error:", err);
    };

    // Periodic light refresh for tech-in (no SSE channel for it).
    setInterval(refreshTech, 60000);
  });
})();
