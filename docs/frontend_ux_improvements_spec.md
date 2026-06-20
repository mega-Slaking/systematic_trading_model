# Design Spec: Frontend UX & Maintainability Improvements

## 1. Objective

Improve the React analytics dashboard's **interpretability, usability, and
maintainability** without changing any analytics, compute, or API behaviour. The
work is deliberately sliced into small, independently shippable phases so each
can be delivered to a high standard, reviewed in isolation, and reverted cleanly
if needed. No single phase should be a large multi-area rewrite.

This spec turns a UX review of the current dashboard into actionable scopes. The
review found the app is effective and trustworthy for an expert user, but is held
back by three things:

1. **Density without hierarchy** — some pages (notably Volatility Features) stack
   many equally-weighted sections, so "what do I look at first?" is unclear.
2. **Statelessness** — the active tab and per-view selections are local React
   state, lost on refresh and impossible to bookmark or share.
3. **Styling sprawl** — large inline `style={{}}` objects with hardcoded hex
   colours and duplicated per-mode ternaries, which already caused one visual
   drift (a 14px-vs-17px tooltip button) and make global restyling error-prone.

The product principle:

> Make the existing analytics easier to read, navigate, and return to — and make
> the UI codebase cheaper to change — **without altering any computed values,
> chart data, API responses, or strategy/engine behaviour.**

---

## 2. Architecture context

The live analytics frontend is the **FastAPI + React** stack (the Streamlit →
React migration completed across V1.12.0–V1.16.0; Streamlit is frozen legacy and
must not be extended). This spec touches **only the React presentation layer**
under `frontend/src/`; it does not touch `api/`, `src/`, the database, or any
computed output.

**Current frontend structure (relevant pieces):**

| Area | Location | Notes |
| ---- | -------- | ----- |
| App shell + tab nav | `frontend/src/App.tsx` | 7 tabs, one page at a time, active tab in `useState`. `ErrorBoundary` keyed per tab. |
| Pages | `frontend/src/pages/*.tsx` | `NavComparisonPage`, `ReturnsPage`, `TearsheetPage`, `EtfPricesPage`, `VolatilityPage`, `MacroPage`, `StrategiesPage`. |
| Theme | `frontend/src/theme/ThemeContext.tsx`, `theme/chartTheme.ts`, `index.css` | 3 modes (`light`/`dark`/`contrast`) via `data-theme` + CSS-var palettes; `useChartColors()` for chart chrome; data-trace colours intentionally constant across modes. |
| Charts | `frontend/src/components/charts/*` | Shared `PlotlyLineChart`, `BaseBoxplot` (+ `OutcomeBoxplot`/`ReturnsBoxplot`), lazy-loaded Plotly. |
| Tables / cards | `components/tables/DataTable.tsx`, `components/MetricGrid.tsx`, per-page `SnapCard`/`Stat`/`LabeledBadge` | Several overlapping "labelled value" patterns. |
| Data layer | `api/client.ts`, `api/hooks.ts`, generated `api/schema.d.ts` | TanStack Query hooks; types generated from the live OpenAPI schema. |

**Hard rules, applied to every phase:**

* **No behaviour or data changes.** No computed value, chart series, table row,
  API request/response, or engine/strategy behaviour changes. Phases are
  presentation-only.
* **Pixel-stable light mode unless a phase explicitly says otherwise.** Light
  mode is the reference look; visual refactors (e.g. tokenisation) must be a
  no-op in light mode, matching the existing theme contract.
* **One concern per phase / PR.** A phase that grows beyond its stated scope
  should be split, not expanded.
* **Each phase ends green:** `npm run build` clean (`tsc -b` + Vite), no new
  type errors, and a manual smoke of the affected pages in all three themes.
* **Comment-out, don't delete, when refactoring** working code that may need
  rollback (per repo convention), except for provably-dead code a phase is
  explicitly removing.

---

## 3. Delivery principles

