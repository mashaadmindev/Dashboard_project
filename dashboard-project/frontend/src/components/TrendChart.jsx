import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export default function TrendChart({ trend }) {
  if (!trend) {
    return (
      <div className="empty-state">
        No date column detected in this dataset, so no time trend is available.
      </div>
    );
  }

  return (
    <div>
      <p className="upload-hint" style={{ marginBottom: 14 }}>
        {trend.value_column.replace(/_/g, " ")} over {trend.date_column.replace(/_/g, " ")}
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={trend.points} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis dataKey="period" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "var(--muted)" }} stroke="var(--muted)" />
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
          <Line type="monotone" dataKey="value" stroke="var(--teal)" strokeWidth={2.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
