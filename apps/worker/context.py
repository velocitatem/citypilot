from dataclasses import dataclass

from langchain_daytona import DaytonaSandbox


@dataclass
class RunContext:
    agent_run_id: str
    user_id: str
    company_id: str
    role: str
    backend: DaytonaSandbox
