
/* ===== Cover: a small, believable weather screen (demo values, plausible for October in KZN) ===== */
var CITY = {
  "Durban": { hi: 25, lo: 18, hum: 72, wind: 14, dir: "South-west", uv: 9, rain: 20, rise: "05:08", set: "18:13" },
  "Pietermaritzburg": { hi: 27, lo: 13, hum: 55, wind: 11, dir: "East", uv: 10, rain: 30, rise: "05:15", set: "18:20" },
  "Richards Bay": { hi: 27, lo: 20, hum: 78, wind: 16, dir: "North-east", uv: 9, rain: 25, rise: "04:54", set: "18:00" },
  "Newcastle": { hi: 26, lo: 11, hum: 45, wind: 12, dir: "West", uv: 10, rain: 35, rise: "05:22", set: "18:24" },
  "Port Shepstone": { hi: 24, lo: 17, hum: 74, wind: 15, dir: "South-west", uv: 9, rain: 15, rise: "05:12", set: "18:16" }
};
var unit = "C", cityName = "Durban";
function T(c) { return Math.round(unit === "C" ? c : c * 9 / 5 + 32); }
function $(id) { return document.getElementById(id); }
function ico(name) { var s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("class", "icon"); s.setAttribute("aria-hidden", "true"); s.setAttribute("focusable", "false"); var u = document.createElementNS("http://www.w3.org/2000/svg", "use"); u.setAttribute("href", "#i-" + name); s.appendChild(u); return s; }
function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
function paint() {
  var c = CITY[cityName], now = new Date(), hr = now.getHours(), mean = (c.hi + c.lo) / 2, amp = (c.hi - c.lo) / 2;
  function at(h) { return mean + amp * Math.sin((h - 8) / 24 * 2 * Math.PI); }   /* warmest mid-afternoon, coolest before dawn */
  var night = hr < 6 || hr >= 19; if (location.search.indexOf("tone=day") > -1) { night = false; hr = 14; }
  $("phone").setAttribute("data-tone", night ? "night" : "day");
  $("temp").textContent = T(at(hr + now.getMinutes() / 60)); $("deg").textContent = "°";
  $("hilo").textContent = "H " + T(c.hi) + "°  L " + T(c.lo) + "°";
  var cond = c.rain >= 30 ? ["Chance of showers", "cloud-rain"] : c.hum > 70 ? ["Partly cloudy", "cloud-sun"] : ["Mostly sunny", "sun"];
  if (night && cond[1] !== "cloud-rain") cond = ["Partly cloudy", "cloud"];
  $("cond").textContent = cond[0]; $("cond-ico").setAttribute("href", "#i-" + cond[1]);
  $("date").textContent = now.toLocaleDateString("en-ZA", { weekday: "long", day: "numeric", month: "long" });
  var hs = $("hours"); hs.textContent = "";
  for (var i = 0; i < 10; i++) { var h = (hr + i) % 24, d = el("div", "wx-hour"); d.appendChild(el("span", "", i === 0 ? "Now" : (h < 10 ? "0" : "") + h)); d.appendChild(ico(h >= 6 && h < 19 ? (c.rain >= 30 && i % 4 === 3 ? "cloud-rain" : i % 3 === 2 ? "cloud-sun" : "sun") : "cloud")); d.appendChild(el("span", "", T(at(hr + i)) + "°")); hs.appendChild(d); }
  var ds = $("days"); ds.textContent = ""; var names = ["Today"], dh = [0, 1, -2, -1, 2, 0, -3], dl = [0, 0, -1, 1, 0, 1, -2], di = ["cloud-sun", "sun", "cloud-rain", "cloud", "sun", "cloud-sun", "cloud-rain"];
  for (var k = 1; k < 7; k++) names.push(new Date(now.getTime() + k * 864e5).toLocaleDateString("en-ZA", { weekday: "short" }));
  var min = c.lo - 3, max = c.hi + 3;
  for (var j = 0; j < 7; j++) {
    var hi = c.hi + dh[j], lo = c.lo + dl[j], li = el("li", "wx-day"); li.appendChild(el("span", "", names[j])); li.appendChild(ico(di[j])); li.appendChild(el("span", "lo", T(lo) + "°"));
    var r = el("span", "wx-range"), b = el("i"); b.style.left = ((lo - min) / (max - min) * 100) + "%"; b.style.right = (100 - (hi - min) / (max - min) * 100) + "%"; r.appendChild(b); li.appendChild(r); li.appendChild(el("span", "", T(hi) + "°")); ds.appendChild(li);
  }
  $("uv").textContent = c.uv; $("uvl").textContent = c.uv >= 8 ? "Very high" : "High"; $("wind").textContent = c.wind + " km/h"; $("winddir").textContent = c.dir;
  $("hum").textContent = c.hum + "%"; $("rain").textContent = c.rain + "% chance of rain"; $("sunrise").textContent = c.rise; $("sunset").textContent = "Sunset " + c.set;
}
$("city").addEventListener("change", function () { cityName = this.value; paint(); });
paint();

