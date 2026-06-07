"""Host-side helper: invoke a sandbox_lib command and parse its JSON result."""

import json

from context import RunContext


def call_sandbox(ctx: RunContext, name: str, args: dict):
    payload = json.dumps(args).encode()
    try:
        ctx.backend.upload_files([("/tmp/args.json", payload)])
        res = ctx.backend.execute(f"python -m sandbox_lib {name}")
    except Exception as e:
        return f"[tool_error] sandbox unavailable ({type(e).__name__}): {e}"
    out = (res.output or "").strip()
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        return f"[tool_error] sandbox returned no JSON:\n{out}"
    if not parsed.get("ok"):
        return f"[tool_error] {parsed.get('error')}"
    return parsed["result"]
