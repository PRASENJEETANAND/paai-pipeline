const PAAI_FULL_NAME = window.PAAI_FULL_NAME || "Prasenjeet Anand Artist Interface";
/**
 * Standalone PAAI Render Browser for Blender (same Nuke look).
 * Talks to the local /paai/* HTTP endpoints served by the add-on.
 */
const COLS = ["Sequence", "Shot", "Type", "Name", "Version", "Frames", "Note", "User", "Date", "Path"];
const API = "";  // same origin

async function jget(url) {
  const r = await fetch(API + url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function jpost(url, body) {
  const r = await fetch(API + url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
function el(tag, attrs = {}, kids = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null) n.setAttribute(k, v);
  }
  for (const c of [].concat(kids)) if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return n;
}
function btn(label, onClick, cls = "") {
  return el("button", { class: "paai-btn " + cls, type: "button", onclick: onClick, text: label });
}

function buildTree(container, data, { folded = false, onChange } = {}) {
  container.innerHTML = "";
  function leafKey(p, c) { return JSON.stringify([p, c]); }
  function syncParent(details) {
    const boxes = [...details.querySelectorAll(":scope > .kids .paai-cb")];
    const parentCb = details.querySelector(":scope > summary > .paai-cb");
    if (!parentCb || !boxes.length) return;
    const n = boxes.filter((b) => b.checked).length;
    parentCb.indeterminate = n > 0 && n < boxes.length;
    parentCb.checked = n === boxes.length && boxes.length > 0;
  }
  if (Array.isArray(data)) {
    for (const v of data) {
      const row = el("div", { class: "leaf" });
      const cb = el("input", { class: "paai-cb", type: "checkbox" });
      cb.checked = true; cb.dataset.key = leafKey(v, null);
      cb.addEventListener("change", () => onChange && onChange());
      row.appendChild(cb); row.appendChild(document.createTextNode(v));
      container.appendChild(row);
    }
    return {
      checkedKeys: () => [...container.querySelectorAll(".paai-cb")].filter((b) => b.checked).map((b) => JSON.parse(b.dataset.key)),
      setAll: (on) => { container.querySelectorAll(".paai-cb").forEach((b) => { b.checked = on; b.indeterminate = false; }); onChange && onChange(); },
      setChecked: (keys) => {
        const want = new Set(keys.map((k) => JSON.stringify(k)));
        container.querySelectorAll(".paai-cb").forEach((b) => { b.checked = want.has(b.dataset.key); b.indeterminate = false; });
      },
      toggleFold: () => false, isFolded: () => false,
    };
  }
  for (const [parent, kids] of Object.entries(data || {})) {
    const details = el("details"); details.open = !folded;
    const sum = el("summary");
    const pcb = el("input", { class: "paai-cb", type: "checkbox" });
    pcb.dataset.parent = parent;
    sum.appendChild(pcb); sum.appendChild(document.createTextNode(parent));
    details.appendChild(sum);
    const kidsEl = el("div", { class: "kids" });
    const list = kids && kids.length ? kids : [];
    if (!list.length) {
      pcb.dataset.key = leafKey(parent, null); pcb.checked = true;
      pcb.addEventListener("change", () => onChange && onChange());
    } else {
      for (const k of list) {
        const row = el("div", { class: "leaf" });
        const cb = el("input", { class: "paai-cb", type: "checkbox" });
        cb.checked = true; cb.dataset.key = leafKey(parent, k);
        cb.addEventListener("change", () => { syncParent(details); onChange && onChange(); });
        row.appendChild(cb); row.appendChild(document.createTextNode(k));
        kidsEl.appendChild(row);
      }
      pcb.checked = true;
      pcb.addEventListener("change", () => {
        const on = pcb.checked;
        kidsEl.querySelectorAll(".paai-cb").forEach((b) => { b.checked = on; b.indeterminate = false; });
        pcb.indeterminate = false; onChange && onChange();
      });
      details.appendChild(kidsEl); syncParent(details);
    }
    container.appendChild(details);
  }
  return {
    checkedKeys: () => {
      const keys = [];
      container.querySelectorAll(".paai-cb").forEach((b) => {
        if (b.dataset.key && b.checked && !b.indeterminate) keys.push(JSON.parse(b.dataset.key));
      });
      return keys;
    },
    setAll: (on) => {
      container.querySelectorAll(".paai-cb").forEach((b) => { b.checked = on; b.indeterminate = false; });
      onChange && onChange();
    },
    setChecked: (keys) => {
      const want = new Set(keys.map((k) => JSON.stringify(k)));
      const wantParents = new Set(keys.filter((k) => k[1] == null).map((k) => k[0]));
      container.querySelectorAll(".kids .paai-cb").forEach((b) => {
        const k = JSON.parse(b.dataset.key);
        b.checked = want.has(b.dataset.key) || wantParents.has(k[0]);
        b.indeterminate = false;
      });
      container.querySelectorAll("details").forEach((d) => syncParent(d));
      container.querySelectorAll(":scope > details > summary > .paai-cb[data-key]").forEach((b) => {
        b.checked = want.has(b.dataset.key);
      });
    },
    toggleFold: () => {
      const all = [...container.querySelectorAll("details")];
      const anyOpen = all.some((d) => d.open);
      all.forEach((d) => (d.open = !anyOpen));
      return anyOpen;
    },
    isFolded: () => [...container.querySelectorAll("details")].every((d) => !d.open),
  };
}

let rbState = null;

function openRenderBrowser() {
  if (document.querySelector(".paai-rb-overlay")) return;
  const overlay = el("div", { class: "paai-rb-overlay" });
  const root = el("div", { class: "paai-rb-root" });
  const titlebar = el("div", { class: "paai-rb-titlebar" }, [
    el("div", { class: "paai-title-wrap" }, [
      el("div", { class: "paai-brand-col" }, [
        el("img", { class: "paai-logo", src: "/paai_logo_header.png", alt: "PAAI" }),
        el("div", { class: "paai-brand-sub", text: PAAI_FULL_NAME }),
      ]),
      el("b", { text: "PAAI Pipeline · Render Browser" }),
    ]),
  ]);
  const rootEdit = el("input", { type: "text", value: "" });
  const topBar = el("div", { class: "paai-top" }, [
    el("label", { text: "Root" }), rootEdit,
    btn("...", () => { const v = prompt("Project root folder", rootEdit.value); if (v != null) { rootEdit.value = v.trim(); rescan(); } }),
    btn("Scan", () => rescan()),
    btn("Show config", () => openConfig()),
  ]);
  const shotTree = el("div", { class: "paai-tree" });
  const typeTree = el("div", { class: "paai-tree" });
  let shotApi = null, typeApi = null;
  const shotFold = btn("Collapse All", () => { if (!shotApi) return; shotFold.textContent = shotApi.toggleFold() ? "Expand All" : "Collapse All"; });
  const typeFold = btn("Collapse All", () => { if (!typeApi) return; typeFold.textContent = typeApi.toggleFold() ? "Expand All" : "Collapse All"; });
  const shotPanel = el("div", { class: "paai-panel" }, [
    el("div", { class: "hd", text: "Sequence / Shot" }),
    el("div", { class: "bar" }, [
      btn("All", () => shotApi && shotApi.setAll(true)),
      btn("None", () => shotApi && shotApi.setAll(false)),
      el("span", { class: "sp" }),
      btn("+ Shot", () => addShotDialog()), shotFold,
    ]),
    shotTree,
  ]);
  const typePanel = el("div", { class: "paai-panel" }, [
    el("div", { class: "hd", text: "Type / Name" }),
    el("div", { class: "bar" }, [
      btn("All", () => typeApi && typeApi.setAll(true)),
      btn("None", () => typeApi && typeApi.setAll(false)),
      el("span", { class: "sp" }),
      btn("+ Type", () => addTypeDialog()), typeFold,
    ]),
    typeTree,
  ]);
  const left = el("div", { class: "paai-left" }, [shotPanel, typePanel]);
  const latestOnly = el("input", { type: "checkbox", class: "paai-cb" });
  const search = el("input", { type: "text", placeholder: "Search path or note..." });
  const filt = el("div", { class: "paai-filt" }, [
    el("label", {}, [latestOnly, document.createTextNode(" Latest version only")]), search,
  ]);
  const table = el("table", { class: "paai-table" });
  const thead = el("thead"); const hr = el("tr");
  for (const c of COLS) hr.appendChild(el("th", { text: c }));
  thead.appendChild(hr); table.appendChild(thead);
  const tbody = el("tbody"); table.appendChild(tbody);
  const tableWrap = el("div", { class: "paai-table-wrap" }, [table]);
  const noteView = el("textarea", { placeholder: "Select a version to see or edit its note" });
  const noteRow = el("div", { class: "paai-note-row" }, [
    el("div", { class: "col" }, [el("span", { text: "Version note" }), noteView]),
    el("div", { class: "btns" }, [
      btn("Save note", () => saveNote()),
      btn("Open folder", () => openFolder()),
      btn("Set as output", () => setAsOutput(), "primary"),
      btn("Load as image", () => loadAsImage()),
    ]),
  ]);
  const right = el("div", { class: "paai-right" }, [filt, tableWrap, noteRow]);
  const split = el("div", { class: "paai-split" }, [left, right]);
  const body = el("div", { class: "paai-rb-body" }, [topBar, split]);
  root.appendChild(titlebar); root.appendChild(body);
  overlay.appendChild(root); document.body.appendChild(overlay);

  rbState = { items: [], selected: null, prefs: {}, rootEdit, latestOnly, search, tbody, noteView };
  latestOnly.addEventListener("change", () => { populate(); remember(); });
  search.addEventListener("input", () => populate());
  rootEdit.addEventListener("keydown", (e) => { if (e.key === "Enter") rescan(); });

  (async () => {
    try {
      const prefs = await jget("/paai/prefs");
      rbState.prefs = prefs || {};
      rootEdit.value = prefs.root || "";
      latestOnly.checked = !!prefs.latest_only;
      if (rootEdit.value) await rescan();
    } catch (e) { console.warn("[PAAI] prefs", e); }
  })();

  async function rescan() {
    const r = rootEdit.value.trim();
    if (!r) return alert("Set a project root first.");
    try {
      const data = await jget("/paai/scan?root=" + encodeURIComponent(r));
      if (!data.ok) return alert(data.error || "scan failed");
      rbState.items = data.items || [];
      rbState.prefs = data.prefs || rbState.prefs;
      const first = !shotTree.childElementCount;
      shotApi = buildTree(shotTree, data.shots || {}, { onChange: () => { populate(); remember(); } });
      typeApi = buildTree(typeTree, data.names || {}, { onChange: () => { populate(); remember(); } });
      if (first) restoreChecks();
      populate();
    } catch (e) { alert("Scan failed: " + e.message); }
  }
  function restoreChecks() {
    const p = rbState.prefs || {};
    if (p.checked_shots && shotApi) shotApi.setChecked(p.checked_shots);
    if (p.checked_types && typeApi) {
      typeApi.setChecked(p.checked_types.map((k) => (Array.isArray(k) ? k : [k, null])));
    }
  }
  function remember() {
    if (!rbState) return;
    const shots = shotApi ? shotApi.checkedKeys() : [];
    const types = typeApi ? typeApi.checkedKeys() : [];
    const firstShot = shots.find((k) => k[1]) || [null, null];
    const typeNames = [...new Set(types.map((k) => k[0]))];
    jpost("/paai/prefs", {
      root: rootEdit.value.trim(), seq: firstShot[0], shot: firstShot[1],
      type: typeNames.length === 1 ? typeNames[0] : null,
      checked_shots: shots, checked_types: types, latest_only: latestOnly.checked,
    }).catch(() => {});
  }
  function filtered() {
    const shots = new Set((shotApi ? shotApi.checkedKeys() : []).map((k) => JSON.stringify(k)));
    const names = typeApi ? typeApi.checkedKeys() : [];
    const nameSet = new Set(names.map((k) => JSON.stringify(k)));
    const typeOnly = new Set(names.filter((k) => k[1] == null).map((k) => k[0]));
    const text = (search.value || "").toLowerCase();
    let rows = rbState.items.filter((i) => {
      if (!shots.has(JSON.stringify([i.seq, i.shot]))) return false;
      const nk = JSON.stringify([i.type, i.name]);
      if (!(nameSet.has(nk) || typeOnly.has(i.type) || nameSet.has(JSON.stringify([i.type, null])))) return false;
      if (text && !(i.path || "").toLowerCase().includes(text) && !(i.note || "").toLowerCase().includes(text)) return false;
      return true;
    });
    if (latestOnly.checked) {
      const best = {};
      for (const i of rows) {
        const k = [i.seq, i.shot, i.type, i.name].join("|");
        if (!best[k] || parseInt(i.version.slice(1), 10) > parseInt(best[k].version.slice(1), 10)) best[k] = i;
      }
      rows = Object.values(best);
    }
    rows.sort((a, b) => {
      const ka = [a.seq, a.shot, a.type, a.name, -parseInt(a.version.slice(1), 10)];
      const kb = [b.seq, b.shot, b.type, b.name, -parseInt(b.version.slice(1), 10)];
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
    return rows;
  }
  function populate() {
    const rows = filtered();
    tbody.innerHTML = ""; rbState.selected = null; noteView.value = "";
    for (const i of rows) {
      const tr = el("tr");
      const frames = i.first != null ? `${i.first}-${i.last} (${i.count})` : "movie/still";
      const vals = [i.seq, i.shot, i.type, i.name, i.version, frames, (i.note || "").replace(/\n/g, " "), i.user, i.date, i.path];
      vals.forEach((v, c) => {
        const td = el("td", { text: v || "" });
        if (c === COLS.length - 1) {
          td.classList.add("path"); td.textContent = "";
          const b = document.createElement("bdi"); b.dir = "ltr"; b.textContent = v || "";
          td.appendChild(b); td.title = v || "";
        }
        if (c === 6) td.title = i.note || "";
        tr.appendChild(td);
      });
      tr.addEventListener("click", () => {
        tbody.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel"));
        tr.classList.add("sel"); rbState.selected = i; noteView.value = i.note || "";
      });
      tr.addEventListener("dblclick", () => { rbState.selected = i; loadAsImage(); });
      tbody.appendChild(tr);
    }
    if (tbody.firstChild) {
      tbody.firstChild.classList.add("sel");
      rbState.selected = rows[0];
      noteView.value = rows[0]?.note || "";
    }
  }
  async function saveNote() {
    const i = rbState.selected;
    if (!i) return alert("Select one version to save its note.");
    try {
      const res = await jpost("/paai/note", { folder: i.folder, note: noteView.value });
      const n = res.note || {};
      for (const it of rbState.items) {
        if (it.folder === i.folder) { it.note = n.note || noteView.value; it.user = n.user || it.user; it.date = n.date || it.date; }
      }
      populate();
    } catch (e) { alert(e.message); }
  }
  async function openFolder() {
    const i = rbState.selected; if (!i) return;
    try { await jpost("/paai/open_folder", { folder: i.folder }); } catch (e) { alert(e.message); }
  }
  async function openConfig() {
    const r = rootEdit.value.trim(); if (!r) return alert("Set a valid project root first.");
    try {
      const cfg = await jget("/paai/config?root=" + encodeURIComponent(r));
      await jpost("/paai/open_folder", { path: cfg.config_dir });
    } catch (e) { alert(e.message); }
  }
  async function setAsOutput() {
    const i = rbState.selected; if (!i) return alert("Select a render first.");
    try {
      await jpost("/paai/action", {
        action: "set_as_output",
        root: rootEdit.value.trim(), seq: i.seq, shot: i.shot,
        type: i.type, name: i.name, version: i.version,
      });
    } catch (e) { alert(e.message); }
  }
  async function loadAsImage() {
    const i = rbState.selected; if (!i) return alert("Select a render first.");
    try {
      await jpost("/paai/action", {
        action: "load_as_image",
        path: i.path, name: `${i.seq}_${i.shot}_${i.type}_${i.name}_${i.version}`,
        first: i.first, last: i.last,
      });
    } catch (e) { alert(e.message); }
  }
  function addShotDialog() {
    const ov = el("div", { class: "paai-dlg-overlay" });
    const seq = el("input", { type: "text", value: (shotApi && shotApi.checkedKeys().find(k => k[1]) || ["",""])[0] || "" });
    const shots = el("input", { type: "text", placeholder: "SH0030 or SH0030, SH0040" });
    const mk = el("input", { type: "checkbox", class: "paai-cb" }); mk.checked = true;
    const dlg = el("div", { class: "paai-dlg" }, [
      el("h3", { text: "Add Shot" }),
      el("div", { class: "row" }, [el("label", { text: "Sequence" }), seq]),
      el("div", { class: "row" }, [el("label", { text: "Shot(s)" }), shots]),
      el("div", { class: "row" }, [el("label", { text: "" }), el("label", {}, [mk, document.createTextNode(" Create folders")])]),
      el("div", { class: "actions" }, [
        btn("Cancel", () => ov.remove()),
        btn("OK", async () => {
          try {
            await jpost("/paai/add_shot", {
              root: rootEdit.value.trim(), seq: seq.value.trim(),
              shots: shots.value, make_folders: mk.checked,
            });
            ov.remove(); await rescan();
          } catch (e) { alert(e.message); }
        }, "primary"),
      ]),
    ]);
    ov.appendChild(dlg); document.body.appendChild(ov);
  }
  function addTypeDialog() {
    const ov = el("div", { class: "paai-dlg-overlay" });
    const name = el("input", { type: "text", placeholder: "e.g. denoise, cg_render" });
    const ext = el("select", {}, ["exr","png","jpg","tif","dpx","mov"].map(x => el("option", { text: x, value: x })));
    const named = el("input", { type: "checkbox", class: "paai-cb" });
    const dlg = el("div", { class: "paai-dlg" }, [
      el("h3", { text: "Add Render Type" }),
      el("div", { class: "row" }, [el("label", { text: "Type name" }), name]),
      el("div", { class: "row" }, [el("label", { text: "File type" }), ext]),
      el("div", { class: "row" }, [el("label", { text: "" }), el("label", {}, [named, document.createTextNode(" Needs element name")])]),
      el("div", { class: "actions" }, [
        btn("Cancel", () => ov.remove()),
        btn("OK", async () => {
          try {
            await jpost("/paai/add_type", {
              root: rootEdit.value.trim(), name: name.value.trim(),
              ext: ext.value, named: named.checked,
            });
            ov.remove(); await rescan();
          } catch (e) { alert(e.message); }
        }, "primary"),
      ]),
    ]);
    ov.appendChild(dlg); document.body.appendChild(ov);
  }
}

document.addEventListener("DOMContentLoaded", openRenderBrowser);
