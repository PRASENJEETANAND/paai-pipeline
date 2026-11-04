const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

let jobs = [];
let selectedId = null;
let settings = null;
let pollTimer = null;

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

function fmtFrames(j) {
  const f = j.frames || {};
  const step = f.step && f.step !== 1 ? `x${f.step}` : "";
  return `${f.start ?? "?"}-${f.end ?? "?"}${step}`;
}

function badge(status) {
  return `<span class="badge ${status || ""}">${status || "?"}</span>`;
}

function filtered() {
  const show = {
    running: $("#fltRunning").checked,
    queued: $("#fltQueued").checked,
    done: $("#fltDone").checked,
    failed: $("#fltFailed").checked,
    cancelled: $("#fltFailed").checked,
    paused: $("#fltQueued").checked,
  };
  const q = ($("#search").value || "").toLowerCase();
  return jobs.filter((j) => {
    if (!show[j.status]) return false;
    if (!q) return true;
    const hay = [j.name, j.target, j.user, j.app, j.id].join(" ").toLowerCase();
    return hay.includes(q);
  });
}

function renderJobs() {
  const body = $("#jobsBody");
  const rows = filtered();
  body.innerHTML = rows.map((j) => {
    const res = j.resources || {};
    const gpu = res.gpu_index === null || res.gpu_index === undefined || res.gpu_index === ""
      ? "—" : `GPU ${res.gpu_index}`;
    const pct = (j.progress && j.progress.percent) || 0;
    const sel = j.id === selectedId ? "sel" : "";
    return `<tr class="${sel}" data-id="${j.id}">
      <td>${badge(j.status)}</td>
      <td><span class="app-tag">${j.app}</span></td>
      <td title="${j.name} / ${j.target}"><b>${esc(j.name)}</b><div class="muted">${esc(j.target || "")}</div>${j.wait_reason ? `<div class="wait">${esc(j.wait_reason)}</div>` : ""}</td>
      <td>${fmtFrames(j)}</td>
      <td><div style="display:flex;align-items:center"><div class="bar"><i style="width:${pct}%"></i></div><span class="pct">${pct}%</span></div></td>
      <td>${res.cpu_cores || 1}c / ${gpu}</td>
      <td>${j.priority ?? 50}</td>
      <td>${esc(j.user || "")}</td>
      <td class="actions" data-actions="${j.id}">
        ${actionsHtml(j)}
      </td>
    </tr>`;
  }).join("") || `<tr><td colspan="9" class="muted">No jobs match filters.</td></tr>`;

  body.querySelectorAll("tr[data-id]").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target.closest("[data-actions] button")) return;
      selectJob(tr.dataset.id);
    });
  });
  body.querySelectorAll("[data-actions] button").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const id = btn.closest("[data-actions]").dataset.actions;
      const act = btn.dataset.act;
      await doAction(id, act, btn);
    });
  });
}