* **Small over big.** Prefer six clean PRs over one sprawling one. Phases are
  ordered so that low-risk *enabling* refactors land first and reduce churn for
  the higher-value phases that follow, but each phase is independently shippable
  and valuable on its own.
* **Behaviour-preserving refactors are verified as such.** Where a phase claims
  "no visual change," call it out and confirm by screenshot/diff in the relevant
  themes.
* **No cross-phase coupling.** A reviewer should be able to understand and accept
  any phase without having read the others.

### Phase summary

| Phase | Scope | Risk | Depends on | User-visible? |
| ----- | ----- | ---- | ---------- | ------------- |
| 1 | Theme token consolidation (kill hardcoded hex / per-mode ternaries) | Low | — | No (refactor) |
| 2 | Shared "labelled value" primitive (`Stat`/`StatCard`) | Low | 1 (tokens) | No (refactor) |
| 3 | Tab + selection persistence (URL / localStorage) | Med | — | Yes |
| 4 | Volatility page information hierarchy (progressive disclosure) | Med | 2 (primitive) | Yes |
| 5 | Interaction affordances + accessibility | Low–Med | — | Yes |
| 6 | Dead-code cleanup + loading/empty-state polish | Low | — | Minor |

Phases 1, 3, 5, 6 are mutually independent and can be reordered. Phase 2 is
easier after 1; Phase 4 is easier after 2 but does not strictly require it.

---

## 4. Phase 1 — Theme token consolidation

**Problem.** Components hardcode hex values (`#06b6d4`, `#f5b301`, `#00b3ff`,
`#1f77b4`) and repeat per-mode ternaries (`mode === "dark" ? … : mode ===
"contrast" ? …`) across `StrategiesPage.tsx`, `charts/PlotlyLineChart.tsx`,
`charts/BaseBoxplot.tsx`, and the regime palettes in `VolatilityPage.tsx` /
`MacroPage.tsx`. This duplication is how the tooltip-size drift happened and
makes a palette change a multi-file hunt.

**Scope.**
* Introduce **semantic chart/data tokens** in the theme layer so components ask
  for meaning, not a hex:
  * Extend `chartTheme.ts`'s `ChartColors` (and the per-mode `PALETTES`) with
    `primarySeries` (cyan on dark/contrast, Plotly blue on light) and a
    `dataPalette` tail, so `PlotlyLineChart`/`BaseBoxplot` read
    `useChartColors().primarySeries` instead of inline ternaries/arrays.
  * Add CSS-var tokens in `index.css` for the remaining UI accents currently
    hardcoded in components (e.g. `--star-live`, `--star-empty`,
    `--ui-accent-strong`) defined per `data-theme`, replacing the `emptyStarColor`
    / `resetTextColor` ternaries in `StrategiesPage.tsx`.
* Centralise the **regime/state shading palettes** (vol confirmed-state bands +
  Macro regime bands, including the high-contrast neon variants) into one
  module (e.g. `theme/regimeColors.ts`) consumed by both pages, instead of two
  separate per-file maps.

**Out of scope.** Any colour *value* change. This is a pure relocation — the
rendered colours in all three modes must be identical before/after.

**Files.** `theme/chartTheme.ts`, `theme/ThemeContext.tsx` (only if a helper is
added), `index.css`, `pages/StrategiesPage.tsx`, `pages/VolatilityPage.tsx`,
`pages/MacroPage.tsx`, `components/charts/PlotlyLineChart.tsx`,
`components/charts/BaseBoxplot.tsx`, new `theme/regimeColors.ts`.

**Acceptance criteria.**
* No literal chart/regime/star hex colour remains in a page or chart component
  (grep clean); they live in the theme layer.
* All three themes render byte-identical to pre-phase (screenshot diff on
  Volatility, Macro, Strategies, Tearsheet).
* `npm run build` clean.

---

## 5. Phase 2 — Shared "labelled value" primitive

