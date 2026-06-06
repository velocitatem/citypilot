from dataclasses import dataclass

from langchain_daytona import DaytonaSandbox


@dataclass
class RunContext:
    agent_run_id: str
    backend: DaytonaSandbox
