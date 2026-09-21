# Ford Vehicle Fleet & KPI Dashboard: Code Review & Walkthrough Guide

This document is prepared in **simple, clear English** to help you confidently explain the entire project, architecture, code structure, and design decisions during your code review with your manager or technical lead.

---

## 1. Executive Summary (The 30-Second Elevator Pitch)

> *"This project is an end-to-end Fleet KPI and Glide Path Analytics platform. It allows users to drop in operational Excel sheets (such as Vehicle Arrivals and Disposals), automatically validates, cleans, and stores them in PostgreSQL, and generates dynamic dashboards with KPIs, monthly trends, team-wise breakdowns, operational alerts, department vehicle glide path projections, and an AI-powered conversational analyst."*

---

## 2. High-Level Architecture

```mermaid
graph TD
    User["User / Manager"] -->|Uploads Excel / Interacts| UI["React + Vite Frontend"]
    
    subgraph Frontend ["Frontend Layer (React 18 + Recharts)"]
        UI --> Dashboard["Dashboard (KPIs, Trends, Breakdowns, Tables)"]
        UI --> TeamWise["Team Wise & Operational Alerts"]
        UI --> GlidePath["Glide Path (Budget & Monthly Fleet Projections)"]
        UI --> AIAnalystUI["Ask Ford AI Chat Interface"]
        UI --> UniversalFilter["Universal Filter Bar (Year, Month, Team, VCI)"]
    end
    
    UI -->|REST API Calls (Axios)| API["FastAPI Backend (Python)"]
    
    subgraph Backend ["Backend Layer (Python + FastAPI)"]
        API --> Ingest["Ingestion Engine (Pandas + Regex + Date Coercion)"]
        API --> CoreLogic["Aggregations, Trends & KPI Calculator"]
        API --> GlideEngine["Glide Path Governance & Calculations"]
        API --> AIAnalyst["AI Analyst (Gemini Tool Calling + SQL Queries)"]
    end
    
    Ingest -->|Clean Data & Deduplication| DB[(PostgreSQL Database)]
    CoreLogic -->|SQLAlchemy Queries| DB
    GlideEngine -->|Views & Tables| DB
    AIAnalyst -->|Dynamic SQL Inspections| DB
```

---

## 3. Technology Stack & Why We Chose Them

| Component | Technology | Why We Chose It |
| :--- | :--- | :--- |
| **Backend** | **Python 3.10+ / FastAPI** | Extremely fast asynchronous REST API, automatic OpenAPI/Swagger documentation (`/docs`), and native type hints with Pydantic. |
| **Data Processing** | **Pandas & NumPy** | Fast tabular data manipulation, dynamic column cleaning, and flexible aggregation. |
| **Database ORM** | **PostgreSQL + SQLAlchemy** | Reliable relational database with ACID compliance, connection pooling (`pool_pre_ping`), and complex multi-table SQL views. |
| **Frontend** | **React 18 + Vite** | Instant hot-reloading, modular component architecture, and responsive state management. |
| **Charts & Visuals** | **Recharts** | Declarative, smooth SVG charting library for interactive line charts, bar charts, and pie charts. |
| **AI Layer** | **Google Gemini LLM** | Natural language tool-calling to convert user questions into exact database queries and fleet summaries. |

---

## 4. Project Structure (File-by-File Walkthrough)

### Backend (`/dashboard-project/backend/app/`)

#### 1. `database.py` — Database Engine & Connection Lifecycle
- **What it does**: Establishes connection to PostgreSQL using SQLAlchemy.
- **Key Features**:
  - `create_database_if_not_exists()`: Automatically creates the `ford_database` in PostgreSQL if it doesn't already exist on the server.
  - `init_metadata_table()`: Sets up the `_uploaded_tables` bookkeeping table that tracks uploaded file metadata (upload time, row count, column schemas, primary date columns).
  - `init_glidepath_tables()`: Sets up the departmental budget, governance, and 12-month vehicle addition/disposal tables and views.

#### 2. `ingest.py` — Intelligent Excel Parsing & Deduplication
- **What it does**: Handles raw file uploads from users and transforms them into clean SQL tables.
- **Key Features**:
  - **Smart Date Coercion (`coerce_date_series`)**: Accurately parses multiple date formats, including Excel serial integers (e.g., `45230`), strings (`'2026-08-20'`, `'5-Aug'`), and timestamps without throwing format errors.
  - **Column Sanitization (`sanitize_identifier`)**: Converts messy Excel headers (with spaces, symbols, mixed casing) into clean PostgreSQL snake_case column names.
  - **Intelligent Deduplication (`_dedupe_against_existing`)**: Compares incoming row signatures against existing database rows. If a user re-uploads an updated sheet, only truly *new* records are appended, avoiding duplicate data.
  - **Auto-Schema Expansion**: If an uploaded sheet introduces new columns, it executes `ALTER TABLE ADD COLUMN` automatically.

