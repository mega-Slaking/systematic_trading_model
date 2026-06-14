/**
 * InfoTooltip: a small "ⓘ" trigger that reveals an explanatory panel on hover or
 * keyboard focus. Themed via the CSS variable tokens so it reads correctly in all
 * three colour modes. Content is arbitrary JSX (headings, lists, etc.).
 */

import { useState, type ReactNode } from "react";

export function InfoTooltip({
  children,
  label = "More information",
  width = 340,
}: {
  children: ReactNode;
  label?: string;
  width?: number;
}) {
  const [open, setOpen] = useState(false);

  return (
    <span
      style={{ position: "relative", display: "inline-flex", verticalAlign: "middle" }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={label}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 17,
          height: 17,
          padding: 0,
          borderRadius: "50%",
          border: "1px solid var(--border-strong)",
          background: "var(--surface)",
          color: "var(--text-muted)",
          fontFamily: "Georgia, 'Times New Roman', serif",
          fontStyle: "italic",
          fontSize: "0.72rem",
          lineHeight: 1,
          cursor: "help",
        }}
      >
        i
      </button>

      {open && (
        <span
          role="tooltip"
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            left: 0,
            zIndex: 50,
            width,
            maxWidth: "80vw",
            padding: "0.75rem 0.85rem",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            boxShadow: "0 8px 24px rgba(0, 0, 0, 0.18)",
            color: "var(--text)",
            fontFamily: "var(--font-dashboard)",
            fontSize: "0.8rem",
            fontWeight: 400,
            lineHeight: 1.5,
            textAlign: "left",
            whiteSpace: "normal",
          }}
        >
          {children}
        </span>
      )}
    </span>
  );
}
