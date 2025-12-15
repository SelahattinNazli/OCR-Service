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
You are an expert in parsing Turkish government documents.
Extract the requested fields EXACTLY as they appear—NO CORRECTIONS, NO INFERENCE.

TEXT:
{raw_text}

FIELDS TO EXTRACT (JSON):
{fields_description}

STRICT RULES:
1. Output MUST be ONLY VALID JSON. The first character must be '{{' and the last '}}'.
2. Use ONLY the keys provided.
3. Extract values EXACTLY as written in the text.
4. For numbers, REMOVE spaces but keep all digits.
5. Missing fields → use null.
6. NO explanations, NO markdown, NO comments, NO extra text.
7. IF YOU OUTPUT ANYTHING OUTSIDE JSON, YOU FAIL.

Return ONLY the JSON object:
"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/api/generate", json=payload
                )

            if "response" in response.json():
                result_text = response.json()["response"]
            elif "data" in response.json() and len(response.json()["data"]) > 0:
                result_text = response.json()["data"][0].get("response", "")
            else:
                result_text = ""

            # Try direct JSON parsing
            try:
                result = json.loads(result_text)
            except Exception:
                json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                    except Exception:
                        result = {}
                else:
                    result = {}

            # Clean vergi_no: remove spaces, newlines, convert to int
            if "vergi_no" in result and result["vergi_no"]:
                try:
                    result["vergi_no"] = int(
                        str(result["vergi_no"]).replace(" ", "").strip()
                    )
                except (ValueError, AttributeError):
                    result["vergi_no"] = None
            else:
                # Regex fallback ONLY for vergi_no
                vergi_no = re.search(r"\b(\d[\d\s]{9,})\b", raw_text)
                if vergi_no:
                    result["vergi_no"] = int(vergi_no.group(1).replace(" ", ""))
                else:
                    result["vergi_no"] = None

            return result

        except Exception as e:
            raise Exception(f"Ollama API error: {str(e)}")
