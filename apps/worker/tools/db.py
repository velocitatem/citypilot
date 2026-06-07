from langchain_core.tools import tool

from context import RunContext
from tools._invoke import call_sandbox


def _tool_err(e: Exception) -> str:
    return f"[tool_error] {type(e).__name__}: {e}"


def db_tools(ctx: RunContext) -> list:
    @tool
    def list_tables() -> list[str]:
        """List tables in the run-local RBAC-filtered database (DuckDB, in sandbox)."""
        try:
            return call_sandbox(ctx, "list_tables", {})
        except Exception as e:
            return _tool_err(e)

    @tool
    def describe_table(table: str) -> list[dict]:
        """Return column name and type for a table."""
        try:
            return call_sandbox(ctx, "describe_table", {"table": table})
        except Exception as e:
            return _tool_err(e)

    @tool
    def query_db(sql: str) -> list[dict]:
        """Run a single read-only SELECT/WITH against the run-local DuckDB."""
        try:
            return call_sandbox(ctx, "query_db", {"sql": sql})
        except Exception as e:
            return _tool_err(e)

    @tool
    def load_data_as_table(table_name: str, rows: list[dict]) -> dict:
        """Load a list of records into the sandbox DuckDB as a queryable table.

        Use this to bring API results, weather data, news records, or any
        fetched dataset into DuckDB so they can be JOIN-ed with existing tables
        via query_db. The table is created fresh each call (DROP + CREATE).

        `table_name`: alphanumeric/underscore name (e.g. "weather_daily",
                      "air_quality_march", "news_sentiment").
        `rows`: list of dicts — all dicts must share the same keys (columns).

        Returns {"table": name, "rows": count, "columns": [...]}.

        Example workflow:
          1. Call get_weather_archive to get daily weather rows.
          2. Call load_data_as_table("weather_hk", weather_data["daily"] ...)
          3. Call query_db("SELECT ... FROM weather_hk JOIN hospital_admissions ...")
        """
        try:
            return call_sandbox(ctx, "load_data_as_table", {"table_name": table_name, "rows": rows})
        except Exception as e:
            return _tool_err(e)

    return [list_tables, describe_table, query_db, load_data_as_table]
