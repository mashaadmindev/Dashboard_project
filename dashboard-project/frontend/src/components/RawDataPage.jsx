import { useEffect, useState } from "react";
import { fetchData } from "../api";
import TableExportMenu from "./TableExportMenu";

const PAGE_SIZE = 50;

const TABS = [
  { key: "arrival", label: "Arrival Data" },
  { key: "disposal", label: "Disposal Data" },
];

export default function RawDataPage({ globalFilters, arrivalMeta, disposalMeta, refreshKey }) {
  const [activeTab, setActiveTab] = useState("arrival");
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const meta = activeTab === "arrival" ? arrivalMeta : disposalMeta;
  const columns = meta?.columns?.map((c) => c.name) ?? [];

  // Jumping tabs or changing filters always starts back at page 1.
  useEffect(() => {
    setOffset(0);
  }, [activeTab, globalFilters]);

  useEffect(() => {
    if (!meta) {
      setRows([]);
      setTotal(0);
      return;
    }
    setLoading(true);
    setError(null);
    fetchData(activeTab, PAGE_SIZE, offset, globalFilters)
      .then((res) => {
        setRows(res.data.rows);
        setTotal(res.data.total);
      })
      .catch((err) => setError(err?.response?.data?.detail ?? "Could not load data"))
      .finally(() => setLoading(false));
  }, [activeTab, offset, globalFilters, meta, refreshKey]);

  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="raw-data-page">
      <div className="tabs-row">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`btn-toggle ${activeTab === t.key ? "active" : ""}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {!meta ? (
        <div className="empty-state">
          No {activeTab === "arrival" ? "arrival" : "disposal"} data uploaded yet.
        </div>
      ) : (
        <>
          <div className="raw-data-toolbar">
            <span className="raw-data-count font-mono">
              {loading ? "Loading…" : `${rangeStart}-${rangeEnd} of ${total} rows`}
            </span>
            <TableExportMenu table={activeTab} globalFilters={globalFilters} />
          </div>

          {error && <div className="upload-error">{error}</div>}

          {!error && (
            <div className="team-table-wrap">
              <table className="team-table">
                <thead>
                  <tr>
                    {columns.map((c) => (
                      <th key={c}>{c.replace(/_/g, " ")}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr>
                      <td colSpan={columns.length || 1} className="empty-state">
                        No rows for the selected filters.
                      </td>
                    </tr>
                  ) : (
                    rows.map((row, i) => (
                      <tr key={i}>
                        {columns.map((c) => (
                          <td key={c}>{row[c] === null || row[c] === undefined ? "—" : String(row[c])}</td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          <div className="raw-data-pagination">
            <button
              type="button"
              className="btn-action btn-secondary"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            >
              ← Prev
            </button>
            <button
              type="button"
              className="btn-action btn-secondary"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            >
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  );
}