/* ===== Settings + A friend ===== */
var sdlg = $("settings"), friend = null;
try { friend = JSON.parse(localStorage.getItem("wx-friend") || "null"); } catch (e) { friend = null; }
function openSettings() { $("set-main").hidden = false; $("set-friend").hidden = true; if (!sdlg.open) sdlg.showModal(); $("set-title").focus(); }
$("gear").addEventListener("click", openSettings);
document.querySelectorAll("[data-unit]").forEach(function (b) { b.addEventListener("click", function () { unit = b.getAttribute("data-unit"); document.querySelectorAll("[data-unit]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); }); paint(); }); });
$("open-friend").addEventListener("click", function () { $("set-main").hidden = true; $("set-friend").hidden = false; $("friend-title").focus(); });
$("friend-back").addEventListener("click", function () { $("set-main").hidden = false; $("set-friend").hidden = true; });
$("set-done").addEventListener("click", function () {
  if (!$("set-friend").hidden) { var n = $("f-name").value.trim(), m = $("f-mob").value.trim(); if (n && m) { friend = { n: n, m: m }; try { localStorage.setItem("wx-friend", JSON.stringify(friend)); } catch (e) {} $("friend-sub").textContent = "Shared with " + n; } }
  sdlg.close();
});

/* ===== Help: hold ~1.2 s or double-tap the weather icon; confirm sheet always comes first ===== */
var hdlg = $("help"), lang = "en", hold = null, lastTap = 0;
var I = {
  en: { exit: "Exit", c_t: "Ask for help?", c_b: "A police desk will see your approximate area and can call you back, if you choose. Nothing is sent until you tap Send on the next screen.", c_demo: "This is a demonstration. No real police desk will receive this.", c_yes: "Yes, I need help", c_no: "No, go back",
    s_t: "Are you safe right now?", s_b: "We believe you. Share only what you want to.", s_yes: "Yes, I can talk", s_no: "No, I am not safe. Send help quietly", s_un: "I am not sure", s_call: "If you are in danger right now, call 10111.",
    k_t: "How can we reach you?", k_call: "You may call me", k_sms: "SMS only", k_none: "Do not contact me yet", n_t: "What would help? (choose any)", n_talk: "Someone to talk to", n_med: "Medical care", n_safe: "A safe place or transport",
    w_t: "Do you know who did this? (You do not have to say now.)", w_yes: "Yes", w_no: "No", w_later: "Not now", s_send: "Send to the desk",
    d_t: "We have your request", d_b: "A desk officer has it. If you chose to be called, they will call you.", d_friend: "We also sent a message to your friend.", d_line: "GBV Command Centre: 0800 428 428, free, 24 hours.", d_done: "Done", m_t: "Your mobile number", m_h: "Only used to reach you, the way you chose." },
  zu: { exit: "Phuma", c_t: "Ucela usizo?", c_b: "Ihhovisi lamaphoyisa lizobona indawo yakho ngokufanele futhi lingakushayela, uma ukhetha lokho. Akukho okuthunyelwayo kuze kube uthinta Thumela esikrinini esilandelayo.", c_demo: "Le yi-demo. Akukho hhovisi lamaphoyisa langempela eliyitholayo.", c_yes: "Yebo, ngidinga usizo", c_no: "Cha, buyela emuva",
    s_t: "Uphephile yini manje?", s_b: "Siyakukholwa. Yabelana kuphela nalokho ofuna ukukwabelana.", s_yes: "Yebo, ngiyakwazi ukukhuluma", s_no: "Cha, angiphephile. Thumela usizo ngokuthula", s_un: "Angiqinisekile", s_call: "Uma usengozini manje, shayela u-10111.",
    k_t: "Singakuthola kanjani?", k_call: "Ningangishayela", k_sms: "Ama-SMS kuphela", k_none: "Ningangixhumani nami okwamanje", n_t: "Yini engakusiza? (khetha noma yiziphi)", n_talk: "Umuntu okhuluma naye", n_med: "Ukunakekelwa ngokwezempilo", n_safe: "Indawo ephephile noma ezokuthutha",
    w_t: "Uyamazi yini owenze lokhu? (Akudingeki ukusho manje.)", w_yes: "Yebo", w_no: "Cha", w_later: "Hhayi manje", s_send: "Thumela ehhovisi",
    d_t: "Sinakho ukucela kwakho", d_b: "Iphoyisa lasehhovisi linakho. Uma ukhethe ukushayelwa, lizokushayela.", d_friend: "Sithumele nomyalezo kumngani wakho.", d_line: "Isikhungo Sokuyalela se-GBV: 0800 428 428, mahhala, amahora angu-24.", d_done: "Kuphelile", m_t: "Inombolo yakho yefoni", m_h: "Isetshenziselwa ukukuthola kuphela, ngendlela oyikhethile." }
};
function hl() { hdlg.lang = lang; hdlg.querySelectorAll("[data-i]").forEach(function (e) { e.textContent = I[lang][e.getAttribute("data-i")]; }); document.querySelectorAll("[data-hl]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-hl") === lang)); }); }
document.querySelectorAll("[data-hl]").forEach(function (b) { b.addEventListener("click", function () { lang = b.getAttribute("data-hl"); hl(); }); });
function step(n) { ["st1", "st2", "st3"].forEach(function (id, i) { $(id).hidden = i !== n - 1; }); var t = [$("h-title"), $("t-title"), $("d-title")][n - 1]; hdlg.scrollTop = 0; t.focus(); }
function openHelp() { if (hdlg.open) return; $("triage").reset(); $("more").hidden = true; $("danger").hidden = true; $("send-foot").hidden = true; $("d-friend").hidden = !friend; step(1); hl(); document.title = "Weather"; hdlg.showModal(); $("h-title").focus(); if (navigator.vibrate) navigator.vibrate(30); }
/* QUICK EXIT: closes everything and returns to the weather screen immediately. It cannot erase the browser's history. */
function quickExit() { try { hdlg.close(); sdlg.close(); } catch (e) {} $("triage").reset(); $("more").hidden = true; step(1); window.scrollTo(0, 0); document.title = "Weather"; }
$("qx").addEventListener("click", quickExit);
hdlg.addEventListener("cancel", function (e) { e.preventDefault(); quickExit(); });   /* Esc = quick exit */
$("c-no").addEventListener("click", quickExit);
$("c-yes").addEventListener("click", function () { step(2); });
document.querySelectorAll("input[name=safe]").forEach(function (r) { r.addEventListener("change", function () { $("more").hidden = false; $("send-foot").hidden = false; toggleMobile(); $("danger").hidden = r.value === "yes"; }); });

function toggleMobile() { var r = document.querySelector("input[name=reach]:checked"); $("mob-f").hidden = !r || r.value === "none"; }
document.querySelectorAll("input[name=reach]").forEach(function (r) { r.addEventListener("change", toggleMobile); });
function geo(ms) { return new Promise(function (ok) { if (!navigator.geolocation) return ok(null); navigator.geolocation.getCurrentPosition(function (p) { ok({ lat: +p.coords.latitude.toFixed(5), lon: +p.coords.longitude.toFixed(5) }); }, function () { ok(null); }, { timeout: ms, maximumAge: 120000 }); }); }
$("send").addEventListener("click", async function () {
  var btn = this, err = $("send-error"); err.hidden = true;
  var safe = (document.querySelector("input[name=safe]:checked") || {}).value;
  var reach = (document.querySelector("input[name=reach]:checked") || {}).value || "none";
  var mob = $("mob").value.trim();
  if (reach !== "none" && !mob) { err.hidden = false; err.textContent = lang === "zu" ? "Faka inombolo yefoni, noma khetha ukungathintwa." : "Add a number we may use, or choose Do not contact me yet."; $("mob").focus(); return; }
  var needs = Array.prototype.map.call(document.querySelectorAll("input[name=need]:checked"), function (c) { return c.getAttribute("data-w"); }).join(",").split(",").filter(Boolean);
  var wants = []; needs.forEach(function (w) { if (wants.indexOf(w) < 0) wants.push(w); });
  btn.disabled = true;
  var pos = await geo(4000);
  var prof = null; try { prof = JSON.parse(localStorage.getItem("saps-profile") || "null"); } catch (e) { prof = null; }
  var fnum = friend ? friend.m : (prof && prof.friend) || "", fname = friend ? friend.n : (prof && prof.friend_name) || "";
  var body = { kind: "gbv", via: "weather", safe_now: safe, contact_pref: reach, mobile: reach === "none" ? "" : mob, wants: wants,
    know_person: (document.querySelector("input[name=who]:checked") || {}).value === "yes" ? "yes" : (document.querySelector("input[name=who]:checked") || {}).value === "no" ? "no" : "skip",
    friend: fnum, friend_name: fname, lang: lang };
  if (prof) { body.name = prof.name; body.home_address = prof.addr || ""; body.gender = prof.gender || "undisclosed"; body.age_band = prof.age_band || "undisclosed"; body.registered = true; if (prof.face) body.face = prof.face; if (reach === "none") body.mobile = prof.mobile || ""; else body.mobile = mob || prof.mobile || ""; }
  if (pos) { body.lat = pos.lat; body.lon = pos.lon; }
  try {
    var r = await SAPS.api("/api/c/report", { body: body });
    $("d-ref").textContent = r.ref; $("d-friend").hidden = !r.friend_notified;
    var box = $("d-friend-links"); box.textContent = ""; box.hidden = true;
    if (fnum) {
      var digits = fnum.replace(/[^\d+]/g, "").replace(/^0/, "27").replace(/^\+/, ""), text = (lang === "zu" ? "Ngidinga usizo. Sicela ungishayele noma weze kimi." : "I need help. Please call me or come to me.") + (pos ? " https://www.openstreetmap.org/?mlat=" + pos.lat + "&mlon=" + pos.lon : "");
      var nm = fname || fnum;
      var a = document.createElement("a"); a.className = "btn btn--primary btn--block"; a.target = "_blank"; a.rel = "noopener"; a.textContent = (lang === "zu" ? "Thumela umyalezo ku-" : "Message ") + nm + (lang === "zu" ? " ku-WhatsApp" : " on WhatsApp"); a.href = "https://wa.me/" + digits + "?text=" + encodeURIComponent(text);
      var b = document.createElement("a"); b.className = "btn btn--secondary btn--block"; b.textContent = (lang === "zu" ? "Thumela i-SMS ku-" : "Text ") + nm; b.href = "sms:" + fnum + "?&body=" + encodeURIComponent(text);
      box.appendChild(a); box.appendChild(b); box.hidden = false;
    }
    step(3); if (navigator.vibrate) navigator.vibrate(20);
  } catch (e) {
    err.hidden = false; err.textContent = e.offline ? (lang === "zu" ? "Awunaso isignali. Shayela u-10111 uma usengozini." : "No signal. If you are in danger, call 10111.") : (e.message || "Something went wrong.");
  } finally { btn.disabled = false; }
});
$("d-done").addEventListener("click", quickExit);

/* gesture on the weather icon */
var trig = $("trigger");
trig.addEventListener("pointerdown", function () { clearTimeout(hold); hold = setTimeout(function () { hold = null; lastTap = 0; openHelp(); }, 1200); });
["pointerup", "pointerleave", "pointercancel"].forEach(function (ev) { trig.addEventListener(ev, function () { clearTimeout(hold); hold = null; }); });
trig.addEventListener("click", function () { var t = Date.now(); if (t - lastTap < 420) { lastTap = 0; openHelp(); } else lastTap = t; });
trig.addEventListener("contextmenu", function (e) { e.preventDefault(); });
trig.addEventListener("keydown", function (e) { if ((e.key === "Enter" || e.key === " ") && e.repeat && !hold) { hold = setTimeout(function () { hold = null; openHelp(); }, 1000); } });
trig.addEventListener("keyup", function () { clearTimeout(hold); hold = null; });

if (location.hash === "#help") openHelp();
if (location.hash === "#triage") { openHelp(); step(2); }
if (location.hash === "#sent") { openHelp(); step(3); }
if (location.hash === "#friend") { openSettings(); $("open-friend").click(); }

/* initial friend label */
if (friend) { $("friend-sub").textContent = "Shared with " + friend.n; }
document.title = "Weather";
