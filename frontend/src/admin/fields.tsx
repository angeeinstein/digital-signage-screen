import { useId, useState, type ReactNode } from "react";
import { api, ApiError } from "../lib/api";

export function Field({ label, help, children }: { label: string; help?: ReactNode; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(id)}
      {help && <div className="help">{help}</div>}
    </div>
  );
}

export function TextInput(props: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  help?: ReactNode;
  placeholder?: string;
  type?: "text" | "password";
  readOnly?: boolean;
}) {
  return (
    <Field label={props.label} help={props.help}>
      {(id) => (
        <input
          id={id}
          type={props.type ?? "text"}
          value={props.value}
          placeholder={props.placeholder}
          readOnly={props.readOnly}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => props.onChange(e.target.value)}
        />
      )}
    </Field>
  );
}

export function TextArea(props: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  help?: ReactNode;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <Field label={props.label} help={props.help}>
      {(id) => (
        <textarea
          id={id}
          rows={props.rows ?? 3}
          value={props.value}
          placeholder={props.placeholder}
          spellCheck={false}
          onChange={(e) => props.onChange(e.target.value)}
        />
      )}
    </Field>
  );
}

/** Number input that keeps the raw text while typing (so "4." or "" are allowed). */
export function NumberInput(props: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  help?: ReactNode;
}) {
  const [text, setText] = useState<string | null>(null);
  return (
    <Field label={props.label + (props.unit ? ` (${props.unit})` : "")} help={props.help}>
      {(id) => (
        <input
          id={id}
          type="number"
          inputMode="decimal"
          min={props.min}
          max={props.max}
          step={props.step ?? 1}
          value={text ?? String(props.value)}
          onChange={(e) => {
            setText(e.target.value);
            const n = Number(e.target.value);
            if (e.target.value !== "" && Number.isFinite(n)) props.onChange(n);
          }}
          onBlur={() => setText(null)}
        />
      )}
    </Field>
  );
}

export function Toggle({ label, checked, onChange, help }: { label: string; checked: boolean; onChange: (v: boolean) => void; help?: ReactNode }) {
  const id = useId();
  return (
    <div className="field toggle">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <label htmlFor={id}>{label}</label>
      {help && <div className="help">{help}</div>}
    </div>
  );
}

export function Select<T extends string>(props: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  help?: ReactNode;
}) {
  return (
    <Field label={props.label} help={props.help}>
      {(id) => (
        <select id={id} value={props.value} onChange={(e) => props.onChange(e.target.value as T)}>
          {props.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

export function Card({ title, icon, children, actions }: { title: string; icon?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      <header className="card-head">
        <h2>
          {icon}
          {title}
        </h2>
        {actions}
      </header>
      {children}
    </section>
  );
}

type TestState = { kind: "idle" } | { kind: "running" } | { kind: "ok" | "error"; message: string };

/** Button that runs a backend test with the current (unsaved) form values. */
export function TestButton({ source, draft, label = "Test" }: { source: string; draft: unknown; label?: string }) {
  const [state, setState] = useState<TestState>({ kind: "idle" });
  const run = async () => {
    setState({ kind: "running" });
    try {
      const r = await api<{ message: string }>(`/api/admin/test/${source}`, { method: "POST", body: { config: draft } });
      setState({ kind: "ok", message: r.message });
    } catch (e) {
      setState({ kind: "error", message: e instanceof ApiError ? e.message : String(e) });
    }
  };
  return (
    <div className="test">
      <button type="button" className="btn btn-secondary" onClick={run} disabled={state.kind === "running"}>
        {state.kind === "running" ? "Testing…" : label}
      </button>
      {(state.kind === "ok" || state.kind === "error") && (
        <span className={`test-result ${state.kind}`} role="status">
          {state.kind === "ok" ? "✓ " : "✗ "}
          {state.message}
        </span>
      )}
    </div>
  );
}
