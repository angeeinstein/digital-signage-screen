import { api, ApiError } from "../lib/api";

export type Mode = "connecting" | "direct" | "relay";
type Msg = { type: string; [k: string]: unknown };

const DIRECT_TIMEOUT_MS = 6000;
const RELAY_CHUNK_MS = 250;

/** Recording formats for the fallback, in order of preference. */
const RELAY_TYPES = [
  "video/webm;codecs=vp8,opus",
  "video/webm;codecs=vp8",
  "video/webm",
  "video/mp4;codecs=avc1.42E01E,mp4a.40.2",
  "video/mp4;codecs=avc1.42E01E",
  "video/mp4",
];

function pickRelayType(withAudio: boolean): string | null {
  const candidates = withAudio ? RELAY_TYPES : RELAY_TYPES.filter((t) => !/opus|mp4a/.test(t));
  return candidates.find((t) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) ?? null;
}

const randomId = () => Array.from(crypto.getRandomValues(new Uint8Array(9)), (b) => b.toString(36)).join("").slice(0, 16);

/**
 * Laptop side of an active share: tries a direct WebRTC connection to the
 * TV first (local network), and falls back to uploading recorded chunks
 * through the server if that doesn't connect within a few seconds.
 */
export class ShareSession {
  private pc: RTCPeerConnection | null = null;
  private recorder: MediaRecorder | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private since = 0;
  private closed = false;
  private generation = 0;
  mode: Mode = "connecting";

  constructor(
    private token: string,
    private stream: MediaStream,
    private relayAllowed: boolean,
    private onMode: (m: Mode) => void,
    private onEnd: (reason: string) => void,
  ) {
    const track = stream.getVideoTracks()[0];
    if (track && "contentHint" in track) track.contentHint = "detail"; // sharp text over smooth motion
    track?.addEventListener("ended", () => this.stop("You stopped sharing."));
  }

  start() {
    this.pollEvents();
    this.connect();
  }

  private setMode(m: Mode) {
    this.mode = m;
    this.onMode(m);
  }

  private signal(message: Msg) {
    return api("/api/share/signal", { method: "POST", body: { token: this.token, message } });
  }

