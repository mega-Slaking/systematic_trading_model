/**
 * StatCard / StatGrid: the shared "labelled value tile" used by the dashboards
 * (the Volatility state grid and the Macro "Latest readings" row). One place for
 * the card shell, uppercase label header, and tabular value styling so the tiles
 * across pages can't drift.
 *
 * Flexible slots:
 *   - `info`        — an InfoTooltip rendered inline next to the label.
 *   - `headerRight` — content pushed to the right of the header (e.g. a "stale" tag).
 *   - `value`       — default value rendering (1.2rem, tabular Play font).
 *   - `children`    — custom value content (e.g. a coloured badge), replaces `value`.
 *   - `footer`      — extra lines below the value (e.g. a delta + "as of" date).
 */

import type { ReactNode } from "react";

import { InfoTooltip } from "./InfoTooltip";

export function StatCard({
  label,
  value,
  children,
  info,
  headerRight,
  footer,
}: {
  label: string;
  value?: string;
  children?: ReactNode;
  info?: ReactNode;
  headerRight?: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div style={{
      border: "1px solid var(--border-soft)", borderRadius: 8,
      padding: "0.8rem 0.9rem", background: "var(--surface-raised)",
    }}>
      <div style={{
        fontSize: "0.72rem", color: "var(--text-subtle)", textTransform: "uppercase",
        letterSpacing: "0.02em", display: "flex", alignItems: "center", gap: "0.4rem",
        justifyContent: headerRight ? "space-between" : undefined,
      }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
          {label}
          {info ? <InfoTooltip label={label}>{info}</InfoTooltip> : null}
        </span>
        {headerRight}
      </div>
      {children ? (
        <div style={{ marginTop: "0.35rem" }}>{children}</div>
      ) : (
        <div style={{ fontSize: "1.2rem", marginTop: "0.35rem", fontVariantNumeric: "tabular-nums", fontFamily: "var(--font-data)" }}>
          {value}
        </div>
      )}
      {footer}
    </div>
  );
}

/** Responsive grid of StatCards. `minColWidth`/`gap` match each page's current layout. */
export function StatGrid({
  children,
  minColWidth = 170,
  gap = "1rem",
}: {
  children: ReactNode;
  minColWidth?: number;
  gap?: string;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(${minColWidth}px, 1fr))`, gap }}>
      {children}
    </div>
  );
}
