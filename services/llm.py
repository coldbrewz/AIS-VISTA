import base64
import io
import json
import re
import time
from typing import Tuple, Optional
from PIL import Image
import requests
from pydantic import ValidationError
from schemas import SLAExtractionPayload
from config import settings


def prepare_image_for_llm(image_bytes: bytes, max_size: int = 1536, quality: int = 85) -> str:
    """
    Resizes and compresses images to prevent HTTP 413 (Payload Too Large) errors
    while preserving high OCR clarity for watermarks.
    Returns base64 encoded string.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
            width, height = img.size
            if max(width, height) > max_size:
                scale = max_size / max(width, height)
                new_size = (int(width * scale), int(height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"Warning: Image compression for LLM failed ({e}), using raw bytes.")
        return base64.b64encode(image_bytes).decode("utf-8")


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

priority and source rules:
1. caption overrides image for defect codes, methods, and dimensions.
2. for tanggal_perbaikan (date and time):
   - ALWAYS look for the camera watermark on the photo (e.g. Marki camera box, GPS Map Camera stamp, clock icon 🕒 like "13:44 Senin 19-10-2026").
   - extract the EXACT TIME (hour and minute, e.g. "13:44" -> 13:44:00).
   - if caption only provides the date (e.g. "19-10-2026" or "19/10/2026") without hour/minute, you MUST combine the date from caption with the exact time from the image watermark.
   - NEVER output 00:00:00 if an exact time is visible on the image watermark.
   - if caption explicitly contains both date AND time (e.g. "19-10-2026 13:44"), use both from caption.
   - if no date or time can be found on either caption or watermark, use fallback: {fallback_date}.
3. return json only.
4. no explanations.
5. no markdown.
6. no extra fields.

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
- extract sheet code from kode (letters in kode like PV, DR, FE, GR, SG, LC, RM, CA, WR).
- if not in kode, infer from image or watermark context (e.g. guardrail -> GR, perkerasan -> PV, drainase -> DR).
- valid values:
  PV, DR, FE, GR, SG, LC, RM, CA, WR
- otherwise ""

date rules:
- output format:
  YYYY-MM-DD HH:MM:SS
- format examples:
  - if watermark has "13:44 Senin 19-10-2026" -> output "2026-10-19 13:44:00"
  - if caption has "19-10-2026" and watermark has "13:44" -> output "2026-10-19 13:44:00"
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

    b64_image = prepare_image_for_llm(image_bytes)

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
        print(f"[Token Usage] Prompt: {prompt_tokens} | Output: {completion_tokens} | Total: {total_tokens}")

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


def extract_opname_form_ocr(
    page_images: list[bytes],
    aset_hint: str,
    caption: str,
    boq_menu_text: str,
) -> tuple[dict, str]:
    """
    High-resolution Vision OCR for standardized A4 opname forms (photo or PDF pages).
    Prioritizes handwritten edits in `Vol. Opname` over printed `Vol. Vendor`, grounded strictly on `boq_menu_text`.
    Returns: ({"aset": ..., "vendor": ..., "wilayah": ..., "minggu": ..., "rows": [...]}, error_str)
    """
    if not page_images:
        return {}, "Tidak ada halaman gambar opname untuk dibaca."
    if not settings.VIKEY_API_KEY:
        return {}, "LLM client not configured. Please set VIKEY_API_KEY in .env."

    model_name = (settings.VIKEY_OCR_MODEL or settings.VIKEY_MODEL).strip() or settings.VIKEY_MODEL
    prompt = (
        f"You are an expert civil engineering opname OCR reader for Indonesian toll road forms.\n"
        f"Context hint from user: Aset='{aset_hint or 'auto'}', Caption='{caption or '-'}'.\n\n"
        f"Instructions:\n"
        f"1. Read header fields if visible: aset (PV/GR/SG/WR/RM/LC/CA/DR/FE), vendor, wilayah (W1/W2), minggu (M1/M2/M3/M4).\n"
        f"2. Read every non-empty row from the opname table. IGNORE completely empty blank rows.\n"
        f"3. CRITICAL: If a number in `Vol. Vendor` is crossed out and replaced by a handwritten number in `Vol. Opname` (or margin note), extract BOTH `vol_vendor` and the handwritten `vol_opname`, and set `handwritten_edited: true`.\n"
        f"4. Map `raw_item` strictly using the closest exact keyword or item_key from the BOQ menu below when available.\n"
        f"5. Return valid JSON ONLY (no markdown fences, no commentary):\n"
        f'{{"aset": "", "vendor": "", "wilayah": "", "minggu": "", "rows": ['
        f'{{"tanggal": "YYYY-MM-DD", "kode_temuan": "", "wilayah": "", "vendor": "", "lokasi": "", "jalur": "", "lajur": "", "raw_item": "", "p": null, "l": null, "t": null, "jml": null, "vol_vendor": null, "vol_opname": null, "keterangan": "", "handwritten_edited": false}}'
        f"]}}\n\n"
        f"OFFICIAL BOQ MENU:\n{boq_menu_text}"
    )

    content_parts: list[dict] = [{"type": "text", "text": prompt}]
    for img_bytes in page_images[:5]:
        b64_page = prepare_image_for_llm(img_bytes, max_size=2048, quality=88)
        content_parts.append(
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_page}"}}
        )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.VIKEY_API_KEY}",
    }
    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": content_parts}],
        "temperature": 0.0,
    }

    for attempt in range(3):
        try:
            resp = requests.post(settings.VIKEY_BASE_URL, headers=headers, json=body, timeout=90)
            if resp.status_code in [429, 500, 502, 503, 504] and attempt < 2:
                time.sleep(3)
                continue
            if resp.status_code != 200:
                return {}, f"OCR LLM API Error ({resp.status_code}): {resp.text}"
            data_json = resp.json()
            raw_content = data_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not raw_content:
                break
            parsed = json.loads(extract_json_str(raw_content))
            return parsed if isinstance(parsed, dict) else {}, ""
        except Exception as e:
            if attempt == 2:
                return {}, f"OCR LLM Error: {e}"
            time.sleep(2)

    return {}, "Failed to extract table rows from opname scan."
