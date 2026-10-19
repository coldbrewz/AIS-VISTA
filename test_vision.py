import sys
import time
import io
import json

# Ensure utf-8 output on Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PIL import Image, ImageDraw
from config import settings
from services.llm import extract_sla_data


def create_sample_image() -> bytes:
    """Create a dummy asphalt road patch image with watermark text."""
    img = Image.new("RGB", (800, 600), color=(70, 75, 80))
    draw = ImageDraw.Draw(img)
    # Draw simulated road patch rectangle
    draw.rectangle([200, 200, 600, 400], fill=(45, 48, 52), outline=(30, 30, 30), width=3)
    
    # Draw GPS / Timestamp watermark text (similar to GPS Map Camera app used by field workers)
    watermark = (
        "GPS MAP CAMERA\n"
        "Lat: -6.2088 | Long: 106.8456\n"
        "Time: 2026-05-20 14:32:15 WIB\n"
        "Location: Ruas Tol Jakarta - Cikampek KM 38+400"
    )
    draw.rectangle([10, 490, 500, 590], fill=(0, 0, 0))
    draw.text((20, 500), watermark, fill=(255, 255, 255))
    
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def run_test():
    print("=" * 60)
    print("VISTA LLM Vision Test - GLM-5.3-Flash via Vikey AI")
    print("=" * 60)
    
    if not settings.VIKEY_API_KEY:
        print("[!] Error: VIKEY_API_KEY is not set in .env")
        print("Please edit .env and set: VIKEY_API_KEY=your_vikey_api_key")
        return

    print(f"Provider URL : {settings.VIKEY_BASE_URL}")
    print(f"Model        : {settings.VIKEY_MODEL}")
    print("-" * 60)

    # 1. Determine image source
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith((".jpg", ".jpeg", ".png")):
        img_path = sys.argv[1]
        print(f"[i] Using image from file: {img_path}")
        with open(img_path, "rb") as f:
            img_bytes = f.read()
    else:
        print("[i] No image path provided. Creating synthetic road photo with GPS watermark...")
        img_bytes = create_sample_image()

    # 2. Determine caption
    if len(sys.argv) > 2:
        caption = sys.argv[2]
    else:
        # Default test caption with typos to test both OCR and typo correction
        caption = "Kode: 260520PV001\nMetode: coolmix\nPanjang: 1,5\nLebar: 0,8\nTebal: 0,05"

    print(f"[i] Test Caption:\n{caption}\n")
    print("[*] Sending request to Vikey AI...")
    
    start_time = time.time()
    payload, err = extract_sla_data(
        image_bytes=img_bytes,
        caption=caption,
        fallback_date="2026-05-20 00:00:00"
    )
    elapsed = time.time() - start_time

    print(f"[*] Response Time: {elapsed:.2f} seconds\n")

    if err:
        print(f"[!] Extraction Failed: {err}")
        return

    print("[+] Extraction Succeeded! Structured Payload:")
    print(json.dumps(payload.model_dump(), indent=2))
    
    print("-" * 60)
    print("Verification checklist:")
    print(f"- Kode detected       : {payload.kode} (expected: 260520PV001)")
    print(f"- Sheet name inferred : {payload.sheet_name} (expected: PV)")
    print(f"- Metode perbaikan    : {payload.metode_perbaikan} (raw or normalized)")
    print(f"- Tanggal perbaikan   : {payload.tanggal_perbaikan}")
    print(f"- Dimensions (P/L/T)  : P={payload.panjang}, L={payload.lebar}, T={payload.tebal}")
    print("=" * 60)


if __name__ == "__main__":
    run_test()
