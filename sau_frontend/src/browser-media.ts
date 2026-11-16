import { api, post } from "./api";

export class BrowserMedia {
  private peer: RTCPeerConnection | null = null;
  private id = "";
  private closed = false;

  async connect(video: HTMLVideoElement, status: (value: string) => void) {
    const peer = (this.peer = new RTCPeerConnection({ iceServers: [] }));
    const stream = new MediaStream();
    video.srcObject = stream;
    peer.ontrack = (event) => {
      event.track.onended = () => {
        if (!this.closed) status("播放已中断，请重连");
      };
      stream.addTrack(event.track);
      void video.play().catch((error: DOMException) => {
        if (this.closed || error.name === "AbortError") return;
        video.muted = true;
        status("点击开启声音");
        void video.play().catch(() => status("点击重新连接"));
      });
    };
    peer.onconnectionstatechange = () => {
      if (this.closed) return;
      if (peer.connectionState === "connected")
        status(video.muted ? "点击开启声音" : "实时播放");
      else if (
        ["failed", "disconnected", "closed"].includes(peer.connectionState)
      )
        status("播放连接中断，请重连");
    };
    peer.addTransceiver("video", { direction: "recvonly" });
    peer.addTransceiver("audio", { direction: "recvonly" });
    await peer.setLocalDescription(await peer.createOffer());
    await new Promise<void>((resolve, reject) => {
      if (peer.iceGatheringState === "complete") return resolve();
      const timer = setTimeout(
        () => reject(new Error("音视频连接超时，请重连")),
        8000,
      );
      peer.onicegatheringstatechange = () => {
        if (peer.iceGatheringState === "complete") {
          clearTimeout(timer);
          resolve();
        }
      };
    });
    if (this.closed) return;
    const answer = await post<{
      id: string;
      type: RTCSdpType;
      sdp: string;
      revision: number;
    }>("/youtube/browser/media", peer.localDescription!.toJSON());
    this.id = answer.id;
    if (this.closed) {
      this.release();
      return;
    }
    await peer.setRemoteDescription({ type: answer.type, sdp: answer.sdp });
  }

  private release() {
    if (this.id)
      void api("/youtube/browser/media/" + this.id, {
        method: "DELETE",
        keepalive: true,
      }).catch(() => {});
    this.id = "";
  }

  close() {
    this.closed = true;
    if (this.peer) {
      this.peer.ontrack = null;
      this.peer.onconnectionstatechange = null;
      this.peer.close();
    }
    this.peer = null;
    this.release();
  }
}
