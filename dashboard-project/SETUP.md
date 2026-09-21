# Setup Guide

How to get this running on a fresh machine. Written for Windows/PowerShell,
with notes for macOS/Linux where the commands differ.

## Prerequisites

- **Python 3.10+** (3.13 works fine — `requirements.txt` is pinned to
  versions that ship prebuilt wheels for it)
- **Node.js 18+** (for the frontend)
- **PostgreSQL** installed and running on your local machine (`localhost:5432`)

## 1. PostgreSQL Database Setup

1. Ensure your PostgreSQL service is running locally on port `5432`.
   - On Windows: check with `Get-Service -Name *postgres*` in PowerShell.

2. Create the database (e.g. `ford_database`):

```powershell
# Using psql:
& "C:\Program Files\PostgreSQL\<version>\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE ford_database;"
```
*(Or use pgAdmin / DBeaver / your preferred GUI tool to create `ford_database`)*

3. Configure your connection in `backend/.env`:
```env
DATABASE_URL=postgresql+psycopg2://postgres:<your-password>@localhost:5432/ford_database
```

## 2. Backend setup

```powershell
cd backend
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

The API is now at http://localhost:8000 (interactive docs at `/docs`).

> **PowerShell script execution blocked?** If `venv\Scripts\activate`
> errors with "running scripts is disabled", run:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (answer `Y`), then
> retry.

## 3. Frontend setup

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` requests to the backend on
port 8000 (see `frontend/vite.config.js`), so both servers need to be
running.

## 4. Load some data

Go to **Upload Data** in the sidebar and upload Excel files. **The table a
file lands in is decided by a keyword in its filename**, not its exact name
— this is what routes uploads to a fixed set of tables instead of creating a
new one per file:

| Filename contains | Goes to table       | Shown on Team Wise as |
|--------------------|---------------------|------------------------|
| `arrival`           | `arrival`            | Arrivals               |
| `disposal`           | `disposal`           | Disposal               |
| `maximo`             | `maximo_budget`      | Maximo_Budget          |
| `niv sheet arrival` / `niv_sheet_arrival` / `nivsheetarrival` | `niv_sheet_arrival` | Niv Sheet Arrival |
| `niv sheet disposal` / `to be disposed` / `tobedisposed` | `niv_sheet_disposal` / `to_be_disposed` | Niv Sheet Disposal |
| `budget` (and not `maximo`) | `budget`      | Budget                 |

Anything else falls back to a table named after the sanitized filename.

Sample files are in `sample-data/` (`Arrival.xlsx`, `Disposal.xlsx`).

**Re-uploading is safe**: each upload is compared row-by-row (across every
shared column) against what's already in that table, and only genuinely new
rows are appended. Uploading the exact same file twice adds nothing.

## How the app is put together

- **Backend**: FastAPI + pandas + SQLAlchemy (`backend/app/`). Column names,
  date columns, and dtypes are auto-detected at upload time — no schema
  config needed.
- **Frontend**: React (Vite) + Recharts (`frontend/src/`). Three pages:
  Dashboard (Arrival + Disposal, each with KPIs/pie/trend/breakdown),
  Team Wise (per-category totals, per-team breakdown, alerts), and Upload.
- **Universal filter bar** (Year/Month/Team/Region/VCI) sits above both the
  Dashboard and Team Wise pages and drives everything on both at once —
  options are merged from whichever datasets have those columns.

## Troubleshooting

- **Two backends fighting over port 8000**: only run one `uvicorn` process
  at a time. If you get stale-looking responses, check
  `Get-NetTCPConnection -LocalPort 8000` for more than one owning process.
- **`ModuleNotFoundError` after `pip install`**: make sure the venv is
  activated (`(venv)` should show in your prompt) before running `pip` or
  `uvicorn`.
- **Postgres connection refused**: confirm it's actually running —
  `Get-Service postgresql*` (Windows service) — and that `backend/.env`'s `DATABASE_URL` matches its user/password/port.

