"""create_pdf_report(markdown_or_html, name) — render to /workspace/artifacts/<name>.pdf.

Accepts JSON on stdin: { "name": "report", "content": "...", "format": "markdown" | "html" }.
Uses pandoc (markdown -> pdf via wkhtmltopdf) or weasyprint (html -> pdf).
"""
import json
import subprocess
import sys
from pathlib import Path

ARTIFACTS = Path("/workspace/artifacts")


def main() -> int:
    req = json.load(sys.stdin)
    name = req["name"].replace("/", "_")
    content = req["content"]
    fmt = req.get("format", "markdown")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / f"{name}.pdf"

    if fmt == "markdown":
        proc = subprocess.run(
            ["pandoc", "-f", "markdown", "-t", "html", "-o", "-"],
            input=content.encode(), capture_output=True, check=True,
        )
        html = proc.stdout.decode()
    else:
        html = content

    from weasyprint import HTML
    HTML(string=html).write_pdf(str(out))

    json.dump({"path": str(out), "filename": out.name}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
