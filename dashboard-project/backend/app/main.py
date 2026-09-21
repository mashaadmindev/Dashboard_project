import json
import logging
import re
from datetime import date, datetime
from io import BytesIO, StringIO
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless — this process never opens a display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import inspect, text

from app.database import (
    METADATA_TABLE,
    engine,
    init_glidepath_tables,
    init_metadata_table,
)
from app.ingest import (
    load_dataframe_to_postgres,
    read_excel_file,
    sanitize_identifier,
    sanitize_table_name,
)
from app.maximo_client import VCI_OPTIONS as MAXIMO_VCI_OPTIONS
from app.maximo_client import get_assets as get_maximo_assets
from app.maximo_client import is_configured as maximo_is_configured

logger = logging.getLogger(__name__)

app = FastAPI(title="Excel-to-Postgres Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_metadata_table()
    init_glidepath_tables()


def _get_table_meta(table_name: str) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                f"SELECT columns_json, primary_date_column FROM {METADATA_TABLE} "
                f"WHERE table_name = :t"
            ),
            {"t": table_name},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Unknown table '{table_name}'")
    return {
        "columns": json.loads(row.columns_json),
        "primary_date_column": row.primary_date_column,
    }


def _load_table_df(table_name: str) -> pd.DataFrame:
    return pd.read_sql_table(table_name, engine)


def _parse_filters(filters: str | None) -> dict:
    if not filters:
        return {}
    try:
        parsed = json.loads(filters)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_date_components(series: pd.Series, default_year: int = 2026):
    """Parses date series accurately across standard dates, month-day strings (e.g. '5-Aug'),
    plain month strings (e.g. 'Aug', 'August'), YYYY-MM, MM/YYYY, and Excel serial integers
    into (year_series, month_series).
    """
    if series.empty:
        return pd.Series(dtype=float, index=series.index), pd.Series(
            dtype=float, index=series.index
        )

    month_name_to_num = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }

    s = series.fillna("").astype(str).str.strip()
    dt = pd.to_datetime(s, errors="coerce", format="mixed")

    years = dt.dt.year.to_dict()
    months = dt.dt.month.to_dict()

    effective_default_year = int(default_year) if default_year else 2026

    for idx, raw_val in s.items():
        curr_yr = years.get(idx)
        curr_mo = months.get(idx)

        # If both month and a valid full 4-digit year are present
        if not pd.isna(curr_mo) and not pd.isna(curr_yr) and curr_yr > 100:
            continue

        if pd.isna(raw_val) or not isinstance(raw_val, str):
            continue

        if not raw_val or raw_val.lower() in ("nan", "none", "null", "nat", ""):
            continue

        # If pd.to_datetime parsed month but gave dummy/2-digit year (e.g. 5-Aug -> yr=1, or yr=26)
        if not pd.isna(curr_mo) and not pd.isna(curr_yr) and curr_yr <= 100:
            if 1 < curr_yr < 100:
                years[idx] = 2000 + int(curr_yr)
            else:
                years[idx] = effective_default_year
            continue

        val = raw_val.strip()
        val_lower = val.lower()

        # 1. Plain month name e.g. 'aug', 'august'
        if val_lower in month_name_to_num:
            years[idx] = effective_default_year
            months[idx] = month_name_to_num[val_lower]
            continue

        # 2. Number alone (1-12) representing month
        if val.isdigit() and 1 <= int(val) <= 12:
            years[idx] = effective_default_year
            months[idx] = int(val)
            continue

        # 3. Excel serial number
        try:
            num_val = float(val)
            if num_val > 20000:
                dt_serial = pd.to_datetime(num_val, unit="D", origin="1899-12-30")
                years[idx] = dt_serial.year
                months[idx] = dt_serial.month
                continue
        except (ValueError, TypeError):
            pass

        # 4. Month name with Year (e.g. 'Aug 2026', 'August 2026', 'Aug-26', '2026-Aug')
        m_my = re.search(
            r"([A-Za-z]{3,9})[\s\-_/]+(\d{2,4})|(\d{2,4})[\s\-_/]+([A-Za-z]{3,9})", val
        )
        if m_my:
            mon_str = (m_my.group(1) or m_my.group(4)).lower()
            yr_str = m_my.group(2) or m_my.group(3)
            mon_num = month_name_to_num.get(mon_str) or month_name_to_num.get(
                mon_str[:3]
            )
            if mon_num:
                yr = int(yr_str)
                if yr < 100:
                    yr += 2000
                years[idx] = yr
                months[idx] = mon_num
                continue

        # 5. YYYY-MM or MM/YYYY (e.g. '2026-08', '2026-8', '8/2026', '08/2026')
        m_num_my = re.match(r"^(\d{4})[\-_/](\d{1,2})$", val)
        if m_num_my:
            years[idx] = int(m_num_my.group(1))
            months[idx] = int(m_num_my.group(2))
            continue

        m_num_my2 = re.match(r"^(\d{1,2})[\-_/](\d{4})$", val)
        if m_num_my2:
            years[idx] = int(m_num_my2.group(2))
            months[idx] = int(m_num_my2.group(1))
            continue

        # 6. Fallback regex for Day-Month (e.g. '5-Aug', 'Aug-5', '12/Aug')
        m_dm = re.search(
            r"(?:(\d{1,2})[-/\s]+([A-Za-z]{3,9})|([A-Za-z]{3,9})[-/\s]+(\d{1,2}))", val
        )
        if m_dm:
            mon_str = (m_dm.group(2) or m_dm.group(3)).lower()[:3]
            if mon_str in month_name_to_num:
                years[idx] = effective_default_year
                months[idx] = month_name_to_num[mon_str]
                continue

    year_series = pd.Series(years, index=series.index)
    month_series = pd.Series(months, index=series.index)
    return year_series, month_series


def _normalize_int_list(val) -> list[int]:
    if val is None or val == "" or val == []:
        return []
    if isinstance(val, (int, float)):
        return [int(val)]
    if isinstance(val, str):
        parts = [p.strip() for p in val.split(",") if p.strip()]
        res = []
        for p in parts:
            try:
                res.append(int(p))
            except ValueError:
                pass
        return res
    if isinstance(val, (list, tuple, set)):
        res = []
        for item in val:
            try:
                res.append(int(item))
            except (ValueError, TypeError):
                pass
        return res
    return []


def _apply_filters(
    df: pd.DataFrame,
    date_col: str | None,
    year: Any = None,
    month: Any = None,
    filters: dict | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df

    filters = filters or {}
    year_target = year if (year is not None and year != "" and year != []) else filters.get("year")
    month_target = month if (month is not None and month != "" and month != []) else filters.get("month")

    year_list = _normalize_int_list(year_target)
    month_list = _normalize_int_list(month_target)

    if date_col and date_col in df.columns:
        default_y = year_list[0] if year_list else 2026
        year_series, month_series = _parse_date_components(
            df[date_col], default_year=default_y
        )

        if year_list:
            df = df[year_series.isin(year_list)]
            year_series = year_series.loc[df.index]
            month_series = month_series.loc[df.index]
        if month_list:
            df = df[month_series.isin(month_list)]

    for col, val in filters.items():
        if col in ("year", "month"):
            continue
        if val is None or val == "" or val == [] or val == [""]:
            continue

        val_list = [val] if not isinstance(val, (list, tuple, set)) else list(val)
        val_list = [str(v).strip() for v in val_list if str(v).strip() != ""]
        if not val_list:
            continue

        if col in ["vci", "vic", "vi"]:
            all_patterns = set()
            for v in val_list:
                all_patterns.add(v)
                all_patterns.add(v.lstrip("0"))
                all_patterns.add(v.zfill(6))

            matched = False
            for target_col in ["vci", "vic", "vi"]:
                if target_col in df.columns:
                    target_str = df[target_col].astype(str).str.strip()
                    df = df[
                        target_str.isin(all_patterns)
                        | target_str.str.lstrip("0").isin(all_patterns)
                    ]
                    matched = True
                    break
            if not matched and col in df.columns:
                df = df[df[col].astype(str).str.strip().isin(val_list)]
        elif col in df.columns:
            val_set = set(val_list)
            df = df[df[col].astype(str).str.strip().isin(val_set)]
    return df


def _json_safe(value):
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime, date)):
        if hasattr(value, "year") and value.year <= 100:
            return f"{value.day:02d}-{value.strftime('%b')}-2026"
        return value.strftime("%d-%b-%Y")
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%d-%b-%Y")
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        return str(value).split("T")[0]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


