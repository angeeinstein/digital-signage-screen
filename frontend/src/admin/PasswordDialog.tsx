import { useState, type FormEvent } from "react";
import { api, ApiError } from "../lib/api";

const MIN = 8;

export function PasswordDialog(props: { username: string; forced: boolean; onClose: () => void; onChanged: () => void }) {
  const [username, setUsername] = useState(props.username);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next.length < MIN) return setError(`The new password needs at least ${MIN} characters.`);
    if (next !== confirm) return setError("The new passwords do not match.");
    setBusy(true);
    setError(null);
    try {
      await api("/api/auth/password", {
        method: "POST",
        body: { current_password: current, new_password: next, username: username.trim() || undefined },
      });
      props.onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={props.forced ? undefined : props.onClose}>
      <form className="card modal" onSubmit={submit} onClick={(e) => e.stopPropagation()}>
        <h2>Account</h2>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label>
          Current password
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        </label>
        <label>
          New password <span className="muted">(min. {MIN} characters)</span>
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required />
        </label>
        <label>
          Repeat new password
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
        </label>
        {error && <div className="alert error">{error}</div>}
        <div className="row-end">
          {!props.forced && (
            <button type="button" className="btn btn-secondary" onClick={props.onClose}>
              Cancel
            </button>
          )}
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : "Change password"}
          </button>
        </div>
      </form>
    </div>
  );
}
