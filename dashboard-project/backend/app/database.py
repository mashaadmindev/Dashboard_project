import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/ford_database",
)


def create_database_if_not_exists(url: str):
    """Automatically creates the PostgreSQL database if it does not exist yet."""
    try:
        parsed = urlparse(url)
        db_name = parsed.path.lstrip("/")
        if not db_name or db_name == "postgres":
            return
        sys_url = url.rsplit("/", 1)[0] + "/postgres"
        sys_engine = create_engine(sys_url, isolation_level="AUTOCOMMIT")
        with sys_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": db_name}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        sys_engine.dispose()
    except Exception as e:
        # Fallback if connecting to postgres default db is restricted
        print(f"Database check/creation notice: {e}")


create_database_if_not_exists(DATABASE_URL)

# pool_pre_ping avoids stale-connection errors on a long-running local dev server
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

METADATA_TABLE = "_uploaded_tables"


def init_metadata_table():
    """One-time bootstrap of the bookkeeping table that tracks every dataset
    we've ingested — reads the current schema first and only creates or
    alters what's actually missing, rather than firing CREATE/ALTER on every
    startup and relying on the database to reject the ones that already exist."""
    inspector = inspect(engine)

    if not inspector.has_table(METADATA_TABLE):
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    CREATE TABLE {METADATA_TABLE} (
                        table_name TEXT PRIMARY KEY,
                        original_filename TEXT NOT NULL,
                        uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        row_count INTEGER NOT NULL,
                        columns_json TEXT NOT NULL,
                        primary_date_column TEXT
                    )
                    """
                )
            )
        return

    # Table already exists from a previous run — only add columns it's
    # actually missing (e.g. an older database created before this column
    # existed), instead of blindly re-running ALTER TABLE.
    existing_columns = {c["name"] for c in inspector.get_columns(METADATA_TABLE)}
    if "primary_date_column" not in existing_columns:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"ALTER TABLE {METADATA_TABLE} ADD COLUMN primary_date_column TEXT"
                )
            )

    # Ensure preferred operational primary date columns (e.g. calendar_month) are properly mapped
    with engine.begin() as conn:
        for tbl in inspector.get_table_names():
            if tbl.startswith("_") or tbl in [
                "department",
                "glidepath",
                "glidepath_budget",
                "vehicle_glidepath_monthly",
            ]:
                continue
            cols = {c["name"] for c in inspector.get_columns(tbl)}
            preferred = next(
                (
                    p
                    for p in ["calendar_month", "calender_month", "actual_arrival_date"]
                    if p in cols
                ),
                None,
            )
            if preferred:
                conn.execute(
                    text(
                        f"UPDATE {METADATA_TABLE} SET primary_date_column = :pd WHERE table_name = :t"
                    ),
                    {"pd": preferred, "t": tbl},
                )


def init_glidepath_tables():
    """Bootstrap the Glidepath normalized tables, dashboard view, and default seed data."""
    schema_sql = """
    CREATE TABLE IF NOT EXISTS department (
        department_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        department_no VARCHAR(20) NOT NULL UNIQUE,
        department_name VARCHAR(200),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS glidepath (
        glidepath_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        department_id BIGINT NOT NULL,
        glidepath_year INTEGER NOT NULL,
        activity VARCHAR(200),
        manager VARCHAR(150),
        coordinator VARCHAR(150),
        chief_engineer VARCHAR(150),
        director_ll2 VARCHAR(150),
        finance_approver VARCHAR(150),
        finance_cost_center VARCHAR(100),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP,
        CONSTRAINT fk_glidepath_department
            FOREIGN KEY (department_id)
            REFERENCES department(department_id)
            ON DELETE CASCADE,
        CONSTRAINT uq_department_glidepath_year
            UNIQUE (department_id, glidepath_year)
    );

    CREATE TABLE IF NOT EXISTS glidepath_budget (
        budget_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        glidepath_id BIGINT NOT NULL,
        budget_year INTEGER NOT NULL,
        budget_amount NUMERIC(15,2),
        actual_amount NUMERIC(15,2),
        december_budget NUMERIC(15,2),
        reduction_percent NUMERIC(5,2) DEFAULT 5.00,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP,
        CONSTRAINT fk_budget_glidepath
            FOREIGN KEY (glidepath_id)
            REFERENCES glidepath(glidepath_id)
            ON DELETE CASCADE,
        CONSTRAINT uq_glidepath_budget_year
            UNIQUE (glidepath_id, budget_year)
    );

    CREATE TABLE IF NOT EXISTS vehicle_glidepath_monthly (
        monthly_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        glidepath_id BIGINT NOT NULL,
        requirement_month DATE NOT NULL,
        build_count INTEGER NOT NULL DEFAULT 0,
        production_count INTEGER NOT NULL DEFAULT 0,
        disposal_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP,
        CONSTRAINT fk_monthly_glidepath
            FOREIGN KEY (glidepath_id)
            REFERENCES glidepath(glidepath_id)
            ON DELETE CASCADE,
        CONSTRAINT uq_glidepath_month
            UNIQUE (glidepath_id, requirement_month),
        CONSTRAINT chk_build_count
            CHECK (build_count >= 0),
        CONSTRAINT chk_production_count
            CHECK (production_count >= 0),
        CONSTRAINT chk_disposal_count
            CHECK (disposal_count >= 0)
    );

    CREATE OR REPLACE VIEW vw_department_glidepath_dashboard AS
    WITH monthly AS
    (
        SELECT
            d.department_id,
            d.department_no,
            d.department_name,
            g.glidepath_id,
            g.glidepath_year,
            g.activity,
            g.manager,
            g.coordinator,
            g.chief_engineer,
            g.director_ll2,
            g.finance_approver,
            g.finance_cost_center,
            b.budget_year,
            b.budget_amount,
            b.actual_amount,
            b.december_budget,
            b.reduction_percent,
            m.requirement_month,
            m.build_count,
            m.production_count,
            m.disposal_count,
            (m.build_count + m.production_count) AS total_adds,
            COALESCE(b.actual_amount, 0) +
            SUM(m.build_count + m.production_count - m.disposal_count) OVER (
                PARTITION BY g.glidepath_id
                ORDER BY m.requirement_month
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS total_monthly_count
        FROM department d
        INNER JOIN glidepath g ON g.department_id = d.department_id
        LEFT JOIN glidepath_budget b ON b.glidepath_id = g.glidepath_id AND b.budget_year = g.glidepath_year - 1
        INNER JOIN vehicle_glidepath_monthly m ON m.glidepath_id = g.glidepath_id
    )
    SELECT * FROM monthly;
    """

    with engine.begin() as conn:
        conn.execute(text(schema_sql))

        vcis = [
            "018309",
            "018092",
            "018434",
            "018118",
            "018253",
            "018276",
            "018312",
            "018117",
            "025411",
            "018285",
            "018114",
            "018342",
            "040223",
        ]

        disposals = [0, 5, 8, 10, 10, 25, 25, 30, 35, 42, 44, 45]

        for dept_no in vcis:
            dept_id = conn.execute(
                text("""
                    INSERT INTO department (department_no, department_name)
                    VALUES (:dno, :dno)
                    ON CONFLICT (department_no) DO UPDATE SET department_name = EXCLUDED.department_name
                    RETURNING department_id
                """),
                {"dno": dept_no},
            ).scalar()

            gp_id = conn.execute(
                text("""
                    INSERT INTO glidepath (
                        department_id, glidepath_year, activity, manager, coordinator,
                        chief_engineer, director_ll2, finance_approver, finance_cost_center
                    )
                    VALUES (
                        :dept_id, 2026, :dno, 'LLS', 'ABUSHAN',
                        'Kevin Wong', 'Matt Jones', 'RSHAIKH2', :cc
                    )
                    ON CONFLICT (department_id, glidepath_year) DO UPDATE SET activity = EXCLUDED.activity
                    RETURNING glidepath_id
                """),
                {"dept_id": dept_id, "dno": dept_no, "cc": f"{dept_no} / 63044030"},
            ).scalar()

            conn.execute(
                text("""
                    INSERT INTO glidepath_budget (
                        glidepath_id, budget_year, budget_amount, actual_amount, december_budget, reduction_percent
                    )
                    VALUES (:gp_id, 2025, 789, 789, 750, 5.00)
                    ON CONFLICT (glidepath_id, budget_year) DO NOTHING
                """),
                {"gp_id": gp_id},
            )

            for idx, d_cnt in enumerate(disposals):
                m_str = f"2026-{idx + 1:02d}-01"
                conn.execute(
                    text("""
                        INSERT INTO vehicle_glidepath_monthly (
                            glidepath_id, requirement_month, build_count, production_count, disposal_count
                        )
                        VALUES (:gp_id, :m_str, 20, 0, :d_cnt)
                        ON CONFLICT (glidepath_id, requirement_month) DO UPDATE SET disposal_count = EXCLUDED.disposal_count
                    """),
                    {"gp_id": gp_id, "m_str": m_str, "d_cnt": d_cnt},
                )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