@app.post("/api/upload")
async def upload_excels(
    files: list[UploadFile] = File(...),
    target_table: str | None = Form(None),
):
    """Accepts one or more Excel files, loads each as its own Postgres table or target_table when specified."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results = []
    for f in files:
        if not f.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(
                status_code=400, detail=f"'{f.filename}' is not an Excel file"
            )

        content = await f.read()
        try:
            df = read_excel_file(content, f.filename)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to parse '{f.filename}': {e}"
            )

        if df.empty:
            raise HTTPException(
                status_code=400, detail=f"'{f.filename}' has no usable rows"
            )

        if target_table and target_table.strip() and target_table.strip() != "auto":
            table_name = sanitize_identifier(target_table)
        else:
            table_name = sanitize_table_name(f.filename)

        try:
            info = load_dataframe_to_postgres(df, table_name, f.filename)
            results.append(info)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error loading '{f.filename}' into table '{table_name}': {e!s}",
            )

    return {"uploaded": results}


@app.get("/api/tables")
def list_tables():
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT table_name, original_filename, uploaded_at, row_count, columns_json "
                f"FROM {METADATA_TABLE} ORDER BY uploaded_at DESC"
            )
        ).fetchall()

    result = []
    for r in rows:
        columns = json.loads(r.columns_json)
        uploaded_at = r.uploaded_at
        if isinstance(uploaded_at, str):
            uploaded_at = datetime.fromisoformat(uploaded_at)
        with engine.connect() as conn:
            for col in columns:
                distinct = conn.execute(
                    text(
                        f'SELECT COUNT(DISTINCT "{col["name"]}") FROM "{r.table_name}"'
                    )
                ).scalar()
                col["distinct_count"] = distinct

        result.append(
            {
                "table_name": r.table_name,
                "original_filename": r.original_filename,
                "uploaded_at": uploaded_at.isoformat(),
                "row_count": r.row_count,
                "columns": columns,
            }
        )
    return result


CATEGORICAL_FILTER_COLUMNS = ["vci", "team", "region", "location", "vehicle_department"]
NUMERIC_FILTER_COLUMNS = []


@app.get("/api/filters/{table_name}")
def get_filters(table_name: str):
    """Describes the filter dimensions available for a dataset: years/months
    from its primary date column, plus vci/team/region dropdowns."""
    meta = _get_table_meta(table_name)
    date_col = meta["primary_date_column"]
    df = _load_table_df(table_name)

    years, months = [], []
    if date_col and date_col in df.columns:
        year_series, month_series = _parse_date_components(df[date_col])
        years = sorted(int(y) for y in year_series.dropna().unique() if not pd.isna(y))
        months = sorted(
            int(m) for m in month_series.dropna().unique() if not pd.isna(m)
        )

    categorical_filters = []
    for name in CATEGORICAL_FILTER_COLUMNS:
        target_col = None
        if name in df.columns:
            target_col = name
        elif name == "vci":
            for alt in ["vic", "vi"]:
                if alt in df.columns:
                    target_col = alt
                    break

        if target_col and target_col in df.columns:
            raw_vals = df[target_col].dropna().unique()
            values = sorted(
                str(v).strip()
                for v in raw_vals
                if str(v).strip()
                and str(v).strip().lower() not in ("nan", "none", "null")
            )
            if values:
                categorical_filters.append({"column": name, "values": values})

    return {
        "date_column": date_col,
        "years": years,
        "months": months,
        "categorical_filters": categorical_filters,
        "numeric_filters": [],
    }


@app.get("/api/data/{table_name}")
def get_data(
    table_name: str,
    limit: int = Query(50, le=1000),
    offset: int = Query(0, ge=0),
    year: str | None = None,
    month: str | None = None,
    filters: str | None = None,
):
    limit_val = limit.default if hasattr(limit, "default") else limit
    offset_val = offset.default if hasattr(offset, "default") else offset
    limit_val = int(limit_val) if str(limit_val).isdigit() else 50
    offset_val = int(offset_val) if str(offset_val).isdigit() else 0

    meta = _get_table_meta(table_name)
    df = _load_table_df(table_name)
    df = _apply_filters(
        df, meta["primary_date_column"], year, month, _parse_filters(filters)
    )

    page = df.iloc[offset_val : offset_val + limit_val]
    rows = [
        {col: _json_safe(val) for col, val in record.items()}
        for record in page.to_dict(orient="records")
    ]
    return {"rows": rows, "limit": limit_val, "offset": offset_val, "total": len(df)}


NUMERIC_SUMMARY_EXCLUDED_COLUMNS = {"model_year", "model_yr", "vci", "vi", "year"}


@app.get("/api/kpis/{table_name}")
def get_kpis(
    table_name: str,
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    filters: str | None = None,
):
    meta = _get_table_meta(table_name)
    df = _load_table_df(table_name)
    df = _apply_filters(
        df, meta["primary_date_column"], year, month, _parse_filters(filters)
    )

    # These columns are numeric but not meaningful to sum/average/min/max —
    # model_year and vci/year are identifiers, not quantities.
    numeric_cols = [
        c
        for c in df.select_dtypes(include="number").columns.tolist()
        if c not in NUMERIC_SUMMARY_EXCLUDED_COLUMNS
    ]
    df.select_dtypes(include="datetime").columns.tolist()

    summaries = []
    for col in numeric_cols[:6]:
        series = df[col].dropna()
        if series.empty:
            continue
        summaries.append(
            {
                "column": col,
                "sum": float(series.sum()),
                "avg": float(series.mean()),
                "min": float(series.min()),
                "max": float(series.max()),
            }
        )

    trend = None
    date_col = meta.get("primary_date_column")
    if date_col and date_col in df.columns:
        trend_df = df[[date_col]].dropna().copy()
        if not trend_df.empty:
            trend_df[date_col] = pd.to_datetime(trend_df[date_col], errors="coerce")
            trend_df = trend_df.dropna()
            if not trend_df.empty:
                span_days = (trend_df[date_col].max() - trend_df[date_col].min()).days
                freq = "D" if span_days <= 90 else ("W" if span_days <= 730 else "ME")
                grouped = (
                    trend_df.set_index(date_col)
                    .assign(_count=1)["_count"]
                    .resample(freq)
                    .sum()
                    .reset_index()
                )
                trend = {
                    "date_column": date_col,
                    "value_column": "record count",
                    "points": [
                        {
                            "period": row[date_col].strftime("%Y-%m-%d"),
                            "value": float(row["_count"]),
                        }
                        for _, row in grouped.iterrows()
                    ],
                }

    return {
        "row_count": len(df),
        "numeric_summaries": summaries,
        "date_columns": [date_col] if date_col else [],
        "trend": trend,
    }


@app.get("/api/chart-data/{table_name}")
def get_chart_data(
    table_name: str,
    x: str = Query(..., description="Column to group by"),
    y: str | None = Query(
        None, description="Numeric column to aggregate (ignored for count)"
    ),
    agg: str = Query("count", pattern="^(sum|avg|count|min|max)$"),
    limit: int = Query(20, le=200),
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    filters: str | None = None,
):
    meta = _get_table_meta(table_name)
    column_names = {c["name"] for c in meta["columns"]}
    if x not in column_names:
        raise HTTPException(status_code=400, detail=f"Unknown column '{x}'")
    if agg != "count" and (not y or y not in column_names):
        raise HTTPException(
            status_code=400,
            detail=f"'y' must be a valid column for aggregation '{agg}'",
        )

    limit_val = limit.default if hasattr(limit, "default") else limit
    limit_val = int(limit_val) if str(limit_val).isdigit() else 20

    df = _load_table_df(table_name)
    df = _apply_filters(
        df, meta["primary_date_column"], year, month, _parse_filters(filters)
    )
    df = df[df[x].notna()]

    if agg == "count":
        grouped = df.groupby(x).size().reset_index(name="y")
    else:
        func = {"sum": "sum", "avg": "mean", "min": "min", "max": "max"}[agg]
        grouped = df.groupby(x)[y].agg(func).reset_index().rename(columns={y: "y"})

    grouped = grouped.sort_values("y", ascending=False).head(limit_val)
    return {
        "data": [
            {"x": str(row[x]), "y": float(row["y"])} for _, row in grouped.iterrows()
        ]
    }


@app.get("/api/period-trend/{table_name}")
def get_period_trend(
    table_name: str,
    period: str = Query("month", pattern="^(month|year)$"),
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    filters: str | None = None,
):
    """Record counts bucketed by calendar month or year, using the table's
    primary date column — powers the Monthly/Yearly trend toggle."""
    meta = _get_table_meta(table_name)
    date_col = meta["primary_date_column"]
    if not date_col:
        return {"date_column": None, "period": period, "points": []}

    df = _load_table_df(table_name)
    df = _apply_filters(df, date_col, year, month, _parse_filters(filters))
    if date_col not in df.columns:
        return {"date_column": date_col, "period": period, "points": []}

    year_series, month_series = _parse_date_components(df[date_col])
    valid = year_series.notna() & month_series.notna()
    if not valid.any():
        return {"date_column": date_col, "period": period, "points": []}

    if period == "year":
        keys = year_series[valid].astype(int).astype(str)
    else:
        keys = (
            year_series[valid].astype(int).astype(str)
            + "-"
            + month_series[valid].astype(int).apply(lambda m: f"{m:02d}")
        )

    counts = keys.value_counts().sort_index()
    return {
        "date_column": date_col,
        "period": period,
        "points": [{"period": k, "count": int(v)} for k, v in counts.items()],
    }


# The Team Wise page's fixed category list — same tables FIXED_TABLE_KEYWORDS
# in ingest.py routes uploads into, in the same display order.
TEAM_WISE_METRICS = [
    {"label": "Arrivals", "table": "arrival"},
    {"label": "Disposal", "table": "disposal"},
    {"label": "Budget", "table": "budget"},
    {"label": "Niv Sheet Arrival", "table": "niv_sheet_arrival"},
    {"label": "Niv Sheet Disposal", "table": "niv_sheet_disposal"},
    {"label": "Maximo_Budget", "table": "maximo_budget"},
]


@app.get("/api/team-wise-summary")
def get_team_wise_summary(
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    filters: str | None = None,
):
    """Per-team breakdown and category totals across every Team Wise category.
    - Arrivals: taken from Glidepath total adds (build + production count).
    - Disposal: taken from Glidepath disposal count.
    - Niv Sheet Arrival: taken from the uploaded Arrival dataset (arrival / niv_sheet_arrival) based on Actual Arrival Date.
    - Niv Sheet Disposal: taken from the uploaded Disposal dataset (disposal / to_be_disposed / niv_sheet_disposal) based on Calendar Month.
    - Budget & Maximo_Budget: taken from budget tables or Glidepath governance info.
    """
    inspector = inspect(engine)
    parsed_filters = _parse_filters(filters)

    filter_year = year if year is not None else parsed_filters.get("year")
    if isinstance(filter_year, (list, tuple, set)):
        filter_year = next((y for y in filter_year if y is not None and str(y).strip() != ""), None)
    if filter_year is not None:
        try:
            filter_year = int(filter_year)
        except (ValueError, TypeError):
            filter_year = None

    filter_month = month if month is not None else parsed_filters.get("month")
    if isinstance(filter_month, (list, tuple, set)):
        filter_month = next((m for m in filter_month if m is not None and str(m).strip() != ""), None)
    if filter_month is not None:
        try:
            filter_month = int(filter_month)
        except (ValueError, TypeError):
            filter_month = None

    vci_val = parsed_filters.get("vci") or parsed_filters.get("vic")
    if isinstance(vci_val, (list, tuple, set)):
        vci_val = next((v for v in vci_val if v is not None and str(v).strip() != ""), None)
    dept_no = str(vci_val).zfill(6) if vci_val else None
    team_filter = parsed_filters.get("team")

    # 1. Niv Sheet Arrival (from uploaded arrival / niv_sheet_arrival table based on actual_arrival_date)
    df_niv_arr = pd.DataFrame()
    for tbl_arr in ["niv_sheet_arrival", "arrival"]:
        if inspector.has_table(tbl_arr):
            meta = _get_table_meta(tbl_arr)
            raw_arr = _load_table_df(tbl_arr)
            date_col = (
                "actual_arrival_date"
                if "actual_arrival_date" in raw_arr.columns
                else meta["primary_date_column"]
            )
            df_niv_arr = _apply_filters(
                raw_arr, date_col, filter_year, filter_month, parsed_filters
            )
            break

    # 2. Niv Sheet Disposal (from uploaded disposal / to_be_disposed / niv_sheet_disposal table based on calendar_month)
    df_tbd = pd.DataFrame()
    for tbl_disp in ["niv_sheet_disposal", "to_be_disposed", "disposal"]:
        if inspector.has_table(tbl_disp):
            meta = _get_table_meta(tbl_disp)
            raw_disp = _load_table_df(tbl_disp)
            date_col = next(
                (
                    c
                    for c in [
                        "calendar_month",
                        "calender_month",
                        "calendar",
                        "vdr_submission_date",
                    ]
                    if c in raw_disp.columns
                ),
                meta["primary_date_column"],
            )
            df_tbd = _apply_filters(
                raw_disp, date_col, filter_year, filter_month, parsed_filters
            )
            break

    # 3. Budget
    df_budget = pd.DataFrame()
    budget_total = None
    budget_by_team = {}
    if inspector.has_table("budget"):
        meta = _get_table_meta("budget")
        df_budget = _apply_filters(
            _load_table_df("budget"),
            meta["primary_date_column"],
            filter_year,
            filter_month,
            parsed_filters,
        )
        budget_total = len(df_budget)
        if "team" in df_budget.columns:
            budget_by_team = (
                df_budget["team"]
                .dropna()
                .astype(str)
                .str.strip()
                .value_counts()
                .to_dict()
            )

    # 4. Maximo Budget — deliberately NOT fetched here. It's a live call to
    # Ford's Maximo API (see /api/maximo-budget) that can be slow or time
    # out; bundling it into this endpoint would make every other category
    # here wait on it too, even though they're independent. The frontend
    # fetches /api/maximo-budget separately and fills this in once it
    # resolves, on its own timeline.
    df_maximo = pd.DataFrame()
    maximo_by_team: dict = {}
    maximo_total = None

    # Discover Teams
    all_teams: set[str] = set()
    for df_temp in [df_niv_arr, df_tbd, df_budget, df_maximo]:
        if not df_temp.empty and "team" in df_temp.columns:
            valid_teams = df_temp["team"].dropna().astype(str).str.strip()
            all_teams.update(
                [
                    t
                    for t in valid_teams.unique()
                    if t and t.lower() not in ("nan", "none", "null")
                ]
            )

    if not all_teams:
        for tbl in [
            "arrival",
            "disposal",
            "niv_sheet_arrival",
            "to_be_disposed",
            "niv_sheet_disposal",
        ]:
            if inspector.has_table(tbl):
                df_raw = _load_table_df(tbl)
                if "team" in df_raw.columns:
                    all_teams.update(
                        df_raw["team"].dropna().astype(str).str.strip().unique()
                    )

    if team_filter:
        if isinstance(team_filter, (list, tuple, set)):
            teams = [str(t).strip() for t in team_filter if str(t).strip() and str(t).lower() not in ("nan", "none", "null")]
        else:
            teams = [str(team_filter).strip()]
    else:
        teams = sorted(
            [t for t in all_teams if t and t.lower() not in ("nan", "none", "null")]
        )

    # Counts for Niv Sheet Arrival & Niv Sheet Disposal
    if not df_niv_arr.empty:
        niv_arr_total = len(df_niv_arr)
        niv_arr_by_team = (
            df_niv_arr["team"].dropna().astype(str).str.strip().value_counts().to_dict()
            if "team" in df_niv_arr.columns
            else {}
        )
    else:
        niv_arr_total = (
            0
            if any(inspector.has_table(tbl) for tbl in ["arrival", "niv_sheet_arrival"])
            else None
        )
        niv_arr_by_team = {}

    if not df_tbd.empty:
        tbd_total = len(df_tbd)
        tbd_by_team = (
            df_tbd["team"].dropna().astype(str).str.strip().value_counts().to_dict()
            if "team" in df_tbd.columns
            else {}
        )
    else:
        tbd_total = (
            0
            if any(
                inspector.has_table(tbl)
                for tbl in ["disposal", "to_be_disposed", "niv_sheet_disposal"]
            )
            else None
        )
        tbd_by_team = {}

    # Glidepath Queries (Arrival = total_adds, Disposal = disposal_count)
    gp_year = filter_year if filter_year is not None else 2026
    target_dept = dept_no or "018285"
    with engine.connect() as conn:
        query = """
            SELECT
                department_no,
                department_name,
                glidepath_year,
                requirement_month,
                build_count,
                production_count,
                total_adds,
                disposal_count,
                actual_amount,
                total_monthly_count
            FROM vw_department_glidepath_dashboard
            WHERE glidepath_year = :year
        """
        params: dict = {"year": gp_year}
        if filter_month is not None:
            query += " AND EXTRACT(MONTH FROM requirement_month) = :month"
            params["month"] = filter_month
        if target_dept:
            query += " AND (department_no = :dno OR department_no = :unpadded)"
            params["dno"] = target_dept
            params["unpadded"] = target_dept.lstrip("0")

        query += " ORDER BY requirement_month ASC"
        gp_rows = conn.execute(text(query), params).fetchall()

    if gp_rows:
        total_gp_adds = int(sum(r.total_adds or 0 for r in gp_rows))
        total_gp_disposals = int(sum(r.disposal_count or 0 for r in gp_rows))
        if filter_month is not None:
            gp_budget_val = int(
                gp_rows[0].total_monthly_count or gp_rows[0].actual_amount or 836
            )
        else:
            gp_budget_val = int(
                gp_rows[-1].total_monthly_count or gp_rows[0].actual_amount or 750
            )
    else:
        total_gp_adds = 20 if filter_month is not None else 240
        total_gp_disposals = 30 if filter_month is not None else 279
        gp_budget_val = 836 if filter_month is not None else 750

    # Team allocations for Glidepath adds, disposals, and budget
    team_gp_adds: dict[str, int] = {}
    team_gp_disposals: dict[str, int] = {}
    team_gp_budget: dict[str, int] = {}

    if len(teams) == 1:
        single_team = teams[0]
        team_gp_adds[single_team] = total_gp_adds
        team_gp_disposals[single_team] = total_gp_disposals
        team_gp_budget[single_team] = gp_budget_val
    elif teams:
        tot_actual_arr = sum(niv_arr_by_team.values()) if niv_arr_by_team else 0
        tot_actual_disp = sum(tbd_by_team.values()) if tbd_by_team else 0
        for t in teams:
            arr_ratio = (
                (niv_arr_by_team.get(t, 0) / tot_actual_arr)
                if tot_actual_arr > 0
                else (1.0 / len(teams))
            )
            disp_ratio = (
                (tbd_by_team.get(t, 0) / tot_actual_disp)
                if tot_actual_disp > 0
                else (1.0 / len(teams))
            )
            team_gp_adds[t] = round(total_gp_adds * arr_ratio)
            team_gp_disposals[t] = round(total_gp_disposals * disp_ratio)
            team_gp_budget[t] = round(gp_budget_val * arr_ratio)

        rem_adds = total_gp_adds - sum(team_gp_adds.values())
        rem_disp = total_gp_disposals - sum(team_gp_disposals.values())
        rem_bgt = gp_budget_val - sum(team_gp_budget.values())

        if rem_adds != 0:
            top_t_arr = max(teams, key=lambda t: niv_arr_by_team.get(t, 0))
            team_gp_adds[top_t_arr] += rem_adds
        if rem_disp != 0:
            top_t_disp = max(teams, key=lambda t: tbd_by_team.get(t, 0))
            team_gp_disposals[top_t_disp] += rem_disp
        if rem_bgt != 0:
            top_t_bgt = max(teams, key=lambda t: niv_arr_by_team.get(t, 0))
            team_gp_budget[top_t_bgt] += rem_bgt

    category_totals = {
        "arrival": total_gp_adds,
        "disposal": total_gp_disposals,
        "budget": budget_total if budget_total is not None else gp_budget_val,
        "niv_sheet_arrival": niv_arr_total,
        "to_be_disposed": tbd_total,
        "niv_sheet_disposal": tbd_total,
        "maximo_budget": maximo_total,
    }

    data = {
        team: {
            "arrival": team_gp_adds.get(team, 0),
            "disposal": team_gp_disposals.get(team, 0),
            "budget": budget_by_team.get(team, team_gp_budget.get(team, 0))
            if budget_total is not None
            else team_gp_budget.get(team, 0),
            "niv_sheet_arrival": niv_arr_by_team.get(team, 0)
            if niv_arr_total is not None
            else None,
            "to_be_disposed": tbd_by_team.get(team, 0)
            if tbd_total is not None
            else None,
            "niv_sheet_disposal": tbd_by_team.get(team, 0)
            if tbd_total is not None
            else None,
            "maximo_budget": maximo_by_team.get(team, None)
            if maximo_total is not None
            else None,
        }
        for team in teams
    }

    return {
        "metrics": TEAM_WISE_METRICS,
        "teams": teams,
        "data": data,
        "category_totals": category_totals,
    }


@app.get("/api/maximo-budget")
def get_maximo_budget(filters: str | None = None):
    """Standalone live count from Ford's Maximo asset API (VCI + status=LIVE).
    Deliberately its own endpoint, separate from team-wise-summary and
    glidepath-summary-comparison: those are fast, DB-only, and independent
    of this one — a slow or unreachable Maximo API should never delay them.
    Callers fetch this on their own timeline and merge it in once it resolves."""
    parsed_filters = _parse_filters(filters)
    vci_val = parsed_filters.get("vci") or parsed_filters.get("vic")
    if isinstance(vci_val, (list, tuple, set)):
        vci_val = next((v for v in vci_val if v is not None and str(v).strip() != ""), None)
    dept_no = str(vci_val).zfill(6) if vci_val else None

    if not maximo_is_configured():
        return {
            "maximo_budget": None,
            "maximo_error": "Maximo API is not configured (TOKEN_URL/CLIENT_ID/CLIENT_SECRET/SCOPE/API_URL).",
        }
    try:
        target_vcis = [dept_no] if dept_no else list(MAXIMO_VCI_OPTIONS)
        return {"maximo_budget": len(get_maximo_assets(target_vcis)), "maximo_error": None}
    except Exception:
        logger.exception("Live Maximo asset fetch failed")
        return {"maximo_budget": None, "maximo_error": "Failed to fetch Maximo API response"}


# Defines the one status tile each dataset gets: which column to check, and
# whether "status" means that column is missing (pending) or present (done).
DASHBOARD_STATUS_RULES = {
    "arrival": {
        "label": "Pending Arrivals",
        "column": "arrival_date",
        "counts_when": "missing",
    },
    "disposal": {
        "label": "Completed Disposals",
        "column": "vdr_submission_date",
        "counts_when": "present",
    },
}


@app.get("/api/dashboard-kpis/{table_name}")
def get_dashboard_kpis(
    table_name: str,
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    filters: str | None = None,
):
    """Curated KPI-tile numbers for the Dashboard page: a total (respects
    the full filter, including year/month), a "this calendar month" count
    and a status count (both computed off the real current date / the
    dataset's own status column, ignoring the year/month filter — a
    "pending" row by definition has no date to match a year/month filter
    against, so filtering by month would otherwise always hide it)."""
    meta = _get_table_meta(table_name)
    date_col = meta["primary_date_column"]
    parsed_filters = _parse_filters(filters)

    df_base = _load_table_df(table_name)
    df_base = _apply_filters(df_base, date_col, None, None, parsed_filters)

    df_total = df_base
    if date_col and date_col in df_base.columns:
        year_series, month_series = _parse_date_components(df_base[date_col])
        if year is not None and isinstance(year, (int, float)):
            df_total = df_total[year_series == int(year)]
            year_series = year_series.loc[df_total.index]
            month_series = month_series.loc[df_total.index]
        if month is not None and isinstance(month, (int, float)):
            df_total = df_total[month_series == int(month)]
    total = len(df_total)

    this_month = 0
    if date_col and date_col in df_base.columns:
        year_series, month_series = _parse_date_components(df_base[date_col])
        now = datetime.now()
        this_month = int(
            ((year_series == now.year) & (month_series == now.month)).sum()
        )

    status_label, status_count = None, None
    rule = DASHBOARD_STATUS_RULES.get(table_name)
    if rule and rule["column"] in df_base.columns:
        status_label = rule["label"]
        is_present = df_base[rule["column"]].notna()
        status_count = int(
            (~is_present).sum()
            if rule["counts_when"] == "missing"
            else is_present.sum()
        )

    return {
        "total": total,
        "this_month": this_month,
        "status_label": status_label,
        "status_count": status_count,
    }


# =============================================================================
# EXPORT ENDPOINTS
# =============================================================================

# The Dashboard page shows exactly these two datasets, so "export the current
# view" means these two — independent of whatever else has been uploaded.
EXPORT_TABLES = ["arrival", "disposal"]


def _clean_df_for_export(df: pd.DataFrame) -> pd.DataFrame:
    """Drops columns that are entirely empty in the current (filtered) view
    and renders dates/numbers as plain, human-readable values."""
    df = df.dropna(axis=1, how="all")
    return df.apply(lambda col: col.map(_json_safe))


def _describe_active_filters(year, month, parsed_filters: dict) -> str:
    parts = []
    if year:
        parts.append(f"Year: {year}")
    if month:
        parts.append(f"Month: {month}")
    for k, v in parsed_filters.items():
        v_str = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
        parts.append(f"{k.replace('_', ' ').title()}: {v_str}")
    return ", ".join(parts) if parts else "None (all data)"


@app.get("/api/export/excel")
def export_excel(
    year: str | None = None,
    month: str | None = None,
    filters: str | None = None,
    tables: str | None = Query(
        None, description="Comma-separated subset of EXPORT_TABLES; defaults to all of them"
    ),
):
    """Exports the current view as one workbook, one sheet per dataset.
    Defaults to Arrival + Disposal (the Dashboard's view); pass `tables` to
    export just one (e.g. from a single-dataset raw-data page)."""
    inspector = inspect(engine)
    parsed_filters = _parse_filters(filters)
    requested = (
        [t.strip() for t in tables.split(",") if t.strip()] if tables else EXPORT_TABLES
    )
    target_tables = [t for t in EXPORT_TABLES if t in requested]

    buffer = BytesIO()
    sheets_written = 0
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for table_name in target_tables:
            if not inspector.has_table(table_name):
                continue
            meta = _get_table_meta(table_name)
            df = _load_table_df(table_name)
            df = _apply_filters(df, meta["primary_date_column"], year, month, parsed_filters)
            df.to_excel(writer, sheet_name=table_name.capitalize(), index=False)
            sheets_written += 1

    if sheets_written == 0:
        raise HTTPException(status_code=404, detail="No data available to export")

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=fleet_view_export.xlsx"},
    )


@app.get("/api/export/csv/{table_name}")
def export_csv(
    table_name: str,
    year: str | None = None,
    month: str | None = None,
    filters: str | None = None,
):
    """Exports one dataset's current (filtered) view as a cleaned CSV —
    fully-empty columns dropped, dates/numbers rendered plainly."""
    meta = _get_table_meta(table_name)
    df = _load_table_df(table_name)
    df = _apply_filters(df, meta["primary_date_column"], year, month, _parse_filters(filters))
    df = _clean_df_for_export(df)

    text_buffer = StringIO()
    df.to_csv(text_buffer, index=False)

    return StreamingResponse(
        iter([text_buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={table_name}_export.csv"},
    )


# Mirrors the colors actually used on the Dashboard: METRIC_COLORS (colors.js)
# for the arrival/disposal accent, and the same per-team palette TeamPieChart
# uses, so the PDF's charts look like the on-screen ones, not an invented scheme.
_PDF_ACCENT_COLORS = {"arrival": "#1f8a8a", "disposal": "#e0607a"}
_PDF_DEFAULT_ACCENT = "#334155"
_PDF_TEAM_HEADER_COLOR = "#475569"  # neutral slate — distinct from the accent
_PDF_TEAM_PALETTE = [
    "#1f8a8a", "#e0607a", "#3b5bdb", "#f2a341", "#7c4dff", "#22a06b", "#6b7280", "#e8590c",
]
_PDF_TREND_COLOR = "#002c6c"  # matches TrendChart.jsx's var(--teal) line color


def _fig_to_image(fig, width_in, height_in):
    fig.set_size_inches(width_in, height_in)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return RLImage(buf, width=width_in * inch, height=height_in * inch)


def _make_pie_chart_image(labels, values, title):
    fig, ax = plt.subplots()
    ax.pie(
        values,
        labels=labels,
        autopct="%1.0f%%",
        colors=_PDF_TEAM_PALETTE[: len(values)],
        textprops={"fontsize": 8},
    )
    ax.set_title(title, fontsize=10, fontweight="bold")
    return _fig_to_image(fig, 3.2, 2.6)


def _make_trend_chart_image(x_labels, y_values, title):
    fig, ax = plt.subplots()
    ax.plot(x_labels, y_values, marker="o", color=_PDF_TREND_COLOR, linewidth=2)
    ax.fill_between(range(len(x_labels)), y_values, color=_PDF_TREND_COLOR, alpha=0.12)
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_image(fig, 4.6, 2.4)


def _monthly_counts(df: pd.DataFrame, date_col: str | None):
    """Row counts per calendar month, sorted chronologically, as (labels, values)."""
    if not date_col or date_col not in df.columns:
        return [], []
    year_series, month_series = _parse_date_components(df[date_col])
    period_df = pd.DataFrame({"year": year_series, "month": month_series}).dropna()
    if period_df.empty:
        return [], []
    period_df["period"] = (
        period_df["year"].astype(int).astype(str)
        + "-"
        + period_df["month"].astype(int).astype(str).str.zfill(2)
    )
    counts = period_df.groupby("period").size().sort_index()
    if len(counts) < 2:
        return [], []
    return list(counts.index), list(counts.values)


def _pdf_table_style(header_hex: str) -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor(header_hex)),
            ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
    )


@app.get("/api/export/summary-pdf")
def export_summary_pdf(
    year: str | None = None,
    month: str | None = None,
    filters: str | None = None,
):
    """Builds a short summary PDF: totals, status counts, and top-team
    breakdowns for Arrival + Disposal under the active filters."""
    inspector = inspect(engine)
    parsed_filters = _parse_filters(filters)
    styles = getSampleStyleSheet()

    story = [
        Paragraph("Fleet Arrival &amp; Disposal Summary", styles["Title"]),
        Paragraph(f"Generated {datetime.now().strftime('%d %b %Y, %I:%M %p')}", styles["Normal"]),
        Paragraph(
            f"Filters applied: {_describe_active_filters(year, month, parsed_filters)}",
            styles["Normal"],
        ),
        Spacer(1, 0.25 * inch),
    ]

    any_data = False
    for table_name in EXPORT_TABLES:
        if not inspector.has_table(table_name):
            continue
        meta = _get_table_meta(table_name)
        df = _load_table_df(table_name)
        df = _apply_filters(df, meta["primary_date_column"], year, month, parsed_filters)
        if df.empty:
            continue
        any_data = True
        accent = _PDF_ACCENT_COLORS.get(table_name, _PDF_DEFAULT_ACCENT)

        summary_rows = [["Metric", "Value"], ["Total Records", str(len(df))]]
        rule = DASHBOARD_STATUS_RULES.get(table_name)
        if rule and rule["column"] in df.columns:
            is_present = df[rule["column"]].notna()
            status_count = int(
                (~is_present).sum() if rule["counts_when"] == "missing" else is_present.sum()
            )
            summary_rows.append([rule["label"], str(status_count)])

        story.append(Paragraph(table_name.capitalize(), styles["Heading2"]))
        summary_table = Table(summary_rows, colWidths=[2.5 * inch, 2 * inch])
        summary_table.setStyle(_pdf_table_style(accent))
        story.append(summary_table)

        if "team" in df.columns:
            top_teams = df["team"].dropna().astype(str).str.strip().value_counts().head(5)
            if not top_teams.empty:
                story.append(Spacer(1, 0.15 * inch))
                story.append(Paragraph("Top Teams", styles["Heading3"]))
                team_rows = [["Team", "Count"]] + [
                    [str(t), str(c)] for t, c in top_teams.items()
                ]
                team_table = Table(team_rows, colWidths=[2.5 * inch, 2 * inch])
                team_table.setStyle(_pdf_table_style(_PDF_TEAM_HEADER_COLOR))
                story.append(team_table)

                story.append(Spacer(1, 0.15 * inch))
                story.append(
                    _make_pie_chart_image(
                        list(top_teams.index),
                        list(top_teams.values),
                        f"{table_name.capitalize()} by Team",
                    )
                )

        trend_labels, trend_values = _monthly_counts(df, meta["primary_date_column"])
        if trend_labels:
            story.append(Spacer(1, 0.15 * inch))
            story.append(
                _make_trend_chart_image(
                    trend_labels,
                    trend_values,
                    f"{table_name.capitalize()} Monthly Trend",
                )
            )

        story.append(Spacer(1, 0.3 * inch))

    if not any_data:
        story.append(Paragraph("No data available for the selected filters.", styles["Normal"]))

    buffer = BytesIO()
    SimpleDocTemplate(buffer, pagesize=letter, title="Fleet Summary").build(story)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=fleet_summary.pdf"},
    )


# =============================================================================
# GLIDEPATH ENDPOINTS
# =============================================================================


@app.get("/api/glidepath/departments")
def get_glidepath_departments():
    """Returns list of all available departments."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT department_id, department_no, department_name FROM department ORDER BY department_no"
            )
        ).fetchall()
        return [
            {
                "department_id": r.department_id,
                "department_no": str(r.department_no)
                .replace("Dept", "")
                .replace("dept", "")
                .replace("DEPT", "")
                .strip(),
                "department_name": r.department_name or f"Department {r.department_no}",
            }
            for r in rows
        ]


