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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

base_agent = BaseAgent(tools=[BashTool()])
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
