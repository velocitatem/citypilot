FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice \
        pandoc \
        fonts-dejavu \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /workspace

COPY apps/sandbox/pyproject.toml apps/sandbox/uv.loc[k] /opt/sandbox/
RUN cd /opt/sandbox && uv sync --no-install-project

COPY apps/sandbox/skills /workspace/skills
COPY apps/sandbox/tools  /workspace/tools

CMD ["python", "-c", "print('sandbox ready')"]
