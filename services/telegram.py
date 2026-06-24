import asyncio
import requests
from config import settings

def send_telegram_alert(text: str):
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        chat_ids = [cid.strip().strip('\"').strip('\'') for cid in str(settings.TELEGRAM_CHAT_ID).split(",") if cid.strip()]
        for cid in chat_ids:
            requests.post(url, data={"chat_id": cid, "text": text}, timeout=10)
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
                    
                    authorized_ids = [cid.strip().strip('\"').strip('\'') for cid in str(settings.TELEGRAM_CHAT_ID).split(",") if cid.strip()]
                    if str(chat_id) in authorized_ids and "/qr" in text:
                        print("TELEGRAM POLLER: Received /qr request!")
                        # Grab raw QR code image from WAHA
                        qr_resp = await asyncio.to_thread(
                            requests.get,
                            f"{settings.WAHA_URL}/api/default/auth/qr",
                            headers=headers,
                            timeout=15
                        )
                        if qr_resp.status_code == 200 and 'image' in qr_resp.headers.get('Content-Type', ''):
                            # Send as Photo so it opens instantly without downloading a file (combats QR expiration)
                            send_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendPhoto"
                            await asyncio.to_thread(
                                requests.post,
                                send_url,
                                data={"chat_id": chat_id, "caption": "Live WAHA QR Code (Scan immediately!)"},
                                files={"photo": ("qr.png", qr_resp.content, "image/png")},
                                timeout=20
                            )
                        else:
                            # send text error (might be already authenticated or WAHA is still booting)
                            err_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                            await asyncio.to_thread(requests.post, err_url, data={"chat_id": chat_id, "text": f"Failed to grab QR. Either WAHA is still booting, or the bot is already logged in!"}, timeout=10)
        except requests.exceptions.ConnectionError:
            # Harmless network timeouts during long-polling
            pass
        except Exception as e:
            print(f"TELEGRAM POLLER ERROR: {e}")
        await asyncio.sleep(1)
