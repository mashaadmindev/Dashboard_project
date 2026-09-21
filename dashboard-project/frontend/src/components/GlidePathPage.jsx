import { useEffect, useState, useMemo } from "react";
import {
  fetchGlidepathDepartments,
  fetchGlidepathYears,
  fetchGlidepath,
  saveGlidepath,
} from "../api";
import GaugeChart from "./GaugeChart";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

export default function GlidePathPage() {
  const [departments, setDepartments] = useState([]);
  const [selectedDeptNo, setSelectedDeptNo] = useState("018285");
  const [years, setYears] = useState([2026]);
  const [selectedYear, setSelectedYear] = useState(2026);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Edit mode for all fields
  const [isEditing, setIsEditing] = useState(false);
  const [editDept, setEditDept] = useState({});
  const [editBudget, setEditBudget] = useState({});
  const [editMonths, setEditMonths] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState(null);

  // Load department options
  useEffect(() => {
    fetchGlidepathDepartments()
      .then((res) => {
        const depts = res.data || [];
        setDepartments(depts);
        if (depts.length > 0 && !depts.some((d) => d.department_no === selectedDeptNo)) {
          setSelectedDeptNo(depts[0].department_no);
        }
      })
      .catch((err) => {
        console.error("Failed to load departments:", err);
      });
  }, []);

  // Load years for chosen department
  useEffect(() => {
    if (!selectedDeptNo) return;
    fetchGlidepathYears(selectedDeptNo)
      .then((res) => {
        const yrList = res.data || [2026];
        setYears(yrList);
        if (!yrList.includes(selectedYear)) {
          setSelectedYear(yrList[0] || 2026);
        }
      })
      .catch((err) => {
        console.error("Failed to load years:", err);
      });
  }, [selectedDeptNo]);

  const initEditStates = (d) => {
    if (!d) return;
    setEditDept({
      activity: d.department?.activity || "",
      manager: d.department?.manager || "",
      coordinator: d.department?.coordinator || "",
      chief_engineer: d.department?.chief_engineer || "",
      director_ll2: d.department?.director_ll2 || "",
      finance_approver: d.department?.finance_approver || "",
      finance_cost_center: d.department?.finance_cost_center || "",
    });
    setEditBudget({
      budget_year: d.budget?.budget_year || (selectedYear - 1),
      budget_amount: d.budget?.budget_amount || 0,
      actual_amount: d.budget?.actual_amount || 0,
      december_budget: d.budget?.december_budget || 0,
      reduction_percent: d.budget?.reduction_percent ?? 0,
    });
    setEditMonths(
      (d.monthly || []).map((m) => ({
        requirement_month: m.requirement_month,
        month_name: m.month_name,
        build_count: m.build_count,
        production_count: m.production_count,
        disposal_count: m.disposal_count,
      }))
    );
  };

  // Load glidepath data
  const loadGlidepath = () => {
    if (!selectedDeptNo) return;
    setLoading(true);
    setError(null);
    fetchGlidepath(selectedDeptNo, selectedYear)
      .then((res) => {
        setData(res.data);
        initEditStates(res.data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load glidepath data:", err);
        setError("Failed to load Glide Path data for this department.");
        setLoading(false);
      });
  };

  useEffect(() => {
    loadGlidepath();
    setIsEditing(false);
    setSaveMessage(null);
  }, [selectedDeptNo, selectedYear]);

  // Calculate live edited data if user is modifying counts
  const liveCalculatedMonthly = useMemo(() => {
    if (!data) return [];
    const actualStarting = isEditing
      ? (Number(editBudget.actual_amount) || 0)
      : (data.budget?.actual_amount ?? 0);
    let running = actualStarting;

    const sourceMonths = isEditing ? editMonths : (data.monthly || []);

    return sourceMonths.map((m) => {
      const b = Number(m.build_count) || 0;
      const p = Number(m.production_count) || 0;
      const d = Number(m.disposal_count) || 0;
      const adds = b + p;
      running = running + adds - d;

      return {
        ...m,
        build_count: b,
        production_count: p,
        total_adds: adds,
        disposal_count: d,
        total_monthly_count: running,
      };
    });
  }, [data, isEditing, editMonths, editBudget.actual_amount]);

  // Totals for the table footer
  const liveTotals = useMemo(() => {
    const startCount = isEditing
      ? (Number(editBudget.actual_amount) || 0)
      : (data?.budget?.actual_amount ?? 0);

    if (!data || liveCalculatedMonthly.length === 0) {
      return {
        build: 0,
        prod: 0,
        adds: 0,
        disposals: 0,
        startCount,
        endCount: startCount,
      };
    }
    const bTotal = liveCalculatedMonthly.reduce((s, m) => s + m.build_count, 0);
    const pTotal = liveCalculatedMonthly.reduce((s, m) => s + m.production_count, 0);
    const aTotal = liveCalculatedMonthly.reduce((s, m) => s + m.total_adds, 0);
    const dTotal = liveCalculatedMonthly.reduce((s, m) => s + m.disposal_count, 0);
    const endCount = liveCalculatedMonthly[liveCalculatedMonthly.length - 1].total_monthly_count;

    return {
      build: bTotal,
      prod: pTotal,
      adds: aTotal,
      disposals: dTotal,
      startCount,
      endCount,
    };
  }, [data, liveCalculatedMonthly, isEditing, editBudget.actual_amount]);

  // Row representing "now": current calendar month if we're viewing the current
  // year, otherwise the year's final (December) row.
  const currentMonthRow = useMemo(() => {
    if (liveCalculatedMonthly.length === 0) return null;
    const now = new Date();
    if (selectedYear === now.getFullYear()) {
      const nowMonth = now.getMonth() + 1;
      const match = liveCalculatedMonthly.find((m) => {
        const parsed = new Date(m.requirement_month);
        return !isNaN(parsed) && parsed.getUTCMonth() + 1 === nowMonth;
      });
      if (match) return match;
    }
    return liveCalculatedMonthly[liveCalculatedMonthly.length - 1];
  }, [liveCalculatedMonthly, selectedYear]);

  const nextMonthRow = useMemo(() => {
    if (!currentMonthRow) return null;
    const idx = liveCalculatedMonthly.indexOf(currentMonthRow);
    return idx >= 0 ? liveCalculatedMonthly[idx + 1] ?? null : null;
  }, [liveCalculatedMonthly, currentMonthRow]);

  const handleDeptChange = (field, value) => {
    setEditDept((prev) => ({ ...prev, [field]: value }));
  };

  const handleBudgetChange = (field, value) => {
    const num = parseFloat(value) || 0;
    setEditBudget((prev) => {
      const updated = { ...prev, [field]: num };
      // If user adjusts budget amount or reduction %, suggest calculated December budget if not customized
      if (field === "budget_amount" || field === "reduction_percent") {
        const bAmt = field === "budget_amount" ? num : (prev.budget_amount || 0);
        const rPct = field === "reduction_percent" ? num : (prev.reduction_percent ?? 0);
        updated.december_budget = Math.round(bAmt * (1 - rPct / 100));
      }
      return updated;
    });
  };

  const handleEditChange = (index, field, value) => {
    const num = Math.max(0, parseInt(value, 10) || 0);
    setEditMonths((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: num };
      return copy;
    });
  };

  const handleSave = () => {
    setSaving(true);
    setSaveMessage(null);
    saveGlidepath({
      department_no: selectedDeptNo,
      year: selectedYear,
      department: editDept,
      budget: editBudget,
      months: editMonths,
    })
      .then(() => {
        setSaving(false);
        setIsEditing(false);
        setSaveMessage({ type: "success", text: "All Glide Path fields saved successfully." });
        loadGlidepath();
      })
      .catch((err) => {
        console.error("Save error:", err);
        setSaving(false);
        setSaveMessage({ type: "error", text: "Failed to save Glide Path changes." });
      });
  };

  const handleCancel = () => {
    setIsEditing(false);
    initEditStates(data);
  };

  if (loading && !data) {
    return (
      <div className="section">
        <div className="empty-state">Loading Glide Path data...</div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="section">
        <div className="empty-state">{error}</div>
      </div>
    );
  }

  const dept = data?.department || {};
  const budget = data?.budget || {};
  const capAmount = isEditing
    ? Number(editBudget.budget_amount) || 0
    : budget.budget_amount ?? 0;
  const currentCount = currentMonthRow?.total_monthly_count ?? liveTotals.endCount;
  const capUsedPct = capAmount > 0 ? (currentCount / capAmount) * 100 : 0;
  const currentDecBudget = isEditing
    ? (Number(editBudget.december_budget) || 0)
    : (budget.december_budget ?? 0);
  const targetMet =
    currentDecBudget > 0 && Math.abs(liveTotals.endCount - currentDecBudget) < 0.01;

  const cleanDeptNo = String(dept.department_no || selectedDeptNo).replace(/^dept\s*/i, "").trim();

  return (
    <div className="glidepath-page">
      {/* Top Controls Bar */}
      <div className="glidepath-header-bar">
        <div className="glidepath-title-group">
          <div>
            <div className="glidepath-title-row">
              <h1 className="page-title" style={{ margin: 0 }}>Glide Path</h1>
              <span className="glidepath-badge-dept font-mono">
                #{cleanDeptNo}
              </span>
            </div>
            <p className="page-subtitle" style={{ margin: "4px 0 0", fontSize: "13px" }}>
              Department fleet governance, budget reduction tracking & 12-month trajectory
            </p>
          </div>
        </div>

        <div className="glidepath-controls">
          <div className="filter-group">
            <label className="filter-label">Department</label>
            <div className="gp-select-wrapper">
              <select
                className="filter-select font-mono"
                value={selectedDeptNo}
                onChange={(e) => setSelectedDeptNo(e.target.value)}
                disabled={isEditing}
              >
                {departments.map((d) => {
                  const numOnly = String(d.department_no).replace(/^dept\s*/i, "").trim();
                  return (
                    <option key={d.department_no} value={d.department_no}>
                      {numOnly}
                    </option>
                  );
                })}
              </select>
            </div>
          </div>

          <div className="filter-group">
            <label className="filter-label">Glide Path Year</label>
            <div className="gp-select-wrapper">
              <select
                className="filter-select font-mono"
                value={selectedYear}
                onChange={(e) => setSelectedYear(parseInt(e.target.value, 10))}
                disabled={isEditing}
              >
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="filter-group" style={{ alignSelf: "flex-end" }}>
            {!isEditing ? (
              <button
                className="btn-action btn-secondary gp-btn-edit"
                onClick={() => {
                  initEditStates(data);
                  setIsEditing(true);
                }}
                title="Edit all fields in governance, budget, and monthly plan"
              >
                <span>✏️</span>
                <span>Edit All Fields</span>
              </button>
            ) : (
              <div style={{ display: "flex", gap: "8px" }}>
                <button
                  className="btn-action btn-primary gp-btn-save"
                  onClick={handleSave}
                  disabled={saving}
                >
                  <span>{saving ? "⏳" : "💾"}</span>
                  <span>{saving ? "Saving..." : "Save All Changes"}</span>
                </button>
                <button
                  className="btn-action btn-secondary gp-btn-cancel"
                  onClick={handleCancel}
                  disabled={saving}
                >
                  <span>Cancel</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {saveMessage && (
        <div
          className={`gp-alert ${
            saveMessage.type === "success" ? "gp-alert-success" : "gp-alert-error"
          }`}
        >
          {saveMessage.text}
        </div>
      )}

      {/* Top Card: Department Details */}
      <div className="gp-card gp-dept-details-card">
        <div className="gp-card-header">
          <div className="gp-card-title">Department Details & Governance</div>
          {isEditing ? (
            <span className="gp-editing-badge">✏️ Editing Governance</span>
          ) : (
            <span className="gp-tag">Cost Center: {dept.finance_cost_center}</span>
          )}
        </div>

        <div className="gp-details-grid">
          <div className="gp-detail-item">
            <span className="gp-detail-label">Department No.</span>
            <span className="gp-detail-val font-mono">{dept.department_no}</span>
          </div>

          <div className="gp-detail-item">
            <span className="gp-detail-label">Activity</span>
            {isEditing ? (
              <input
                type="text"
                className="gp-input-text"
                value={editDept.activity ?? ""}
                onChange={(e) => handleDeptChange("activity", e.target.value)}
                placeholder="Activity"
              />
            ) : (
              <span className="gp-detail-val">{dept.activity}</span>
            )}
          </div>

          <div className="gp-detail-item">
            <span className="gp-detail-label">Manager</span>
            {isEditing ? (
              <input
                type="text"
                className="gp-input-text"
                value={editDept.manager ?? ""}
                onChange={(e) => handleDeptChange("manager", e.target.value)}
                placeholder="Manager"
              />
            ) : (
              <span className="gp-detail-val">{dept.manager}</span>
            )}
          </div>

          <div className="gp-detail-item">
            <span className="gp-detail-label">Coordinator</span>
            {isEditing ? (
              <input
                type="text"
                className="gp-input-text"
                value={editDept.coordinator ?? ""}
                onChange={(e) => handleDeptChange("coordinator", e.target.value)}
                placeholder="Coordinator"
              />
            ) : (
              <span className="gp-detail-val">{dept.coordinator}</span>
            )}
          </div>

          <div className="gp-detail-item">
            <span className="gp-detail-label">Chief Engineer</span>
            {isEditing ? (
              <input
                type="text"
                className="gp-input-text"
                value={editDept.chief_engineer ?? ""}
                onChange={(e) => handleDeptChange("chief_engineer", e.target.value)}
                placeholder="Chief Engineer"
              />
            ) : (
              <span className="gp-detail-val">{dept.chief_engineer}</span>
            )}
          </div>

          <div className="gp-detail-item">
            <span className="gp-detail-label">Director LL2</span>
            {isEditing ? (
              <input
                type="text"
                className="gp-input-text"
                value={editDept.director_ll2 ?? ""}
                onChange={(e) => handleDeptChange("director_ll2", e.target.value)}
                placeholder="Director LL2"
              />
            ) : (
              <span className="gp-detail-val">{dept.director_ll2}</span>
            )}
          </div>

          <div className="gp-detail-item">
            <span className="gp-detail-label">Finance Approver</span>
            {isEditing ? (
              <input
                type="text"
                className="gp-input-text"
                value={editDept.finance_approver ?? ""}
                onChange={(e) => handleDeptChange("finance_approver", e.target.value)}
                placeholder="Finance Approver"
              />
            ) : (
              <span className="gp-detail-val">{dept.finance_approver}</span>
            )}
          </div>

          <div className="gp-detail-item">
            <span className="gp-detail-label">Finance Cost Center</span>
            {isEditing ? (
              <input
                type="text"
                className="gp-input-text font-mono"
                value={editDept.finance_cost_center ?? ""}
                onChange={(e) => handleDeptChange("finance_cost_center", e.target.value)}
                placeholder="e.g. 018285 / 63044030"
              />
            ) : (
              <span className="gp-detail-val font-mono">{dept.finance_cost_center}</span>
            )}
          </div>
        </div>
      </div>

      {/* Budget Cap Utilization Gauge */}
      <div className="gp-card">
        <div className="gp-card-header">
          <div>
            <div className="gp-card-title">% of Annual Budget Cap Used</div>
            <div className="gp-card-sub">
              {currentMonthRow?.month_name ?? "Current"} {selectedYear} fleet count against the authorized budget cap
            </div>
          </div>
        </div>
        <div className="gp-gauge-row">
          <GaugeChart value={capUsedPct} sublabel="of Annual Budget Cap Used" />
          <div className="gp-gauge-stats-grid">
            <div className="kpi-card">
              <div className="kpi-label">Budget Cap</div>
              <div className="kpi-value font-mono">{capAmount || "—"}</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Current Count</div>
              <div className="kpi-value font-mono">{currentCount}</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Planned Additions Next Month</div>
              <div className="kpi-value font-mono">{nextMonthRow?.total_adds ?? "—"}</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Planned Disposals Next Month</div>
              <div className="kpi-value font-mono">{nextMonthRow?.disposal_count ?? "—"}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Middle Stat Strip: Budget & Year End Status */}
      <div className="gp-budget-strip">
        <div className="kpi-card">
          <div className="kpi-label">{editBudget.budget_year ?? (selectedYear - 1)} Authorized Budget</div>
          {isEditing ? (
            <input
              type="number"
              className="gp-input-kpi font-mono"
              value={editBudget.budget_amount ?? ""}
              onChange={(e) => handleBudgetChange("budget_amount", e.target.value)}
              placeholder="Budget"
            />
          ) : (
            <div className="kpi-value font-mono">{budget.budget_amount ?? "—"}</div>
          )}
          <div className="kpi-subrow">Previous Year Authorized</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">{editBudget.budget_year ?? (selectedYear - 1)} Actual Starting</div>
          {isEditing ? (
            <input
              type="number"
              className="gp-input-kpi font-mono"
              value={editBudget.actual_amount ?? ""}
              onChange={(e) => handleBudgetChange("actual_amount", e.target.value)}
              placeholder="Starting Count"
            />
          ) : (
            <div className="kpi-value font-mono">{budget.actual_amount ?? "—"}</div>
          )}
          <div className="kpi-subrow">Base fleet count entering {selectedYear}</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">
            {editBudget.budget_year ?? (selectedYear - 1)} Dec Budget (-{isEditing ? editBudget.reduction_percent : (budget.reduction_percent ?? 0)}%)
          </div>
          {isEditing ? (
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <input
                type="number"
                className="gp-input-kpi font-mono"
                value={editBudget.december_budget ?? ""}
                onChange={(e) => handleBudgetChange("december_budget", e.target.value)}
                placeholder="Dec Target"
                style={{ color: "var(--teal)" }}
              />
              <span style={{ fontSize: "12px", color: "var(--muted)" }}>Red %:</span>
              <input
                type="number"
                className="gp-input-kpi font-mono"
                style={{ width: "60px" }}
                value={editBudget.reduction_percent ?? ""}
                onChange={(e) => handleBudgetChange("reduction_percent", e.target.value)}
                placeholder="%"
              />
            </div>
          ) : (
            <div className="kpi-value font-mono" style={{ color: "var(--teal)" }}>
              {budget.december_budget ?? "—"}
            </div>
          )}
          <div className="kpi-subrow">Mandated Glide Path target</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">{selectedYear} Dec Ending Count</div>
          <div
            className="kpi-value font-mono"
            style={{ color: targetMet ? "var(--teal)" : "var(--amber)" }}
          >
            {liveTotals.endCount}
          </div>
          <div className="kpi-subrow">
            {targetMet ? (
              <span style={{ color: "var(--teal)", fontWeight: 600 }}>✓ Target Exactly Met</span>
            ) : (
              <span style={{ color: "var(--amber)", fontWeight: 600 }}>
                {liveTotals.endCount > currentDecBudget
                  ? `+${liveTotals.endCount - currentDecBudget} over target`
                  : `${liveTotals.endCount - currentDecBudget} under target`}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Visual Chart: Glide Path Trajectory */}
      <div className="gp-card">
        <div className="gp-card-header">
          <div>
            <div className="gp-card-title">{selectedYear} Vehicle Glide Path Trajectory</div>
            <div className="gp-card-sub">
              Fleet Count running glide from {budget.actual_amount} down to target {budget.december_budget}
            </div>
          </div>
          <div className="gp-legend-pills">
            <span className="gp-pill-dot" style={{ background: "var(--teal)" }}>
              Fleet Total Count (Line)
            </span>
            <span className="gp-pill-dot" style={{ background: "#4a90e2" }}>
              Adds (Build + Prod)
            </span>
            <span className="gp-pill-dot" style={{ background: "var(--amber)" }}>
              Disposals
            </span>
          </div>
        </div>

        <div style={{ width: "100%", height: 320, marginTop: 16 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={liveCalculatedMonthly}
              margin={{ top: 10, right: 30, left: 10, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="month_name" stroke="var(--muted)" />
              <YAxis
                yAxisId="count"
                domain={["dataMin - 30", "dataMax + 20"]}
                stroke="var(--teal)"
                tickFormatter={(v) => Math.round(v)}
              />
              <YAxis
                yAxisId="bars"
                orientation="right"
                stroke="var(--muted)"
                domain={[0, "dataMax + 10"]}
              />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (active && payload && payload.length) {
                    const row = payload[0].payload;
                    return (
                      <div className="gp-chart-tooltip">
                        <div className="gp-tooltip-header">{label} {selectedYear}</div>
                        <div className="gp-tooltip-row">
                          <span>Build:</span>
                          <strong>{row.build_count}</strong>
                        </div>
                        <div className="gp-tooltip-row">
                          <span>Production:</span>
                          <strong>{row.production_count}</strong>
                        </div>
                        <div className="gp-tooltip-row">
                          <span style={{ color: "#4a90e2" }}>Total Adds:</span>
                          <strong>+{row.total_adds}</strong>
                        </div>
                        <div className="gp-tooltip-row">
                          <span style={{ color: "var(--amber)" }}>Disposals:</span>
                          <strong>-{row.disposal_count}</strong>
                        </div>
                        <div
                          className="gp-tooltip-row"
                          style={{
                            borderTop: "1px solid var(--line)",
                            paddingTop: 4,
                            marginTop: 4,
                          }}
                        >
                          <span style={{ color: "var(--teal)", fontWeight: 600 }}>
                            Running Fleet Count:
                          </span>
                          <strong style={{ fontSize: "14px", color: "var(--teal)" }}>
                            {row.total_monthly_count}
                          </strong>
                        </div>
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <Legend verticalAlign="top" height={36} />
              {budget.december_budget && (
                <ReferenceLine
                  yAxisId="count"
                  y={budget.december_budget}
                  label={{
                    value: `Dec Target: ${budget.december_budget}`,
                    position: "insideBottomRight",
                    fill: "var(--amber)",
                    fontSize: 12,
                    fontWeight: 600,
                  }}
                  stroke="var(--amber)"
                  strokeDasharray="4 4"
                />
              )}
              <Bar
                yAxisId="bars"
                dataKey="total_adds"
                name="Total Adds (Build+Prod)"
                fill="#4a90e2"
                barSize={16}
                radius={[4, 4, 0, 0]}
              />
              <Bar
                yAxisId="bars"
                dataKey="disposal_count"
                name="Disposals"
                fill="var(--amber)"
                barSize={16}
                radius={[4, 4, 0, 0]}
              />
              <Line
                yAxisId="count"
                type="monotone"
                dataKey="total_monthly_count"
                name="Total Monthly Count"
                stroke="var(--teal)"
                strokeWidth={3}
                dot={{ r: 5, fill: "var(--teal)", stroke: "#ffffff", strokeWidth: 2 }}
                activeDot={{ r: 7 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bottom Section: Excel Reproduction Matrix */}
      <div className="gp-card">
        <div className="gp-card-header">
          <div>
            <div className="gp-card-title">{selectedYear} Vehicle Glidepath Matrix</div>
            <div className="gp-card-sub">
              Complete spreadsheet view: monthly builds, additions, disposals & cumulative count
            </div>
          </div>
          {isEditing && (
            <span className="gp-editing-badge">
              ✏️ Live Edit Mode — Modify numbers below to simulate running trajectory
            </span>
          )}
        </div>

        <div className="gp-table-container">
          <table className="gp-matrix-table">
            <thead>
              <tr>
                <th className="gp-th-metric">Metric / Month</th>
                {liveCalculatedMonthly.map((m) => (
                  <th key={m.requirement_month} className="gp-th-month">
                    {m.month_name}
                  </th>
                ))}
                <th className="gp-th-total">Total / Dec End</th>
              </tr>
            </thead>
            <tbody>
              {/* Row 1: Build */}
              <tr>
                <td className="gp-td-label">Build</td>
                {liveCalculatedMonthly.map((m, idx) => (
                  <td key={`b-${idx}`} className="gp-td-num">
                    {isEditing ? (
                      <input
                        type="number"
                        min="0"
                        className="gp-input-num"
                        value={editMonths[idx]?.build_count ?? m.build_count}
                        onChange={(e) => handleEditChange(idx, "build_count", e.target.value)}
                      />
                    ) : (
                      m.build_count
                    )}
                  </td>
                ))}
                <td className="gp-td-total font-mono">{liveTotals.build}</td>
              </tr>

              {/* Row 2: Production */}
              <tr>
                <td className="gp-td-label">Prod.</td>
                {liveCalculatedMonthly.map((m, idx) => (
                  <td key={`p-${idx}`} className="gp-td-num">
                    {isEditing ? (
                      <input
                        type="number"
                        min="0"
                        className="gp-input-num"
                        value={editMonths[idx]?.production_count ?? m.production_count}
                        onChange={(e) =>
                          handleEditChange(idx, "production_count", e.target.value)
                        }
                      />
                    ) : (
                      m.production_count
                    )}
                  </td>
                ))}
                <td className="gp-td-total font-mono">{liveTotals.prod}</td>
              </tr>

              {/* Row 3: Total Adds */}
              <tr className="gp-row-highlight">
                <td className="gp-td-label font-bold">Total Adds</td>
                {liveCalculatedMonthly.map((m, idx) => (
                  <td key={`a-${idx}`} className="gp-td-num font-bold">
                    {m.total_adds}
                  </td>
                ))}
                <td className="gp-td-total font-mono font-bold">{liveTotals.adds}</td>
              </tr>

              {/* Row 4: Disposals */}
              <tr>
                <td className="gp-td-label" style={{ color: "var(--amber)" }}>
                  Disposals
                </td>
                {liveCalculatedMonthly.map((m, idx) => (
                  <td key={`d-${idx}`} className="gp-td-num" style={{ color: "var(--amber)" }}>
                    {isEditing ? (
                      <input
                        type="number"
                        min="0"
                        className="gp-input-num"
                        value={editMonths[idx]?.disposal_count ?? m.disposal_count}
                        onChange={(e) => handleEditChange(idx, "disposal_count", e.target.value)}
                      />
                    ) : (
                      m.disposal_count
                    )}
                  </td>
                ))}
                <td className="gp-td-total font-mono" style={{ color: "var(--amber)" }}>
                  {liveTotals.disposals}
                </td>
              </tr>

              {/* Row 5: Total Monthly Count */}
              <tr className="gp-row-total-count">
                <td className="gp-td-label font-bold" style={{ color: "var(--teal)" }}>
                  Total Monthly Count
                </td>
                {liveCalculatedMonthly.map((m, idx) => (
                  <td key={`tm-${idx}`} className="gp-td-num">
                    <span className="gp-count-pill font-mono">{m.total_monthly_count}</span>
                  </td>
                ))}
                <td className="gp-td-total">
                  <span
                    className="gp-count-pill font-mono"
                    style={{
                      background: targetMet ? "var(--teal)" : "var(--amber)",
                      color: "#ffffff",
                    }}
                  >
                    {liveTotals.endCount}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Calculation footnote matching Excel logic */}
        <div className="gp-table-footer-note">
          * <strong>Running Count Formula:</strong> Previous Month Count + Total Adds (Build + Production) - Disposals.
          Starting from {budget.budget_year} Actual = <strong>{budget.actual_amount}</strong>.
          Target December Budget (-{budget.reduction_percent}% reduction) = <strong>{budget.december_budget}</strong>.
        </div>
      </div>
    </div>
  );
}
