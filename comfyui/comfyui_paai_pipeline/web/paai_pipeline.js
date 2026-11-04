import { PAAI_FULL_NAME } from "./paai_branding.js";
/**
 * PAAI Pipeline for ComfyUI
 * - Top-bar "PAAI Pipeline" button (beside Manager / settings) -> Render Browser
 * - Render Browser modal matching Nuke UI colors/layout
 * - Combo refresh + path preview for PAAI Load / PAAI Write nodes
 */
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const COLS = ["Sequence", "Shot", "Type", "Name", "Version", "Frames", "Note", "User", "Date", "Path"];
const CSS_HREF = new URL("./paai_browser.css", import.meta.url).href;

function ensureCSS() {
  if (document.getElementById("paai-browser-css")) return;
  const link = document.createElement("link");
  link.id = "paai-browser-css";
  link.rel = "stylesheet";
  link.href = CSS_HREF;
  document.head.appendChild(link);
}

async function jget(url) {
  const r = await api.fetchApi(url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function jpost(url, body) {
  const r = await api.fetchApi(url, {
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
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null) n.setAttribute(k, v);
  }
  for (const c of [].concat(kids)) if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return n;
}

function btn(label, onClick, cls = "") {
  return el("button", { class: "paai-btn " + cls, type: "button", onclick: onClick, text: label });
}

/* ------------------------------------------------------------------ Pipeline top-bar button */
function showPipelineMenu(anchor) {
  document.querySelectorAll(".paai-drop").forEach((d) => d.remove());
  const menu = el("div", { class: "paai-drop" }, [
    el("div", {
      class: "mi", text: "Render Browser", onclick: () => {
        menu.remove();
        openRenderBrowser();
      },
    }),
    el("div", {
      class: "mi", text: "Submit to Queue", onclick: () => {
        menu.remove();
        openSubmitQueue();
      },
    }),
    el("div", {
      class: "mi", text: "Open Render Queue", onclick: () => {
        menu.remove();
        window.open((localStorage.getItem("paai_rq_url") || "http://127.0.0.1:8790").replace(/\/$/, "") + "/", "_blank");
      },
    }),
    el("div", {
      class: "mi", text: "Create / Check Show", onclick: () => {
        menu.remove();
        openShowTool();
      },
    }),
  ]);
  document.body.appendChild(menu);
  const r = anchor.getBoundingClientRect();
  menu.style.left = Math.max(8, r.left) + "px";
  menu.style.top = r.bottom + 4 + "px";
  const off = (e) => {
    if (!e.target.closest?.(".paai-drop") && !e.target.closest?.(".paai-menu-btn") && !e.target.closest?.(".paai-top-group")) {
      menu.remove();
      removeEventListener("pointerdown", off, true);
    }
  };
  setTimeout(() => addEventListener("pointerdown", off, true), 0);
}

async function attachPipelineButton(attempt = 0) {
  if (document.querySelector(".paai-top-group")) return;

  // Strategy 1: modern ComfyButton + settingsGroup (like Manager / LoRA Manager)
  try {
    const { ComfyButton } = await import("../../scripts/ui/components/button.js");
    const { ComfyButtonGroup } = await import("../../scripts/ui/components/buttonGroup.js");
    const settingsGroup = app.menu?.settingsGroup;
    if (settingsGroup?.element?.parentElement) {
      const button = new ComfyButton({
        icon: "folder",
        tooltip: "PAAI Pipeline",
        app,
        enabled: true,
        classList: "comfyui-button comfyui-menu-mobile-collapse",
        action: () => {},
      });
      // Prefer a labeled control
      try {
        button.element.textContent = "";
        button.element.appendChild(document.createTextNode("PAAI Pipeline"));
        button.element.classList.add("paai-menu-btn", "accent");
      } catch {}
      button.element.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        showPipelineMenu(button.element);
      });
      const group = new ComfyButtonGroup(button);
      group.element.classList.add("paai-top-group");
      settingsGroup.element.before(group.element);
      return;
    }
  } catch (e) {
    /* fall through */
  }

  // Strategy 2: actionBarButtons API (newer frontends)
  try {
    if (app.extensionManager?.registerSidebarTab) {
      /* keep going to DOM fallback for a visible Pipeline button */
    }
  } catch {}

    // Strategy 2b: new frontend command / topbar API
  try {
    const em = app.extensionManager || app.ui?.extensionManager || null;
    if (em) {
      const run = () => openRenderBrowser();
      const reg = em.commands?.register?.bind(em.commands) || em.registerCommand?.bind(em);
      if (typeof reg === "function") {
        try { reg({ id: "paai.openRenderBrowser", label: "PAAI Pipeline", function: run }); } catch (e) {}
      }
      const add = em.addTopbarButton || em.registerToolbarButton || em.topbar?.register;
      if (typeof add === "function") {
        try { add.call(em, { id: "paai-pipeline", label: "PAAI Pipeline", tooltip: "PAAI Pipeline", action: run }); return true; } catch (e) {}
      }
    }
  } catch (e) {}

// Strategy 3: legacy .comfy-menu / comfyui-menu
  const menu =
    document.querySelector(".comfyui-menu") ||
    document.querySelector(".comfy-menu") ||
    document.querySelector("#comfy-menu") ||
    document.querySelector(".comfyui-menu-right");
  if (menu) {
    const b = el("button", {
      class: "paai-menu-btn accent paai-top-group",
      type: "button",
      text: "PAAI Pipeline",
      title: "PAAI Pipeline",
      onclick: (e) => {
        e.preventDefault();
        showPipelineMenu(b);
      },
    });
    // Try to place near Manager
    const mgr =
      [...menu.querySelectorAll("button, a, div")].find((x) => /manager/i.test(x.textContent || x.title || "")) || null;
    if (mgr && mgr.parentElement) mgr.parentElement.insertBefore(b, mgr.nextSibling);
    else menu.appendChild(b);
    return;
  }

  if (attempt < 120) requestAnimationFrame(() => attachPipelineButton(attempt + 1));
  else {
    // Last resort: floating chip
    const b = el("button", {
      class: "paai-menu-btn accent paai-top-group",
      type: "button",
      text: "PAAI Pipeline",
      style: "position:fixed;top:8px;right:120px;z-index:9999;background:#323232;border:1px solid #f7931e;",
      onclick: (e) => showPipelineMenu(b),
    });
    document.body.appendChild(b);
  }
}

