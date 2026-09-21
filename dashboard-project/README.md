# Excel → Postgres → Dashboard

Upload two Excel files, load them into PostgreSQL, and explore them as a dashboard
(KPIs, trend chart, ad-hoc breakdown chart, raw data table). Works with **any**
Excel schema — columns are detected automatically at upload time, so you don't need
to configure anything up front.

## Stack

- **Backend**: FastAPI + pandas + SQLAlchemy + psycopg2
- **Database**: PostgreSQL (Running locally on `localhost:5432`)
- **Frontend**: React (Vite) + Recharts + Axios

## 1. PostgreSQL Database Setup

Ensure PostgreSQL is installed and running on your local machine (`localhost:5432`).

Create a database named `ford_database` (or any database name of your choice):

```sql
CREATE DATABASE ford_database;
```

Update your connection string in `backend/.env` if your username, password, or port differs:
```env
DATABASE_URL=postgresql+psycopg2://postgres:your_password@localhost:5432/ford_database
```

## 2. Start the backend

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

The API is now at `http://localhost:8000` (docs at `http://localhost:8000/docs`).

## 3. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## How it works

1. **Upload** — drop your two `.xlsx` files in the browser. Each file is parsed
   with pandas, column names are cleaned up (lowercase, snake_case), and
   date-like text columns are auto-detected and converted.
2. **Load** — each file becomes its own Postgres table (named after the file),
   replacing any previous version on re-upload. A small `_uploaded_tables`
   metadata table tracks what's been loaded.
3. **Explore** — navigate the dashboard sections:
   - **Dashboard**: KPI cards, trend lines, and breakdown charts for arrivals & disposals.
   - **Team Wise**: Cross-category totals, team breakdowns, and alerts.
   - **Glide Path**: Complete department vehicle glide path (Governance, 2025 Budget & Actual, 2026 Monthly Build/Prod/Adds/Disposals matrix, and running fleet trajectory).
   - **Upload Data**: Seamless Excel uploads with automatic deduplication and ingestion.

## Your data

`sample-data/` contains the `Arrival.xlsx` and `Disposal.xlsx` files you shared —
vehicle fleet tracking data (arrivals with milestones/dates, disposals with
scrap/auction/transfer status). Upload both once the app is running and you'll
get:

- **Arrival** — trend of arrivals over time (using `Arrival Date`, which is
  more complete than `Expected Time of Delivery`), breakdown by `Milestone`,
  `Team`, or `Region`
- **Disposal** — trend of disposal submissions over time, breakdown by
  `Scrap/Auction/Transfer`, `VDR Status`, or `Location of Origin`

The breakdown chart defaults to **count of records** grouped by the
lowest-cardinality column (e.g. `Milestone` rather than `Tag` or `VIN`, which
are unique per row and useless to group by) — this fits tracking/operational
data much better than summing an arbitrary numeric column like `VCI` or
`Model Year`. You can still switch to sum/avg/min/max on a numeric column from
the dropdown if you want that.

## Notes / next steps

- This scaffold trusts uploaded files enough to load them directly — if you'll
  expose this beyond your own machine, add auth and tighten file validation.
- `to_sql(if_exists="replace")` means re-uploading a file overwrites that
  table. Switch to `"append"` in `backend/app/ingest.py` if you want to
  accumulate data across uploads instead.
- Column types are inferred by pandas/SQLAlchemy automatically; for very large
  files you may want to switch to chunked/streaming ingestion.
