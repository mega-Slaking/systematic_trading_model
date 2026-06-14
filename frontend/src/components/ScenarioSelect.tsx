/**
 * ScenarioSelect (spec §7.2): a compact multi-select for backtest scenarios,
 * shared by the NAV-comparison and Returns pages. Selection order follows the
 * canonical `scenarios` order, not click order.
 */

import { type ReactNode } from "react";

interface ScenarioSelectProps {
  scenarios: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  label?: string;
}

export function ScenarioSelect({ scenarios, selected, onChange, label = "Scenarios" }: ScenarioSelectProps) {
  const selectedSet = new Set(selected);

  function toggle(id: string) {
    const next = new Set(selectedSet);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    onChange(scenarios.filter((s) => next.has(s)));
  }

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "0.75rem", marginBottom: "1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
        <strong style={{ fontSize: "0.9rem" }}>
          {label}{" "}
          <span style={{ color: "var(--text-faint)", fontWeight: 400 }}>
            ({selected.length}/{scenarios.length})
          </span>
        </strong>
        <span style={{ display: "flex", gap: "0.4rem" }}>
          <SmallButton onClick={() => onChange(scenarios)}>All</SmallButton>
          <SmallButton onClick={() => onChange([])}>None</SmallButton>
        </span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
        {scenarios.map((id) => {
          const on = selectedSet.has(id);
          return (
            <label
              key={id}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.35rem",
                padding: "0.2rem 0.5rem",
                borderRadius: 6,
                border: `1px solid ${on ? "var(--accent)" : "var(--border-strong)"}`,
                background: on ? "var(--accent-bg)" : "var(--surface)",
                color: on ? "var(--accent)" : "var(--text-3)",
                fontSize: "0.8rem",
                cursor: "pointer",
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              }}
            >
              <input type="checkbox" checked={on} onChange={() => toggle(id)} style={{ margin: 0 }} />
              {id}
            </label>
          );
        })}
      </div>
    </div>
  );
}

function SmallButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: "0.2rem 0.6rem",
        borderRadius: 6,
        border: "1px solid var(--border-strong)",
        background: "var(--surface-sunken)",
        fontSize: "0.8rem",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}
