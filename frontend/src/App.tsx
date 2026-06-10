/**
 * App shell (spec §7.2): header + tab nav, mirroring `streamlit/app.py`.
 *
 * Phases 1-2 wire the first three business views (NAV Comparison, Returns
 * Analysis, ETF Prices) behind the tab nav; the remaining tabs are present but
 * disabled until their phases land. Everything sits behind the `HealthGate`.
 */

import { useState } from "react";

import { useHealth } from "./api/hooks";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { HealthGate } from "./components/HealthGate";
import { EtfPricesPage } from "./pages/EtfPricesPage";
import { NavComparisonPage } from "./pages/NavComparisonPage";
import { ReturnsPage } from "./pages/ReturnsPage";

const TABS = [
  "NAV Comparison",
  "Returns Analysis",
  "Tearsheet",
  "ETF Prices",
  "Volatility Features",
  "ETFs vs Macro",
] as const;

type Tab = (typeof TABS)[number];

// Tabs with a built page (grows each phase).
const ENABLED_TABS: ReadonlySet<Tab> = new Set<Tab>([
  "NAV Comparison",
  "Returns Analysis",
  "ETF Prices",
]);

export default function App() {
  return (
    <HealthGate>
      <Shell />
    </HealthGate>
  );
}

function Shell() {
  const { data } = useHealth();
  const [active, setActive] = useState<Tab>("NAV Comparison");

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 1200, margin: "0 auto", padding: "1.5rem" }}>
      <header style={{ borderBottom: "1px solid #e5e5e5", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
        <h1 style={{ margin: 0 }}>Scenario Testing Dashboard</h1>
        <p style={{ margin: "0.25rem 0 0", color: "#666" }}>
          Analyze backtest scenarios. API v{data?.api_version ?? "?"} — connected.
        </p>
      </header>

      <nav style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1.5rem" }}>
        {TABS.map((tab) => {
          const enabled = ENABLED_TABS.has(tab);
          const isActive = tab === active;
          return (
            <button
              key={tab}
              type="button"
              disabled={!enabled}
              onClick={() => setActive(tab)}
              title={enabled ? undefined : "Coming in a later phase"}
              style={{
                padding: "0.4rem 0.75rem",
                borderRadius: 6,
                border: isActive ? "1px solid #1f77b4" : "1px solid transparent",
                background: isActive ? "#e8f1fb" : "#f3f4f6",
                color: enabled ? (isActive ? "#1f77b4" : "#374151") : "#9ca3af",
                cursor: enabled ? "pointer" : "not-allowed",
                fontSize: "0.9rem",
              }}
            >
              {tab}
            </button>
          );
        })}
      </nav>

      <main>
        <ErrorBoundary key={active}>
          {active === "NAV Comparison" ? (
            <NavComparisonPage />
          ) : active === "Returns Analysis" ? (
            <ReturnsPage />
          ) : active === "ETF Prices" ? (
            <EtfPricesPage />
          ) : (
            <ComingSoon tab={active} />
          )}
        </ErrorBoundary>
      </main>
    </div>
  );
}

function ComingSoon({ tab }: { tab: Tab }) {
  return (
    <section style={{ border: "1px dashed #d1d5db", borderRadius: 8, padding: "2rem", color: "#555", textAlign: "center" }}>
      <strong>{tab}</strong>
      <p style={{ margin: "0.5rem 0 0" }}>This view lands in a later phase.</p>
    </section>
  );
}
