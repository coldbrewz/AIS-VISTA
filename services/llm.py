import json
from typing import Tuple, Optional
from pydantic import ValidationError
from google import genai
from google.genai import types
from schemas import SLAExtractionPayload
from config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

def extract_sla_data(image_bytes: bytes, caption: str, fallback_date: str) -> tuple[SLAExtractionPayload | None, str]:
    """
    Calls Gemini 2.5 Flash to extract SLA data from the image and caption.
    Returns (payload, error_string).
    """
    if not client:
        return None, "LLM client not configured. Please set GEMINI_API_KEY."

    prompt = f"""
    You are an automated SLA tracking assistant for a toll road company.
    Analyze the provided WhatsApp photo (which has a 'Marki' app watermark) and the user's caption.
    
    Extract the following information:
    1. 'kode': The unique work code (Kode). This is the anchor identifier. Look carefully at the watermark or caption. It is usually a combination of letters and numbers (e.g., PV-123).
    2. 'tanggal_perbaikan': The repair date. Look for it in the caption or watermark. If you cannot find any date in the caption or watermark, use this exact fallback date: {fallback_date}. You MUST format the final date strictly as 'YYYY-MM-DD HH:MM:SS' (e.g., "2026-05-22 15:52:00").
    3. 'metode_perbaikan': The repair method. (Only applicable for the PV sheet. Otherwise leave empty).
    4. 'sheet_name': Infer the exact sheet name by looking for one of the sheet codes embedded anywhere inside the 'kode' (e.g., if kode is "010126PV001", the sheet is "PV"). You MUST output exactly one of these 9 sheet names: PV, DR, FE, GR, SG, LC, RM, CA, WR.
    5. 'panjang': Extract the numeric value for 'panjang' (length) if mentioned in the caption. Otherwise leave empty.
    6. 'lebar': Extract the numeric value for 'lebar' (width) if mentioned in the caption. Otherwise leave empty.
    7. 'tebal': Extract the numeric value for 'tebal' (thickness) if mentioned in the caption. Otherwise leave empty.
    
    IMPORTANT: Prioritize any data explicitly written in the user's caption over the image watermark. If the caption provides the Kode or Date, trust the caption.
    
    Caption from sender: "{caption}"
    
    Return a raw JSON object containing these exactly 7 keys. Do not wrap in markdown blocks.
    """

    import time
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                )
            )
            break # Success, exit loop
        except Exception as e:
            if "503" in str(e) and attempt < 2:
                time.sleep(3) # Wait 3 seconds and try again
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
