import { useEffect, useRef, useState } from "react";
import { exportCsvUrl, exportExcelUrl, exportSummaryPdfUrl } from "../api";

function triggerDownload(url) {
  const link = document.createElement("a");
  link.href = url;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// Single "Export" toggle (matches the Filters pill pattern) that opens a
// small menu of the three download options for the Dashboard's current view.
export default function ExportToolbar({ globalFilters, hasArrival, hasDisposal }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  if (!hasArrival && !hasDisposal) return null;

  const runAndClose = (fn) => {
    fn();
    setOpen(false);
  };

  const handleExcel = () => triggerDownload(exportExcelUrl(globalFilters));

  const handleCsv = () => {
    if (hasArrival) triggerDownload(exportCsvUrl("arrival", globalFilters));
    if (hasDisposal) {
      // Staggered so the browser treats these as two distinct downloads
      // instead of dropping the second one.
      setTimeout(() => triggerDownload(exportCsvUrl("disposal", globalFilters)), 400);
    }
  };

  const handlePdf = () => triggerDownload(exportSummaryPdfUrl(globalFilters));

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
          <button type="button" className="export-menu-item" onClick={() => runAndClose(handleExcel)}>
            <span className="export-menu-icon">📊</span>
            <span>Export View to Excel (.xlsx)</span>
          </button>
          <button type="button" className="export-menu-item" onClick={() => runAndClose(handleCsv)}>
            <span className="export-menu-icon">📄</span>
            <span>Export Cleaned CSV (.csv)</span>
          </button>
          <button type="button" className="export-menu-item" onClick={() => runAndClose(handlePdf)}>
            <span className="export-menu-icon">🧾</span>
            <span>Export Summary PDF</span>
          </button>
        </div>
      )}
    </div>
  );
}
