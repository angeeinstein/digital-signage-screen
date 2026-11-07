import { useEffect, useState } from "react";
import { MonitorUp } from "lucide-react";
import { api } from "../lib/api";
import type { Config } from "../lib/types";
import { Card, NumberInput, TextInput, Toggle } from "./fields";

interface ShareStatus {
  state: { pending: { name: string } | null; active: { name: string; mode: string } | null };
  screen_online: boolean;
  public_url: string;
  detected_url: string;
}

/** Screen sharing settings (saved with the Save bar) plus live status. */
export function ShareCard({ draft, setDraft }: { draft: Config; setDraft: (c: Config) => void }) {
  const s = draft.share;
  const set = <K extends keyof Config["share"]>(k: K) => (v: Config["share"][K]) => setDraft({ ...draft, share: { ...s, [k]: v } });
  const [status, setStatus] = useState<ShareStatus | null>(null);

  const load = () =>
    api<ShareStatus>("/api/admin/share")
      .then(setStatus)
      .catch(() => {});

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const stopNow = async () => {
    await api("/api/admin/share/stop", { method: "POST" }).catch(() => {});
    load();
  };

  const link = `${(s.public_url || status?.detected_url || window.location.origin).replace(/\/$/, "")}/share`;
  const active = status?.state.active;

  return (
    <Card title="Screen sharing" icon={<MonitorUp className="icon" />}>
      <Toggle
        label="Allow sharing a laptop screen on the TV"
        checked={s.enabled}
        onChange={set("enabled")}
        help="Anyone with the link can ask to share; the TV then shows a 4-digit code that must be entered on the laptop."
      />
      {s.enabled && (
        <>
          <div className="field">
            <label>Link for sharing</label>
            <div className="input-row">
              <input readOnly value={link} onFocus={(e) => e.target.select()} />
              <button type="button" className="btn btn-secondary" onClick={() => navigator.clipboard?.writeText(link)}>
                Copy
              </button>
            </div>
            <div className="help">
              {status?.detected_url
                ? `Detected from visits through Cloudflare: ${status.detected_url}`
                : "No visit through Cloudflare seen yet; open the dashboard once through its public address to detect it."}
            </div>
          </div>
          <TextInput
            label="Public address (optional)"
            value={s.public_url}
            placeholder={status?.detected_url || "https://…"}
            onChange={set("public_url")}
            help="Only needed if the detected address is wrong. Shown on the TV while someone is sharing."
          />
          <NumberInput
            label="End sharing automatically after"
            unit="minutes"
            value={s.max_minutes}
            min={0}
            max={480}
            step={15}
            onChange={set("max_minutes")}
            help={
              s.max_minutes > 0
                ? `5 minutes before the end, the laptop can extend once by ${Math.round(s.max_minutes / 2)} minutes. Prevents a forgotten laptop from blocking the TV. 0 = no limit.`
                : "No limit: sharing runs until it is stopped or the laptop disconnects."
            }
          />
          <Toggle
            label="Fall back to streaming through the internet"
            checked={s.relay_enabled}
            onChange={set("relay_enabled")}
            help="Normally the video goes directly over the local network. If that fails (e.g. the laptop is on another network), it is sent through this server and Cloudflare instead, with 1–2 s delay."
          />
          <div className="row-between">
            <span className="small muted">
              {!status
                ? "…"
                : active
                  ? `Now sharing: ${active.name} (${active.mode === "relay" ? "through the internet" : active.mode === "direct" ? "direct" : "connecting"})`
                  : status.screen_online
                    ? "The TV is ready. Nobody is sharing."
                    : "The TV is not connected (or the dashboard isn't open on the Pi itself)."}
            </span>
            {active && (
              <button type="button" className="btn btn-secondary" onClick={stopNow}>
                Stop sharing
              </button>
            )}
          </div>
        </>
      )}
    </Card>
  );
}
