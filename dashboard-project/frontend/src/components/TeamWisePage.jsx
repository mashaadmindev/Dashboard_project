import { useEffect, useState } from "react";
import TeamWiseSection from "./TeamWiseSection";
import TeamWiseByTeam from "./TeamWiseByTeam";
import { fetchTeamWiseSummary, fetchMaximoBudget } from "../api";

const METRICS = [
  { label: "Arrivals", table: "arrival" },
  { label: "Disposal", table: "disposal" },
  { label: "Budget", table: "budget" },
  { label: "Niv Sheet Arrival", table: "niv_sheet_arrival" },
  { label: "Niv Sheet Disposal", table: "niv_sheet_disposal" },
  { label: "Maximo_Budget", table: "maximo_budget" },
];

export default function TeamWisePage({ tables, refreshKey, globalFilters }) {
  const [summary, setSummary] = useState(null);
  // Fetched independently of summary — a slow/unreachable Maximo API should
  // never delay the rest of Team Wise, which is fast and DB-only.
  const [maximo, setMaximo] = useState({ loading: true, value: null, error: null });

  useEffect(() => {
    fetchTeamWiseSummary(globalFilters).then((res) => setSummary(res.data));
  }, [refreshKey, globalFilters]);

  useEffect(() => {
    setMaximo({ loading: true, value: null, error: null });
    fetchMaximoBudget(globalFilters).then((res) =>
      setMaximo({
        loading: false,
        value: res.data.maximo_budget,
        error: res.data.maximo_error,
      })
    );
  }, [refreshKey, globalFilters]);

  const hasArrival = tables.some((t) => t.table_name === "arrival" || t.table_name === "niv_sheet_arrival");
  const arrivalTable = tables.find((t) => t.table_name === "niv_sheet_arrival") ? "niv_sheet_arrival" : "arrival";

  const hasDisposal = tables.some((t) => t.table_name === "disposal" || t.table_name === "to_be_disposed" || t.table_name === "niv_sheet_disposal");
  const disposalTable = tables.find((t) => t.table_name === "niv_sheet_disposal")
    ? "niv_sheet_disposal"
    : (tables.find((t) => t.table_name === "to_be_disposed") ? "to_be_disposed" : "disposal");

  const teamOrder = summary?.teams ?? [];

  return (
    <>
      <div className="kpi-strip">
        {METRICS.map((m) => {
          if (m.table === "maximo_budget") {
            const hasData = maximo.value !== null && maximo.value !== undefined;
            return (
              <div className="kpi-card" key={m.table}>
                <div className="kpi-label">{m.label}</div>
                <div className="kpi-value">
                  {maximo.loading ? "…" : hasData ? maximo.value : "—"}
                </div>
                {!maximo.loading && !hasData && (
                  <div className="kpi-subrow">{maximo.error ?? "No data available"}</div>
                )}
              </div>
            );
          }

          const value = summary
            ? (summary.category_totals[m.table] ?? (m.table === "niv_sheet_disposal" ? summary.category_totals["to_be_disposed"] : null))
            : null;
          const hasData = value !== null && value !== undefined;
          return (
            <div className="kpi-card" key={m.table}>
              <div className="kpi-label">{m.label}</div>
              <div className="kpi-value">{hasData ? value : "—"}</div>
              {!hasData && <div className="kpi-subrow">No data available</div>}
            </div>
          );
        })}
      </div>

      <TeamWiseByTeam summary={summary} />

      {hasArrival ? (
        <TeamWiseSection table={arrivalTable} label="Niv Sheet Arrival" teamOrder={teamOrder} globalFilters={globalFilters} />
      ) : (
        <div className="section">
          <p className="section-title">Niv Sheet Arrival — Team Wise</p>
          <div className="empty-state">No arrival data uploaded yet.</div>
        </div>
      )}

      {hasDisposal ? (
        <TeamWiseSection table={disposalTable} label="Niv Sheet Disposal" teamOrder={teamOrder} globalFilters={globalFilters} />
      ) : (
        <div className="section">
          <p className="section-title">Niv Sheet Disposal — Team Wise</p>
          <div className="empty-state">No disposal data uploaded yet.</div>
        </div>
      )}
    </>
  );
}