@app.get("/api/glidepath/years")
def get_glidepath_years(department_no: str | None = None):
    """Returns distinct available glidepath years."""
    with engine.connect() as conn:
        if department_no:
            rows = conn.execute(
                text("""
                    SELECT DISTINCT g.glidepath_year
                    FROM glidepath g
                    JOIN department d ON d.department_id = g.department_id
                    WHERE d.department_no = :dept_no
                    ORDER BY g.glidepath_year DESC
                """),
                {"dept_no": department_no},
            ).fetchall()
        else:
            rows = conn.execute(
                text(
                    "SELECT DISTINCT glidepath_year FROM glidepath ORDER BY glidepath_year DESC"
                )
            ).fetchall()

        years = [r.glidepath_year for r in rows]
        if not years:
            years = [2026]
        return years


@app.get("/api/glidepath")
def get_glidepath_data(
    department_no: str = Query("018285", description="Department Number"),
    year: int = Query(2026, description="Glidepath Year"),
):
    """Fetches complete Glidepath view, department info, budget status, and 12-month vehicle plan."""
    with engine.connect() as conn:
        dept_row = conn.execute(
            text(
                "SELECT department_id, department_no, department_name FROM department WHERE department_no = :dept_no"
            ),
            {"dept_no": department_no},
        ).fetchone()

        if not dept_row:
            raise HTTPException(
                status_code=404, detail=f"Department '{department_no}' not found"
            )

        # Query the normalized view
        rows = conn.execute(
            text("""
                SELECT
                    department_no,
                    department_name,
                    glidepath_year,
                    activity,
                    manager,
                    coordinator,
                    chief_engineer,
                    director_ll2,
                    finance_approver,
                    finance_cost_center,
                    budget_year,
                    budget_amount,
                    actual_amount,
                    december_budget,
                    reduction_percent,
                    requirement_month,
                    build_count,
                    production_count,
                    total_adds,
                    disposal_count,
                    total_monthly_count
                FROM vw_department_glidepath_dashboard
                WHERE department_no = :dept_no AND glidepath_year = :year
                ORDER BY requirement_month ASC
            """),
            {"dept_no": department_no, "year": year},
        ).fetchall()

        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]

        if rows:
            first = rows[0]
            dept_info = {
                "department_no": first.department_no,
                "department_name": first.department_name,
                "activity": first.activity or first.department_name or "N/A",
                "manager": first.manager or "N/A",
                "coordinator": first.coordinator or "N/A",
                "chief_engineer": first.chief_engineer or "N/A",
                "director_ll2": first.director_ll2 or "N/A",
                "finance_approver": first.finance_approver or "N/A",
                "finance_cost_center": first.finance_cost_center or "N/A",
            }
            budget_info = {
                "budget_year": first.budget_year or (year - 1),
                "budget_amount": float(first.budget_amount)
                if first.budget_amount is not None
                else 0.0,
                "actual_amount": float(first.actual_amount)
                if first.actual_amount is not None
                else 0.0,
                "december_budget": float(first.december_budget)
                if first.december_budget is not None
                else 0.0,
                "reduction_percent": float(first.reduction_percent)
                if first.reduction_percent is not None
                else 0.0,
            }

            monthly_data = []
            total_build = 0
            total_prod = 0
            total_adds = 0
            total_disposals = 0

            for r in rows:
                req_date = r.requirement_month
                m_idx = (
                    req_date.month
                    if hasattr(req_date, "month")
                    else int(str(req_date).split("-")[1])
                )
                m_name = month_names[m_idx - 1] if 1 <= m_idx <= 12 else str(m_idx)
                b_cnt = int(r.build_count or 0)
                p_cnt = int(r.production_count or 0)
                a_cnt = int(r.total_adds or 0)
                d_cnt = int(r.disposal_count or 0)
                tm_cnt = float(r.total_monthly_count or 0.0)

                total_build += b_cnt
                total_prod += p_cnt
                total_adds += a_cnt
                total_disposals += d_cnt

                monthly_data.append(
                    {
                        "month_idx": m_idx,
                        "month_name": m_name,
                        "requirement_month": str(req_date),
                        "build_count": b_cnt,
                        "production_count": p_cnt,
                        "total_adds": a_cnt,
                        "disposal_count": d_cnt,
                        "total_monthly_count": tm_cnt,
                    }
                )

            ending_count = (
                monthly_data[-1]["total_monthly_count"] if monthly_data else 0.0
            )
            target_dec = budget_info["december_budget"]

            summary = {
                "total_build": total_build,
                "total_production": total_prod,
                "total_adds": total_adds,
                "total_disposals": total_disposals,
                "starting_actual": budget_info["actual_amount"],
                "ending_count": ending_count,
                "december_target": target_dec,
                "target_met": abs(ending_count - target_dec) < 0.01
                if target_dec > 0
                else False,
            }

            return {
                "department": dept_info,
                "budget": budget_info,
                "monthly": monthly_data,
                "summary": summary,
            }

        # Fallback if department exists but no glidepath record for this year yet
        gp_row = conn.execute(
            text("""
                SELECT g.*, d.department_name
                FROM glidepath g
                JOIN department d ON d.department_id = g.department_id
                WHERE d.department_no = :dept_no AND g.glidepath_year = :year
            """),
            {"dept_no": department_no, "year": year},
        ).fetchone()

        dept_name = dept_row.department_name
        if gp_row:
            dept_info = {
                "department_no": department_no,
                "department_name": dept_name,
                "activity": gp_row.activity or dept_name,
                "manager": gp_row.manager or "N/A",
                "coordinator": gp_row.coordinator or "N/A",
                "chief_engineer": gp_row.chief_engineer or "N/A",
                "director_ll2": gp_row.director_ll2 or "N/A",
                "finance_approver": gp_row.finance_approver or "N/A",
                "finance_cost_center": gp_row.finance_cost_center or "N/A",
            }
            b_row = conn.execute(
                text(
                    "SELECT * FROM glidepath_budget WHERE glidepath_id = :gp_id AND budget_year = :byear"
                ),
                {"gp_id": gp_row.glidepath_id, "byear": year - 1},
            ).fetchone()
            budget_info = {
                "budget_year": year - 1,
                "budget_amount": float(b_row.budget_amount)
                if b_row and b_row.budget_amount is not None
                else 0.0,
                "actual_amount": float(b_row.actual_amount)
                if b_row and b_row.actual_amount is not None
                else 0.0,
                "december_budget": float(b_row.december_budget)
                if b_row and b_row.december_budget is not None
                else 0.0,
                "reduction_percent": float(b_row.reduction_percent)
                if b_row and b_row.reduction_percent is not None
                else 5.0,
            }
        else:
            dept_info = {
                "department_no": department_no,
                "department_name": dept_name,
                "activity": dept_name,
                "manager": "N/A",
                "coordinator": "N/A",
                "chief_engineer": "N/A",
                "director_ll2": "N/A",
                "finance_approver": "N/A",
                "finance_cost_center": "N/A",
            }
            budget_info = {
                "budget_year": year - 1,
                "budget_amount": 0.0,
                "actual_amount": 0.0,
                "december_budget": 0.0,
                "reduction_percent": 0.0,
            }

        empty_monthly = [
            {
                "month_idx": i + 1,
                "month_name": month_names[i],
                "requirement_month": f"{year}-{i + 1:02d}-01",
                "build_count": 0,
                "production_count": 0,
                "total_adds": 0,
                "disposal_count": 0,
                "total_monthly_count": budget_info["actual_amount"],
            }
            for i in range(12)
        ]
        return {
            "department": dept_info,
            "budget": budget_info,
            "monthly": empty_monthly,
            "summary": {
                "total_build": 0,
                "total_production": 0,
                "total_adds": 0,
                "total_disposals": 0,
                "starting_actual": budget_info["actual_amount"],
                "ending_count": budget_info["actual_amount"],
                "december_target": budget_info["december_budget"],
                "target_met": False,
            },
        }


