import io
import json
import re

import pandas as pd
from sqlalchemy import inspect, text

from app.database import METADATA_TABLE, engine

# Uploaded files are routed to a fixed table by filename keyword, rather than
# always deriving the table name from the exact filename, so "Arrival_Sept.xlsx"
# and "arrival (2).xlsx" both land in the same "arrival" table as the original.
# Order matters: more specific keywords are checked first so e.g. a
# "Maximo_Budget.xlsx" upload matches "maximo" before the generic "budget",
# and "Niv Sheet Arrival.xlsx" matches "nivsheetarrival" before "arrival".
FIXED_TABLE_KEYWORDS = {
    "maximo": "maximo_budget",
    "nivsheetarrival": "niv_sheet_arrival",
    "nivsheetdisposal": "niv_sheet_disposal",
    "nivdisposal": "niv_sheet_disposal",
    "tobedisposed": "to_be_disposed",
    "budget": "budget",
    "disposal": "disposal",
    "arrival": "arrival",
}


def _normalize(text: str) -> str:
    """Lowercases and strips every non-alphanumeric character, so filenames
    that differ only by spaces/underscores/casing (e.g. "Niv Sheet Arrival",
    "niv_sheet_arrival", "NivSheetArrival") all match the same keyword."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def sanitize_identifier(name: str, fallback: str = "col") -> str:
    """Turns an arbitrary string into a safe, lowercase snake_case SQL identifier."""
    name = str(name).strip().lower()
    name = re.sub(r"[^\w]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        name = fallback
    if name[0].isdigit():
        name = f"_{name}"
    return name


def sanitize_table_name(filename: str) -> str:
    base = filename.rsplit(".", 1)[0]
    normalized = _normalize(base)
    for keyword, table_name in FIXED_TABLE_KEYWORDS.items():
        if keyword in normalized:
            return table_name
    return sanitize_identifier(base, fallback="dataset")


def dedupe_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for col in columns:
        if col not in seen:
            seen[col] = 0
            result.append(col)
        else:
            seen[col] += 1
            result.append(f"{col}_{seen[col]}")
    return result


NON_DATE_COLUMNS = {
    "model_year",
    "model_yr",
    "year",
    "yr",
    "vci",
    "vi",
    "vic",
    "vin",
    "milage",
    "mileage",
    "miles",
    "mileslip",
    "vehicle_tag",
    "vehicle_ta",
    "tag",
    "job",
    "trim",
    "milestone",
    "engine_type",
    "parking_location_rolo",
    "team",
    "vehicle_department",
    "organization",
    "orginization",
    "location",
    "region",
    "license_p",
    "completed",
    "de_prep_by_cds",
    "vehicle_status_comm",
    "vdr_status",
    "scrap_auction_transfer",
    "awaiting_shipper",
    "notes",
    "row",
    "id",
    "count",
    "budget",
    "actual",
    "budget_amount",
    "actual_amount",
}


def is_date_column_name(col_name: str) -> bool:
    col_clean = str(col_name).strip().lower()
    if col_clean in NON_DATE_COLUMNS:
        return False
    return any(
        k in col_clean
        for k in [
            "date",
            "submission",
            "delivery",
            "eta",
            "calendar",
            "future_scrap",
            "prep_pack_start",
        ]
    )


def coerce_date_series(series: pd.Series) -> pd.Series:
    """Robustly parses a pandas Series into pure dates, handling:
    1. Excel numeric serial day numbers (e.g. 46254 -> 2026-08-20)
    2. Standard date strings (e.g. '8/20/2026', '2026-08-20', '26-Aug')
    3. Existing Timestamp / datetime objects
    """
    # Try numeric conversion for Excel serial day numbers
    num = pd.to_numeric(series, errors="coerce")
    is_excel_serial = num.notna() & num.between(25000, 80000)

    dates_from_serial = pd.to_datetime(
        num.where(is_excel_serial), unit="D", origin="1899-12-30", errors="coerce"
    )

    # For non-numeric string values, convert with pandas to_datetime
    str_series = series.where(~is_excel_serial)
    dates_from_str = pd.to_datetime(str_series, errors="coerce", format="mixed")

    combined = dates_from_serial.combine_first(dates_from_str)
    return combined.dt.floor("D")


def read_excel_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0, engine="openpyxl")
    df.columns = dedupe_columns([sanitize_identifier(c) for c in df.columns])
    # Drop fully-empty rows/columns that openpyxl sometimes trails in.
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    for col in df.columns:
        if is_date_column_name(col):
            df[col] = coerce_date_series(df[col])
    return df


def pick_primary_date_column(df: pd.DataFrame) -> str | None:
    """Picks whichever date column has the most non-null values, prioritizing
    explicit primary operational fields like calendar_month and actual_arrival_date."""
    # Priority check for operational date columns
    for preferred in ["calendar_month", "calender_month", "actual_arrival_date"]:
        if preferred in df.columns and df[preferred].notna().any():
            return preferred

    date_cols = df.select_dtypes(include="datetime").columns.tolist()
    if not date_cols:
        # Check string date columns if any
        for col in df.columns:
            if is_date_column_name(col):
                date_cols.append(col)
    if not date_cols:
        return None
    return max(date_cols, key=lambda c: df[c].notna().sum())


def _row_signature(row: pd.Series) -> tuple:
    """A hashable, dtype-agnostic fingerprint of a row's values, so the same
    row read back from Postgres (e.g. int64 vs Python int, NaT vs None)
    still compares equal to the freshly-parsed Excel row."""
    return tuple("" if pd.isna(v) else str(v) for v in row)


def _dedupe_against_existing(new_df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """Drops rows from new_df that already exist (by full row content) in
    table_name, comparing only columns both sides share."""
    existing = pd.read_sql_table(table_name, engine)
    shared_cols = [c for c in existing.columns if c in new_df.columns]
    if not shared_cols:
        return new_df

    existing_sigs = set(existing[shared_cols].apply(_row_signature, axis=1))
    is_new = ~new_df[shared_cols].apply(_row_signature, axis=1).isin(existing_sigs)
    return new_df[is_new]


def load_dataframe_to_postgres(
    df: pd.DataFrame, table_name: str, original_filename: str
) -> dict:
    table_exists = inspect(engine).has_table(table_name)

    if table_exists:
        existing_cols_info = inspect(engine).get_columns(table_name)
        existing_col_names = [c["name"] for c in existing_cols_info]
        existing_col_set = set(existing_col_names)

        # Automatically alter table to add any new columns present in uploaded file
        new_cols_in_df = [c for c in df.columns if c not in existing_col_set]
        if new_cols_in_df:
            with engine.begin() as conn:
                for col in new_cols_in_df:
                    conn.execute(
                        text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col}" TEXT')
                    )
            existing_cols_info = inspect(engine).get_columns(table_name)
            existing_col_names = [c["name"] for c in existing_cols_info]

        rows_in_file = len(df)
        df_to_insert = _dedupe_against_existing(df, table_name)
        new_rows_added = len(df_to_insert)
        duplicate_rows_skipped = rows_in_file - new_rows_added

        if new_rows_added > 0:
            df_to_insert = df_to_insert.reindex(columns=existing_col_names)
            df_to_insert.to_sql(
                table_name,
                engine,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )
    else:
        df.to_sql(
            table_name,
            engine,
            if_exists="replace",
            index=False,
            method="multi",
            chunksize=1000,
        )
        new_rows_added = len(df)
        duplicate_rows_skipped = 0

    full_df = pd.read_sql_table(table_name, engine)
    columns_info = [
        {"name": col, "dtype": str(dtype)} for col, dtype in full_df.dtypes.items()
    ]
    primary_date_column = pick_primary_date_column(full_df)

    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                INSERT INTO {METADATA_TABLE}
                    (table_name, original_filename, row_count, columns_json, primary_date_column)
                VALUES (:table_name, :original_filename, :row_count, :columns_json, :primary_date_column)
                ON CONFLICT (table_name) DO UPDATE SET
                    original_filename = EXCLUDED.original_filename,
                    uploaded_at = CURRENT_TIMESTAMP,
                    row_count = EXCLUDED.row_count,
                    columns_json = EXCLUDED.columns_json,
                    primary_date_column = EXCLUDED.primary_date_column
                """
            ),
            {
                "table_name": table_name,
                "original_filename": original_filename,
                "row_count": len(full_df),
                "columns_json": json.dumps(columns_info),
                "primary_date_column": primary_date_column,
            },
        )

    return {
        "table_name": table_name,
        "row_count": len(full_df),
        "new_rows_added": new_rows_added,
        "duplicate_rows_skipped": duplicate_rows_skipped,
        "columns": columns_info,
        "primary_date_column": primary_date_column,
    }
