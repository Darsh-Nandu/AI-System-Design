# News Aggregator Ingestion Pipeline

**Domain:** Real-time content aggregation, RAG systems with high-churn data  
**Interview question:** *"You run a news RAG system ingesting 50,000 articles/day. Three problems: duplicate articles from different sources, articles going stale within hours, and 2-hour ingestion lag. Design the pipeline to fix all three."*  
**Industry reference:** Google News, Apple News, Bloomberg Terminal, Reuters Connect

---

## The Three Problems

| Problem | Naive fix | Why it fails |
|---|---|---|
| Duplicates | Exact string match | CNN and BBC cover same story in completely different words |
| Staleness | Scheduled daily scan | Election result wrong for hours before scan runs |
| Ingestion lag | Bigger batch jobs | Batch has inherent latency - you're waiting to fill the batch |

All three require different architectural patterns, solved at different stages of the pipeline.

---

## Full Architecture

```
50,000 articles/day from RSS feeds, APIs, scrapers
  │
  ▼
[Streaming Ingestion - Kafka]
  │  articles published to Kafka topic immediately on arrival
  │  no batching at this stage - eliminates ingestion lag
  │  each article: { url, source, title, body, published_at, raw_tags }
  ▼
[Parallel Async Workers - fan-out]
  │  N workers consume from Kafka in parallel
  │  each worker handles: parse → clean → enrich → embed
  │  async I/O: workers don't block on DB writes
  ▼
[Enrichment Stage]
  │  NLP extraction: named entities, locations, people, organizations
  │  Topic classification: politics, finance, sports, breaking_news
  │  Volatility tagging: is this topic high-churn? (elections, wars, markets)
  │  Generate: article embedding, tag set, entity fingerprint
  ▼
[Deduplication Gate]
  │  Step 1: entity fingerprint pre-filter (cheap)
  │    → if no overlapping named entities → can't be same story → skip
  │  Step 2: cosine similarity on embedding (fast, ~1ms in Qdrant)
  │    → similarity > 0.97: exact duplicate → reject
  │    → similarity 0.85-0.97: same story, different angle → cluster
  │    → similarity < 0.85: different story → accept as new
  ▼
[Event-Driven Invalidation Trigger]
  │  on every new article accepted:
  │    → search DB for related articles (same entities, similar embedding)
  │    → for each match: evaluate if new article supersedes it
  │    → if superseded: mark existing article { stale: true, superseded_by: new_id }
  │    → do NOT delete - keep for historical context
  ▼
[Tiered Write - Hot / Warm / Cold]
  │
  ├── Volatile topics (elections, breaking news, markets, conflicts)
  │     → HOT partition: high-frequency invalidation, prioritized indexing
  │
  ├── General news (< 24h old)
  │     → WARM partition: standard indexing, daily staleness scan
  │
  └── Archived articles (> 7 days old)
        → COLD partition: compressed, low-priority, rarely queried
  │
  ▼
[Main Vector DB - write path]
  │  primary store, accepts all writes
  ▼
[Read Replica - read path]
  │  synced from main DB, serves all queries
  │  eventual consistency: ~seconds behind is acceptable for news
  │  CQRS pattern: writes and reads are completely separate workloads
  ▼
[Query Router]
  │  classifies incoming journalist query
  │  extracts entities → checks against volatile topics registry
  │  volatile match → route to HOT partition first
  │  no match → route to WARM/COLD partitions
  │  always filters: { stale: false } unless journalist explicitly
  │  requests historical view
  ▼
Results to journalist with source citations and freshness timestamps
```

---

## Problem 1 - Deduplication

### Why String Matching Fails

CNN: *"President signs landmark climate bill into law at White House ceremony"*  
BBC: *"US leader enacts sweeping environmental legislation in Washington"*

Zero word overlap. Same story. String matching misses it entirely.

### Two-Stage Semantic Dedup

**Stage 1 - Entity fingerprint pre-filter (cheap, ~0.1ms):**

Extract named entities from incoming article: people, organizations, locations, dates.
Build a fingerprint: `hash(sorted(entities))`.

If the incoming article shares no named entities with any existing article → it cannot be the same story → skip similarity check entirely. This eliminates ~80% of comparison candidates before any embedding math.

**Stage 2 - Cosine similarity (fast, ~1ms):**

Compare incoming article's embedding against existing articles that passed the entity filter.

