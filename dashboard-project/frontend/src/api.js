import axios from "axios";

const client = axios.create({ baseURL: "/api" });

function buildParams({ year, month, filters } = {}) {
  const params = {};
  if (year !== undefined && year !== null && year !== "") {
    if (Array.isArray(year)) {
      if (year.length > 0) params.year = year.join(",");
    } else {
      params.year = year;
    }
  }
  if (month !== undefined && month !== null && month !== "") {
    if (Array.isArray(month)) {
      if (month.length > 0) params.month = month.join(",");
    } else {
      params.month = month;
    }
  }
  if (filters && Object.keys(filters).length > 0) {
    const cleaned = {};
    for (const [k, v] of Object.entries(filters)) {
      if (v !== undefined && v !== null && v !== "") {
        if (Array.isArray(v)) {
          if (v.length > 0) cleaned[k] = v;
        } else {
          cleaned[k] = v;
        }
      }
    }
    if (Object.keys(cleaned).length > 0) {
      params.filters = JSON.stringify(cleaned);
    }
  }
  return params;
}

export const uploadFiles = (files, targetTable = "auto") => {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  if (targetTable) {
    form.append("target_table", targetTable);
  }
  return client.post("/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const fetchTables = () => client.get("/tables");

export const fetchFilterOptions = (table) => client.get(`/filters/${table}`);

export const fetchData = (table, limit = 50, offset = 0, filterState) =>
  client.get(`/data/${table}`, { params: { limit, offset, ...buildParams(filterState) } });

export const fetchKpis = (table, filterState) =>
  client.get(`/kpis/${table}`, { params: buildParams(filterState) });

export const fetchChartData = (table, x, y, agg, filterState) =>
  client.get(`/chart-data/${table}`, {
    params: { x, y: y || undefined, agg, ...buildParams(filterState) },
  });

export const fetchPeriodTrend = (table, period, filterState) =>
  client.get(`/period-trend/${table}`, { params: { period, ...buildParams(filterState) } });

export const fetchTeamWiseSummary = (filterState) =>
  client.get("/team-wise-summary", { params: buildParams(filterState) });

// Independent of fetchTeamWiseSummary — it's a live call to Ford's Maximo
// API that can be slow or unreachable, so it's fetched on its own timeline
// rather than bundled into the (fast, DB-only) team-wise-summary response.
export const fetchMaximoBudget = (filterState) =>
  client.get("/maximo-budget", { params: buildParams(filterState) });

export const fetchDashboardKpis = (table, filterState) =>
  client.get(`/dashboard-kpis/${table}`, { params: buildParams(filterState) });

export const fetchGlidepathDepartments = () => client.get("/glidepath/departments");

export const fetchGlidepathYears = (departmentNo) =>
  client.get("/glidepath/years", { params: { department_no: departmentNo } });

export const fetchGlidepath = (departmentNo, year) =>
  client.get("/glidepath", { params: { department_no: departmentNo, year } });

export const saveGlidepathMonthly = (payload) =>
  client.post("/glidepath/save-monthly", payload);

export const saveGlidepath = (payload) =>
  client.post("/glidepath/save", payload);

export const fetchGlidepathSummaryComparison = (filterState) =>
  client.get("/glidepath-summary-comparison", { params: buildParams(filterState) });

export const askFordAi = (message, conversationHistory = [], filters = {}) =>
  client.post("/ai/chat", {
    message,
    conversation_history: conversationHistory,
    filters,
  });

const buildQueryString = (filterState) =>
  new URLSearchParams(buildParams(filterState)).toString();

export const exportExcelUrl = (filterState, tables) => {
  const qs = buildQueryString(filterState);
  const tablesParam = tables && tables.length ? `&tables=${tables.join(",")}` : "";
  return `/api/export/excel?${qs}${tablesParam}`;
};

export const exportCsvUrl = (table, filterState) =>
  `/api/export/csv/${table}?${buildQueryString(filterState)}`;

export const exportSummaryPdfUrl = (filterState) =>
  `/api/export/summary-pdf?${buildQueryString(filterState)}`;
