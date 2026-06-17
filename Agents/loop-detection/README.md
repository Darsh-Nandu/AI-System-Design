# Agent Loop Detection and Recovery

**Domain:** Any multi-step LLM agent using tool calls
**Interview question:** *"An agent is stuck in a tool-call loop -- how do you detect and break it without losing context?"*
**Industry reference:** LangGraph recursion limits, AutoGPT loop guards

---

## The Problem

Agents get stuck for reasons that look different on the surface but share a root cause: the agent keeps acting without making *progress*. Naive fixes (timeouts, retry limits) catch the obvious cases but miss subtler ones, and a hard kill loses the agent's reasoning state and forces the user to start over.

---

## Layered Detection Architecture

```
Agent loop (plan -> act -> observe -> repeat)
  |
  v
[Layer 1: Per-tool dynamic time limits]
  |  timeout = historical_p95 * 3 (not a fixed number)
  |  variable-duration tools get per-call limits based on input size
  v
[Layer 2: Action fingerprinting]
  |  hash(tool_name, normalized_args) on every call
  |  exact duplicate within window -> immediate flag
  |  normalize: sort dict keys, round floats, strip whitespace
  v
[Layer 3: Semantic similarity]
  |  embed (action, observation) pair
  |  cosine similarity vs last N pairs
  |  high similarity with different args -> soft loop
  v
[Layer 4: Step and token budget]
  |  hard cap: N steps or K tokens
  |  on exhaustion -> force summarize_and_halt (not a silent kill)
  v
[Layer 5: Progress tracking]
  |  did this step add new unique information?
  |  cumulative cost without progress -> halt
  v
[Layer 6: Monitoring agent]
  |  separate process observing tool execution in real time
  |  can interrupt a stuck tool mid-execution
  |  sends structured error, not a silent kill
  v
Recovery (not kill)
```

---

## Recovery Strategies (escalating)

**Strategy 1 -- Inject correction:**
Loop detected -> inject a system message into context: *"You have called search_database with identical arguments 3 times. The previous results did not change. Try a different approach."* Agent continues with awareness, no restart.

**Strategy 2 -- Forced summarization:**
Budget exhausted -> agent is forced to call `summarize_and_halt`, producing a partial result and explanation of what it tried, rather than silently failing.

**Strategy 3 -- Human checkpoint:**
After M consecutive detections -> serialize full agent state (messages, tool results, plan) and surface to a human review queue. Human edits the plan and resumes -- agent picks up from serialized state, not from scratch.

---

## Causal Loop Detection

Beyond exact/semantic duplicates, track a dependency graph of which tool outputs feed into which subsequent inputs.

```
Step 1: search("user database") -> result A
Step 2: filter(result A) -> result B
Step 3: search("user database") -> result A (again)
Step 4: filter(result A) -> result B (again)
```

If output of step N equals output of step N+2, and the inputs trace back to the same upstream call, that is a causal cycle -- the agent is re-deriving the same conclusion repeatedly even though no two adjacent calls are exact duplicates.

---

## Drop-in Usage

```python
from loop_detector.middleware.langgraph import LoopDetectionMiddleware, LoopDetectorConfig

graph = StateGraph(MyState)
# ... add nodes and edges ...

config = LoopDetectorConfig(
    max_steps=50,
    fingerprint_window=10,
    semantic_threshold=0.92,
    consecutive_detections_for_checkpoint=3,
)
protected_graph = LoopDetectionMiddleware(graph, config=config)

# Use exactly like a normal compiled graph
result = await protected_graph.ainvoke(initial_state, config={"configurable": {"thread_id": "sess_1"}})
```

---

## Running Locally

```bash
cd Agents/loop-detection

cp .env.example .env
make up
make install
make migrate

# Run the example looping agent (to see detection in action)
make example

# Start the monitoring dashboard API
make api
```

| Service | URL |
|---|---|
| Monitoring Dashboard API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

---

## Stack

| Component | Technology |
|---|---|
| Middleware / agent | LangGraph |
| LLM | Claude claude-sonnet-4-6 (Anthropic) |
| Semantic detection | sentence-transformers (all-MiniLM-L6-v2) |
| State and fingerprint store | Redis |
| Loop event history | PostgreSQL 16 |
| Monitoring API | FastAPI |
| Metrics | Prometheus + Grafana |
| CI | GitHub Actions |

---

## Detection Decision Table

| Signal | Likely cause | Response |
|---|---|---|
| Exact duplicate call | Agent forgot it already tried this | Inject correction |
| High semantic similarity, different args | Agent rephrasing the same failed approach | Inject correction with pattern callout |
| Tool timeout (monitoring agent) | External service down or stuck | Structured error, suggest fallback |
| Budget exhausted, no new info | Task may be unsolvable as framed | Forced summarization |
| M consecutive detections | Agent fundamentally stuck | Human checkpoint |

---

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| Dynamic per-call timeouts | Handles variable-duration tools correctly | Requires historical data to calibrate |
| Separate monitoring agent | Real-time visibility, can interrupt mid-execution | Extra process, added complexity |
| Inject correction vs kill | Preserves context, agent can self-correct | May take an extra step to break |
| Causal loop detection | Catches subtle cycles fingerprinting misses | Requires building and maintaining a dependency graph |
