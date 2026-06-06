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

    @tool
    def create_plotly_chart(filename: str, figure: dict) -> str:
        """Render an interactive Plotly chart and save it as artifacts/plots/<filename>.html.

        `figure` must be a Plotly figure dict with two keys:
          - "data": list of trace dicts. Each trace needs at minimum "type" and the
            axis/value fields for that type. Common types and their required fields:
              "bar"       → x (categories), y (values)
              "scatter"   → x, y; add mode="lines"|"markers"|"lines+markers"
              "pie"       → labels, values
              "heatmap"   → x, y, z (2-D list)
              "histogram" → x (raw values)
              "box"       → y (raw values), optional x for grouping
            Optional on every trace: name (legend label), marker (color/size dict).
          - "layout": dict controlling appearance. Useful keys:
              title (str or {text, font}), xaxis/yaxis ({title, type, tickformat}),
              barmode ("group"|"stack"), colorscale, legend, width, height.

        Example — grouped bar chart:
        {
          "data": [
            {"type": "bar", "name": "2024", "x": ["Jan","Feb","Mar"], "y": [10,14,9]},
            {"type": "bar", "name": "2025", "x": ["Jan","Feb","Mar"], "y": [12,11,15]}
          ],
          "layout": {"title": "Monthly Sales", "barmode": "group",
                     "xaxis": {"title": "Month"}, "yaxis": {"title": "Units"}}
        }

        Returns the sandbox path to the saved .html file.
        """
        return call_sandbox(ctx, "create_plotly_chart", {"filename": filename, "figure": figure})

    return [create_pdf_report, create_docx_report, create_xlsx_workbook, create_plotly_chart]