/* ------------------------------------------------------------------ Tree panel (Sequence/Shot, Type/Name) */
function buildTree(container, data, { folded = false, onChange } = {}) {
  container.innerHTML = "";
  const state = new Map(); // key "p/c" -> bool

  function leafKey(p, c) {
    return JSON.stringify([p, c]);
  }

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
      cb.checked = true;
      cb.dataset.key = leafKey(v, null);
      cb.addEventListener("change", () => onChange && onChange());
      row.appendChild(cb);
      row.appendChild(document.createTextNode(v));
      container.appendChild(row);
    }
    return {
      checkedKeys: () =>
        [...container.querySelectorAll(".paai-cb")]
          .filter((b) => b.checked)
          .map((b) => JSON.parse(b.dataset.key)),
      setAll: (on) => {
        container.querySelectorAll(".paai-cb").forEach((b) => {
          b.checked = on;
          b.indeterminate = false;
        });
        onChange && onChange();
      },
      setChecked: (keys) => {
        const want = new Set(keys.map((k) => JSON.stringify(k)));
        container.querySelectorAll(".paai-cb").forEach((b) => {
          b.checked = want.has(b.dataset.key);
          b.indeterminate = false;
        });
      },
      toggleFold: () => {},
      isFolded: () => false,
    };
  }

  for (const [parent, kids] of Object.entries(data || {})) {
    const details = el("details");
    details.open = !folded;
    const sum = el("summary");
    const pcb = el("input", { class: "paai-cb", type: "checkbox" });
    pcb.dataset.parent = parent;
    sum.appendChild(pcb);
    sum.appendChild(document.createTextNode(parent));
    details.appendChild(sum);
    const kidsEl = el("div", { class: "kids" });
    const list = kids && kids.length ? kids : [];
    if (!list.length) {
      // empty parent is itself a leaf key (parent, null)
      pcb.dataset.key = leafKey(parent, null);
      pcb.checked = true;
      pcb.addEventListener("change", () => onChange && onChange());
    } else {
      for (const k of list) {
        const row = el("div", { class: "leaf" });
        const cb = el("input", { class: "paai-cb", type: "checkbox" });
        cb.checked = true;
        cb.dataset.key = leafKey(parent, k);
        cb.addEventListener("change", () => {
          syncParent(details);
          onChange && onChange();
        });
        row.appendChild(cb);
        row.appendChild(document.createTextNode(k));
        kidsEl.appendChild(row);
      }
      pcb.checked = true;
      pcb.addEventListener("change", () => {
        const on = pcb.checked;
        kidsEl.querySelectorAll(".paai-cb").forEach((b) => {
          b.checked = on;
          b.indeterminate = false;
        });
        pcb.indeterminate = false;
        onChange && onChange();
      });
      details.appendChild(kidsEl);
      syncParent(details);
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
      container.querySelectorAll(".paai-cb").forEach((b) => {
        b.checked = on;
        b.indeterminate = false;
      });
      onChange && onChange();
    },
    setChecked: (keys) => {
      const want = new Set(keys.map((k) => JSON.stringify(k)));
      // also accept type-only (t, null) as all children of t
      const wantParents = new Set(keys.filter((k) => k[1] == null).map((k) => k[0]));
      container.querySelectorAll(".kids .paai-cb").forEach((b) => {
        const k = JSON.parse(b.dataset.key);
        b.checked = want.has(b.dataset.key) || wantParents.has(k[0]);
        b.indeterminate = false;
      });
      container.querySelectorAll("details").forEach((d) => syncParent(d));
      // empty parents
      container.querySelectorAll(":scope > details > summary > .paai-cb[data-key]").forEach((b) => {
        b.checked = want.has(b.dataset.key);
      });
    },
    toggleFold: () => {
      const all = [...container.querySelectorAll("details")];
      const anyOpen = all.some((d) => d.open);
      all.forEach((d) => (d.open = !anyOpen));
      return anyOpen; // was open -> now collapsed
    },
    isFolded: () => [...container.querySelectorAll("details")].every((d) => !d.open),
  };
}

