# Coding Assistant Eval Pipeline - Model Upgrade Regression Detection

**Domain:** Any AI product undergoing model upgrades  
**Interview question:** *"You're upgrading your coding assistant's base model. Design an eval system that catches regressions and gives your team confidence to ship - using 3 months of production logs."*  
**Industry reference:** GitHub Copilot, Cursor, SWE-bench, HumanEval

---

## The Core Problem

Model upgrades are not guaranteed improvements. A new model might be better at code generation but worse at explanations. Without a systematic eval, teams ship blind - relying on "it feels better" from a few manual tests.

The eval system needs to:
1. Compare old vs new model on real-world inputs (not synthetic benchmarks alone)
2. Cover all three task types: code generation, explanation, bug fixing
3. Be cheap enough to run on every model candidate, not just final release
4. Be reusable for the *next* upgrade without rebuilding

---

## Architecture Overview

```
3 months of production logs (golden dataset)
  │  prompts + old model outputs + implicit feedback signals
  │  (copy rate, re-ask rate, edit distance - already recorded)
  ▼
[Replay Pipeline - Shadow Evaluation]
  │  same prompts → new model → new outputs
  │  old model outputs already exist in logs, no need to re-run
  ▼
[Cascaded Comparison]
  │
  ├── Cosine similarity (old output vs new output)
  │     high similarity → skip judge, mark "no change"
  │     low similarity → proceed to LLM judge
  │
  ▼
[Task-Specific Evaluation]
  │
  ├── CODE GENERATION
  │     → Execution-based eval (run code against test cases)
  │     → pass@k metric (does it pass within k attempts?)
  │     → Static analysis (linting, complexity score)
  │
  ├── BUG FIXING
  │     → SWE-bench style: real repo + known bug + known fix
  │     → Does generated patch pass the test suite?
  │     → Compare patch similarity to ground-truth fix
  │
  └── CODE EXPLANATION
        → Strip docs/README from open-source repos (no cheating,
          disable web search)
        → Model explains uncommented code
        → LLM-as-judge compares explanation accuracy vs ground truth
        → Use larger/different model as judge (avoid self-preference)
        → Swap order + average (avoid position bias)
  │
  ▼
[Implicit Feedback Correlation]
  │  for prompts where new model's output diverges from old:
  │  was the OLD output's implicit feedback positive or negative?
  │  (high copy rate = old output was good - new model should match
  │   or exceed; low copy rate = old output was bad - new model
  │   improving here is a win even if "different")
  ▼
[Scorecard]
  │  aggregate scores per task type, per model version
  │  stored in eval registry - versioned over time
  ▼
Ship / Hold decision
```

---

## Using Production Logs as the Golden Dataset

The key insight: you don't need to re-run the old model. Its outputs are already in your logs, along with real user behavior.

```
LogEntry {
  prompt: "fix this null pointer exception in..."
  old_model_output: "...",
  task_type: "bug_fixing",
  implicit_signals: {
    copied: true,
    re_asked_within_60s: false,
    edit_distance_after_copy: 0.05,   // user barely changed it
    thumbs: null
  }
}
```

For the new model, only the new output needs to be generated - this halves your compute cost compared to re-running both models from scratch.

---

## Cascaded Evaluation - Cost Control

Running an LLM judge on every single comparison is expensive at scale (3 months of logs could be hundreds of thousands of entries).

**Stage 1 - Cheap filter:** cosine similarity between old and new output embeddings.
- Similarity > 0.95 → outputs are essentially the same, mark "no change," skip judge
- Similarity < 0.95 → genuinely different, proceed to Stage 2

This typically eliminates 60-70% of comparisons before any expensive LLM call.

**Stage 2 - LLM judge:** only for divergent outputs, with task-specific rubrics (below).

---

## Execution-Based Evaluation (Code Generation)

The gold standard for code - don't ask "does this look right," run it.

```
For each prompt in golden set where task_type = "code_generation":
  1. Extract generated code from both old and new outputs
  2. If test cases exist in logs (from user's actual usage context)
     or can be derived from the prompt → run both versions
  3. pass@k: did the new model's code pass within k generation attempts?
  4. Compare runtime, memory usage if relevant
  5. Static analysis: cyclomatic complexity, lint warnings
```

