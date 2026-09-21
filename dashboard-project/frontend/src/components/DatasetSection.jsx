import { useEffect, useState } from "react";
import { fetchKpis } from "../api";
import TeamPieChart from "./TeamPieChart";
import TrendChart from "./TrendChart";
import ChartBuilder from "./ChartBuilder";

// A self-contained dashboard block for one dataset. Filters come entirely
// from the app-wide UniversalFilterBar (globalFilters) — no local filter
// bar here, so Year/Month/Team/Region/VCI all apply the same way everywhere.
export default function DatasetSection({ table, label, meta, refreshKey, globalFilters }) {
  const [kpis, setKpis] = useState(null);

  useEffect(() => {
    setKpis(null);
    fetchKpis(table, globalFilters).then((res) => setKpis(res.data));
  }, [table, globalFilters, refreshKey]);

  return (
    <div className="dataset-section">
      <h2 className="dataset-section-title">{label}</h2>

      <div className="section">
        <p className="section-title">Breakdown by team</p>
        <TeamPieChart table={table} columns={meta.columns} filters={globalFilters} refreshKey={refreshKey} />
      </div>

      <div className="section">
        <p className="section-title">Trend</p>
        <TrendChart trend={kpis?.trend} />
      </div>

      <div className="section">
        <p className="section-title">Ad-hoc breakdown</p>
        <ChartBuilder
          table={table}
          columns={meta.columns}
          rowCount={meta.row_count}
          filters={globalFilters}
          refreshKey={refreshKey}
        />
      </div>
    </div>
  );
}
