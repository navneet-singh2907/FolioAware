FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN groupadd --system folioaware \
    && useradd --system --gid folioaware --home-dir /nonexistent folioaware

WORKDIR /app

COPY --from=builder --chown=folioaware:folioaware /app/.venv /app/.venv
COPY --from=builder --chown=folioaware:folioaware /app/src /app/src
COPY --chown=folioaware:folioaware examples /app/examples

USER folioaware

EXPOSE 8080

CMD ["uvicorn", "folioaware.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
