/**
 * App shell (spec §7.2): header + tab nav, mirroring `streamlit/app.py`. All
 * seven business views are built; the tab nav is an ARIA tablist behind the
 * `HealthGate`.
 */

import type { KeyboardEvent } from "react";

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

/** Stable DOM id for a tab button, so the panel can label itself + arrow-nav can focus. */
const tabId = (tab: Tab) => `tab-${tab.replace(/\s+/g, "-").toLowerCase()}`;

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

  // ARIA tablist keyboard model: arrows/Home/End move between tabs (wrapping) and
  // activate, moving focus to the newly-selected tab.
  function onTabKeyDown(e: KeyboardEvent<HTMLButtonElement>, tab: Tab) {
    const i = TABS.indexOf(tab);
    if (i < 0) return;
    let next: Tab | undefined;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = TABS[(i + 1) % TABS.length];
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = TABS[(i - 1 + TABS.length) % TABS.length];
    else if (e.key === "Home") next = TABS[0];
    else if (e.key === "End") next = TABS[TABS.length - 1];
    if (!next) return;
    e.preventDefault();
    setActive(next);
    document.getElementById(tabId(next))?.focus();
  }

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

      <nav
        role="tablist"
        aria-label="Dashboard views"
        style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1.5rem" }}
      >
        {TABS.map((tab) => {
          const isActive = tab === active;
          return (
            <button
              key={tab}
              id={tabId(tab)}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls="dashboard-tabpanel"
              tabIndex={isActive ? 0 : -1}
              onClick={() => setActive(tab)}
              onKeyDown={(e) => onTabKeyDown(e, tab)}
              style={{
                padding: "0.4rem 0.75rem",
                borderRadius: 6,
                border: isActive ? "1px solid var(--accent)" : "1px solid transparent",
                background: isActive ? "var(--accent-bg)" : "var(--surface-tab)",
                color: isActive ? "var(--accent)" : "var(--text-tab)",
                cursor: "pointer",
                fontSize: "0.9rem",
              }}
            >
              {tab}
            </button>
          );
        })}
      </nav>

      <main
        id="dashboard-tabpanel"
        role="tabpanel"
        aria-labelledby={tabId(active)}
        style={{ paddingBottom: "6rem" }}
      >
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
          ) : (
            <StrategiesPage />
          )}
        </ErrorBoundary>
      </main>
    </div>
  );
}
