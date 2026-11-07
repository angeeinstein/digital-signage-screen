import { useEffect, useRef, useState } from "react";
import { MonitorUp } from "lucide-react";
import { api, ApiError } from "../lib/api";

export interface ShareState {
  pending: { code: string; name: string; expires: number } | null;
  active: { id: string; name: string; mode: string; ends_at: number | null; extended: boolean } | null;
}

interface ScreenEvents {
  events: ShareMessage[];
  seq: number;
  state: ShareState;
  public_url: string;
}

type ShareMessage = { type: string; sender?: string; [k: string]: unknown };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * The TV side of screen sharing. Only the browser on the Pi itself may
 * receive (the server enforces this); anywhere else the first request
 * fails with 403 and this component stays idle.
 *
 * Shows the code card when someone asks to share, and the shared screen
 * on top of everything while sharing. Video arrives either directly over
 * WebRTC or, as fallback, as recorded chunks through the server (MSE).
 */
export function ShareLayer({ onActiveChange, now }: { onActiveChange: (active: boolean) => void; now: Date }) {
  const [state, setState] = useState<ShareState | null>(null);
  const [publicUrl, setPublicUrl] = useState("");
  const [hasVideo, setHasVideo] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const conn = useRef<Connection | null>(null);

  const active = !!state?.active;
  useEffect(() => {
    onActiveChange(active);
    return () => onActiveChange(false);
  }, [active, onActiveChange]);

  useEffect(() => {
    let cancelled = false;
    const send = (to: string, message: ShareMessage) =>
      api("/api/share/screen/signal", { method: "POST", body: { to, message } }).catch(() => {});

    const close = () => {
      conn.current?.close();
      conn.current = null;
      setHasVideo(false);
      if (video.current) {
        video.current.srcObject = null;
        video.current.removeAttribute("src");
        video.current.load();
      }
    };

    const handle = async (ev: ShareMessage, current: ShareState) => {
      const sender = ev.sender ?? "";
      if (ev.type === "offer") {
        close();
        conn.current = new DirectConnection(sender, video.current!, send, () => setHasVideo(true));
        await (conn.current as DirectConnection).accept(String(ev.sdp));
      } else if (ev.type === "ice") {
        if (conn.current instanceof DirectConnection && conn.current.sender === sender) {
          await conn.current.addIce(ev.candidate as RTCIceCandidateInit | null);
        }
      } else if (ev.type === "relay") {
        close();
        const relay = new RelayConnection(sender, String(ev.session), String(ev.mime), video.current!, () => setHasVideo(true), () => {
          // Fell too far behind: ask the laptop to restart its recording.
          send(sender, { type: "relay-restart" });
        });
        conn.current = relay;
        relay.start();
      } else if (ev.type === "stop") {
        if (!current.active || conn.current?.sender === sender) close();
      }
    };

    (async () => {
      let since = 0;
      let first = true;
      while (!cancelled) {
        try {
          const r = await api<ScreenEvents>(`/api/share/screen/events?since=${since}`);
          if (cancelled) return;
          since = r.seq;
          setState(r.state);
          setPublicUrl(r.public_url);
          if (first) {
            first = false;
            // After a reload while someone is sharing: ask them to reconnect.
            if (r.state.active) send(r.state.active.id, { type: "resync" });
            continue; // old messages are not for this page load
          }
          for (const ev of r.events) {
            if (ev.type === "state") continue;
            await handle(ev, r.state).catch((e) => console.warn("share:", e));
          }
          if (!r.state.active && conn.current) close();
        } catch (e) {
          setState(null);
          close();
          // 403: not the Pi's own browser; 404: sharing turned off. Check again later.
          const status = e instanceof ApiError ? e.status : 0;
          await sleep(status === 403 || status === 404 ? 60_000 : 3_000);
        }
      }
    })();

    return () => {
      cancelled = true;
      close();
    };
  }, []);

  const pending = state?.pending;
  const remaining = pending ? Math.max(0, pending.expires - now.getTime() / 1000) : 0;
  const host = publicUrl.replace(/^https?:\/\//, "");
  const endsAt = state?.active?.ends_at;
  const left = endsAt ? endsAt - now.getTime() / 1000 : null;
  const ending = left !== null && left <= 300;

  return (
    <>
      <div className={`share-screen${active ? " on" : ""}`} aria-hidden={!active}>
        <video ref={video} autoPlay playsInline />
        {active && !hasVideo && <div className="share-wait">Connecting to {state?.active?.name}…</div>}
        {active && (
          <div className="share-badge">
            <MonitorUp className="icon" aria-hidden /> {state?.active?.name}
            {state?.active?.mode === "relay" && <span className="muted"> · via internet</span>}
            {ending && (
              <span className="share-ending">
                {" "}
                · ends in {Math.floor(Math.max(0, left) / 60)}:{String(Math.floor(Math.max(0, left) % 60)).padStart(2, "0")}
              </span>
            )}
            {host && <span className="muted"> · share yours at {host}/share</span>}
          </div>
        )}
      </div>
      {pending && remaining > 0 && (
        <div className="share-code" role="status">
          <div className="share-code-title">
            <MonitorUp className="icon" aria-hidden /> {pending.name} wants to share
          </div>
          <div className="share-code-label">Enter this code on the laptop</div>
          <div className="share-code-digits">{pending.code}</div>
          <div className="share-code-bar" style={{ transform: `scaleX(${remaining / 60})` }} />
        </div>
      )}
    </>
  );
}

interface Connection {
  sender: string;
  close(): void;
}

/** WebRTC: the laptop sends an offer; we answer. Video flows peer to peer. */
class DirectConnection implements Connection {
  private pc: RTCPeerConnection;
  private pendingIce: (RTCIceCandidateInit | null)[] = [];

  constructor(
    readonly sender: string,
    private video: HTMLVideoElement,
    private send: (to: string, m: ShareMessage) => void,
    private onVideo: () => void,
  ) {
    // No STUN/TURN: the direct path is the local network only. The Pi's
    // browser is allowed to announce its real IP (Chromium policy set by
    // the installer), because mDNS names can't be resolved on this network.
    this.pc = new RTCPeerConnection({ iceServers: [] });
    this.pc.ontrack = (e) => {
      const stream = e.streams[0] ?? new MediaStream([e.track]);
      if (this.video.srcObject !== stream) this.video.srcObject = stream;
      this.video.play().catch(() => {});
      this.onVideo();
    };
    this.pc.onicecandidate = (e) => this.send(sender, { type: "ice", candidate: e.candidate ? e.candidate.toJSON() : null });
  }

  async accept(sdp: string) {
    await this.pc.setRemoteDescription({ type: "offer", sdp });
    for (const c of this.pendingIce.splice(0)) await this.pc.addIceCandidate(c ?? undefined).catch(() => {});
    const answer = await this.pc.createAnswer();
    await this.pc.setLocalDescription(answer);
    this.send(this.sender, { type: "answer", sdp: answer.sdp });
  }

  async addIce(c: RTCIceCandidateInit | null) {
    if (!this.pc.remoteDescription) {
      this.pendingIce.push(c);
      return;
    }
    await this.pc.addIceCandidate(c ?? undefined).catch(() => {});
  }

  close() {
    this.pc.close();
  }
}

/** Fallback: recorded chunks fetched from the server, played with Media Source Extensions. */
class RelayConnection implements Connection {
  private stopped = false;
  private ms = new MediaSource();
  private sb: SourceBuffer | null = null;
  private url: string;
  private appended = 0;

  constructor(
    readonly sender: string,
    private session: string,
    private mime: string,
    private video: HTMLVideoElement,
    private onVideo: () => void,
    private onGap: () => void,
  ) {
    this.url = URL.createObjectURL(this.ms);
  }

  start() {
    if (!MediaSource.isTypeSupported(this.mime)) {
      console.warn("share: unsupported stream format", this.mime);
      return;
    }
    this.video.srcObject = null;
    this.video.src = this.url;
    this.ms.addEventListener(
      "sourceopen",
      () => {
        this.sb = this.ms.addSourceBuffer(this.mime);
        this.sb.mode = "sequence";
        this.loop();
      },
      { once: true },
    );
  }

  private async loop() {
    let after = -1;
    while (!this.stopped) {
      try {
        const res = await fetch(`/api/share/screen/relay?session=${encodeURIComponent(this.session)}&after=${after}`, {
          cache: "no-store",
        });
        if (this.stopped) return;
        if (res.status === 204) continue;
        if (res.status === 409) {
          const body = (await res.json().catch(() => ({}))) as { error?: string };
          if (body.error === "gap") this.onGap();
          return; // "gone": a new stream (or none) replaces this one
        }
        if (!res.ok) {
          await sleep(1000);
          continue;
        }
        after = Number(res.headers.get("X-Seq"));
        await this.append(await res.arrayBuffer());
      } catch {
        await sleep(1000);
      }
    }
  }

  private async append(data: ArrayBuffer) {
    const sb = this.sb;
    if (!sb || this.stopped) return;
    await this.whenIdle(sb);
    try {
      sb.appendBuffer(data);
    } catch (e) {
      if ((e as DOMException).name === "QuotaExceededError") {
        await this.trim(sb, 5);
        sb.appendBuffer(data);
      } else throw e;
    }
    await this.whenIdle(sb);
    this.appended++;
    const v = this.video;
    if (v.buffered.length) {
      const end = v.buffered.end(v.buffered.length - 1);
      // Stay close to live: skip ahead if we lag more than 1.5 s.
      if (end - v.currentTime > 1.5) v.currentTime = Math.max(0, end - 0.3);
      if (v.paused) v.play().catch(() => {});
      this.onVideo();
    }
    if (this.appended % 40 === 0) await this.trim(sb, 20);
  }

  private async trim(sb: SourceBuffer, keepSeconds: number) {
    const t = this.video.currentTime - keepSeconds;
    if (t <= 0) return;
    await this.whenIdle(sb);
    sb.remove(0, t);
    await this.whenIdle(sb);
  }

  private whenIdle(sb: SourceBuffer) {
    return sb.updating ? new Promise<void>((r) => sb.addEventListener("updateend", () => r(), { once: true })) : Promise.resolve();
  }

  close() {
    this.stopped = true;
    try {
      if (this.ms.readyState === "open") this.ms.endOfStream();
    } catch {
      /* already closed */
    }
    URL.revokeObjectURL(this.url);
  }
}