#### 3. `main.py` — REST API Endpoints & Business Logic
- **What it does**: Exposes all REST endpoints consumed by the React UI.
- **Key Endpoints**:
  - `POST /api/upload`: Accepts Excel files and invokes the ingestion pipeline.
  - `GET /api/tables`: Returns all loaded datasets and their column statistics.
  - `GET /api/filters/{table}`: Returns available filter values (Years, Months, Teams, Regions, VCIs).
  - `GET /api/kpis/{table}`: Computes dataset KPIs (Total Rows, Active Milestones, Date Ranges).
  - `GET /api/trend/{table}`: Computes time-series month-by-month volume trends.
  - `GET /api/breakdown/{table}`: Dynamic grouping (e.g. by Milestone, Team, Status, or Scrap/Auction).
  - `GET /api/team-wise`: Cross-table analysis combining Arrivals and Disposals to show team workload and net balance.
  - `GET /api/alerts`: Scans data for operational issues (e.g., missing arrival dates, pending disposals, duplicate tags).
  - `GET /api/glidepath`: Delivers department governance, 2025 actuals/budgets, and 2026 monthly run-rate matrices.

#### 4. `ai_analyst.py` — Conversational Fleet AI
- **What it does**: Allows managers to ask natural language questions (e.g., *"What is the disposal trend for Team 3?"* or *"Show me Department 018285 glide path variance"*).
- **Key Features**:
  - Uses Function Calling / Tool Calling to query SQL database tables dynamically.
  - Generates clear narrative answers, bullet points, and data summaries.

---

### Frontend (`/dashboard-project/frontend/src/`)

#### 1. `App.jsx` — Main Application Shell & Navigation
- Manages top-level navigation: **Dashboard**, **Team Wise**, **Glide Path**, **Upload Data**, and **Ask Ford AI**.
- Coordinates `globalFilters` so when a manager filters by Year or Team, all dashboard views update simultaneously.

#### 2. `components/UniversalFilterBar.jsx` — Unified Filtering
- Dropdowns for **Year**, **Month**, **Team**, **Region**, and **VCI/VIN**.
- Syncs state globally to avoid re-filtering on every separate chart.

#### 3. `components/DashboardKpiRow.jsx` & `DatasetSection.jsx`
- Renders high-level summary cards (Total Vehicles, Active Teams, In-Progress Deliveries).
- Displays side-by-side Arrival & Disposal charts with switchable aggregations (Count, Sum, Avg).

#### 4. `components/TrendChart.jsx` & `ChartBuilder.jsx`
- Uses Recharts for interactive line and bar charts with hover tooltips and responsive layouts.

#### 5. `components/TeamWisePage.jsx` & `TeamWiseSection.jsx`
- Aggregates metrics by Team/Department to compare Arrivals vs. Disposals and net fleet inventory changes.

#### 6. `components/GlidePathPage.jsx`
- Renders the complete Department Vehicle Glide Path matrix.
- Shows Governance Approvers (Manager, Chief Engineer, Director LL2, Finance), 2025 Budget vs. Actual, and 12-month build/production/addition/disposal trajectories.

#### 7. `components/AlertsPanel.jsx`
- Proactively highlights operational warnings (e.g., records with missing dates, unassigned teams, or overdue disposal reviews).

#### 8. `components/AskFordAiPage.jsx`
- Interactive AI chat interface for executives to get quick answers without manually filtering tables.

---

## 5. End-to-End Data Flow (How Data Moves)

```
[1. User Uploads Excel (.xlsx)]
             │
             ▼
[2. backend/app/ingest.py reads file with openpyxl/pandas]
  • Sanitizes column headers (e.g., "Arrival Date" -> "arrival_date")
  • Parses date columns (handles serial numbers & strings)
  • Deduplicates rows against existing Postgres table
             │
             ▼
[3. Stored into PostgreSQL Database]
  • Data table created or appended: 'arrival', 'disposal'
  • Metadata table updated: '_uploaded_tables'
             │
             ▼
[4. User opens Dashboard / Selects Filters]
  • React UI calls /api/universal-filters, /api/kpis, /api/trend
  • FastAPI runs targeted SQL queries / Pandas aggregation
             │
             ▼
[5. Visualized in React UI]
  • Recharts displays trends, pie charts, and monthly matrices
  • Tables show paginated records with instant search
```

---

## 6. Key Engineering Highlights & Problem Solving

