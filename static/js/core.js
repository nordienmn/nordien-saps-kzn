/* Shared helpers. No framework. Citizen text is only ever placed with textContent. */
(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";

  /** h("div.card#id", {attr}, child, child ...) builds elements. Strings become text nodes, never HTML. */
  function h(spec, attrs, ...kids) {
    // "tag.class.class#id" in any order after the tag name
    const tagM = /^([a-z][a-z0-9-]*)?/i.exec(spec);
    const el = document.createElement(tagM && tagM[1] ? tagM[1] : "div");
    const rest = spec.slice(tagM ? tagM[0].length : 0);
    const parts = rest.match(/[.#][\w-]+/g) || [];
    const classes = [];
    parts.forEach((part) => { if (part[0] === "#") el.id = part.slice(1); else classes.push(part.slice(1)); });
    if (classes.length) el.className = classes.join(" ");
    if (attrs && typeof attrs === "object" && !(attrs instanceof Node) && !Array.isArray(attrs)) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") el.className += (el.className ? " " : "") + v;
        else if (k === "text") el.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
        else if (k === "dataset") Object.assign(el.dataset, v);
        else el.setAttribute(k, v === true ? "" : v);
      }
    } else if (attrs !== undefined && attrs !== null) {
      kids.unshift(attrs);
    }
    append(el, kids);
    return el;
  }

  function append(el, kids) {
    for (const k of kids.flat(Infinity)) {
      if (k === null || k === undefined || k === false) continue;
      el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
    }
    return el;
  }

  function clear(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
    return el;
  }

  function icon(name, cls) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "icon" + (cls ? " " + cls : ""));
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", "/static/img/icons.svg#i-" + name);
    svg.appendChild(use);
    return svg;
  }

  /** JSON fetch. Throws an Error whose .message is safe to show and .field names a bad field. */
  async function api(path, opts) {
    opts = opts || {};
    const init = { method: opts.method || (opts.body ? "POST" : "GET"), headers: {}, credentials: "same-origin" };
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    let res;
    try {
      res = await fetch(path, init);
    } catch (e) {
      const err = new Error("offline");
      err.offline = true;
      throw err;
    }
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      /* non-JSON error body */
    }
    if (!res.ok) {
      const err = new Error((data && data.error) || "Something went wrong. Please try again.");
      err.status = res.status;
      err.field = data && data.field;
      err.code = data && data.code;
      throw err;
    }
    return data;
  }

  /** Polls fn every ms; skips while the tab is hidden; backs off after failures. Returns stop(). */
  function poll(fn, ms) {
    let stopped = false, fails = 0, timer = null;
    async function tick() {
      if (stopped) return;
      try { await fn(); fails = 0; } catch (e) { fails += 1; if (window.console) console.error("poll error:", e); if (e && e.code === "auth") return; }
      // A hidden tab still polls, but slowly, so a desk left in the background is never stale for long.
      const base = document.hidden ? ms * 4 : ms;
      timer = setTimeout(tick, Math.min(base * (1 + fails), 20000));
    }
    tick();
    document.addEventListener("visibilitychange", () => { if (!document.hidden && !stopped) { clearTimeout(timer); tick(); } });
    return () => { stopped = true; clearTimeout(timer); };
  }

  function fmtAge(ts, now) {
    const s = Math.max(0, Math.round((now || Date.now() / 1000) - ts));
    if (s < 60) return s + "s";
    if (s < 3600) return Math.floor(s / 60) + "m";
    if (s < 86400) return Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m";
    return Math.floor(s / 86400) + "d";
  }

  function fmtTime(ts) {
    return new Date(ts * 1000).toLocaleString("en-ZA", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function fmtClock(sec) {
    sec = Math.max(0, Math.floor(sec));
    return String(Math.floor(sec / 60)).padStart(2, "0") + ":" + String(sec % 60).padStart(2, "0");
  }

  /** A polite live region. Announce confirmations to screen readers. */
  function announce(text) {
    let r = document.getElementById("live-region");
    if (!r) {
      r = h("div#live-region", { class: "sr-only", "aria-live": "polite", role: "status" });
      document.body.appendChild(r);
    }
    r.textContent = "";
    setTimeout(() => { r.textContent = text; }, 30);
  }

  /** A short beep for an incoming call. Browsers only allow it after the user has clicked once. */
  const sound = {
    ctx: null,
    enabled: false,
    enable() {
      try {
        this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
        if (this.ctx.state === "suspended") this.ctx.resume();
        this.enabled = true;
      } catch (e) { this.enabled = false; }
    },
    ring() {
      if (!this.enabled || !this.ctx) return;
      [0, 0.28].forEach((d) => {
        const o = this.ctx.createOscillator(), g = this.ctx.createGain();
        o.type = "sine"; o.frequency.value = 880;
        g.gain.setValueAtTime(0.0001, this.ctx.currentTime + d);
        g.gain.exponentialRampToValueAtTime(0.25, this.ctx.currentTime + d + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + d + 0.22);
        o.connect(g); g.connect(this.ctx.destination);
        o.start(this.ctx.currentTime + d); o.stop(this.ctx.currentTime + d + 0.25);
      });
    },
  };

  function store(key, value) {
    try {
      if (value === undefined) return JSON.parse(localStorage.getItem(key));
      if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(value));
    } catch (e) { /* private mode or blocked storage: the page still works */ }
    return null;
  }

  /** Shrinks a picture in the browser before upload, so it stays small and EXIF location is dropped. */
  function shrinkImage(file, maxSide, quality) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = () => {
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const c = document.createElement("canvas");
        c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        resolve(c.toDataURL("image/jpeg", quality));
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("That picture could not be read.")); };
      img.src = url;
    });
  }

  /** A selfie camera for the sign-in and sign-out photos. Nothing is kept unless the officer presses the button. */
  const camera = {
    stream: null,
    async start(video) {
      this.stop();
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error("no camera");
      this.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 640 } }, audio: false });
      video.srcObject = this.stream;
      await video.play();
    },
    snap(video, maxW) {
      const w = video.videoWidth || 640, h = video.videoHeight || 480, scale = Math.min(1, (maxW || 360) / w);
      const c = document.createElement("canvas"); c.width = Math.round(w * scale); c.height = Math.round(h * scale);
      c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
      return c.toDataURL("image/jpeg", 0.72);
    },
    stop() { if (this.stream) { this.stream.getTracks().forEach((t) => t.stop()); this.stream = null; } },
  };

  window.SAPS = { camera, h, append, clear, icon, api, poll, fmtAge, fmtTime, fmtClock, announce, sound, store, shrinkImage };
})();
