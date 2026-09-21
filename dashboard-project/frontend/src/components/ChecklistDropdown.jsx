import { useState, useRef, useEffect } from "react";

export default function ChecklistDropdown({
  label,
  options = [], // [{ value: any, label: string }] or [string/number]
  selectedValues = [], // array of selected values
  onChange, // (newSelectedValues) => void
  placeholder = "Select...",
  allLabel = "All",
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const dropdownRef = useRef(null);
  const searchInputRef = useRef(null);

  // Normalize options to [{ value, label }]
  const normalizedOptions = options.map((opt) => {
    if (opt !== null && typeof opt === "object" && "value" in opt) {
      return { value: opt.value, label: String(opt.label) };
    }
    return { value: opt, label: String(opt) };
  });

  // Close when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Focus search input on open
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    } else {
      setSearchTerm("");
    }
  }, [isOpen]);

  const selectedSet = new Set((selectedValues || []).map((v) => String(v)));

  // Filter options by search term
  const filteredOptions = normalizedOptions.filter((opt) =>
    opt.label.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const isAllSelected =
    normalizedOptions.length > 0 &&
    normalizedOptions.every((opt) => selectedSet.has(String(opt.value)));

  const isSomeSelected =
    !isAllSelected &&
    normalizedOptions.some((opt) => selectedSet.has(String(opt.value)));

  const handleToggleOption = (val) => {
    const valStr = String(val);
    const newSet = new Set(selectedSet);
    if (newSet.has(valStr)) {
      newSet.delete(valStr);
    } else {
      newSet.add(valStr);
    }
    const result = normalizedOptions
      .filter((opt) => newSet.has(String(opt.value)))
      .map((opt) => opt.value);
    onChange(result);
  };

  const handleToggleSelectAll = () => {
    if (isAllSelected || isSomeSelected) {
      onChange([]);
    } else {
      onChange(normalizedOptions.map((opt) => opt.value));
    }
  };

  const handleClear = (e) => {
    if (e) e.stopPropagation();
    onChange([]);
  };

  // Label to show on the button
  const getButtonText = () => {
    if (selectedSet.size === 0) {
      return `${allLabel} (${normalizedOptions.length})`;
    }
    if (selectedSet.size === 1) {
      const selectedOpt = normalizedOptions.find((opt) =>
        selectedSet.has(String(opt.value))
      );
      return selectedOpt ? selectedOpt.label : "1 selected";
    }
    if (selectedSet.size === normalizedOptions.length) {
      return `${allLabel} (${normalizedOptions.length})`;
    }
    return `${selectedSet.size} selected`;
  };

  return (
    <div className="checklist-dropdown" ref={dropdownRef}>
      {label && <label className="checklist-dropdown-label">{label}</label>}

      <button
        type="button"
        className={`checklist-trigger-btn ${isOpen ? "active" : ""} ${
          selectedSet.size > 0 ? "has-selection" : ""
        }`}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className="checklist-trigger-text">{getButtonText()}</span>

        <div className="checklist-trigger-icons">
          {selectedSet.size > 0 && (
            <span
              className="checklist-clear-btn"
              title="Clear selection"
              onClick={handleClear}
            >
              ✕
            </span>
          )}
          <span className={`checklist-arrow ${isOpen ? "open" : ""}`}>▼</span>
        </div>
      </button>

      {isOpen && (
        <div className="checklist-popover" role="dialog">
          <div className="checklist-search-box">
            <span className="checklist-search-icon">🔍</span>
            <input
              ref={searchInputRef}
              type="text"
              className="checklist-search-input"
              placeholder={`Search ${label || "options"}...`}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button
                type="button"
                className="checklist-search-clear"
                onClick={() => setSearchTerm("")}
              >
                ✕
              </button>
            )}
          </div>

          <div className="checklist-actions-bar">
            <label className="checklist-item select-all-item">
              <input
                type="checkbox"
                className="checklist-checkbox"
                checked={isAllSelected}
                ref={(el) => {
                  if (el) el.indeterminate = isSomeSelected;
                }}
                onChange={handleToggleSelectAll}
              />
              <span className="checklist-item-text font-bold">
                (Select All)
              </span>
            </label>

            <span className="checklist-counts">
              {selectedSet.size > 0
                ? `${selectedSet.size}/${normalizedOptions.length} selected`
                : "All"}
            </span>
          </div>

          <div className="checklist-options-list" role="listbox">
            {filteredOptions.length === 0 ? (
              <div className="checklist-no-matches">No matches found</div>
            ) : (
              filteredOptions.map((opt) => {
                const isChecked = selectedSet.has(String(opt.value));
                return (
                  <label
                    key={String(opt.value)}
                    className={`checklist-item ${isChecked ? "checked" : ""}`}
                  >
                    <input
                      type="checkbox"
                      className="checklist-checkbox"
                      checked={isChecked}
                      onChange={() => handleToggleOption(opt.value)}
                    />
                    <span className="checklist-item-text">{opt.label}</span>
                  </label>
                );
              })
            )}
          </div>

          <div className="checklist-footer">
            <button
              type="button"
              className="checklist-action-btn"
              onClick={handleClear}
            >
              Clear
            </button>
            <button
              type="button"
              className="checklist-action-btn primary"
              onClick={() => setIsOpen(false)}
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
