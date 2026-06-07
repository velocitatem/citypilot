"""Per-run sandbox via Daytona.

The sandbox holds the RBAC-filtered ETL output AND runs all DB/report tools.
The host only orchestrates: it builds the ETL package, uploads it, and
forwards tool calls (which `agent_runner` exposes as LangChain tools that
proxy into the sandbox via `sandbox_lib.py`).
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams, Daytona
from langchain_daytona import DaytonaSandbox

log = logging.getLogger("worker.sandbox")

SANDBOX_ROOT = "/home/daytona/workspace"
SANDBOX_DATA_DIR = f"{SANDBOX_ROOT}/data"
SANDBOX_ARTIFACTS_DIR = f"{SANDBOX_ROOT}/artifacts"
SANDBOX_LIB_DIR = "/home/daytona/lib"
SANDBOX_SKILLS_DIR = "/home/daytona/skills"

_HOST_SKILLS_DIR = Path(__file__).resolve().parent.parent / "sandbox" / "skills"

_PIP_DEPS = "duckdb pandas weasyprint python-docx xlsxwriter plotly"
_APT_DEPS = "libpango-1.0-0 libpangoft2-1.0-0 libcairo2 fonts-dejavu"


@dataclass
class SandboxHandle:
    workspace: Path           # host-side ETL package dir
    sandbox: object           # daytona.Sandbox
    backend: DaytonaSandbox   # deepagents backend


def provision_sandbox(agent_run_id: str) -> SandboxHandle:
    import tempfile
    workspace = Path(tempfile.mkdtemp(prefix=f"run_{agent_run_id}_"))
    log.info("[sandbox] creating daytona sandbox agent_run_id=%s", agent_run_id)

    t0 = time.monotonic()
    client = Daytona()
    sandbox = client.create(
        CreateSandboxFromSnapshotParams(
            labels={"invertix.agent_run_id": agent_run_id},
            auto_delete_interval=3600,
        )
    )
    log.info("[sandbox] sandbox created sandbox_id=%s elapsed=%.1fs", getattr(sandbox, "id", "?"), time.monotonic() - t0)

    backend = DaytonaSandbox(sandbox=sandbox)

    log.info("[sandbox] creating directories")
    _exec(backend, f"mkdir -p {SANDBOX_DATA_DIR} {SANDBOX_ARTIFACTS_DIR} {SANDBOX_LIB_DIR} {SANDBOX_SKILLS_DIR}")

    uploads: list[tuple[str, bytes]] = []
    lib_src = Path(__file__).parent / "sandbox_lib.py"
    uploads.append((f"{SANDBOX_LIB_DIR}/sandbox_lib.py", lib_src.read_bytes()))
    for p in _HOST_SKILLS_DIR.glob("**/*"):
        if p.is_file():
            rel = p.relative_to(_HOST_SKILLS_DIR)
            uploads.append((f"{SANDBOX_SKILLS_DIR}/{rel}", p.read_bytes()))
    log.info("[sandbox] uploading %d files (lib + skills)", len(uploads))
    backend.upload_files(uploads)

    log.info("[sandbox] installing apt deps: %s", _APT_DEPS)
    t1 = time.monotonic()
    _exec(backend, f"sudo apt-get update -qq && sudo apt-get install -y --no-install-recommends {_APT_DEPS}")
    log.info("[sandbox] apt done elapsed=%.1fs", time.monotonic() - t1)

    log.info("[sandbox] installing pip deps: %s", _PIP_DEPS)
    t2 = time.monotonic()
    _exec(backend, f"pip install --quiet {_PIP_DEPS}")
    log.info("[sandbox] pip done elapsed=%.1fs", time.monotonic() - t2)

    _exec(backend, f"echo 'export PYTHONPATH={SANDBOX_LIB_DIR}' >> ~/.bashrc")

    _wrap_pythonpath(backend)
    log.info("[sandbox] provision complete total_elapsed=%.1fs agent_run_id=%s", time.monotonic() - t0, agent_run_id)
    return SandboxHandle(workspace=workspace, sandbox=sandbox, backend=backend)


def _exec(backend: DaytonaSandbox, cmd: str):
    """Run a command and log its output at DEBUG level."""
    result = backend.execute(cmd)
    output = getattr(result, "output", "") or ""
    exit_code = getattr(result, "exit_code", None)
    log.debug("[sandbox.exec] cmd=%r exit_code=%s output=%r", cmd[:120], exit_code, output[:300])
    if exit_code not in (None, 0):
        log.warning("[sandbox.exec] non-zero exit exit_code=%s cmd=%r output=%r", exit_code, cmd[:120], output[:500])
    return result


def _wrap_pythonpath(backend: DaytonaSandbox) -> None:
    """Make PYTHONPATH=SANDBOX_LIB_DIR the default for every execute() call."""
    orig = backend.execute

    def wrapped(cmd: str, *args, **kw):
        return orig(f"export PYTHONPATH={SANDBOX_LIB_DIR}:$PYTHONPATH && {cmd}", *args, **kw)

    backend.execute = wrapped  # type: ignore[assignment]


def _list_artifacts(backend: DaytonaSandbox) -> list[str]:
    res = backend.execute(
        f"find {SANDBOX_ARTIFACTS_DIR} -type f -printf '%p\\n' 2>/dev/null || true"
    )
    return [line for line in (res.output or "").splitlines() if line.strip()]


def destroy_sandbox(handle: SandboxHandle) -> None:
    """Pull artifacts back to the host, then tear the sandbox down."""
    try:
        paths = _list_artifacts(handle.backend)
        log.info("[sandbox] destroy: found %d artifact(s) to pull", len(paths))
        if paths:
            results = handle.backend.download_files(paths)
            saved = 0
            for r in results:
                if r.content is None:
                    log.warning("[sandbox] artifact download returned no content path=%s", r.path)
                    continue
                rel = Path(r.path).relative_to(SANDBOX_ARTIFACTS_DIR)
                out = handle.workspace / "artifacts" / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(r.content)
                saved += 1
                log.debug("[sandbox] saved artifact %s (%d bytes)", rel, len(r.content))
            log.info("[sandbox] pulled %d/%d artifacts to %s", saved, len(paths), handle.workspace)
    except Exception:
        log.exception("[sandbox] artifact pull failed")
    finally:
        log.info("[sandbox] deleting sandbox sandbox_id=%s", getattr(handle.sandbox, "id", "?"))
        try:
            handle.sandbox.delete()
            log.info("[sandbox] sandbox deleted")
        except Exception:
            log.exception("[sandbox] delete failed, attempting stop")
            try:
                handle.sandbox.stop()
            except Exception:
                log.exception("[sandbox] stop also failed")
