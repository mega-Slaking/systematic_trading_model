/**
 * HealthGate (spec §7.2): blocks the app until `/health` confirms the DB exists.
 *
 * Replaces the Streamlit `app.py` `DB_PATH.exists()` guard. While the health
 * query is loading it shows a spinner; on error or `db_exists === false` it
 * shows a blocking message; otherwise it renders its children (the app).
 */

import type { ReactNode } from "react";

import { useHealth } from "../api/hooks";

export function HealthGate({ children }: { children: ReactNode }) {
  const { data, isLoading, isError, error } = useHealth();

  if (isLoading) {
    return <FullScreen title="Connecting to analytics API..." />;
  }

  if (isError) {
    return (
      <FullScreen
        title="Cannot reach the analytics API"
        detail={
          error instanceof Error
            ? error.message
            : "The FastAPI service is not responding. Start it with: uvicorn api.main:app --reload --port 8000"
        }
        tone="error"
      />
    );
  }

  if (!data?.db_exists) {
    return (
      <FullScreen
        title="No database found"
        detail={`Expected SQLite DB at ${data?.db_path ?? "data/database.db"}. Run the backtest/persistence pipeline first.`}
        tone="error"
      />
    );
  }

  return <>{children}</>;
}

function FullScreen({
  title,
  detail,
  tone = "info",
}: {
  title: string;
  detail?: string;
  tone?: "info" | "error";
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        fontFamily: "system-ui, sans-serif",
        color: tone === "error" ? "var(--danger)" : "var(--text)",
        gap: "0.5rem",
        padding: "2rem",
        textAlign: "center",
      }}
    >
      <h2 style={{ margin: 0 }}>{title}</h2>
      {detail ? <p style={{ margin: 0, color: "var(--text-3)", maxWidth: 640 }}>{detail}</p> : null}
    </div>
  );
}
