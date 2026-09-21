import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from "recharts";
import { fetchChartData } from "../api";

const COLORS = ["#1f8a8a", "#e0607a", "#3b5bdb", "#f2a341", "#7c4dff", "#22a06b", "#6b7280", "#e8590c"];

export default function TeamPieChart({ table, columns, filters, refreshKey }) {
  const categoricalCols = columns.filter((c) => c.dtype === "str" || c.dtype === "object");
  const groupBy = categoricalCols.find((c) => c.name === "team")?.name ?? categoricalCols[0]?.name ?? "";

  const [data, setData] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!groupBy) return;
    fetchChartData(table, groupBy, undefined, "count", filters)
      .then((res) => {
        setData(res.data.data);
        setError(null);
      })
      .catch((err) => setError(err?.response?.data?.detail ?? "Could not load chart data"));
  }, [table, groupBy, filters, refreshKey]);

  if (categoricalCols.length === 0) {
    return <div className="empty-state">No categorical column available to break this down by.</div>;
  }

  const total = data.reduce((sum, d) => sum + d.y, 0);

  return (
    <div>
      {error && <div className="upload-error">{error}</div>}

      {!error && data.length === 0 && (
        <div className="empty-state">No data for the selected filters.</div>
      )}

      {!error && data.length > 0 && (
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={data}
              dataKey="y"
              nameKey="x"
              cx="50%"
              cy="50%"
              outerRadius={105}
              label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              labelLine={false}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
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
              formatter={(value) => [`${value} (${((value / total) * 100).toFixed(1)}%)`, "count"]}
            />
            <Legend wrapperStyle={{ fontSize: 12, fontFamily: "IBM Plex Mono" }} />
          </PieChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
