import asyncio
import json
import logging
from collections.abc import AsyncIterator

from backend.config import OPENROUTER_MODEL, MAX_TOOL_CALLS
from backend.llm import get_openrouter_client
from backend.base_agent import BaseAgent
from backend.tracing import get_langfuse

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = (
    "You are Themis, a legal research planner. You do NOT have direct access to data or tools. "
    "You MUST use the research_agent tool to look up any information. "
    "The research_agent has access to ChromaDB for semantic search, DuckDB for SQL queries on court case JSON data, and bash as a fallback. "
    "Instruct it to prefer ChromaDB and DuckDB — they are faster and more reliable. Bash should only be used as a last resort. "
    "Your job: break down the user's question, call research_agent one or more times, then synthesize the results. "
    "You can launch up to 3 research_agent calls in parallel in a single response to speed up research. "
    "Never answer from memory — always delegate to research_agent first."
)

RESEARCH_AGENT_TOOL = {
    "type": "function",
    "function": {
        "name": "research_agent",
        "description": "Delegate a research task to the base agent. It can run bash commands to explore court case data. Give it clear, specific instructions about what to find.",
        "parameters": {
            "type": "object",
            "properties": {
                "instructions": {
                    "type": "string",
                    "description": "Detailed instructions for what the research agent should find or do.",
                }
            },
            "required": ["instructions"],
        },
    },
}


class PlannerAgent:
    def __init__(self, base_agent: BaseAgent):
        self.base_agent = base_agent

    async def run(self, user_input: str) -> AsyncIterator[dict]:
        client = get_openrouter_client()
        langfuse = get_langfuse()

        trace = None
        if langfuse:
            trace = langfuse.start_span(
                name="themis-planner",
                input={"user_input": user_input},
            )

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        for iteration in range(MAX_TOOL_CALLS):
            generation = None
            if trace:
                generation = trace.start_generation(
                    name=f"planner-llm-call-{iteration}",
                    model=OPENROUTER_MODEL,
                    input=messages,
                )

            response_text = ""
            tool_calls = []

            stream = await client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages,
                tools=[RESEARCH_AGENT_TOOL],
                stream=True,
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if delta.content:
                    response_text += delta.content
                    yield {"type": "token", "content": delta.content}

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        while len(tool_calls) <= tc.index:
                            tool_calls.append({"id": "", "name": "", "arguments": ""})
                        if tc.id:
                            tool_calls[tc.index]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls[tc.index]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls[tc.index]["arguments"] += tc.function.arguments

            if generation:
                generation.update(output={"response": response_text, "tool_calls": tool_calls})
                generation.end()

            if not any(tc["name"] for tc in tool_calls):
                if trace:
                    trace.update(output={"response": response_text})
                    trace.end()
                return

            assistant_msg = {"role": "assistant", "content": response_text or None}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls
                if tc["name"]
            ]
            messages.append(assistant_msg)

            # Run all base agents concurrently, streaming events live via queue
            valid_tcs = [tc for tc in tool_calls if tc["name"]]
            queue = asyncio.Queue()
            sub_results = {}  # tc_id -> result text

            async def _run_subagent(tc):
                tool_input = json.loads(tc["arguments"]) if tc["arguments"] else {}
                instructions = tool_input.get("instructions", "")
                agent_id = tc["id"]
                await queue.put({"type": "subagent_start", "agent_id": agent_id, "instructions": instructions})
                sub_result_text = ""
                async for event in self.base_agent.run(instructions, parent_span=trace):
                    if event["type"] == "token":
                        sub_result_text += event["content"]
                    await queue.put({"type": "subagent_event", "agent_id": agent_id, "event": event})
                await queue.put({"type": "subagent_end", "agent_id": agent_id, "result": sub_result_text})
                sub_results[agent_id] = sub_result_text

            tasks = [asyncio.create_task(_run_subagent(tc)) for tc in valid_tcs]

            # Yield events live as they arrive; stop when all tasks finish
            done_count = 0
            while done_count < len(valid_tcs):
                event = await queue.get()
                if event["type"] == "subagent_end":
                    done_count += 1
                yield event

            await asyncio.gather(*tasks)  # propagate any exceptions

            for tc in valid_tcs:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": sub_results.get(tc["id"], "Agent completed with no text output."),
                })
                logger.info(f"Sub-agent result: {sub_results.get(tc['id'], '')[:80]}...")

        if trace:
            trace.update(output={"status": "max_iterations"})
            trace.end()

        yield {"type": "token", "content": "\n\nMax tool calls reached."}
