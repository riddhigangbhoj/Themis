import asyncio
import functools

import duckdb

from backend.config import DATA_DIR
from backend.tools.base import BaseTool, ToolRequest, ToolResponse

MAX_OUTPUT_LENGTH = 10000


class DuckDBTool(BaseTool):
    name = "sql"
    description = (
        f"Run a read-only SQL query using DuckDB against the court case JSON files in {DATA_DIR}. "
        "DuckDB can directly read JSON files with read_json_auto(). "
        f"Example: SELECT * FROM read_json_auto('{DATA_DIR}/json/year=2024/**/*.json') LIMIT 5"
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
                        "query": {
                            "type": "string",
                            "description": (
                                "A read-only SQL query. Use read_json_auto() to read JSON files. "
                                f"All file paths must be within {DATA_DIR}. "
                                f"Example: SELECT count(*) FROM read_json_auto('{DATA_DIR}/json/**/*.json')"
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(self, request: ToolRequest) -> ToolResponse:
        query = request.parameters.get("query", "")

        if not query.strip():
            return ToolResponse(success=False, data={}, error="Empty query")

        # Block writes
        first_word = query.strip().split()[0].upper()
        if first_word not in ("SELECT", "DESCRIBE", "SHOW", "EXPLAIN", "WITH", "FROM"):
            return ToolResponse(success=False, data={}, error="Only read-only queries are allowed")

        def _run_query(q: str):
            conn = duckdb.connect(":memory:")
            result = conn.execute(q)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            conn.close()
            return columns, rows

        try:
            loop = asyncio.get_running_loop()
            columns, rows = await asyncio.wait_for(
                loop.run_in_executor(None, functools.partial(_run_query, query)),
                timeout=20,
            )
        except TimeoutError:
            return ToolResponse(
                success=False,
                data={},
                error=(
                    "Query timed out after 20 seconds. Your query is scanning too many files — "
                    "narrow the glob pattern to a specific partition "
                    "(e.g. year=YYYY/court=XX_YY/bench=NAME/*.json) instead of using broad wildcards. "
                    "Add a LIMIT clause and try a lighter query."
                ),
            )
        except Exception as e:
            return ToolResponse(success=False, data={}, error=str(e))

        if not rows:
            return ToolResponse(
                success=True,
                data={"output": "(no results) The query returned 0 rows. Try adjusting your search or query.", "row_count": 0},
            )

        # Format as text table
        output = "\t".join(columns) + "\n"
        for row in rows:
            output += "\t".join(str(v) for v in row) + "\n"

        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:MAX_OUTPUT_LENGTH] + f"\n... (truncated, {len(output)} chars total)"

        return ToolResponse(success=True, data={"output": output, "row_count": len(rows)})
