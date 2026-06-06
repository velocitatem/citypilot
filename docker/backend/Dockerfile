FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY apps/backend/pyproject.toml apps/backend/uv.loc[k] ./
RUN uv sync --no-install-project

COPY apps/backend /app
COPY scripts/init.sql /opt/seed/init.sql
COPY scripts/seed.py /opt/seed/seed.py
COPY data.zip /opt/seed/data.zip

ENV SEED_DATA_ZIP=/opt/seed/data.zip \
    SEED_INIT_SQL=/opt/seed/init.sql \
    SEED_MODULE_DIR=/opt/seed

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
