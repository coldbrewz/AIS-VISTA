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


def _read_chat_completion_content(resp: requests.Response, max_seconds: float | None = None) -> str:
    """Read message text from either an SSE stream or a standard JSON chat completion."""
    hdrs = {str(k).lower(): str(v) for k, v in (getattr(resp, "headers", None) or {}).items()}
    ctype = hdrs.get("content-type", "").lower()
    deadline = (time.monotonic() + max_seconds) if max_seconds else None
    if "text/event-stream" in ctype:
        parts: list[str] = []
        for raw_line in resp.iter_lines(decode_unicode=True):
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"OCR SSE stream exceeded {int(max_seconds)}s total limit")
            line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else (raw_line or "")
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            payload_str = line[5:].strip()
            if payload_str == "[DONE]":
                break
            try:
                chunk = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            if not isinstance(chunk, dict):
                continue
            choices = chunk.get("choices") or []
            if not choices or not isinstance(choices, list) or not isinstance(choices[0], dict):
                continue
            delta = choices[0].get("delta") or choices[0].get("message") or {}
            piece = delta.get("content") if isinstance(delta, dict) else ""
            if piece:
                parts.append(str(piece))
        return "".join(parts)

    if callable(getattr(resp, "iter_content", None)):
        raw_buf = bytearray()
        for chunk in resp.iter_content(chunk_size=4096):
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"OCR response exceeded {int(max_seconds)}s total limit")
            if chunk:
                raw_buf.extend(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
        body_text = raw_buf.decode("utf-8", errors="replace")
        try:
            data_json = json.loads(body_text)
        except json.JSONDecodeError as je:
            raise ValueError(
                f"Invalid API JSON (ctype={ctype or 'unknown'}, len={len(body_text)}, sample={body_text[:120]!r}): {je}"
            ) from je
    else:
        data_json = resp.json()
    if not isinstance(data_json, dict):
        return ""
    choices = data_json.get("choices") or []
    if not choices or not isinstance(choices, list) or not isinstance(choices[0], dict):
        return ""
    return str(choices[0].get("message", {}).get("content", "") or "")


def _verify_handwritten_edits_on_page(
    img_bytes: bytes,
    page_rows: list[dict],
    model_name: str,
    headers: dict[str, str],
    p_idx: int,
    total_pages: int,
) -> None:
    """
    Focused second pass for rows flagged as edited/crossed-out on a form page.
    Reads ONLY handwritten pen replacements without back-calculating from `Vol. Vendor`.
    """
    flagged = [
        {
            "row_index": idx,
            "row_no": str(r.get("row_no") or "").strip(),
            "lokasi": str(r.get("lokasi") or "").strip(),
            "raw_item": str(r.get("raw_item") or "").strip(),
            "current": {
                k: r.get(k)
                for k in ("p", "l", "t", "jml", "vol_vendor", "vol_opname")
                if r.get(k) is not None
            },
        }
        for idx, r in enumerate(page_rows)
        if isinstance(r, dict) and (r.get("handwritten_edited") or r.get("dimension_edited"))
    ]
    if not flagged:
        return

    b64_hi = prepare_image_for_llm(img_bytes, max_size=1800, quality=84)
    img2_kb = max(1, (len(b64_hi) * 3) // (4 * 1024))
    verify_prompt = (
        "Inspect ONLY the highlighted rows below on this scanned toll road opname form.\n"
        "A printed number in `P`, `L`, `T`, `Jml`, or `Vol. Vendor` was crossed out or scribbled over with pen ink, "
        "and a NEW handwritten number was written next to it inside the same cell.\n\n"
        "Rules:\n"
        "1. Read ONLY the handwritten pen ink carefully (digit by digit, decimal comma `,` becomes `.`, e.g. `5,4` -> `5.4`, `1,2` -> `1.2`, `2,9` -> `2.9`).\n"
        "2. Separate the crossed-out printed value into `crossed_out_printed`, and put ONLY the uncrossed handwritten number into `handwritten_replacement`.\n"
        "3. NEVER back-calculate `P`, `L`, `T`, or `Jml` from `Vol. Vendor` - the handwritten replacement intentionally changes the volume.\n"
        "4. Return valid JSON ONLY:\n"
        '{"corrections": [{"row_index": 0, "row_no": "", "field": "p", "crossed_out_printed": 6.1, "handwritten_replacement": 5.4}]}\n\n'
        f"FLAGGED ROWS TO VERIFY:\n{json.dumps(flagged, ensure_ascii=False)}"
    )
    body = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": verify_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_hi}"}},
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 1024,
        "stream": True,
    }
    t0 = time.monotonic()
    try:
        print(
            f"[Opname OCR] Page {p_idx}/{total_pages} | sending Pass 2 (flagged={len(flagged)}, img={img2_kb}KB)...",
            flush=True,
        )
        with requests.post(
            settings.VIKEY_BASE_URL,
            headers=headers,
            json=body,
            timeout=(15, 40),
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                print(
                    f"[Opname OCR] Page {p_idx}/{total_pages} | Pass 2 skipped (HTTP {resp.status_code})",
                    flush=True,
                )
                return
            raw_content = _read_chat_completion_content(resp, max_seconds=45.0)
        elapsed = time.monotonic() - t0
        if not raw_content:
            return
        parsed = json.loads(extract_json_str(raw_content))
        corrections = parsed.get("corrections") if isinstance(parsed, dict) else []
        if not isinstance(corrections, list):
            return

        applied = 0
        for corr in corrections:
            if not isinstance(corr, dict):
                continue
            field = str(corr.get("field") or "").strip().lower()
            if field not in ("p", "l", "t", "jml", "vol_opname"):
                continue
            raw_val = corr.get("handwritten_replacement")
            if raw_val is None or isinstance(raw_val, bool):
                continue
            try:
                new_num = float(str(raw_val).strip().replace(",", "."))
            except (TypeError, ValueError):
                continue
            if new_num <= 0:
                continue

            target_idx = None
            raw_ri = corr.get("row_index")
            raw_rno = str(corr.get("row_no") or "").strip()
            if isinstance(raw_ri, int) and 0 <= raw_ri < len(page_rows):
                cand_rno = str(page_rows[raw_ri].get("row_no") or "").strip()
                if not raw_rno or cand_rno in ("", raw_rno):
                    target_idx = raw_ri
            if target_idx is None and raw_rno:
                for cand_i, cand_r in enumerate(page_rows):
                    if isinstance(cand_r, dict) and str(cand_r.get("row_no") or "").strip() == raw_rno:
                        target_idx = cand_i
                        break
            if target_idx is None:
                continue

            row = page_rows[target_idx]
            row[field] = round(new_num, 4)
            row["handwritten_edited"] = True
            if field in ("p", "l", "t", "jml"):
                row["dimension_edited"] = True
            applied += 1

        print(
            f"[Opname OCR] Page {p_idx}/{total_pages} | verified {applied} handwritten correction(s) in {elapsed:.1f}s",
            flush=True,
        )
    except Exception as e:
        print(f"[Opname OCR] Page {p_idx}/{total_pages} | Pass 2 warning: {e}", flush=True)


def extract_opname_form_ocr(
    page_images: list[bytes],
    aset_hint: str,
    caption: str,
    boq_menu_text: str,
) -> tuple[dict, str]:
    """
    Per-page streaming Vision OCR for standardized A4 opname forms (photo or PDF pages).
    Prioritizes handwritten edits in `Vol. Opname` and revised dimensions, grounded strictly on `boq_menu_text`.
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
        f"1. Read header fields if visible: aset (PV/GR/SG/WR/RM/LC/CA/DR/FE), wilayah (W1/W2) and vendor from top header box or rows, minggu (M1/M2/M3/M4/M5).\n"
        f"2. Read every non-empty row from the main opname table (include the printed `No.` value in `row_no`). IGNORE completely empty blank rows, and IGNORE the bottom `REKAP VOLUME PER ITEM` summary table and signature block. If a page ONLY contains summary rows or signatures, return `{{\"rows\": []}}`.\n"
        f"   If Tanggal, Minggu, Kode Temuan, or STA/Jalur/Lajur are left blank on subsequent rows at the same location ('ditto'), carry forward the values from the row above.\n"
        f"3. CRITICAL: When a printed number in `P`, `L`, `T`, or `Jml` is scribbled/crossed out (often right-aligned) and a handwritten pen number is written next to it (often on the left), extract ONLY the uncrossed handwritten number into `p`, `l`, `t`, or `jml`, and set `dimension_edited: true` and `handwritten_edited: true`.\n"
        f"   Convert Indonesian comma decimals to dots (e.g. `5,4` -> `5.4`, `1,2` -> `1.2`, `2,9` -> `2.9`). NEVER back-calculate `P`, `L`, `T`, or `Jml` from `Vol. Vendor`.\n"
        f"4. CRITICAL: Leave `vol_opname` as `null` when the `Vol. Opname` column is blank on paper (do NOT copy `vol_vendor` and do NOT mentally multiply dimensions into `vol_opname`). If a handwritten number is explicitly written in `Vol. Opname` (or crossed out in `Vol. Vendor` and replaced), extract both `vol_vendor` and handwritten `vol_opname`, and set `handwritten_edited: true`.\n"
        f"5. Map `raw_item` strictly using the closest exact keyword or item_key from the BOQ menu below when available.\n"
        f"6. Return valid JSON ONLY (no markdown fences, no commentary):\n"
        f'{{"aset": "", "vendor": "", "wilayah": "", "minggu": "", "rows": ['
        f'{{"row_no": "", "tanggal": "YYYY-MM-DD", "kode_temuan": "", "wilayah": "", "vendor": "", "lokasi": "", "jalur": "", "lajur": "", "raw_item": "", "p": null, "l": null, "t": null, "jml": null, "vol_vendor": null, "vol_opname": null, "keterangan": "", "dimension_edited": false, "handwritten_edited": false}}'
        f"]}}\n\n"
        f"OFFICIAL BOQ MENU:\n{boq_menu_text}"
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.VIKEY_API_KEY}",
    }

    pages = page_images[:5]
    total_pages = len(pages)
    merged: dict = {"aset": "", "vendor": "", "wilayah": "", "minggu": "", "rows": []}
    last_err = ""

    for p_idx, img_bytes in enumerate(pages, start=1):
        b64_page = prepare_image_for_llm(img_bytes, max_size=1600, quality=82)
        img_kb = max(1, (len(b64_page) * 3) // (4 * 1024))
        body = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_page}"}},
                    ],
                }
            ],
            "temperature": 0.0,
            "max_tokens": 4096,
            "stream": True,
        }

        page_ok = False
        for attempt in range(2):
            t0 = time.monotonic()
            try:
                print(
                    f"[Opname OCR] Page {p_idx}/{total_pages} | sending Pass 1 (model={model_name}, img={img_kb}KB, attempt {attempt + 1}/2)...",
                    flush=True,
                )
                with requests.post(
                    settings.VIKEY_BASE_URL,
                    headers=headers,
                    json=body,
                    timeout=(15, 60),
                    stream=True,
                ) as resp:
                    if resp.status_code in [429, 500, 502, 503, 504] and attempt == 0:
                        print(
                            f"[Opname OCR] Page {p_idx}/{total_pages} | model={model_name} | HTTP {resp.status_code} retrying...",
                            flush=True,
                        )
                        time.sleep(2)
                        continue
                    if resp.status_code != 200:
                        last_err = f"OCR LLM API Error ({resp.status_code}): {resp.text}"
                        print(f"[Opname OCR] Page {p_idx}/{total_pages} HTTP error: {last_err}", flush=True)
                        break
                    raw_content = _read_chat_completion_content(resp, max_seconds=90.0)
                elapsed = time.monotonic() - t0
                if not raw_content:
                    last_err = f"Page {p_idx}: empty OCR response"
                    if attempt == 0:
                        time.sleep(2)
                        continue
                    break
                try:
                    parsed = json.loads(extract_json_str(raw_content))
                except json.JSONDecodeError as je:
                    raise ValueError(
                        f"Invalid OCR JSON (len={len(raw_content)}, sample={raw_content[:120]!r}): {je}"
                    ) from je
                if not isinstance(parsed, dict):
                    raise ValueError("OCR JSON root is not an object")
                page_rows = parsed.get("rows") or []
                if not isinstance(page_rows, list):
                    page_rows = []
                page_rows = [r for r in page_rows if isinstance(r, dict)]
                print(
                    f"[Opname OCR] Page {p_idx}/{total_pages} | model={model_name} | img={img_kb}KB | "
                    f"{elapsed:.1f}s | rows={len(page_rows)}",
                    flush=True,
                )
                _verify_handwritten_edits_on_page(
                    img_bytes,
                    page_rows,
                    model_name,
                    headers,
                    p_idx,
                    total_pages,
                )
                for key in ("aset", "vendor", "wilayah", "minggu"):
                    if not merged[key] and parsed.get(key):
                        merged[key] = str(parsed.get(key)).strip()
                merged["rows"].extend(page_rows)
                page_ok = True
                break
            except Exception as e:
                elapsed = time.monotonic() - t0
                last_err = f"OCR LLM Error: {e}"
                print(
                    f"[Opname OCR] Page {p_idx}/{total_pages} failed in {elapsed:.1f}s "
                    f"(attempt {attempt + 1}/2): {e}",
                    flush=True,
                )
                if attempt == 0:
                    time.sleep(2)

        if not page_ok and merged["rows"]:
            print(
                f"[Opname OCR] Warning: Page {p_idx} failed ({last_err}); "
                f"returning {len(merged['rows'])} row(s) from earlier pages.",
                flush=True,
            )

    if merged["rows"]:
        return merged, ""
    if last_err:
        return {}, last_err
    return {}, "Failed to extract table rows from opname scan."
