# Agent Loop Detection & Recovery

**Domain:** Any multi-step LLM agent using tool calls  
**Interview question:** *"An agent is stuck in a tool-call loop - how do you detect and break it without losing context?"*  
**Industry reference:** LangGraph recursion limits, AutoGPT loop guards

---

## The Core Problem

Agents can get stuck for reasons that look different on the surface but share a root cause: the agent keeps acting without making *progress*. Naive fixes (timeouts, retry limits) catch the obvious cases but miss subtler ones - and a hard kill loses the agent's reasoning state, forcing the user to start over.

---

## Layered Detection Architecture

```
Agent loop (plan → act → observe → repeat)
  │
  ▼
[Layer 1 - Per-tool time limits]
  │  each tool call has a max duration based on its type
  │  variable-time tools (file write, long jobs) get dynamic limits,
  │  not fixed ones - based on expected size/complexity
  ▼
[Layer 2 - Action fingerprinting]
  │  hash(tool_name, normalized_args) on every call
  │  exact duplicate within window → immediate flag
  │  normalize args: sort dict keys, round floats, strip whitespace
  ▼
[Layer 3 - Semantic similarity check]
  │  embed (action, observation) pairs
  │  cosine similarity vs last N pairs
  │  high similarity with different exact args → "soft loop" detected
  ▼
[Layer 4 - Step/token budget]
  │  hard cap: N reasoning steps or K tokens
  │  on exhaustion → force "summarize_and_halt" action
  │  (not a kill - agent produces partial summary first)
  ▼
[Layer 5 - Progress tracking]
  │  did this step add new unique information to context?
  │  cumulative cost without new information → halt
  ▼
[Layer 6 - Monitoring agent (separate process)]
  │  watches tool execution in real time
  │  sees file I/O, API responses, error states directly
  │  can terminate a stuck tool call mid-execution
  │  notifies main LLM with structured error, not silent kill
  ▼
On detection → Recovery (not kill)
```

---

## Why Per-Tool Time Limits Aren't Enough

Tools have wildly different "normal" durations:
- API call: should respond in <2s, timeout at 5s is safe
- File write: could be 10KB or 10GB - fixed timeout either kills valid long writes or lets stuck writes run forever
- LLM sub-call: variable based on output length

**Better approach:** dynamic limits based on expected complexity, set per-call rather than per-tool-type:
```
estimated_duration = f(input_size, tool_type, historical_p95)
timeout = estimated_duration * 3   // generous multiplier
```

If a call exceeds 3x its own historical p95 for similar inputs, that's anomalous - even if it's "fast" in absolute terms.

---

## The Monitoring Agent Pattern

A separate lightweight process (not the main LLM) observes tool execution:

```
Main Agent                    Monitoring Agent
    │                                │
    ├── calls write_file() ────────►│ sees file descriptor opened
    │                                │ tracks bytes written over time
    │                                │ if bytes written = 0 for 30s
    │                                │   → flags as stuck
    │                                │
    │◄── structured error ───────────┤ "write_file stalled: 0 bytes
    │    (not raw kill)              │  written in 30s, file handle
    │                                │  may be locked"
    │
    ├── agent reasons about error,
    │   tries alternative approach
```

This agent can also do output correctness checks - comparing what the LLM *claims* it did against what the monitoring agent *observed* actually happening. Mismatch → flag for review.

**Health endpoints:** each tool exposes a lightweight `/health` check the monitoring agent polls - useful for tools that wrap external services (databases, APIs) that might be down entirely rather than just slow.

---

## Recovery - Not Kill

The goal is to break the loop *without losing context*. Three recovery strategies, escalating:

**Strategy 1 - Inject a correction:**
Loop detected → inject a system message into the agent's context: *"You have called search_database with identical arguments 3 times. The previous results did not change. Try a different approach or ask the user for clarification."* Agent continues with awareness, doesn't restart.

**Strategy 2 - Forced summarization:**
Budget exhausted → agent is forced to call `summarize_and_halt`, producing a partial result and explanation of what it tried, rather than silently failing.

**Strategy 3 - Human checkpoint:**
After M consecutive loop detections → serialize full agent state (messages, tool results, plan) and surface to a human review queue. Human can edit the plan and resume - agent picks up from serialized state, not from scratch.

---

## Causal Loop Detection (Advanced)

Beyond exact/semantic duplicates, track a dependency graph: which tool outputs feed into which subsequent inputs.

```
Step 1: search("user database") → result A
Step 2: filter(result A) → result B
Step 3: search("user database") → result A (again)
Step 4: filter(result A) → result B (again)
```

If output of step N equals output of step N+2 *and* the inputs that produced them trace back to the same upstream call, that's a causal cycle - the agent is re-deriving the same conclusion repeatedly, even though individual calls aren't exact duplicates of the immediately preceding one.

---

## Combining Layers - Decision Table

| Signal | Likely cause | Response |
|---|---|---|
| Exact duplicate call | Agent forgot it already tried this | Inject correction (Strategy 1) |
| High semantic similarity, different args | Agent rephrasing same failed approach | Inject correction with explicit pattern callout |
| Tool hangs (monitoring agent) | External service issue | Structured error + suggest fallback tool |
| Step budget exhausted, no new info | Task may be unsolvable as framed | Forced summarization (Strategy 2) |
| M loop detections in a row | Agent fundamentally stuck | Human checkpoint (Strategy 3) |

---

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| Dynamic per-call timeouts | Handles variable-duration tools correctly | Requires historical data to calibrate |
| Separate monitoring agent | Real-time visibility, can interrupt mid-execution | Extra process, added system complexity |
| Inject correction vs kill | Preserves context, agent can self-correct | May take an extra step to actually break the loop |
| Causal loop detection | Catches subtle cycles fingerprinting misses | Requires building and maintaining dependency graph |

---

## Tools Referenced

| Component | Tool |
|---|---|
| Agent orchestration with recursion limits | LangGraph |
| State checkpointing | LangGraph checkpointer, Redis |
| Semantic similarity | sentence-transformers + cosine similarity |
| Observability / tracing | LangSmith, Arize Phoenix |
| Health checks | Standard `/health` endpoints per tool |
