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
  const PRIO_NUM = { critical: 1, high: 2, normal: 3, low: 4 };
  const PRIO_WORD = { critical: "Critical", high: "High", normal: "Medium", low: "Routine" };
  const STATUS_WORD = { new: "New", assigned: "Accepted", in_progress: "In progress", referred: "Referred", closed: "Closed", verified: "Verified", acknowledged: "With HQ", directed: "Directed" };
  const STATUS_CHIP = { new: "new", assigned: "accepted", in_progress: "accepted", referred: "referred", closed: "closed", verified: "accepted", acknowledged: "referred", directed: "referred" };
  const TIP_WORD = { new: "New", verified: "Verified", referred: "Referred to HQ", acknowledged: "With HQ", directed: "Directed by HQ", closed: "Closed" };
  const GENDER = { female: "Female", male: "Male", other: "Other / self-described", undisclosed: "Not given" };
  const AGE = { under_18: "Under 18", "18_24": "18-24", "25_34": "25-34", "35_49": "35-49", "50_64": "50-64", "65_plus": "65+", undisclosed: "Not given" };

  const S = { selfie: "", points: [], drag: null, recStream: null, recorder: null, me: null, feed: null, version: null, door: "calls", filter: "all", sel: null, detail: null, opened: new Set(), ringing: new Set(), stop: null, partners: null, stations: null, room: null, recog: null };

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
          h("span.queue-row__meta", h("span.ref", { text: c.ref }), h("span.chip.chip--dot.chip--" + chip, { text: word + (c.call_state === "ringing" ? " (ringing)" : "") }))),
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

  // ------------------------------------------------------------------ incoming calls
  let ringTimer = null;
  function renderIncoming() {
    const wrap = $("incoming-wrap"); clear(wrap);
    const ringing = S.feed.cases.filter((c) => c.call_state === "ringing");
    ringing.forEach((c) => {
      if (!S.ringing.has(c.id)) { S.ringing.add(c.id); sound.ring(); announce("Incoming call " + c.ref); }
      const waited = nowSec() - c.created_at;
      wrap.appendChild(h("div.incoming-call", { role: "alert" },
        h("div", h("p.incoming-call__name", { text: (c.call_mode === "video" ? "Video call" : "Voice call") + " · " + c.ref }),
          h("p.incoming-call__meta", c.cluster_name + (c.has_contact ? " · profile attached" : " · no profile"))),
        h("div.incoming-call__actions", h("p.incoming-call__timer.num", { "aria-label": "Waiting time" }, fmtClock(waited)),
          h("button.btn.btn--answer.btn--lg.btn--block", { type: "button", onclick: () => answer(c, false) }, icon("phone"), "Answer"),
          S.me.video && c.call_mode === "video" ? h("button.btn.btn--secondary.btn--block", { type: "button", onclick: () => answer(c, true) }, icon("video"), "Answer with video") : null)));
    });
    for (const id of Array.from(S.ringing)) if (!ringing.some((c) => c.id === id)) S.ringing.delete(id);
    clearInterval(ringTimer);
    if (ringing.length) ringTimer = setInterval(() => { sound.ring(); document.querySelectorAll(".incoming-call__timer").forEach((el, i) => { el.textContent = fmtClock(Date.now() / 1000 - ringing[i].created_at - (Date.now() / 1000 - (S.feed.now))); }); }, 4000);
  }

  async function answer(c, video) {
    try {
      const r = await call(`/api/staff/case/${c.id}/answer`, { video });
      toast("Call answered. You are connected to the caller.");
      setDoor("calls"); select({ id: c.id, kind: "case" });
      if (r.transport === "video") joinVideo(r.token, r.room, c.call_mode, c.id);
      await refresh();
    } catch (e) { showError(e.message); }
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
  function startCaptions() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR || S.recog || !S.sel) return;
    const id = S.sel.id;
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
    right.appendChild(timelineCard(d));
    right.appendChild(contentCard(d, tip));
    if (tip) right.appendChild(tipFlowCard(d)); else right.appendChild(referralsCard(d));
    if (d.media && d.media.length) right.appendChild(mediaCard(d));
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

  function personCard(d) {
    const c = card("Person");
    const photo = (d.media || []).find((m) => m.type === "face");
    const av = h("div.avatar", { role: "img", "aria-label": "Profile photo" }, icon("user"));
    if (photo) api(`/api/staff/media/${photo.id}`).then((m) => { clear(av); av.appendChild(h("img", { src: m.data_url, alt: "" })); }).catch(() => {});
    c.append(
      h("div.person", av, h("div", h("p.person__name", { text: d.name || "Not given" }), h("p.muted.text-sm", { text: d.name ? (photo ? "Profile photo taken on the citizen's phone" : "Name given on the report") : "No profile on this report" }))),
      h("div", { style: "margin-top:var(--space-4)" }, kv([
        ["Mobile", d.mobile || "Not given"], ["Address", d.address || "Not given"], ["Channel", d.channel + (d.language === "zu" ? " · isiZulu" : "")],
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
    const c = card("Call", h("span.chip.chip--neutral", { text: call.transport === "video" ? "Live video" : "Text only in this demo" }));
    c.append(h("div.remote-video#remote-video", { hidden: true }));
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
    const groups = {};
    S.points.forEach((ap) => { (groups[ap.group] = groups[ap.group] || []).push(ap); });
    const order = ["SAPS units", "Police stations", "Partners outside SAPS"];
    order.forEach((g) => {
      let list = groups[g] || [];
      if (!list.length) return;
      if (g === "SAPS units") list = list.filter((ap) => ap.type !== "saps_cluster").concat(list.filter((ap) => ap.type === "saps_cluster"));
      const boxes = h("div.dock__boxes", ...list.map((ap) => box(ap, ap.type === "station" ? ap.cluster : undefined)));
      const open = g === "SAPS units" || (g === "Partners outside SAPS" && d.kind !== "crime") || (g === "Police stations" && d.kind !== "area");
      wrap.appendChild(h("details.dock__group", { open: open ? true : null }, h("summary.label-caps", { style: "cursor:pointer;min-height:2rem;display:flex;align-items:center", text: g + " (" + list.length + ")" }), boxes));
    });
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
      const v = await ask({ title: "Send " + item.ref + " to " + ap.name, body: "The station will see this task on its own page and acknowledge it. Demo: nobody is really dispatched.",
        fields: [{ id: "unit", type: "select", label: "Unit asked for", value: item.kind === "gbv" ? "FCS unit" : "Patrol vehicle", options: ((await getStations()).units).map((u) => ({ value: u, label: u })) }, { id: "note", type: "text", label: "Instruction", hint: "One line for the officers." }], ok: "Send to the station" });
      if (v) guarded(async () => { await call(`/api/staff/case/${item.id}/dispatch`, { station: ap.station, unit: v.unit, note: v.note }); toast("Sent to " + ap.name); });
      return;
    }
    const v = await ask({ title: "Send " + item.ref + " to " + ap.name, body: "It appears on this action point's page. You stay the owner until they acknowledge. Demo: nothing is really sent.",
      fields: [
        { id: "urgency", type: "select", label: "Urgency", value: item.priority === "critical" ? "urgent" : "routine", options: [{ value: "routine", label: "Routine" }, { value: "urgent", label: "Urgent (15 minute limit)" }] },
        item.has_contact ? { id: "consent_to_share", type: "checkbox", label: "The citizen agreed to share their contact details", hint: "Leave unticked if they did not agree." } : null,
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
    const v = await ask({
      title: "Send a station", body: "Choose the station and the kind of unit. The times you record here feed HQ's response figures. Demo: nobody is really dispatched.",
      fields: [
        { id: "station", type: "select", label: "Station", value: near, options: st.stations.map((s) => ({ value: s.key, label: s.name + (s.key === near ? " (nearest)" : "") })) },
        { id: "unit", type: "select", label: "Unit", value: d.kind === "gbv" ? "FCS unit" : "Patrol vehicle", options: st.units.map((u) => ({ value: u, label: u })) },
      ], ok: "Dispatch",
    });
    if (v) guarded(async () => { await call(`/api/staff/case/${d.id}/dispatch`, v); toast("Dispatched from " + (st.stations.find((s) => s.key === v.station) || {}).name); });
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
