# app/services/llm_ocr_service.py
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
        """Extract text - delegated to EasyOCR (not used here)."""
        return ""

    async def parse_fields(
        self, raw_text: str, fields: Dict[str, Dict[str, str]]
    ) -> Dict[str, Any]:
        """Parse fields using Ollama Gemma3 with robust parsing + post-processing."""

        fields_description = json.dumps(fields, ensure_ascii=False, indent=2)

        prompt = f"""You are a document parsing expert. Extract the requested fields from the text EXACTLY as they appear.

TEXT:
{raw_text}

FIELDS TO EXTRACT (JSON format):
{fields_description}

RULES:
1. Return ONLY a valid JSON object.
2. Use only the field keys provided. Do NOT add new keys.
3. Extract values EXACTLY as they appear in the text.
4. For numbers: include ALL digits without spaces.
5. If a field is missing, set it to null.
6. ABSOLUTELY NO explanation, NO markdown, NO commentary, NO code fences.
7. Output MUST be raw JSON only — the first character MUST be '{" and the last MUST be "}'.

RESPONSE (JSON ONLY):"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.api_url}/api/generate",
                    json=payload,
                )

            # Ollama returns JSON object under some key; previous code used "response"
            result_text = response.json().get("response", "")
            if result_text is None:
                result_text = ""

            result_text = result_text.strip()

            # Try direct JSON parse first
            result = {}
            if result_text:
                try:
                    result = json.loads(result_text)
                except json.JSONDecodeError:
                    # Try to find a JSON object within the text by locating first { and last }
                    first = result_text.find("{")
                    last = result_text.rfind("}")
                    if first != -1 and last != -1 and last > first:
                        candidate = result_text[first : last + 1]
                        try:
                            result = json.loads(candidate)
                        except json.JSONDecodeError:
                            # try a looser regex to capture {...}
                            m = re.search(r"\{[\s\S]*\}", result_text)
                            if m:
                                try:
                                    result = json.loads(m.group())
                                except json.JSONDecodeError:
                                    result = {}
                            else:
                                result = {}
                    else:
                        result = {}
            else:
                result = {}

            # Post-process values: trim whitespace/newlines; normalize integers
            processed: Dict[str, Any] = {}
            for key, expected in fields.items():
                expected_type = expected.get("type", "").lower()
                raw_value = result.get(key) if isinstance(result, dict) else None

                if raw_value is None:
                    processed[key] = None
                    continue

                # If model returned number as int already
                if expected_type == "integer":
                    # If value is int
                    if isinstance(raw_value, int):
                        processed[key] = raw_value
                        continue
                    # If string: strip, remove non-digits, convert
                    if isinstance(raw_value, str):
                        s = raw_value.strip()
                        # remove any non-digit characters
                        digits = re.sub(r"\D", "", s)
                        processed[key] = int(digits) if digits else None
                        continue
                    # else fallback
                    processed[key] = None
                else:
                    # for strings: just strip outer whitespace/newlines
                    if isinstance(raw_value, str):
                        processed[key] = raw_value.strip()
                    else:
                        processed[key] = raw_value

            # If LLM returned empty {} or all nulls, attempt a simple fallback for common numeric fields
            # (e.g., tax number detection) using regex on the raw_text.
            any_not_found = all(v is None for v in processed.values())
            if any_not_found:
                # Example fallback: look for 11-digit numbers (Turkish tax number)
                compact = re.sub(r"\s+", "", raw_text)
                tax_matches = re.findall(r"\d{11}", compact)
                if tax_matches:
                    # If the user requested a field that likely is tax number, fill it
                    for key, conf in fields.items():
                        name = conf.get("name", "").lower()
                        if "vergi" in name or "tax" in name:
                            # put first match
                            try:
                                processed[key] = int(tax_matches[0])
                            except Exception:
                                processed[key] = tax_matches[0]
            return processed
        except Exception as e:
            raise Exception(f"Ollama API error: {str(e)}")
