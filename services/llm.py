import json
from typing import Tuple, Optional
from pydantic import ValidationError
from google import genai
from google.genai import types
from schemas import SLAExtractionPayload
from config import settings

client = (
    genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None
)


def extract_sla_data(
    image_bytes: bytes, caption: str, fallback_date: str
) -> tuple[SLAExtractionPayload | None, str]:
    """
    Calls Gemini 2.5 Flash to extract SLA data from the image and caption.
    Returns (payload, error_string).
    """
    if not client:
        return None, "LLM client not configured. Please set GEMINI_API_KEY."

    prompt = f"""you are an automated sla tracking assistant for a toll road company.
analyze the image and whatsapp caption.

priority rules:
1. caption overrides image.
2. return json only.
3. no explanations.
4. no markdown.
5. no extra fields.

extract:
- kode
- tanggal_perbaikan
- metode_perbaikan
- sheet_name
- panjang
- lebar
- tebal

extraction rules:
- for panjang, lebar, tebal: extract the numbers precisely regardless of messy spacing, missing spaces, colons, commas, or typos (e.g., "Tebal:0,07" -> "0,07").

sheet_name rules:
- extract sheet code from kode
- valid values:
  PV, DR, FE, GR, SG, LC, RM, CA, WR
- otherwise ""

date rules:
- output format:
  YYYY-MM-DD HH:MM:SS
- if date not found use:
  {fallback_date}

missing values:
- use ""

caption:
{caption}

return exactly:
{{
  "kode":"",
  "tanggal_perbaikan":"",
  "metode_perbaikan":"",
  "sheet_name":"",
  "panjang":"",
  "lebar":"",
  "tebal":""
}}"""

    import time

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SLAExtractionPayload,
                    temperature=0.0,
                ),
            )
            if response.usage_metadata:
                print(f"📊 Token Usage -> Prompt: {response.usage_metadata.prompt_token_count} | Output: {response.usage_metadata.candidates_token_count} | Total: {response.usage_metadata.total_token_count}")
            break  # Success, exit loop
        except Exception as e:
            if "503" in str(e) and attempt < 2:
                time.sleep(3)  # Wait 3 seconds and try again
                continue
            return None, f"LLM Error: {str(e)}"

    try:
        data = json.loads(response.text)
        payload = SLAExtractionPayload(**data)
        return payload, ""

    except ValidationError as e:
        return None, f"Could not extract all required SLA fields. Details: {str(e)}"
    except json.JSONDecodeError:
        return None, "Failed to parse JSON from Gemini."
    except Exception as e:
        return None, f"LLM Error: {str(e)}"
