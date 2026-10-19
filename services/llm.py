import base64
import json
import re
import time
from typing import Tuple, Optional
import requests
from pydantic import ValidationError
from schemas import SLAExtractionPayload
from config import settings


def extract_json_str(text: str) -> str:
    cleaned = text.strip()
    # Remove reasoning/thinking tags (e.g. <think>...</think>)
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE).strip()
    # Remove markdown code blocks if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    # Slice between the first { and the last }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return cleaned


def extract_sla_data(
    image_bytes: bytes, caption: str, fallback_date: str
) -> tuple[SLAExtractionPayload | None, str]:
    """
    Calls Vikey AI (OpenAI-compatible chat completions) to extract SLA data from image and caption.
    Returns (payload, error_string).
    """
    if not settings.VIKEY_API_KEY:
        return None, "LLM client not configured. Please set VIKEY_API_KEY in .env."

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
- for metode_perbaikan:
  If the sheet_name is "PV", you MUST map the method to one of the following official values by correcting any typos or spelling variations:
  * "CnP"
  * "Hotmix"
  * "Coldmix" (e.g., map "coolmix", "cold-mix", "colmix" to "Coldmix")
  * "Scrapmix" (e.g., map "scrap", "scrab" to "Scrapmix")
  * "Sealent" (e.g., map "sealen", "selent", "sealant" to "Sealent")
  * "Asphaltic Plug" (e.g., map "asphaltic", "plug", "asphalt" to "Asphaltic Plug")
  * "Marka" (e.g., map "marker", "mark" to "Marka")

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

    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.VIKEY_API_KEY}",
    }

    body = {
        "model": settings.VIKEY_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_image}"
                        },
                    },
                ],
            }
        ],
        "temperature": 0.0,
    }

    data_json = None
    for attempt in range(3):
        try:
            resp = requests.post(
                settings.VIKEY_BASE_URL,
                headers=headers,
                json=body,
                timeout=60,
            )
            if resp.status_code in [429, 500, 502, 503, 504] and attempt < 2:
                time.sleep(3)
                continue
            if resp.status_code != 200:
                return None, f"LLM API Error ({resp.status_code}): {resp.text}"
            data_json = resp.json()
            break
        except requests.exceptions.RequestException as e:
            if attempt < 2:
                time.sleep(3)
                continue
            return None, f"LLM Network Error: {str(e)}"

    if not data_json:
        return None, "Failed to get response from LLM."

    usage = data_json.get("usage")
    if usage:
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        print(f"📊 Token Usage -> Prompt: {prompt_tokens} | Output: {completion_tokens} | Total: {total_tokens}")

    choices = data_json.get("choices")
    if not choices or not isinstance(choices, list):
        return None, f"Unexpected LLM response format: {data_json}"

    raw_content = choices[0].get("message", {}).get("content", "")
    if not raw_content:
        return None, "LLM returned empty message content."

    try:
        json_str = extract_json_str(raw_content)
        data = json.loads(json_str)
        payload = SLAExtractionPayload(**data)
        return payload, ""
    except ValidationError as e:
        return None, f"Could not extract all required SLA fields. Details: {str(e)}"
    except json.JSONDecodeError:
        return None, f"Failed to parse JSON from LLM: {raw_content}"
    except Exception as e:
        return None, f"LLM Error: {str(e)}"
