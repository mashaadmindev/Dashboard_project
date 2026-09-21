import { METRIC_COLORS, TEAM_ACCENT_COLORS } from "../colors";

export default function TeamWiseByTeam({ summary }) {
  if (!summary) return null;

  if (summary.teams.length === 0) {
    return (
      <div className="section">
        <p className="section-title">By Team</p>
        <div className="empty-state">No team data available yet.</div>
      </div>
    );
  }

  return (
    <div className="section">
      <p className="section-title">By Team</p>
      <div className="team-table-wrap">
        <table className="team-table">
          <thead>
            <tr>
              <th>Team</th>
              {summary.metrics.map((m) => (
                <th key={m.table}>{m.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {summary.teams.map((team, i) => (
              <tr key={team}>
                <td className="team-table-name">
                  <span
                    className="team-dot"
                    style={{ background: TEAM_ACCENT_COLORS[i % TEAM_ACCENT_COLORS.length] }}
                  />
                  {team}
                </td>
                {summary.metrics.map((m) => {
                  const value = summary.data[team]?.[m.table] ?? (m.table === "niv_sheet_disposal" ? summary.data[team]?.["to_be_disposed"] : null);
                  const color = METRIC_COLORS[m.table] ?? "#6b7280";
                  return (
                    <td key={m.table}>
                      {value === null ? (
                        <span className="metric-badge metric-badge-empty">—</span>
                      ) : (
                        <span className="metric-badge" style={{ background: `${color}1a`, color }}>
                          {value}
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
