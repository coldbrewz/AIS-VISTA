import io
from PIL import Image

def crop_qr_code(image_bytes: bytes) -> bytes:
    """
    Takes a full-page WAHA screenshot and crops it to the right half
    so the QR code is prominent and easier to scan on mobile devices.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        
        # WhatsApp Web QR code is consistently on the right side of the screen
        left = int(w * 0.5)
        top = int(h * 0.1)
        right = int(w * 0.95)
        bottom = int(h * 0.9)
        
        cropped_img = img.crop((left, top, right, bottom))
        
        out_bytes = io.BytesIO()
        cropped_img.save(out_bytes, format="PNG")
        return out_bytes.getvalue()
    except Exception as e:
        print(f"Failed to crop QR code image: {e}")
        return image_bytes # Fallback to original image if anything goes wrong
