"""create_xlsx_workbook(dataframes, name) — write a multi-sheet .xlsx to /workspace/artifacts.

Stdin JSON: {
  "name": "workbook",
  "sheets": { "<sheet_name>": [ {col: val, ...}, ... ], ... }
}
"""
import json
import sys
from pathlib import Path

import pandas as pd

ARTIFACTS = Path("/workspace/artifacts")


def main() -> int:
    req = json.load(sys.stdin)
    name = req["name"].replace("/", "_")
    sheets: dict[str, list[dict]] = req["sheets"]
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / f"{name}.xlsx"

    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        for sheet_name, rows in sheets.items():
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name=sheet_name[:31] or "Sheet1", index=False)

    json.dump({"path": str(out), "filename": out.name}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
