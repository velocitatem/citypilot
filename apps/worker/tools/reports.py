from langchain_core.tools import tool

from context import RunContext
from tools._invoke import call_sandbox


def report_tools(ctx: RunContext) -> list:
    @tool
    def create_pdf_report(filename: str, html: str) -> str:
        """Render HTML to PDF inside the sandbox under artifacts/pdf/."""
        return call_sandbox(ctx, "create_pdf_report", {"filename": filename, "html": html})

    @tool
    def create_docx_report(filename: str, sections: list[dict]) -> str:
        """Write a .docx inside the sandbox under artifacts/docx/. Sections: {heading, body, level}."""
        return call_sandbox(ctx, "create_docx_report", {"filename": filename, "sections": sections})

    @tool
    def create_xlsx_workbook(filename: str, sheets: dict[str, list[dict]]) -> str:
        """Write an .xlsx inside the sandbox under artifacts/xlsx/. `sheets` maps name -> rows."""
        return call_sandbox(ctx, "create_xlsx_workbook", {"filename": filename, "sheets": sheets})

    return [create_pdf_report, create_docx_report, create_xlsx_workbook]