function actionsHtml(j) {
  const a = [];
  const st = j.status;
  if (["queued", "waiting", "ready", "paused", "failed", "killed", "cancelled", "done"].includes(st) && st !== "running") {
    if (st !== "paused") a.push(btn("Start", "start", "tiny primary"));
  }
  if (st === "running") a.push(btn("Pause", "pause"));
  if (st === "paused") a.push(btn("Resume", "resume"));
  if (["queued", "waiting", "ready"].includes(st)) a.push(btn("Hold", "pause"));
  if (["running", "paused", "queued", "waiting", "ready"].includes(st)) a.push(btn("Kill", "kill", "danger"));
  if (["failed", "cancelled", "killed", "done", "paused"].includes(st)) a.push(btn("Retry", "retry"));
  a.push(btn("Log", "log"));
  a.push(btn("🗑", "delete", "ghost"));
  return a.join("");
}
function btn(label, act, cls = "tiny") {
  return `<button class="btn ${cls} tiny" data-act="${act}">${label}</button>`;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function doAction(id, act) {
  if (act === "log") { selectJob(id); return; }
  if (act === "delete") {
    if (!confirm("Delete this job?")) return;
    await api(`/api/jobs/${id}/delete`, { method: "POST", body: "{}" });
    if (selectedId === id) selectedId = null;
    return refresh();
  }
  await api(`/api/jobs/${id}/${act}`, { method: "POST", body: "{}" });
  return refresh();
}

async function selectJob(id) {
  selectedId = id;
  renderJobs();
  const j = jobs.find((x) => x.id === id);
  $("#detailTitle").textContent = j ? `${j.name} · ${j.target || j.app}` : "Select a job";
  $("#detailMeta").textContent = j ? `${j.id} · ${j.status} · ${j.machine || ""}` : "";
  if (!j) { $("#logView").textContent = ""; return; }
  try {
    const data = await api(`/api/jobs/${id}/log?tail=300`);
    $("#logView").textContent = data.log || "(empty log)";
    $("#logView").scrollTop = $("#logView").scrollHeight;
  } catch (e) {
    $("#logView").textContent = String(e);
  }
}

async function refresh() {
  try {
    const data = await api("/api/jobs");
    jobs = data.jobs || [];
    const s = data.scheduler || {};
    const state = s.state || (s.paused ? "paused" : "running");
    const qEl = $("#qState");
    if (qEl) {
      qEl.textContent = state;
      qEl.className = "qstate " + state;
    }
    $("#schedInfo").textContent =
      `${(s.running || []).length} running · CPU ${s.reserved_cpu || 0}/${s.total_cpu || "?"} · max ${s.max_concurrent || "?"}`;
    const pauseBtn = $("#btnPauseQueue");
    pauseBtn.textContent = state === "paused" ? "Resume Queue" : "Pause Queue";
    pauseBtn.dataset.paused = state === "paused" ? "1" : "0";
    const auto = $("#chkAutoStart");
    if (auto && document.activeElement !== auto) auto.checked = !!s.auto_start;
    if (window.PAAI_FULL_NAME && $("#paaiFullName")) $("#paaiFullName").textContent = window.PAAI_FULL_NAME;
    renderJobs();
    if (selectedId) {
      // refresh log lightly
      const still = jobs.find((j) => j.id === selectedId);
      if (still && (still.status === "running" || document.hasFocus())) {
        try {
          const log = await api(`/api/jobs/${selectedId}/log?tail=300`);
          $("#logView").textContent = log.log || "";
        } catch {}
      }
    }
  } catch (e) {
    $("#schedInfo").textContent = "offline: " + e.message;
  }
}

/* ---------------- settings ---------------- */
function openSettings() {
  $("#settingsModal").classList.remove("hidden");
  drawSettingsForm(settings || {});
}
function closeSettings() { $("#settingsModal").classList.add("hidden"); }

function drawSettingsForm(s) {
  const servers = (s.comfyui_servers || []).map((x, i) =>
    `<div class="server-row" data-i="${i}">
      <input data-k="name" value="${esc(x.name || "")}" placeholder="name"/>
      <input data-k="url" value="${esc(x.url || "")}" placeholder="http://127.0.0.1:8188"/>
      <button class="btn tiny" data-test-comfy="${i}">Test</button>
      <button class="btn tiny ghost" data-del-server="${i}">✕</button>
    </div>`
  ).join("");
  const defaultHome = (window.__PAAI_RQ_META__ && window.__PAAI_RQ_META__.default_data_folder) || "";
  const docsDir = (window.__PAAI_RQ_META__ && window.__PAAI_RQ_META__.documents_dir) || "";
  $("#settingsForm").innerHTML = `
    <div class="form-section">DATA LOCATION</div>
    <div class="form-row"><label>Data folder</label><input id="s_data" value="${esc(s.data_folder || "")}" placeholder="${esc(defaultHome)}"/><span></span></div>
    <div class="help">Default: &lt;Documents&gt;/PAAI Render Queue/${docsDir ? " (Documents = " + esc(docsDir) + ")" : ""}. Shared via ~/.paai/render_queue_location.json so Nuke / ComfyUI / Blender all find the same queue. Not tied to any show.</div>
    <div class="form-row"><label></label><label style="width:auto;text-align:left"><input type="checkbox" id="s_move"/> Move existing jobs / logs / scripts into the new folder</label><span></span></div>
    <div class="form-row"><label>Port</label><input id="s_port" type="number" value="${s.port || 8790}"/><span></span></div>
    <div class="form-row"><label></label><label style="width:auto;text-align:left"><input type="checkbox" id="s_auto" ${s.auto_start ? "checked" : ""}/> Auto start queue when jobs are submitted</label><span></span></div>

    <div class="form-section">LAUNCHERS</div>
    <div class="form-row"><label>Nuke launcher</label><input id="s_nuke" value="${esc(s.nuke_launcher || "")}" placeholder="nuke or path to .exe/.bat/.sh"/>
      <button class="btn tiny" id="testNuke">Test</button></div>
    <div class="form-row"><label>Blender launcher</label><input id="s_blender" value="${esc(s.blender_launcher || "")}" placeholder="blender or full path"/>
      <button class="btn tiny" id="testBlender">Test</button></div>
    <div id="testOut" class="help"></div>

    <div class="form-section">RESOURCES</div>
    <div class="form-row"><label>Total CPU cores</label><input id="s_cores" type="number" value="${s.total_cpu_cores || 0}"/><span></span></div>
    <div class="form-row"><label>Max concurrent</label><input id="s_max" type="number" value="${s.max_concurrent_jobs || 2}"/><span></span></div>
    <div class="form-row"><label>GPUs (comma ids)</label><input id="s_gpus" value="${esc((s.gpus || []).join(", "))}" placeholder="0, 1"/><span></span></div>

    <div class="form-section">COMFYUI SERVERS</div>
    <div id="serverList">${servers || "<div class='muted'>No servers</div>"}</div>
    <button class="btn tiny" id="addServer">+ Server</button>
  `;
  $("#testNuke").onclick = () => testLauncher("nuke", $("#s_nuke").value);
  $("#testBlender").onclick = () => testLauncher("blender", $("#s_blender").value);
  $("#addServer").onclick = () => {
    s.comfyui_servers = s.comfyui_servers || [];
    s.comfyui_servers.push({ name: "server", url: "http://127.0.0.1:8188" });
    drawSettingsForm(readSettingsForm(s));
  };
  $$("[data-del-server]").forEach((b) => b.onclick = () => {
    const i = +b.dataset.delServer;
    const cur = readSettingsForm(s);
    cur.comfyui_servers.splice(i, 1);
    drawSettingsForm(cur);
  });
  $$("[data-test-comfy]").forEach((b) => b.onclick = async () => {
    const i = +b.dataset.testComfy;
    const row = b.closest(".server-row");
    const url = row.querySelector('[data-k="url"]').value;
    const res = await api("/api/test_comfy", { method: "POST", body: JSON.stringify({ url }) });
    $("#testOut").textContent = res.result.ok
      ? `Comfy OK: ${JSON.stringify(res.result.version).slice(0, 180)}`
      : `Comfy fail: ${res.result.error}`;
  });
}

function readSettingsForm(base = {}) {
  const gpus = ($("#s_gpus").value || "").split(",").map((x) => x.trim()).filter(Boolean).map((x) => +x);
  const servers = $$("#serverList .server-row").map((row) => ({
    name: row.querySelector('[data-k="name"]').value,
    url: row.querySelector('[data-k="url"]').value,
  }));
  return {
    ...base,
    data_folder: $("#s_data").value.trim(),
    port: +$("#s_port").value || 8790,
    auto_start: !!($("#s_auto") && $("#s_auto").checked),
    nuke_launcher: $("#s_nuke").value.trim(),
    blender_launcher: $("#s_blender").value.trim(),
    total_cpu_cores: +$("#s_cores").value || 0,
    max_concurrent_jobs: +$("#s_max").value || 1,
    gpus,
    comfyui_servers: servers,
  };
}

async function testLauncher(kind, path) {
  const res = await api("/api/test_launcher", { method: "POST", body: JSON.stringify({ kind, path }) });
  $("#testOut").textContent = res.result.ok
    ? `${kind} OK → ${res.result.path} · ${res.result.version}`
    : `${kind} fail: ${res.result.error || res.result.version}`;
}

async function saveSettings() {
  const body = readSettingsForm(settings || {});
  const move = !!($("#s_move") && $("#s_move").checked);
  const res = await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({ settings: body, move_data: move }),
  });
  settings = res.settings;
  closeSettings();
  refresh();
}

