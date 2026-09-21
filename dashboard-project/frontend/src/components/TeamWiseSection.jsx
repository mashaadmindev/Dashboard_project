import { useEffect, useState } from "react";
import {
  BarChart, Bar, Cell, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { fetchChartData, fetchPeriodTrend } from "../api";
import { METRIC_COLORS, colorForTeam } from "../colors";

export default function TeamWiseSection({ table, label, teamOrder, globalFilters }) {
  const [teamData, setTeamData] = useState([]);
  const [teamError, setTeamError] = useState(null);
  const [period, setPeriod] = useState("month");
  const [trendPoints, setTrendPoints] = useState([]);
  const metricColor = METRIC_COLORS[table] ?? "#1f8a8a";

  useEffect(() => {
    fetchChartData(table, "team", undefined, "count", globalFilters)
      .then((res) => {
        setTeamData(res.data.data);
        setTeamError(null);
      })
      .catch((err) => setTeamError(err?.response?.data?.detail ?? "Could not load team breakdown"));
  }, [table, globalFilters]);

  useEffect(() => {
    fetchPeriodTrend(table, period, globalFilters).then((res) => setTrendPoints(res.data.points));
  }, [table, period, globalFilters]);

  return (
    <div className="section">
      <p className="section-title">{label} — Team Wise</p>

      <div className="teamwise-grid">
        <div>
          <p className="chart-subtitle">By team</p>
          {teamError && <div className="upload-error">{teamError}</div>}
          {!teamError && teamData.length === 0 && (
            <div className="empty-state">No team data available.</div>
          )}
          {!teamError && teamData.length > 0 && (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={teamData} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="x" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "var(--muted)" }} stroke="var(--muted)" />
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
                <Bar dataKey="y" radius={[4, 4, 0, 0]}>
                  {teamData.map((d) => (
                    <Cell key={d.x} fill={colorForTeam(d.x, teamOrder)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div>
          <div className="chart-controls" style={{ marginBottom: 8, alignItems: "center" }}>
            <p className="chart-subtitle" style={{ margin: 0, flex: 1 }}>Trend</p>
            <button
              className={`btn-toggle ${period === "month" ? "active" : ""}`}
              onClick={() => setPeriod("month")}
            >
              Monthly
            </button>
            <button
              className={`btn-toggle ${period === "year" ? "active" : ""}`}
              onClick={() => setPeriod("year")}
            >
              Yearly
            </button>
          </div>
          {trendPoints.length === 0 ? (
            <div className="empty-state">No date column detected for this dataset.</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={trendPoints} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
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
                <Line type="monotone" dataKey="count" stroke={metricColor} strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
