# Image for Cloud Run. Build: docker build -t gym-server .
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --locked --no-dev

FROM python:3.13-slim
RUN useradd --system --uid 1000 app
WORKDIR /app
COPY --from=build --chown=app /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
# Cloud Run sets PORT (8080 by default).
CMD ["sh", "-c", "exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
