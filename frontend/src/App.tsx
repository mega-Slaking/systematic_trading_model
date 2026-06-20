/**
 * App shell (spec §7.2): header + tab nav, mirroring `streamlit/app.py`.
 *
 * Phases 1-2 wire the first three business views (NAV Comparison, Returns
 * Analysis, ETF Prices) behind the tab nav; the remaining tabs are present but
 * disabled until their phases land. Everything sits behind the `HealthGate`.
 */

import { useHealth } from "./api/hooks";
import { useUrlState } from "./hooks/useUrlState";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { HealthGate } from "./components/HealthGate";
import { ThemeToggle } from "./components/ThemeToggle";
import { EtfPricesPage } from "./pages/EtfPricesPage";
import { MacroPage } from "./pages/MacroPage";
import { NavComparisonPage } from "./pages/NavComparisonPage";
import { ReturnsPage } from "./pages/ReturnsPage";
import { StrategiesPage } from "./pages/StrategiesPage";
import { TearsheetPage } from "./pages/TearsheetPage";
import { VolatilityPage } from "./pages/VolatilityPage";

const TABS = [
  "NAV Comparison",
  "Returns Analysis",
  "Tearsheet",
  "ETF Prices",
  "Volatility Features",
  "ETFs vs Macro",
  "Strategies",
] as const;

type Tab = (typeof TABS)[number];

// Tabs with a built page (all of them as of Phase 4).
const ENABLED_TABS: ReadonlySet<Tab> = new Set<Tab>([
  "NAV Comparison",
  "Returns Analysis",
  "Tearsheet",
  "ETF Prices",
  "Volatility Features",
  "ETFs vs Macro",
  "Strategies",
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
  // Active tab is URL-synced (refresh-safe + shareable); an unknown ?tab= falls back.
  const [active, setActive] = useUrlState<Tab>("tab", "NAV Comparison", { allowed: TABS });

  return (
    <div style={{ fontFamily: "var(--font-dashboard)", maxWidth: "min(2000px, 95vw)", margin: "0 auto", padding: "1.5rem 2rem" }}>
      <header style={{ borderBottom: "1px solid var(--border)", paddingBottom: "0.75rem", marginBottom: "1rem", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
        <div>
          <h1 style={{ margin: 0, fontFamily: "var(--font-title)" }}>Scenario Testing Dashboard</h1>
          <p style={{ margin: "0.25rem 0 0", color: "var(--text-muted)" }}>
            Analyze backtest scenarios. API v{data?.api_version ?? "?"} — connected.
          </p>
        </div>
        <ThemeToggle />
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
                border: isActive ? "1px solid var(--accent)" : "1px solid transparent",
                background: isActive ? "var(--accent-bg)" : "var(--surface-tab)",
                color: enabled ? (isActive ? "var(--accent)" : "var(--text-tab)") : "var(--text-disabled)",
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
          ) : active === "Tearsheet" ? (
            <TearsheetPage />
          ) : active === "ETF Prices" ? (
            <EtfPricesPage />
          ) : active === "Volatility Features" ? (
            <VolatilityPage />
          ) : active === "ETFs vs Macro" ? (
            <MacroPage />
          ) : active === "Strategies" ? (
            <StrategiesPage />
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
    <section style={{ border: "1px dashed var(--border-strong)", borderRadius: 8, padding: "2rem", color: "var(--text-3)", textAlign: "center" }}>
      <strong>{tab}</strong>
      <p style={{ margin: "0.5rem 0 0" }}>This view lands in a later phase.</p>
    </section>
  );
}
