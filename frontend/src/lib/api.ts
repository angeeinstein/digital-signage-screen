export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly body?: unknown) {
    super(message);
  }
}

type Json = Record<string, unknown>;

/** JSON request helper. Adds the header the backend requires on writes (CSRF guard). */
export async function api<T = Json>(path: string, init: { method?: string; body?: unknown; signal?: AbortSignal; keepalive?: boolean } = {}): Promise<T> {
  const res = await fetch(path, {
    method: init.method ?? "GET",
    headers: {
      Accept: "application/json",
      "X-Requested-With": "signage",
      ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    credentials: "same-origin",
    signal: init.signal,
    // Lets requests sent while a page is closing still reach the server.
    keepalive: init.keepalive,
  });
  let body: Json | undefined;
  try {
    body = (await res.json()) as Json;
  } catch {
    body = undefined;
  }
  if (!res.ok || (body && body.ok === false)) {
    const msg = (body && typeof body.error === "string" && body.error) || `HTTP ${res.status}`;
    throw new ApiError(msg, res.status, body);
  }
  return body as T;
}

/** Upload one file as multipart/form-data (field "file"). */
export async function uploadFile<T = Json>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(path, {
    method: "POST",
    headers: { Accept: "application/json", "X-Requested-With": "signage" },
    body: form,
    credentials: "same-origin",
  });
  let body: Json | undefined;
  try {
    body = (await res.json()) as Json;
  } catch {
    body = undefined;
  }
  if (res.status === 413) throw new ApiError("The image is too large (max. 10 MB)", 413, body);
  if (!res.ok || (body && body.ok === false)) {
    const msg = (body && typeof body.error === "string" && body.error) || `HTTP ${res.status}`;
    throw new ApiError(msg, res.status, body);
  }
  return body as T;
}
