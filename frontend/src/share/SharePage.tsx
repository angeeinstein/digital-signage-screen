import { useEffect, useRef, useState, type FormEvent } from "react";
import { Loader2, MonitorUp, Square, Wifi, Globe } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { ShareSession, type Mode } from "./session";
import "./share.css";

interface Info {
  enabled: boolean;
  relay: boolean;
  screen_online: boolean;
  email: string;
}

type Step =
  | { kind: "loading" }
  | { kind: "unavailable"; text: string }
  | { kind: "start" }
  | { kind: "code"; token: string; expires: number }
  | { kind: "ready"; token: string; relay: boolean }
  | { kind: "sharing"; mode: Mode }
  | { kind: "ended"; text: string };

const NAME_KEY = "signage.share.name";

function loadName(): string {
  try {
    return localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveName(name: string) {
  try {
    localStorage.setItem(NAME_KEY, name);
  } catch {
    /* private mode */
  }
}

const canShare = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getDisplayMedia;

/** /share: lets a laptop show its screen on the TV after entering the code shown there. */
export function SharePage() {
  const [step, setStep] = useState<Step>({ kind: "loading" });
  const [info, setInfo] = useState<Info | null>(null);
  const [name, setName] = useState(loadName);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const session = useRef<ShareSession | null>(null);
  const preview = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);

  useEffect(() => {
    document.title = "Share your screen";
    api<Info>("/api/share/info")
      .then((i) => {
        setInfo(i);
        if (!i.enabled) setStep({ kind: "unavailable", text: "Screen sharing is turned off." });
        else if (!canShare)
          setStep({ kind: "unavailable", text: "This browser can't share its screen. Use Chrome, Edge, Firefox or Safari on a laptop." });
        else setStep({ kind: "start" });
      })
      .catch(() => setStep({ kind: "unavailable", text: "The dashboard can't be reached." }));
  }, []);

  useEffect(() => {
    if (step.kind !== "code") return;
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [step.kind]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (session.current) e.preventDefault();
    };
    const leave = () => session.current?.stop();
    window.addEventListener("beforeunload", warn);
    window.addEventListener("pagehide", leave);
    return () => {
      window.removeEventListener("beforeunload", warn);
      window.removeEventListener("pagehide", leave);
    };
  }, []);

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : String(e));

  const requestCode = async (e?: FormEvent) => {
    e?.preventDefault();
    setError(null);
    setBusy(true);
    saveName(name.trim());
    try {
      const r = await api<{ token: string; expires_in: number }>("/api/share/request", { method: "POST", body: { name: name.trim() } });
      setCode("");
      setStep({ kind: "code", token: r.token, expires: Date.now() + r.expires_in * 1000 });
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const verify = async (token: string, value: string) => {
    setError(null);
    setBusy(true);
    try {
      const r = await api<{ relay: boolean }>("/api/share/verify", { method: "POST", body: { token, code: value } });
      setStep({ kind: "ready", token, relay: r.relay });
    } catch (err) {
      fail(err);
      setCode("");
      if (err instanceof ApiError && err.status === 410) setStep({ kind: "start" });
    } finally {
      setBusy(false);
    }
  };

  const onCode = (token: string, value: string) => {
    const digits = value.replace(/\D/g, "").slice(0, 4);
    setCode(digits);
    if (digits.length === 4) verify(token, digits);
  };

  // Must run directly in the click handler: browsers only open the picker on a user action.
  const pickScreen = async (token: string, relay: boolean) => {
    setError(null);
    let s: MediaStream;
    try {
      s = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: { ideal: 30, max: 30 }, width: { max: 1920 }, height: { max: 1080 } },
        audio: true,
      });
    } catch (err) {
      if ((err as DOMException).name !== "NotAllowedError") fail(err);
      return; // picker cancelled
    }
    stream.current = s;
    const sess = new ShareSession(
      token,
      s,
      relay,
      (mode) => setStep({ kind: "sharing", mode }),
      (text) => {
        session.current = null;
        stream.current = null;
        setStep({ kind: "ended", text });
      },
    );
    session.current = sess;
    setStep({ kind: "sharing", mode: "connecting" });
    sess.start();
  };

  useEffect(() => {
    if (step.kind === "sharing" && preview.current && stream.current && preview.current.srcObject !== stream.current) {
      preview.current.srcObject = stream.current;
    }
  }, [step]);

  return (
    <main className="share-page">
      <div className="share-card">
        <h1>
          <MonitorUp className="icon" aria-hidden /> Share your screen on the TV
        </h1>

        {step.kind === "loading" && <p className="muted">Loading…</p>}

        {step.kind === "unavailable" && <p>{step.text}</p>}

        {step.kind === "start" && (
          <form onSubmit={requestCode}>
            {!info?.screen_online && <p className="warn">The TV doesn't seem to be on right now.</p>}
            <label>
              Your name (shown on the TV)
              <input
                value={name}
                maxLength={40}
                placeholder={info?.email || "e.g. Anna – Group 3"}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
              />
            </label>
            <button className="btn btn-primary" disabled={busy}>
              {busy ? <Loader2 className="icon spin" /> : <MonitorUp className="icon" />} Show a code on the TV
            </button>
          </form>
        )}

        {step.kind === "code" && (
          <form onSubmit={(e) => (e.preventDefault(), verify(step.token, code))}>
            <p>Enter the 4-digit code that is now shown on the TV.</p>
            <input
              className="code-input"
              value={code}
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              placeholder="····"
              aria-label="Code from the TV"
              disabled={busy}
              onChange={(e) => onCode(step.token, e.target.value)}
            />
            {step.expires > now ? (
              <p className="muted small">The code is valid for {Math.ceil((step.expires - now) / 1000)} s.</p>
            ) : (
              <p className="warn small">
                The code has expired.{" "}
                <button type="button" className="link" onClick={() => requestCode()}>
                  Show a new one
                </button>
              </p>
            )}
          </form>
        )}

        {step.kind === "ready" && (
          <div>
            <p>Code accepted. Now choose a window, a browser tab or your whole screen.</p>
            <button className="btn btn-primary" onClick={() => pickScreen(step.token, step.relay)}>
              <MonitorUp className="icon" /> Choose what to share
            </button>
            <p className="muted small">Sound is shared too if you tick "Share audio" in the browser's dialog.</p>
          </div>
        )}

        {step.kind === "sharing" && (
          <div>
            <video ref={preview} className="share-preview" autoPlay muted playsInline />
            <p className="share-status">
              {step.mode === "connecting" && (
                <>
                  <Loader2 className="icon spin" /> Connecting to the TV…
                </>
              )}
              {step.mode === "direct" && (
                <>
                  <Wifi className="icon ok" /> On the TV · direct connection
                </>
              )}
              {step.mode === "relay" && (
                <>
                  <Globe className="icon" /> On the TV · through the internet (about 1–2 s delay)
                </>
              )}
            </p>
            <button className="btn btn-danger" onClick={() => session.current?.stop()}>
              <Square className="icon" /> Stop sharing
            </button>
          </div>
        )}

        {step.kind === "ended" && (
          <div>
            <p>{step.text}</p>
            <button className="btn btn-primary" onClick={() => setStep({ kind: "start" })}>
              Share again
            </button>
          </div>
        )}

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
    </main>
  );
}
