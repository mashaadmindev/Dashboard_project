import { useEffect, useState } from "react";
import { fetchDashboardKpis } from "../api";

export default function DashboardKpiRow({ hasArrival, hasDisposal, globalFilters, refreshKey }) {
  const [arrival, setArrival] = useState(null);
  const [disposal, setDisposal] = useState(null);

  useEffect(() => {
    if (hasArrival) fetchDashboardKpis("arrival", globalFilters).then((res) => setArrival(res.data));
  }, [hasArrival, globalFilters, refreshKey]);

  useEffect(() => {
    if (hasDisposal) fetchDashboardKpis("disposal", globalFilters).then((res) => setDisposal(res.data));
  }, [hasDisposal, globalFilters, refreshKey]);

  if (!hasArrival && !hasDisposal) return null;

  const tiles = [
    hasArrival && arrival && {
      key: "total-arrivals",
      icon: "🚚",
      accent: "#6366f1",
      label: "Total Arrivals",
      value: arrival.total,
      sub: "Vehicles received",
    },
    hasDisposal && disposal && {
      key: "total-disposals",
      icon: "♻️",
      accent: "#06b6d4",
      label: "Total Disposals",
      value: disposal.total,
      sub: "Decommissioned vehicles",
    },
    hasArrival && arrival && {
      key: "arrivals-this-month",
      icon: "📅",
      accent: "#8b5cf6",
      label: "Arrivals This Month",
      value: arrival.this_month,
      sub: "Current month intakes",
    },
    hasDisposal && disposal && {
      key: "disposals-this-month",
      icon: "🗓️",
      accent: "#eab308",
      label: "Disposals This Month",
      value: disposal.this_month,
      sub: "Current month actions",
    },
    hasArrival && arrival && arrival.status_label && {
      key: "pending-arrivals",
      icon: "⏳",
      accent: "#ef4444",
      label: arrival.status_label,
      value: arrival.status_count,
      sub: "Awaiting arrival date",
    },
    hasDisposal && disposal && disposal.status_label && {
      key: "completed-disposals",
      icon: "✅",
      accent: "#22c55e",
      label: disposal.status_label,
      value: disposal.status_count,
      sub: "Fully processed VDRs",
    },
  ].filter(Boolean);

  return (
    <div className="kpi-strip">
      {tiles.map((t) => (
        <div className="kpi-tile" key={t.key} style={{ borderTopColor: t.accent }}>
          <div className="kpi-tile-header">
            <span className="kpi-tile-label">{t.label}</span>
            <span className="kpi-tile-icon" style={{ background: `${t.accent}1a`, color: t.accent }}>
              {t.icon}
            </span>
          </div>
          <div className="kpi-tile-value" style={{ color: t.accent }}>{t.value}</div>
          <div className="kpi-tile-sub">{t.sub}</div>
        </div>
      ))}
    </div>
  );
}
