// DocAudit — interfața locală. Fără biblioteci externe; tot conținutul paginilor
// se pune în pagină ca text (textContent), niciodată ca HTML.
"use strict";

const TOKEN = document.querySelector('meta[name="docaudit-token"]').content;
const S = { info: null, texts: {}, lang: "ro", ds: null, state: null, tab: "groups", group: null,
            focus: 0, filter: "all", pages: {}, tree: null, plan: null };

// ---------- ajutoare ----------
function t(key, params) {
  let s = S.texts[key] || key;
  if (params) {
    s = s.replace(/\{(\w+)(?::[^}]*)?\}/g, (m, k) => {
      if (!(k in params)) return m;
      const v = params[k];
      if (m.includes(":.0%")) return Math.round(v * 100) + "%";
      if (m.includes(":.2f")) return Number(v).toFixed(2);
      return v;
    });
  }
  return s;
}

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v === null || v === undefined) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

async function api(path, body) {
  const opts = { headers: { "X-DocAudit-Token": TOKEN } };
  if (body !== undefined) {
    opts.method = "POST";
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(t(data.error || "ui.error.internal", data.params || {}));
  return data;
}

function q(params) {
  return "?" + new URLSearchParams(params).toString();
}

let toastTimer = null;
function toast(msg, err) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "toast" + (err ? " err" : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, err ? 7000 : 3500);
}

async function guard(fn) {
  try { return await fn(); } catch (e) { toast(e.message, true); }
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleDateString(S.lang, { year: "numeric", month: "short", day: "numeric" });
}

// ---------- pornire ----------
const TABS = ["source", "analysis", "groups", "apply", "journal", "settings"];

async function boot() {
  S.info = await api("/api/info");
  S.lang = S.info.settings.lang;
  S.texts = await api("/api/texts" + q({ lang: S.lang }));
  try { const th = localStorage.getItem("docaudit-theme"); if (th) document.documentElement.dataset.theme = th; } catch (e) {}
  const ds = S.info.datasets;
  S.ds = ds.length ? ds[0].name : null;
  S.tab = !ds.length ? "source" : (ds[0].compared ? "groups" : "analysis");
  renderChrome();
  await openTab(S.tab);
  document.addEventListener("keydown", onKey);
}

function renderChrome() {
  document.documentElement.lang = S.lang;
  document.querySelectorAll("[data-t]").forEach(el => { el.textContent = t(el.dataset.t); });
  const nav = document.getElementById("tabs");
  nav.replaceChildren(...TABS.map(tab => h("button", {
    type: "button", "aria-current": S.tab === tab ? "page" : false, text: t("ui.tab." + tab),
    onclick: () => openTab(tab),
  })));
  const sel = document.getElementById("dataset");
  sel.replaceChildren(...S.info.datasets.map(d => h("option", { value: d.name, selected: d.name === S.ds },
    `${d.name} · ${t("ui.pages", { count: d.pages })}`)));
  if (!S.info.datasets.length) sel.append(h("option", { value: "", text: t("ui.nodata") }));
  sel.onchange = () => { S.ds = sel.value; S.state = null; S.group = null; S.pages = {}; openTab(S.tab); };
  const lang = document.getElementById("lang");
  lang.replaceChildren(...S.info.languages.map(l => h("option", { value: l, selected: l === S.lang }, l.toUpperCase())));
  lang.onchange = () => guard(async () => {
    await api("/api/settings", { lang: lang.value });
    S.lang = lang.value;
    S.texts = await api("/api/texts" + q({ lang: S.lang }));
    S.info = await api("/api/info");
    renderChrome();
    await openTab(S.tab);
  });
  document.getElementById("theme").onclick = () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("docaudit-theme", root.dataset.theme); } catch (e) {}
  };
  const banner = document.getElementById("banner");
  banner.hidden = !S.info.settings.write_enabled;
  banner.textContent = t("ui.banner.write");
}

