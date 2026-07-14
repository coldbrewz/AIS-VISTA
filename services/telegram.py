import asyncio
import time
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
    # Rate-limit: track last QR fetch time to prevent WhatsApp account restrictions
    last_qr_fetch = 0
    QR_COOLDOWN_SECONDS = 30  # Minimum seconds between QR code generations
    
    print("TELEGRAM POLLER: Started listening for /qr and /status commands...")
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            resp = await asyncio.to_thread(requests.get, url, timeout=35)
            data = resp.json()
            if data.get("ok"):
                for result in data.get("result", []):
                    offset = result["update_id"] + 1
                    msg = result.get("message", {})
                    text = str(msg.get("text", "")).strip().lower()
                    chat_id = msg.get("chat", {}).get("id")
                    
                    authorized_ids = [cid.strip().strip('\"').strip('\'') for cid in str(settings.TELEGRAM_CHAT_ID).split(",") if cid.strip()]
                    if str(chat_id) not in authorized_ids:
                        continue

                    # /status - Check WAHA status WITHOUT generating a new QR (safe to spam)
                    if text == "/status":
                        try:
                            status_resp = await asyncio.to_thread(
                                requests.get,
                                f"{settings.WAHA_URL}/api/sessions?all=true",
                                headers=headers,
                                timeout=5
                            )
                            sessions = status_resp.json()
                            if sessions and isinstance(sessions, list):
                                s = sessions[0]
                                status_text = (
                                    f"📊 WAHA Status\n"
                                    f"• Session: {s.get('name', 'N/A')}\n"
                                    f"• Status: {s.get('status', 'N/A')}\n"
                                    f"• Engine: {s.get('engine', {}).get('engine', 'N/A')}"
                                )
                            else:
                                status_text = "⚠️ No active WAHA sessions found."
                        except Exception as e:
                            status_text = f"❌ Cannot reach WAHA: {e}"
                        
                        send_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                        await asyncio.to_thread(requests.post, send_url, data={"chat_id": chat_id, "text": status_text}, timeout=10)
                    
                    # /qr - Fetch QR code WITH rate-limiting
                    elif text == "/qr":
                        now = time.time()
                        elapsed = now - last_qr_fetch
                        
                        if elapsed < QR_COOLDOWN_SECONDS:
                            remaining = int(QR_COOLDOWN_SECONDS - elapsed)
                            warn_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                            await asyncio.to_thread(
                                requests.post, warn_url,
                                data={"chat_id": chat_id, "text": f"⏳ Cooldown active. Wait {remaining}s before requesting another QR.\n\n⚠️ Spamming /qr will get your WhatsApp account temporarily banned!\n\nUse /status to check without generating a new QR."},
                                timeout=10
                            )
                            continue
                        
                        print("TELEGRAM POLLER: Received /qr request!")
                        # Grab raw QR code image from WAHA
                        qr_headers = headers.copy()
                        qr_headers["Accept"] = "image/png"
                        qr_resp = await asyncio.to_thread(
                            requests.get,
                            f"{settings.WAHA_URL}/api/default/auth/qr",
                            headers=qr_headers,
                            timeout=60
                        )
                        last_qr_fetch = time.time()  # Update timestamp AFTER fetch
                        
                        if qr_resp.status_code == 200 and 'image' in qr_resp.headers.get('Content-Type', ''):
                            # Send as Photo so it opens instantly without downloading a file (combats QR expiration)
                            send_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendPhoto"
                            await asyncio.to_thread(
                                requests.post,
                                send_url,
                                data={"chat_id": chat_id, "caption": "📱 Live WAHA QR Code\nScan within 20 seconds!\n\n⚠️ Do NOT request another /qr until this one expires."},
                                files={"photo": ("qr.png", qr_resp.content, "image/png")},
                                timeout=20
                            )
                        else:
                            # send text error (might be already authenticated or WAHA is still booting)
                            err_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
                            await asyncio.to_thread(requests.post, err_url, data={"chat_id": chat_id, "text": f"Failed to grab QR. Either WAHA is still booting, or the bot is already logged in!\n\nUse /status to check."}, timeout=10)
        except requests.exceptions.ConnectionError:
            # Harmless network timeouts during long-polling
            pass
        except Exception as e:
            print(f"TELEGRAM POLLER ERROR: {e}")
        await asyncio.sleep(1)
