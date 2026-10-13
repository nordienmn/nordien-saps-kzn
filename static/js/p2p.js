/* Direct voice and video between the caller's app and the control-room desk (WebRTC).
   The server only passes the connection messages between the two; the sound and picture go straight between them.
   The caller always makes the offer once the call is live; the desk answers it.
   If the link drops or fails, the caller's side restarts it (up to three times) so a brief network blip does not end the picture. */
(function () {
  "use strict";

  function connect(o) {
    const pc = new RTCPeerConnection({ iceServers: o.ice && o.ice.length ? o.ice : [{ urls: "stun:stun.l.google.com:19302" }] });
    const remote = new MediaStream();
    let after = 0, closed = false, remoteSet = false, queued = [], timer = null, busy = false, added = false, restarts = 0, downSince = 0;
    const started = Date.now();
    const offerer = o.role === "offerer";

    pc.ontrack = (e) => {
      (e.streams && e.streams[0] ? e.streams[0].getTracks() : [e.track]).forEach((t) => { if (!remote.getTracks().includes(t)) remote.addTrack(t); });
      if (o.onTrack) o.onTrack(remote);
    };
    pc.onicecandidate = (e) => { if (e.candidate) Promise.resolve(o.post("ice", e.candidate.toJSON())).catch(() => {}); };
    pc.onconnectionstatechange = () => {
      const st = pc.connectionState;
      if (st === "connected") downSince = 0;
      if ((st === "disconnected" || st === "failed") && !downSince) downSince = Date.now();
      if (o.onState) o.onState(st);
    };

    const addLocal = () => {
      if (added) return; added = true;
      const s = o.stream;
      if (s) s.getTracks().forEach((t) => pc.addTrack(t, s));
      const has = (k) => !!s && s.getTracks().some((t) => t.kind === k);
      // Always be ready to receive what the other side sends, even if our own microphone or camera is blocked.
      if (offerer) {
        if (!has("audio")) pc.addTransceiver("audio", { direction: "recvonly" });
        if (o.wantVideo && !has("video")) pc.addTransceiver("video", { direction: "recvonly" });
      }
    };
    if (offerer) addLocal();

    async function flush() { const q = queued; queued = []; for (const c of q) { try { await pc.addIceCandidate(c); } catch (e) { /* late or duplicate */ } } }

    async function sendOffer(restart) {
      const offer = await pc.createOffer(restart ? { iceRestart: true } : undefined);
      await pc.setLocalDescription(offer);
      await o.post("offer", { type: pc.localDescription.type, sdp: pc.localDescription.sdp });
    }

    async function handle(m) {
      if (m.type === "offer" && !offerer) {
        await pc.setRemoteDescription(m.data); remoteSet = true;
        addLocal(); // after the offer is set, our tracks take the places the caller offered
        const ans = await pc.createAnswer(); await pc.setLocalDescription(ans);
        await o.post("answer", { type: pc.localDescription.type, sdp: pc.localDescription.sdp });
        await flush();
      } else if (m.type === "answer" && offerer) {
        await pc.setRemoteDescription(m.data); remoteSet = true; await flush();
      } else if (m.type === "ice") {
        if (remoteSet) { try { await pc.addIceCandidate(m.data); } catch (e) { /* ignore */ } } else queued.push(m.data);
      }
    }

    async function tick() {
      if (closed || busy) return; busy = true;
      try {
        const msgs = await o.fetchSince(after);
        for (const m of msgs) { after = Math.max(after, m.n); await handle(m); }
      } catch (e) { /* keep trying */ }
      // A link that dropped, or never came up, is restarted by the caller's side.
      try {
        const st = pc.connectionState;
        const stuck = st !== "connected" && Date.now() - started > 12000 * (restarts + 1);
        const lost = downSince && Date.now() - downSince > 4000;
        if (offerer && remoteSet && restarts < 3 && (stuck || lost || st === "failed")) {
          restarts++; downSince = Date.now(); remoteSet = false;
          if (o.onState) o.onState("retrying");
          if (pc.restartIce) pc.restartIce();
          await sendOffer(true);
        }
      } catch (e) { /* try again on the next tick */ }
      busy = false;
      if (!closed && pc.connectionState !== "connected" && Date.now() - started > 25000 && o.onState && !pc._warned) { pc._warned = true; o.onState("slow"); }
    }

    (async () => {
      if (offerer) { try { await sendOffer(false); } catch (e) { if (o.onState) o.onState("failed"); } }
      timer = setInterval(tick, 500); tick();
    })();

    return {
      pc, remote,
      // How the call is travelling: host (same network), srflx (through the internet), relay (through a relay server).
      async route() {
        try {
          const stats = await pc.getStats(); let id = null, kind = "";
          stats.forEach((r) => { if (r.type === "transport" && r.selectedCandidatePairId) id = r.selectedCandidatePairId; });
          stats.forEach((r) => { if (id && r.id === id) { const l = stats.get(r.localCandidateId); kind = l ? l.candidateType : ""; } });
          if (!kind) stats.forEach((r) => { if (r.type === "candidate-pair" && r.state === "succeeded" && r.nominated) { const l = stats.get(r.localCandidateId); kind = l ? l.candidateType : ""; } });
          return kind || "unknown";
        } catch (e) { return "unknown"; }
      },
      close() { closed = true; clearInterval(timer); try { pc.close(); } catch (e) { /* ok */ } },
    };
  }

  // Waits at most a few seconds for the microphone and camera, so a slow permission prompt cannot hold the call up.
  async function localMedia(video, waitMs) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return null;
    const ask = async () => {
      try { return await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: video ? { facingMode: "user", width: { ideal: 640 } } : false }); }
      catch (e) {
        if (video) { try { return await navigator.mediaDevices.getUserMedia({ audio: true, video: false }); } catch (e2) { return null; } }
        return null;
      }
    };
    const p = ask();
    const out = await Promise.race([p, new Promise((r) => setTimeout(() => r("late"), waitMs || 8000))]);
    if (out === "late") { p.then((s) => { if (s) s.getTracks().forEach((t) => t.stop()); }); return null; }
    return out;
  }

  window.SAPS_P2P = { connect, localMedia };
})();