/* ------------------------------------------------------------------ Render Browser */
let rbState = null;

function openRenderBrowser() {
  ensureCSS();
  if (document.querySelector(".paai-rb-overlay")) {
    document.querySelector(".paai-rb-overlay").style.display = "flex";
    return;
  }

  const overlay = el("div", { class: "paai-rb-overlay" });
  const root = el("div", { class: "paai-rb-root" });
  const titlebar = el("div", { class: "paai-rb-titlebar" }, [
    el("div", { class: "paai-title-wrap" }, [
      el("div", { class: "paai-brand-col" }, [
        el("img", { class: "paai-logo", src: new URL("./paai_logo_header.png", import.meta.url).href, alt: "PAAI" }),
        el("div", { class: "paai-brand-sub", text: PAAI_FULL_NAME }),
      ]),
      el("b", { text: "PAAI Pipeline · Render Browser" }),
    ]),
    el("button", {
      class: "paai-x", type: "button", text: "✕", onclick: () => {
        remember();
        overlay.remove();
        rbState = null;
      },
    }),
  ]);

  // drag
  (function makeDrag(bar, win) {
    let ox = 0, oy = 0, dragging = false;
    bar.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button")) return;
      dragging = true;
      const r = win.getBoundingClientRect();
      ox = e.clientX - r.left;
      oy = e.clientY - r.top;
      win.style.position = "fixed";
      win.style.margin = "0";
      bar.setPointerCapture(e.pointerId);
    });
    bar.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      win.style.left = Math.max(0, e.clientX - ox) + "px";
      win.style.top = Math.max(0, e.clientY - oy) + "px";
      overlay.style.alignItems = "flex-start";
      overlay.style.justifyContent = "flex-start";
      overlay.style.padding = "0";
    });
    bar.addEventListener("pointerup", () => (dragging = false));
  })(titlebar, root);

  const rootEdit = el("input", { type: "text", value: "" });
  const topBar = el("div", { class: "paai-top" }, [
    el("label", { text: "Root" }),
    rootEdit,
    btn("...", () => {
      const v = prompt("Project root folder", rootEdit.value);
      if (v != null) {
        rootEdit.value = v.trim();
        rescan();
      }
    }),
    btn("Scan", () => rescan()),
    btn("Show config", () => openConfig()),
  ]);

  const shotTree = el("div", { class: "paai-tree" });
  const typeTree = el("div", { class: "paai-tree" });
  let shotApi = null, typeApi = null;

  const shotFold = btn("Collapse All", () => {
    if (!shotApi) return;
    const collapsed = shotApi.toggleFold();
    shotFold.textContent = collapsed ? "Expand All" : "Collapse All";
  });
  const typeFold = btn("Collapse All", () => {
    if (!typeApi) return;
    const collapsed = typeApi.toggleFold();
    typeFold.textContent = collapsed ? "Expand All" : "Collapse All";
  });

  const shotPanel = el("div", { class: "paai-panel" }, [
    el("div", { class: "hd", text: "Sequence / Shot" }),
    el("div", { class: "bar" }, [
      btn("All", () => shotApi && shotApi.setAll(true)),
      btn("None", () => shotApi && shotApi.setAll(false)),
      el("span", { class: "sp" }),
      btn("+ Shot", () => addShotDialog()),
      shotFold,
    ]),
    shotTree,
  ]);
  const typePanel = el("div", { class: "paai-panel" }, [
    el("div", { class: "hd", text: "Type / Name" }),
    el("div", { class: "bar" }, [
      btn("All", () => typeApi && typeApi.setAll(true)),
      btn("None", () => typeApi && typeApi.setAll(false)),
      el("span", { class: "sp" }),
      btn("+ Type", () => addTypeDialog()),
      typeFold,
    ]),
    typeTree,
  ]);
  const left = el("div", { class: "paai-left" }, [shotPanel, typePanel]);

  const latestOnly = el("input", { type: "checkbox", class: "paai-cb" });
  const search = el("input", { type: "text", placeholder: "Search path or note..." });
  const filt = el("div", { class: "paai-filt" }, [
    el("label", {}, [latestOnly, document.createTextNode(" Latest version only")]),
    search,
  ]);

  const table = el("table", { class: "paai-table" });
  const thead = el("thead");
  const hr = el("tr");
  for (const c of COLS) hr.appendChild(el("th", { text: c }));
  thead.appendChild(hr);
  table.appendChild(thead);
  const tbody = el("tbody");
  table.appendChild(tbody);
  const tableWrap = el("div", { class: "paai-table-wrap" }, [table]);

  const noteView = el("textarea", { placeholder: "Select a version to see or edit its note" });
  const noteRow = el("div", { class: "paai-note-row" }, [
    el("div", { class: "col" }, [el("span", { text: "Version note" }), noteView]),
    el("div", { class: "btns" }, [
      btn("Save note", () => saveNote()),
      btn("Open folder", () => openFolder()),
      btn("Set selected Writes", () => setSelectedWrites()),
      btn("Load as Read", () => loadAsRead(), "primary"),
    ]),
  ]);

  const right = el("div", { class: "paai-right" }, [filt, tableWrap, noteRow]);
  const split = el("div", { class: "paai-split" }, [left, right]);
  const body = el("div", { class: "paai-rb-body" }, [topBar, split]);
  root.appendChild(titlebar);
  root.appendChild(body);
  overlay.appendChild(root);
  // click outside chrome to close? keep open; only X closes
  overlay.addEventListener("mousedown", (e) => {
    if (e.target === overlay) {
      /* don't auto-close — Nuke panel stays */
    }
  });
  document.body.appendChild(overlay);

  rbState = {
    items: [],
    selected: null,
    prefs: {},
    rootEdit,
    latestOnly,
    search,
    tbody,
    noteView,
    shotTree,
    typeTree,
    get shotApi() { return shotApi; },
    set shotApi(v) { shotApi = v; },
    get typeApi() { return typeApi; },
    set typeApi(v) { typeApi = v; },
  };

  latestOnly.addEventListener("change", () => { populate(); remember(); });
  search.addEventListener("input", () => populate());
  rootEdit.addEventListener("keydown", (e) => {
    if (e.key === "Enter") rescan();
  });

  // bootstrap
  (async () => {
    try {
      const prefs = await jget("/paai/prefs");
      rbState.prefs = prefs || {};
      rootEdit.value = prefs.root || "";
      latestOnly.checked = !!prefs.latest_only;
      if (rootEdit.value) await rescan();
    } catch (e) {
      console.warn("[PAAI] prefs", e);
    }
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
      shotApi = buildTree(shotTree, data.shots || {}, {
        onChange: () => { populate(); remember(); },
      });
      typeApi = buildTree(typeTree, data.names || {}, {
        onChange: () => { populate(); remember(); },
      });
      rbState.shotApi = shotApi;
      rbState.typeApi = typeApi;
      if (first) restoreChecks();
      populate();
    } catch (e) {
      alert("Scan failed: " + e.message);
    }
  }

  function restoreChecks() {
    const p = rbState.prefs || {};
    if (p.checked_shots && shotApi) shotApi.setChecked(p.checked_shots);
    if (p.checked_types && typeApi) {
      const keys = p.checked_types.map((k) => (Array.isArray(k) ? k : [k, null]));
      typeApi.setChecked(keys);
    }
  }

  function remember() {
    if (!rbState) return;
    const shots = shotApi ? shotApi.checkedKeys() : [];
    const types = typeApi ? typeApi.checkedKeys() : [];
    const firstShot = shots.find((k) => k[1]) || [null, null];
    const typeNames = [...new Set(types.map((k) => k[0]))];
    jpost("/paai/prefs", {
      root: rootEdit.value.trim(),
      seq: firstShot[0],
      shot: firstShot[1],
      type: typeNames.length === 1 ? typeNames[0] : null,
      checked_shots: shots,
      checked_types: types,
      latest_only: latestOnly.checked,
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
    tbody.innerHTML = "";
    rbState.selected = null;
    noteView.value = "";
    for (const i of rows) {
      const tr = el("tr");
      const frames =
        i.first != null ? `${i.first}-${i.last} (${i.count})` : "movie/still";
      const vals = [i.seq, i.shot, i.type, i.name, i.version, frames, (i.note || "").replace(/\n/g, " "), i.user, i.date, i.path];
      vals.forEach((v, c) => {
        const td = el("td", { text: v || "" });
        if (c === COLS.length - 1) { td.classList.add("path"); td.textContent = ""; const b = document.createElement("bdi"); b.dir = "ltr"; b.textContent = v || ""; td.appendChild(b); td.title = v || ""; }
        if (c === 6) td.title = i.note || "";
        tr.appendChild(td);
      });
      tr.addEventListener("click", () => {
        tbody.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel"));
        tr.classList.add("sel");
        rbState.selected = i;
        noteView.value = i.note || "";
      });
      tr.addEventListener("dblclick", () => {
        rbState.selected = i;
        loadAsRead();
      });
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
        if (it.folder === i.folder) {
          it.note = n.note || noteView.value;
          it.user = n.user || it.user;
          it.date = n.date || it.date;
        }
      }
      populate();
    } catch (e) {
      alert(e.message);
    }
  }

  async function openFolder() {
    const i = rbState.selected;
    if (!i) return;
    try {
      await jpost("/paai/open_folder", { folder: i.folder });
    } catch (e) {
      alert(e.message);
    }
  }

  async function openConfig() {
    const r = rootEdit.value.trim();
    if (!r) return alert("Set a valid project root first.");
    try {
      const cfg = await jget("/paai/config?root=" + encodeURIComponent(r));
      await jpost("/paai/open_folder", { path: cfg.config_dir });
    } catch (e) {
      alert(e.message);
    }
  }

  function loadAsRead() {
    const i = rbState.selected;
    if (!i) return alert("Select a render first.");
    const node = LiteGraph.createNode("PAAI_Load");
    if (!node) return alert("PAAI_Load node not registered.");
    app.graph.add(node);
    node.pos = [app.canvas.graph_mouse[0], app.canvas.graph_mouse[1]];
    setWidget(node, "root", rootEdit.value.trim());
    setWidget(node, "sequence", i.seq);
    setWidget(node, "shot", i.shot);
    setWidget(node, "type", i.type);
    setWidget(node, "name", i.name);
    setWidget(node, "version", i.version);
    setWidget(node, "path_override", i.path);
    app.graph.setDirtyCanvas(true, true);
  }

  function setSelectedWrites() {
    const i = rbState.selected;
    const writes = (app.canvas.selected_nodes
      ? Object.values(app.canvas.selected_nodes)
      : app.graph._nodes.filter((n) => n.is_selected)
    ).filter((n) => n.comfyClass === "PAAI_Write" || n.type === "PAAI_Write");
    if (!writes.length) return alert("Select one or more PAAI Write nodes in the graph first.");
    const seq = i?.seq || (shotApi?.checkedKeys().find((k) => k[1]) || [])[0];
    const shot = i?.shot || (shotApi?.checkedKeys().find((k) => k[1]) || [])[1];
    if (!seq) return alert("Pick a shot in the list or the Sequence / Shot panel.");
    for (const n of writes) {
      setWidget(n, "root", rootEdit.value.trim());
      setWidget(n, "sequence", seq);
      setWidget(n, "shot", shot);
      if (i) {
        setWidget(n, "type", i.type);
        setWidget(n, "name", i.name);
      }
      refreshWritePreview(n);
    }
    remember();
  }

  function addShotDialog() {
    const r = rootEdit.value.trim();
    if (!r) return alert("Set a valid project root first.");
    const seqs = shotApi
      ? [...new Set(shotApi.checkedKeys().map((k) => k[0]).concat(
          [...shotTree.querySelectorAll("details > summary")].map((s) => s.textContent.trim())
        ))]
      : [];
    const dlg = makeDialog("Add Shot", [
      { key: "seq", label: "Sequence", type: "combo", options: seqs, editable: true, value: seqs[0] || "" },
      { key: "shots", label: "Shot(s)", type: "text", placeholder: "SH0030  or several: SH0030, SH0040" },
      { key: "mk", label: "", type: "check", text: "Create shot folders on disk", checked: true },
    ], async (vals) => {
      await jpost("/paai/add_shot", {
        root: r, seq: vals.seq, shots: vals.shots, make_folders: vals.mk,
      });
      await rescan();
      const names = String(vals.shots || "").replace(/;/g, ",").split(",").map((x) => x.trim()).filter(Boolean);
      if (shotApi && names.length) shotApi.setChecked(names.map((sh) => [vals.seq, sh]));
      populate();
      remember();
    });
    document.body.appendChild(dlg);
  }

  function addTypeDialog() {
    const r = rootEdit.value.trim();
    if (!r) return alert("Set a valid project root first.");
    const dlg = makeDialog("Add Render Type", [
      { key: "name", label: "Type name", type: "text", placeholder: "e.g. denoise, cleanup, lighting" },
      { key: "ext", label: "File type", type: "combo", options: ["exr", "png", "jpg", "tif", "dpx", "mov"], value: "exr", editable: true },
      { key: "named", label: "", type: "check", text: "Needs an element name (like element / comfyui)", checked: false },
    ], async (vals) => {
      const n = (vals.name || "").trim().replace(/ /g, "_");
      const res = await jpost("/paai/add_type", { root: r, name: n, ext: vals.ext, named: vals.named });
      if (!res.ok) return alert("Type is empty or already exists.");
      await rescan();
      if (typeApi) typeApi.setChecked([[n, "main"]]);
      populate();
      remember();
    });
    document.body.appendChild(dlg);
  }
}

