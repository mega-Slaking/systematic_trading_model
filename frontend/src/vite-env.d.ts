/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the FastAPI service. Defaults to `/api/v1` (Vite dev proxy). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
