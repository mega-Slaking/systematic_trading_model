/**
 * Typed fetch wrapper for the FastAPI service (spec §7.2).
 *
 * Base URL comes from `VITE_API_BASE_URL`; it defaults to `/api/v1`, which the
 * Vite dev proxy forwards to the API on :8000 (so CORS never bites in dev,
 * spec §8). Errors are normalized to the API's `{ detail, code }` envelope
 * (spec §4.1) and thrown as `ApiError`.
 */

export interface ApiErrorBody {
  detail: string;
  code?: string | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.detail);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code ?? null;
  }
}

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

/** GET `path` (relative to the API base) and parse JSON, raising `ApiError` on failure. */
export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const resp = await fetch(url, {
    headers: { Accept: "application/json" },
    ...init,
  });

  if (!resp.ok) {
    let body: ApiErrorBody = { detail: `Request failed: ${resp.status}` };
    try {
      body = (await resp.json()) as ApiErrorBody;
    } catch {
      // non-JSON error body; keep the generic detail above
    }
    throw new ApiError(resp.status, body);
  }

  return (await resp.json()) as T;
}

/** POST a JSON body to `path` and parse the JSON response, raising `ApiError` on failure. */
export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!resp.ok) {
    let errorBody: ApiErrorBody = { detail: `Request failed: ${resp.status}` };
    try {
      errorBody = (await resp.json()) as ApiErrorBody;
    } catch {
      // keep the generic detail
    }
    throw new ApiError(resp.status, errorBody);
  }

  return (await resp.json()) as T;
}
