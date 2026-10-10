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

  function mmss(sec) { sec = Math.max(0, Math.floor(sec || 0)); return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0"); }
  function transcriptText(t) {
    const f = t.folder.call;
    const lines = ["SAPS KZN DEMO. CALL RECORD (synthetic demonstration data)", "Reference: " + t.case_ref, "Type: " + (f.mode === "video" ? "Video call" : "Voice call"),
      "Answered by: " + (f.operator || "n/a"), "Duration: " + (f.duration != null ? mmss(f.duration) : "n/a"), "-".repeat(60)];
    f.lines.forEach((l) => lines.push("[" + new Date(l.at * 1000).toLocaleTimeString("en-ZA") + "] " + (l.who === "citizen" ? "Caller" : "Officer") + " (" + l.src + "): " + l.text));
    return lines.join("\n") + "\n";
  }
  function folderBlock(t) {
    const f = t.folder;
    if (!f) return null;
    const media = (e) => {
      const src = `/api/unit/${encodeURIComponent(apId)}/media/${encodeURIComponent(e.id)}${q}`;
      if (e.type === "recording" || e.type === "video") return h("div", h("p.label-caps", { text: e.type === "recording" ? "Call recording" + (e.source === "caller" ? " (caller's phone)" : "") : "Video from the citizen" }), h("video", { controls: true, preload: "metadata", src, style: "width:100%;border-radius:var(--radius-md);background:#000" }));
      if (e.type === "audio") return h("div", h("p.label-caps", { text: "Audio from the citizen" }), h("audio", { controls: true, preload: "metadata", src, style: "width:100%" }));
      const slot = h("div");
      slot.appendChild(h("button.btn.btn--secondary", { type: "button", onclick: async (ev) => { ev.currentTarget.disabled = true; try { const r = await api(src); clear(slot); slot.appendChild(h("img", { src: r.data_url, alt: "Picture from the citizen", style: "max-width:100%;border-radius:var(--radius-md)" })); } catch (er) { toast(er.message, true); } } }, icon("image"), "Show picture"));
      return slot;
    };
    const parts = [];
    if (f.call) {
      parts.push(h("p.muted.text-sm", { text: (f.call.mode === "video" ? "Video call" : "Voice call") + (f.call.operator ? " answered by " + f.call.operator : "") + (f.call.duration != null ? " · " + mmss(f.call.duration) : "") }));
      parts.push(h("ul.transcript__list", ...f.call.lines.map((l) => h("li.transcript__line" + (l.who === "citizen" ? ".transcript__line--you" : ""), h("span.transcript__who", { text: l.who === "citizen" ? "Caller" : "Officer" }), h("span.transcript__text", { text: l.text })))));
      parts.push(h("button.btn.btn--secondary", { type: "button", onclick: () => { const a = h("a", { href: URL.createObjectURL(new Blob([transcriptText(t)], { type: "text/plain" })), download: "call-record-" + t.case_ref + ".txt" }); document.body.appendChild(a); a.click(); a.remove(); } }, icon("download"), "Download call record (.txt)"));
    }
    f.evidence.forEach((e) => parts.push(media(e)));
    return h("details.card.card--sunken.card--tight", { open: f.call && f.call.lines.length ? true : null }, h("summary.label-caps", { style: "cursor:pointer;min-height:2rem;display:flex;align-items:center", text: "Folder: call record and evidence" }), h("div.stack.stack--3", { style: "margin-top:var(--space-2)" }, ...parts));
  }

  async function answerNeed(t, n, answer) {
    const note = answer === "unavailable" ? await askNote("We do not have: " + n.label) : "";
    if (note === null) return;
    try { await api(`/api/unit/${encodeURIComponent(apId)}/need${q}`, { body: { task_id: t.id, need: n.key, answer, note, k: token } }); toast(answer === "available" ? "Recorded: you have it" : "Recorded. The request has gone out."); last = ""; await load(); }
    catch (e) { toast(e.message, true); }
  }
  function needsBlock(t) {
    if (!t.needs || !t.needs.length) return null;
    return h("div.card.card--sunken.card--tight", h("div.card__head", h("h3.card__title", { text: "Have ready for this file" }), h("span.chip.chip--danger", { text: "GBV: national priority" })),
      h("p.muted.text-sm", { text: "Tell the control room, for each item, whether your station has it. If you do not, the request goes out automatically to who can supply it." }),
      h("ul.mini-list", ...t.needs.map((n) => h("li", h("span", h("b", { text: n.label }), n.note ? h("span.muted", { text: " · " + n.note }) : null),
        n.status === "asked" ? h("span.chip-row", h("button.btn.btn--primary.btn--sm", { type: "button", onclick: () => answerNeed(t, n, "available") }, "We have it"), h("button.btn.btn--secondary.btn--sm", { type: "button", onclick: () => answerNeed(t, n, "unavailable") }, "We do not have it"))
          : n.status === "available" ? h("span.chip.chip--closed", { text: "Has it ready" }) : h("span.chip.chip--danger", { text: "Requested from " + (n.request_partner || "another unit") })))));
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
      needsBlock(t),
      folderBlock(t),
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
