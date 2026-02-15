import json
import logging
from collections.abc import AsyncIterator

from backend.config import OPENROUTER_MODEL, MAX_TOOL_CALLS
from backend.llm import get_openrouter_client
from backend.tools.base import BaseTool, ToolRequest
from backend.tracing import get_langfuse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Themis, a legal research assistant. You have access to a directory of Indian court case data "
    "stored as JSON files partitioned by year, court, and bench. "
    "Use the bash tool to explore the data directory, search for cases, and answer questions. "
    "Be precise, cite case numbers, and always ground your answers in the data you find."
)


class BaseAgent:
    def __init__(self, tools: list[BaseTool]):
        self.tools = {tool.name: tool for tool in tools}
        self.tool_schemas = [tool.get_schema() for tool in tools]

    async def run(self, user_input: str, parent_span=None) -> AsyncIterator[dict]:
        client = get_openrouter_client()
        langfuse = get_langfuse()

        trace = None
        if parent_span:
            trace = parent_span.start_span(
                name="themis-base",
                input={"user_input": user_input},
            )
        elif langfuse:
            trace = langfuse.start_span(
                name="themis-base",
                input={"user_input": user_input},
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        for iteration in range(MAX_TOOL_CALLS):
            generation = None
            if trace:
                generation = trace.start_generation(
                    name=f"llm-call-{iteration}",
                    model=OPENROUTER_MODEL,
                    input=messages,
                )

            response_text = ""
            tool_calls = []

            stream = await client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages,
                tools=self.tool_schemas,
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

            # No tool calls = final answer
            if not any(tc["name"] for tc in tool_calls):
                if trace:
                    trace.update(output={"response": response_text})
                    trace.end()
                return

            # Build assistant message with tool calls
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

            # Execute each tool call
            for tc in tool_calls:
                if not tc["name"]:
                    continue

                tool_name = tc["name"]
                tool_id = tc["id"]

                tool_input = json.loads(tc["arguments"]) if tc["arguments"] else {}

                tool = self.tools.get(tool_name)
                if not tool:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": json.dumps({"error": f"Unknown tool: {tool_name}"}),
                    })
                    continue

                yield {"type": "tool_start", "name": tool_name, "input": tool_input}

                tool_span = None
                if trace:
                    tool_span = trace.start_span(name=f"tool-{tool_name}", input=tool_input)

                result = await tool.execute(ToolRequest(parameters=tool_input))

                result_payload = result.data if result.success else {"error": result.error}

                yield {"type": "tool_end", "name": tool_name, "output": result_payload}

                if tool_span:
                    tool_span.update(output=result_payload)
                    tool_span.end()

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": json.dumps(result_payload),
                })

                logger.info(f"Tool {tool_name} -> success={result.success}")

        if trace:
            trace.update(output={"status": "max_iterations"})
            trace.end()

        yield {"type": "token", "content": "\n\nMax tool calls reached."}