This is the same principle as **HumanEval** and **MBPP** - execution is ground truth, no judge bias possible.

---

## SWE-bench Style Bug Fixing Eval

For bug fixing specifically, synthetic test cases aren't enough - real bugs in real codebases are the standard.

```
1. Clone real open-source repos (post-training-cutoff repos preferred,
   to avoid data contamination)
2. Identify a real historical bug + its real fix (from git history)
3. Revert the fix, present the buggy state + bug description to model
4. Model generates a patch
5. Apply patch, run the repo's actual test suite
6. Pass/fail is binary and objective - no judge needed
```

This is literally how **SWE-bench** works - and it's the standard for evaluating coding agents (Claude, GPT-4, Gemini are all ranked on it).

---

## Code Explanation Eval - Preventing "Cheating"

LLMs can cheat explanation tasks by reading README/docs instead of actually understanding code.

```
1. Select open-source repos
2. Strip: README.md, CLAUDE.md, GEMINI.md, inline comments, docstrings
3. Disable web search / tool access for the eval run
4. Present raw, uncommented code + question: "explain what this does"
5. Compare model's explanation against:
   - Original comments/docs (ground truth, hidden from model)
   - LLM judge scores explanation accuracy
```

This isolates genuine code comprehension from documentation regurgitation.

---

## LLM-as-Judge - Bias Mitigation

| Bias | Mitigation |
|---|---|
| Self-preference (judge prefers outputs similar to its own style) | Use a different, larger model as judge than either model being compared |
| Position bias (judge prefers first-shown answer) | Run twice with swapped order, average scores |
| Verbosity bias (judge prefers longer answers) | Explicit rubric instruction: "length is not a quality signal" |
| Vague rubric ("which is better?") | Structured rubric: correctness (0-3), clarity (0-3), completeness (0-3) |

---

## Implicit Feedback as Ground Truth

Production logs contain free quality signals that require no annotation:

| Signal | What it indicates |
|---|---|
| Copy rate | Did the user find the output usable as-is? (GitHub Copilot's primary metric) |
| Re-ask within 60s | User was dissatisfied, tried again |
| Edit distance after copy | How much did the user have to fix? Low = high quality |
| Thumbs up/down | Explicit signal, sparse but high-value |

These signals are attached to the *old* model's outputs in your logs. Use them to weight which divergences matter most:

> If old model had high copy rate on a prompt, and new model's output diverges significantly → high-priority review (potential regression)
>
> If old model had low copy rate (user was unhappy), and new model diverges → potential improvement, lower priority for manual review

---

## Eval Registry - Making This Reusable

The system must work for the *next* upgrade without rebuilding.

```
EvalRegistry {
  test_suites: {
    "code_gen_v1": [...],      // versioned independently of models
    "bug_fix_swebench_v1": [...],
    "explanation_v1": [...]
  }
  runs: [
    { model: "gpt-4-0613", date: "2024-01", scores: {...} },
    { model: "gpt-4-turbo", date: "2024-03", scores: {...} },
    { model: "new-candidate", date: "2024-06", scores: {...} }
  ]
}
```

Each new model upgrade = point the pipeline at the new model endpoint, rerun against existing test suites. Scores stored alongside historical runs → dashboard shows trend lines per task type over every model version ever evaluated.

---

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| Reuse old model outputs from logs | Halves compute cost | Logs must have been comprehensive from day one |
| Cascaded similarity filter | 60-70% cost reduction on judge calls | Similarity threshold needs tuning |
| Execution-based eval for code | Objective, no judge bias | Requires sandboxed execution environment |
| SWE-bench style bug fixing | Real-world difficulty, objective pass/fail | Time-consuming to curate good bug/fix pairs |
| Eval registry | Reusable across upgrades | Upfront investment in versioning infrastructure |

---

## Tools Referenced

| Component | Tool |
|---|---|
| Eval orchestration & registry | Braintrust, LangSmith, Promptfoo |
| Code execution sandbox | Docker-based sandbox, E2B |
| Embedding similarity | OpenAI/Cohere embeddings + cosine similarity |
| Benchmarks referenced | HumanEval, MBPP, SWE-bench |
| Observability (source of logs) | LangSmith, Helicone, Arize Phoenix |
