"""Seed the database with sample production log entries.

Creates realistic examples for all three task types so the pipeline can
be run end-to-end without a live production log export.
"""

from __future__ import annotations

import asyncio

from eval_pipeline.dataset.loader import insert_log_entry
from eval_pipeline.logging import configure_logging
from eval_pipeline.models import ImplicitSignals, LogEntry, TaskType, TestCase
from eval_pipeline.storage.postgres import create_tables

configure_logging()

_CODE_GEN_ENTRIES = [
    LogEntry(
        prompt="Write a Python function that reverses a string without using slicing.",
        old_model_output="""
```python
def reverse_string(s: str) -> str:
    result = ""
    for char in s:
        result = char + result
    return result
```
""",
        task_type=TaskType.CODE_GENERATION,
        language="python",
        implicit_signals=ImplicitSignals(copied=True, edit_distance_after_copy=0.02, re_asked_within_60s=False),
        test_cases=[
            TestCase(input_data='s = "hello"\nprint(reverse_string(s))', expected_output="olleh"),
            TestCase(input_data='s = ""\nprint(reverse_string(s))', expected_output=""),
            TestCase(input_data='s = "a"\nprint(reverse_string(s))', expected_output="a"),
        ],
    ),
    LogEntry(
        prompt="Write a function that checks if a number is prime.",
        old_model_output="""
```python
def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True
```
""",
        task_type=TaskType.CODE_GENERATION,
        language="python",
        implicit_signals=ImplicitSignals(copied=True, edit_distance_after_copy=0.0, re_asked_within_60s=False),
        test_cases=[
            TestCase(input_data="print(is_prime(7))", expected_output="True"),
            TestCase(input_data="print(is_prime(4))", expected_output="False"),
            TestCase(input_data="print(is_prime(1))", expected_output="False"),
        ],
    ),
    LogEntry(
        prompt="Implement binary search on a sorted list.",
        old_model_output="""
```python
def binary_search(arr: list[int], target: int) -> int:
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
```
""",
        task_type=TaskType.CODE_GENERATION,
        language="python",
        implicit_signals=ImplicitSignals(copied=False, re_asked_within_60s=True),
        test_cases=[
            TestCase(input_data="arr=[1,3,5,7,9]\nprint(binary_search(arr,5))", expected_output="2"),
            TestCase(input_data="arr=[1,3,5,7,9]\nprint(binary_search(arr,6))", expected_output="-1"),
        ],
    ),
]

_BUG_FIX_ENTRIES = [
    LogEntry(
        prompt="Fix the bug: this function should return the factorial but returns 0 for n=0.\n\n```python\ndef factorial(n):\n    if n == 0:\n        return 0\n    return n * factorial(n - 1)\n```",
        old_model_output="""
The bug is in the base case. When n=0, factorial should return 1, not 0.

```diff
- if n == 0:
-     return 0
+ if n == 0:
+     return 1
```
""",
        task_type=TaskType.BUG_FIXING,
        language="python",
        implicit_signals=ImplicitSignals(copied=True, edit_distance_after_copy=0.0),
        bug_description="factorial(0) returns 0 instead of 1",
    ),
    LogEntry(
        prompt="Fix the off-by-one error in this loop:\n\n```python\nfor i in range(1, len(arr)):\n    print(arr[i])\n```",
        old_model_output="""
The loop starts at index 1, skipping the first element. Change to start at 0.

```diff
- for i in range(1, len(arr)):
+ for i in range(0, len(arr)):
```
""",
        task_type=TaskType.BUG_FIXING,
        language="python",
        implicit_signals=ImplicitSignals(copied=False, re_asked_within_60s=True),
        bug_description="Loop skips first element",
    ),
]

_EXPLANATION_ENTRIES = [
    LogEntry(
        prompt="Explain what this code does:\n\ndef f(n):\n    if n <= 1:\n        return n\n    return f(n-1) + f(n-2)",
        old_model_output="This is a recursive implementation of the Fibonacci sequence. f(n) returns the nth Fibonacci number by summing the two previous values. The base cases are f(0)=0 and f(1)=1.",
        task_type=TaskType.CODE_EXPLANATION,
        language="python",
        implicit_signals=ImplicitSignals(copied=True, edit_distance_after_copy=0.05),
        raw_code="def f(n):\n    if n <= 1:\n        return n\n    return f(n-1) + f(n-2)",
        reference_explanation="Recursive Fibonacci: returns the nth number in the Fibonacci sequence (0, 1, 1, 2, 3, 5...) with base cases for n=0 and n=1.",
    ),
    LogEntry(
        prompt="Explain what this code does:\n\ndef g(lst):\n    seen = set()\n    return [x for x in lst if not (x in seen or seen.add(x))]",
        old_model_output="This function removes duplicates from a list while preserving the original order. It uses a set called 'seen' to track which elements have already appeared.",
        task_type=TaskType.CODE_EXPLANATION,
        language="python",
        implicit_signals=ImplicitSignals(copied=True, edit_distance_after_copy=0.1),
        raw_code="def g(lst):\n    seen = set()\n    return [x for x in lst if not (x in seen or seen.add(x))]",
        reference_explanation="Order-preserving deduplication: iterates through the list and keeps only the first occurrence of each element using a set for O(1) membership tests.",
    ),
    LogEntry(
        prompt="Explain what this code does:\n\nresult = sorted(data, key=lambda x: (-x['score'], x['name']))",
        old_model_output="This sorts a list of dictionaries by score in descending order. Ties in score are broken alphabetically by name in ascending order.",
        task_type=TaskType.CODE_EXPLANATION,
        language="python",
        implicit_signals=ImplicitSignals(thumbs_up=True),
        raw_code="result = sorted(data, key=lambda x: (-x['score'], x['name']))",
        reference_explanation="Multi-key sort: primary key is score descending (negated for reverse), secondary key is name ascending (string natural order). Stable sort preserves original order for equal keys.",
    ),
]


async def seed() -> None:
    await create_tables()
    all_entries = [*_CODE_GEN_ENTRIES, *_BUG_FIX_ENTRIES, *_EXPLANATION_ENTRIES]
    for entry in all_entries:
        await insert_log_entry(entry)
    print(f"Seeded {len(all_entries)} log entries.")


if __name__ == "__main__":
    asyncio.run(seed())
