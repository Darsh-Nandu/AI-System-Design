FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install uv


# ---- dependency layer ----
FROM base AS deps

WORKDIR /app
COPY pyproject.toml .
RUN uv pip install --system --no-cache ".[api]"


# ---- source layer ----
FROM deps AS source

COPY src/ src/
RUN uv pip install --system --no-cache -e . --no-deps


# ---- api target ----
FROM source AS api

EXPOSE 8080
CMD ["uvicorn", "loop_detector.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