function makeDialog(title, fields, onOk) {
  const overlay = el("div", { class: "paai-dlg-overlay" });
  const box = el("div", { class: "paai-dlg" }, [el("h3", { text: title })]);
  const vals = {};
  const inputs = {};
  for (const f of fields) {
    const row = el("div", { class: "row" });
    if (f.type === "check") {
      const cb = el("input", { type: "checkbox", class: "paai-cb" });
      cb.checked = !!f.checked;
      inputs[f.key] = cb;
      row.appendChild(el("label", { text: "" }));
      row.appendChild(el("label", {}, [cb, document.createTextNode(" " + (f.text || ""))]));
    } else if (f.type === "combo") {
      row.appendChild(el("label", { text: f.label }));
      const sel = el("input", { type: "text", list: "paai-dl-" + f.key, value: f.value || "" });
      const dl = el("datalist", { id: "paai-dl-" + f.key });
      for (const o of f.options || []) dl.appendChild(el("option", { value: o }));
      inputs[f.key] = sel;
      row.appendChild(sel);
      row.appendChild(dl);
    } else {
      row.appendChild(el("label", { text: f.label }));
      const inp = el("input", { type: "text", placeholder: f.placeholder || "", value: f.value || "" });
      inputs[f.key] = inp;
      row.appendChild(inp);
    }
    box.appendChild(row);
  }
  const actions = el("div", { class: "actions" }, [
    btn("Cancel", () => overlay.remove()),
    btn("OK", async () => {
      for (const f of fields) {
        const inp = inputs[f.key];
        vals[f.key] = f.type === "check" ? inp.checked : inp.value;
      }
      overlay.remove();
      try { await onOk(vals); } catch (e) { alert(e.message); }
    }, "primary"),
  ]);
  box.appendChild(actions);
  overlay.appendChild(box);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) overlay.remove(); });
  return overlay;
}

