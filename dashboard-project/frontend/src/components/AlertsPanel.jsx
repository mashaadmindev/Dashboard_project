import { useEffect, useState } from "react";
import { fetchTeamWiseSummary, fetchGlidepathSummaryComparison } from "../api";
import { colorForTeam } from "../colors";

export default function AlertsPanel({ globalFilters, refreshKey }) {
  const [summary, setSummary] = useState(null);
  const [gpComparison, setGpComparison] = useState(null);

  useEffect(() => {
    fetchTeamWiseSummary(globalFilters).then((res) => setSummary(res.data));
    fetchGlidepathSummaryComparison(globalFilters)
      .then((res) => setGpComparison(res.data))
      .catch(() => setGpComparison(null));
  }, [globalFilters, refreshKey]);

  if (!summary) return null;

  const teamOrder = summary.teams;
  const alerts = teamOrder.flatMap((team) => {
    const disposal = summary.data[team]?.disposal ?? 0;
    const budget = summary.data[team]?.budget;
    const maximoBudget = summary.data[team]?.maximo_budget;
    const toBeDisposed = summary.data[team]?.niv_sheet_disposal ?? summary.data[team]?.to_be_disposed ?? 0;

    const teamAlerts = [];
    if (toBeDisposed > disposal) {
      teamAlerts.push({
        key: `${team}-surplus-disposal`,
        team,
        message: "Dispose Additional count",
        detail: `Niv Sheet Disposal (${toBeDisposed}) is greater than Disposal (${disposal})`,
      });
    }
    if (budget != null && maximoBudget != null && budget > maximoBudget) {
      teamAlerts.push({
        key: `${team}-budget-exceed`,
        team,
        message: "Budget Exceed",
        detail: `Budget (${budget}) exceeds Maximo Budget (${maximoBudget})`,
      });
    }
    return teamAlerts;
  });

  return (
    <div className="section">
      <p className="section-title">Glide Path & Team Alerts</p>
      
      {gpComparison && (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "16px",
          marginBottom: "20px"
        }}>
          <div style={{
            background: "var(--panel)",
            borderRadius: "12px",
            padding: "16px 20px",
            border: "1px solid rgba(99, 102, 241, 0.3)",
            boxShadow: "var(--shadow-card)",
            borderLeft: "5px solid #6366f1"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "14px", fontWeight: "600", color: "var(--muted)" }}>Arrival vs GlidePath</span>
              <span style={{ fontSize: "20px" }}>🚚</span>
            </div>
            <div style={{ fontSize: "28px", fontWeight: "700", color: "#6366f1", margin: "6px 0" }}>
              {gpComparison.actual_arrival} <span style={{ fontSize: "14px", fontWeight: "500", color: "var(--muted)" }}>Niv Arrivals</span>
            </div>
            <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: "1.4" }}>
              GlidePath Adds (Arrival): <strong style={{ color: "var(--ink)" }}>{gpComparison.gp_arrival}</strong><br />
              Arrival Status: <strong style={{ color: "var(--ink)" }}>{gpComparison.surplus_arrival > 0 ? `+${gpComparison.surplus_arrival} Surplus Arrivals` : "On Track"}</strong>
            </div>
          </div>

          <div style={{
            background: "var(--panel)",
            borderRadius: "12px",
            padding: "16px 20px",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            boxShadow: "var(--shadow-card)",
            borderLeft: "5px solid #ef4444"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "14px", fontWeight: "600", color: "var(--muted)" }}>Disposal Alert</span>
              <span style={{ fontSize: "20px" }}>🚨</span>
            </div>
            <div style={{ fontSize: "28px", fontWeight: "700", color: "#ef4444", margin: "6px 0" }}>
              {gpComparison.disposal_alert_count} <span style={{ fontSize: "14px", fontWeight: "500", color: "var(--muted)" }}>vehicles to dispose</span>
            </div>
            <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: "1.4" }}>
              GlidePath: <strong style={{ color: "var(--ink)" }}>{gpComparison.gp_disposal}</strong> | Niv Disposed: <strong style={{ color: "var(--ink)" }}>{gpComparison.actual_disposal}</strong><br />
              Target: <strong style={{ color: "var(--ink)" }}>{gpComparison.target_disposal}</strong> (GP {gpComparison.gp_disposal} + Surplus {gpComparison.surplus_arrival})
            </div>
          </div>

          {gpComparison.maximo_budget != null && (
            <div style={{
              background: "var(--panel)",
              borderRadius: "12px",
              padding: "16px 20px",
              border: "1px solid rgba(245, 158, 11, 0.3)",
              boxShadow: "var(--shadow-card)",
              borderLeft: "5px solid #f59e0b"
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "14px", fontWeight: "600", color: "var(--muted)" }}>Maximo Budget Variance</span>
                <span style={{ fontSize: "20px" }}>📊</span>
              </div>
              <div style={{ fontSize: "28px", fontWeight: "700", color: gpComparison.maximo_variance > 0 ? "#f59e0b" : "#10b981", margin: "6px 0" }}>
                {gpComparison.maximo_budget} <span style={{ fontSize: "14px", fontWeight: "500", color: "var(--muted)" }}>Maximo Budget</span>
              </div>
              <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: "1.4" }}>
                GlidePath Budget: <strong style={{ color: "var(--ink)" }}>{gpComparison.gp_budget}</strong><br />
                Variance: <strong style={{ color: "var(--ink)" }}>{gpComparison.maximo_variance > 0 ? `${gpComparison.maximo_variance} vehicles over budget` : gpComparison.maximo_variance < 0 ? `${Math.abs(gpComparison.maximo_variance)} under budget` : "On budget"}</strong>
              </div>
            </div>
          )}
        </div>
      )}

      {alerts.length > 0 && (
        <div className="alerts-list">
          {alerts.map((a) => (
            <div className="alert-item" key={a.key}>
              <span className="alert-dot" />
              <div style={{ flex: 1 }}>
                <div className="alert-message">
                  {a.message}
                  <span className="alert-team-badge" style={{ background: colorForTeam(a.team, teamOrder) }}>
                    {a.team}
                  </span>
                </div>
                <div className="alert-detail">{a.detail}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

