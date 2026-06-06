"""create_docx_report(markdown, name) — render to /workspace/artifacts/<name>.docx via pandoc.

Stdin JSON: { "name": "report", "content": "<markdown>" }.
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
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / f"{name}.docx"

    subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "docx", "-o", str(out)],
        input=content.encode(), check=True,
    )

    json.dump({"path": str(out), "filename": out.name}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
