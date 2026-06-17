# Fintech Refund Agent

**Domain:** Fintech, payments, any system with irreversible agentic actions
**Interview question:** *"Design a customer support agent for a fintech that can initiate refunds. A user says 'refund everything from last month.' How do you handle this safely?"*
**Industry reference:** Razorpay, Stripe, PayPal support automation

---

## The Core Problem

Refunds are irreversible. Standard agent design does not account for:

1. Ambiguous bulk commands ("everything from last month")
2. Mid-execution crashes leaving partial state
3. Varying evidence quality across refund reasons
4. Action magnitude being independent of confidence

---

## Agent Pipeline

```
User: "Refund everything from last month"
  |
  v
[Ambiguity Resolution]          Claude parses vague intent, queries DB,
  |                             returns structured list for user to confirm.
  v
[User confirms specific list]
  |
  v
[Velocity Check]                Redis rate-limit: max N refunds per 24h.
  |                             Exceeded -> flag for fraud team.
  v
[Eligibility Gate]              Per-transaction rules:
  |                             - owned by this user?
  |                             - within 30-day refund window?
  |                             - not already refunded?
  v
[Evidence Grading]              Claude classifies evidence:
  |                             HIGH   (system-verifiable) -> auto-approve if confidence >= 0.85
  |                             MEDIUM (document-verifiable) -> OCR + compare
  |                             LOW    (subjective) -> escalate to human
  v
[Magnitude Check]               Even if confidence = 1.0:
  |                             amount > threshold -> escalate to human.
  v
[Idempotency Key Generation]    key = SHA256(user_id + txn_id + session_id)
  |                             Stored before execution. Deterministic on retry.
  v
[Execution - per transaction]   Each refund fired individually with key.
  |                             Payment API deduplicates on key.
  |                             State checkpointed after each success.
  v
[Confirmation]                  Itemized receipt to user.
```

---

## Running Locally

### Prerequisites

- Docker + Docker Compose v2
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Anthropic API key (for Claude)

### Quick Start

```bash
cd Agents/fintech-refund-agent

# Copy and fill in your Anthropic API key
cp .env.example .env

# Start infrastructure
make up

# Install Python deps
make install

# Run migrations
make migrate

# Seed sample transactions
make seed

# Start the API
make api
```

Open http://localhost:8000/docs to interact with the agent.

### Services

| Service | URL |
|---|---|
| Refund Agent API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Grafana | http://localhost:3000 (admin/admin) |
| Prometheus | http://localhost:9090 |
| Kafka UI (Redpanda Console) | http://localhost:8080 |

---

## Configuration

All thresholds are configurable at runtime by the risk team:

```env
CONFIDENCE_THRESHOLD=0.85       # auto-approve above this
ESCALATION_THRESHOLD=0.60       # auto-reject below this, route to human
MAX_AUTO_REFUND_AMOUNT=500      # USD, regardless of confidence
MAX_REFUNDS_PER_24H=5           # velocity limit per user
REFUND_WINDOW_DAYS=30           # eligibility window
```

---

## System Design Deep-Dive

### Idempotency

`key = SHA256(user_id + txn_id + session_id)`

Stored before execution. On crash + retry, the same inputs produce the same key.
The payment API deduplicates: if key already processed, return success without charging again.
This is how Stripe, Razorpay, and every serious payment processor works.

### Session Checkpointing

```json
{
  "session_id": "abc123",
  "completed": ["txn_1", "txn_2"],
  "pending": ["txn_3", "txn_4"],
  "last_checkpoint": "2024-01-20T14:32:00Z"
}
```

Crash after txn_2: resume, process txn_3 onward. No double-processing.

### Escalation Conditions

| Condition | Action |
|---|---|
| confidence < 0.85 | Human queue |
| amount > threshold | Human queue |
| velocity limit exceeded | Fraud team flag |
| LOW confidence evidence | Human queue |

---

## Stack

| Component | Technology |
|---|---|
| Agent orchestration | LangGraph |
| LLM | Claude claude-sonnet-4-6 (Anthropic) |
| API | FastAPI + uvicorn |
| Session checkpoint | Redis |
| Velocity limiting | Redis (sliding window) |
| Persistence | PostgreSQL 16 + SQLAlchemy 2.0 async |
| Audit log | Apache Kafka (Redpanda) |
| Metrics | Prometheus + Grafana |
| CI | GitHub Actions |

---

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| Ambiguity resolution before action | Prevents bulk mistakes | Extra round-trip with user |
| Per-transaction execution | Partial failure recovery | Slower than bulk API call |
| Confidence as configurable threshold | Risk team can tune without redeploy | Requires monitoring to set correctly |
| Idempotency keys | Crash-safe, no double refunds | Key storage + management overhead |
| Magnitude check independent of confidence | Catches high-value fraud | May frustrate legitimate large refunds |
