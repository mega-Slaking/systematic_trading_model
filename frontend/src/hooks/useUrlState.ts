/**
 * useUrlState — sync a discrete UI selection (tab, dropdown, view toggle) to a
 * URL query param so views are refresh-safe, bookmarkable, and shareable.
 *
 * Deliberately tiny: no router dependency. Reads the param once on mount, writes
 * via `history.replaceState` (no history-stack spam — the URL just mirrors the
 * current state). The default value is omitted from the URL so links stay clean,
 * and an unknown value (garbage param, or one no longer in `allowed`) falls back
 * to the default rather than breaking the page. Multiple keys coexist because
 * each write reads the current query string and edits only its own key.
 *
 * For discrete selections only — do not wire to free-text inputs (every keystroke
 * would rewrite the URL).
 */

import { useCallback, useState } from "react";

function readParam(key: string): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get(key);
}

function writeParam(key: string, value: string | null): void {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  if (value == null || value === "") params.delete(key);
  else params.set(key, value);
  const qs = params.toString();
  const url = `${window.location.pathname}${qs ? `?${qs}` : ""}${window.location.hash}`;
  window.history.replaceState(window.history.state, "", url);
}

export function useUrlState<T extends string = string>(
  key: string,
  defaultValue: T,
  opts?: { allowed?: readonly T[] },
): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => {
    const raw = readParam(key);
    if (raw == null) return defaultValue;
    if (opts?.allowed && !opts.allowed.includes(raw as T)) return defaultValue;
    return raw as T;
  });

  const set = useCallback(
    (next: T) => {
      setValue(next);
      // Keep the URL clean: the default is implied by its absence.
      writeParam(key, next === defaultValue ? null : next);
    },
    [key, defaultValue],
  );

  return [value, set];
}
