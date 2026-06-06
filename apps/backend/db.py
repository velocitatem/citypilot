import os
import re
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_engine: Engine | None = None

_SCHEME_RE = re.compile(r"^postgresql(\+\w+)?://")


def _normalize_url(url: str) -> str:
    return _SCHEME_RE.sub("postgresql+psycopg://", url)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = _normalize_url(os.environ["DATABASE_URL"])
        _engine = create_engine(url, pool_pre_ping=True, future=True)
    return _engine