When your lead asks: *"What technical challenges did you solve?"*, you can highlight these:

1. **Flexible Schema Handling (No hardcoded rigid schemas)**:
   - Real-world Excel sheets often change column order or add new columns. The ingestion pipeline dynamically adapts, auto-creates columns in Postgres, and prevents ingestion crashes.
2. **Robust Excel Date Parsing**:
   - Excel represents dates in multiple ways: numeric serial days (e.g., `45230`), standard text (`2026-08-20`), or shortened text (`5-Aug`). The `coerce_date_series()` function handles all these formats automatically.
3. **Smart Deduplication**:
   - Re-uploading the same sheet or an updated sheet will not create duplicate records; the system compares row fingerprints and inserts only new records.
4. **Fast Performance with Connection Pooling**:
   - Uses SQLAlchemy `pool_pre_ping=True` and efficient SQL queries so dashboards render in milliseconds even with thousands of rows.
5. **Universal Global Filter State**:
   - Changing a filter (like `Team: Powertrain` or `Year: 2026`) immediately syncs across KPIs, Trend Lines, Team Breakdown, and Alerts simultaneously.

---

## 7. Manager / Lead Q&A Cheat Sheet (What They Might Ask & How to Answer)

### Q1: *"How does the system handle an Excel file with new or unexpected columns?"*
> **Answer**:  
> *"In `ingest.py`, we inspect the incoming columns against the existing database table. If new columns are detected, we dynamically issue an `ALTER TABLE ADD COLUMN` statement to expand the schema automatically before inserting the data. No manual database migrations are needed."*

### Q2: *"How do we prevent duplicate data when a user uploads the same Excel twice?"*
> **Answer**:  
> *"We generate a row signature (hash/fingerprint) of all values for each row in `_dedupe_against_existing()`. We query existing row signatures in Postgres and filter out any incoming rows that already exist. Only net-new rows are appended."*

### Q3: *"How does the Glide Path module calculate the vehicle trajectory?"*
> **Answer**:  
> *"It takes the starting budget/actual from 2025, and for each of the 12 months in 2026, it adds new vehicle builds/production additions (`total_adds`) and subtracts vehicle disposals (`disposal_count`) to compute the net running monthly fleet count."*

### Q4: *"How does the AI Analyst work and is it safe to use?"*
> **Answer**:  
> *"The AI Analyst uses structured tool-calling. Instead of giving the LLM direct unrestricted access, it calls predefined Python functions (`tool_get_glidepath`, `tool_get_table_summary`, etc.) that execute parameterized SQL queries and return the results back to the LLM to format the explanation. This keeps the database secure and grounded in actual data."*

### Q5: *"What would be the next steps to take this to production?"*
> **Answer**:  
> 1. *"Add User Authentication (SSO / OAuth2 with JWT tokens) for role-based access control."*  
> 2. *"Containerize the backend, frontend, and PostgreSQL with Docker & Docker Compose or Kubernetes."*  
> 3. *"Set up automated background ingestion via cloud storage buckets (e.g., S3/Azure Blob) or scheduled jobs."*

---

## 8. 5-Minute Code Review Script (What to Say Step-by-Step)

1. **Introduction (1 min)**:  
   *"Hi [Manager Name], today I'll walk you through our Vehicle Fleet & KPI Dashboard. The goal of this application is to automate fleet analytics — specifically tracking vehicle arrivals, disposals, team performance, budget governance, and glide path projections."*

2. **Architecture & Stack (1 min)**:  
   *"We built this with a FastAPI backend in Python, PostgreSQL for persistent storage, and React with Vite and Recharts on the frontend. We also integrated Google Gemini for an interactive AI fleet analyst."*

3. **Backend & Ingestion Walkthrough (1.5 min)**:  
   *"In the backend, `ingest.py` takes Excel files, sanitizes headers, parses varied date formats including Excel serial numbers, and deduplicates rows before writing to Postgres. `database.py` manages connection pooling and table initialization. `main.py` provides clean REST APIs for filtered KPIs, trends, breakdowns, and Glide Path matrices."*

4. **Frontend UI Walkthrough (1 min)**:  
   *"On the frontend, the UI is organized into 5 intuitive sections: Dashboard for KPIs and time-series trends, Team Wise for cross-department workload, Glide Path for annual vehicle addition/disposal trajectories, Upload Data for easy self-service ingestion, and Ask Ford AI for conversational queries. The Universal Filter Bar keeps all views in sync."*

5. **Conclusion & Q&A (30 sec)**:  
   *"Everything is modular, tested, and ready for deployment. I'm happy to dive deeper into any specific file or function you'd like to review!"*
