FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install uv

FROM base AS deps
WORKDIR /app
COPY pyproject.toml .
RUN uv pip install --system -e ".[dev]"

FROM deps AS models
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

FROM models AS source
COPY src/ ./src/

FROM source AS api
EXPOSE 8085
CMD ["python", "-m", "uvicorn", "medical_rag.api.main:app", "--host", "0.0.0.0", "--port", "8085"]
