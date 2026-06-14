/**
 * Theme mode context: the single source of truth for the colour theme.
 *
 * Three modes — "light" (the original look), "dark", and "contrast"
 * (electric-blue-on-black high contrast). The active mode is written to the
 * `data-theme` attribute on <html>, where the CSS variable palettes in
 * index.css pick it up; everything else in the app reads those variables. The
 * choice is persisted to localStorage so it survives reloads.
 *
 * This affects colour only — no layout, typography, or logic depends on it.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export const THEME_MODES = ["light", "dark", "contrast"] as const;
export type ThemeMode = (typeof THEME_MODES)[number];

const STORAGE_KEY = "dashboard-theme";

interface ThemeContextValue {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  /** Advance to the next mode in THEME_MODES order (wraps). */
  cycle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStoredMode(): ThemeMode {
  if (typeof localStorage === "undefined") return "light";
  const stored = localStorage.getItem(STORAGE_KEY);
  return THEME_MODES.includes(stored as ThemeMode) ? (stored as ThemeMode) : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readStoredMode);

  // Reflect the mode onto <html data-theme> (where the CSS palettes live) and
  // persist it. Runs on mount too, so the initial stored mode is applied.
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // localStorage can throw in private modes; the in-memory state still works.
    }
  }, [mode]);

  const setMode = useCallback((next: ThemeMode) => setModeState(next), []);
  const cycle = useCallback(
    () => setModeState((prev) => THEME_MODES[(THEME_MODES.indexOf(prev) + 1) % THEME_MODES.length]),
    [],
  );

  const value = useMemo<ThemeContextValue>(() => ({ mode, setMode, cycle }), [mode, setMode, cycle]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
