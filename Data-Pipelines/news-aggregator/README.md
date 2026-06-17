# News Aggregator Ingestion Pipeline

**Domain:** Real-time content aggregation, RAG systems with high-churn data
**Interview question:** *"You run a news RAG system ingesting 50,000 articles/day. Three problems: duplicate articles from different sources, articles going stale within hours, and 2-hour ingestion lag. Design the pipeline to fix all three."*
**Industry reference:** Google News, Apple News, Bloomberg Terminal, Reuters Connect

---

## Architecture

```
50,000 articles/day from RSS feeds, APIs, scrapers
  │
  ▼
[Streaming Ingestion - Kafka]
  │  articles published to Kafka topic immediately on arrival
  │  no batching at this stage - eliminates ingestion lag
  ▼
[Parallel Async Workers - fan-out]
  │  N workers consume from Kafka in parallel
  │  each worker handles: parse → clean → enrich → embed
  ▼
[Enrichment Stage]
  │  NLP extraction: named entities, locations, people, organizations
  │  Topic classification: politics, finance, sports, breaking_news
  │  Volatility tagging: is this topic high-churn? (elections, wars, markets)
  ▼
[Deduplication Gate]
  │  Step 1: entity fingerprint pre-filter (cheap)
  │    → if no overlapping named entities → skip
  │  Step 2: cosine similarity on embedding (fast, ~1ms in Qdrant)
  │    → similarity > 0.97: exact duplicate → reject
  │    → similarity 0.85-0.97: same story, different angle → cluster
  │    → similarity < 0.85: different story → accept as new
  ▼
[Event-Driven Invalidation Trigger]
  │  on every new article accepted:
  │    → search DB for related articles
  │    → mark superseded articles stale
  ▼
[Tiered Write - Hot / Warm / Cold]
  │
  ├── Volatile topics (elections, breaking news, markets)
  │     → HOT partition
  ├── General news (< 24h old)
  │     → WARM partition
  └── Archived articles (> 7 days old)
        → COLD partition
  ▼
[CQRS - Write → Main DB, Reads → Replica]
  ▼
[Query Router]
  │  volatile match → route to HOT partition first
  │  always filters: { stale: false }
  ▼
Results with source citations and freshness timestamps
```

---

## Running Locally

### Prerequisites
- Docker + Docker Compose v2
- Python 3.12+ (for development)
- [uv](https://docs.astral.sh/uv/) (package manager)

### Quick Start

```bash
# Clone and enter
git clone <repo>
cd Data-Pipelines/news-aggregator

# Start all infrastructure
make up

# Install Python deps
make install

# Run database migrations
make migrate

# Start the worker (in a second terminal)
make worker

# Start the API (in a third terminal)
make api

# Seed with sample RSS feeds
make seed
```

### Services

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Kafka UI | http://localhost:8080 |
| Grafana | http://localhost:3000 (admin/admin) |
| Prometheus | http://localhost:9090 |
| Qdrant Dashboard | http://localhost:6333/dashboard |

---

## System Design Deep-Dive

### Problem 1 — Deduplication

Two-stage semantic dedup:

**Stage 1 — Entity fingerprint (cheap, ~0.1ms):**
Extract named entities → `hash(sorted(entities))`. If no entity overlap, skip similarity check. Eliminates ~80% of candidates.

**Stage 2 — Cosine similarity (fast, ~1ms):**

| Similarity | Action |
|---|---|
| > 0.97 | Exact duplicate → reject |
| 0.85–0.97 | Same story, different angle → cluster under `story_id` |
| < 0.85 | Different story → accept |

### Problem 2 — Staleness

Event-driven: every accepted article triggers a search for related articles that may be superseded. Mark stale within seconds — not hours.

Hot partition for volatile topics (elections, markets): dedicated checker every 5 minutes.

### Problem 3 — Ingestion Lag

Kafka streaming: article is searchable < 10 seconds after publication. No batch windows.

CQRS: write path (Kafka → Workers → Main DB) is isolated from read path (Read Replica → Journalists). Write spikes don't degrade query performance.

---

## Stack

| Component | Technology |
|---|---|
| Streaming | Apache Kafka (Redpanda in dev) |
| Workers | Python 3.12 + aiokafka |
| NLP | spaCy (en_core_web_sm) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector DB | Qdrant |
| Cache | Redis |
| Persistence | PostgreSQL 16 + SQLAlchemy 2.0 async |
| API | FastAPI + uvicorn |
| Migrations | Alembic |
| Metrics | Prometheus + Grafana |
| CI | GitHub Actions |

---

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| Cluster instead of delete duplicates | No information loss | More storage |
| Event-driven invalidation | Near-instant staleness | Extra search per ingestion |
| Kafka over cron | < 10s lag | More infra complexity |
| CQRS read replica | Reads insulated from write spikes | Two DBs, replication lag |
| Stale flag instead of delete | Historical queries possible | Archival strategy needed |
