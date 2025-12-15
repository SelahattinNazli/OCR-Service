import json
import re
import httpx
from typing import Dict, Any
from app.services.ocr_service import BaseOCRService
from app.config import settings


class LLMOCRService(BaseOCRService):
    def __init__(self):
        self.api_url = settings.OLLAMA_API_URL
        self.model = settings.OLLAMA_MODEL

    async def extract_text(self, image_path: str) -> str:
        return ""

    async def parse_fields(
        self, raw_text: str, fields: Dict[str, Dict[str, str]]
    ) -> Dict[str, Any]:
        fields_description = json.dumps(fields, ensure_ascii=False, indent=2)

        prompt = f"""
You are a document parsing expert. Extract the requested fields from the text EXACTLY as they appear.

TEXT:
{raw_text}

FIELDS TO EXTRACT (JSON format):
{fields_description}

RULES:
1. Return ONLY a valid JSON object.
2. Use ONLY the field keys provided.
3. Extract values EXACTLY as written.
4. If a number contains spaces (e.g. '8 9 3 0 ...'), remove all spaces and output as a continuous number.
5. DO NOT include newline characters, \\n, trailing spaces, or extra whitespace.
6. If a field is missing, return null.
7. Absolutely NO explanation, NO markdown, NO commentary.

RESPONSE (JSON ONLY):
"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(f"{self.api_url}/api/generate", json=payload)

            result_text = resp.json().get("response", "{}")

            # JSON parse
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        result = {}
                else:
                    result = {}

            # Normalize numeric fields (remove whitespace, trim)
            for key, value in result.items():
                if isinstance(value, str):
                    cleaned = value.strip().replace(" ", "")
                    result[key] = cleaned if cleaned != "" else None

            return result

        except Exception as e:
            raise Exception(f"Ollama API error: {str(e)}")
