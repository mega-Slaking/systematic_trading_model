/**
 * ErrorBoundary: contains a render/runtime error in one view instead of letting
 * it white-screen the whole SPA, and surfaces the actual error message (e.g. a
 * lazy-loaded chart chunk that fails to evaluate). Wrap it around each page,
 * keyed by the active tab so navigating away resets it.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Logged so the full stack is visible in the console for diagnosis.
    console.error("ErrorBoundary caught:", error, info);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        style={{
          border: "1px solid #f3c2c2",
          background: "#fdf2f2",
          borderRadius: 8,
          padding: "1.25rem",
          color: "#7a1f1f",
        }}
      >
        <strong>This view failed to render.</strong>
        <pre
          style={{
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            marginTop: "0.75rem",
            fontSize: "0.8rem",
            color: "#922",
          }}
        >
          {error.message}
        </pre>
        <button
          type="button"
          onClick={() => this.setState({ error: null })}
          style={{
            marginTop: "0.5rem",
            padding: "0.3rem 0.7rem",
            borderRadius: 6,
            border: "1px solid #d1d5db",
            background: "#fff",
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </div>
    );
  }
}
