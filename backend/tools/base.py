from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolRequest:
    parameters: dict[str, Any]


@dataclass
class ToolResponse:
    success: bool
    data: dict[str, Any]
    error: str | None = None


class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def get_schema(self) -> dict:
        """Return tool schema in OpenAI function-calling format."""

    @abstractmethod
    async def execute(self, request: ToolRequest) -> ToolResponse:
        """Execute the tool and return a response."""
