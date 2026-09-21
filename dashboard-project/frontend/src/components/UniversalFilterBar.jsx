import { useEffect, useState } from "react";
import { fetchTables, fetchFilterOptions } from "../api";
import ChecklistDropdown from "./ChecklistDropdown";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export const EMPTY_GLOBAL_FILTERS = { year: [], month: [], filters: {} };

// Merges each dataset's /api/filters response into one option set
function mergeFilterOptions(resultsByTable) {
  const years = new Set();
  const months = new Set();
  const categoricalMap = new Map();
  const numericSet = new Set();

  resultsByTable.forEach((res) => {
    if (!res || !res.data) return;
    (res.data.years || []).forEach((y) => years.add(y));
    (res.data.months || []).forEach((m) => months.add(m));
    (res.data.categorical_filters || []).forEach((f) => {
      if (!categoricalMap.has(f.column)) categoricalMap.set(f.column, new Set());
      (f.values || []).forEach((v) => categoricalMap.get(f.column).add(v));
    });
    (res.data.numeric_filters || []).forEach((f) => numericSet.add(f.column));
  });

  return {
    years: [...years].sort((a, b) => a - b),
    months: [...months].sort((a, b) => a - b),
    categorical_filters: [...categoricalMap.entries()].map(([column, values]) => ({
      column,
      values: [...values].sort(),
    })),
    numeric_filters: [...numericSet].map((column) => ({ column })),
  };
}

export default function UniversalFilterBar({ value, onChange, alwaysOpen = false }) {
  const [options, setOptions] = useState(null);
  const [draft, setDraft] = useState(value || EMPTY_GLOBAL_FILTERS);
  const [open, setOpen] = useState(alwaysOpen);

  useEffect(() => {
    fetchTables()
      .then((res) => {
        const tableList = (res.data || []).map((t) => t.table_name);
        const allTargets = Array.from(
          new Set([
            ...tableList,
            "arrival",
            "disposal",
            "niv_sheet_arrival",
            "niv_sheet_disposal",
            "to_be_disposed",
            "budget",
            "maximo_budget",
          ])
        );
        return Promise.all(
          allTargets.map((tbl) => fetchFilterOptions(tbl).catch(() => null))
        );
      })
      .catch(() => {
        return Promise.all([
          fetchFilterOptions("arrival").catch(() => null),
          fetchFilterOptions("disposal").catch(() => null),
          fetchFilterOptions("niv_sheet_arrival").catch(() => null),
          fetchFilterOptions("niv_sheet_disposal").catch(() => null),
          fetchFilterOptions("to_be_disposed").catch(() => null),
        ]);
      })
      .then((results) => {
        const merged = mergeFilterOptions(results || []);
        setOptions(merged);
      });
  }, []);

  useEffect(() => {
    setDraft(value || EMPTY_GLOBAL_FILTERS);
  }, [value]);

  if (!options) return null;

  const setFilterValue = (col, vals) => {
    setDraft((d) => {
      const filters = { ...(d.filters || {}) };
      if (Array.isArray(vals)) {
        if (vals.length > 0) filters[col] = vals;
        else delete filters[col];
      } else if (vals) {
        filters[col] = vals;
      } else {
        delete filters[col];
      }
      return { ...d, filters };
    });
  };

  // Helper to normalize selected values to arrays
  const toArray = (val) => {
    if (Array.isArray(val)) return val;
    if (val !== undefined && val !== null && val !== "") return [val];
    return [];
  };

  const isDirty = JSON.stringify(draft) !== JSON.stringify(value);
  const apply = () => onChange(draft);
  const reset = () => {
    setDraft(EMPTY_GLOBAL_FILTERS);
    onChange(EMPTY_GLOBAL_FILTERS);
  };

  // Count active applied filters
  const activeCount =
    toArray(draft.year).length +
    toArray(draft.month).length +
    Object.values(draft.filters || {}).reduce(
      (acc, v) => acc + (Array.isArray(v) ? (v.length > 0 ? 1 : 0) : v ? 1 : 0),
      0
    );

  const hasAnyFilters =
    options.years.length > 0 ||
    options.categorical_filters.length > 0 ||
    options.numeric_filters.length > 0;
  if (!hasAnyFilters) return null;

  // Applied (not just drafted) filter count, shown on the collapsed toggle.
  const appliedActiveCount =
    toArray(value?.year).length +
    toArray(value?.month).length +
    Object.values(value?.filters || {}).reduce(
      (acc, v) => acc + (Array.isArray(v) ? (v.length > 0 ? 1 : 0) : v ? 1 : 0),
      0
    );

  if (!alwaysOpen && !open) {
    return (
      <div className="filters-bar-collapsed">
        <button type="button" className="filters-toggle-btn" onClick={() => setOpen(true)}>
          <span>Filters</span>
          {appliedActiveCount > 0 && (
            <span className="filters-active-badge">{appliedActiveCount}</span>
          )}
        </button>
      </div>
    );
  }

  return (
    <div className="filters-bar">
      <div className="filters-header">
        <div className="filters-header-left">
          <span className="filters-title">Filters</span>
          {activeCount > 0 && (
            <span className="filters-active-badge">
              {activeCount} active filter{activeCount > 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="filters-header-right">
          <button className="btn-reset" onClick={reset}>
            Reset all filters
          </button>
          {!alwaysOpen && (
            <button type="button" className="filters-toggle-btn" onClick={() => setOpen(false)}>
              Hide Filters
            </button>
          )}
        </div>
      </div>

      <div className="filters-row">
        {options.years.length > 0 && (
          <ChecklistDropdown
            label="Year"
            options={options.years}
            selectedValues={toArray(draft.year)}
            onChange={(vals) => setDraft((d) => ({ ...d, year: vals }))}
            allLabel="All Years"
          />
        )}

        {options.months.length > 0 && (
          <ChecklistDropdown
            label="Month"
            options={options.months.map((m) => ({
              value: m,
              label: MONTH_NAMES[m - 1],
            }))}
            selectedValues={toArray(draft.month)}
            onChange={(vals) => setDraft((d) => ({ ...d, month: vals }))}
            allLabel="All Months"
          />
        )}

        {options.categorical_filters.map((f) => (
          <ChecklistDropdown
            key={f.column}
            label={f.column.replace(/_/g, " ")}
            options={f.values}
            selectedValues={toArray(draft.filters?.[f.column])}
            onChange={(vals) => setFilterValue(f.column, vals)}
            allLabel={`All ${f.column.replace(/_/g, " ")}`}
          />
        ))}

        {options.numeric_filters.map((f) => (
          <div className="filter-field" key={f.column}>
            <label>{f.column.toUpperCase()}</label>
            <input
              className="select"
              type="text"
              placeholder={`Enter ${f.column.toUpperCase()}`}
              value={draft.filters?.[f.column] ?? ""}
              onChange={(e) => setFilterValue(f.column, e.target.value)}
            />
          </div>
        ))}

        <div className="filters-actions">
          <button
            className={`btn filters-apply ${isDirty ? "btn-primary-glow" : ""}`}
            onClick={apply}
            disabled={!isDirty}
          >
            Apply Filters
          </button>
        </div>
      </div>
    </div>
  );
}