```
Similarity thresholds:

> 0.97  → EXACT DUPLICATE
          Action: reject incoming article, discard
          Example: wire service article republished verbatim

0.85 - 0.97  → SAME STORY, DIFFERENT PERSPECTIVE
               Action: accept + cluster with existing articles
               Link both under a shared "story_id"
               Example: CNN and BBC covering same election result

< 0.85  → DIFFERENT STORY
          Action: accept as independent article
          No clustering needed
```

### Story Clustering (Not Deleting)

Articles in the 0.85-0.97 range are kept, not deleted. They're linked under a shared `story_id`:

```
Story {
  story_id: "us-election-result-2024-11-05"
  topic: "2024 US Presidential Election"
  articles: [
    { source: "Reuters", angle: "result announcement", published: "14:32" },
    { source: "CNN", angle: "reaction from supporters", published: "14:45" },
    { source: "BBC", angle: "international reaction", published: "15:01" }
  ]
  latest_article_id: "bbc-15:01"
  superseded_articles: []
}
```

When a journalist queries, the system returns the story cluster - "5 sources are covering this story" - not a single deduplicated article. More useful. No information lost.

---

## Problem 2 - Staleness & Real-Time Invalidation

### Why Scheduled Scans Fail

Scheduled daily scanner runs at midnight. Election result declared at 2pm. Article says "candidate X leading." Result confirmed at 6pm: candidate Y won. Journalists querying between 6pm and midnight get the wrong answer.

### Event-Driven Invalidation

Instead of a scheduled scan, every incoming article **triggers** a staleness check on existing articles:

```
New article arrives: "Candidate Y wins 2024 election - official result"

Trigger:
  1. Extract entities: { person: "Candidate Y", event: "2024 election" }
  2. Search DB: find articles with same entities, published in last 48h
  3. Found: "Candidate X leading in early counts" (published 4h ago)
  4. LLM or rule check: does new article supersede old article?
     → Yes: new article is a later development on same event
  5. Mark old article: { stale: true, superseded_by: "new_article_id", stale_at: "18:03" }
  6. Old article stays in DB for historical context
  7. Query filter: { stale: false } → journalist gets correct result immediately
```

Staleness is resolved within seconds of the new article arriving - not hours later when a scheduler runs.

### Hot Partition - High-Frequency Topics

For topics that change faster than event-driven invalidation can keep up with (live markets, live election counts, breaking disaster news):

A separate **hot partition** holds only the last N articles on volatile topics. A lightweight checker agent runs every 5 minutes on this partition only - not the entire DB. Cheap because the partition is small (only truly volatile content lives here).

```
Volatile topics registry (maintained by editorial team + auto-detected):
  - "2024 US Election" → hot until 2024-11-10
  - "Federal Reserve Rate Decision" → hot on announcement days only
  - "Gaza conflict" → hot indefinitely (ongoing)
  - "Apple earnings" → hot for 48h around earnings date
```

Topics graduate from hot → warm automatically after their volatility window closes.

### Stale Flag Strategy - Keep, Don't Delete

Stale articles are never deleted. They're filtered at query time by default but accessible when needed:

```
Default query: { stale: false }               → journalist gets current info
Historical query: { include_stale: true }     → journalist sees how story evolved
Debug query: { stale: true, story_id: X }    → see what was superseded and when
```

This lets journalists do historical research ("what did sources report in the first hour of the election night?") without polluting current queries with outdated information.

---

## Problem 3 - Ingestion Lag

### Why Batch Processing Creates Lag

Batch job runs every 2 hours → articles wait up to 2 hours before processing begins → not searchable for up to 2 hours after publication.

### Streaming with Kafka

Replace batch ingestion with a streaming pipeline:

```
Article published by source
  → RSS/API poller detects it (polling every 30s)
  → Published to Kafka topic immediately
  → Worker picks up within seconds
  → Parse → embed → dedup → write: ~3-5 seconds total
  → Article searchable: < 10 seconds after publication
```

Kafka gives additional benefits:
- **Backpressure handling**: if workers are overwhelmed, articles queue in Kafka without loss
- **Replay**: if a worker crashes mid-processing, article stays in Kafka and gets reprocessed
- **Fan-out**: multiple downstream systems (search index, notification service, analytics) consume the same Kafka topic independently

### Parallel Async Workers

Workers are stateless and horizontally scalable. Each handles one article end-to-end:

