/* Control room desk. Everything shown is built with textContent (the h() helper), never innerHTML with data. */
(function () {
  "use strict";
  const { h, clear, icon, api, poll, fmtAge, fmtTime, fmtClock, announce, sound } = window.SAPS;
  const $ = (id) => document.getElementById(id);

  const DOORS = {
    calls: { label: "Calls", icon: "phone", pick: (c) => c.kind === "call" },
    crime: { label: "Crime", icon: "alert", pick: (c) => c.kind === "crime" },
    gbv: { label: "GBV", icon: "heart", pick: (c) => c.kind === "gbv" || c.kind === "sos" },
    area: { label: "Infrastructure", icon: "lamp", pick: (c) => c.kind === "area" },
    anon: { label: "Tip-off line", icon: "eye-off", tips: true },
  };
  const GBV_NEEDS = {
    female_officer: "Female officer to attend", counsellor: "Counsellor or victim support", kit_d1: "Evidence kit for an adult (D1 rape kit)", kit_d7: "Evidence kit for a child under 13 (D7 rape kit)",
    medical: "Medical examination and treatment (including PEP within 72 hours)", vfr: "Victim Friendly Room", transport: "Transport to a care centre", shelter: "A safe place to stay", protection_order: "Help with a protection order",
  };
  const isGbv = (k) => k === "gbv" || k === "sos";
  const PRIO_NUM = { critical: 1, high: 2, normal: 3, low: 4 };
  const PRIO_WORD = { critical: "Critical", high: "High", normal: "Medium", low: "Routine" };
  const STATUS_WORD = { new: "New", assigned: "Accepted", in_progress: "In progress", referred: "Referred", closed: "Closed", verified: "Verified", acknowledged: "With HQ", directed: "Directed" };
  const STATUS_CHIP = { new: "new", assigned: "accepted", in_progress: "accepted", referred: "referred", closed: "closed", verified: "accepted", acknowledged: "referred", directed: "referred" };
  const TIP_WORD = { new: "New", verified: "Verified", referred: "Referred to HQ", acknowledged: "With HQ", directed: "Directed by HQ", closed: "Closed" };
  const GENDER = { female: "Female", male: "Male", other: "Other / self-described", undisclosed: "Not given" };
  const AGE = { under_18: "Under 18", "18_24": "18-24", "25_34": "25-34", "35_49": "35-49", "50_64": "50-64", "65_plus": "65+", undisclosed: "Not given" };

  const S = { selfie: "", points: [], drag: null, recStream: null, recorder: null, me: null, feed: null, version: null, door: "calls", filter: "all", sel: null, detail: null, opened: new Set(), ringing: new Set(), expect: new Set(), stage: null, missedSeen: new Set(), firstFeed: false, skew: 0, stop: null, partners: null, stations: null, room: null, recog: null };

  // ------------------------------------------------------------------ helpers
  function toast(msg, kind) {
    const el = h("div.toast", icon(kind === "error" ? "alert" : "check-circle"), h("span", { text: msg }));
    $("toasts").appendChild(el);
    setTimeout(() => { el.classList.add("toast--out"); setTimeout(() => el.remove(), 200); }, 3200);
  }
  const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit" });
  const nowSec = () => (S.feed ? S.feed.now : Date.now() / 1000) + 0;

  function showError(text) {
    const slot = $("error-slot");
    clear(slot);
    if (text) slot.appendChild(h("div.banner.banner--danger", { role: "alert" }, icon("alert"), h("span", { text })));
  }

  async function call(path, body) {
    try { return await api(path, { body: body || {} }); } catch (e) {
      if (e.code === "auth") { await boot(); }
      throw e;
    }
  }

  // ------------------------------------------------------------------ sign in
  // ---- sign-in photo
  async function startSelfie() {
    $("selfie-img").hidden = true; $("selfie-v").hidden = false; $("selfie-take").hidden = false; $("selfie-retake").hidden = true; S.selfie = "";
    $("photo-err").hidden = true;
    try { await SAPS.camera.start($("selfie-v")); }
    catch (e) { $("photo-err").hidden = false; $("photo-err").textContent = "The camera could not start. Allow the camera for this page, then press Take photo again."; $("no-camera").hidden = false; }
  }
  $("selfie-take").addEventListener("click", async () => {
    if (!SAPS.camera.stream) { await startSelfie(); if (!SAPS.camera.stream) return; }
    S.selfie = SAPS.camera.snap($("selfie-v"), 360);
    $("selfie-img").src = S.selfie; $("selfie-img").hidden = false; $("selfie-v").hidden = true; $("selfie-take").hidden = true; $("selfie-retake").hidden = false;
    SAPS.camera.stop(); $("photo-err").hidden = true;
  });
  $("selfie-retake").addEventListener("click", startSelfie);
  $("no-camera").addEventListener("click", () => { S.noCamera = true; $("login-form").requestSubmit(); });
  if ($("login-view") && !$("login-view").hidden) startSelfie();

  try { const last = localStorage.getItem("desk-section"); if (last && $("section")) $("section").value = last; } catch (e) { /* ok */ }
  $("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("login-error"); err.hidden = true;
    const btn = $("login-btn"); btn.disabled = true;
    try {
      try { localStorage.setItem("desk-section", $("section").value); } catch (e) { /* ok */ }
      await api("/api/auth/login", { body: { role: "desk", section: $("section").value, officer: $("officer").value, photo: S.selfie || "", no_camera: !S.selfie && S.noCamera, password: $("password").value } });
      SAPS.camera.stop();
      $("password").value = "";
      await boot();
    } catch (ex) {
      err.hidden = false; err.replaceChildren(icon("alert", "icon--sm"), document.createTextNode(ex.offline ? "No connection. Try again." : ex.message));
    } finally { btn.disabled = false; }
  });
  const outDlg = $("out-dlg");
  async function doLogout(photo) {
    try { await api("/api/auth/logout", { body: { photo: photo || "" } }); } catch (e) { /* ignore */ }
    SAPS.camera.stop(); if (S.stop) S.stop(); location.reload();
  }
  $("logout").addEventListener("click", async () => {
    $("out-err").hidden = true; $("out-img").hidden = true; $("out-v").hidden = false; $("out-take").hidden = false; $("out-skip").hidden = true;
    outDlg.showModal();
    try { await SAPS.camera.start($("out-v")); }
    catch (e) { $("out-err").hidden = false; $("out-err").textContent = "The camera could not start. Allow the camera and try again, or sign out without a photo (this is flagged in the shift record)."; $("out-skip").hidden = false; }
  });
  $("out-take").addEventListener("click", () => {
    if (!SAPS.camera.stream) { $("out-err").hidden = false; $("out-err").textContent = "No camera. Use the option below."; $("out-skip").hidden = false; return; }
    const photo = SAPS.camera.snap($("out-v"), 360);
    $("out-img").src = photo; $("out-img").hidden = false; $("out-v").hidden = true;
    doLogout(photo);
  });
  $("out-skip").addEventListener("click", () => doLogout(""));
  $("out-cancel").addEventListener("click", () => { SAPS.camera.stop(); outDlg.close(); });
  outDlg.addEventListener("close", () => SAPS.camera.stop());

  // Each section opens its own doors and nothing else.
  const SECTION_DOORS = { call_centre: ["calls"], desk: ["crime", "area"], tip_line: ["anon"], gbv: ["gbv"] };
  function applySection(section, label) {
    const allowed = SECTION_DOORS[section] || [];
    S.allowed = allowed;
    document.querySelectorAll("#doors [data-door]").forEach((t) => { t.hidden = !allowed.includes(t.dataset.door); });
    $("doors").hidden = allowed.length < 2;
    const name = { call_centre: "Call centre", desk: "Desk", tip_line: "Tip-off line", gbv: "GBV desk" }[section] || "Control room";
    $("section-name").textContent = "Control room · " + name;
    $("queue-title").textContent = name;
    if (!allowed.includes(S.door)) { S.door = allowed[0] || "calls"; }
    document.querySelectorAll("#doors [role=tab]").forEach((t) => { const on = t.dataset.door === S.door; t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1; });
  }

  async function boot() {
    let me;
    try { me = await api("/api/auth/me"); } catch (e) { me = { role: null }; }
    S.me = me;
    if (me.role === "desk") {
      $("login-view").hidden = true; $("desk-view").hidden = false;
      $("officer-id").textContent = me.officer;
      document.title = me.officer + " · SAPS KZN control room (DEMO)";
      applySection(me.section, me.officer);
      SAPS.camera.stop();
      if (!S.stop) S.stop = poll(refresh, 2000);
    } else {
      $("login-view").hidden = false; $("desk-view").hidden = true;
      if (!me.login_desk) { const err = $("login-error"); err.hidden = false; err.textContent = "The desk login is not switched on for this demo."; }
    }
  }

  // ------------------------------------------------------------------ feed
  async function refresh() {
    const url = "/api/staff/feed" + (S.version !== null ? "?since=" + S.version : "");
    const f = await api(url);
    if (f.unchanged) { S.feed && (S.feed.now = f.now); return; }
    S.feed = f; S.version = f.version;
    showError("");
    renderCounts(); renderQueue(); renderIncoming(); loadPoints();
    if (S.sel && S.detail && (S.opened.has(S.sel.id) || !S.detail.restricted)) loadDetail(S.sel, true);
    if (!S.sel) autoSelect();
  }

  async function loadPoints() {
    try { S.points = (await api("/api/staff/action-points")).points; paintLoads(); } catch (e) { /* the dock keeps its last view */ }
  }
  function paintLoads() {
    document.querySelectorAll(".dropbox[data-ap]").forEach((b) => {
      const ap = S.points.find((p) => p.id === b.dataset.ap); if (!ap) return;
      const el = b.querySelector(".dropbox__load"); if (!el) return;
      el.textContent = ap.load.open ? String(ap.load.open) : ""; el.className = "dropbox__load chip chip--" + (ap.load.urgent ? "danger" : "info"); el.hidden = !ap.load.open;
    });
  }

  function items(door) {
    if (!S.feed) return [];
    const d = DOORS[door];
    return d.tips ? S.feed.tips : S.feed.cases.filter(d.pick);
  }
  function isOpen(it) { return it.status !== "closed"; }

  function renderCounts() {
    (S.allowed || Object.keys(DOORS)).forEach((k) => { $("n-" + k).textContent = items(k).filter(isOpen).length; });
  }

  function visible() {
    let list = items(S.door);
    if (S.filter === "new") list = list.filter((c) => c.status === "new");
    if (S.filter === "mine") list = list.filter((c) => c.assigned_to === S.me.officer);
    const prio = (c) => PRIO_NUM[c.priority] || 3;
    return list.slice().sort((a, b) => (a.status === "closed") - (b.status === "closed") || prio(a) - prio(b) || a.created_at - b.created_at);
  }

  function renderQueue() {
    const ul = $("queue"); clear(ul);
    const all = items(S.door).filter(isOpen);
    const oldest = all.reduce((m, c) => Math.max(m, nowSec() - c.created_at), 0);
    const st = $("stats"); clear(st);
    st.append(h("span", h("b", String(all.length)), " open"), h("span", "oldest ", h("b", all.length ? fmtAge(nowSec() - oldest, nowSec()) : "0")));
    const list = visible();
    if (!list.length) {
      ul.appendChild(h("li.queue-empty", h("div.state", h("span.state__icon", icon("inbox", "icon--lg")), h("p.state__title", { text: "Nothing here" }), h("p.state__text", { text: "New items appear here by themselves." }))));
      return;
    }
    list.forEach((c) => {
      const tip = c.kind === "tip";
      const pnum = PRIO_NUM[c.priority] || 3;
      const word = tip ? TIP_WORD[c.status] : STATUS_WORD[c.status];
      const chip = tip ? ({ new: "new", verified: "accepted", referred: "escalated", acknowledged: "referred", directed: "referred", closed: "closed" })[c.status] : STATUS_CHIP[c.status];
      const ageCls = c.sla === "red" ? "age--late" : c.sla === "amber" ? "age--warn" : "";
      const ico = c.kind === "call" ? "phone" : c.kind === "gbv" || c.kind === "sos" ? "heart" : tip ? "eye-off" : c.kind === "area" ? "lamp" : "alert";
      const b = h("button.queue-row.queue-row--p" + pnum, { type: "button", draggable: c.status === "closed" ? null : "true", dataset: { id: c.id, kind: tip ? "tip" : "case" } },
        h("span.queue-row__main",
          h("span.queue-row__title", icon(ico), c.label, c.restricted ? icon("lock", "icon--sm") : null),
          h("span.queue-row__meta", c.cluster_name + (c.address ? " · " + c.address : "")),
          h("span.queue-row__meta", h("span.ref", { text: c.ref }), h("span.chip.chip--dot.chip--" + chip, { text: word + (c.call_state === "ringing" ? " (ringing)" : "") }), c.incomplete ? h("span.chip.chip--warning", { text: "Incomplete" }) : null)),
        h("span.queue-row__side",
          h("span.prio.prio--" + pnum, { text: "P" + pnum }),
          c.status !== "closed" ? h("span.age" + (ageCls ? "." + ageCls : ""), { "aria-label": "waiting " + fmtAge(c.created_at, nowSec()) }, fmtAge(c.created_at, nowSec())) : null));
      if (S.sel && S.sel.id === c.id) b.setAttribute("aria-current", "true");
      ul.appendChild(h("li", b));
    });
  }
  $("queue").addEventListener("dragstart", (e) => {
    const b = e.target.closest(".queue-row"); if (!b) return;
    S.drag = { id: b.dataset.id, kind: b.dataset.kind }; b.classList.add("is-dragging");
    e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", b.dataset.id);
    select(S.drag);
  });
  $("queue").addEventListener("dragend", (e) => { const b = e.target.closest(".queue-row"); if (b) b.classList.remove("is-dragging"); });
  $("queue").addEventListener("click", (e) => {
    const b = e.target.closest(".queue-row");
    if (b) select({ id: b.dataset.id, kind: b.dataset.kind });
  });

  function autoSelect() {
    const l = visible();
    if (l.length) select({ id: l[0].id, kind: l[0].kind === "tip" ? "tip" : "case" }); else { S.sel = null; S.detail = null; renderCase(); }
  }

  // ------------------------------------------------------------------ doors and filters
  function setDoor(d, focus) {
    S.door = d; S.filter = "all";
    document.querySelectorAll("#doors [role=tab]").forEach((t) => { const on = t.dataset.door === d; t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1; if (on && focus) t.focus(); });
    document.querySelectorAll("#qfilter button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.f === "all")));
    renderQueue(); S.sel = null; S.detail = null; autoSelect();
  }
  document.querySelectorAll("#doors [role=tab]").forEach((t) => t.addEventListener("click", () => setDoor(t.dataset.door)));
  $("doors").addEventListener("keydown", (e) => {
    const order = S.allowed || Object.keys(DOORS), i = order.indexOf(S.door);
    if (e.key === "ArrowRight") { e.preventDefault(); setDoor(order[(i + 1) % order.length], true); }
    if (e.key === "ArrowLeft") { e.preventDefault(); setDoor(order[(i + order.length - 1) % order.length], true); }
  });
  document.querySelectorAll("#qfilter button").forEach((b) => b.addEventListener("click", () => {
    S.filter = b.dataset.f;
    document.querySelectorAll("#qfilter button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    renderQueue();
  }));
  $("alerts").addEventListener("click", () => {
    const on = $("alerts").getAttribute("aria-pressed") !== "true";
    $("alerts").setAttribute("aria-pressed", String(on)); $("alerts-l").textContent = on ? "Alerts on" : "Alerts off";
    if (on) { sound.enable(); sound.ring(); }
  });

  // ------------------------------------------------------------------ calls strip: the same on every section's desk
  // Calling is the most important thing the desk does, so it sits above everything else and is never hidden.
  let ringTimer = null, tickTimer = null;
  const wordy = (v) => (v && v !== "undisclosed" ? String(v).replace(/_/g, " ") : "");
  // The caller's profile, shown when they are registered and calling from the app.
  function callerBlock(c) {
    const p = c.caller; if (!p) return null;
    const meta = [p.mobile, wordy(p.gender), wordy(p.age_band)].filter(Boolean).join(" · ");
    return h("div.caller-block",
      p.has_photo ? h("img.caller-block__photo", { src: `/api/staff/case/${c.id}/face`, alt: "Caller's profile photo", width: "56", height: "56" }) : h("span.caller-block__photo", icon("user")),
      h("div", h("p.caller-block__name", { text: p.name || "Caller with no profile" }),
        meta ? h("p.caller-block__meta", { text: meta }) : null,
        p.home_address ? h("p.caller-block__meta", { text: p.home_address }) : null,
        p.registered ? h("span.chip.chip--success", { text: "Registered citizen" }) : null));
  }
  const MISS_WHY = { unanswered: "Nobody answered", caller_hung_up: "Caller hung up", dropped: "Call dropped" };
  const sinceNow = (since) => Math.max(0, Date.now() / 1000 + (S.skew || 0) - since);
  const agoText = (sec) => (sec < 60 ? "just now" : sec < 3600 ? Math.floor(sec / 60) + " min ago" : Math.floor(sec / 3600) + " h ago");
  function renderIncoming() {
    const wrap = $("incoming-wrap"); clear(wrap);
    S.skew = S.feed.now - Date.now() / 1000;
    const calls = S.feed.cases.filter((c) => c.kind === "call");
    const ringing = calls.filter((c) => c.call_state === "ringing");
    const live = calls.filter((c) => c.call_state === "live");
    const missed = calls.filter((c) => c.call_missed && !c.call_callback && c.call_state === "ended").sort((a, b) => b.call_ended_at - a.call_ended_at);
    const pill = (n, word, tone) => h("span.chip.chip--" + (n ? tone : "neutral") + (n ? ".chip--dot" : ""), { text: n + " " + word });
    wrap.appendChild(h("div.calls-bar" + (ringing.length ? ".calls-bar--ring" : ""),
      h("span.calls-bar__title", icon("phone"), "Calls"),
      h("span.calls-bar__line", ringing.length ? "Incoming call. Answer it." : live.length ? "On a call." : "Phone line open. Nobody is waiting."),
      h("span.calls-bar__pills", pill(ringing.length, "ringing", "danger"), pill(live.length, "live", "success"), pill(missed.length, "missed", "warning"))));
    ringing.forEach((c) => {
      if (!S.ringing.has(c.id)) { S.ringing.add(c.id); sound.ring(); announce("Incoming call " + c.ref); }
      wrap.appendChild(h("div.incoming-call", { role: "alert" },
        h("div.incoming-call__icon", icon("phone")),
        h("div", h("span.incoming-call__tag", "Incoming call"), h("p.incoming-call__name", { text: (c.call_mode === "video" ? "Video call" : "Voice call") + " · " + c.ref }),
          callerBlock(c) || h("p.incoming-call__meta", { text: c.cluster_name + " · no profile" }),
          c.caller ? h("p.incoming-call__meta", { text: c.cluster_name }) : null),
        h("div.incoming-call__actions", h("p.incoming-call__timer.num", { "aria-label": "Waiting time", "data-since": String(c.created_at) }, fmtClock(sinceNow(c.created_at))),
          h("button.btn.btn--answer.btn--lg.btn--block", { type: "button", onclick: () => answer(c, false) }, icon("phone"), "Answer"),
          S.me.video && c.call_mode === "video" ? h("button.btn.btn--secondary.btn--block", { type: "button", onclick: () => answer(c, true) }, icon("video"), "Answer with video") : null)));
    });
    for (const id of Array.from(S.ringing)) if (!ringing.some((c) => c.id === id)) S.ringing.delete(id);
    live.filter((c) => !(S.stage && S.stage.id === c.id)).forEach((c) => {
      wrap.appendChild(h("div.call-row.call-row--live",
        h("span.call-row__icon", icon("phone")),
        h("div.call-row__main", h("p.call-row__title", { text: "Live call · " + c.ref }), h("p.call-row__meta", { text: "Answered by " + (c.call_operator || "an officer") + " · " + c.cluster_name })),
        h("span.call-row__timer.num", { "data-since": String(c.call_answered_at || c.created_at) }, fmtClock(sinceNow(c.call_answered_at || c.created_at))),
        h("div.call-row__actions",
          h("button.btn.btn--secondary.btn--sm", { type: "button", onclick: () => select({ id: c.id, kind: "case" }) }, "Open call"),
          h("button.btn.btn--secondary.btn--sm", { type: "button", onclick: () => endLive(c) }, icon("end-call"), "End call"))));
    });
    missed.slice(0, 4).forEach((c) => {
      if (!S.missedSeen.has(c.id)) { if (S.missedSeen.size || S.firstFeed) { sound.ring(); announce("Missed call " + c.ref); } S.missedSeen.add(c.id); }
      wrap.appendChild(h("div.call-row.call-row--missed",
        h("span.call-row__icon", icon("phone")),
        h("div.call-row__main", h("p.call-row__title", { text: "Missed call · " + c.ref + (c.caller && c.caller.name ? " · " + c.caller.name : "") }),
          h("p.call-row__meta", h("span", { text: (MISS_WHY[c.call_missed_reason] || "Missed") + " · " }), h("span", { "data-ago": String(c.call_ended_at), text: agoText(sinceNow(c.call_ended_at)) }),
            h("span", { text: " · " + (c.has_contact ? "number on record" : "no number: reply goes to the app") + ({ ringing: " · ringing the caller's app now", no_answer: " · call-back not answered", declined: " · caller declined the call-back" }[c.call_ring] || "") }))),
        h("div.call-row__actions",
          h("button.btn.btn--primary.btn--sm", { type: "button", disabled: c.call_ring === "ringing" ? true : null, onclick: () => callBack(c) }, icon("phone"), c.call_ring === "ringing" ? "Ringing…" : c.call_ring ? "Try again" : "Call back"),
          h("button.btn.btn--ghost.btn--sm", { type: "button", onclick: () => select({ id: c.id, kind: "case" }) }, "Open"))));
    });
    if (missed.length > 4) wrap.appendChild(h("p.muted.text-sm", { text: "+" + (missed.length - 4) + " more missed calls. The oldest are shown last." }));
    S.firstFeed = true;
    const mine = live.find((c) => S.expect.has(c.id) && c.call_transport === "p2p" && c.call_operator === S.me.officer);
    if (mine && (!S.stage || S.stage.id !== mine.id)) startStage(mine);
    if (S.stage && !live.some((c) => c.id === S.stage.id)) endStage();
    clearInterval(ringTimer); clearInterval(tickTimer);
    if (ringing.length) ringTimer = setInterval(() => sound.ring(), 4000);
    tickTimer = setInterval(() => {
      document.querySelectorAll("[data-since]").forEach((el) => { el.textContent = fmtClock(sinceNow(Number(el.dataset.since))); });
      document.querySelectorAll("[data-ago]").forEach((el) => { el.textContent = agoText(sinceNow(Number(el.dataset.ago))); });
    }, 1000);
  }

  async function endLive(c) {
    try { await call(`/api/staff/case/${c.id}/end`); endStage(); leaveVideo(); toast("Call ended"); await refresh(); } catch (e) { showError(e.message); }
  }

  // A missed or dropped call is returned by ringing the caller's app, a message to the app, or a logged call on the number on record.
  async function callBack(c) {
    try {
      const d = await api(`/api/staff/case/${c.id}`);
      const options = [
        { value: "ring_voice", label: "Ring the caller's app now (voice call)" },
        { value: "ring_video", label: "Ring the caller's app now (video call)" },
        { value: "app", label: "Send a call-back message to the caller's app" },
      ];
      if (d.mobile) options.push({ value: "phone", label: "Log a call on the number on record: " + d.mobile });
      const v = await ask({
        title: "Call back " + c.ref,
        body: (d.name ? d.name + ". " : "") + "Ringing works while the caller has the app open. Otherwise they see a message the next time they open it. Demo: nothing is dialled on the phone network.",
        fields: [{ id: "how", type: "select", label: "How", options, value: c.call_mode === "video" ? "ring_video" : "ring_voice" }, { id: "note", type: "text", label: "Note (optional)" }], ok: "Go" });
      if (!v) return;
      await call(`/api/staff/case/${c.id}/callback`, { method: v.how, note: v.note });
      if (v.how.startsWith("ring")) { S.expect.add(c.id); toast("Ringing the caller's app. You will be connected when they answer."); }
      else toast(v.how === "phone" ? "Call-back logged on the file" : "Message sent to the caller's app");
      await refresh();
    } catch (e) { showError(e.message); }
  }

  async function answer(c, video) {
    try {
      const r = await call(`/api/staff/case/${c.id}/answer`, { video });
      toast("Call answered. You are connected to the caller.");
      if ((S.allowed || []).includes("calls")) setDoor("calls");
      select({ id: c.id, kind: "case" });
      S.expect.add(c.id);
      if (r.transport === "video") joinVideo(r.token, r.room, c.call_mode, c.id);
      else if (r.transport === "p2p") startStage(Object.assign({}, c, { call_answered_at: Date.now() / 1000 + (S.skew || 0) }));
      await refresh();
    } catch (e) { showError(e.message); }
  }

  // ---- the live call: a direct voice or video connection to the caller's app, kept above everything else
  async function startStage(c) {
    if (S.stage) { if (S.stage.id === c.id) return; endStage(); }
    const video = c.call_mode === "video";
    const box = $("call-stage"); clear(box); box.hidden = false;
    const wait = h("p.call-stage__wait", { text: "Connecting to the caller…" });
    const remoteBox = h("div.call-stage__remote", wait);
    const selfBox = h("div.call-stage__self", { hidden: true });
    const state = h("span.chip.chip--neutral", { text: "Connecting" });
    const muteB = h("button.btn.btn--secondary.btn--sm", { type: "button" }, icon("mic"), "Mute");
    const camB = video ? h("button.btn.btn--secondary.btn--sm", { type: "button" }, icon("camera"), "Camera off") : null;
    const stage = S.stage = { id: c.id, p2p: null, local: null };
    muteB.onclick = () => { const tr = stage.local ? stage.local.getAudioTracks() : []; const on = tr.length && !tr[0].enabled; tr.forEach((t) => { t.enabled = !!on; }); muteB.lastChild.textContent = on ? "Mute" : "Unmute"; };
    if (camB) camB.onclick = () => { const tr = stage.local ? stage.local.getVideoTracks() : []; const on = tr.length && !tr[0].enabled; tr.forEach((t) => { t.enabled = !!on; }); camB.lastChild.textContent = on ? "Camera off" : "Camera on"; };
    box.append(
      h("div.call-stage__head", h("span.call-stage__live", { text: (video ? "Video call · " : "Voice call · ") + c.ref }), state, h("span.call-stage__timer.num", { "data-since": String(c.call_answered_at || Date.now() / 1000) }, "00:00")),
      callerBlock(c), remoteBox, selfBox,
      h("div.call-stage__controls", muteB, camB,
        h("button.btn.btn--secondary.btn--sm", { type: "button", onclick: () => select({ id: c.id, kind: "case" }) }, icon("file"), "Open file"),
        h("button.btn.btn--secondary.btn--sm", { type: "button", onclick: () => endLive(c) }, icon("end-call"), "End call")));
    const local = await window.SAPS_P2P.localMedia(video);
    if (S.stage !== stage) { if (local) local.getTracks().forEach((t) => t.stop()); return; }
    stage.local = local;
    if (!local) toast("Your microphone is blocked. You can hear the caller but they cannot hear you. Type in the file.", "error");
    if (local && video && local.getVideoTracks().length) {
      const v = document.createElement("video"); v.autoplay = true; v.muted = true; v.setAttribute("playsinline", ""); v.srcObject = local;
      selfBox.appendChild(v); selfBox.hidden = false; v.play().catch(() => {});
    }
    stage.p2p = window.SAPS_P2P.connect({
      role: "answerer", ice: (S.me && S.me.ice) || [], stream: local, wantVideo: video,
      post: (type, data) => call(`/api/staff/case/${c.id}/signal`, { type, data }),
      fetchSince: async (after) => (await api(`/api/staff/case/${c.id}/signal?after=${after}`)).messages,
      onTrack: (remote) => {
        let a = document.getElementById("a-remote");
        if (!a) { a = document.createElement("audio"); a.id = "a-remote"; a.autoplay = true; a.setAttribute("playsinline", ""); document.body.appendChild(a); }
        if (a.srcObject !== remote) { a.srcObject = remote; a.play().catch(() => {}); }
        if (remote.getVideoTracks().length && !remoteBox.querySelector("video")) {
          const v = document.createElement("video"); v.autoplay = true; v.muted = true; v.setAttribute("playsinline", ""); v.srcObject = remote;
          clear(remoteBox); remoteBox.appendChild(v); v.play().catch(() => {});
        } else if (!remote.getVideoTracks().length) wait.textContent = "Connected. Voice only.";
        S.recStream = remote;
        if (!S.recorder) setTimeout(() => { if (S.stage === stage && !S.recorder) startRecording(c.id); }, 900);
      },
      onState: (st) => { state.textContent = { connected: "Connected", connecting: "Connecting", new: "Connecting", checking: "Connecting", failed: "Connection failed", slow: "Still connecting", disconnected: "Reconnecting" }[st] || st; state.className = "chip chip--" + (st === "connected" ? "success" : st === "failed" ? "danger" : "neutral"); },
    });
    startCaptions(c.id);
  }
  function endStage() {
    const st = S.stage; if (!st) return;
    S.stage = null;
    try { if (st.p2p) st.p2p.close(); } catch (e) { /* ok */ }
    try { if (st.local) st.local.getTracks().forEach((t) => t.stop()); } catch (e) { /* ok */ }
    const box = $("call-stage"); clear(box); box.hidden = true;
    leaveVideo();
  }

  // ---- video (Twilio) for officers, only when the service has it switched on
  let sdkPromise = null;
  function loadSdk() {
    if (window.Twilio && window.Twilio.Video) return Promise.resolve();
    if (sdkPromise) return sdkPromise;
    sdkPromise = new Promise((resolve, reject) => {
      const s = h("script", { src: "https://unpkg.com/twilio-video@2/dist/twilio-video.min.js" });
      s.onload = resolve; s.onerror = () => { sdkPromise = null; reject(new Error("sdk")); };
      document.head.appendChild(s);
    });
    return sdkPromise;
  }
  async function joinVideo(token, room, mode, caseId) {
    try {
      await loadSdk();
      S.room = await window.Twilio.Video.connect(token, { name: room, audio: true, video: mode === "video" ? { width: 640 } : false });
      const target = () => document.getElementById("remote-video");
      S.recStream = new MediaStream(); S.recorder = null;
      const attach = (track) => {
        try { S.recStream.addTrack(track.mediaStreamTrack); if (!S.recorder) startRecording(caseId); } catch (e) { /* recording is best effort */ }
        const box = target();
        if (!box) return;
        if (track.kind === "video") { clear(box); box.appendChild(track.attach()); box.hidden = false; } else { const a = track.attach(); a.id = "a-remote"; document.body.appendChild(a); }
      };
      const sub = (p) => { p.tracks.forEach((pub) => pub.track && attach(pub.track)); p.on("trackSubscribed", attach); };
      S.room.participants.forEach(sub); S.room.on("participantConnected", sub);
      startCaptions();
    } catch (e) { toast("Video could not start. You can still type to the caller.", "error"); }
  }
  // The call is recorded automatically and saved on the file, five seconds at a time.
  function startRecording(caseId) {
    if (!window.MediaRecorder || !S.recStream) return;
    try {
      const rec = new MediaRecorder(S.recStream, { mimeType: MediaRecorder.isTypeSupported("video/webm") ? "video/webm" : "" });
      rec.ondataavailable = (e) => { if (e.data && e.data.size) fetch(`/api/staff/case/${caseId}/recording`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "video/webm" }, body: e.data }).catch(() => {}); };
      rec.start(5000); S.recorder = rec;
    } catch (e) { S.recorder = null; }
  }
  function leaveVideo() {
    try { if (S.recorder && S.recorder.state !== "inactive") S.recorder.stop(); } catch (e) { /* ok */ }
    S.recorder = null;
    try { if (S.recog) { const r = S.recog; S.recog = null; r.stop(); } if (S.room) S.room.disconnect(); } catch (e) { /* ok */ }
    S.room = null; document.querySelectorAll("#a-remote").forEach((a) => a.remove());
  }
  function startCaptions(forId) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR || S.recog || !(forId || S.sel)) return;
    const id = forId || S.sel.id;
    S.recog = new SR(); S.recog.continuous = true; S.recog.interimResults = true; S.recog.lang = "en-ZA";
    let last = 0;
    S.recog.onresult = (ev) => { const r = ev.results[ev.results.length - 1]; const n = Date.now(); if (!r.isFinal && n - last < 600) return; last = n; call(`/api/staff/case/${id}/line`, { text: r[0].transcript, src: "caption", partial: !r.isFinal }).catch(() => {}); };
    S.recog.onend = () => { if (S.recog) try { S.recog.start(); } catch (e) { /* running */ } };
    try { S.recog.start(); } catch (e) { S.recog = null; }
  }

  // ------------------------------------------------------------------ selecting and loading a file
  function select(sel) {
    S.sel = sel; S.detail = null;
    renderQueue();
    const restricted = sel.kind === "case" && (S.feed.cases.find((c) => c.id === sel.id) || {}).restricted;
    if (restricted && !S.opened.has(sel.id)) { S.detail = { restricted: true, locked: true, summary: S.feed.cases.find((c) => c.id === sel.id) }; renderCase(); return; }
    loadDetail(sel, false);
  }
  async function loadDetail(sel, quiet) {
    try {
      const d = await api(sel.kind === "tip" ? `/api/staff/tip/${sel.id}` : `/api/staff/case/${sel.id}`);
      if (!S.sel || S.sel.id !== sel.id) return;
      S.detail = d;
      renderCase(quiet);
    } catch (e) { if (!quiet) showError(e.message); }
  }

  // ------------------------------------------------------------------ case file
  function card(title, extra) { return h("section.card.card--tight", h("div.card__head", h("h3.card__title", { text: title }), extra || null)); }
  function kv(rows) { const dl = h("dl.kv"); rows.forEach((r) => { dl.append(h("dt", { text: r[0] }), h("dd", { text: r[1] })); }); return dl; }
  function abtn(label, ico, cls, fn, disabled) { return h("button.btn." + cls.split(" ").join("."), { type: "button", disabled: disabled || null, onclick: fn }, icon(ico), label); }

  let mapInst = null;
  function renderCase(quiet) {
    const root = $("casefile");
    const keepY = quiet ? window.scrollY : 0;
    const keepChat = $("chat-in") ? $("chat-in").value : "";
    clear(root);
    if (mapInst) { try { mapInst.remove(); } catch (e) { /* ok */ } mapInst = null; }
    const d = S.detail;
    if (!d) {
      root.appendChild(h("div.state", h("span.state__icon", icon("file", "icon--lg")), h("p.state__title", { text: "Select a case" }), h("p.state__text", { text: "Choose an item from the queue to open its file." })));
      return;
    }
    if (d.locked) return renderLocked(root, d.summary);
    const tip = S.sel.kind === "tip";
    const pnum = PRIO_NUM[d.priority] || 3;
    const word = tip ? TIP_WORD[d.status] : STATUS_WORD[d.status];
    const chip = tip ? ({ new: "new", verified: "accepted", referred: "escalated", acknowledged: "referred", directed: "referred", closed: "closed" })[d.status] : STATUS_CHIP[d.status];

    root.appendChild(h("div.casefile__head",
      h("span.ref.casefile__ref", { text: d.ref }),
      h("h1.casefile__title", { text: d.label + ", " + d.cluster_name }),
      h("div.cluster",
        h("span.prio.prio--" + pnum, { text: "P" + pnum + " " + PRIO_WORD[d.priority || "normal"] }),
        h("span.chip.chip--dot.chip--" + chip, { text: word }),
        d.restricted ? h("span.restricted", icon("lock"), "Restricted record - access logged") : null,
        h("span.muted.text-sm", { text: "Received " + hhmm(d.created_at) + (d.status !== "closed" ? " · " + fmtAge(d.created_at, nowSec()) + " ago" : "") }))));

    if (d.incomplete) root.appendChild(h("div.banner.banner--warning", icon("alert"), h("span", { text: "Incomplete report. Not given: " + (d.missing || []).join(", ") + ". It reached the desk anyway. Follow up if you can." })));
    root.appendChild(h("div.actions-wrap", h("div.action-bar", { role: "group", "aria-label": "Case actions" }, ...actionButtons(d, tip))));

    root.appendChild(dockCard(d, tip));
    const head = root.querySelector(".casefile__head");
    if (head && d.status !== "closed") { head.draggable = true; head.addEventListener("dragstart", (e) => { S.drag = { id: S.sel.id, kind: S.sel.kind }; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", S.sel.id); }); }
    const grid = h("div.casefile__grid"), left = h("div.casefile__col"), right = h("div.casefile__col");

    // person (cases) or no-identity box (tips)
    if (tip) {
      left.appendChild(h("section.card.card--tight", h("div.card__head", h("h3.card__title", { text: "Source" })),
        h("div.lockbox", icon("eye-off", "icon--lg"), h("strong", { text: "No identity held" }), h("p.text-sm", { text: "This tip was sent anonymously. No name, number or device ID exists in this record, by design. The citizen can check progress with their one-time code." }))));
    } else {
      left.appendChild(personCard(d));
    }
    left.appendChild(locationCard(d));
    if (!tip) left.appendChild(deploymentsCard(d));
    if (isGbv(d.kind)) right.appendChild(gbvCard(d));
    if (d.call) {
      right.appendChild(contentCard(d, tip));
      if (d.media && d.media.length) right.appendChild(mediaCard(d));
      right.appendChild(timelineCard(d));
      right.appendChild(referralsCard(d));
    } else {
      right.appendChild(timelineCard(d));
      right.appendChild(contentCard(d, tip));
      if (tip) right.appendChild(tipFlowCard(d)); else right.appendChild(referralsCard(d));
      if (d.media && d.media.length) right.appendChild(mediaCard(d));
    }
    grid.append(left, right); root.appendChild(grid);
    drawMap(d);
    if (quiet) window.scrollTo(0, keepY);
    if ($("chat-in") && keepChat) $("chat-in").value = keepChat;
  }

  function renderLocked(root, c) {
    root.appendChild(h("div.casefile__head", h("span.ref.casefile__ref", { text: c.ref }), h("h1.casefile__title", { text: c.label + ", " + c.cluster_name }),
      h("div.cluster", h("span.restricted", icon("lock"), "Restricted record - access logged"))));
    root.appendChild(h("div.lockbox", icon("lock", "icon--lg"), h("strong", { text: "Name and number are hidden" }),
      h("p.text-sm", { text: "Opening this record is logged with your section and the time. Open it only to act on it." }),
      h("button.btn.btn--secondary", { type: "button", onclick: () => { S.opened.add(c.id); loadDetail({ id: c.id, kind: "case" }, false); toast("Record opened. Access has been logged."); } }, icon("lock"), "Open restricted record")));
  }

  function actionButtons(d, tip) {
    const closed = d.status === "closed";
    if (tip) {
      return [
        abtn("Verify", "check", "btn--primary", () => tipVerify(d), closed),
        abtn("Record action", "file", "btn--secondary", () => tipAction(d), closed),
        abtn("Refer to HQ", "escalate", "btn--secondary", () => tipRefer(d), closed || d.status !== "verified"),
        abtn("Close", "close", "btn--secondary", () => tipClose(d), closed || ["referred", "acknowledged", "directed"].includes(d.status)),
      ];
    }
    const live = d.call && d.call.state === "live", ringing = d.call && d.call.state === "ringing";
    const out = [
      abtn("Accept", "check", "btn--primary", () => doAct(d, "accept"), closed || d.status !== "new"),
      abtn("Dispatch", "building", "btn--secondary", () => dispatchDlg(d), closed || d.kind === "area"),
      abtn("Refer", "referral", "btn--secondary", () => referDlg(d), closed),
    ];
    if (live) out.push(abtn("End call", "end-call", "btn--secondary", async () => { try { await call(`/api/staff/case/${d.id}/end`); leaveVideo(); toast("Call ended"); await refresh(); } catch (e) { showError(e.message); } }));
    else if (ringing) out.push(abtn("Answer", "phone", "btn--answer", () => answer(d, false)));
    else out.push(abtn("Close", "close", "btn--secondary", () => closeDlg(d), closed));
    return out;
  }

  // GBV is a national priority: the file shows what the response needs and what each station has confirmed.
  function gbvCard(d) {
    const c = card("GBV response", h("span.chip.chip--danger", { text: "National priority" }));
    const picked = new Set(d.needs || []);
    const boxes = Object.entries(GBV_NEEDS).map(([k, label]) => h("label.choice", h("input", { type: "checkbox", value: k, checked: picked.has(k) ? true : null }), h("span.choice__title", { text: label })));
    c.append(h("p.muted.text-sm", { text: "Tick what this file needs. When you send it to a station, the station must say whether it has each one ready." }),
      h("div.choice-group", { id: "gbv-needs", style: "max-height:15rem;overflow:auto" }, ...boxes),
      h("p", { style: "margin-top:var(--space-2)" }, h("button.btn.btn--secondary", { type: "button", onclick: () => { const keys = Array.from(document.querySelectorAll("#gbv-needs input:checked")).map((i) => i.value); doAct(d, "needs", { needs: keys }); } }, icon("check"), "Save needs")));
    const deps = (d.deployments || []).filter((x) => x.needs && Object.keys(x.needs).length);
    if (deps.length) {
      c.append(h("p.label-caps", { style: "margin-top:var(--space-4)", text: "What each station has confirmed" }));
      deps.forEach((x) => c.append(h("div", { style: "margin-top:var(--space-2)" }, h("b", { text: x.station_name }),
        h("ul.mini-list", ...Object.entries(x.needs).map(([k, v]) => h("li", h("span", { text: GBV_NEEDS[k] || k }),
          v.status === "available" ? h("span.chip.chip--closed", { text: "Has it ready" }) : v.status === "unavailable" ? h("span.chip.chip--danger", { text: "Not available. Requested from " + (v.request_partner || "another unit") }) : h("span.chip.chip--warning", { text: "Waiting for the station" })))))));
    } else {
      c.append(h("p.muted.text-sm", { style: "margin-top:var(--space-3)", text: "No station has been asked yet. Use Dispatch or drag the file onto a station or an FCS unit." }));
    }
    return c;
  }

  function personCard(d) {
    const c = card("Person");
    const photo = (d.media || []).find((m) => m.type === "face");
    const av = h("div.avatar", { role: "img", "aria-label": "Profile photo" }, icon("user"));
    if (photo) api(`/api/staff/media/${photo.id}`).then((m) => { clear(av); av.appendChild(h("img", { src: m.data_url, alt: "" })); }).catch(() => {});
    c.append(
      h("div.person", av, h("div", h("p.person__name", { text: d.name || "Not given" }),
        h("p.muted.text-sm", d.registered ? h("span.chip.chip--info", { text: "Registered citizen" }) : null, " " + (d.name ? (photo ? "Profile photo taken on the citizen's phone" : "Name given on the report") : "No profile on this report")))),
      h("div", { style: "margin-top:var(--space-4)" }, kv([
        ["Mobile", d.mobile || "Not given"], d.home_address ? ["Home address", d.home_address] : null, ["Place of incident", d.address || "Not given"], ["Channel", d.channel + (d.language === "zu" ? " · isiZulu" : "")],
        d.friend_name || d.friend ? ["Trusted person", (d.friend_name || "") + (d.friend ? " · " + d.friend : "")] : null,
        ["Gender", GENDER[d.gender] || "Not given"], ["Age group", AGE[d.age_band] || "Not given"],
        d.contact_pref ? ["May we contact?", { call: "Yes, call", sms: "Text only", none: "No" }[d.contact_pref]] : null,
      ].filter(Boolean))),
      h("p.text-sm", { style: "margin-top:var(--space-3)" }, h("button.btn.btn--ghost", { type: "button", onclick: () => demographicsDlg(d) }, icon("users"), "Record gender and age group")),
      h("p.muted.text-sm", { text: "Used only in grouped statistics for HQ. Never shown with a name." }));
    return c;
  }

  function locationCard(d) {
    const c = card("Location");
    if (d.lat !== null && d.lat !== undefined) {
      c.append(h("div.map.map--small", h("div.map__canvas#case-map")), h("p.muted.text-sm", { style: "margin-top:var(--space-3)", text: (d.address || d.cluster_name) + " · " + d.lat.toFixed(4) + ", " + d.lon.toFixed(4) + (d.restricted ? " (shown to you because you opened the record)" : "") }));
    } else {
      c.append(h("div.banner.banner--neutral", icon("map-pin"), h("span", { text: d.address ? "No coordinates. The citizen typed: " + d.address : "Location not shared. Ask the caller where they are." })));
      if (d.kind && d.kind !== "tip") c.append(h("p.text-sm", { style: "margin-top:var(--space-3)" }, h("button.btn.btn--secondary", { type: "button", onclick: () => stationClusterDlg(d) }, icon("map-pin"), "Set station cluster")));
    }
    return c;
  }

  function drawMap(d) {
    const el = $("case-map");
    if (!el || d.lat === null || d.lat === undefined) return;
    loadLeaflet().then(() => {
      if (!$("case-map")) return;
      mapInst = L.map(el, { zoomControl: true, scrollWheelZoom: false }).setView([d.lat, d.lon], 15);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" }).addTo(mapInst);
      L.marker([d.lat, d.lon]).addTo(mapInst);
    }).catch(() => { el.appendChild(h("div.map__fallback", h("span.muted", { text: "Map unavailable offline" }))); });
  }
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

  function timelineCard(d) {
    const c = card("Timeline");
    const ol = h("ol.timeline.timeline--compact");
    (d.timeline || []).forEach((e, i, a) => {
      ol.appendChild(h("li.timeline__item.timeline__item--done" + (i === a.length - 1 ? ".timeline__item--new" : ""),
        h("span.timeline__dot", icon("check")), h("span.timeline__time", { text: hhmm(e.at) }), h("span.timeline__title", { text: e.actor }), h("span.timeline__text", { text: e.text })));
    });
    c.appendChild(ol);
    return c;
  }

  function contentCard(d, tip) {
    if (d.call) return callCard(d);
    if (d.kind === "gbv" || d.kind === "sos") {
      const ans = [];
      if (d.safe_now) ans.push(["Safe right now", { yes: "Yes, safe", no: "No, not safe", unsure: "Not sure" }[d.safe_now]]);
      if (d.wants) ans.push(["Help wanted", d.wants.length ? d.wants.map((w) => ({ social_worker: "Social worker", hospital: "Hospital or clinic", shelter: "Shelter", transport: "Transport", police: "Police to attend" })[w] || w).join(", ") : "None chosen"]);
      if (d.know_person) ans.push(["Knows who did this", { yes: "Yes", no: "No", skip: "Prefers not to say" }[d.know_person]]);
      if (d.friend) ans.push(["Friend named", "Yes (not notified in this demo)"]);
      const c = card("Citizen's answers", h("span.chip.chip--neutral", { text: d.kind === "sos" ? "Discreet SOS" : "Triage form" }));
      c.appendChild(h("ul.answers", ...ans.map((a) => h("li", h("span", { text: a[0] }), h("span", { text: a[1] })))));
      if (d.note) c.appendChild(h("p", { style: "margin-top:var(--space-3)", text: d.note }));
      c.appendChild(h("p.muted.text-sm", { style: "margin-top:var(--space-3)", text: "Believe the person. Do not ask them to repeat what they have already shared. Ask about who did this only if they choose to say." }));
      return c;
    }
    const c = card(tip ? "Tip text" : "Written report", h("span.chip.chip--neutral", { text: "Typed by the citizen" }));
    c.appendChild(h("p", { text: d.note || "No description given." }));
    if (d.occurred_at) c.appendChild(h("p.muted.text-sm", { text: "Happened around " + fmtTime(d.occurred_at) }));
    return c;
  }

  function callCard(d) {
    const call = d.call || {};
    const c = card("Call", h("span.chip.chip--neutral", { text: call.transport === "p2p" ? (call.mode === "video" ? "Live video" : "Live voice") : call.transport === "video" ? "Live video" : "Text only in this demo" }));
    if (d.name || d.mobile) c.append(h("div.caller-block", { style: "margin-bottom:var(--space-3)" }, (d.media || []).some((m) => m.type === "face") ? h("img.caller-block__photo", { src: `/api/staff/case/${d.id}/face`, alt: "Caller's profile photo", width: "56", height: "56" }) : h("span.caller-block__photo", icon("user")), h("div", h("p.caller-block__name", { text: d.name || "Caller" }), h("p.caller-block__meta", { text: [d.mobile, d.home_address].filter(Boolean).join(" · ") }), d.registered ? h("span.chip.chip--success", { text: "Registered citizen" }) : null)));
    const hasRec = (d.media || []).some((m) => m.type === "recording");
    c.append(h("p.muted.text-sm", { text: (call.mode === "video" ? "Video call" : "Voice call") + (call.operator ? " answered by " + call.operator : "") + (call.duration != null ? " · " + fmtClock(call.duration) : "") + " · Recording: " + (hasRec ? "saved on this file" : "none") }),
      h("span.chip-row", { style: "margin-bottom:var(--space-3)" },
        h("a.btn.btn--secondary", { href: `/api/staff/case/${d.id}/record.txt`, download: `call-record-${d.ref}.txt` }, icon("download"), "Download call record (.txt)"),
        h("button.btn.btn--ghost", { type: "button", onclick: () => window.print() }, "Print")),
      h("div.remote-video#remote-video", { hidden: true }));
    const ul = h("ul.transcript__list#tlist", { role: "log", "aria-live": "polite" });
    (d.transcript || []).forEach((l) => ul.appendChild(h("li.transcript__line" + (l.who === "citizen" ? ".transcript__line--you" : "") + (l.partial ? ".transcript__line--partial" : ""), h("span.transcript__who", { text: l.who === "citizen" ? "Caller" : "You (" + (call.operator || "OP") + ")" }), h("span.transcript__text", { text: l.text + (l.partial ? " …" : "") }))));
    if (!(d.transcript || []).length) ul.appendChild(h("li.transcript__empty", { text: call.state === "live" ? "Nothing said yet." : "Messages and captions appear here once the call is answered." }));
    c.append(h("div.transcript", ul));
    if (call.state === "live") {
      const form = h("form.chat-box", { onsubmit: async (e) => { e.preventDefault(); const v = $("chat-in").value.trim(); if (!v) return; $("chat-in").value = ""; try { await call_(`/api/staff/case/${d.id}/line`, { text: v }); loadDetail(S.sel, true); } catch (er) { showError(er.message); } } },
        h("input.input#chat-in", { placeholder: "Type to the caller", maxlength: "500", "aria-label": "Message to the caller" }),
        h("button.btn.btn--primary", { type: "submit" }, icon("send"), "Send"));
      c.append(form);
    }
    if (call.duration !== undefined && call.state === "ended") c.append(h("p.muted.text-sm", { text: "Duration " + fmtClock(call.duration) }));
    if (call.state === "ended" && call.answered_at && d.call_options) {
      const sel = (id, opts, value) => h("select.select#" + id, h("option", { value: "", text: "Choose…" }), ...opts.map((o) => h("option", { value: o.key, selected: o.key === value ? true : null, text: o.label })));
      c.append(h("div.wrapup", { style: "margin-top:var(--space-3)" },
        h("div.field", h("label.field__label", { for: "wu-nature", text: "Nature of the call" }), sel("wu-nature", d.call_options.natures, call.nature)),
        h("div.field", h("label.field__label", { for: "wu-outcome", text: "Action taken" }), sel("wu-outcome", d.call_options.outcomes, call.outcome)),
        h("div.field", h("label.field__label", { for: "wu-text", text: "Detail (optional)" }), h("input.input#wu-text", { type: "text", maxlength: "160", value: call.action_text || "" })),
        h("button.btn.btn--primary", { type: "button", onclick: () => { const n = $("wu-nature").value, o = $("wu-outcome").value; if (!n || !o) { toast("Choose the nature of the call and the action taken.", "error"); return; } doAct(d, "callwrap", { nature: n, outcome: o, action_text: $("wu-text").value }); } }, icon("check"), "Save for the HQ call log")));
    }
    return c;
  }
  const call_ = call;

  function deploymentsCard(d) {
    const c = card("Deployments", h("span.chip.chip--neutral", { text: "Feeds the HQ board" }));
    const list = d.deployments || [];
    if (!list.length) { c.appendChild(h("p.muted.text-sm", { text: "No station has been sent yet." })); return c; }
    const ul = h("ul.mini-list");
    list.forEach((x) => {
      const label = { dispatched: "On the way", on_scene: "On scene", cleared: "Cleared" }[x.status];
      ul.appendChild(h("li", h("span", h("b", { text: x.station_name }), " · " + x.unit + " · " + label + " · sent " + hhmm(x.dispatched_at)),
        x.status === "cleared" ? null : h("span.chip-row",
          x.status === "dispatched" ? h("button.btn.btn--secondary", { type: "button", onclick: () => depStatus(d, x, "on_scene") }, "On scene") : null,
          h("button.btn.btn--secondary", { type: "button", onclick: () => depStatus(d, x, "cleared") }, "Cleared"))));
    });
    c.appendChild(ul);
    return c;
  }
  async function depStatus(d, x, status) { try { await call(`/api/staff/case/${d.id}/deployment/${x.id}`, { status }); toast("Updated"); await refresh(); } catch (e) { showError(e.message); } }

  function referralsCard(d) {
    const c = card("Referrals out of SAPS");
    const list = d.referral_list || [];
    if (!list.length) { c.appendChild(h("p.muted.text-sm", { text: "No referral yet." })); return c; }
    c.appendChild(h("ul.mini-list", ...list.map((r) => h("li", h("span", h("b", { text: r.partner_name }), " · " + (r.urgency === "urgent" ? "urgent" : "routine") + (r.consent_to_share ? " · contact shared" : " · no contact details")), h("span.chip.chip--" + (r.status === "completed" ? "closed" : r.status === "acknowledged" ? "accepted" : "referred"), { text: r.status })))));
    return c;
  }

  function tipFlowCard(d) {
    const c = card("How this tip is moving", h("span.chip.chip--neutral", { text: "Desk then HQ" }));
    const steps = [["Received at the tip-off line", true], ["Verified by the desk", d.verification && d.verification.result === "verified"], ["Verified referral to HQ", ["referred", "acknowledged", "directed"].includes(d.status) || !!d.referred_at], ["Acknowledged by HQ", ["acknowledged", "directed"].includes(d.status)], ["Directed to a SAPS unit", d.status === "directed"], ["Closed", d.status === "closed"]];
    c.appendChild(h("ol.timeline.timeline--compact", ...steps.map((s) => h("li.timeline__item" + (s[1] ? ".timeline__item--done" : ""), h("span.timeline__dot", s[1] ? icon("check") : null), h("span.timeline__title", { text: s[0] })))));
    if (d.verification) c.appendChild(h("p.text-sm", { style: "margin-top:var(--space-3)", text: (d.verification.result === "verified" ? "Verified" : "Could not verify") + " by " + d.verification.by + ": " + d.verification.note }));
    c.appendChild(h("p.muted.text-sm", { style: "margin-top:var(--space-3)", text: "HQ sees every tip as it arrives. A verified referral lands in its action list." }));
    return c;
  }

  function mediaCard(d) {
    const c = card("Evidence and recordings", h("span.chip.chip--neutral", { text: "Saved automatically" }));
    let any = false;
    (d.media || []).forEach((m, i) => {
      if (m.type === "face") return;
      any = true;
      const slot = h("div.photo-btn", { style: "margin-bottom:var(--space-3)" });
      if (m.type === "photo") {
        slot.appendChild(h("button.btn.btn--secondary", { type: "button", onclick: async (ev) => { ev.currentTarget.disabled = true; try { const r = await api(`/api/staff/media/${m.id}`); clear(slot); slot.appendChild(h("img", { src: r.data_url, alt: "Picture sent by the citizen" })); } catch (e) { showError(e.message); } } }, icon("image"), "Show picture"));
      } else if (m.type === "video" || m.type === "recording") {
        slot.append(h("p.label-caps", { text: m.type === "recording" ? "Call recording" : "Video from the citizen" }), h("video", { controls: true, preload: "metadata", src: `/api/staff/blob/${m.id}`, style: "width:100%;border-radius:var(--radius-md);background:#000" }));
      } else if (m.type === "audio") {
        slot.append(h("p.label-caps", { text: "Audio from the citizen" }), h("audio", { controls: true, preload: "metadata", src: `/api/staff/blob/${m.id}`, style: "width:100%" }));
      }
      c.appendChild(slot);
    });
    if (!any) return h("span");
    c.appendChild(h("p.muted.text-sm", { text: "Opening evidence is logged." }));
    return c;
  }

  // ------------------------------------------------------------------ send for action (drag and drop)
  function summaryOf(sel) { return sel.kind === "tip" ? S.feed.tips.find((t) => t.id === sel.id) : S.feed.cases.find((c) => c.id === sel.id); }
  function allowed(ap, item) {
    if (item.kind === "tip") return ap.id === "hq";
    if (item.kind === "area") return ap.type === "municipal";
    return ap.type !== "municipal" && ap.id !== "hq";
  }
  function dockCard(d, tip) {
    if (d.status === "closed") return h("span");
    const item = summaryOf(S.sel) || d;
    const box = (ap, sub) => {
      const ok = allowed(ap, item);
      const b = h("button.dropbox", { type: "button", "aria-disabled": ok ? null : "true", dataset: { ap: ap.id }, title: ok ? "Drop the file here, or press to send" : "This file cannot go here" },
        h("span.dropbox__name", { text: ap.short || ap.name.replace(" (demo)", "") }), h("span.dropbox__sub", { text: sub || ap.cluster || "" }),
        h("span.dropbox__load.chip", { hidden: true }));
      b.addEventListener("click", () => { if (ok) sendTo(ap, S.sel); });
      b.addEventListener("dragover", (e) => { if (ok && S.drag) { e.preventDefault(); b.dataset.over = "true"; } });
      b.addEventListener("dragleave", () => { b.dataset.over = "false"; });
      b.addEventListener("drop", (e) => { e.preventDefault(); b.dataset.over = "false"; if (ok && S.drag) { const sel = S.drag; S.drag = null; sendTo(ap, sel); } });
      return b;
    };
    const wrap = h("section.card.card--tight.dock", { "aria-label": "Send for action" },
      h("div.card__head", h("h3.card__title", { text: "Send for action" }), h("span.drag-handle", icon("referral"), "Drag this file onto a box, or press a box")));
    if (tip) {
      wrap.appendChild(h("div.dock__boxes", box({ id: "hq", name: "HQ (Commissioner)", type: "hq", cluster: "Verified referral" }, "Verified tips only")));
      wrap.appendChild(h("p.muted.text-sm", { text: "A tip goes to HQ only after you verify it. HQ sees every tip anyway." }));
      paintLoads(); return wrap;
    }
    const byType = (f) => S.points.filter(f);
    // The most used targets stay in view; everything else folds away so the page stays short.
    const gbvQuick = ["fcs_unit", "gbv_tcc", "social_worker", "shelter", "health", "forensic_supply", "transport"];
    const quick = isGbv(d.kind) ? byType((ap) => gbvQuick.includes(ap.type)) : byType((ap) => ap.group === "SAPS units" && ap.type !== "saps_cluster");
    wrap.appendChild(h("div.dock__quick", ...quick.map((ap) => box(ap, ap.cluster))));
    const sub = (title, list) => list.length ? h("div.dock__sub", h("p.label-caps", { text: title + " (" + list.length + ")" }), h("div.dock__boxes", ...list.map((ap) => box(ap)))) : null;
    wrap.appendChild(h("details.dock__group", { open: d.kind === "gbv" || d.kind === "sos" || d.kind === "area" ? true : null },
      h("summary.label-caps", { style: "cursor:pointer;min-height:1.75rem;display:flex;align-items:center", text: "More places to send: stations, cluster commanders, partners" }),
      h("div.stack.stack--3", { style: "margin-top:var(--space-2)" },
        sub("Police stations", byType((ap) => ap.type === "station")),
        sub("Cluster commanders", byType((ap) => ap.type === "saps_cluster")),
        sub("Partners outside SAPS", byType((ap) => ap.group === "Partners outside SAPS")))));
    setTimeout(paintLoads, 0);
    return wrap;
  }

  async function sendTo(ap, sel) {
    const item = summaryOf(sel);
    if (!item) return;
    S.sel = sel;
    if (ap.id === "hq") {
      if (item.status !== "verified") return toast("Verify the tip first. Only a verified tip is referred to HQ.", "error");
      return tipRefer({ id: item.id, ref: item.ref });
    }
    const d = { id: item.id, kind: item.kind, ref: item.ref, priority: item.priority, has_contact: item.has_contact, mobile: "", suggested_station: null };
    if (ap.type === "station") {
      const gbvF = isGbv(item.kind) ? Object.entries(GBV_NEEDS).map(([k, label]) => ({ id: "need_" + k, type: "checkbox", label, checked: ["female_officer", "counsellor"].includes(k) })) : [];
      const v = await ask({ title: "Send " + item.ref + " to " + ap.name, body: "The station will see this task on its own page and acknowledge it." + ((item.call_mode || item.has_media) ? " The folder goes with it: call record, recording and any evidence." : "") + " Demo: nobody is really dispatched.",
        fields: [{ id: "unit", type: "select", label: "Unit asked for", value: item.kind === "gbv" ? "FCS unit" : "Patrol vehicle", options: ((await getStations()).units).map((u) => ({ value: u, label: u })) }, { id: "note", type: "text", label: "Instruction", hint: "One line for the officers." }, ...gbvF], ok: "Send to the station" });
      if (v && gbvF.length) v.needs = Object.keys(GBV_NEEDS).filter((k) => v["need_" + k]);
      if (v) guarded(async () => { await call(`/api/staff/case/${item.id}/dispatch`, { station: ap.station, unit: v.unit, note: v.note, needs: v.needs }); toast("Sent to " + ap.name); });
      return;
    }
    const v = await ask({ title: "Send " + item.ref + " to " + ap.name, body: "It appears on this action point's page. You stay the owner until they acknowledge." + ((item.call_mode || item.has_media) ? " The folder goes with it: call record, recording and any evidence." : "") + " Demo: nothing is really sent.",
      fields: [
        { id: "urgency", type: "select", label: "Urgency", value: item.priority === "critical" ? "urgent" : "routine", options: [{ value: "routine", label: "Routine" }, { value: "urgent", label: "Urgent (15 minute limit)" }] },
        { id: "note", type: "text", label: "Note" },
      ].filter(Boolean), ok: "Send" });
    if (v) guarded(async () => { await call(`/api/staff/case/${item.id}/refer`, Object.assign({ partner_id: ap.id }, v)); toast("Sent to " + ap.name); });
  }

  // ------------------------------------------------------------------ dialogs
  const dlg = $("act-dlg");
  /** Asks the officer for input. fields: [{id, type, label, options, value, hint, checked}]. Resolves to {id: value} or null. */
  function ask({ title, body, fields, ok }) {
    return new Promise((resolve) => {
      $("act-title").textContent = title; $("act-body").textContent = body || "";
      $("act-ok").textContent = ok || "Confirm"; $("act-error").hidden = true;
      const box = $("act-fields"); clear(box); box.className = "dlg-fields";
      (fields || []).forEach((f) => {
        let control;
        if (f.type === "select") { control = h("select.select", { id: "af-" + f.id }, ...f.options.map((o) => h("option", { value: o.value, selected: o.value === f.value ? true : null, text: o.label }))); }
        else if (f.type === "textarea") { control = h("textarea.textarea", { id: "af-" + f.id, rows: "3", maxlength: "300" }); control.value = f.value || ""; }
        else if (f.type === "checkbox") { control = h("label.choice", h("input", { type: "checkbox", id: "af-" + f.id, checked: f.checked ? true : null }), h("span", h("span.choice__title", { text: f.label }), f.hint ? h("span.choice__hint", { text: f.hint }) : null)); box.appendChild(control); return; }
        else { control = h("input.input", { id: "af-" + f.id, type: "text", maxlength: "300" }); control.value = f.value || ""; }
        box.appendChild(h("div.field", h("label.field__label", { for: "af-" + f.id, text: f.label }), control, f.hint ? h("p.field__hint", { text: f.hint }) : null));
      });
      const done = (val) => { dlg.removeEventListener("close", onClose); $("act-form").onsubmit = null; $("act-cancel").onclick = null; resolve(val); };
      const onClose = () => done(null);
      dlg.addEventListener("close", onClose);
      $("act-cancel").onclick = () => dlg.close();
      $("act-form").onsubmit = (e) => {
        e.preventDefault();
        const vals = {};
        (fields || []).forEach((f) => { const el = $("af-" + f.id); vals[f.id] = f.type === "checkbox" ? el.checked : el.value; });
        dlg.removeEventListener("close", onClose); dlg.close(); done(vals);
      };
      dlg.showModal();
    });
  }

  async function guarded(fn) { try { await fn(); await refresh(); if (S.sel) await loadDetail(S.sel, true); } catch (e) { if (!e.offline) toast(e.message, "error"); else toast("No connection. Try again.", "error"); } }

  function doAct(d, action, extra) { return guarded(async () => { await call(`/api/staff/case/${d.id}/action`, Object.assign({ action }, extra || {})); toast(action === "accept" ? d.ref + " accepted" : "Done"); }); }

  async function closeDlg(d) {
    const v = await ask({ title: "Close this case", body: "Closing removes it from the queue. The file and timeline stay on record.", fields: [{ id: "note", type: "text", label: "Outcome", hint: "For example: resolved, no further action, duplicate." }], ok: "Close case" });
    if (v) doAct(d, "close", { note: v.note });
  }

  async function stationClusterDlg(d) {
    const st = await getStations();
    const clusters = [];
    st.stations.forEach((s) => { if (!clusters.some((c) => c.value === s.cluster)) clusters.push({ value: s.cluster, label: s.cluster.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase()) }); });
    const v = await ask({ title: "Set station cluster", body: "The caller's location is not known. Choose the cluster that will handle this.", fields: [{ id: "cluster", type: "select", label: "Cluster", options: clusters }], ok: "Set cluster" });
    if (v) doAct(d, "station", { cluster: v.cluster });
  }

  async function demographicsDlg(d) {
    const v = await ask({
      title: "Record gender and age group", body: "Optional. Used only in grouped statistics for HQ, never next to a name. Record what the person tells you.",
      fields: [
        { id: "gender", type: "select", label: "Gender", value: d.gender, options: Object.entries(GENDER).map(([value, label]) => ({ value, label })) },
        { id: "age_band", type: "select", label: "Age group", value: d.age_band, options: Object.entries(AGE).map(([value, label]) => ({ value, label })) },
      ], ok: "Save",
    });
    if (v) doAct(d, "demographics", v);
  }

  async function getStations() { if (!S.stations) S.stations = await api("/api/staff/stations"); return S.stations; }
  async function getPartners() { if (!S.partners) S.partners = await api("/api/staff/partners"); return S.partners; }

  async function dispatchDlg(d) {
    const st = await getStations();
    const near = d.suggested_station || "";
    const gbvFields = isGbv(d.kind) ? Object.entries(GBV_NEEDS).map(([k, label]) => ({ id: "need_" + k, type: "checkbox", label, checked: (d.needs || []).includes(k) })) : [];
    const v = await ask({
      title: "Send a station", body: "Choose the station and the kind of unit. The call record, recording and any evidence go with the file. The times you record here feed HQ's response figures. Demo: nobody is really dispatched.",
      fields: [
        { id: "station", type: "select", label: "Station", value: near, options: st.stations.map((s) => ({ value: s.key, label: s.name + (s.key === near ? " (nearest)" : "") })) },
        { id: "unit", type: "select", label: "Unit", value: d.kind === "gbv" ? "FCS unit" : "Patrol vehicle", options: st.units.map((u) => ({ value: u, label: u })) },
        ...(gbvFields.length ? [{ id: "needs_h", type: "text", label: "The station must say whether it has these ready", hint: "Tick what this file needs. If the station does not have one, the request goes out automatically and HQ sees it." }, ...gbvFields] : []),
      ], ok: "Dispatch",
    });
    if (v && gbvFields.length) { v.needs = Object.keys(GBV_NEEDS).filter((k) => v["need_" + k]); }
    if (v) guarded(async () => { await call(`/api/staff/case/${d.id}/dispatch`, { station: v.station, unit: v.unit, note: v.note, needs: v.needs }); toast("Dispatched from " + (st.stations.find((s) => s.key === v.station) || {}).name); });
  }

  async function referDlg(d) {
    const p = await getPartners();
    const allowed = p.partners.filter((x) => (d.kind === "area" ? x.type === "municipal" : x.type !== "municipal"));
    const v = await ask({
      title: "Refer this case", body: "Pass it to the right service. You stay the owner until they acknowledge. Demo: nothing is dispatched.",
      fields: [
        { id: "partner_id", type: "select", label: "Refer to", options: allowed.map((x) => ({ value: x.id, label: (p.types[x.type] || x.type) + ": " + x.name })) },
        { id: "urgency", type: "select", label: "Urgency", value: d.priority === "critical" ? "urgent" : "routine", options: [{ value: "routine", label: "Routine" }, { value: "urgent", label: "Urgent (15 minute limit)" }] },
        d.has_contact || d.mobile ? { id: "consent_to_share", type: "checkbox", label: "The citizen agreed to share their contact details", hint: "Leave unticked if they did not agree. The partner then sees the place and note only." } : null,
        { id: "note", type: "text", label: "Note for the partner" },
      ].filter(Boolean), ok: "Refer case",
    });
    if (v) guarded(async () => { await call(`/api/staff/case/${d.id}/refer`, v); toast("Referred"); });
  }

  async function tipVerify(d) {
    const v = await ask({ title: "Verify this tip", body: "Check it against what you know. Say how you checked. Only a verified tip can be referred to HQ.",
      fields: [{ id: "result", type: "select", label: "Result", options: [{ value: "verified", label: "Verified" }, { value: "not_verified", label: "Could not verify" }] }, { id: "note", type: "textarea", label: "How you checked it" }], ok: "Save result" });
    if (v) guarded(async () => { await call(`/api/staff/tip/${d.id}/verify`, v); toast("Saved"); });
  }
  async function tipAction(d) {
    const v = await ask({ title: "Record action taken", body: "What did the desk do with this tip?", fields: [{ id: "note", type: "textarea", label: "Action" }], ok: "Save" });
    if (v) guarded(async () => { await call(`/api/staff/tip/${d.id}/action`, v); toast("Saved"); });
  }
  async function tipRefer(d) {
    const v = await ask({ title: "Refer to HQ", body: "This sends a verified referral to HQ for its action. HQ already sees the tip itself.", fields: [{ id: "note", type: "textarea", label: "Why HQ should act (optional)" }], ok: "Send to HQ" });
    if (v) guarded(async () => { await call(`/api/staff/tip/${d.id}/refer-hq`, v); toast("Verified referral sent to HQ"); });
  }
  async function tipClose(d) {
    const v = await ask({ title: "Close this tip", body: "The citizen can see the outcome if they check with their code.", fields: [{ id: "outcome", type: "select", label: "Outcome", options: [{ value: "used", label: "The information was used" }, { value: "no_action", label: "Not enough to act on" }, { value: "duplicate", label: "Matched another tip" }, { value: "not_verified", label: "Could not be verified" }] }], ok: "Close tip" });
    if (v) guarded(async () => { await call(`/api/staff/tip/${d.id}/close`, v); toast("Closed"); });
  }

  boot();
})();
