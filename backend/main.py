import json
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.base_agent import BaseAgent
from backend.planner_agent import PlannerAgent
from backend.tools.bash import BashTool
from backend.tools.chromadb_tool import ChromaDBTool
from backend.tools.duckdb_tool import DuckDBTool
from backend.tools.pdf_tool import PDFTool

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

base_agent = BaseAgent(tools=[BashTool(), DuckDBTool(), ChromaDBTool(), PDFTool()])
planner = PlannerAgent(base_agent=base_agent)
logger.info("Themis started: PlannerAgent -> BaseAgent")


class QueryRequest(BaseModel):
    input: str


@app.post("/query")
async def query(request: QueryRequest):
    async def stream():
        async for event in planner.run(request.input):
            yield f"data: {json.dumps(event)}\n\n"
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/test-parallel")
async def test_parallel():
    """Spawn 2 base agents in parallel, each just runs `ls`. For testing only."""
    import asyncio

    queue = asyncio.Queue()
    sub_results = {}

    agent_configs = [
        {"id": "agent-1", "instructions": "Run `ls` in the current directory and report the output."},
        {"id": "agent-2", "instructions": "Run `ls /tmp` and report the output."},
    ]

    async def _run(agent_id: str, instructions: str):
        await queue.put({"type": "subagent_start", "agent_id": agent_id, "instructions": instructions})
        result_text = ""
        async for event in base_agent.run(instructions):
            if event["type"] == "token":
                result_text += event["content"]
            await queue.put({"type": "subagent_event", "agent_id": agent_id, "event": event})
        await queue.put({"type": "subagent_end", "agent_id": agent_id, "result": result_text})
        sub_results[agent_id] = result_text

    async def stream():
        tasks = [asyncio.create_task(_run(c["id"], c["instructions"])) for c in agent_configs]

        done_count = 0
        while done_count < len(agent_configs):
            event = await queue.get()
            if event["type"] == "subagent_end":
                done_count += 1
            yield f"data: {json.dumps(event)}\n\n"

        await asyncio.gather(*tasks)

        yield f'data: {json.dumps({"type": "token", "content": "Both agents finished."})}\n\n'
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(stream(), media_type="text/event-stream")
