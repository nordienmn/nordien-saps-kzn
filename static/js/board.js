/* HQ operations board. The Provincial Commissioner and Head Office own the whole process.
   Built with textContent only. No names, numbers or photos exist in the data this page receives. */
(function () {
  "use strict";
  const { h, clear, icon, api, poll, fmtAge, fmtTime } = window.SAPS;
  const $ = (id) => document.getElementById(id);

  const TIP_STAGES = [["new", "At the desk"], ["verified", "Verified"], ["referred", "Referred to HQ"], ["acknowledged", "Acknowledged"], ["directed", "Directed"], ["closed", "Closed"]];
  const TIP_CHIP = { new: "new", verified: "accepted", referred: "escalated", acknowledged: "referred", directed: "referred", closed: "closed" };
  const STATUS_WORD = { new: "New", assigned: "Accepted", in_progress: "In progress", referred: "Referred", closed: "Closed" };
  const STATUS_CHIP = { new: "new", assigned: "accepted", in_progress: "accepted", referred: "referred", closed: "closed" };
  const GENDERS = [["female", "Female"], ["male", "Male"], ["other", "Other"], ["undisclosed", "Not given"]];

  const S = { feed: null, version: null, tab: "overview", stop: null, units: null, audit: null, map: null, layers: null };

  const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit" });
  const nowS = () => (S.feed ? S.feed.now : Date.now() / 1000);
  function dur(sec) {
    if (!sec) return "n/a";
    if (sec < 90) return Math.round(sec) + " s";
    if (sec < 5400) return Math.round(sec / 60) + " min";
    return (sec / 3600).toFixed(1) + " h";
  }
  function toast(msg, kind) {
    const el = h("div.toast", icon(kind === "error" ? "alert" : "check-circle"), h("span", { text: msg }));
    $("toasts").appendChild(el);
    setTimeout(() => { el.classList.add("toast--out"); setTimeout(() => el.remove(), 200); }, 3200);
  }

  // ------------------------------------------------------------------ sign in
  $("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("login-error"); err.hidden = true; $("login-btn").disabled = true;
    try { await api("/api/auth/login", { body: { role: "board", password: $("password").value } }); $("password").value = ""; await boot(); }
    catch (ex) { err.hidden = false; err.replaceChildren(icon("alert", "icon--sm"), document.createTextNode(ex.offline ? "No connection. Try again." : ex.message)); }
    finally { $("login-btn").disabled = false; }
  });
  $("logout").addEventListener("click", async () => { try { await api("/api/auth/logout", { body: {} }); } catch (e) { /* ignore */ } if (S.stop) S.stop(); location.reload(); });

  async function boot() {
    let me;
    try { me = await api("/api/auth/me"); } catch (e) { me = { role: null }; }
    if (me.role === "board") {
      $("login-view").hidden = true; $("board-view").hidden = false;
      document.title = "SAPS KZN HQ operations board (DEMO)";
      const m = /tab=(\w+)/.exec(location.hash); if (m) S.tab = m[1];
      if (!S.stop) S.stop = poll(refresh, 2500);
    } else {
      $("login-view").hidden = false; $("board-view").hidden = true;
      if (!me.login_board) { const err = $("login-error"); err.hidden = false; err.textContent = "The board login is not switched on for this demo."; }
    }
  }

  async function refresh() {
    const f = await api("/api/staff/feed" + (S.version !== null ? "?since=" + S.version : ""));
    if (f.unchanged) { if (S.feed) S.feed.now = f.now; $("updated").textContent = "Live · updated " + hhmm(f.now); return; }
    S.feed = f; S.version = f.version;
    $("updated").textContent = "Live · updated " + hhmm(f.now);
    renderAttention(); renderKpis(); renderTabs(); renderPanel();
  }

  // ------------------------------------------------------------------ needs HQ action
  function renderAttention() {
    const list = S.feed.attention || [];
    const ul = $("esc-list"); clear(ul);
    const box = $("esc");
    box.classList.toggle("escalations--clear", !list.length);
    $("esc-hint").textContent = list.length ? list.length + " need" + (list.length === 1 ? "s" : "") + " your decision" : "Nothing is waiting for you";
    list.slice(0, 6).forEach((a) => {
      const isTip = a.kind === "tip";
      ul.appendChild(h("li.escalation", { "data-new": a.type === "verified_referral" ? "true" : null },
        h("div", h("p.escalation__title", { text: a.label + (a.cluster_name ? ", " + a.cluster_name : "") }),
          h("p.escalation__meta", h("span.ref", { text: a.ref }), " · " + a.reason + " · " + fmtAge(a.since, nowS()) + " ago")),
        h("div.escalation__act",
          isTip && a.type === "verified_referral" ? h("button.btn.btn--primary", { type: "button", onclick: () => ackTip(a.id) }, icon("check"), "Acknowledge") : null,
          a.type !== "unanswered_call" ? h("button.btn.btn--secondary", { type: "button", onclick: () => directDlg(a.id, a.ref, a.label) }, icon("escalate"), "Direct") : null,
          isTip ? h("button.btn.btn--ghost", { type: "button", onclick: () => { setTab("tips"); } }, "Open") : null)));
    });
    $("tab-tips-n").textContent = (S.feed.stats.hq_referrals_waiting || 0);
    $("tab-tips-n").hidden = !S.feed.stats.hq_referrals_waiting;
  }

  // ------------------------------------------------------------------ KPIs
  function kpi(label, value, sub, cls) {
    return h("div.kpi" + (cls ? "." + cls : ""), h("p.kpi__label", { text: label }), h("p.kpi__value", value), h("p.kpi__sub", { text: sub || "" }));
  }
  function renderKpis() {
    const st = S.feed.stats, ins = S.feed.insights;
    const box = $("kpis"); clear(box);
    box.append(
      kpi("Received", String(st.received), st.tips_total + " anonymous tips included"),
      kpi("Open files", String(st.open), st.urgent_open + " urgent", st.urgent_open ? "kpi--alert" : ""),
      kpi("Calls answered in 30 s", h("span", String(ins.calls.within_30s_pct), h("small", { text: " %" })), "average wait " + dur(ins.calls.avg_wait_s)),
      kpi("Time to dispatch", h("span", dur(ins.response.avg_to_dispatch_s)), ins.response.deployments_7d + " deployments in 7 days"),
      kpi("Verified referrals waiting", String(st.hq_referrals_waiting), "from the desk's tip-off line", st.hq_referrals_waiting ? "kpi--alert" : ""),
      kpi("Tips unverified over 1 h", String(ins.tips.unverified_over_1h), "at the desk", ins.tips.unverified_over_1h ? "kpi--alert" : ""));
  }

  // ------------------------------------------------------------------ tabs
  function renderTabs() {
    document.querySelectorAll("#tabs [role=tab]").forEach((t) => { const on = t.dataset.tab === S.tab; t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1; });
  }
  function setTab(tab, focus) {
    S.tab = tab; renderTabs(); S.audit = null;
    try { history.replaceState(null, "", location.pathname + "#tab=" + tab); } catch (e) { /* ok */ }
    renderPanel();
    if (focus) document.querySelector(`#tabs [data-tab="${tab}"]`).focus();
  }
  document.querySelectorAll("#tabs [role=tab]").forEach((t) => t.addEventListener("click", () => setTab(t.dataset.tab)));
  $("tabs").addEventListener("keydown", (e) => {
    const order = Array.from(document.querySelectorAll("#tabs [role=tab]")).map((t) => t.dataset.tab), i = order.indexOf(S.tab);
    if (e.key === "ArrowRight") { e.preventDefault(); setTab(order[(i + 1) % order.length], true); }
    if (e.key === "ArrowLeft") { e.preventDefault(); setTab(order[(i + order.length - 1) % order.length], true); }
  });

  function renderPanel() {
    const p = $("panel");
    if (S.map && S.tab !== "overview" && S.tab !== "deploy") { try { S.map.remove(); } catch (e) { /* ok */ } S.map = null; }
    const fn = { overview, tips, deploy, people, refs, perf, audit, brief }[S.tab] || overview;
    const keepY = window.scrollY;
    clear(p);
    fn(p);
    window.scrollTo(0, keepY);
  }

  // ------------------------------------------------------------------ small chart helpers
  function card(title, extra, ...body) { return h("section.card", h("div.card__head", h("h2.card__title", { text: title }), extra || null), ...body); }
  function bars(rows, opt) {
    opt = opt || {};
    const max = Math.max(1, ...rows.map((r) => (typeof r.value === "number" ? r.value : 0)));
    return h("ul.bars", ...rows.map((r) => {
      const n = typeof r.value === "number" ? r.value : 0;
      return h("li", h("span.bars__label", { text: r.label }),
        h("span.bars__track", h("span.bars__fill" + (r.cls ? "." + r.cls : ""), { style: "width:" + Math.round((n / max) * 100) + "%" }),
          r.ghost ? h("span.bars__ghost", { style: "left:" + Math.min(99, Math.round((r.ghost / max) * 100)) + "%", title: "Previous 7 days: " + r.ghost }) : null),
        h("span.bars__n", { text: r.text !== undefined ? String(r.text) : String(r.value) }));
    }));
  }
  function cols(values, labels, peak) {
    const max = Math.max(1, ...values);
    return h("div", h("div.cols", ...values.map((v, i) => h("span.cols__col", { title: labels[i] + ": " + v }, h("span.cols__bar" + (i === peak ? ".cols__bar--peak" : ""), { style: "height:" + Math.round((v / max) * 100) + "%" })))),
      h("div.cols__lbl", h("span", { text: labels[0] }), h("span", { text: labels[Math.floor(labels.length / 2)] }), h("span", { text: labels[labels.length - 1] })));
  }
  function matrix(headers, rows) {
    const cell = (v) => (v === "<5" ? h("td.small", { text: "<5", title: "Fewer than 5. Not shown." }) : h("td", { text: String(v) }));
    return h("div.table-wrap", h("table.matrix", h("thead", h("tr", ...headers.map((x) => h("th", { scope: "col", text: x })))),
      h("tbody", ...rows.map((r) => h("tr", h("th", { scope: "row", text: r[0] }), ...r.slice(1).map(cell))))));
  }
  const chipFor = (c) => h("span.chip.chip--dot.chip--" + (STATUS_CHIP[c.status] || "neutral"), { text: STATUS_WORD[c.status] || c.status });

  // ------------------------------------------------------------------ overview
  function overview(p) {
    const ins = S.feed.insights;
    p.appendChild(h("div.main-grid",
      h("section.card.map-card", h("div.card__head", { style: "margin:0" }, h("h2.card__title", { text: "Where callers and reporters are" }),
        h("span.chip-row", layerBtn("cases", "Cases"), layerBtn("stations", "Stations deployed"), layerBtn("clusters", "Cluster totals"))),
        h("div.map", { id: "mapbox" }, h("div.map__canvas#leaflet")),
        h("p.muted.text-sm", { text: "GBV, SOS and anonymous tips are never placed on the map. They appear only as banded totals per cluster (the small-number rule). Positions are rounded to about 100 m. Cluster centres and stations are approximate." })),
      h("section.card.feed", h("div.card__head", h("h2.card__title", { text: "Latest movement" }), h("span.chip.chip--neutral", { text: "No personal data" })),
        h("ul.feed__list", ...S.feed.cases.slice(0, 14).map((c) => h("li.feed-item", h("span.feed-item__time", { text: hhmm(c.created_at) }),
          h("div", h("div.feed-item__title", { text: c.label + ", " + c.cluster_name }),
            h("div.feed-item__meta", h("span.ref", { text: c.ref }), chipFor(c), c.restricted ? h("span.restricted", icon("lock"), "Restricted") : null, c.deployed ? h("span.chip.chip--info", { text: "Station deployed" }) : null))))))));
    p.appendChild(h("div.panel-grid.panel-grid--2", { style: "margin-top:var(--space-4)" },
      card("What this means", h("span.chip.chip--neutral", { text: "From the data" }), h("div", ...ins.signals.map((s) => h("div.signal.signal--" + s.level, icon(s.level === "good" ? "check-circle" : s.level === "attention" ? "alert" : "info"), h("p", { text: s.text }))))),
      card("Calls", h("span.chip.chip--neutral", { text: "The reason this app exists" }), callsCompare(ins))));
    setTimeout(() => drawMap(), 0);
  }

  function callsCompare(ins) {
    const c = ins.calls, ref = ins.reference_10111;
    return h("div.stack.stack--3",
      h("div.compare",
        h("div.compare__box", h("span.muted.text-sm", { text: "Answered within 30 seconds (this system)" }), h("b", { text: c.within_30s_pct + "%" }), h("span.text-sm", { text: c.answered + " answered, " + c.abandoned + " abandoned, average wait " + dur(c.avg_wait_s) })),
        h("div.compare__box", h("span.muted.text-sm", { text: "National 10111 average police response, as reported" }), h("b", { text: Math.round(ref.alpha_min) + " min" }), h("span.text-sm", { text: "Alpha complaints. Bravo " + Math.round(ref.bravo_min) + " min, Charlie " + Math.round(ref.charlie_min) + " min." }))),
      h("p.muted.text-sm", { text: ref.note + " Source: written parliamentary reply, as of " + ref.as_of + " (Parliamentary Monitoring Group). These are different measures and are shown side by side for context only." }));
  }

  // ---- map
  let leafletP = null;
  function loadLeaflet() {
    if (window.L) return Promise.resolve();
    if (leafletP) return leafletP;
    leafletP = new Promise((res, rej) => {
      document.head.appendChild(h("link", { rel: "stylesheet", href: "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css", integrity: "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=", crossorigin: "" }));
      const s = h("script", { src: "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js", integrity: "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=", crossorigin: "" });
      s.onload = res; s.onerror = () => { leafletP = null; rej(new Error("map")); }; document.head.appendChild(s);
    });
    return leafletP;
  }
  const layerOn = { cases: true, stations: true, clusters: false };
  function layerBtn(key, label) {
    return h("button.btn.btn--secondary", { type: "button", "aria-pressed": String(layerOn[key]), dataset: { layer: key }, onclick: (e) => { layerOn[key] = !layerOn[key]; e.currentTarget.setAttribute("aria-pressed", String(layerOn[key])); drawLayers(); } }, label);
  }
  const PRIO_COLOUR = { critical: "#e3452e", high: "#e8892b", normal: "#e3b94f", low: "#8aa0c2" };
  async function drawMap() {
    const el = $("leaflet");
    if (!el) return;
    try { await loadLeaflet(); } catch (e) { el.appendChild(h("div.map__fallback", h("p.muted", { text: "The map could not load. Cluster totals are on the Performance tab." }))); return; }
    if (!$("leaflet")) return;
    if (S.map) { try { S.map.remove(); } catch (e) { /* ok */ } }
    S.map = L.map($("leaflet"), { zoomControl: true, scrollWheelZoom: false }).setView([-29.2, 30.9], 7);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "&copy; OpenStreetMap contributors" }).addTo(S.map);
    S.layers = { cases: L.layerGroup().addTo(S.map), stations: L.layerGroup().addTo(S.map), clusters: L.layerGroup().addTo(S.map) };
    drawLayers();
  }
  function drawLayers() {
    if (!S.map || !S.layers || !S.feed) return;
    const ins = S.feed.insights;
    Object.values(S.layers).forEach((g) => g.clearLayers());
    document.querySelectorAll("[data-layer]").forEach((b) => b.setAttribute("aria-pressed", String(layerOn[b.dataset.layer])));
    if (layerOn.cases) ins.points.forEach((pt) => L.circleMarker([pt.lat, pt.lon], { radius: pt.priority === "critical" ? 8 : 6, color: "#0a2347", weight: 1.5, fillColor: PRIO_COLOUR[pt.priority] || "#e3b94f", fillOpacity: 0.85 }).bindTooltip(pt.label + " · " + pt.cluster + " · " + pt.status).addTo(S.layers.cases));
    if (layerOn.stations) {
      const active = {};
      ins.deployments_active.forEach((d) => { active[d.station_key] = (active[d.station_key] || 0) + 1; });
      ins.stations.forEach((s) => { if (active[s.key]) L.circleMarker([s.lat, s.lon], { radius: 9 + active[s.key] * 2, color: "#e3b94f", weight: 2.5, fillColor: "#0a2347", fillOpacity: 0.9 }).bindTooltip(s.name + ": " + active[s.key] + " unit(s) out").addTo(S.layers.stations); });
    }
    if (layerOn.clusters) {
      const cl = S.feed.clusters;
      ins.stations.forEach((s) => { /* cluster centre markers use the cluster table below */ });
      Object.entries(cl).forEach(([key, c]) => {
        const st = ins.stations.find((s) => s.cluster === key);
        if (!st || !c.received) return;
        const band = ins.restricted_by_cluster[key];
        L.circleMarker([st.lat, st.lon], { radius: 10 + Math.min(18, c.received), color: "#ffffff", weight: 1, fillColor: "#8aa0c2", fillOpacity: 0.35 }).bindTooltip(c.name + ": " + (c.received < 5 ? "<5" : c.received) + " files · GBV and tips " + band).addTo(S.layers.clusters);
      });
    }
  }

  // ------------------------------------------------------------------ anonymous tips
  function tips(p) {
    const ins = S.feed.insights, pipe = ins.tips.pipeline;
    const referred = S.feed.tips.filter((t) => t.status === "referred");
    p.appendChild(h("div.stack.stack--4",
      h("div.banner.banner--restricted", icon("lock"), h("span", { text: "Anonymous tips carry no identity. HQ sees every tip as it arrives. The desk's tip-off line checks each one and refers only verified tips for HQ action. Opening a tip is written to the access log." })),
      h("div.pipeline", ...TIP_STAGES.map(([k, label]) => h("div.stage" + (k === "referred" && pipe[k] ? ".stage--alert" : ""), h("b", { text: String(pipe[k] || 0) }), h("span", { text: label })))),
      card("Verified referrals for HQ action", h("span.chip.chip--escalated", { text: referred.length + " waiting" }),
        referred.length ? tipTable(referred, true) : h("p.muted", { text: "No verified referral is waiting. Everything the desk has verified has been dealt with." })),
      card("All anonymous tips (oversight)", h("span.chip.chip--neutral", { text: ins.tips.total + " tips · verified " + ins.tips.verified_pct + "%" }),
        tipTable(S.feed.tips, false),
        h("p.muted.text-sm", { style: "margin-top:var(--space-3)", text: "Average time to verify at the desk: " + dur(ins.tips.avg_to_verify_s) + ". Average time for HQ to acknowledge a referral: " + dur(ins.tips.avg_hq_ack_s) + "." }))));
  }
  function tipTable(list, referredOnly) {
    return h("div.table-wrap", h("table.matrix", h("thead", h("tr", ...["Reference", "Type", "Cluster", "Age", "Status", "Desk check", ""].map((x) => h("th", { scope: "col", text: x })))),
      h("tbody", ...list.map((t) => h("tr",
        h("th", { scope: "row" }, h("span.ref", { text: t.ref })), h("td", { text: t.label }), h("td", { text: t.cluster_name }), h("td", { text: fmtAge(t.created_at, nowS()) }),
        h("td", h("span.chip.chip--dot.chip--" + TIP_CHIP[t.status], { text: (TIP_STAGES.find((s) => s[0] === t.status) || [0, t.status])[1] })),
        h("td", { text: t.verification ? (t.verification.result === "verified" ? "Verified by " + t.verification.by : "Not verified") : "Not yet checked" }),
        h("td", h("span.chip-row", { style: "justify-content:flex-end" },
          h("button.btn.btn--ghost", { type: "button", onclick: () => readTip(t.id) }, "Read"),
          t.status === "referred" ? h("button.btn.btn--primary", { type: "button", onclick: () => ackTip(t.id) }, "Acknowledge") : null,
          t.status !== "closed" ? h("button.btn.btn--secondary", { type: "button", onclick: () => directDlg(t.id, t.ref, t.label) }, "Direct") : null,
          t.status !== "closed" ? h("button.btn.btn--ghost", { type: "button", onclick: () => closeTipDlg(t) }, "Close") : null)))))));
  }

  async function ackTip(id) { try { await api(`/api/staff/tip/${id}/ack`, { body: {} }); toast("Acknowledged"); await refresh(); } catch (e) { toast(e.message, "error"); } }
  async function readTip(id) {
    try {
      const d = await api(`/api/staff/tip/${id}`);
      await ask({ title: d.ref + ": " + d.label, body: "", ok: "Close", noCancel: true, node: h("div.stack.stack--3",
        h("p.chip-row", h("span.chip.chip--neutral", { text: d.cluster_name }), h("span.restricted", icon("lock"), "Restricted record - access logged")),
        h("p", { text: d.note || "No description." }),
        h("ol.timeline.timeline--compact", ...d.timeline.map((e) => h("li.timeline__item.timeline__item--done", h("span.timeline__dot", icon("check")), h("span.timeline__time", { text: hhmm(e.at) }), h("span.timeline__title", { text: e.actor }), h("span.timeline__text", { text: e.text }))))) });
    } catch (e) { toast(e.message, "error"); }
  }
  async function closeTipDlg(t) {
    const v = await ask({ title: "Close " + t.ref, body: "The citizen can see the outcome if they check with their one-time code.", fields: [{ id: "outcome", type: "select", label: "Outcome", options: [{ value: "used", label: "The information was used" }, { value: "no_action", label: "Not enough to act on" }, { value: "duplicate", label: "Matched another tip" }, { value: "not_verified", label: "Could not be verified" }] }], ok: "Close tip" });
    if (v) { try { await api(`/api/staff/tip/${t.id}/close`, { body: v }); toast("Closed"); await refresh(); } catch (e) { toast(e.message, "error"); } }
  }

  // ------------------------------------------------------------------ direct a unit
  async function directDlg(id, ref, label) {
    if (!S.units) { try { S.units = (await api("/api/staff/units")).units; } catch (e) { return toast(e.message, "error"); } }
    const v = await ask({
      title: "Direct " + ref, body: "Send this to a SAPS unit with an instruction and a due time. The unit acknowledges and completes it. If it runs late it comes back to your list.",
      fields: [
        { id: "unit_id", type: "select", label: "Unit", options: S.units.map((u) => ({ value: u.id, label: u.name })) },
        { id: "instruction", type: "text", label: "Instruction", hint: "One clear sentence." },
        { id: "due_minutes", type: "select", label: "Due in", value: "60", options: [{ value: "30", label: "30 minutes" }, { value: "60", label: "1 hour" }, { value: "120", label: "2 hours" }, { value: "240", label: "4 hours" }, { value: "1440", label: "24 hours" }] },
      ], ok: "Send direction",
    });
    if (v) { try { await api("/api/staff/direct", { body: Object.assign({ target_id: id }, v) }); toast("Direction sent to the unit"); await refresh(); } catch (e) { toast(e.message, "error"); } }
  }

  // ------------------------------------------------------------------ deployments
  function deploy(p) {
    const ins = S.feed.insights, r = ins.response;
    p.appendChild(h("div.stack.stack--4",
      h("div.panel-grid.panel-grid--3",
        kpi("Units out now", String(r.active), "dispatched or on scene"), kpi("Average time to dispatch", dur(r.avg_to_dispatch_s), "from the report to a unit being sent"), kpi("Average time to arrive", dur(r.avg_to_arrival_s), "from dispatch to on scene")),
      h("div.main-grid",
        card("Stations out now", h("span.chip.chip--neutral", { text: ins.deployments_active.length + " units" }),
          ins.deployments_active.length ? h("div.table-wrap", h("table.matrix", h("thead", h("tr", ...["Station", "Unit", "Reference", "Where", "Status", "Out for"].map((x) => h("th", { scope: "col", text: x })))),
            h("tbody", ...ins.deployments_active.map((d) => h("tr", h("th", { scope: "row", text: d.station }), h("td", { text: d.unit }), h("td", h("span.ref", { text: d.case_ref })), h("td", { text: d.cluster_name }),
              h("td", h("span.chip.chip--dot.chip--" + (d.status === "on_scene" ? "accepted" : "new"), { text: d.status === "on_scene" ? "On scene" : "On the way" })), h("td", { text: fmtAge(d.since, nowS()) })))))) : h("p.muted", { text: "No unit is out right now." })),
        card("Where they are", null, h("div.map", { id: "mapbox" }, h("div.map__canvas#leaflet")))),
      h("div.panel-grid.panel-grid--2",
        card("Deployments by station, last 7 days", h("span.chip.chip--neutral", { text: "Average time to arrive shown at the right" }),
          bars(ins.deployments_by_station.slice(0, 12).map((s) => ({ label: s.station + " (" + s.cluster + ")", value: s.dispatched, text: s.dispatched + " · " + dur(s.avg_arrival_s) })))),
        card("Demand against deployment, last 7 days", h("span.chip.chip--neutral", { text: "Where is cover thin?" }),
          bars(ins.demand_vs_deployment.filter((c) => c.incidents).sort((a, b) => b.per_deployment - a.per_deployment).map((c) => ({ label: c.name, value: c.per_deployment, text: c.incidents + " in · " + c.deployments + " out", cls: c.per_deployment > 3 ? "bars__fill--alert" : "" }))),
          h("p.muted.text-sm", { style: "margin-top:var(--space-3)", text: "Bar length is incidents per deployment. A long bar means few units were sent for the number of reports." })))));
    setTimeout(() => { layerOn.cases = false; layerOn.stations = true; layerOn.clusters = true; drawMap(); }, 0);
  }

  // ------------------------------------------------------------------ crime and people
  function people(p) {
    const ins = S.feed.insights;
    const peak = ins.by_hour.indexOf(Math.max(...ins.by_hour));
    const total = (arr) => arr.reduce((a, x) => a + (typeof x.n === "number" ? x.n : 0), 0) || 1;
    p.appendChild(h("div.stack.stack--4",
      h("div.banner.banner--neutral", icon("users"), h("span", { text: "Gender and age are optional and self-described. They are counted in groups and never shown next to a name. A cell with fewer than 5 records shows as <5." })),
      h("div.panel-grid.panel-grid--2",
        card("Types of crime, last 7 days", h("span.chip.chip--neutral", { text: "Marker = previous 7 days" }),
          bars(ins.by_type.map((t) => ({ label: t.label + (t.restricted ? " (restricted)" : ""), value: typeof t.this_week === "number" ? t.this_week : 0, text: t.this_week, ghost: typeof t.last_week === "number" ? t.last_week : 0, cls: t.restricted ? "bars__fill--accent" : "" })))),
        card("When reports come in", null, h("p.label-caps", { text: "By hour of day" }), cols(ins.by_hour, Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0") + ":00"), peak),
          h("p.label-caps", { style: "margin-top:var(--space-4)", text: "By day of week" }), cols(ins.by_weekday, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], ins.by_weekday.indexOf(Math.max(...ins.by_weekday))))),
      h("div.panel-grid.panel-grid--2",
        card("Gender", null, bars(ins.gender.map((g) => ({ label: g.label, value: typeof g.n === "number" ? g.n : 0, text: g.n === "<5" ? "<5" : Math.round(100 * g.n / total(ins.gender)) + "% (" + g.n + ")" })))),
        card("Age group", null, bars(ins.age.map((g) => ({ label: g.label, value: typeof g.n === "number" ? g.n : 0, text: g.n === "<5" ? "<5" : Math.round(100 * g.n / total(ins.age)) + "% (" + g.n + ")", cls: "bars__fill--accent" }))))),
      h("div.panel-grid.panel-grid--2",
        card("Crime type by gender", null, matrix(["Type", "Female", "Male", "Other", "Not given"], ins.crime_by_gender.map((r) => [r.label, r.female, r.male, r.other, r.undisclosed]))),
        card("Age group by gender", null, matrix(["Age group", "Female", "Male", "Other", "Not given"], ins.age_by_gender.map((r) => [r.label, r.female, r.male, r.other, r.undisclosed])))),
      h("div.panel-grid.panel-grid--3",
        card("How people reached us", null, bars(Object.entries(ins.channels).map(([k, v]) => ({ label: { app: "Citizen app", whatsapp: "WhatsApp", weather: "Discreet cover app", phone: "Phone" }[k] || k, value: v })))),
        card("Language", null, bars(Object.entries(ins.languages).map(([k, v]) => ({ label: k === "zu" ? "isiZulu" : "English", value: v })))),
        card("Last 14 days", null, cols(ins.trend.map((d) => d.call + d.crime + d.gbv + d.sos + d.area + d.tip), ins.trend.map((d) => d.day))))));
  }

  // ------------------------------------------------------------------ referrals and directions
  function refs(p) {
    const r = S.feed.insights.referrals;
    p.appendChild(h("div.stack.stack--4",
      h("div.banner.banner--neutral", icon("referral"), h("span", { text: "A referral goes OUT of SAPS to another body (Thuthuzela Care Centres belong to the NPA, shelters and clinics to others, municipalities are a separate sphere). A direction goes DOWN to a SAPS unit and HQ owns it until it is complete." })),
      h("div.panel-grid.panel-grid--3",
        kpi("Referrals out of SAPS", String(r.out), r.completed_pct + "% completed"), kpi("Average time to acknowledge", dur(r.avg_to_acknowledge_s), "partner acknowledged the referral"),
        kpi("Your directions", String(r.directions), r.directions_overdue + " overdue", r.directions_overdue ? "kpi--alert" : "")),
      h("div.panel-grid.panel-grid--2",
        card("Referrals by who they went to", null, bars(Object.entries(r.by_type).map(([k, v]) => ({ label: k, value: v })))),
        card("Referral status", null, bars(Object.entries(r.by_status).map(([k, v]) => ({ label: { sent: "Sent, not yet acknowledged", acknowledged: "Acknowledged", completed: "Completed" }[k] || k, value: v, cls: k === "completed" ? "" : "bars__fill--accent" }))))),
      card("Directions you have given", null, S.feed.directions.length ? h("div.table-wrap", h("table.matrix", h("thead", h("tr", ...["Reference", "Unit", "Instruction", "Given", "Due", "Status"].map((x) => h("th", { scope: "col", text: x })))),
        h("tbody", ...S.feed.directions.map((d) => { const late = d.status !== "completed" && d.due_at && nowS() > d.due_at; return h("tr", h("th", { scope: "row" }, h("span.ref", { text: d.case_ref })), h("td", { text: d.partner_name }), h("td", { text: d.instruction }), h("td", { text: hhmm(d.created_at) }), h("td", { text: hhmm(d.due_at) }),
          h("td", h("span.chip.chip--dot.chip--" + (late ? "danger" : d.status === "completed" ? "closed" : d.status === "acknowledged" ? "accepted" : "referred"), { text: late ? "Overdue" : d.status }))); })))) : h("p.muted", { text: "You have not directed anything yet. Use Direct on a tip or a file." }))));
  }

  // ------------------------------------------------------------------ performance
  function perf(p) {
    const ins = S.feed.insights, cl = Object.values(S.feed.clusters);
    p.appendChild(h("div.stack.stack--4",
      card("Clusters: what each commander answers for", h("span.chip.chip--neutral", { text: "10 demo clusters" }),
        h("div.table-wrap", h("table.matrix", h("thead", h("tr", ...["Cluster", "Files", "Open", "Closed", "First response", "Past limit"].map((x) => h("th", { scope: "col", text: x })))),
          h("tbody", ...cl.sort((a, b) => b.received - a.received).map((c) => h("tr", h("th", { scope: "row", text: c.name }), h("td", { text: c.received < 5 && c.received > 0 ? "<5" : String(c.received) }), h("td", { text: String(c.open) }), h("td", { text: c.closed_pct + "%" }), h("td", { text: dur(c.avg_first_response_s) }), h("td", { text: String(c.past_limit) })))))),
        h("p.muted.text-sm", { style: "margin-top:var(--space-3)", text: "The demo groups stations into 10 clusters. KwaZulu-Natal has about 184 police stations in a larger number of clusters, so treat this as an illustration of the view, not as the official structure." })),
      card("The anonymous tip pipeline", null, bars(Object.entries(ins.tips.pipeline).map(([k, v]) => ({ label: (TIP_STAGES.find((s) => s[0] === k) || [0, k])[1], value: v })))),
      card("Calls", null, callsCompare(ins))));
  }

  // ------------------------------------------------------------------ access log
  async function audit(p) {
    p.appendChild(card("Who opened what", h("span.chip.chip--restricted", { text: "Restricted records are logged" }), h("div#audit-body", h("div.state", h("span.spinner"), h("p.state__text", { text: "Loading the log" })))));
    try {
      const a = await api("/api/staff/audit");
      const body = $("audit-body"); if (!body) return;
      clear(body);
      body.appendChild(h("p.muted.text-sm", { text: "Every time a GBV, SOS or tip record is opened, and every action that changes a file, is written here with the officer ID and the time. This is what an oversight body would ask to see." }));
      body.appendChild(h("div.table-wrap", h("table.matrix", h("thead", h("tr", ...["Time", "Who", "Role", "Action", "Record", "Detail"].map((x) => h("th", { scope: "col", text: x })))),
        h("tbody", ...a.audit.slice(0, 120).map((r) => h("tr", h("td", { text: fmtTime(r.at) }), h("td", { text: r.actor }), h("td", { text: r.role }), h("td", { text: r.action }), h("td", h("span.ref", { text: r.target || "" })), h("td", { text: r.detail || "" })))))));
    } catch (e) { const body = $("audit-body"); if (body) { clear(body); body.appendChild(h("p.error-line", { text: e.message })); } }
  }

  // ------------------------------------------------------------------ daily brief
  function brief(p) {
    const st = S.feed.stats, ins = S.feed.insights, att = S.feed.attention;
    const topType = ins.by_type.filter((t) => !t.restricted)[0];
    p.appendChild(h("div.brief",
      h("div.cluster.cluster--between", h("h2", { text: "Daily brief for Head Office" }), h("button.btn.btn--secondary", { type: "button", onclick: () => window.print() }, icon("download"), "Print or save as PDF")),
      h("p.muted", { text: "Province: KwaZulu-Natal. Prepared " + new Date().toLocaleString("en-ZA") + ". All figures in this demo are synthetic." }),
      h("h3", { text: "The picture" }),
      h("ul", h("li", { text: st.received + " reports and tips received; " + st.open + " files open, " + st.urgent_open + " of them urgent." }),
        h("li", { text: ins.calls.total + " calls: " + ins.calls.within_30s_pct + "% answered within 30 seconds, average wait " + dur(ins.calls.avg_wait_s) + "." }),
        h("li", { text: ins.response.deployments_7d + " deployments in 7 days; average " + dur(ins.response.avg_to_dispatch_s) + " to dispatch and " + dur(ins.response.avg_to_arrival_s) + " to arrive." }),
        topType ? h("li", { text: "Most reported crime this week: " + topType.label + " (" + topType.this_week + ")." }) : null,
        h("li", { text: "Referrals out of SAPS: " + ins.referrals.out + " (" + ins.referrals.completed_pct + "% completed). Directions given: " + ins.referrals.directions + ", " + ins.referrals.directions_overdue + " overdue." })),
      h("h3", { text: "Anonymous tips" }),
      h("ul", h("li", { text: ins.tips.total + " tips received. " + ins.tips.pipeline.referred + " verified referral(s) waiting for HQ action; " + ins.tips.unverified_over_1h + " unverified at the desk for over an hour." }),
        h("li", { text: "Average time for the desk to verify: " + dur(ins.tips.avg_to_verify_s) + "." })),
      h("h3", { text: "Needs a decision" }),
      att.length ? h("ul", ...att.slice(0, 8).map((a) => h("li", { text: a.ref + ": " + a.reason }))) : h("p", { text: "Nothing is waiting." }),
      h("h3", { text: "What the data suggests" }),
      h("ul", ...ins.signals.map((s) => h("li", { text: s.text }))),
      h("p.muted.text-sm", { text: "Restricted records (GBV, SOS, anonymous tips) are reported as groups only. Fewer than 5 is shown as <5." })));
  }

  // ------------------------------------------------------------------ dialog
  const dlg = $("act-dlg");
  function ask({ title, body, fields, ok, node, noCancel }) {
    return new Promise((resolve) => {
      $("act-title").textContent = title; $("act-body").textContent = body || ""; $("act-ok").textContent = ok || "Confirm"; $("act-error").hidden = true;
      $("act-cancel").hidden = !!noCancel;
      const box = $("act-fields"); clear(box); box.className = "dlg-fields";
      if (node) box.appendChild(node);
      (fields || []).forEach((f) => {
        let control;
        if (f.type === "select") control = h("select.select", { id: "af-" + f.id }, ...f.options.map((o) => h("option", { value: o.value, selected: o.value === f.value ? true : null, text: o.label })));
        else control = h("input.input", { id: "af-" + f.id, type: "text", maxlength: "300" });
        box.appendChild(h("div.field", h("label.field__label", { for: "af-" + f.id, text: f.label }), control, f.hint ? h("p.field__hint", { text: f.hint }) : null));
      });
      const finish = (v) => { dlg.removeEventListener("close", onClose); $("act-form").onsubmit = null; $("act-cancel").onclick = null; resolve(v); };
      const onClose = () => finish(null);
      dlg.addEventListener("close", onClose);
      $("act-cancel").onclick = () => dlg.close();
      $("act-form").onsubmit = (e) => { e.preventDefault(); const vals = {}; (fields || []).forEach((f) => { vals[f.id] = $("af-" + f.id).value; }); dlg.removeEventListener("close", onClose); dlg.close(); finish(noCancel ? {} : vals); };
      dlg.showModal();
    });
  }

  $("reset-demo").addEventListener("click", async () => {
    const v = await ask({ title: "Reset the demo", body: "This puts the demo back to its starting data. Everything entered since is removed. Use it before a showing.", fields: [], ok: "Reset now" });
    if (v) { try { await api("/api/admin/reset", { body: {} }); S.version = null; toast("Demo reset"); await refresh(); } catch (e) { toast(e.message, "error"); } }
  });

  boot();
})();
