"""list_available_tables() — return tables + their columns from the role-filtered DuckDB.

Output: JSON array of { "table": str, "columns": [ { "name": str, "type": str } ] }.
"""
import json
import sys
import duckdb

DB_PATH = "/workspace/data/agent.duckdb"


def main() -> int:
    con = duckdb.connect(DB_PATH, read_only=True)
    tables = [
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY 1"
        ).fetchall()
    ]
    out = []
    for t in tables:
        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [t],
        ).fetchall()
        out.append({"table": t, "columns": [{"name": c[0], "type": c[1]} for c in cols]})
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
