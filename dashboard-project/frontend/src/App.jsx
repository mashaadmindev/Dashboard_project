import { useEffect, useState } from "react";
import { fetchTables } from "./api";
import FileUpload from "./components/FileUpload";
import DatasetSection from "./components/DatasetSection";
import DashboardKpiRow from "./components/DashboardKpiRow";
import AlertsPanel from "./components/AlertsPanel";
import TeamWisePage from "./components/TeamWisePage";
import GlidePathPage from "./components/GlidePathPage";
import AskFordAiPage from "./components/AskFordAiPage";
import UniversalFilterBar, { EMPTY_GLOBAL_FILTERS } from "./components/UniversalFilterBar";
import ExportToolbar from "./components/ExportToolbar";
import RawDataPage from "./components/RawDataPage";

export default function App() {
  const [page, setPage] = useState("dashboard"); // "dashboard" | "teamwise" | "glidepath" | "upload" | "ai_analyst"
  const [tables, setTables] = useState([]);
  // Shared across Dashboard and Team Wise so picking a filter (year, month,
  // team, region, vci) applies everywhere at once instead of per-section.
  const [globalFilters, setGlobalFilters] = useState(EMPTY_GLOBAL_FILTERS);
  // Bumped after every upload so KPIs/charts refetch even when the upload
  // added rows to a table that's already on screen (nothing else would
  // otherwise change to re-trigger a fetch).
  const [refreshKey, setRefreshKey] = useState(0);

  const [theme, setTheme] = useState(() => {
    return localStorage.getItem("ford_theme") || "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("ford_theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  };

  const loadTables = () => {
    fetchTables().then((res) => setTables(res.data));
  };

  const handleUploaded = () => {
    loadTables();
    setRefreshKey((k) => k + 1);
  };

  useEffect(() => {
    // Refetches on every page switch too, not just on first mount — table
    // row counts can change from outside this browser tab (another tab,
    // another user, a direct API call), so an already-open tab needs to
    // re-read the database whenever you navigate to a page that shows counts.
    loadTables();
  }, [page]);

  const arrivalMeta = tables.find((t) => t.table_name === "arrival");
  const disposalMeta = tables.find((t) => t.table_name === "disposal");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-logo-wrapper">
          <img src="/ford-logo.webp" alt="Ford" className="brand-logo" />
        </div>
        <div className="brand-sub">Arrival & Disposal Analytics</div>

        <ul className="nav-list">
          <li>
            <button
              className={`nav-item ${page === "dashboard" ? "active" : ""}`}
              onClick={() => setPage("dashboard")}
            >
              Dashboard
            </button>
          </li>
          <li>
            <button
              className={`nav-item ${page === "teamwise" ? "active" : ""}`}
              onClick={() => setPage("teamwise")}
            >
              Team Wise
            </button>
          </li>
          <li>
            <button
              className={`nav-item ${page === "glidepath" ? "active" : ""}`}
              onClick={() => setPage("glidepath")}
            >
              Glide Path
            </button>
          </li>
          <li>
            <button
              className={`nav-item ${page === "raw_data" ? "active" : ""}`}
              onClick={() => setPage("raw_data")}
            >
              Arrivals & Disposals
            </button>
          </li>
          <li>
            <button
              className={`nav-item ${page === "upload" ? "active" : ""}`}
              onClick={() => setPage("upload")}
            >
              Upload Data
            </button>
          </li>
          <li>
            <button
              className={`nav-item ${page === "ai_analyst" ? "active" : ""}`}
              onClick={() => setPage("ai_analyst")}
            >
              Ask Ford data analysis AI
            </button>
          </li>
        </ul>

        <div className="sidebar-footer">
          <div className="theme-switch-row">
            <span className="theme-switch-label">
              {theme === "dark" ? "🌙 Dark Mode" : "☀️ Light Mode"}
            </span>
            <button
              type="button"
              className={`theme-switch ${theme === "dark" ? "on" : ""}`}
              onClick={toggleTheme}
              role="switch"
              aria-checked={theme === "dark"}
              title={`Switch to ${theme === "dark" ? "Light" : "Dark"} mode`}
            >
              <span className="theme-switch-knob" />
            </button>
          </div>
        </div>
      </aside>

      <main className="main">
        {page === "ai_analyst" ? (
          <AskFordAiPage globalFilters={globalFilters} />
        ) : page === "upload" ? (
          <>
            <h1 className="page-title">Upload Data</h1>
            <p className="page-subtitle">
              Upload Excel files to load them into the database. Rows are matched against
              what's already there, so only genuinely new rows get appended.
            </p>
            <FileUpload onUploaded={handleUploaded} />
          </>
        ) : page === "glidepath" ? (
          <>
            <UniversalFilterBar value={globalFilters} onChange={setGlobalFilters} />
            <GlidePathPage />
          </>
        ) : page === "raw_data" ? (
          <>
            <h1 className="page-title">Arrival & Disposal Data</h1>
            <p className="page-subtitle">
              Every uploaded row and column, exactly as stored — filter, page through it, or
              export it below.
            </p>
            <UniversalFilterBar value={globalFilters} onChange={setGlobalFilters} />
            <RawDataPage
              globalFilters={globalFilters}
              arrivalMeta={arrivalMeta}
              disposalMeta={disposalMeta}
              refreshKey={refreshKey}
            />
          </>
        ) : (
          <>
            <UniversalFilterBar
              value={globalFilters}
              onChange={setGlobalFilters}
              alwaysOpen={page === "dashboard"}
            />

            {page === "teamwise" ? (
              <>
                <h1 className="page-title">Team Wise</h1>
                <p className="page-subtitle">
                  Row counts across every tracked category. Upload a file named after a
                  category (e.g. "Budget.xlsx", "Niv Sheet Arrival.xlsx") to populate it.
                </p>
                <TeamWisePage tables={tables} refreshKey={refreshKey} globalFilters={globalFilters} />
              </>
            ) : (
              <>
                <div className="page-title-row">
                  <div>
                    <h1 className="page-title">Dashboard</h1>
                    <p className="page-subtitle">
                      Explore KPIs, filters, and breakdowns for arrivals and disposals.
                    </p>
                  </div>
                  {tables.length > 0 && (
                    <ExportToolbar
                      globalFilters={globalFilters}
                      hasArrival={!!arrivalMeta}
                      hasDisposal={!!disposalMeta}
                    />
                  )}
                </div>

                {tables.length === 0 ? (
                  <p className="empty-message">
                    No datasets yet. Go to <strong>Upload Data</strong> to get started.
                  </p>
                ) : (
                  <>
                    <DashboardKpiRow
                      hasArrival={!!arrivalMeta}
                      hasDisposal={!!disposalMeta}
                      globalFilters={globalFilters}
                      refreshKey={refreshKey}
                    />

                    <AlertsPanel globalFilters={globalFilters} refreshKey={refreshKey} />

                    {arrivalMeta ? (
                      <DatasetSection
                        table="arrival"
                        label="Arrivals"
                        meta={arrivalMeta}
                        refreshKey={refreshKey}
                        globalFilters={globalFilters}
                      />
                    ) : (
                      <div className="section">
                        <p className="section-title">Arrivals</p>
                        <div className="empty-state">No arrival data uploaded yet.</div>
                      </div>
                    )}

                    {disposalMeta ? (
                      <DatasetSection
                        table="disposal"
                        label="Disposal"
                        meta={disposalMeta}
                        refreshKey={refreshKey}
                        globalFilters={globalFilters}
                      />
                    ) : (
                      <div className="section">
                        <p className="section-title">Disposal</p>
                        <div className="empty-state">No disposal data uploaded yet.</div>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
