"""Per-run sandbox via Daytona.

The sandbox holds the RBAC-filtered ETL output AND runs all DB/report tools.
The host only orchestrates: it builds the ETL package, uploads it, and
forwards tool calls (which `agent_runner` exposes as LangChain tools that
proxy into the sandbox via `sandbox_lib.py`).
"""

from dataclasses import dataclass
from pathlib import Path

from daytona import CreateSandboxFromSnapshotParams, Daytona
from langchain_daytona import DaytonaSandbox


SANDBOX_ROOT = "/home/daytona/workspace"
SANDBOX_DATA_DIR = f"{SANDBOX_ROOT}/data"
SANDBOX_ARTIFACTS_DIR = f"{SANDBOX_ROOT}/artifacts"
SANDBOX_LIB_DIR = "/home/daytona/lib"
SANDBOX_SKILLS_DIR = "/home/daytona/skills"

_HOST_SKILLS_DIR = Path(__file__).resolve().parent.parent / "sandbox" / "skills"

_PIP_DEPS = "duckdb pandas weasyprint python-docx xlsxwriter"
_APT_DEPS = "libpango-1.0-0 libpangoft2-1.0-0 libcairo2 fonts-dejavu"


@dataclass
class SandboxHandle:
    workspace: Path           # host-side ETL package dir
    sandbox: object           # daytona.Sandbox
    backend: DaytonaSandbox   # deepagents backend


def provision_sandbox(agent_run_id: str, package_dir: Path) -> SandboxHandle:
    client = Daytona()
    sandbox = client.create(
        CreateSandboxFromSnapshotParams(
            labels={"invertix.agent_run_id": agent_run_id},
            auto_delete_interval=3600,
        )
    )
    backend = DaytonaSandbox(sandbox=sandbox)
    backend.execute(
        f"mkdir -p {SANDBOX_DATA_DIR} {SANDBOX_ARTIFACTS_DIR} {SANDBOX_LIB_DIR} {SANDBOX_SKILLS_DIR}"
    )

    # Upload ETL package + the in-sandbox tool runner + skill bundles.
    uploads: list[tuple[str, bytes]] = []
    for p in (package_dir / "data").glob("**/*"):
        if p.is_file():
            rel = p.relative_to(package_dir / "data")
            uploads.append((f"{SANDBOX_DATA_DIR}/{rel}", p.read_bytes()))
    lib_src = Path(__file__).parent / "sandbox_lib.py"
    uploads.append((f"{SANDBOX_LIB_DIR}/sandbox_lib.py", lib_src.read_bytes()))
    for p in _HOST_SKILLS_DIR.glob("**/*"):
        if p.is_file():
            rel = p.relative_to(_HOST_SKILLS_DIR)
            uploads.append((f"{SANDBOX_SKILLS_DIR}/{rel}", p.read_bytes()))
    backend.upload_files(uploads)

    # Install runtime deps. PYTHONPATH so `python -m sandbox_lib` works.
    backend.execute(
        f"sudo apt-get update -qq && sudo apt-get install -y --no-install-recommends {_APT_DEPS}"
    )
    backend.execute(f"pip install --quiet {_PIP_DEPS}")
    backend.execute(f"echo 'export PYTHONPATH={SANDBOX_LIB_DIR}' >> ~/.bashrc")

    # Wrap execute so every tool call sees PYTHONPATH (bashrc doesn't apply
    # to non-interactive shells).
    _wrap_pythonpath(backend)
    return SandboxHandle(workspace=package_dir, sandbox=sandbox, backend=backend)


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
        if paths:
            results = handle.backend.download_files(paths)
            for r in results:
                if r.content is None:
                    continue
                rel = Path(r.path).relative_to(SANDBOX_ARTIFACTS_DIR)
                out = handle.workspace / "artifacts" / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(r.content)
    finally:
        try:
            handle.sandbox.delete()
        except Exception:
            try:
                handle.sandbox.stop()
            except Exception:
                pass