**Problem.** "A labelled value/badge" is re-implemented several times: `SnapCard`
and `Stat`/`LabeledBadge` in `VolatilityPage.tsx`, the snapshot tiles in
`MacroPage.tsx` (`SnapshotCardTile`), and `MetricGrid` in the Tearsheet. Each
carries its own inline styles, so they drift.

**Scope.**
* Add a single reusable primitive under `components/` — e.g. `StatCard`
  (label, value, optional badge/pill, optional `InfoTooltip`, optional
  delta/trend line) and a `StatGrid` wrapper (the `repeat(auto-fill, minmax(...))`
  grid used in three places).
* Migrate the Volatility state grid (`SnapCard`) and the Macro "Latest readings"
  tiles to it. Tearsheet `MetricGrid` migration is **optional** within this phase
  and may be deferred to a follow-up if it grows the diff.

**Out of scope.** Changing which metrics are shown, their formatting, or their
order. Layout should match current spacing in light mode.

**Files.** new `components/StatCard.tsx` (+ `StatGrid`), `pages/VolatilityPage.tsx`,
`pages/MacroPage.tsx`, (optional) `components/MetricGrid.tsx` /
`pages/TearsheetPage.tsx`.

**Acceptance criteria.**
* Volatility state grid and Macro snapshot tiles render via the shared primitive,
  visually unchanged in all three themes.
* Net reduction in inline-style lines across the migrated pages.
* `npm run build` clean.

---

## 6. Phase 3 — Tab + selection persistence

**Problem.** Active tab is `useState` in `App.tsx`; per-view selections (ticker,
estimator, window, view, date ranges, ETF/macro pickers) are local page state.
All of it resets on refresh and none of it is shareable/bookmarkable.

**Scope.**
* Sync the **active tab** to the URL (hash or query param) and restore it on
  load. Lightweight approach preferred — a small custom hook or a minimal router;
  do **not** pull in a heavy routing framework if a query-param hook suffices.
* Sync the **highest-value per-page selections** to the URL query string so a
  view is linkable, starting with the Volatility page (`ticker`, `estimator`,
  `window`, `view`) and the ETF/Macro explorer selections. Other pages can adopt
  the same hook incrementally (not required to complete the phase).
* Provide a single shared hook (e.g. `useUrlState`) so pages opt in uniformly.

**Out of scope.** Server-side state, user accounts, saved-view management.
Persisting *every* control on every page (do the high-value ones; leave a clear
pattern for the rest).

**Files.** `App.tsx`, new `hooks/useUrlState.ts` (or `lib/`), `pages/VolatilityPage.tsx`,
`pages/MacroPage.tsx` (explorer), and any page adopting the hook.

**Acceptance criteria.**
* Refreshing the page preserves the active tab and the synced selections.
* A copied URL reproduces the same tab + selections in a fresh session.
* Invalid/garbage params fall back to defaults without crashing.
* `npm run build` clean.

---

## 7. Phase 4 — Volatility page information hierarchy

**Problem.** `VolatilityPage.tsx` stacks the 6-view chart, a 15-card state grid,
the estimator table, the all-asset states table, cross-asset (two tables + a
ratio chart), the outcomes section (table + boxplot + conditions table), and the
latest-values table — all at equal visual weight. It's a long scroll with no
clear reading order.

**Scope.**
* Introduce **progressive disclosure** without removing any content:
  * Keep the diagnostic chart + state card as the always-visible top (the
    centrepiece, already established).
  * Group the lower sections under in-page **sub-tabs or collapsible sections**
    (suggested grouping: *Estimators & State*, *Cross-asset*, *Historical
    outcomes*, *Raw values*), so a user sees one analytical theme at a time.
  * Persist the chosen sub-section via the Phase 3 `useUrlState` hook if
    available (graceful default otherwise).
* Tighten visual hierarchy: section headers, consistent spacing (using the
  Phase 2 primitive for the stat grid).

