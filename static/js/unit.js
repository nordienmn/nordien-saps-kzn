/* An action point's own page: a station, the Flying Squad, a unit, or a partner. Shows only the tasks sent to it.
   Reached by a private link (no account). Desk and board officers can open any of them. */
(function () {
  "use strict";
  const { h, clear, icon, api, poll, fmtAge, fmtTime } = window.SAPS;
  const $ = (id) => document.getElementById(id);
  const parts = location.pathname.split("/").filter(Boolean);
  const apId = parts[1] ? decodeURIComponent(parts[1]) : "";
  const token = new URLSearchParams(location.search).get("k") || "";
  const q = token ? "?k=" + encodeURIComponent(token) : "";

  const PRIO = { critical: "Critical", high: "High", normal: "Routine", low: "Low" };
  const NEXT = {
    deployment: { dispatched: ["Acknowledge", "acknowledged"], acknowledged: ["On scene", "on_scene"], on_scene: ["Cleared", "cleared"] },
    referral: { sent: ["Acknowledge", "acknowledged"], acknowledged: ["Complete", "completed"] },
  };
  const WORD = { dispatched: "Sent to you", acknowledged: "Acknowledged", on_scene: "On scene", cleared: "Cleared", sent: "Sent to you", completed: "Completed" };

  function toast(msg, bad) {
    const el = h("div.toast", icon(bad ? "alert" : "check-circle"), h("span", { text: msg }));
    $("toasts").appendChild(el);
    setTimeout(() => { el.classList.add("toast--out"); setTimeout(() => el.remove(), 200); }, 3000);
  }
  const dlg = $("note-dlg");
  function askNote(title) {
    return new Promise((resolve) => {
      $("note-title").textContent = title; $("note-in").value = "";
      const done = (v) => { dlg.removeEventListener("close", onClose); $("note-form").onsubmit = null; resolve(v); };
      const onClose = () => done(null);
      dlg.addEventListener("close", onClose);
      $("note-cancel").onclick = () => dlg.close();
      $("note-form").onsubmit = (e) => { e.preventDefault(); const v = $("note-in").value; dlg.removeEventListener("close", onClose); dlg.close(); done(v); };
      dlg.showModal(); $("note-in").focus();
    });
  }

  // ---------------------------------------------------------------- index (officers only)
  async function index() {
    $("sub").textContent = "Action points";
    clear($("unit-head")).append(h("h1", { text: "Action points" }), h("p.muted", { text: "Every place a file can be sent. Each has its own page and its own private link. In real life a station or unit would open its link on its own screen." }));
    let pts;
    try { pts = (await api("/api/staff/action-points")).points; } catch (e) {
      return clear($("unit-body")).append(h("div.banner.banner--neutral", icon("lock"), h("span", { text: "Sign in at the desk or the board to see all action points. A station opens its own page with its own link." }), h("a.btn.btn--secondary", { href: "/desk" }, "Control room desk")));
    }
    const groups = {};
    pts.forEach((p) => { (groups[p.group] = groups[p.group] || []).push(p); });
    const body = clear($("unit-body"));
    Object.entries(groups).forEach(([g, list]) => {
      body.appendChild(h("section.card", h("div.card__head", h("h2.card__title", { text: g }), h("span.chip.chip--neutral", { text: list.length + " points" })),
        h("ul.mini-list", ...list.map((p) => h("li", h("span", h("a", { href: p.url }, p.name), p.cluster ? " · " + p.cluster : ""),
          h("span.chip-row", p.load.open ? h("span.chip.chip--" + (p.load.urgent ? "danger" : "info"), { text: p.load.open + " open" }) : h("span.muted.text-sm", { text: "nothing waiting" })))))));
    });
  }

  // ---------------------------------------------------------------- one action point
  let last = "";
  async function load() {
    let data;
    try { data = await api(`/api/unit/${encodeURIComponent(apId)}/tasks${q}`); } catch (e) {
      clear($("unit-head")); clear($("unit-body")).append(h("div.state.state--error", h("span.state__icon", icon("lock", "icon--lg")), h("h1.state__title", { text: "This link is not valid" }), h("p.state__text", { text: "Ask the control room desk for this action point's link." })));
      return;
    }
    const sig = JSON.stringify(data.tasks.map((t) => [t.id, t.status])) + data.point.name;
    if (sig === last) { updateAges(); return; }
    last = sig;
    $("sub").textContent = data.point.name;
    document.title = data.point.name + " (DEMO)";
    const open = data.tasks.filter((t) => !t.closed).length;
    clear($("unit-head")).append(h("p.label-caps", { text: data.point.group }), h("h1", { text: data.point.name }),
      h("p.muted", { text: open ? open + " task" + (open === 1 ? "" : "s") + " waiting for you." : "Nothing is waiting for you." }));
    const body = clear($("unit-body"));
    if (!data.tasks.length) body.appendChild(h("div.state", h("span.state__icon", icon("inbox", "icon--lg")), h("h2.state__title", { text: "No tasks yet" }), h("p.state__text", { text: "When the control room sends a file here, it appears on this page by itself." })));
    data.tasks.forEach((t) => body.appendChild(taskCard(t)));
  }

  function taskCard(t) {
    const next = (NEXT[t.kind] || {})[t.status];
    const late = t.due_at && !t.closed && Date.now() / 1000 > t.due_at;
    return h("article.card.task" + (t.closed ? ".task--done" : ""),
      h("div.card__head", h("div", h("p.ref", { text: t.case_ref }), h("h2.card__title", { text: t.label + ", " + t.cluster })),
        h("span.chip-row", h("span.chip.chip--" + (t.priority === "critical" ? "danger" : t.priority === "high" ? "warning" : "neutral"), { text: PRIO[t.priority] || "Routine" }),
          h("span.chip.chip--dot.chip--" + (t.closed ? "closed" : t.status === "on_scene" || t.status === "acknowledged" ? "accepted" : "new"), { text: WORD[t.status] || t.status }),
          late ? h("span.chip.chip--danger", { text: "Overdue" }) : null)),
      t.instruction ? h("p.task__instr", { text: t.instruction }) : null,
      t.detail ? h("p", { text: t.detail }) : null,
      h("dl.kv", ...[
        ["Where", [t.address, t.cluster].filter(Boolean).join(", ") || "Not given"],
        t.lat !== null && t.lat !== undefined ? ["Map", h("a", { href: `https://www.openstreetmap.org/?mlat=${t.lat}&mlon=${t.lon}#map=17/${t.lat}/${t.lon}`, target: "_blank", rel: "noopener" }, "Open the location")] : null,
        t.unit ? ["Unit asked for", t.unit] : null,
        t.name ? ["Contact", t.name + (t.mobile ? ", " + t.mobile : "")] : (t.mobile ? ["Contact", t.mobile] : null),
        ["Sent", fmtTime(t.since) + " (" + fmtAge(t.since, Date.now() / 1000) + " ago)", "age"],
        t.due_at ? ["Due", fmtTime(t.due_at)] : null,
      ].filter(Boolean).flatMap((r) => [h("dt", { text: r[0] }), h("dd", r[1] instanceof Node ? r[1] : { text: r[1] })])),
      next ? h("div.action-bar", { style: "grid-template-columns:1fr" }, h("button.btn.btn--primary.btn--lg", { type: "button", onclick: () => advance(t, next) }, icon("check"), next[0])) : null);
  }
  function updateAges() { /* ages are shown at send time; a fresh poll rebuilds when anything changes */ }

  async function advance(t, next) {
    const note = await askNote(next[0] + ": " + t.case_ref);
    if (note === null) return;
    try { await api(`/api/unit/${encodeURIComponent(apId)}/task${q}`, { body: { task_kind: t.kind, task_id: t.id, status: next[1], note, k: token } }); toast(next[0] + " recorded"); last = ""; await load(); }
    catch (e) { toast(e.message, true); }
  }

  if (apId) poll(load, 3000); else index();
})();