async function openTab(tab) {
  S.tab = tab;
  document.querySelectorAll("#tabs button").forEach((b, i) => {
    if (TABS[i] === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  const view = document.getElementById("view");
  view.replaceChildren(h("div", { class: "empty", text: t("ui.loading") }));
  await guard(async () => {
    const render = { source: viewSource, analysis: viewAnalysis, groups: viewGroups, apply: viewApply,
                     journal: viewJournal, settings: viewSettings }[tab];
    view.replaceChildren(await render());
  });
}

async function reloadInfo() {
  S.info = await api("/api/info");
  renderChrome();
}

async function loadState() {
  if (!S.ds) return null;
  S.state = await api("/api/state" + q({ ds: S.ds, lang: S.lang }));
  return S.state;
}

function needData() {
  return h("div", { class: "card empty" }, t("ui.nodata.long"), " ",
           h("button", { class: "primary", onclick: () => openTab("source"), text: t("ui.tab.source") }));
}

// ---------- 1. Sursă ----------
async function viewSource() {
  const demo = h("input", { type: "checkbox", id: "demo" });
  const name = h("input", { type: "text", value: S.ds || "onenote", size: 16 });
  const profile = h("input", { type: "text", placeholder: t("ui.source.profile.placeholder"), size: 16 });
  const full = h("input", { type: "checkbox" });
  const treeBox = h("div", { class: "tree" });
  const out = h("div", { class: "muted" });
  demo.onchange = () => { if (demo.checked && name.value === "onenote") name.value = "demo"; };

  const link = h("input", { type: "text", placeholder: t("ui.source.link.placeholder"), size: 48 });
  const linkOut = h("div", { class: "small" });

  // Eroarea rămâne în pagină (nu doar câteva secunde într-un toast), cu ce e de verificat.
  async function loadTree() {
    treeBox.replaceChildren(h("p", { class: "muted", text: t("ui.loading") }));
    try {
      S.tree = await api("/api/tree" + q({ demo: demo.checked ? "1" : "0" }));
    } catch (e) {
      S.tree = null;
      treeBox.replaceChildren(h("div", { class: "notice err" },
        h("p", {}, h("strong", { text: t("ui.source.treefail") })), h("p", { text: e.message }),
        h("p", { class: "small", text: t("ui.source.treehelp") })));
      return false;
    }
    treeBox.replaceChildren(S.tree.notebooks.length ? renderTree(S.tree)
      : h("p", { class: "notice", text: t("ui.source.empty") }));
    return S.tree.notebooks.length > 0;
  }

  function tick(kind, value) {
    const cb = [...treeBox.querySelectorAll(`input[data-kind="${kind}"]`)].find(x => x.dataset.value === value);
    if (!cb) return false;
    if (!cb.checked) { cb.checked = true; cb.dispatchEvent(new Event("change")); }
    const det = cb.closest("details");
    if (det) det.open = true;
    cb.scrollIntoView({ block: "center" });
    return true;
  }

  async function findLink() {
    linkOut.replaceChildren(h("span", { class: "muted", text: t("ui.loading") }));
    let r;
    try {
      r = await api("/api/link", { link: link.value, demo: demo.checked });
    } catch (e) {
      linkOut.replaceChildren(h("p", { class: "notice err", text: e.message }));
      return;
    }
    if (r.found) {
      await loadTree(); // arborele proaspăt, apoi bifa
      const bySection = r.section && tick("sections", r.section);
      if (!bySection) tick("notebooks", r.notebook);
      linkOut.replaceChildren(h("span", { text: t("ui.source.link.found", { name: bySection ? r.section : r.notebook }) }));
      return;
    }
    linkOut.replaceChildren(h("p", { class: "notice", text: t("ui.source.link.missing") }),
      r.open_url ? h("a", { href: r.open_url, class: "button", text: t("ui.source.link.open") })
                 : h("p", { class: "muted", text: t("ui.source.link.openweb") }));
  }

  async function extract() {
    const picked = { notebooks: [], sections: [], pages: [] };
    treeBox.querySelectorAll("input[data-kind]:checked").forEach(cb => {
      const parent = cb.closest("li").parentElement.closest("li");
      const parentBox = parent && parent.querySelector("input[data-kind]");
      if (parentBox && parentBox !== cb && parentBox.checked) return; // inclus prin părinte
      picked[cb.dataset.kind].push(cb.dataset.value);
    });
    out.textContent = t("ui.source.running");
    await guard(async () => {
      const r = await api("/api/extract", { demo: demo.checked, out: name.value, profile: profile.value || null,
                                            full: full.checked, ...picked });
      out.textContent = t("ui.source.done", r) + (r.errors.length ? " · " + r.errors.join("; ") : "");
      S.ds = r.name; S.state = null; S.pages = {};
      await reloadInfo();
      toast(t("ui.source.next"));
    });
  }

  const list = S.info.datasets.length ? h("table", {},
    h("tr", {}, ["ui.col.name", "ui.col.pages", "ui.col.extracted", "ui.col.status"].map(k => h("th", { text: t(k) }))),
    S.info.datasets.map(d => h("tr", {},
      h("td", {}, h("button", { class: "ghost", onclick: () => { S.ds = d.name; S.state = null; renderChrome(); openTab(d.compared ? "groups" : "analysis"); }, text: d.name })),
      h("td", { text: d.pages }), h("td", { text: fmtDate(d.extracted_at) }),
      h("td", { text: d.compared ? t("ui.status.compared") : d.grouped ? t("ui.status.grouped") : t("ui.status.extracted") }))))
    : h("p", { class: "muted", text: t("ui.nodata.long") });

  return h("div", { class: "stack" },
    h("div", { class: "card stack" }, h("h1", { text: t("ui.source.title") }), h("p", { class: "muted", text: t("ui.source.help") }),
      h("div", { class: "row" },
        h("label", {}, demo, " ", t("ui.source.demo")),
        h("button", { onclick: loadTree, text: t("ui.source.tree") })),
      treeBox,
      h("div", { class: "stack" },
        h("div", { class: "row" },
          h("label", {}, t("ui.source.link"), " ", link),
          h("button", { onclick: findLink, text: t("ui.source.link.find") })),
        h("p", { class: "small muted", text: t("ui.source.link.help") }),
        linkOut),
      h("div", { class: "row" },
        h("label", {}, t("ui.source.name"), " ", name),
        h("label", {}, t("ui.source.profile"), " ", profile),
        h("label", {}, full, " ", t("ui.source.full")),
        h("button", { class: "primary", onclick: extract, text: t("ui.source.extract") })),
      h("p", { class: "small muted", text: t("ui.source.where", { path: S.info.data_dir }) }),
      out),
    h("div", { class: "card" }, h("h2", { text: t("ui.source.datasets") }), list));
}

function renderTree(tree) {
  const archive = (S.info.settings.exclude_sections || []).map(s => s.toLowerCase());
  const box = (kind, value, label, checked) => {
    const cb = h("input", { type: "checkbox", "data-kind": kind, "data-value": value, checked });
    cb.addEventListener("change", () => {
      cb.closest("li").querySelectorAll("input[data-kind]").forEach(x => { x.checked = cb.checked; });
    });
    return h("label", {}, cb, " ", label);
  };
  return h("ul", {}, tree.notebooks.map(nb => h("li", {},
    box("notebooks", nb.name, h("strong", { text: nb.name }), false),
    h("ul", {}, nb.sections.map(s => {
      const excluded = archive.includes(s.path.split("/").pop().toLowerCase());
      return h("li", {}, h("details", {}, h("summary", {}, box("sections", `${nb.name}/${s.path}`,
          `${s.path} (${s.pages.length})${excluded ? " · " + t("ui.source.excluded") : ""}`, false)),
        h("ul", {}, s.pages.map(p => h("li", {}, box("pages", p.id, `${p.title} · ${fmtDate(p.modified)}`, false))))));
    })))));
}

// ---------- 2. Analiză ----------
async function viewAnalysis() {
  if (!S.ds) return needData();
  const st = S.info.settings;
  const current = S.info.datasets.find(d => d.name === S.ds) || {};
  const value = h("strong", { text: Number(st.threshold).toFixed(2) });
  const slider = h("input", { type: "range", min: "0.30", max: "0.95", step: "0.05", value: st.threshold });
  slider.oninput = () => { value.textContent = Number(slider.value).toFixed(2); };
  const semantic = h("input", { type: "checkbox", checked: st.semantic });
  const scanBox = h("div");
  const out = h("p", { class: "muted" });

  async function scan() {
    scanBox.replaceChildren(h("p", { class: "muted", text: t("ui.loading") }));
    await guard(async () => {
      const r = await api("/api/scan" + q({ ds: S.ds }));
      scanBox.replaceChildren(h("table", {},
        h("tr", {}, h("th", { text: t("ui.analysis.threshold") }), h("th", { text: t("ui.col.groups") }), h("th", { text: t("ui.analysis.grouped") })),
        r.rows.map(row => h("tr", { onclick: () => { slider.value = row.threshold; slider.oninput(); }, class: "clickable" },
          h("td", { text: row.threshold.toFixed(2) }), h("td", { text: row.groups }), h("td", { text: row.pages })))));
    });
  }

  async function run() {
    out.textContent = t("ui.analysis.running");
    await guard(async () => {
      await api("/api/settings", { threshold: Number(slider.value), semantic: semantic.checked });
      const r = await api("/api/analyze", { ds: S.ds, threshold: Number(slider.value), semantic: semantic.checked });
      out.textContent = t("ui.analysis.done", r);
      S.state = null; S.group = null;
      await reloadInfo();
      await openTab("groups");
    });
  }

  return h("div", { class: "card stack" },
    h("h1", { text: t("ui.analysis.title") }),
    h("p", { class: "muted", text: t("ui.analysis.help", { name: S.ds, pages: current.pages || 0 }) }),
    h("div", { class: "row" }, h("label", {}, t("ui.analysis.threshold"), " ", slider), value,
      h("button", { onclick: scan, text: t("ui.analysis.scan") })),
    h("p", { class: "small muted", text: t("ui.analysis.threshold.help") }),
    h("label", {}, semantic, " ", t("ui.analysis.semantic")),
    h("div", {}, h("button", { class: "primary", onclick: run, text: t("ui.analysis.run") })),
    out, scanBox);
}

// ---------- 3. Grupuri ----------
const FILTERS = {
  all: () => true,
  open: g => !g.resolved,
  value_conflict: g => g.findings.some(f => f.kind === "value_conflict" && !f.ignored),
  stale: g => g.findings.some(f => f.kind === "stale" && !f.ignored),
  duplicate: g => g.findings.some(f => f.kind === "duplicate" && !f.ignored),
};

async function viewGroups() {
  if (!S.ds) return needData();
  const st = await loadState();
  if (!st.compared) {
    return h("div", { class: "card empty" }, t("ui.groups.notyet"), " ",
             h("button", { class: "primary", onclick: () => openTab("analysis"), text: t("ui.tab.analysis") }));
  }
  if (!st.groups.length) return h("div", { class: "card empty", text: t("ui.groups.none") });
  const visible = st.groups.filter(FILTERS[S.filter]);
  if (!S.group || !st.groups.some(g => g.id === S.group)) S.group = (visible[0] || st.groups[0]).id;

  const list = h("div", { class: "card glist" },
    h("div", { class: "filters" }, Object.keys(FILTERS).map(f => h("button", {
      class: S.filter === f ? "on" : "", text: t("ui.filter." + f),
      onclick: () => { S.filter = f; openTab("groups"); } }))),
    visible.map(g => {
      const open = g.findings.filter(f => !f.ignored).length;
      return h("div", { class: `gitem${g.id === S.group ? " sel" : ""}${g.resolved ? " resolved" : ""}`, "data-id": g.id,
                        onclick: () => selectGroup(g.id) },
        h("span", { class: "dot " + (g.resolved ? "done" : g.severity) }),
        h("span", { class: "name", title: g.label, text: g.label }),
        h("span", { class: "small muted", text: `${g.pages.length} · ${open}` }));
    }),
    !visible.length ? h("p", { class: "muted small", text: t("ui.groups.nofilter") }) : null,
    h("p", { class: "small muted" }, t("ui.groups.keys"), " ",
      ...["J", "K", "1–9", "R", "O", "A", "I"].map(k => [h("span", { class: "kbd", text: k }), " "])));

  const detail = h("div", { id: "gdetail" });
  const wrap = h("div", { class: "stack" },
    h("div", { class: "row" },
      h("span", { class: "muted grow", text: t("ui.groups.summary", { groups: st.groups.length, pages: st.page_count,
        open: st.groups.filter(g => !g.resolved).length, ungrouped: st.ungrouped }) }),
      h("span", { class: "muted small", text: t("ui.report") }),
      ["html", "csv", "md"].map(f => h("a", { href: "/api/report" + q({ ds: S.ds, format: f, lang: S.lang, t: TOKEN }),
                                              class: "small", text: f.toUpperCase() }))),
    h("div", { class: "groups" }, list, detail));
  setTimeout(() => renderGroup(), 0);
  return wrap;
}

function selectGroup(id) {
  S.group = id; S.focus = 0;
  document.querySelectorAll(".gitem").forEach(el => el.classList.toggle("sel", el.dataset.id === id));
  renderGroup();
}

async function pageData(id) {
  if (!S.pages[id]) S.pages[id] = await api("/api/page" + q({ ds: S.ds, id }));
  return S.pages[id];
}

async function renderGroup() {
  const box = document.getElementById("gdetail");
  if (!box) return;
  const g = S.state.groups.find(x => x.id === S.group);
  if (!g) { box.replaceChildren(); return; }
  const pages = await Promise.all(g.pages.map(p => guard(() => pageData(p.id))));
  const staleIds = new Set(g.findings.filter(f => f.kind === "stale" && !f.ignored).map(f => f.pages[0]));
  const marks = {};  // pagină -> [ [fragment, e diferit?] ]
  for (const f of g.findings) {
    if (f.kind !== "value_conflict" || f.ignored) continue;
    for (const [pid, v] of Object.entries(f.details.values)) {
      if (v) (marks[pid] = marks[pid] || []).push([v, f.details.differing.includes(pid)]);
    }
  }

  const findings = h("ul", { class: "findings" }, g.findings.map(f => h("li", { class: f.ignored ? "ignored" : "" },
    h("span", { class: "badge sev-" + f.severity, text: t("ui.kind." + f.kind) }),
    h("span", { class: "txt", text: f.text }),
    f.ignored ? h("span", { class: "small muted", text: t("ui.ignored") })
      : h("button", { class: "ghost small", text: t("ui.ignore"),
                      onclick: () => decide(f.pages[0], "ignore", { finding: f.key }) }))));
  if (!g.findings.length) findings.append(h("li", { class: "muted", text: t("ui.groups.nofindings") }));

  const cols = g.pages.map((p, i) => {
    const data = pages[i] || { text: "", images: [] };
    const badges = [];
    if (g.reference === p.id) badges.push(h("span", { class: "badge b-ok", text: t("ui.badge.reference") }));
    if (staleIds.has(p.id)) badges.push(h("span", { class: "badge sev-medium", text: t("ui.badge.stale") }));
    if (g.other_language.includes(p.id)) badges.push(h("span", { class: "badge b-accent", text: t("ui.badge.language") }));
    if (p.decision) badges.push(h("span", { class: "badge b-accent", text: "✓ " + t("ui.action." + p.decision) }));
    const btn = (action, key) => h("button", { class: p.decision === action ? "on" : "", title: key ? `${key}` : "",
      text: t("ui.action." + action), onclick: () => decide(p.id, action) });
    return h("div", { class: "card pcol" + (i === S.focus ? " focus" : ""), "data-i": i, onclick: () => setFocus(i) },
      h("h3", { text: `${i + 1}. ${p.title}` }),
      h("div", { class: "meta", text: `${p.notebook} › ${p.section} · ${t("ui.modified")} ${fmtDate(p.modified)}` }),
      h("div", { class: "row" }, badges),
      h("div", { class: "actions" }, btn("reference", "R"), btn("mark_stale", "O"), btn("archive", "A"), btn("keep", "I"),
        h("button", { text: t("ui.action.not_in_group"), onclick: () => decide(p.id, "not_in_group") }),
        h("button", { text: t("ui.action.note"), onclick: () => {
          const note = prompt(t("ui.note.prompt"));
          if (note) decide(p.id, "note", { note });
        } }),
        p.decision_id ? h("button", { class: "ghost", text: t("ui.undo"), onclick: () => undo(p.decision_id) }) : null),
      p.notes.length ? h("div", { class: "small muted" }, "📝 ", p.notes.join(" · ")) : null,
      h("div", { class: "body" }, highlight(data.text, marks[p.id] || []),
        (data.images || []).map(img => h("img", { alt: img.alt || "", loading: "lazy",
          src: "/api/image" + q({ ds: S.ds, sha: img.sha256, t: TOKEN }) }))));
  });

  box.replaceChildren(h("div", { class: "card stack" },
    h("div", { class: "row" }, h("h1", { class: "grow", text: g.label }),
      h("span", { class: "badge sev-" + g.severity, text: t("ui.severity." + g.severity) })),
    findings), h("div", { class: "pages" }, cols));
}

function highlight(text, marks) {
  // fragmentele conflictului se evidențiază; textul rămâne text (fără HTML).
  // Se caută doar cuvinte întregi și nu în numărul pasului („4.” de la începutul rândului).
  const frag = document.createDocumentFragment();
  const parts = marks.filter(([v]) => v).sort((a, b) => b[0].length - a[0].length);
  if (!parts.length) { frag.append(text); return frag; }
  const isWord = c => !!c && /[\p{L}\p{N}]/u.test(c);
  const blocked = [];  // [început, sfârșit) pentru numerele de pas
  const re = /^\s*\d{1,3}[.)]\s/gm;
  let m;
  while ((m = re.exec(text))) blocked.push([m.index, m.index + m[0].length]);
  const ok = (at, len) => !isWord(text[at - 1]) && !isWord(text[at + len]) &&
    !blocked.some(([a, b]) => at < b && at + len > a);
  let i = 0;
  while (i < text.length) {
    let best = null;
    for (const [v, diff] of parts) {
      let at = text.indexOf(v, i);
      while (at !== -1 && !ok(at, v.length)) at = text.indexOf(v, at + 1);
      if (at !== -1 && (!best || at < best.at)) best = { at, v, diff };
    }
    if (!best) { frag.append(text.slice(i)); break; }
    frag.append(text.slice(i, best.at), h("mark", { class: best.diff ? "diff" : "", text: best.v }));
    i = best.at + best.v.length;
  }
  return frag;
}

function setFocus(i) {
  S.focus = i;
  document.querySelectorAll(".pcol").forEach(el => el.classList.toggle("focus", Number(el.dataset.i) === i));
}

async function decide(page, action, extra) {
  await guard(async () => {
    await api("/api/decision", { ds: S.ds, page, group: S.group, action, ...(extra || {}) });
    toast(t("ui.saved", { action: t("ui.action." + action) }));
    await loadState();
    if (action === "not_in_group") toast(t("ui.notingroup.help"));
    await renderGroup();
    refreshList();
  });
}

async function undo(id) {
  await guard(async () => {
    await api("/api/undo", { ds: S.ds, id });
    toast(t("ui.undone"));
    await loadState();
    if (S.tab === "groups") { await renderGroup(); refreshList(); } else await openTab(S.tab);
  });
}

function refreshList() {
  for (const g of S.state.groups) {
    const el = document.querySelector(`.gitem[data-id="${CSS.escape(g.id)}"]`);
    if (!el) continue;
    el.classList.toggle("resolved", g.resolved);
    el.querySelector(".dot").className = "dot " + (g.resolved ? "done" : g.severity);
    el.querySelector(".small").textContent = `${g.pages.length} · ${g.findings.filter(f => !f.ignored).length}`;
  }
}

function onKey(e) {
  if (S.tab !== "groups" || !S.state || e.ctrlKey || e.metaKey || e.altKey) return;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
  const items = [...document.querySelectorAll(".gitem")];
  const idx = items.findIndex(el => el.dataset.id === S.group);
  const g = S.state.groups.find(x => x.id === S.group);
  const key = e.key.toLowerCase();
  if (key === "j" || key === "k") {
    const next = items[Math.max(0, Math.min(items.length - 1, idx + (key === "j" ? 1 : -1)))];
    if (next) { selectGroup(next.dataset.id); next.scrollIntoView({ block: "nearest" }); }
  } else if (/^[1-9]$/.test(key) && g && Number(key) <= g.pages.length) {
    setFocus(Number(key) - 1);
  } else if (g && { r: 1, o: 1, a: 1, i: 1 }[key]) {
    const action = { r: "reference", o: "mark_stale", a: "archive", i: "keep" }[key];
    decide(g.pages[S.focus].id, action);
  } else return;
  e.preventDefault();
}

// ---------- 4. De aplicat ----------
async function viewApply() {
  if (!S.ds) return needData();
  const st = S.info.settings;
  const wrap = h("div", { class: "card stack" }, h("h1", { text: t("ui.apply.title") }),
    h("p", { class: "muted", text: t("ui.apply.help", { archive: st.archive_section, prefix: st.stale_prefix }) }));
  let plan;
  try { plan = await api("/api/plan" + q({ ds: S.ds })); } catch (e) {
    wrap.append(h("p", { class: "muted", text: e.message }));
    return wrap;
  }
  if (!plan.items.length) { wrap.append(h("p", { class: "muted", text: t("ui.apply.none") })); return wrap; }
  const checks = {};
  const rows = plan.items.map(it => {
    const cb = h("input", { type: "checkbox", checked: it.status === "ready", disabled: it.status !== "ready" });
    checks[it.decision_id] = cb;
    const what = it.action === "archive" ? t("ui.apply.move", { from: it.section, to: it.target })
                                         : t("ui.apply.rename", { title: it.target });
    return h("tr", {}, h("td", {}, cb), h("td", { text: it.title }), h("td", { text: `${it.notebook} › ${it.section}` }),
      h("td", { text: t("ui.action." + it.action) }), h("td", { text: what }),
      h("td", {}, it.status === "ready"
        ? h("span", { class: "badge b-ok", text: it.reason ? t("ui.apply.reason." + it.reason) : t("ui.apply.ready") })
        : h("span", { class: "badge sev-medium", text: t("ui.apply.reason." + it.reason) })),
      h("td", {}, h("button", { class: "ghost", text: t("ui.undo"), onclick: () => undo(it.decision_id) })));
  });
  const out = h("div");
  const button = h("button", { class: "danger", disabled: !plan.write_enabled, text: t("ui.apply.button") });
  button.onclick = () => guard(async () => {
    const ids = Object.entries(checks).filter(([, cb]) => cb.checked).map(([id]) => Number(id));
    if (!ids.length) return;
    if (!confirm(t("ui.apply.confirm", { count: ids.length }))) return;
    const r = await api("/api/apply", { ds: S.ds, ids, confirm: true });
    out.replaceChildren(h("p", { text: t("ui.apply.result", { done: r.done.length, skipped: r.skipped.length, errors: r.errors.length }) }),
      ...r.errors.map(e => h("p", { class: "small", text: `⚠ ${e.title}: ${e.error}` })));
    toast(t("ui.apply.result", { done: r.done.length, skipped: r.skipped.length, errors: r.errors.length }), r.errors.length > 0);
    setTimeout(() => openTab("apply"), 1500);
  });
  wrap.append(h("table", {}, h("tr", {}, ["", "ui.col.page", "ui.col.where", "ui.col.decision", "ui.col.preview", "ui.col.status", ""]
      .map(k => h("th", { text: k ? t(k) : "" }))), rows),
    plan.write_enabled ? h("p", { class: "small muted", text: t("ui.apply.safety") })
      : h("p", { class: "badge sev-medium", text: t("ui.apply.readonly") }),
    h("div", { class: "row" }, button, !plan.write_enabled
      ? h("button", { onclick: () => openTab("settings"), text: t("ui.tab.settings") }) : null), out);
  return wrap;
}

// ---------- 5. Jurnal și arhivă ----------
async function viewJournal() {
  if (!S.ds) return needData();
  const st = await loadState();
  const applied = (await api("/api/applied" + q({ ds: S.ds }))).items;
  const titles = {};
  st.groups.forEach(g => g.pages.forEach(p => { titles[p.id] = p.title; }));
  const writeOn = S.info.settings.write_enabled;
  const appliedTable = applied.length ? h("table", {},
    h("tr", {}, ["ui.col.when", "ui.col.who", "ui.col.page", "ui.col.decision", "ui.col.where", ""].map(k => h("th", { text: k ? t(k) : "" }))),
    applied.map(a => h("tr", {}, h("td", { text: fmtDate(a.applied_at) }), h("td", { text: a.user }), h("td", { text: a.title }),
      h("td", { text: t("ui.action." + a.action) }), h("td", { text: a.section }),
      h("td", {}, a.restored_at ? h("span", { class: "muted small", text: t("ui.journal.restored") })
        : h("button", { disabled: !writeOn, title: writeOn ? "" : t("ui.apply.readonly"), text: t("ui.journal.restore"),
            onclick: () => guard(async () => {
              if (!confirm(t("ui.journal.restore.confirm", { title: a.title }))) return;
              await api("/api/restore", { ds: S.ds, id: a.id });
              toast(t("ui.journal.restored"));
              await openTab("journal");
            }) })))))
    : h("p", { class: "muted", text: t("ui.journal.noapplied") });

  const hist = st.history.length ? h("table", {},
    h("tr", {}, ["ui.col.when", "ui.col.who", "ui.col.page", "ui.col.decision", "ui.col.note", "ui.col.status", ""].map(k => h("th", { text: k ? t(k) : "" }))),
    st.history.map(d => h("tr", { class: d.undone_at ? "muted" : "" },
      h("td", { text: fmtDate(d.created_at) }), h("td", { text: d.user }), h("td", { text: titles[d.page_id] || d.page_id }),
      h("td", { text: t("ui.action." + d.action) }), h("td", { text: d.note }),
      h("td", { text: d.applied_at ? t("ui.status.applied") : d.undone_at ? t("ui.status.undone") : t("ui.status.active") }),
      h("td", {}, !d.undone_at && !d.applied_at ? h("button", { class: "ghost", text: t("ui.undo"), onclick: () => undo(d.id) }) : null))))
    : h("p", { class: "muted", text: t("ui.journal.empty") });

  return h("div", { class: "stack" },
    h("div", { class: "card" }, h("h1", { text: t("ui.journal.applied") }), appliedTable),
    h("div", { class: "card" }, h("h1", { text: t("ui.journal.title") }), hist));
}

// ---------- 6. Setări ----------
async function viewSettings() {
  const st = S.info.settings;
  const f = {
    threshold: h("input", { type: "number", min: "0.3", max: "0.95", step: "0.05", value: st.threshold }),
    archive_section: h("input", { type: "text", value: st.archive_section }),
    stale_prefix: h("input", { type: "text", value: st.stale_prefix }),
    exclude_sections: h("input", { type: "text", value: (st.exclude_sections || []).join(", "), size: 40 }),
    port: h("input", { type: "number", min: "1024", max: "65535", value: st.port }),
    semantic: h("input", { type: "checkbox", checked: st.semantic }),
    write_enabled: h("input", { type: "checkbox", checked: st.write_enabled }),
  };
  const save = () => guard(async () => {
    if (f.write_enabled.checked && !st.write_enabled && !confirm(t("ui.settings.write.confirm"))) {
      f.write_enabled.checked = false;
      return;
    }
    await api("/api/settings", {
      threshold: Number(f.threshold.value), archive_section: f.archive_section.value.trim(),
      stale_prefix: f.stale_prefix.value, port: Number(f.port.value), semantic: f.semantic.checked,
      exclude_sections: f.exclude_sections.value.split(",").map(s => s.trim()).filter(Boolean),
      write_enabled: f.write_enabled.checked,
    });
    await reloadInfo();
    toast(t("ui.settings.saved"));
  });
  const row = (key, el, help) => h("tr", {}, h("th", { text: t("ui.settings." + key) }),
    h("td", {}, el, help ? h("div", { class: "small muted", text: t(help) }) : null));
  return h("div", { class: "card stack" }, h("h1", { text: t("ui.tab.settings") }),
    h("table", {},
      row("threshold", f.threshold, "ui.analysis.threshold.help"),
      row("semantic", f.semantic, "ui.analysis.semantic"),
      row("archive_section", f.archive_section),
      row("stale_prefix", f.stale_prefix),
      row("exclude_sections", f.exclude_sections, "ui.settings.exclude.help"),
      row("port", f.port, "ui.settings.port.help"),
      row("write_enabled", f.write_enabled, "ui.settings.write.help")),
    h("div", {}, h("button", { class: "primary", onclick: save, text: t("ui.settings.save") })),
    h("p", { class: "small muted", text: t("ui.settings.local", { path: S.info.data_dir, version: S.info.version }) }));
}

boot().catch(e => {
  document.getElementById("view").replaceChildren(h("div", { class: "card empty", text: String(e.message || e) }));
});
