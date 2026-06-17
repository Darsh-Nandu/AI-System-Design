"""Run the example looping agent with loop detection enabled."""

from __future__ import annotations

import asyncio
import uuid

from langchain_core.messages import HumanMessage

from example.agent import build_protected_graph
from loop_detector.storage.postgres import create_tables


async def _run() -> None:
    await create_tables()

    graph = build_protected_graph()
    session_id = str(uuid.uuid4())

    print(f"\n[Example] Starting looping agent session: {session_id}")
    print("[Example] The agent will intentionally loop -- watch the detector intervene.\n")

    initial_state = {
        "messages": [HumanMessage(content="Find all user records and give me a full summary.")],
        "tool_name": "",
        "tool_args": {},
        "observation": "",
        "tokens_used": 0,
        "final_summary": "",
    }

    result = await graph.ainvoke(
        initial_state,
        config={"configurable": {"thread_id": session_id}},
    )

    summary = result.get("final_summary")
    if summary:
        print(f"\n[Result] Forced summarization triggered:\n{summary}")
    else:
        messages = result.get("messages", [])
        if messages:
            print(f"\n[Result] Last message:\n{messages[-1].content}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
