import { useState, type FormEvent } from "react";
import { Plane } from "lucide-react";
import { api, ApiError } from "../lib/api";

export function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/auth/login", { method: "POST", body: { username, password } });
      if (window.location.pathname.startsWith("/login")) window.history.replaceState(null, "", "/admin");
      onLoggedIn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <h1>
          <Plane className="icon" /> Dashboard admin
        </h1>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            autoFocus
            required
          />
        </label>
        {error && <div className="alert error">{error}</div>}
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <a href="/" className="muted small">
          ← Back to display
        </a>
      </form>
    </div>
  );
}
