import asyncio

from backend.config import DATA_DIR
from backend.tools.base import BaseTool, ToolRequest, ToolResponse

# Commands the agent is allowed to run
ALLOWED_COMMANDS = {"ls", "find", "grep", "cat", "head", "tail", "wc", "jq", "tree"}

MAX_OUTPUT_LENGTH = 10000


class BashTool(BaseTool):
    name = "bash"
    description = (
        f"Run a bash command to explore and search the court data directory at {DATA_DIR}. "
        "Use this to list files, search JSON content with grep/jq, count records, etc. "
        "Commands are sandboxed to the data directory."
    )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": (
                                "The bash command to run. Must operate on/within "
                                f"{DATA_DIR}. Examples: 'ls {DATA_DIR}/json/', "
                                f"'grep -r \"keyword\" {DATA_DIR}/json/year=2024/', "
                                f"'find {DATA_DIR}/json -name \"*.json\" | wc -l'"
                            ),
                        },
                    },
                    "required": ["command"],
                },
            },
        }

    async def execute(self, request: ToolRequest) -> ToolResponse:
        command = request.parameters.get("command", "")

        if not self._is_safe(command):
            return ToolResponse(
                success=False,
                data={},
                error=f"Command rejected: must only access {DATA_DIR} using allowed commands: {ALLOWED_COMMANDS}",
            )

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=DATA_DIR,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResponse(
                success=False,
                data={},
                error=(
                    "Command timed out after 20 seconds. Your query is too broad — "
                    "narrow it down by targeting a specific partition "
                    "(e.g. year=YYYY/court=XX_YY/bench=NAME/*.json) instead of scanning everything. "
                    "Try a lighter, more targeted command."
                ),
            )

        output = stdout.decode()
        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:MAX_OUTPUT_LENGTH] + f"\n... (truncated, {len(stdout.decode())} chars total)"

        if proc.returncode != 0:
            err = stderr.decode()
            return ToolResponse(success=False, data={"stderr": err, "stdout": output}, error=err)

        if not output.strip():
            return ToolResponse(
                success=True,
                data={"output": "(no results) The command returned empty output. Try a different search or adjust your query."},
            )

        return ToolResponse(success=True, data={"output": output})

    def _is_safe(self, command: str) -> bool:
        # Must reference the data directory
        if DATA_DIR not in command:
            return False

        # Block dangerous patterns
        dangerous = {"rm ", "mv ", "cp ", "chmod", "chown", "sudo", "dd ", "mkfs", ">", ">>", "|", "&&", ";"}
        # Allow pipes and chaining for search workflows
        safe_pipes = {"|", "&&", ";"}
        dangerous -= safe_pipes

        for pattern in dangerous:
            if pattern in command:
                return False

        return True