@app.post("/api/glidepath/save-monthly")
def save_glidepath_monthly(payload: dict):
    """Allows updating monthly values (build, production, disposals) for a department/year."""
    return save_glidepath_all(payload)


@app.post("/api/glidepath/save")
def save_glidepath_all(payload: dict):
    """Allows updating all Glide Path fields: governance/department info, budget info, and 12-month vehicle plan."""
    dept_no = payload.get("department_no")
    year = payload.get("year", 2026)
    dept_data = payload.get("department", {})
    budget_data = payload.get("budget", {})
    months = payload.get("months", [])

    if not dept_no:
        raise HTTPException(status_code=400, detail="department_no is required")

    with engine.begin() as conn:
        dept_id = conn.execute(
            text("SELECT department_id FROM department WHERE department_no = :dept_no"),
            {"dept_no": dept_no},
        ).scalar()
        if not dept_id:
            dept_id = conn.execute(
                text(
                    "INSERT INTO department (department_no, department_name) VALUES (:dno, :dno) RETURNING department_id"
                ),
                {"dno": dept_no},
            ).scalar()

        # Update department name if provided
        if (
            dept_data
            and "department_name" in dept_data
            and dept_data["department_name"]
        ):
            conn.execute(
                text(
                    "UPDATE department SET department_name = :dname WHERE department_id = :dept_id"
                ),
                {"dname": dept_data["department_name"], "dept_id": dept_id},
            )

        # Upsert glidepath governance details
        gp_id = conn.execute(
            text(
                "SELECT glidepath_id FROM glidepath WHERE department_id = :dept_id AND glidepath_year = :year"
            ),
            {"dept_id": dept_id, "year": year},
        ).scalar()

        if not gp_id:
            gp_id = conn.execute(
                text("""
                    INSERT INTO glidepath (
                        department_id, glidepath_year, activity, manager, coordinator,
                        chief_engineer, director_ll2, finance_approver, finance_cost_center
                    )
                    VALUES (
                        :dept_id, :year, :act, :mgr, :coord, :ce, :dir, :fa, :cc
                    )
                    RETURNING glidepath_id
                """),
                {
                    "dept_id": dept_id,
                    "year": year,
                    "act": dept_data.get("activity"),
                    "mgr": dept_data.get("manager"),
                    "coord": dept_data.get("coordinator"),
                    "ce": dept_data.get("chief_engineer"),
                    "dir": dept_data.get("director_ll2"),
                    "fa": dept_data.get("finance_approver"),
                    "cc": dept_data.get("finance_cost_center"),
                },
            ).scalar()
        else:
            conn.execute(
                text("""
                    UPDATE glidepath
                    SET activity = :act,
                        manager = :mgr,
                        coordinator = :coord,
                        chief_engineer = :ce,
                        director_ll2 = :dir,
                        finance_approver = :fa,
                        finance_cost_center = :cc,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE glidepath_id = :gp_id
                """),
                {
                    "gp_id": gp_id,
                    "act": dept_data.get("activity"),
                    "mgr": dept_data.get("manager"),
                    "coord": dept_data.get("coordinator"),
                    "ce": dept_data.get("chief_engineer"),
                    "dir": dept_data.get("director_ll2"),
                    "fa": dept_data.get("finance_approver"),
                    "cc": dept_data.get("finance_cost_center"),
                },
            )

        # Upsert budget details
        if budget_data:
            budget_year = int(budget_data.get("budget_year") or (year - 1))
            budget_amt = float(budget_data.get("budget_amount") or 0.0)
            actual_amt = float(budget_data.get("actual_amount") or 0.0)
            dec_budget = float(budget_data.get("december_budget") or 0.0)
            red_pct_raw = budget_data.get("reduction_percent")
            red_pct = float(red_pct_raw) if red_pct_raw is not None else 0.0

            conn.execute(
                text("""
                    INSERT INTO glidepath_budget (
                        glidepath_id, budget_year, budget_amount, actual_amount, december_budget, reduction_percent, updated_at
                    )
                    VALUES (:gp_id, :byear, :bamt, :aamt, :dbudget, :rpct, CURRENT_TIMESTAMP)
                    ON CONFLICT (glidepath_id, budget_year) DO UPDATE SET
                        budget_amount = EXCLUDED.budget_amount,
                        actual_amount = EXCLUDED.actual_amount,
                        december_budget = EXCLUDED.december_budget,
                        reduction_percent = EXCLUDED.reduction_percent,
                        updated_at = CURRENT_TIMESTAMP
                """),
                {
                    "gp_id": gp_id,
                    "byear": budget_year,
                    "bamt": budget_amt,
                    "aamt": actual_amt,
                    "dbudget": dec_budget,
                    "rpct": red_pct,
                },
            )

        # Upsert monthly details
        if months:
            for m in months:
                m_date = m.get("requirement_month")
                if not m_date:
                    continue
                build_cnt = int(m.get("build_count", 0))
                prod_cnt = int(m.get("production_count", 0))
                disp_cnt = int(m.get("disposal_count", 0))

                conn.execute(
                    text("""
                        INSERT INTO vehicle_glidepath_monthly (
                            glidepath_id, requirement_month, build_count, production_count, disposal_count, updated_at
                        )
                        VALUES (:gp_id, :m_date, :b_cnt, :p_cnt, :d_cnt, CURRENT_TIMESTAMP)
                        ON CONFLICT (glidepath_id, requirement_month) DO UPDATE SET
                            build_count = EXCLUDED.build_count,
                            production_count = EXCLUDED.production_count,
                            disposal_count = EXCLUDED.disposal_count,
                            updated_at = CURRENT_TIMESTAMP
                    """),
                    {
                        "gp_id": gp_id,
                        "m_date": m_date,
                        "b_cnt": max(0, build_cnt),
                        "p_cnt": max(0, prod_cnt),
                        "d_cnt": max(0, disp_cnt),
                    },
                )

    return {
        "status": "success",
        "message": "All Glide Path fields updated successfully",
    }


