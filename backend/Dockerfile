# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

RUN addgroup --system retailops \
    && adduser --system --ingroup retailops --home /nonexistent retailops

COPY --chown=retailops:retailops app ./app
COPY --chown=retailops:retailops alembic.ini ./
COPY --chown=retailops:retailops migrations ./migrations

USER retailops
EXPOSE 8000

CMD ["uvicorn", "--factory", "app.main:create_app"]
