/**
 * DataTable (spec §7.2): a small generic, client-sortable table. Backs the
 * exposure/regime/benchmark/raw tables in later phases; here it renders the ETF
 * price-statistics rows. Each column carries its own cell renderer + sort
 * accessor, so the same component serves typed rows and (later) `TableModel`.
 */

import { useMemo, useState, type ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "right";
  /** Cell renderer; defaults to `String(row[key])`. */
  render?: (row: T) => ReactNode;
  /** Sort accessor; defaults to `row[key]`. `null` always sorts last. */
  sortValue?: (row: T) => number | string | null;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
}

type SortState = { key: string; dir: "asc" | "desc" };

/** Compare two non-null sort values: numerically when both numbers, else as text. */
function compareValues(a: number | string, b: number | string): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

export function DataTable<T>({ columns, rows }: DataTableProps<T>) {
  const [sort, setSort] = useState<SortState | null>(null);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const accessor =
      col.sortValue ??
      ((row: T) => (row as Record<string, unknown>)[col.key] as number | string | null);
    const factor = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = accessor(a);
      const bv = accessor(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1; // nulls last, regardless of direction
      if (bv == null) return -1;
      return compareValues(av, bv) * factor;
    });
  }, [rows, columns, sort]);

  function toggleSort(key: string) {
    setSort((prev) =>
      prev && prev.key === key ? { key, dir: prev.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" },
    );
  }

  if (rows.length === 0) {
    return <div style={{ padding: "1rem", color: "#777" }}>No rows.</div>;
  }

  return (
    <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.9rem" }}>
      <thead>
        <tr>
          {columns.map((col) => {
            const isSorted = sort?.key === col.key;
            const arrow = isSorted ? (sort?.dir === "asc" ? " ▲" : " ▼") : "";
            return (
              <th
                key={col.key}
                onClick={() => toggleSort(col.key)}
                style={{
                  textAlign: col.align ?? "left",
                  borderBottom: "2px solid #e5e5e5",
                  padding: "0.4rem 0.6rem",
                  cursor: "pointer",
                  userSelect: "none",
                  whiteSpace: "nowrap",
                }}
              >
                {col.header}
                {arrow}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {sortedRows.map((row, rowIndex) => (
          <tr key={rowIndex} style={{ borderBottom: "1px solid #f0f0f0" }}>
            {columns.map((col) => (
              <td
                key={col.key}
                style={{
                  textAlign: col.align ?? "left",
                  padding: "0.35rem 0.6rem",
                  fontVariantNumeric: "tabular-nums",
                  fontFamily: "var(--font-data)", // Play for table body (headers excluded)
                }}
              >
                {col.render ? col.render(row) : String((row as Record<string, unknown>)[col.key] ?? "")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
