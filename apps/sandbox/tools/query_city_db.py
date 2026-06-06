"""query_city_db(sql) — run a read-only SQL query against the role-filtered DuckDB.

Usage (from agent_runner via `docker exec`):
    echo "<SQL>" | python /workspace/tools/query_city_db.py

Output: JSON array of row objects on stdout. Errors go to stderr with non-zero exit.
"""
import json
import sys
import duckdb

DB_PATH = "/workspace/data/agent.duckdb"
MAX_ROWS = 10_000


def main() -> int:
    sql = sys.stdin.read().strip()
    if not sql:
        print("empty query", file=sys.stderr)
        return 2
    con = duckdb.connect(DB_PATH, read_only=True)
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchmany(MAX_ROWS)
    out = [dict(zip(cols, r)) for r in rows]
    json.dump(out, sys.stdout, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
