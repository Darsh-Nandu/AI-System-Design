# AI System Design Portfolio

A collection of system design documents for production AI systems - focused on architecture decisions, tradeoffs, and design patterns. No code, just thinking.

---

## Structure

| Folder | What's inside |
|---|---|
| `RAG/` | Retrieval-Augmented Generation systems for different domains and accuracy requirements |
| `Agents/` | Multi-agent orchestration, loop detection, safety patterns |
| `LLM-Serving/` | Model serving, scaling, batching, and GPU efficiency |
| `Evaluation/` | Eval pipelines, regression detection, LLM-as-judge systems |
| `Guardrails/` | Input/output safety, PII handling, constrained generation |
| `Data-Pipelines/` | Ingestion, chunking, freshness, and deduplication |

---

## Design Documents

### RAG
- [High-Accuracy RAG](RAG/high-accuracy-rag.md) - Legal, medical, and compliance use cases where hallucination is unacceptable
- [Medical RAG with Temporal KG](RAG/medical-rag-temporal-kg.md) - Patient history reasoning using Knowledge Graphs and specialist model routing

### Agents
- [Loop Detection & Recovery](Agents/loop-detection.md) - Detecting and breaking agent loops without losing context
- [Fintech Refund Agent](Agents/fintech-refund-agent.md) - Safe irreversible action execution with confidence scoring and idempotency

### Evaluation
- [Coding Assistant Eval Pipeline](Evaluation/coding-assistant-eval.md) - Regression detection for model upgrades using shadow evaluation and execution-based testing

---

## Design Philosophy

Each document follows this structure:
1. **Problem** - what we're solving and why it's hard
2. **Architecture** - the full system design with components
3. **Key decisions** - why each component was chosen over alternatives
4. **Tradeoffs** - what we gave up and why it was worth it
5. **Failure modes** - what can go wrong and how the system handles it
6. **Interview question** - the prompt this design answers

---

*Designs derived from first-principles reasoning, mapped to production patterns used at Harvey AI, GitHub Copilot, Google Med-PaLM, and Midjourney.*