**Out of scope.** Changing any metric, table, chart series, or its computation.
This is layout/disclosure only. Do **not** redesign the other pages in this phase.

**Files.** `pages/VolatilityPage.tsx` (+ a small `Collapsible`/`SubTabs`
component under `components/` if one doesn't already exist).

**Acceptance criteria.**
* All current content remains reachable; nothing is removed.
* The page presents a clear default reading order; secondary analysis is one
  interaction away rather than always expanded.
* Works in all three themes; `npm run build` clean.

---

## 8. Phase 5 — Interaction affordances & accessibility

**Problem.** Some interactions are discoverable only by reading prose (the
Strategies ☆ is clickable; chart legends toggle curves). The tab nav is plain
buttons without tablist semantics or keyboard arrow navigation.

**Scope.**
* **Affordances:** clearer hover/cursor states on interactive table cells (the
  ☆), and a small, unobtrusive hint where an interaction is non-obvious (e.g.
  "click a legend entry to toggle a series").
* **Accessibility:** give the tab nav `role="tablist"` / `role="tab"` +
  `aria-selected` + left/right arrow-key navigation; ensure focus-visible styles
  on tabs and the star buttons; confirm `InfoTooltip` triggers are keyboard
  reachable (they already open on focus — verify).

**Out of scope.** Making Plotly charts screen-reader accessible (out of practical
reach); full WCAG audit. Keep this to the app chrome and custom controls.

**Files.** `App.tsx` (tab nav), `pages/StrategiesPage.tsx` (star affordance),
chart legend hint where shown, `index.css` (focus-visible tokens).

**Acceptance criteria.**
* Tab nav is operable by keyboard (Tab to focus, arrows to move, Enter/Space to
  activate) with correct ARIA state.
* Interactive controls have visible focus and hover affordances.
* `npm run build` clean.

---

## 9. Phase 6 — Dead-code cleanup & state polish

**Problem.** `App.tsx` has now-dead machinery (`ENABLED_TABS` equals `TABS`, so
the disabled-tab branch and `ComingSoon` are unreachable). Loading states are
bare "Loading…" text.

**Scope.**
* Remove the unreachable disabled-tab logic and `ComingSoon` (all tabs ship), or
  keep the mechanism only if a future-gated tab is actually planned — decide and
  tidy.
* Replace the most prominent bare-text loading states with lightweight skeletons
  (chart/table placeholders) for a more finished feel — start with the heaviest
  pages (Tearsheet, Volatility), not every query.
* Sweep for any other obviously-dead branches introduced by recent work (e.g. the
  commented-out snapshot section — confirm it should stay commented or be removed
  per the owner's call).

**Out of scope.** Behavioural changes; redesigning loading UX wholesale.

**Files.** `App.tsx`, the targeted pages, a small `Skeleton` component if added.

**Acceptance criteria.**
* No unreachable tab/`ComingSoon` code remains (unless an intentional gated tab
  is documented).
* Heaviest pages show a skeleton rather than a bare string while loading.
* `npm run build` clean.

---

## 10. Non-goals

* No changes to `api/`, `src/`, the database, or any computed analytics.
* No new analytics views, metrics, or endpoints.
* No backend or engine/strategy behaviour change.
* No reintroduction or extension of the Streamlit app.
* No heavyweight dependencies where a small local hook/component suffices
  (routing, styling, state).

## 11. Definition of done (per phase)

* Scope matches exactly one section above; anything extra is split out.
* `tsc -b` / `npm run build` clean; no new type errors or warnings introduced.
* Manual smoke of affected pages in **light, dark, and high-contrast** themes.
* For refactor phases (1, 2): a stated, verified "no visual change in light mode"
  (screenshot/diff).
* README changelog entry added per the repo's SemVer convention (UX/maintenance
  phases are typically `z`/patch unless a phase adds user-facing capability like
  Phase 3/4, which are `y`/minor).
