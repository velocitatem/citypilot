"""Seed Postgres on backend startup if empty, using bundled data.zip."""
from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

from psycopg.errors import UndefinedTable
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db import get_engine

ZIP_PATH = Path(os.environ.get("SEED_DATA_ZIP", "/app/data.zip"))
EXTRACT_DIR = Path(os.environ.get("SEED_EXTRACT_DIR", "/tmp/seed_data"))
INIT_SQL_PATH = Path(os.environ.get("SEED_INIT_SQL", "/opt/seed/init.sql"))


def _init_sql_path() -> Path | None:
    candidates = [INIT_SQL_PATH]
    candidates.extend(parent / "scripts" / "init.sql" for parent in Path(__file__).resolve().parents)
    for path in candidates:
        if path.exists():
            return path
    return None


def _is_undefined_table(exc: Exception) -> bool:
    orig = getattr(exc, "orig", None)
    return isinstance(orig, UndefinedTable)


def _ensure_schema() -> None:
    init_sql = _init_sql_path()
    if init_sql is None:
        raise RuntimeError(
            f"companies table is missing and no init.sql was found at {INIT_SQL_PATH}"
        )

    sql = init_sql.read_text()
    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(sql)
        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()
    print(f"[seed] initialized schema from {init_sql}")


def seed_if_empty() -> None:
    force = os.environ.get("SEED_FORCE", "").lower() in ("1", "true", "yes")
    try:
        with get_engine().connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM companies")).scalar_one()
    except SQLAlchemyError as exc:
        if not _is_undefined_table(exc):
            raise
        print("[seed] companies table missing; initializing schema")
        _ensure_schema()
        with get_engine().connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM companies")).scalar_one()

    if count and not force:
        print(f"[seed] skip: {count} companies already present (set SEED_FORCE=1 to reseed)")
        return
    if force:
        print(f"[seed] force=1, reseeding over {count} companies")

    if not ZIP_PATH.exists():
        print(f"[seed] skip: {ZIP_PATH} not found")
        return

    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH) as zf:
        zf.extractall(EXTRACT_DIR)

    os.environ["SEED_DATA_DIR"] = str(EXTRACT_DIR)
    sys.path.insert(0, os.environ.get("SEED_MODULE_DIR", "/opt/seed"))
    import seed as seed_module
    seed_module.DATA = EXTRACT_DIR
    seed_module.main()
    print("[seed] done")