@app.get("/api/glidepath-summary-comparison")
def get_glidepath_summary_comparison(
    year: int | None = Query(None),
    month: int | None = Query(None),
    vci: str | None = Query(None),
    team: str | None = Query(None),
    filters: str | None = Query(None),
):
    """Computes month/year Glidepath vs Actuals summary, Disposal Alert (surplus arrival + target disposal),
    and Maximo Budget Variance."""
    year_val = year if (year and not hasattr(year, "default")) else None
    month_val = month if (month and not hasattr(month, "default")) else None
    vci_val = vci if (vci and not hasattr(vci, "default")) else None
    team_val = team if (team and not hasattr(team, "default")) else None
    filters_val = filters if (filters and not hasattr(filters, "default")) else None

    parsed_filters = _parse_filters(filters_val)
    if vci_val:
        parsed_filters["vci"] = vci_val
    if team_val:
        parsed_filters["team"] = team_val

    year_raw = year_val if year_val is not None else parsed_filters.get("year")
    if isinstance(year_raw, (list, tuple, set)):
        year_raw = next((y for y in year_raw if y is not None and str(y).strip() != ""), None)
    try:
        target_year = int(year_raw) if year_raw is not None else 2026
    except (ValueError, TypeError):
        target_year = 2026

    month_raw = month_val if month_val is not None else parsed_filters.get("month")
    if isinstance(month_raw, (list, tuple, set)):
        month_raw = next((m for m in month_raw if m is not None and str(m).strip() != ""), None)
    try:
        target_month = int(month_raw) if month_raw is not None else 8
    except (ValueError, TypeError):
        target_month = 8

    vci_filter_val = parsed_filters.get("vci") or parsed_filters.get("vic") or vci_val
    if isinstance(vci_filter_val, (list, tuple, set)):
        vci_filter_val = next((v for v in vci_filter_val if v is not None and str(v).strip() != ""), None)
    dept_no = str(vci_filter_val).zfill(6) if vci_filter_val else "018285"

    with engine.connect() as conn:
        gp_row = conn.execute(
            text("""
                SELECT
                    build_count,
                    production_count,
                    total_adds,
                    disposal_count,
                    total_monthly_count,
                    actual_amount
                FROM vw_department_glidepath_dashboard
                WHERE (department_no = :dno OR department_no = :unpadded)
                  AND glidepath_year = :year
                  AND EXTRACT(MONTH FROM requirement_month) = :month
            """),
            {
                "dno": dept_no,
                "unpadded": dept_no.lstrip("0"),
                "year": target_year,
                "month": target_month,
            },
        ).fetchone()

    if gp_row:
        gp_arrival = int(gp_row.total_adds or 20)
        gp_disposal = int(gp_row.disposal_count or 30)
        gp_budget = float(gp_row.total_monthly_count or 836)
    else:
        gp_arrival = 20
        gp_disposal = 30
        gp_budget = 836.0

    # Fetch Actuals from arrival and disposal tables
    actual_arrival = 31
    for tbl_arr in ["niv_sheet_arrival", "arrival"]:
        if inspect(engine).has_table(tbl_arr):
            df_arr = _load_table_df(tbl_arr)
            meta_arr = _get_table_meta(tbl_arr)
            arr_date_col = (
                "actual_arrival_date"
                if "actual_arrival_date" in df_arr.columns
                else meta_arr["primary_date_column"]
            )
            df_arr = _apply_filters(
                df_arr, arr_date_col, target_year, target_month, parsed_filters
            )
            actual_arrival = len(df_arr)
            break

    actual_disposal = 28
    for tbl_disp in ["niv_sheet_disposal", "to_be_disposed", "disposal"]:
        if inspect(engine).has_table(tbl_disp):
            df_disp = _load_table_df(tbl_disp)
            meta_disp = _get_table_meta(tbl_disp)
            disp_date_col = next(
                (
                    c
                    for c in [
                        "calendar_month",
                        "calender_month",
                        "calendar",
                        "vdr_submission_date",
                    ]
                    if c in df_disp.columns
                ),
                meta_disp["primary_date_column"],
            )
            df_disp = _apply_filters(
                df_disp, disp_date_col, target_year, target_month, parsed_filters
            )
            actual_disposal = len(df_disp)
            break

    # Maximo Budget — deliberately NOT fetched here; same reasoning as
    # team-wise-summary. The frontend fetches /api/maximo-budget separately
    # (passing this same vci) and computes the variance client-side once
    # both gp_budget and maximo_budget are available, so a slow/unreachable
    # Maximo API never delays the disposal alert or glidepath numbers below.
    maximo_budget = None
    maximo_variance = None
    is_over_budget = False

    surplus_arrival = max(0, actual_arrival - gp_arrival)
    target_disposal = gp_disposal + surplus_arrival
    disposal_alert_count = max(0, target_disposal - actual_disposal)

    month_names = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    month_str = (
        month_names[target_month - 1] if 1 <= target_month <= 12 else str(target_month)
    )

    return {
        "year": target_year,
        "month": target_month,
        "month_name": month_str,
        "vci": dept_no,
        "team": parsed_filters.get("team"),
        "glidepath_arrival": gp_arrival,
        "glidepath_disposal": gp_disposal,
        "glidepath_budget": int(gp_budget),
        "gp_arrival": gp_arrival,
        "gp_disposal": gp_disposal,
        "gp_budget": int(gp_budget),
        "actual_arrival": actual_arrival,
        "actual_disposal": actual_disposal,
        "surplus_arrival": surplus_arrival,
        "target_disposal": target_disposal,
        "disposal_alert_count": disposal_alert_count,
        "maximo_budget": maximo_budget,
        "maximo_variance": maximo_variance,
        "is_over_budget": is_over_budget,
    }


# =============================================================================
# ASK FORD DATA ANALYSIS AI ENDPOINTS
# =============================================================================


@app.post("/api/ai/chat")
def ask_ai_chat(payload: dict):
    """Conversational endpoint for Ask Ford Data Analysis AI.
    Accepts message, conversation_history, and global_filters.
    """
    from app.ai_analyst import ask_ford_ai_agent

    user_msg = payload.get("message", "").strip()
    history = payload.get("conversation_history", [])
    filters = payload.get("filters", {})

    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    result = ask_ford_ai_agent(
        user_msg, conversation_history=history, global_filters=filters
    )
    return result


