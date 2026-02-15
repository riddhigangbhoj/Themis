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
    "The research_agent can run bash commands to explore Indian court case data (JSON files partitioned by year, court, and bench). "
    "Your job: break down the user's question, call research_agent one or more times, then synthesize the results. "
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

            for tc in tool_calls:
                if not tc["name"]:
                    continue

                tool_input = json.loads(tc["arguments"]) if tc["arguments"] else {}
                instructions = tool_input.get("instructions", "")

                yield {"type": "subagent_start", "instructions": instructions}

                # Run base agent, forwarding its events prefixed as sub-agent events
                sub_result_text = ""
                async for event in self.base_agent.run(instructions, parent_span=trace):
                    if event["type"] == "token":
                        sub_result_text += event["content"]
                    # Forward tool events from sub-agent so UI can display them
                    yield {"type": "subagent_event", "event": event}

                yield {"type": "subagent_end", "result": sub_result_text}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": sub_result_text or "Agent completed with no text output.",
                })

                logger.info(f"Sub-agent result: {sub_result_text[:80]}...")

        if trace:
            trace.update(output={"status": "max_iterations"})
            trace.end()

        yield {"type": "token", "content": "\n\nMax tool calls reached."}
