"""Role-filtered ETL: Postgres -> per-run DuckDB.

The RBAC source of truth is the `role_permissions` table in Postgres.
We never hardcode role->table mappings here. WE Do NOT want ANOTHER Replit Incident ;)
"""

import json
import os
from pathlib import Path

import duckdb
from sqlalchemy import create_engine, text


RUN_ROOT = Path(os.environ.get("SANDBOX_RUN_DIR", "/tmp/runs"))


def _raw_pg_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def _libpq_url() -> str:
    """DuckDB's POSTGRES extension wants a libpq URI (postgresql://...),
    not the SQLAlchemy postgresql+psycopg:// form."""
    url = _raw_pg_url()
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://"):]
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def _pg_engine():
    url = _raw_pg_url()
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return create_engine(url, future=True)


def _allowed_tables(conn, role: str) -> list[str]:
    rows = conn.execute(
        text("SELECT table_name FROM role_permissions WHERE role = :role ORDER BY table_name"),
        {"role": role},
    ).all()
    return [r[0] for r in rows]


def build_role_filtered_package(
    agent_run_id: str, user_id: str, company_id: str, role: str
) -> Path:
    """Export the subset of company data the role is allowed to see.

    Layout:
      {RUN_ROOT}/{agent_run_id}/
        data/agent.duckdb     (read-only inside sandbox)
        data/manifest.json    (allowed tables, row counts)
        artifacts/            (agent writes outputs here)
    """
    run_dir = RUN_ROOT / agent_run_id
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    duckdb_path = data_dir / "agent.duckdb"
    if duckdb_path.exists():
        duckdb_path.unlink()

    pg = _pg_engine()
    manifest = {
        "agent_run_id": agent_run_id,
        "user_id": user_id,
        "company_id": company_id,
        "role": role,
        "tables": {},
    }

    with pg.connect() as pg_conn, duckdb.connect(str(duckdb_path)) as ddb:
        tables = _allowed_tables(pg_conn, role)
        ddb.execute("INSTALL postgres; LOAD postgres;")
        ddb.execute(f"ATTACH '{_libpq_url()}' AS src (TYPE POSTGRES, READ_ONLY)")

        for tbl in tables:
            ddb.execute(
                f"CREATE TABLE {tbl} AS SELECT * FROM src.{tbl} WHERE company_id = ?",
                [company_id],
            )
            count = ddb.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            manifest["tables"][tbl] = count

        ddb.execute("DETACH src")

    (data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return run_dir
