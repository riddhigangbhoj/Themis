import tempfile

import boto3
import fitz
from botocore import UNSIGNED
from botocore.config import Config

from backend.tools.base import BaseTool, ToolRequest, ToolResponse

S3_BUCKET = "indian-high-court-judgments"
S3_REGION = "ap-south-1"

MAX_OUTPUT_LENGTH = 50000


class PDFTool(BaseTool):
    name = "read_pdf"
    description = (
        "Download a court judgment PDF from the public S3 bucket and extract its text. "
        "The s3_key follows the pattern: data/pdf/year=YYYY/court=XX_YY/bench=NAME/FILENAME.pdf. "
        "Use the bash or sql tool first to find the pdf_link field from the JSON case data, "
        "then construct the s3_key from the partition path."
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
                        "s3_key": {
                            "type": "string",
                            "description": (
                                "The S3 object key for the PDF. "
                                "Example: data/pdf/year=2024/court=11_24/bench=sikkimhc_pg/SKHC010000012024_1_2024-03-19.pdf"
                            ),
                        },
                    },
                    "required": ["s3_key"],
                },
            },
        }

    async def execute(self, request: ToolRequest) -> ToolResponse:
        s3_key = request.parameters.get("s3_key", "")

        if not s3_key.strip():
            return ToolResponse(success=False, data={}, error="Empty s3_key")

        if not s3_key.endswith(".pdf"):
            return ToolResponse(success=False, data={}, error="s3_key must end with .pdf")

        try:
            s3 = boto3.client(
                "s3",
                region_name=S3_REGION,
                config=Config(signature_version=UNSIGNED),
            )

            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                s3.download_file(S3_BUCKET, s3_key, tmp.name)
                doc = fitz.open(tmp.name)
                text = "\n".join(page.get_text() for page in doc)
                page_count = len(doc)
                doc.close()

        except Exception as e:
            return ToolResponse(success=False, data={}, error=str(e))

        if len(text) > MAX_OUTPUT_LENGTH:
            text = text[:MAX_OUTPUT_LENGTH] + f"\n... (truncated, {len(text)} chars total)"

        return ToolResponse(success=True, data={"text": text, "pages": page_count})
