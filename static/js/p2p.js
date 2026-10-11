/* Direct voice and video between the caller's app and the control-room desk (WebRTC).
   The server only passes the connection messages between the two; the sound and picture go straight between them.
   The caller always makes the offer once the call is live; the desk answers it. */
(function () {
  "use strict";

  function connect(o) {
    const pc = new RTCPeerConnection({ iceServers: o.ice && o.ice.length ? o.ice : [{ urls: "stun:stun.l.google.com:19302" }] });
    const remote = new MediaStream();
    let after = 0, closed = false, remoteSet = false, queued = [], timer = null, busy = false, started = Date.now();
    const offerer = o.role === "offerer";

    pc.ontrack = (e) => {
      (e.streams && e.streams[0] ? e.streams[0].getTracks() : [e.track]).forEach((t) => { if (!remote.getTracks().includes(t)) remote.addTrack(t); });
      if (o.onTrack) o.onTrack(remote);
    };
    pc.onicecandidate = (e) => { if (e.candidate) Promise.resolve(o.post("ice", e.candidate.toJSON())).catch(() => {}); };
    pc.onconnectionstatechange = () => { if (o.onState) o.onState(pc.connectionState); };

    const addLocal = () => {
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
      busy = false;
      if (!closed && pc.connectionState !== "connected" && Date.now() - started > 25000 && o.onState && !pc._warned) { pc._warned = true; o.onState("slow"); }
    }

    (async () => {
      if (offerer) {
        try {
          const offer = await pc.createOffer(); await pc.setLocalDescription(offer);
          await o.post("offer", { type: pc.localDescription.type, sdp: pc.localDescription.sdp });
        } catch (e) { if (o.onState) o.onState("failed"); }
      }
      timer = setInterval(tick, 500); tick();
    })();

    return {
      pc, remote,
      close() { closed = true; clearInterval(timer); try { pc.close(); } catch (e) { /* ok */ } },
    };
  }

  async function localMedia(video) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return null;
    try { return await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: video ? { facingMode: "user", width: { ideal: 640 } } : false }); }
    catch (e) {
      if (video) { try { return await navigator.mediaDevices.getUserMedia({ audio: true, video: false }); } catch (e2) { return null; } }
      return null;
    }
  }

  window.SAPS_P2P = { connect, localMedia };
})();
