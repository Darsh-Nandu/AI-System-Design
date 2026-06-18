FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install uv


# ---- dependency layer (downloads embedding + reranker models) ----
FROM base AS deps

WORKDIR /app
COPY pyproject.toml .
RUN uv pip install --system --no-cache .

# Pre-download models so the container starts fast
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
RUN python -c "from sentence_transformers.cross_encoder import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"


# ---- source layer ----
FROM deps AS source

COPY src/ src/
RUN uv pip install --system --no-cache -e . --no-deps


# ---- api target ----
FROM source AS api

EXPOSE 8084
CMD ["uvicorn", "rag.api.main:app", "--host", "0.0.0.0", "--port", "8084"]
