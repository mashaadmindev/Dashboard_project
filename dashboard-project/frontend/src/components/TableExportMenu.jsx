import { useEffect, useRef, useState } from "react";
import { exportCsvUrl, exportExcelUrl } from "../api";

function triggerDownload(url) {
  const link = document.createElement("a");
  link.href = url;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// Same dropdown pattern as ExportToolbar, scoped to a single table (CSV or
// a one-sheet Excel export) instead of the Dashboard's combined view.
export default function TableExportMenu({ table, globalFilters }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const runAndClose = (fn) => {
    fn();
    setOpen(false);
  };

  return (
    <div className="export-dropdown" ref={rootRef}>
      <button
        type="button"
        className="export-trigger-btn"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span>⬇</span>
        <span>Export</span>
      </button>

      {open && (
        <div className="export-menu" role="menu">
          <button
            type="button"
            className="export-menu-item"
            onClick={() => runAndClose(() => triggerDownload(exportCsvUrl(table, globalFilters)))}
          >
            <span className="export-menu-icon">📄</span>
            <span>Export CSV (.csv)</span>
          </button>
          <button
            type="button"
            className="export-menu-item"
            onClick={() =>
              runAndClose(() => triggerDownload(exportExcelUrl(globalFilters, [table])))
            }
          >
            <span className="export-menu-icon">📊</span>
            <span>Export Excel (.xlsx)</span>
          </button>
        </div>
      )}
    </div>
  );
}
