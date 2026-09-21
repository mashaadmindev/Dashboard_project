import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { fetchChartData } from "../api";

const AGGS = ["count", "sum", "avg", "min", "max"];

// Columns like VIN, Tag, or a raw ID are unique per row and make useless
// group-by axes. Prefer columns with fewer distinct values relative to row
// count when picking a default.
function pickDefaultGroupCol(columns, rowCount) {
  const candidates = columns.filter((c) => (c.distinct_count ?? rowCount) < rowCount * 0.9);
  const pool = candidates.length > 0 ? candidates : columns;
  return pool.reduce((best, c) =>
    (c.distinct_count ?? Infinity) < (best.distinct_count ?? Infinity) ? c : best
  ).name;
}

export default function ChartBuilder({ table, columns, rowCount, filters, refreshKey }) {
  const numericCols = columns.filter((c) => c.dtype.includes("int") || c.dtype.includes("float"));
  const groupableCols = columns;

  const [x, setX] = useState("");
  const [y, setY] = useState(numericCols[0]?.name ?? "");
  const [agg, setAgg] = useState("count");
  const [data, setData] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    setX(pickDefaultGroupCol(groupableCols, rowCount));
    setY(numericCols[0]?.name ?? "");
    setAgg("count");
  }, [table]);

  useEffect(() => {
    if (!x) return;
    if (agg !== "count" && !y) return;
    fetchChartData(table, x, agg === "count" ? undefined : y, agg, filters)
      .then((res) => {
        setData(res.data.data);
        setError(null);
      })
      .catch((err) => setError(err?.response?.data?.detail ?? "Could not load chart data"));
  }, [table, x, y, agg, filters, refreshKey]);

  if (groupableCols.length === 0) {
    return <div className="empty-state">Not enough columns to build a chart for this dataset.</div>;
  }

  return (
    <div>
      <div className="chart-controls">
        <select className="select" value={x} onChange={(e) => setX(e.target.value)}>
          {groupableCols.map((c) => (
            <option key={c.name} value={c.name}>
              group by: {c.name.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select className="select" value={agg} onChange={(e) => setAgg(e.target.value)}>
          {AGGS.map((a) => (
            <option key={a} value={a}>
              {a === "count" ? "count of records" : a}
            </option>
          ))}
        </select>
        {agg !== "count" && (
          <select className="select" value={y} onChange={(e) => setY(e.target.value)}>
            {numericCols.map((c) => (
              <option key={c.name} value={c.name}>
                measure: {c.name.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && <div className="upload-error">{error}</div>}

      {!error && (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis
              dataKey="x"
              tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "var(--muted)" }}
              stroke="var(--muted)"
              interval={0}
              angle={-25}
              textAnchor="end"
              height={60}
            />
            <YAxis tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "var(--muted)" }} stroke="var(--muted)" />
            <Tooltip
              contentStyle={{
                fontFamily: "IBM Plex Mono",
                fontSize: 12,
                borderRadius: 8,
                border: "1px solid var(--line)",
                background: "var(--panel)",
                color: "var(--ink)",
              }}
              itemStyle={{ color: "var(--ink)" }}
              labelStyle={{ color: "var(--ink)", fontWeight: 700 }}
            />
            <Bar dataKey="y" fill="var(--teal)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