function setWidget(node, name, value) {
  const w = node.widgets?.find((x) => x.name === name);
  if (!w) return;
  w.value = value;
  w.callback?.(value);
}

/* ------------------------------------------------------------------ Node combo refresh */
const FORMATS = {
  exr:  { bit_depth: ["half", "float"], compression: ["zip", "zips", "piz", "pxr24", "rle", "dwaa", "dwab", "none"] },
  png:  { bit_depth: ["8", "16"], compression: ["level 6", "level 0", "level 1", "level 3", "level 9"] },
  jpg:  { bit_depth: ["8"], compression: ["quality 95", "quality 100", "quality 90", "quality 80", "quality 70"] },
  tiff: { bit_depth: ["8", "16", "float"], compression: ["lzw", "zip", "packbits", "none"] },
};

function wval(node, name) {
  const w = node.widgets?.find((x) => x.name === name);
  return w ? (w.value ?? "") : "";
}

function applyFormat(node) {
  const f = FORMATS[wval(node, "file_type")] || FORMATS.png;
  applyCombo(node, "bit_depth", f.bit_depth, wval(node, "bit_depth"));
  applyCombo(node, "compression", f.compression, wval(node, "compression"));
}

async function refreshCombos(node, kind) {
  const root = String(wval(node, "root")).trim();
  if (!root) return;
  const q = new URLSearchParams({
    root, kind,
    sequence: wval(node, "sequence"), shot: wval(node, "shot"),
    type: wval(node, "type"), name: wval(node, "name"),
  });
  let data;
  try { data = await jget("/paai/dropdowns?" + q.toString()); } catch (e) { console.warn("[PAAI] dropdowns", e); return; }
  if (!data.ok) return;
  applyCombo(node, "sequence", data.sequences, data.sequence);
  applyCombo(node, "shot", data.shots, data.shot);
  applyCombo(node, "type", data.types, data.type);
  if (kind === "load") applyCombo(node, "name", data.names, data.name);
  const vers = data.versions && data.versions.length ? data.versions : [kind === "load" ? "" : "New"];
  // Load: newest version by default; Write: keep the pick if it still exists, else New
  const cur = wval(node, "version");
  applyCombo(node, "version", vers, vers.includes(cur) ? cur : (kind === "load" ? [...vers].sort().pop() : "New"));
  if (kind === "load") {
    try {
      const lq = new URLSearchParams({ root, sequence: data.sequence, shot: data.shot, type: data.type,
                                       name: data.name, version: wval(node, "version") });
      const layers = await jget("/paai/layers?" + lq.toString());
      applyCombo(node, "aov", layers.layers || ["rgba"], wval(node, "aov") || "rgba");
    } catch (e) { applyCombo(node, "aov", ["rgba"], "rgba"); }
  } else {
    await refreshWritePreview(node);
  }
}