```
Worker pipeline (per article, async):
  parse()           → extract text, metadata
  clean()           → remove HTML, normalize encoding
  extract_entities() → NLP pipeline
  classify_topic()  → ML classifier
  embed()           → embedding model API call (async, non-blocking)
  dedup_check()     → vector similarity search
  write()           → upsert to vector DB
  trigger_invalidation() → event-driven staleness check
```

All I/O (embedding API, DB writes, similarity searches) is async - workers don't block waiting for responses. At 50,000 articles/day (~0.6 articles/second on average, higher during news cycles), 10-20 workers handle this comfortably with headroom for spikes.

### Read Replica - CQRS

Separate the write path from the read path entirely:

```
Write path: Kafka → Workers → Main DB (optimized for writes)
Read path:  Journalist queries → Read Replica (optimized for reads)

Sync lag: ~1-3 seconds (acceptable for news context)
```

This is the **CQRS pattern** (Command Query Responsibility Segregation). Read and write workloads have different characteristics - writes are bursty and sequential, reads are high-concurrency and latency-sensitive. Separating them lets each be optimized independently.

During a major news event (election night), write volume spikes 10x. Without CQRS, this write spike degrades query performance for journalists. With CQRS, the read replica is insulated from write pressure.

---

## Query Router - Connecting Both Partitions

The router classifies every incoming query before deciding which partition to search:

```
Journalist query: "Who won the 2024 US election?"

Router:
  1. Extract entities: { event: "2024 US election" }
  2. Check volatile topics registry: MATCH → hot topic
  3. Route to: HOT partition first
  4. Apply filter: { stale: false }
  5. If hot partition returns no results: fall back to WARM partition
  6. Return results with freshness timestamps so journalist knows
     when each article was published and when it was last verified
```

Freshness timestamps on every result are non-negotiable for journalists - they need to know if they're reading a 5-minute-old update or a 3-hour-old one.

---

## Daily Checker Agent - Background Validation

Even with event-driven invalidation, some staleness slips through:
- Stories that evolved slowly with no single "superseding" article
- Facts that became outdated due to events in a different topic (a company's stock price mentioned in an article about something else)
- Articles whose claims were quietly corrected by sources without a new article

The daily checker agent handles these edge cases:

```
Runs: once daily on WARM/COLD partitions, every 5 minutes on HOT partition

For each article:
  1. Check publication date - if > 7 days, move to COLD
  2. Extract factual claims that are time-sensitive (prices, positions, counts)
  3. Cross-reference against latest articles in same story cluster
  4. If contradiction found → mark stale, link to superseding article
  5. Log findings for editorial review
```

This is a safety net, not the primary freshness mechanism. Event-driven invalidation handles the fast cases; the checker handles slow drift.

---

## Full Problem → Solution Map

| Problem | Solution | Latency to fix |
|---|---|---|
| Exact duplicate articles | Entity fingerprint + cosine similarity > 0.97 → reject | At ingestion, ~1ms |
| Same story, different angle | Cluster under shared story_id | At ingestion, ~1ms |
| Article superseded by new development | Event-driven invalidation on every new article | Seconds after new article arrives |
| Volatile topic changing rapidly | Hot partition + 5-min checker agent | < 5 minutes |
| Slow factual drift | Daily checker agent | < 24 hours |
| 2-hour ingestion lag | Kafka streaming + async workers | < 10 seconds end-to-end |
| Query performance degraded by write spikes | CQRS read replica | Insulated from write load |

---

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| Cluster instead of delete duplicates | No information loss, richer context | More storage, query must merge cluster |
| Event-driven invalidation | Near-instant staleness resolution | Every ingestion triggers a search - extra load |
| Hot partition for volatile topics | Targeted high-frequency checks | Need to maintain volatile topics registry |
| Kafka streaming over batch | < 10s ingestion lag | More complex infrastructure than cron jobs |
| CQRS read replica | Read performance insulated from writes | Replication lag, two DBs to manage |
| Stale flag instead of delete | Historical queries possible | Stale articles accumulate, need archival strategy |

---

## Tools Referenced

| Component | Tool |
|---|---|
| Streaming ingestion | Apache Kafka |
| Async worker orchestration | Celery + Redis, or Kafka consumer groups |
| NLP entity extraction | spaCy, AWS Comprehend |
| Vector DB (main + replica) | Qdrant (supports named collections for partitions) |
| Embedding model | OpenAI text-embedding-3-small, or Cohere embed-v3 |
| Checker agent orchestration | Prefect, Apache Airflow |
| Query routing | Custom classifier (DistilBERT fine-tuned on topic volatility) |