// Shared across the Team Wise page so the "By Team" table and the charts
// below it always agree on which color means what.

// Every category keeps the same color everywhere it appears.
export const METRIC_COLORS = {
  arrival: "#1f8a8a",
  disposal: "#e0607a",
  budget: "#3b5bdb",
  niv_sheet_arrival: "#f2a341",
  to_be_disposed: "#7c4dff",
  niv_sheet_disposal: "#7c4dff",
  maximo_budget: "#22a06b",
};

// Each team gets its own accent color, cycling through this palette in the
// same order everywhere (see colorForTeam).
export const TEAM_ACCENT_COLORS = [
  "#1f8a8a", "#e0607a", "#3b5bdb", "#f2a341", "#7c4dff", "#22a06b", "#0e9594", "#e8590c",
];

// `teamOrder` must be the same canonical list everywhere (the alphabetically
// sorted `teams` array from /api/team-wise-summary), so a given team always
// lands on the same color regardless of which chart or table renders it.
export function colorForTeam(team, teamOrder) {
  const idx = teamOrder.indexOf(team);
  return TEAM_ACCENT_COLORS[(idx >= 0 ? idx : 0) % TEAM_ACCENT_COLORS.length];
}