async function refreshWritePreview(node) {
  const get = (n) => node.widgets?.find((w) => w.name === n)?.value || "";
  const q = new URLSearchParams({
    root: get("root"), sequence: get("sequence"), shot: get("shot"),
    type: get("type"), name: get("name"), version: get("version") || "New",
    ext: get("file_type") || "png",
  });
  try {
    const data = await jget("/paai/preview_path?" + q.toString());
    let widget = node._paaiPreview;
    if (!widget) {
      // add a read-only label via DOM on the node
      const info = document.createElement("div");
      info.className = data.is_new ? "paai-info-new" : "paai-info-ow";
      const path = document.createElement("div");
      path.className = "paai-path-preview";
      const wrap = document.createElement("div");
      wrap.className = "paai-node-preview";
      wrap.appendChild(info);
      wrap.appendChild(path);
      node._paaiPreview = { info, path, wrap };
      // attach below widgets if possible
      if (node.widgets) {
        node.addDOMWidget?.("paai_preview", "preview", wrap);
      }
      widget = node._paaiPreview;
    }
    widget.info.className = data.is_new ? "paai-info-new" : "paai-info-ow";
    widget.info.textContent = data.info || "";
    widget.path.textContent = "";
    const pb = document.createElement("bdi"); pb.dir = "ltr"; pb.textContent = data.path || "";
    widget.path.appendChild(pb);
    widget.path.title = data.path || "";
  } catch (e) {
    console.warn("[PAAI] preview", e);
  }
}

function applyCombo(node, name, values, current) {
  const w = node.widgets?.find((x) => x.name === name);
  if (!w) return;
  values = values && values.length ? values : [""];
  // Comfy combo widgets use w.options.values
  if (w.options) w.options.values = values;
  if (w.type === "combo" || Array.isArray(w.options?.values)) {
    if (current && values.includes(current)) w.value = current;
    else if (!values.includes(w.value)) w.value = values[0];
  } else {
    // STRING widgets: keep text, optionally no-op
    if (current != null && current !== "") w.value = current;
  }
  node.setDirtyCanvas?.(true, true);
}