  private async pollEvents() {
    while (!this.closed) {
      try {
        const r = await api<{ events: Msg[]; seq: number }>(`/api/share/events?token=${encodeURIComponent(this.token)}&since=${this.since}`);
        this.since = r.seq;
        for (const ev of r.events) await this.handle(ev);
      } catch (e) {
        if (e instanceof ApiError && (e.status === 410 || e.status === 404)) {
          this.finish("The share session has ended.");
          return;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
    }
  }

  private async handle(ev: Msg) {
    switch (ev.type) {
      case "answer":
        if (this.pc && !this.pc.currentRemoteDescription) await this.pc.setRemoteDescription({ type: "answer", sdp: String(ev.sdp) });
        break;
      case "ice":
        if (this.pc) await this.pc.addIceCandidate((ev.candidate as RTCIceCandidateInit | null) ?? undefined).catch(() => {});
        break;
      case "resync": // the TV reloaded
        this.connect();
        break;
      case "relay-restart": // the TV fell behind
        if (this.mode === "relay") this.startRelay();
        break;
      case "replaced":
        this.finish(`${String(ev.by ?? "Someone else")} is sharing now.`);
        break;
      case "ended":
        this.finish(ev.reason === "stopped by admin" ? "Sharing was stopped from the admin page." : "The share session has ended.");
        break;
    }
  }

  /** (Re)connect: direct first, relay as fallback. */
  private connect() {
    const gen = ++this.generation;
    this.teardown();
    this.setMode("connecting");
    const pc = new RTCPeerConnection({ iceServers: [] });
    this.pc = pc;
    for (const t of this.stream.getTracks()) pc.addTrack(t, this.stream);
    for (const s of pc.getSenders()) {
      if (s.track?.kind !== "video") continue;
      const p = s.getParameters();
      p.encodings = (p.encodings?.length ? p.encodings : [{}]).map((e) => ({ ...e, maxBitrate: 8_000_000, maxFramerate: 30 }));
      (p as RTCRtpSendParameters & { degradationPreference?: string }).degradationPreference = "maintain-resolution";
      s.setParameters(p).catch(() => {});
    }
    pc.onicecandidate = (e) => {
      this.signal({ type: "ice", candidate: e.candidate ? e.candidate.toJSON() : null }).catch(() => {});
    };
    pc.onconnectionstatechange = () => {
      if (gen !== this.generation) return;
      if (pc.connectionState === "connected") {
        clearTimeout(this.timer);
        this.setMode("direct");
        this.signal({ type: "mode", mode: "direct" }).catch(() => {});
      } else if (pc.connectionState === "failed") {
        this.fallback();
      }
    };
    (async () => {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await this.signal({ type: "offer", sdp: offer.sdp });
    })().catch((e) => this.finish(`Could not start: ${e instanceof Error ? e.message : String(e)}`));
    this.timer = setTimeout(() => {
      if (gen === this.generation && pc.connectionState !== "connected") this.fallback();
    }, DIRECT_TIMEOUT_MS);
  }

  private fallback() {
    if (this.mode === "relay" || this.closed) return;
    if (!this.relayAllowed) {
      this.finish("Couldn't reach the TV directly. Connect to the same network as the TV and try again.");
      return;
    }
    this.startRelay();
  }

  private startRelay() {
    const gen = ++this.generation;
    this.teardown();
    const withAudio = this.stream.getAudioTracks().length > 0;
    const mime = pickRelayType(withAudio);
    if (!mime) {
      this.finish("This browser can't share over the internet. Connect to the same network as the TV.");
      return;
    }
    // Fewer frames over the internet keeps it smooth.
    this.stream.getVideoTracks()[0]?.applyConstraints({ frameRate: { max: 15 } }).catch(() => {});
    const session = randomId();
    const recorder = new MediaRecorder(this.stream, { mimeType: mime, videoBitsPerSecond: 2_500_000 });
    this.recorder = recorder;
    let seq = 0;
    let chain = Promise.resolve();
    let backlog = 0;
    recorder.ondataavailable = (e) => {
      if (gen !== this.generation || !e.data.size) return;
      const n = seq++;
      backlog++;
      if (backlog > 40) {
        // Upload can't keep up; start a fresh recording.
        this.startRelay();
        return;
      }
      chain = chain
        .then(() =>
          fetch(`/api/share/relay?token=${encodeURIComponent(this.token)}&session=${session}&seq=${n}`, {
            method: "POST",
            headers: { "X-Requested-With": "signage", "Content-Type": "application/octet-stream" },
            body: e.data,
          }),
        )
        .then((res) => {
          backlog--;
          if (gen !== this.generation) return;
          if (res.status === 409) this.startRelay();
          else if (res.status === 410 || res.status === 404) this.finish("The share session has ended.");
        })
        .catch(() => {
          backlog--;
        });
    };
    this.signal({ type: "relay", session, mime })
      .then(() => {
        if (gen !== this.generation) return;
        recorder.start(RELAY_CHUNK_MS);
        this.setMode("relay");
      })
      .catch((e) => this.finish(e instanceof ApiError ? e.message : String(e)));
  }

  private teardown() {
    clearTimeout(this.timer);
    this.pc?.close();
    this.pc = null;
    if (this.recorder && this.recorder.state !== "inactive") this.recorder.stop();
    this.recorder = null;
    this.stream.getVideoTracks()[0]?.applyConstraints({ frameRate: { max: 30 } }).catch(() => {});
  }

  private finish(reason: string) {
    if (this.closed) return;
    this.closed = true;
    this.generation++;
    this.teardown();
    for (const t of this.stream.getTracks()) t.stop();
    this.onEnd(reason);
  }

  /** Stop sharing on purpose. */
  stop(reason = "You stopped sharing.") {
    if (this.closed) return;
    api("/api/share/stop", { method: "POST", body: { token: this.token } }).catch(() => {});
    this.finish(reason);
  }
}
