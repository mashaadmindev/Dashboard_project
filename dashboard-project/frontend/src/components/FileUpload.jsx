import { useRef, useState } from "react";
import { uploadFiles } from "../api";

export default function FileUpload({ onUploaded }) {
  const inputRef = useRef(null);
  const [picked, setPicked] = useState([]);
  const [targetTable, setTargetTable] = useState("auto");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const addFiles = (fileList) => {
    const excelFiles = Array.from(fileList).filter((f) =>
      /\.(xlsx|xls)$/i.test(f.name)
    );
    setPicked(excelFiles);
    setError(null);
    setResult(null);
  };

  const handleUpload = async () => {
    if (picked.length === 0) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await uploadFiles(picked, targetTable);
      setResult(res.data.uploaded);
      setPicked([]);
      onUploaded();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : (err?.message || "Upload failed. Please check backend.");
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div
        className={`upload-zone ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
      >
        <p className="upload-title">Upload Excel files</p>
        <p className="upload-hint">
          Drop your .xlsx files here, or choose a target table below.
        </p>

        {/* Target Table Dropdown */}
        <div style={{ marginBottom: 16, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>
            Target Destination Table:
          </label>
          <select
            className="select"
            style={{ maxWidth: 280, padding: "8px 12px" }}
            value={targetTable}
            onChange={(e) => setTargetTable(e.target.value)}
          >
            <option value="auto">✨ Auto-detect table from filename</option>
            <option value="arrival">📥 Arrivals Table (arrival)</option>
            <option value="disposal">📤 Disposal Table (disposal)</option>
            <option value="budget">💰 Budget Table (budget)</option>
            <option value="maximo_budget">📊 Maximo Budget Table (maximo_budget)</option>
            <option value="niv_sheet_arrival">📋 Niv Sheet Arrival (niv_sheet_arrival)</option>
            <option value="niv_sheet_disposal">📋 Niv Sheet Disposal (niv_sheet_disposal)</option>
          </select>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xls"
          multiple
          className="file-input"
          onChange={(e) => addFiles(e.target.files)}
        />

        <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
          <button className="btn btn-secondary" onClick={() => inputRef.current.click()}>
            Choose files
          </button>
          <button className="btn" onClick={handleUpload} disabled={busy || picked.length === 0}>
            {busy
              ? "Uploading…"
              : picked.length > 0
                ? `Upload ${picked.length} file${picked.length > 1 ? "s" : ""} to ${targetTable === "auto" ? "auto-detected table" : targetTable}`
                : "Upload"}
          </button>
        </div>

        {error && <p className="upload-error">{error}</p>}
      </div>

      {result && result.length > 0 && (
        <div className="upload-result">
          <p className="upload-result-title">
            {result.length} excel{result.length > 1 ? "s" : ""} uploaded successfully to database
          </p>
          <ul className="upload-result-list">
            {result.map((r) => (
              <li key={r.table_name}>
                <strong>{r.table_name}</strong>
                {r.new_rows_added > 0
                  ? ` — ${r.new_rows_added} new row${r.new_rows_added > 1 ? "s" : ""} added`
                  : " — no new rows"}
                {r.duplicate_rows_skipped > 0 &&
                  ` (${r.duplicate_rows_skipped} duplicate${r.duplicate_rows_skipped > 1 ? "s" : ""} skipped)`}
                {`, ${r.row_count} total rows`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
