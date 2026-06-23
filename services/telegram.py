import asyncio
import requests
from config import settings

def send_telegram_alert(text: str):
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": settings.TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print(f"Failed to send telegram alert: {e}")

async def telegram_poller():
    if not settings.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM POLLER: Bot token missing. Poller disabled.")
        return
        
    offset = 0
    headers = {"X-Api-Key": settings.WAHA_API_KEY}
    print("TELEGRAM POLLER: Started listening for /qr commands...")
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            resp = await asyncio.to_thread(requests.get, url, timeout=35)
            data = resp.json()
            if data.get("ok"):
                for result in data.get("result", []):
                    offset = result["update_id"] + 1
                    msg = result.get("message", {})
                    text = str(msg.get("text", ""))
                    chat_id = msg.get("chat", {}).get("id")
                    
                    if str(chat_id) == str(settings.TELEGRAM_CHAT_ID) and "/qr" in text:
                        print("TELEGRAM POLLER: Received /qr request!")
                        # Grab screenshot
                        qr_resp = await asyncio.to_thread(
                            requests.get,
                            "http://localhost:3000/api/screenshot?session=default",
                            headers=headers,
                            timeout=15
                        )
                        if qr_resp.status_code == 200:
                            # Send as document instead of photo to prevent Telegram from blurring/compressing the QR code
                            send_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendDocument"
                            await asyncio.to_thread(
                                requests.post,
                                send_url,
                                data={"chat_id": chat_id, "caption": "Live WAHA QR Code (Open the file to scan clearly!)"},
                                files={"document": ("qr.png", qr_resp.content, "image/png")},
                                timeout=20
                            )
                        else:
                            # send text error
                            err_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                            await asyncio.to_thread(requests.post, err_url, data={"chat_id": chat_id, "text": f"Failed to grab QR screenshot. HTTP {qr_resp.status_code}"}, timeout=10)
        except requests.exceptions.ConnectionError:
            # Harmless network timeouts during long-polling
            pass
        except Exception as e:
            print(f"TELEGRAM POLLER ERROR: {e}")
        await asyncio.sleep(1)
