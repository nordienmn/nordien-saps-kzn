/* Citizen app. One page, several views, hash routes so the back button works. */
(function () {
  "use strict";
  const { h, clear, api, announce, shrinkImage, store, fmtClock } = window.SAPS;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const VIEWS = ["home", "crime", "gbv", "anon", "area", "profile", "done"];
  const KZN = { latMin: -31.2, latMax: -26.7, lonMin: 28.8, lonMax: 33.0 };

  let lang = store("saps-lang") || "en";
  let config = null;

  // ------------------------------------------------------------------ language
  const t = (k, vars) => {
    let s = (window.CITIZEN_I18N[lang] || {})[k];
    if (s === undefined) s = window.CITIZEN_I18N.en[k] || k;
    if (vars) for (const [a, b] of Object.entries(vars)) s = s.replace("{" + a + "}", b);
    return s;
  };

  function applyI18n(root) {
    root = root || document;
    $$("[data-i18n]", root).forEach((el) => { el.textContent = t(el.dataset.i18n); });
    // These strings are fixed text written by us (they contain <b> tags), never citizen input.
    $$("[data-i18n-html]", root).forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
    $$("[data-i18n-aria]", root).forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
    $$("[data-lang]", root).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
    document.documentElement.lang = lang === "zu" ? "zu" : "en";
  }

  function setLang(next) {
    lang = next;
    store("saps-lang", next);
    applyI18n();
    fillSelects();
    renderProfileHints();
    if (call) paintCall();
  }

  // ------------------------------------------------------------------ views
  function show(view) {
    if (!VIEWS.includes(view)) view = "home";
    $$("[data-view]").forEach((s) => { s.hidden = s.dataset.view !== view; });
    const sec = $(`[data-view="${view}"]`);
    window.scrollTo(0, 0);
    const heading = $("h1", sec);
    if (heading) { heading.setAttribute("tabindex", "-1"); heading.focus({ preventScroll: true }); }
    if (view === "crime") openCrime();
    if (view === "gbv") openGbv();
    if (view === "profile") openProfile();
  }
  function route() { if (callOpen) return; show((location.hash || "#home").slice(1)); }
  function go(view) { if (location.hash === "#" + view) route(); else location.hash = view; }
  window.addEventListener("hashchange", route);
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-go]");
    if (b) { e.preventDefault(); go(b.dataset.go); }
  });

  // ------------------------------------------------------------------ privacy notice
  const notice = $("#notice");
  function openNotice() { if (!notice.open) { notice.showModal(); $("#notice-title").focus(); } }
  $("#agree").addEventListener("click", () => { try { sessionStorage.setItem("saps-notice", "1"); } catch (e) { /* ok */ } notice.close(); });
  // A consent gate must be answered, so Esc does not dismiss it. "Call 10111" stays available inside it.
  notice.addEventListener("cancel", (e) => e.preventDefault());
  $("#open-notice").addEventListener("click", openNotice);
  $$("[data-lang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));

  // ------------------------------------------------------------------ config and selects
  function fillSelect(sel, items, placeholder) {
    const keep = sel.value;
    clear(sel);
    sel.appendChild(h("option", { value: "", text: placeholder }));
    items.forEach((it) => sel.appendChild(h("option", { value: it.key, text: it[lang] || it.en })));
    sel.value = keep;
  }
  function fillSelects() {
    if (!config) return;
    fillSelect($("#c-type"), config.crime_types, t("fTypePick"));
    fillSelect($("#a-type"), config.tip_types, t("fTypePick"));
    fillSelect($("#u-type"), config.area_types, t("fTypePick"));
  }
  async function loadConfig() {
    try { config = await api("/api/c/config"); } catch (e) { config = { crime_types: [], tip_types: [], area_types: [], whatsapp: {} }; }
    fillSelects();
    const wa = config.whatsapp || {};
    if (wa.enabled && wa.display) {
      $("#wa-card").hidden = false;
      $("#wa-num").textContent = wa.display;
      $("#wa-hint").textContent = wa.join_hint || "";
    }
  }

  // ------------------------------------------------------------------ errors
  function fieldError(id, text) {
    const wrap = $("#" + id)?.closest(".field");
    const msg = $("#" + id + "-e") || (wrap && $(".field__error", wrap));
    if (wrap) wrap.classList.toggle("field--error", !!text);
    if (msg) msg.textContent = text || "";
    if ($("#" + id)) $("#" + id).setAttribute("aria-invalid", text ? "true" : "false");
  }
  function formError(id, text) {
    const el = $("#" + id);
    el.hidden = !text;
    el.replaceChildren(...(text ? [window.SAPS.icon("alert", "icon--sm"), document.createTextNode(text)] : []));
  }
  function mapError(prefix, err) {
    if (err.offline) return formError(prefix + "-error", t("errOffline"));
    if (err.field === "type") return fieldError(prefix + "-type", t(prefix === "u" ? "errType" : "errType"));
    if (err.field === "place") return formError(prefix + "-error", t("errPlace"));
    if (err.field === "mobile") return formError(prefix + "-error", t("errMobile"));
    formError(prefix + "-error", err.message && !err.offline && err.status && err.status < 500 ? err.message : t("errGeneric"));
  }
  async function submitting(btn, fn) {
    const label = btn.textContent;
    btn.disabled = true; btn.textContent = t("sending");
    try { return await fn(); } finally { btn.disabled = false; btn.textContent = label; }
  }

  // ------------------------------------------------------------------ location widget
  const whereState = {}; // prefix -> {lat, lon}
  function inKzn(lat, lon) { return lat >= KZN.latMin && lat <= KZN.latMax && lon >= KZN.lonMin && lon <= KZN.lonMax; }
  function getPosition(timeout) {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) return reject(new Error("off"));
      navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: timeout || 8000, maximumAge: 60000 });
    });
  }
  function initWhere(root) {
    const prefix = root.dataset.where;
    const status = $("[data-where-status]", root);
    const mapBox = $("[data-where-mapbox]", root);
    let map = null, marker = null;
    const setStatus = (text, ok) => { status.textContent = text; status.dataset.ok = ok ? "true" : "false"; };
    const setPoint = (lat, lon, text) => {
      if (!inKzn(lat, lon)) { setStatus(t("errPlace"), false); whereState[prefix] = null; return false; }
      whereState[prefix] = { lat, lon };
      setStatus(text || t("hereSet"), true);
      return true;
    };
    $("[data-where-here]", root).addEventListener("click", async () => {
      setStatus(t("hereWait"), false);
      try {
        const pos = await getPosition(8000);
        if (setPoint(pos.coords.latitude, pos.coords.longitude, t("hereSet") + " (±" + Math.round(pos.coords.accuracy) + " m)") && map) { marker.setLatLng([pos.coords.latitude, pos.coords.longitude]); map.setView([pos.coords.latitude, pos.coords.longitude], 16); }
      } catch (e) { setStatus(e && e.code === 1 ? t("hereOff") : t("hereFail"), false); }
    });
    $("[data-where-map]", root).addEventListener("click", async () => {
      mapBox.hidden = !mapBox.hidden;
      if (mapBox.hidden || map) { if (map) setTimeout(() => map.invalidateSize(), 50); return; }
      setStatus(t("mapHint"), false);
      try { await loadLeaflet(); } catch (e) { mapBox.hidden = true; return setStatus(t("hereFail"), false); }
      const start = whereState[prefix] || { lat: -29.8587, lon: 31.0218 };
      map = L.map(mapBox).setView([start.lat, start.lon], whereState[prefix] ? 16 : 11);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(map);
      marker = L.marker([start.lat, start.lon], { draggable: true, keyboard: true, title: t("mapHint") }).addTo(map);
      marker.on("dragend", () => { const p = marker.getLatLng(); setPoint(+p.lat.toFixed(5), +p.lng.toFixed(5)); });
      map.on("click", (ev) => { marker.setLatLng(ev.latlng); setPoint(+ev.latlng.lat.toFixed(5), +ev.latlng.lng.toFixed(5)); });
    });
  }
  let leafletPromise = null;
  function loadLeaflet() {
    if (window.L) return Promise.resolve();
    if (leafletPromise) return leafletPromise;
    leafletPromise = new Promise((resolve, reject) => {
      document.head.appendChild(h("link", { rel: "stylesheet", href: "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css", integrity: "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=", crossorigin: "" }));
      const s = h("script", { src: "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js", integrity: "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=", crossorigin: "" });
      s.onload = resolve; s.onerror = () => { leafletPromise = null; reject(new Error("map")); };
      document.head.appendChild(s);
    });
    return leafletPromise;
  }
  function whereValue(prefix) {
    const p = whereState[prefix];
    return { lat: p ? p.lat : null, lon: p ? p.lon : null, address: $("#" + prefix + "-place").value.trim() };
  }
  function resetWhere(prefix) {
    whereState[prefix] = null;
    $("#" + prefix + "-place").value = "";
    const st = $(`[data-where="${prefix}"] [data-where-status]`);
    st.textContent = ""; st.dataset.ok = "false";
  }

  // ------------------------------------------------------------------ photos widget
  const photoState = {}; // prefix -> [dataUrl]
  function initPhotos(root) {
    const prefix = root.dataset.photos;
    const max = +root.dataset.max || 3;
    const input = $("[data-photo-input]", root), thumbs = $("[data-thumbs]", root), add = $("[data-photo-add]", root);
    if (!input) return;
    photoState[prefix] = [];
    const render = () => {
      clear(thumbs);
      photoState[prefix].forEach((src, i) => {
        const img = h("img", { src, alt: "" });
        thumbs.appendChild(h("div.thumb", img, h("button", { type: "button", "aria-label": t("fRemove"), onclick: () => { photoState[prefix].splice(i, 1); render(); } }, window.SAPS.icon("close"))));
      });
      add.hidden = photoState[prefix].length >= max;
    };
    add.addEventListener("click", () => input.click());
    input.addEventListener("change", async () => {
      const f = input.files && input.files[0];
      input.value = "";
      if (!f || photoState[prefix].length >= max) return;
      try { photoState[prefix].push(await shrinkImage(f, 1280, 0.7)); render(); } catch (e) { toast(e.message); }
    });
    root._reset = () => { photoState[prefix] = []; render(); };
  }

  function toast(msg) {
    const el = h("div.toast", window.SAPS.icon("info"), h("span", { text: msg }));
    $("#toasts").appendChild(el);
    setTimeout(() => { el.classList.add("toast--out"); setTimeout(() => el.remove(), 200); }, 3200);
  }

  // ------------------------------------------------------------------ profile
  const getProfile = () => store("saps-profile");
  let profileFace = "";
  function renderProfileHints() {
    const p = getProfile();
    $("#c-profile-row").hidden = !p;
    $("#c-noprofile").hidden = !!p;
    if (p) $("#c-profile-who").textContent = p.name + (p.mobile ? " · " + p.mobile : "");
    $("#p-take-l").textContent = t(profileFace ? "pRetake" : "pTake");
  }
  function openProfile() {
    const p = getProfile() || {};
    $("#p-name").value = p.name || ""; $("#p-mobile").value = p.mobile || ""; $("#p-addr").value = p.addr || "";
    profileFace = p.face || "";
    paintAvatar();
    formError("p-error", "");
    renderProfileHints();
  }
  function paintAvatar() {
    const av = $("#p-avatar");
    clear(av);
    av.appendChild(profileFace ? h("img", { src: profileFace, alt: "" }) : window.SAPS.icon("user", "icon--xl"));
  }
  $("#p-take").addEventListener("click", () => $("#p-file").click());
  $("#p-file").addEventListener("change", async (e) => {
    const f = e.target.files && e.target.files[0]; e.target.value = "";
    if (!f) return;
    try { profileFace = await shrinkImage(f, 480, 0.7); paintAvatar(); renderProfileHints(); } catch (err) { toast(err.message); }
  });
  $("#f-profile").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = $("#p-name").value.trim(), mobile = $("#p-mobile").value.trim();
    if (!name || !mobile) return formError("p-error", t("pNeed"));
    store("saps-profile", { name, mobile, addr: $("#p-addr").value.trim(), face: profileFace });
    toast(t("pSaved")); renderProfileHints(); go("home");
  });
  $("#p-clear").addEventListener("click", () => { store("saps-profile", null); profileFace = ""; toast(t("pCleared")); renderProfileHints(); go("home"); });

  // ------------------------------------------------------------------ crime report (with draft)
  const DRAFT = "saps-draft-crime";
  function nowLocalInput() { const d = new Date(Date.now() - new Date().getTimezoneOffset() * 60000); return d.toISOString().slice(0, 16); }
  function saveDraft() {
    const d = { type: $("#c-type").value, place: $("#c-place").value, text: $("#c-text").value, pt: whereState.c };
    if (d.type || d.place.trim() || d.text.trim()) store(DRAFT, d); else store(DRAFT, null);
  }
  function openCrime() {
    $("#c-time").value = nowLocalInput();
    $("#c-time").max = nowLocalInput();
    formError("c-error", ""); fieldError("c-type", "");
    const d = store(DRAFT);
    $("#c-draft").hidden = !(d && !$("#c-type").value && !$("#c-text").value);
    renderProfileHints();
  }
  $("#c-draft-yes").addEventListener("click", () => {
    const d = store(DRAFT) || {};
    $("#c-type").value = d.type || ""; $("#c-place").value = d.place || ""; $("#c-text").value = d.text || "";
    if (d.pt) { whereState.c = d.pt; const st = $('[data-where="c"] [data-where-status]'); st.textContent = t("hereSet"); st.dataset.ok = "true"; }
    $("#c-draft").hidden = true;
  });
  $("#c-draft-no").addEventListener("click", () => { store(DRAFT, null); $("#c-draft").hidden = true; });
  ["c-type", "c-place", "c-text"].forEach((id) => $("#" + id).addEventListener("input", saveDraft));

  $("#f-crime").addEventListener("submit", async (e) => {
    e.preventDefault();
    formError("c-error", ""); fieldError("c-type", "");
    const type = $("#c-type").value, w = whereValue("c");
    if (!type) { fieldError("c-type", t("errType")); return $("#c-type").focus(); }
    if (w.lat === null && !w.address) return formError("c-error", t("errPlace"));
    const p = getProfile(), useProfile = p && $("#c-profile").checked;
    const timeVal = $("#c-time").value;
    const body = { kind: "crime", type, ...w, note: $("#c-text").value.trim(), photos: photoState.c || [] };
    if (timeVal) body.occurred_at = new Date(timeVal).getTime();
    if (useProfile) { body.name = p.name; body.mobile = p.mobile; if (p.face) body.face = p.face; }
    try {
      const r = await submitting($("#c-submit"), () => api("/api/c/report", { body }));
      store(DRAFT, null);
      $("#f-crime").reset(); resetWhere("c"); $('[data-photos="c"]')._reset();
      showDone({ title: t("doneT"), body: t("doneDemo"), ref: r.ref });
    } catch (err) { mapError("c", err); }
  });

  // ------------------------------------------------------------------ gbv
  function openGbv() {
    formError("g-error", "");
    const p = getProfile();
    if (p && !$("#g-mobile").value) $("#g-mobile").value = p.mobile || "";
  }
  $$('input[name="safe"]').forEach((r) => r.addEventListener("change", () => { $("#g-danger").hidden = r.value !== "no" || !r.checked; $("#g-safe-e").textContent = ""; }));
  $$('input[name="contact"]').forEach((r) => r.addEventListener("change", () => { $("#g-mobile-f").hidden = $('input[name="contact"]:checked').value === "none"; }));
  $("#g-call").addEventListener("click", () => startCall("voice"));
  $("#g-exit").addEventListener("click", () => {
    try { sessionStorage.clear(); localStorage.removeItem(DRAFT); } catch (e) { /* ok */ }
    location.replace("/weather");
  });
  $("#f-gbv").addEventListener("submit", async (e) => {
    e.preventDefault();
    formError("g-error", ""); $("#g-safe-e").textContent = ""; fieldError("g-mobile", "");
    const safe = ($('input[name="safe"]:checked') || {}).value;
    if (!safe) { $("#g-safe-e").textContent = t("gSafeQ"); return $('input[name="safe"]').focus(); }
    const pref = $('input[name="contact"]:checked').value, mobile = $("#g-mobile").value.trim();
    if (pref !== "none" && !mobile) { fieldError("g-mobile", t("errMobile")); return $("#g-mobile").focus(); }
    const p = getProfile();
    const body = {
      kind: "gbv", safe_now: safe, wants: $$('input[name="wants"]:checked').map((i) => i.value),
      know_person: $('input[name="know"]:checked').value, note: $("#g-text").value.trim(),
      contact_pref: pref, mobile: pref === "none" ? "" : mobile, name: pref !== "none" && p ? p.name : "", ...whereValue("g"),
    };
    try {
      const r = await submitting($("#g-submit"), () => api("/api/c/report", { body }));
      $("#f-gbv").reset(); $("#g-danger").hidden = true; $("#g-mobile-f").hidden = true; resetWhere("g");
      showDone({ title: t("gDoneT"), body: t("gDoneBody") + " " + t("gHelpline"), ref: r.ref });
    } catch (err) {
      if (err.field === "mobile") fieldError("g-mobile", t("errMobile")); else if (err.field === "safe_now") $("#g-safe-e").textContent = t("gSafeQ"); else mapError("g", err);
    }
  });

  // ------------------------------------------------------------------ anonymous tip
  $("#f-anon").addEventListener("submit", async (e) => {
    e.preventDefault();
    formError("a-error", ""); fieldError("a-type", "");
    const type = $("#a-type").value, w = whereValue("a");
    if (!type) { fieldError("a-type", t("errType")); return $("#a-type").focus(); }
    if (w.lat === null && !w.address) return formError("a-error", t("errPlace"));
    // Nothing identifying is sent: no profile, no name, no number. The server stores none either.
    const body = { kind: "tip", type, ...w, note: $("#a-text").value.trim(), photos: photoState.a || [] };
    try {
      const r = await submitting($("#a-submit"), () => api("/api/c/report", { body }));
      $("#f-anon").reset(); resetWhere("a"); $('[data-photos="a"]')._reset();
      showDone({ title: t("aCodeT"), body: t("aNotCase"), ref: r.ref, code: r.code });
    } catch (err) { mapError("a", err); }
  });

  // ------------------------------------------------------------------ unsafe place
  $("#f-area").addEventListener("submit", async (e) => {
    e.preventDefault();
    formError("u-error", ""); fieldError("u-type", "");
    const type = $("#u-type").value, w = whereValue("u");
    if (!type) { fieldError("u-type", t("errType")); return $("#u-type").focus(); }
    if (w.lat === null && !w.address) return formError("u-error", t("errPlace"));
    const body = { kind: "area", type, ...w, photos: photoState.u || [] };
    try {
      const r = await submitting($("#u-submit"), () => api("/api/c/report", { body }));
      $("#f-area").reset(); resetWhere("u"); $('[data-photos="u"]')._reset();
      showDone({ title: t("uDoneT"), body: t("uDoneBody"), ref: r.ref });
    } catch (err) { mapError("u", err); }
  });

  // ------------------------------------------------------------------ confirmation screen
  function showDone(d) {
    $("#d-title").textContent = d.title; $("#d-body").textContent = d.body;
    $("#d-ref-c").textContent = d.ref;
    const codeWrap = $("#d-code-wrap");
    codeWrap.hidden = !d.code;
    $("#d-keep").hidden = !!d.code;
    clear($("#d-code"));
    if (d.code) {
      d.code.split("").forEach((c) => $("#d-code").appendChild(h("span.codebox__char", { text: c })));
      $("#d-copy").onclick = async () => { try { await navigator.clipboard.writeText(d.code); toast(t("aCopied")); } catch (e) { /* clipboard blocked */ } };
    }
    go("done");
    announce(d.title + ". " + d.ref);
  }

  // ------------------------------------------------------------------ call
  let call = null, callOpen = false;
  const callEl = $("#call");
  let pollTimer = null, tickTimer = null, videoRoom = null, recog = null;
  const ORDER = ["connecting", "ringing", "connected"];

  function setCallScreen(on) {
    callOpen = on;
    $("#app").hidden = on;
    $("#call-wrap").hidden = !on;
    document.body.classList.toggle("in-call", on);
    document.documentElement.dataset.theme = on ? "ops" : "light";
    if (on) { window.scrollTo(0, 0); callEl.focus({ preventScroll: true }); }
  }

  async function quickLocation() {
    try { const p = await getPosition(2500); const lat = p.coords.latitude, lon = p.coords.longitude; return inKzn(lat, lon) ? { lat: +lat.toFixed(5), lon: +lon.toFixed(5) } : null; } catch (e) { return null; }
  }

  async function startCall(mode) {
    if (call && call.state !== "ended") return;
    setCallScreen(true);
    call = { id: "", ctoken: "", ref: "", mode, state: "connecting", lines: 0, answeredAt: 0, transport: "text", point: null };
    clear($("#lines")); $("#captions").hidden = true; $("#summary").hidden = true; $("#call-fail").hidden = true; $("#call-note").hidden = true;
    $("#bottom").hidden = false; $("#stepper").hidden = false; $("#ref-line").hidden = true; $("#queue-line").hidden = true; $("#timer").textContent = "";
    $("#remote").hidden = true; $("#avatar").hidden = false; $("#pip").hidden = true;
    setState("connecting");
    call.point = await quickLocation();
    $("#loc-text").textContent = call.point ? t("callLoc") : t("callNoLoc");
    const p = getProfile();
    const body = { mode, ...(call.point || {}) };
    if (p) { body.name = p.name; body.mobile = p.mobile; body.address = p.addr || ""; if (p.face) body.face = p.face; }
    try {
      const r = await api("/api/c/call/start", { body });
      Object.assign(call, { id: r.id, ctoken: r.ctoken, ref: r.ref, video: r.video });
      $("#call-ref").textContent = r.ref; $("#sum-ref").textContent = r.ref; $("#ref-line").hidden = false;
      setState("ringing");
      pollTimer = setInterval(pollCall, 1000);
    } catch (e) {
      setState("failed");
    }
  }

  function setState(s) {
    call.state = s;
    callEl.dataset.state = s === "failed" ? "ended" : s;
    const idx = ORDER.indexOf(s);
    $$("#stepper .stepper__step").forEach((el, i) => {
      el.removeAttribute("aria-current"); el.dataset.done = String(s === "ended" || i < idx);
      if (i === idx) el.setAttribute("aria-current", "step");
    });
    const iconId = { connecting: "i-clock", ringing: "i-phone", connected: "i-check-circle", ended: "i-end-call", failed: "i-alert" }[s];
    $("#state-icon").firstElementChild.setAttribute("href", "/static/img/icons.svg#" + iconId);
    const on = s === "connected" && call.transport === "video";
    ["b-mute", "b-cam", "b-spk"].forEach((id) => { $("#" + id).disabled = !on; });
    $("#captions").hidden = !(s === "connected" || (s === "ended" && call.lines > 0));
    $("#call-fail").hidden = s !== "failed";
    $("#summary").hidden = s !== "ended";
    $("#bottom").hidden = s === "ended" || s === "failed";
    $("#stepper").hidden = s === "ended" || s === "failed";
    paintCall();
  }
  function paintCall() {
    if (!call) return;
    $("#state-text").textContent = t("st_" + call.state);
    $("#l-end").textContent = call.state === "connected" ? t("end") : t("cancel");
    $("#b-end").setAttribute("aria-label", call.state === "connected" ? t("end") : t("cancel"));
    $("#l-mute").textContent = $("#b-mute").getAttribute("aria-pressed") === "true" ? t("unmute") : t("mute");
    if (call.state === "connected") {
      $("#call-note").hidden = call.transport === "video";
      $("#call-note").textContent = t("textOnly");
      $("#mode-chip").textContent = call.transport === "video" ? t("simVideo") : t("simText");
    }
  }

  async function pollCall() {
    if (!call || !call.id || call.state === "ended") return;
    let s;
    try { s = await api(`/api/c/call/${call.id}/state?t=${encodeURIComponent(call.ctoken)}`); } catch (e) { return; }
    renderLines(s.lines);
    if (s.state === "ringing") {
      const q = $("#queue-line"); q.hidden = false;
      $("#queue-text").textContent = s.queue_ahead > 0 ? t("ahead", { n: s.queue_ahead }) : t("first");
    } else { $("#queue-line").hidden = true; }
    if (s.state === "live" && call.state !== "connected") {
      call.transport = s.transport; call.answeredAt = s.answered_at;
      setState("connected");
      startTimer();
      if (s.transport === "video") joinVideo();
    }
    if (s.state === "ended") finishCall(s);
  }

  function renderLines(lines) {
    if (lines.length === call.lines) return;
    call.lines = lines.length;
    const ul = $("#lines"); clear(ul);
    lines.forEach((l) => {
      const mine = l.who === "citizen";
      ul.appendChild(h("li", { class: "transcript__line" + (mine ? " transcript__line--you" : "") },
        h("span.transcript__who", { text: mine ? t("you") : t("operator") }), h("span.transcript__text", { text: l.text })));
    });
    ul.scrollTop = ul.scrollHeight;
    if (call.state === "connected" || call.state === "ended") $("#captions").hidden = false;
  }

  function startTimer() {
    clearInterval(tickTimer);
    const tick = () => { $("#timer").textContent = fmtClock(Date.now() / 1000 - call.answeredAt); };
    tick(); tickTimer = setInterval(tick, 1000);
  }

  function finishCall(s) {
    clearInterval(pollTimer); clearInterval(tickTimer);
    leaveVideo();
    const secs = s.answered_at ? Math.max(0, (s.ended_at || Date.now() / 1000) - s.answered_at) : 0;
    $("#dur").textContent = fmtClock(secs);
    $("#timer").textContent = "";
    setState("ended");
    announce(t("st_ended"));
  }

  async function endCall() {
    if (!call) return;
    if (call.id && call.state !== "ended") { try { await api(`/api/c/call/${call.id}/end`, { body: { t: call.ctoken } }); } catch (e) { /* the desk will see the line drop */ } }
    if (call.state === "ringing" || call.state === "connecting") {
      clearInterval(pollTimer); leaveVideo(); closeCall();
    } else {
      finishCall({ answered_at: call.answeredAt, ended_at: Date.now() / 1000 });
    }
  }
  function closeCall() {
    clearInterval(pollTimer); clearInterval(tickTimer); leaveVideo();
    setCallScreen(false); call = null;
    go("home"); route();
  }

  // ---- Twilio Video (real voice and video) when the service has it switched on
  let videoLoading = null;
  function loadVideoSdk() {
    if (window.Twilio && window.Twilio.Video) return Promise.resolve();
    if (videoLoading) return videoLoading;
    videoLoading = new Promise((resolve, reject) => {
      const s = h("script", { src: "https://unpkg.com/twilio-video@2/dist/twilio-video.min.js" });
      s.onload = resolve; s.onerror = () => { videoLoading = null; reject(new Error("sdk")); };
      document.head.appendChild(s);
    });
    return videoLoading;
  }
  async function joinVideo() {
    try {
      const { token, room } = await api(`/api/c/call/${call.id}/token`, { body: { t: call.ctoken } });
      await loadVideoSdk();
      videoRoom = await window.Twilio.Video.connect(token, { name: room, audio: true, video: call.mode === "video" ? { width: 640 } : false });
      const attach = (track, local) => {
        if (track.kind === "video") {
          const el = track.attach();
          if (local) { const box = $("#pip"); box.hidden = false; clear(box); el.id = "v-self"; el.muted = true; box.appendChild(el); }
          else { $("#remote").hidden = false; $("#avatar").hidden = true; clear($("#remote")); $("#remote").appendChild(el); }
        } else if (!local) { const a = track.attach(); a.id = "a-remote"; document.body.appendChild(a); }
      };
      videoRoom.localParticipant.tracks.forEach((pub) => pub.track && attach(pub.track, true));
      const sub = (p) => { p.tracks.forEach((pub) => pub.track && attach(pub.track, false)); p.on("trackSubscribed", (tr) => attach(tr, false)); };
      videoRoom.participants.forEach(sub); videoRoom.on("participantConnected", sub);
      $("#b-cam").setAttribute("aria-pressed", String(call.mode === "video"));
      startCaptions();
    } catch (e) {
      call.transport = "text"; paintCall(); setState("connected");
    }
  }
  function leaveVideo() {
    try { stopCaptions(); if (videoRoom) videoRoom.disconnect(); } catch (e) { /* ok */ }
    videoRoom = null;
    $$("#a-remote").forEach((a) => a.remove());
  }
  function setTrackEnabled(kind, enabled) {
    if (!videoRoom) return;
    const pubs = kind === "audio" ? videoRoom.localParticipant.audioTracks : videoRoom.localParticipant.videoTracks;
    pubs.forEach((pub) => { if (pub.track) { enabled ? pub.track.enable() : pub.track.disable(); } });
  }
  // Live captions use the browser's own speech recognition when it exists. They may be inaccurate.
  function startCaptions() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR || recog) return;
    recog = new SR(); recog.continuous = true; recog.interimResults = false; recog.lang = "en-ZA";
    recog.onresult = (ev) => {
      const res = ev.results[ev.results.length - 1];
      if (res.isFinal && call && call.id) api(`/api/c/call/${call.id}/line`, { body: { t: call.ctoken, text: res[0].transcript, src: "caption" } }).catch(() => {});
    };
    recog.onend = () => { if (recog && call && call.state === "connected") try { recog.start(); } catch (e) { /* already running */ } };
    try { recog.start(); } catch (e) { recog = null; }
  }
  function stopCaptions() { if (recog) { const r = recog; recog = null; try { r.stop(); } catch (e) { /* ok */ } } }

  function toggle(id, useId, onIcon, offIcon) {
    const b = $("#" + id), on = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", String(on));
    $("#" + useId).setAttribute("href", "/static/img/icons.svg#" + (on ? onIcon : offIcon));
    if (navigator.vibrate) navigator.vibrate(12);
    return on;
  }
  $("#b-mute").addEventListener("click", () => { const muted = toggle("b-mute", "u-mute", "i-mic-off", "i-mic"); setTrackEnabled("audio", !muted); paintCall(); });
  $("#b-cam").addEventListener("click", () => { const on = toggle("b-cam", "u-cam", "i-camera", "i-camera-off"); setTrackEnabled("video", on); $("#pip").hidden = !on; });
  $("#b-spk").addEventListener("click", () => { const on = toggle("b-spk", "u-spk", "i-speaker-off", "i-speaker"); $$("#a-remote").forEach((a) => { a.muted = on; }); });
  $("#b-end").addEventListener("click", endCall);
  $("#call-done").addEventListener("click", closeCall);
  $("#call-retry").addEventListener("click", () => { const m = call ? call.mode : "voice"; call = null; startCall(m); });

  // ---- silent text
  const textDlg = $("#text-dlg");
  function openText() { if (!textDlg.open) { textDlg.showModal(); $("#text-title").focus(); } }
  async function sendText(msg) {
    msg = (msg || "").trim();
    if (!msg) return;
    // "Can't talk" from the home screen starts a text call first.
    if (!call || call.state === "ended" || call.state === "failed") { await startCall("voice"); }
    let waited = 0;
    while (call && !call.id && waited < 6000) { await new Promise((r) => setTimeout(r, 200)); waited += 200; }
    if (!call || !call.id) return;
    try { await api(`/api/c/call/${call.id}/line`, { body: { t: call.ctoken, text: msg, src: "typed" } }); toast(t("sent")); } catch (e) { toast(t("errGeneric")); }
    if (textDlg.open) textDlg.close();
    pollCall();
  }
  $("#open-text").addEventListener("click", openText);
  $("#text-x").addEventListener("click", () => textDlg.close());
  $("#text-back").addEventListener("click", () => textDlg.close());
  $$("[data-msg]").forEach((b) => b.addEventListener("click", () => sendText(b.textContent)));
  $("#text-form").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#own-msg").value; $("#own-msg").value = ""; sendText(v); });

  $("#em-call").addEventListener("click", () => startCall("voice"));
  $("#em-video").addEventListener("click", () => startCall("video"));
  $("#em-text").addEventListener("click", async () => { await startCall("voice"); openText(); });

  // ------------------------------------------------------------------ start
  $$("[data-where]").forEach(initWhere);
  $$("[data-photos]").forEach(initPhotos);
  applyI18n();
  renderProfileHints();
  loadConfig();
  route();
  let seen = false;
  try { seen = sessionStorage.getItem("saps-notice") === "1"; } catch (e) { /* ok */ }
  if (!seen) openNotice();
})();
