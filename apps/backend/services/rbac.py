from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection


class UserScope(BaseModel):
    user_id: str
    company_id: str
    role: str
    allowed_tables: list[str]


def resolve_user_scope(
    conn: Connection, user_id: str, company_id: str, role: str
) -> UserScope:
    """Look up role→table grants from the database.

    Source of truth is the `role_permissions` table (seeded by init.sql).
    """
    rows = conn.execute(
        text("SELECT table_name FROM role_permissions WHERE role = :role ORDER BY table_name"),
        {"role": role},
    ).all()
    return UserScope(
        user_id=user_id,
        company_id=company_id,
        role=role,
        allowed_tables=[r[0] for r in rows],
    )
