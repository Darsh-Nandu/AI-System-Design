# Fintech Refund Agent - Safe Irreversible Action Design

**Domain:** Fintech, payments, any system with irreversible agentic actions  
**Interview question:** *"Design a customer support agent for a fintech that can initiate refunds. A user says 'refund everything from last month.' How do you handle this safely?"*  
**Industry reference:** Razorpay, Stripe, PayPal support automation

---

## The Core Problem

Refunds are irreversible. An agent that acts on ambiguous instructions, processes partial actions before a crash, or bypasses authorization checks causes real financial harm. Standard agent design doesn't account for:

1. Ambiguous bulk commands ("everything")
2. Mid-execution crashes leaving partial state
3. Varying evidence quality for different refund reasons
4. The magnitude of an action being independent of its confidence

---

## Architecture Overview

```
User: "Refund everything from last month"
  │
  ▼
[Ambiguity Resolution]
  │  never act on vague bulk commands
  │  resolve: query transaction DB for last 30 days
  │  surface structured confirmation to user:
  │  "Found 7 eligible transactions totalling ₹3,240. Confirm list?"
  ▼
[User confirms specific list]
  │
  ▼
[Velocity Check]
  │  is this user triggering unusual refund volume?
  │  rate limit: max N refund requests per 24h
  │  flag for human review if exceeded
  ▼
[Verifier LLM - Eligibility Gate]
  │  for each transaction:
  │    - was this purchased by this user? (check user_id in DB)
  │    - is it within refund window? (policy: 30 days)
  │    - has it already been refunded?
  │    - is the product/service type eligible?
  │  pass → move to evidence stage
  │  fail → reject, inform user with reason
  ▼
[Evidence Collection]
  │  user provides reason + supporting evidence
  ▼
[Evidence Grading LLM]
  │  classifies each claim:
  │
  │  HIGH CONFIDENCE (system-verifiable):
  │    - "delivered outside promised date" → check delivery DB
  │    - "duplicate charge" → check transaction DB
  │    - "item never arrived" → check logistics API
  │
  │  MEDIUM CONFIDENCE (document-verifiable):
  │    - receipt mismatch → OCR + compare
  │    - wrong item description → product DB check
  │
  │  LOW CONFIDENCE (subjective/media evidence):
  │    - video/photo evidence of defect
  │    - "product didn't work as described"
  │    → escalate to human agent
  │
  │  confidence_score: 0.0 - 1.0  (hyperparameter threshold: default 0.85)
  ▼
[Magnitude Check - independent of confidence]
  │  even if confidence = 1.0:
  │    refund_amount > ₹X → escalate to human
  │  (₹X is a configurable parameter set by risk team)
  ▼
[Idempotency Key Generation]
  │  key = hash(user_id + transaction_id + session_id)
  │  stored before execution begins
  ▼
[Execution - per transaction, not bulk]
  │  each refund fired individually with idempotency key
  │  payment API deduplicates on key - no double refunds on retry
  │  state checkpointed after each successful refund
  ▼
[Session Checkpoint]
  │  full state saved: which refunds completed, which pending
  │  if system crashes → resume from last checkpoint
  │  no transaction processed twice (idempotency key)
  ▼
Confirmation to user with itemized receipt
```

---

## Ambiguity Resolution - Before Any Action

"Refund everything from last month" must never directly trigger execution.

**Step 1:** Parse "last month" → query `transactions WHERE user_id = X AND date >= 30_days_ago AND refund_eligible = true`

**Step 2:** Surface structured list to user:
```
I found 7 transactions from the last 30 days totalling ₹3,240:

1. Zomato order #4821 - ₹340 - Jan 3
2. Myntra order #9923 - ₹1,200 - Jan 7
3. ...

Which of these would you like to refund, or shall I proceed with all 7?
```

**Step 3:** Wait for explicit confirmation on a specific list.

Rule: the more irreversible the action, the more explicit the confirmation must be.

---

## Confidence as a Hyperparameter

The evidence grading threshold is not hardcoded - it's a configurable parameter:

```
config {
  confidence_threshold: 0.85       // auto-approve above this
  human_escalation_threshold: 0.60 // auto-reject below this
  max_auto_refund_amount: 500      // INR, regardless of confidence
  max_refunds_per_24h: 5           // velocity limit
}
```

This allows the risk team to tighten or loosen thresholds based on fraud patterns without redeploying the agent.

---

## Idempotency - The Crash Safety Mechanism

Without idempotency, a crash mid-execution causes double refunds.

**How it works:**

1. Before execution begins, generate: `key = SHA256(user_id + txn_id + session_id)`
2. Store key in DB with status `pending`
3. Pass key to payment API with every refund call
4. Payment API: if key already processed → return success, don't charge again
5. On crash + retry: same key generated, payment API deduplicates

This is how Stripe, Razorpay, and every serious payment processor works. The key must be deterministic - same inputs always produce same key, so a retry generates the same key.

---

## Partial Failure Handling

Refunds are processed individually, not in bulk. After each successful refund, state is checkpointed:

```
SessionState {
  session_id: "abc123"
  user_id: "user_456"
  transactions_to_refund: [txn_1, txn_2, txn_3, txn_4, txn_5]
  completed: [txn_1, txn_2]
  pending: [txn_3, txn_4, txn_5]
  last_checkpoint: "2024-01-20T14:32:00Z"
}
```

If system goes offline after txn_2: resume from checkpoint, process txn_3 onward. txn_1 and txn_2 are not reprocessed.

---

## Human Escalation Routing

| Condition | Action |
|---|---|
| Evidence confidence < threshold | Route to human queue |
| Refund amount > max_auto_refund_amount | Route to human queue |
| User exceeded velocity limit | Flag + route to fraud team |
| System fully offline | Queue request, notify user of delay |
| Human unavailable (off-hours) | Queue with SLA: "response within 4 hours" |

Human agents see full context: user history, evidence submitted, confidence scores, which checks passed/failed.

---

## Audit Trail

Every action logged immutably:

```
AuditEntry {
  timestamp, session_id, user_id,
  action: "refund_initiated",
  transaction_id: "txn_3",
  amount: 340,
  confidence_score: 0.91,
  evidence_type: "delivery_date_verified",
  idempotency_key: "sha256:...",
  agent_version: "refund-agent-v2.1.0",
  decision: "auto_approved"
}
```

---

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| Ambiguity resolution before action | Prevents bulk mistakes | Extra round-trip with user |
| Per-transaction execution | Partial failure recovery | Slower than bulk API call |
| Confidence as hyperparameter | Risk team can tune without redeploy | Requires monitoring to set correctly |
| Idempotency keys | Crash-safe, no double refunds | Key storage + management overhead |
| Magnitude check independent of confidence | Catches high-value fraud even with good evidence | May frustrate legitimate high-value refunds |

---

## Tools Referenced

| Component | Tool |
|---|---|
| Idempotency + payments | Stripe API / Razorpay with idempotency keys |
| Session checkpointing | Redis (with persistence) |
| Audit log | Apache Kafka (infinite retention) or AWS QLDB |
| Agent orchestration | LangGraph (state machine with checkpointing) |
| Human queue | Internal ticketing system (Zendesk, Linear) |