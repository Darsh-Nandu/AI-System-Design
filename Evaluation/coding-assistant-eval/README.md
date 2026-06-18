# Coding Assistant Eval Pipeline

> Model upgrade regression detection using 3 months of production logs.

**Domain:** AI coding assistants undergoing model upgrades
**Reference systems:** GitHub Copilot, Cursor, SWE-bench, HumanEval

---

## The Problem

Model upgrades are not guaranteed improvements. A new model might be better at code generation but worse at explanations. Without a systematic eval, teams ship blind and rely on "it feels better" from a handful of manual tests.

---

## Architecture

```
Production Logs (golden dataset)
  prompts + old model outputs + implicit feedback signals
  (copy rate, re-ask rate, edit distance -- already recorded)
          |
          v
  [Replay Pipeline]
  same prompts  ->  new model  ->  new outputs
  (old outputs already exist in logs, no re-run needed)
          |
          v
  [Cascaded Similarity Filter]
  cosine similarity(old, new) > 0.95  ->  "no change", skip judge (60-70% of entries)
  cosine similarity(old, new) < 0.95  ->  proceed to task-specific eval
          |
     _____|______________________
    |              |             |
    v              v             v
[Code Gen]    [Bug Fix]    [Explanation]
 Execution     SWE-bench    LLM-as-judge
 pass@k        style        bias-mitigated
    |              |             |
    v              v             v
  [Implicit Feedback Correlation]
  old output had high copy rate + new output diverges  ->  high-priority regression review
  old output had low copy rate + new output diverges   ->  potential improvement
          |
          v
     [Scorecard]
  per task type, per model version
  stored in eval registry
          |
          v
   Ship / Hold / Review
```

---

## Eval Layers

### 1. Similarity Pre-filter (cost control)
Cosine similarity between old and new output embeddings. Similarity > 0.95 skips the judge, typically eliminating 60-70% of comparisons before any LLM call.

### 2. Code Generation (execution-based)
- Extract code from both outputs
- Run against test cases in a sandboxed subprocess (10s timeout)
- Compute pass@k and static complexity scores
- No judge bias possible -- execution is ground truth

### 3. Bug Fixing (SWE-bench style)
- Clone repo, revert the historical fix, present buggy state to the model
- Apply generated patch, run the repo's actual test suite
- Pass/fail is binary and objective

### 4. Code Explanation (LLM-as-judge)
- Strip comments, docstrings, README from open-source repos
- Model explains raw, uncommented code
- Judge (a different, larger model) scores both outputs using a structured rubric
- Run twice with swapped order, average scores to cancel position bias

---

## LLM Judge Bias Mitigations

| Bias | Mitigation |
|---|---|
| Self-preference | Use a different model as judge than either candidate |
| Position bias | Swap order, run twice, average |
| Verbosity bias | Explicit rubric: "length is not a quality signal" |
| Vague rubric | Structured: correctness (0-3), clarity (0-3), completeness (0-3) |

---

## Implicit Feedback Weights

| Signal | Quality interpretation |
|---|---|
| `copied=True, edit_distance < 0.1, re_asked=False` | High-quality old output -- divergence is a high-priority regression |
| `copied=False` or `re_asked=True` | Low-quality old output -- divergence may be an improvement |

---

## Ship / Hold Decision

| Condition | Decision |
|---|---|
| Code gen pass rate drops > 5% | HOLD |
| Bug fix pass rate drops > 10% | HOLD |
| Explanation score drops > 0.3 | HOLD |
| Weighted regression score < threshold | SHIP |
| Otherwise | REVIEW |

---

## Quick Start

```bash
# Start infrastructure
docker compose up -d

# Install deps
make install

# Seed sample production logs
python -m example.seed_logs

# Run eval (baseline vs candidate)
python -m example.run_eval --baseline gpt-4-0613 --candidate gpt-4-turbo

# Open API dashboard
open http://localhost:8083/docs
```

---

## Project Structure

```
src/eval_pipeline/
  models.py          -- domain models: LogEntry, TaskResult, EvalRun, EvalSummary
  config.py          -- pydantic-settings
  dataset/           -- log ingestion and stratified sampling
  pipeline/          -- replay, similarity filter, orchestrator
  evaluators/        -- code_gen (execution), bug_fix (SWE-bench), explanation (LLM)
  judge/             -- LLM-as-judge with rubric and bias mitigation
  feedback/          -- implicit feedback weighting
  registry/          -- versioned eval run storage
  storage/           -- SQLAlchemy 2.0 async Postgres
  api/               -- FastAPI dashboard
  cli/               -- command-line runner
```

---

## Tools

| Component | Tool |
|---|---|
| LLM inference | Anthropic Claude (claude-sonnet-4-6) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Code sandbox | subprocess + resource limits |
| Storage | PostgreSQL 16 via SQLAlchemy 2.0 async |
| Observability | Prometheus + Grafana + structlog |
| Packaging | Python 3.12 + uv |