function wireNodeCombos(node, kind) {
  if (node._paaiWired) return;
  node._paaiWired = true;
  let timer = null;
  const later = (fn, ms) => { clearTimeout(timer); timer = setTimeout(fn, ms); };
  const watch = ["root", "sequence", "shot", "type", "name", "version", "file_type", "aov"];
  for (const name of watch) {
    const w = node.widgets?.find((x) => x.name === name);
    if (!w) continue;
    const prev = w.callback;
    w.callback = function () {
      const r = prev?.apply(this, arguments);
      if (name === "file_type") { applyFormat(node); if (kind === "write") refreshWritePreview(node); return r; }
      if (name === "aov") return r;
      if (kind === "write" && ["root", "sequence", "shot", "type", "name"].includes(name)) {
        const vw = node.widgets?.find((x) => x.name === "version");
        if (vw) vw.value = "New";                 // a new target never overwrites by accident
      }
      if (kind === "write" && name === "version") { refreshWritePreview(node); return r; }
      // typing in root / name: wait until typing pauses
      later(() => refreshCombos(node, kind), name === "root" || name === "name" ? 400 : 0);
      return r;
    };
  }
  if (kind === "write") applyFormat(node);
  setTimeout(() => refreshCombos(node, kind), 50);
}

app.registerExtension({
  name: "paai.pipeline",
  async setup() {
    ensureCSS();
    attachPipelineButton();
  },
  loadedGraphNode(node) {
    // saved workflow: re-check its values against the disk once they are restored
    if (node.comfyClass === "PAAI_Load" || node.type === "PAAI_Load") setTimeout(() => refreshCombos(node, "load"), 100);
    if (node.comfyClass === "PAAI_Write" || node.type === "PAAI_Write") setTimeout(() => { applyFormat(node); refreshCombos(node, "write"); }, 100);
  },
  async nodeCreated(node) {
    if (node.comfyClass === "PAAI_Load" || node.type === "PAAI_Load") wireNodeCombos(node, "load");
    if (node.comfyClass === "PAAI_Write" || node.type === "PAAI_Write") wireNodeCombos(node, "write");
  },
});


/* ------------------------------------------------------------------ Submit to Render Queue */
const RQ_URL_KEY = "paai_rq_url";
function rqBase() {
  return (localStorage.getItem(RQ_URL_KEY) || "http://127.0.0.1:8790").replace(/\/$/, "");
}


async function openShowTool() {
  const ov = el("div", { class: "paai-overlay" });
  const root = el("input", { type: "text", value: "" });
  const seq = el("input", { type: "text", value: "SQ010" });
  const shots = el("input", { type: "text", value: "SH010,SH020" });
  const log = el("pre", { style: "max-height:240px;overflow:auto;background:#1e1e1e;padding:8px;border-radius:4px;font-size:11px" });
  try {
    const prefs = await jget("/paai/prefs");
    if (prefs && prefs.root) root.value = prefs.root;
  } catch (e) {}
  const run = async (path) => {
    const body = { root: root.value.trim(), sequence: seq.value.trim(), shots: shots.value.trim() };
    const data = await jpost(path, body);
    log.textContent = (data.check || [data.error || JSON.stringify(data, null, 2)]).join("\n");
  };
  const dlg = el("div", { class: "paai-dlg", style: "min-width:480px" }, [
    el("h3", { text: "Create / Check Show" }),
    el("div", { class: "row" }, [el("label", { text: "Show root" }), root]),
    el("div", { class: "row" }, [el("label", { text: "Sequence" }), seq]),
    el("div", { class: "row" }, [el("label", { text: "Shots" }), shots]),
    log,
    el("div", { class: "actions" }, [
      btn("Cancel", () => ov.remove()),
      btn("Check", async () => { try { await run("/paai/show/check"); } catch (e) { log.textContent = String(e); } }),
      btn("Create + Check", async () => { try { await run("/paai/show/create"); } catch (e) { log.textContent = String(e); } }, "primary"),
    ]),
  ]);
  ov.appendChild(dlg);
  document.body.appendChild(ov);
}

