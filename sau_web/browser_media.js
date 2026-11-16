// Runs only in the local Chrome controller, isolated from the visited website.
window.sauMedia = {
  stream: null,
  peers: new Map(),
  async capture() {
    if (this.stream?.getTracks().every((track) => track.readyState === "live"))
      return;
    this.stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: { ideal: 30, max: 30 } },
      audio: {
        suppressLocalAudioPlayback: true,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
      selfBrowserSurface: "exclude",
    });
    if (!this.stream.getAudioTracks().length) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
      throw new Error("No tab audio track");
    }
  },
  close(id) {
    const peer = this.peers.get(id);
    if (peer) {
      peer.close();
      this.peers.delete(id);
    }
    if (!this.peers.size && this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
  },
  async answer({ id, offer }) {
    if (this.peers.size >= 3) throw new Error("Too many viewers");
    const peer = new RTCPeerConnection({ iceServers: [] });
    this.peers.set(id, peer);
    try {
      await peer.setRemoteDescription(offer);
      for (const track of this.stream.getTracks()) {
        const sender = peer.addTrack(track, this.stream);
        if (track.kind === "video") {
          const parameters = sender.getParameters();
          parameters.encodings = [{ maxBitrate: 5000000, maxFramerate: 30 }];
          await sender.setParameters(parameters);
        }
      }
      peer.onconnectionstatechange = () => {
        if (["failed", "closed"].includes(peer.connectionState)) this.close(id);
        if (peer.connectionState === "disconnected")
          setTimeout(() => {
            if (peer.connectionState === "disconnected") this.close(id);
          }, 15000);
      };
      await peer.setLocalDescription(await peer.createAnswer());
      await new Promise((resolve, reject) => {
        if (peer.iceGatheringState === "complete") return resolve();
        const timer = setTimeout(() => reject(new Error("ICE timeout")), 8000);
        peer.onicegatheringstatechange = () => {
          if (peer.iceGatheringState === "complete") {
            clearTimeout(timer);
            resolve();
          }
        };
      });
      // A viewer that disappears during signaling must not hold capture forever.
      setTimeout(() => {
        if (["new", "connecting"].includes(peer.connectionState))
          this.close(id);
      }, 20000);
      return peer.localDescription.toJSON();
    } catch (error) {
      this.close(id);
      throw error;
    }
  },
};
