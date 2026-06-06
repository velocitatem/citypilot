from langchain_core.tools import tool

from context import RunContext
from tools._invoke import call_sandbox


def db_tools(ctx: RunContext) -> list:
    @tool
    def list_tables() -> list[str]:
        """List tables in the run-local RBAC-filtered database (DuckDB, in sandbox)."""
        return call_sandbox(ctx, "list_tables", {})

    @tool
    def describe_table(table: str) -> list[dict]:
        """Return column name and type for a table."""
        return call_sandbox(ctx, "describe_table", {"table": table})

    @tool
    def query_db(sql: str) -> list[dict]:
        """Run a single read-only SELECT/WITH against the run-local DuckDB."""
        return call_sandbox(ctx, "query_db", {"sql": sql})

    return [list_tables, describe_table, query_db]