async function openSubmitQueue() {
  ensureCSS();
  const ov = el("div", { class: "paai-dlg-overlay" });
  const workflows = [];
  try {
    workflows.push({ id: "current", title: "Current workflow", getPrompt: async () => {
      const p = await app.graphToPrompt();
      return p.output || p;
    }});
  } catch (e) { console.warn(e); }
  try {
    const wm = app.workflowManager || app.extensionManager?.workflow || null;
    const open = wm?.openWorkflows || wm?.workflows || [];
    for (const w of open) {
      const id = w.id || w.path || w.filename || Math.random().toString(36).slice(2);
      const title = w.filename || w.name || w.path || ("Workflow " + id);
      if (workflows.some((x) => x.title === title)) continue;
      workflows.push({
        id, title,
        getPrompt: async () => {
          if (typeof w.changeTo === "function") await w.changeTo();
          else if (wm?.openWorkflow) await wm.openWorkflow(w);
          await new Promise((r) => setTimeout(r, 50));
          const p = await app.graphToPrompt();
          return p.output || p;
        },
      });
    }
  } catch (e) {}

  const rows = workflows.map((w, i) => {
    const cb = el("input", { class: "paai-cb", type: "checkbox" });
    cb.checked = i === 0;
    return el("div", { class: "row", style: "justify-content:flex-start" }, [
      cb, el("span", { text: w.title, style: "margin-left:8px" }),
    ]);
  });

  const repeats = el("input", { type: "text", value: "1" });
  const seed = el("input", { class: "paai-cb", type: "checkbox" });
  const pri = el("input", { type: "text", value: "50" });
  const server = el("input", { type: "text", value: "http://127.0.0.1:8188" });
  const rqUrl = el("input", { type: "text", value: rqBase(), placeholder: "auto-discovered if blank" });
  const rqPath = el("input", { type: "text", value: localStorage.getItem("paai_rq_path") || "", placeholder: "Optional folder (discovery) or URL" });

  const dlg = el("div", { class: "paai-dlg", style: "min-width:460px" }, [
    el("h3", { text: "Submit to PAAI Render Queue" }),
    el("div", { class: "row" }, [el("label", { text: "Queue URL" }), rqUrl]),
    el("div", { class: "row" }, [el("label", { text: "Render Queue path" }), rqPath]),
    el("div", { style: "max-height:180px;overflow:auto;margin:8px 0;background:#1e1e1e;padding:6px;border-radius:4px" }, rows),
    el("div", { class: "row" }, [el("label", { text: "Repeats" }), repeats]),
    el("div", { class: "row" }, [el("label", { text: "" }), el("label", {}, [seed, document.createTextNode(" Randomize seed each repeat")])]),
    el("div", { class: "row" }, [el("label", { text: "Priority" }), pri]),
    el("div", { class: "row" }, [el("label", { text: "Comfy server" }), server]),
    el("p", { text: "Non-active workflow tabs: best-effort via workflowManager; otherwise only the current graph is reliable.", style: "color:#888;font-size:11px;max-width:420px" }),
    el("div", { class: "actions" }, [
      btn("Cancel", () => ov.remove()),
      btn("Open Queue", () => window.open(rqUrl.value.replace(/\/$/, "") + "/", "_blank")),
      btn("Submit", async () => {
        localStorage.setItem(RQ_URL_KEY, rqUrl.value.replace(/\/$/, ""));
        localStorage.setItem("paai_rq_path", rqPath.value.trim());
        try { await jpost("/paai/prefs", { render_queue_path: rqPath.value.trim() }); } catch (e) {}
        if (!rqUrl.value.trim()) {
          try {
            const prefs = await jget("/paai/prefs");
            if (prefs && prefs.queue_url) rqUrl.value = prefs.queue_url;
          } catch (e) {}
          try {
            const disc = await jget("/paai/queue_url?queue_path=" + encodeURIComponent(rqPath.value.trim()));
            if (disc && disc.url) rqUrl.value = disc.url;
          } catch (e) {}
        }
        const picked = rows.map((r, i) => r.querySelector(".paai-cb").checked ? workflows[i] : null).filter(Boolean);
        if (!picked.length) return alert("Select at least one workflow.");
        const jobs = [];
        for (const w of picked) {
          let prompt;
          try { prompt = await w.getPrompt(); }
          catch (e) { alert("Failed to serialize " + w.title + ": " + e.message); return; }
          let showRoot = "";
          try {
            const prefs = await jget("/paai/prefs");
            showRoot = (prefs && prefs.root) || "";
          } catch (e) {}
          jobs.push({
            app: "comfyui", name: w.title, target: "workflow",
            repeats: parseInt(repeats.value, 10) || 1,
            priority: parseInt(pri.value, 10) || 50,
            frames: { start: 1001, end: 1001, step: 1 },
            resources: { cpu_cores: 1, gpu_index: null },
            output_path: showRoot || "",
            extra: {
              server_url: server.value.trim(), workflow: prompt,
              randomize_seed: !!seed.checked, show_root: showRoot,
            },
          });
        }
        try {
          const r = await fetch(rqUrl.value.replace(/\/$/, "") + "/api/jobs", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jobs }),
          });
          const data = await r.json();
          if (!r.ok) throw new Error(data.error || r.statusText);
          alert("Submitted " + (data.jobs || []).length + " job(s) to Render Queue.");
          ov.remove();
        } catch (e) {
          alert("PAAI Render Queue not running at " + (rqUrl.value || "http://127.0.0.1:8790") + ", start it with run_queue.bat\n\n" + e.message);
        }
      }, "primary"),
    ]),
  ]);
  ov.appendChild(dlg);
  document.body.appendChild(ov);
}

// expose for tests
if (window.__PAAI__) { window.__PAAI__.openSubmitQueue = openSubmitQueue; }
else { window.__PAAI__ = { openSubmitQueue }; }

// Expose for headless screenshot tests
window.__PAAI__ = { openRenderBrowser, ensureCSS, buildTree, openShowTool, openSubmitQueue };
