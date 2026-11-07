import { useEffect, useRef, useState, type FormEvent } from "react";
import { ImageIcon, Megaphone, MonitorPlay, Pencil, Plus, Trash2 } from "lucide-react";
import { api, ApiError, uploadFile } from "../lib/api";
import type { Announcement } from "../lib/types";
import { Card, Field, Select, TextArea, TextInput, Toggle } from "./fields";

type Draft = Omit<Announcement, "id" | "active" | "created_at" | "updated_at">;

const EMPTY: Draft = {
  title: "",
  text: "",
  image: "",
  start_date: "",
  end_date: "",
  in_ticker: true,
  as_slide: true,
  image_fit: "contain",
  enabled: true,
};

/**
 * Event invitations and notices. Saved immediately (not via the Save bar),
 * because images are uploaded as soon as they are picked.
 */
export function Announcements() {
  const [items, setItems] = useState<Announcement[] | null>(null);
  const [editing, setEditing] = useState<{ id: string | null; draft: Draft } | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const load = () =>
    api<{ announcements: Announcement[] }>("/api/admin/announcements")
      .then((r) => setItems(r.announcements))
      .catch((e) => setNotice({ kind: "error", text: e.message }));

  useEffect(() => {
    load();
  }, []);

  const remove = async (a: Announcement) => {
    if (!confirm(`Delete "${a.title || "this announcement"}"?`)) return;
    await api(`/api/admin/announcements/${a.id}`, { method: "DELETE" }).catch((e) => setNotice({ kind: "error", text: e.message }));
    load();
  };

  const showNow = async (a: Announcement) => {
    try {
      const r = await api<{ seconds: number }>(`/api/admin/announcements/${a.id}/preview`, { method: "POST" });
      setNotice({ kind: "ok", text: `Showing it on the display now for ${r.seconds} s (within 5 s).` });
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof ApiError ? e.message : String(e) });
    }
  };

  return (
    <Card
      title="Announcements"
      icon={<Megaphone className="icon" />}
      actions={
        !editing && (
          <button className="btn btn-secondary" onClick={() => setEditing({ id: null, draft: { ...EMPTY } })}>
            <Plus className="icon" /> New
          </button>
        )
      }
    >
      <p className="help">
        Invitations to events and other notices, optionally with a poster. Shown as a full-screen slide every few minutes
        and/or in the ticker, between the start and end date. Changes here are saved immediately.
      </p>
      {notice && (
        <div className={`alert ${notice.kind}`} role="status" onClick={() => setNotice(null)}>
          {notice.text}
        </div>
      )}

      {editing && (
        <Editor
          id={editing.id}
          initial={editing.draft}
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setNotice({ kind: "ok", text: "Saved. The display updates within a few seconds." });
            load();
          }}
        />
      )}

      <div className="ann-list">
        {items?.length === 0 && !editing && <div className="muted">No announcements yet.</div>}
        {items?.map((a) => (
          <div key={a.id} className={`ann${a.active && !a.problem ? "" : " inactive"}`}>
            <div className="ann-thumb" style={a.image ? { backgroundImage: `url("/media/${a.image}")` } : undefined}>
              {!a.image && <Megaphone className="icon" />}
            </div>
            <div className="ann-body">
              <strong>{a.title || "(no title, poster only)"}</strong>
              {a.text && <span className="small muted">{a.text}</span>}
              <div className="ann-tags">
                {a.problem ? (
                  <span className="chip warn">{a.problem}</span>
                ) : (
                  <span className={`chip${a.active ? " on" : ""}`}>{status(a)}</span>
                )}
                {a.as_slide && <span className="chip">Slide</span>}
                {a.in_ticker && <span className="chip">Ticker</span>}
                {(a.start_date || a.end_date) && <span className="chip">{dateRange(a)}</span>}
              </div>
            </div>
            <div className="ann-actions">
              {a.as_slide && (
                <button className="icon-btn" title="Show on the display now" onClick={() => showNow(a)}>
                  <MonitorPlay className="icon" />
                </button>
              )}
              <button className="icon-btn" title="Edit" onClick={() => setEditing({ id: a.id, draft: pick(a) })}>
                <Pencil className="icon" />
              </button>
              <button className="icon-btn" title="Delete" onClick={() => remove(a)}>
                <Trash2 className="icon" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Editor({ id, initial, onCancel, onSaved }: { id: string | null; initial: Draft; onCancel: () => void; onSaved: () => void }) {
  const [d, setD] = useState<Draft>(initial);
  const [busy, setBusy] = useState<"upload" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const set = <K extends keyof Draft>(k: K) => (v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy("upload");
    setError(null);
    try {
      const r = await uploadFile<{ image: string }>("/api/admin/media", file);
      setD((x) => ({ ...x, image: r.image }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy("save");
    setError(null);
    try {
      await api(id ? `/api/admin/announcements/${id}` : "/api/admin/announcements", { method: id ? "PUT" : "POST", body: d });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <form className="ann-editor" onSubmit={save}>
      <TextInput label="Title" value={d.title} onChange={set("title")} placeholder="e.g. Aviation Night – Thursday 18:00" help="Shown on the slide and in the ticker. Can be left empty if the poster says it all (then it is only shown as a slide)." />
      <TextArea label="Text (optional)" value={d.text} onChange={set("text")} rows={2} placeholder="Where, when, what to bring…" />
      <div className="field">
        <label>Poster image (optional)</label>
        <div className="ann-image-preview">
          {d.image ? <img src={`/media/${d.image}`} alt="" /> : <span className="muted small">No image</span>}
          <button type="button" className="btn btn-secondary" disabled={busy !== null} onClick={() => fileInput.current?.click()}>
            <ImageIcon className="icon" /> {busy === "upload" ? "Uploading…" : d.image ? "Replace" : "Choose image"}
          </button>
          {d.image && (
            <button type="button" className="btn btn-ghost" onClick={() => set("image")("")}>
              Remove
            </button>
          )}
          <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden onChange={(e) => upload(e.target.files?.[0])} />
        </div>
        <div className="help">PNG, JPEG, WebP or GIF, up to 10 MB. Landscape (16:9) fills the TV best.</div>
      </div>
      {d.image && (
        <Select
          label="Poster layout on the slide"
          value={d.image_fit}
          options={[
            { value: "contain", label: "Fit whole image (blurred background around it)" },
            { value: "cover", label: "Fill the screen (edges may be cropped)" },
          ]}
          onChange={set("image_fit")}
          help="'Fill' suits 16:9 posters that already contain all the text. A title or text is then shown on a band at the bottom."
        />
      )}
      <div className="grid-2">
        <DateInput label="Show from" value={d.start_date} onChange={set("start_date")} help="Empty = right away" />
        <DateInput label="Show until (including)" value={d.end_date} onChange={set("end_date")} help="Empty = until you remove it" />
      </div>
      <Toggle label="Show as full-screen slide" checked={d.as_slide} onChange={set("as_slide")} />
      <Toggle
        label="Show in the ticker"
        checked={d.in_ticker}
        onChange={set("in_ticker")}
        help={d.title ? "Needs the ticker to be turned on." : "The ticker shows the title, so this needs a title."}
      />
      <Toggle label="Enabled" checked={d.enabled} onChange={set("enabled")} help="Turn off to pause it without deleting it." />
      {error && <div className="alert error">{error}</div>}
      <div className="row-end">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Cancel
        </button>
        <button className="btn btn-primary" disabled={busy !== null}>
          {busy === "save" ? "Saving…" : id ? "Save changes" : "Add announcement"}
        </button>
      </div>
    </form>
  );
}

function DateInput({ label, value, onChange, help }: { label: string; value: string; onChange: (v: string) => void; help?: string }) {
  return (
    <Field label={label} help={help}>
      {(id) => <input id={id} type="date" value={value} onChange={(e) => onChange(e.target.value)} />}
    </Field>
  );
}

function pick(a: Announcement): Draft {
  const { title, text, image, start_date, end_date, in_ticker, as_slide, enabled } = a;
  return { title, text, image, start_date, end_date, in_ticker, as_slide, enabled, image_fit: a.image_fit ?? "contain" };
}

function fmt(d: string): string {
  return new Date(`${d}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function dateRange(a: Announcement): string {
  if (a.start_date && a.end_date) return `${fmt(a.start_date)} – ${fmt(a.end_date)}`;
  if (a.start_date) return `from ${fmt(a.start_date)}`;
  return `until ${fmt(a.end_date)}`;
}

function status(a: Announcement): string {
  if (!a.enabled) return "Paused";
  if (a.active) return "Showing";
  const today = new Date().toLocaleDateString("en-CA");
  return a.start_date && a.start_date > today ? "Scheduled" : "Ended";
}
