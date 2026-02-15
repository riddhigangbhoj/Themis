import asyncio
import functools

import chromadb
import duckdb

from backend.tools.base import BaseTool, ToolRequest, ToolResponse

CASES_DB_PATH = "/Users/atharva/workspace/code/projects/buildindia/cases.db"
CHROMA_DIR = "/Users/atharva/workspace/code/projects/buildindia/chroma_db"
COLLECTION_NAME = "cases"

MAX_OUTPUT_LENGTH = 10000


def _ensure_collection() -> chromadb.Collection:
    """Return the cases collection, building the index from DuckDB on first run."""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(COLLECTION_NAME)

    if collection.count() > 0:
        return collection

    # First run: load cases from DuckDB into ChromaDB
    db = duckdb.connect(CASES_DB_PATH, read_only=True)
    rows = db.execute(
        "SELECT cnr, title, judge, disposal, body_text, court_name "
        "FROM cases WHERE body_text != '' AND cnr != ''"
    ).fetchall()
    db.close()

    # Deduplicate by CNR (keep first occurrence)
    seen = set()
    unique_rows = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            unique_rows.append(r)
    rows = unique_rows

    BATCH = 500
    for start in range(0, len(rows), BATCH):
        batch = rows[start : start + BATCH]
        ids = [r[0] for r in batch]
        documents = [f"{r[1]} | {r[3]} | {r[4]}" for r in batch]
        metadatas = [{"judge": r[2] or "", "disposal": r[3] or "", "court": r[5] or ""} for r in batch]
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    return collection


class ChromaDBTool(BaseTool):
    name = "search_cases"
    description = (
        "Semantic search over 127k court cases using ChromaDB. "
        "Use this to find cases by meaning rather than exact keywords — "
        "e.g. 'property dispute illegal occupation', 'bail for murder', 'divorce custody of children'. "
        "Returns the most relevant cases with their title, disposal, judge, and court. "
        "Use the sql tool for structured/exact queries and this tool for fuzzy/semantic search."
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
                                "A natural-language search query describing the type of case you're looking for. "
                                "Example: 'property dispute involving illegal occupation of ancestral home'"
                            ),
                        },
                        "n_results": {
                            "type": "integer",
                            "description": "Number of results to return (default 10, max 30).",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(self, request: ToolRequest) -> ToolResponse:
        query = request.parameters.get("query", "")
        n_results = min(request.parameters.get("n_results", 10), 30)

        if not query.strip():
            return ToolResponse(success=False, data={}, error="Empty query")

        def _search(q: str, n: int):
            collection = _ensure_collection()
            return collection.query(query_texts=[q], n_results=n)

        try:
            loop = asyncio.get_running_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(None, functools.partial(_search, query, n_results)),
                timeout=30,
            )
        except TimeoutError:
            return ToolResponse(success=False, data={}, error="Search timed out after 30 seconds.")
        except Exception as e:
            return ToolResponse(success=False, data={}, error=str(e))

        if not results["ids"][0]:
            return ToolResponse(
                success=True,
                data={"output": "(no results) No matching cases found.", "result_count": 0},
            )

        # Format results
        output_lines = []
        for i, (doc_id, doc, meta, dist) in enumerate(
            zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ):
            # Truncate the document body for readability
            doc_preview = doc[:300].replace("\n", " ")
            output_lines.append(
                f"{i + 1}. [{dist:.3f}] CNR: {doc_id}\n"
                f"   Court: {meta.get('court', '')}\n"
                f"   Judge: {meta.get('judge', '')}\n"
                f"   Disposal: {meta.get('disposal', '')}\n"
                f"   Preview: {doc_preview}"
            )

        output = "\n\n".join(output_lines)

        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:MAX_OUTPUT_LENGTH] + f"\n... (truncated, {len(output)} chars total)"

        return ToolResponse(
            success=True,
            data={"output": output, "result_count": len(results["ids"][0])},
        )