async function loadSettings() {
  const res = await api("/api/settings");
  settings = res.settings;
  window.__PAAI_RQ_META__ = {
    documents_dir: res.documents_dir,
    default_data_folder: res.default_data_folder,
    pointer: res.pointer,
  };
  const sub = document.getElementById("schedInfo");
  // keep scheduler line; data path shown in settings
}

function bind() {
  $("#btnRefresh").onclick = refresh;
  $("#btnSettings").onclick = async () => { await loadSettings(); openSettings(); };
  $("#settingsClose").onclick = closeSettings;
  $("#settingsCancel").onclick = closeSettings;
  $("#settingsSave").onclick = saveSettings;
  $("#btnStartQueue").onclick = async () => {
    await api("/api/queue/start", { method: "POST", body: "{}" });
    refresh();
  };
  $("#btnStopQueue").onclick = async () => {
    await api("/api/queue/stop", { method: "POST", body: "{}" });
    refresh();
  };
  $("#btnPauseQueue").onclick = async () => {
    const paused = $("#btnPauseQueue").dataset.paused === "1";
    await api(paused ? "/api/queue/resume" : "/api/queue/pause", { method: "POST", body: "{}" });
    refresh();
  };
  $("#chkAutoStart").onchange = async () => {
    await api("/api/queue/auto_start", {
      method: "POST",
      body: JSON.stringify({ auto_start: $("#chkAutoStart").checked }),
    });
    refresh();
  };
  ["fltRunning", "fltQueued", "fltDone", "fltFailed", "search"].forEach((id) => {
    $("#" + id).addEventListener("input", renderJobs);
    $("#" + id).addEventListener("change", renderJobs);
  });
}

(async function init() {
  bind();
  await loadSettings().catch(() => {});
  await refresh();
  pollTimer = setInterval(refresh, 1500);
})();
