# ── Base ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.5.10 /uv /usr/local/bin/uv

WORKDIR /app

# System deps for spaCy + lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Dependencies ──────────────────────────────────────────────────────────
FROM base AS deps

COPY pyproject.toml .
RUN uv pip install --system -e "." \
    && python -m spacy download en_core_web_sm \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# ── Source ────────────────────────────────────────────────────────────────
FROM deps AS source
COPY src/ src/

# ── Worker image ──────────────────────────────────────────────────────────
FROM source AS worker
EXPOSE 9100
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:9100/metrics | grep -q "news_articles_processed" || exit 1
CMD ["aggregator-worker"]

# ── API image ─────────────────────────────────────────────────────────────
FROM source AS api
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8000/health | grep -q "healthy" || exit 1
CMD ["aggregator-api"]
