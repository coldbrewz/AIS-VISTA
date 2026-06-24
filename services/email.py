import smtplib
from email.message import EmailMessage
import datetime
from config import settings

import asyncio
import imaplib
import email
import requests

def send_qr_email(screenshot_bytes: bytes, custom_subject: str = None, custom_body: str = None):
    if not settings.SMTP_SENDER or not settings.SMTP_PASSWORD:
        print("SMTP settings not configured. Cannot send email.")
        return
        
    msg = EmailMessage()
    msg['Subject'] = custom_subject if custom_subject else f"🚨 URGENT: WAHA Bot Logged Out - Scan QR Code"
    msg['From'] = settings.SMTP_SENDER
    msg['To'] = settings.ALERT_EMAIL

    default_body = f"""
    The WAHA bot has been logged out of WhatsApp (status: SCAN_QR_CODE).
    Reply to this email with the word 'QR' to request a fresh QR code at any time.
    
    Time detected: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    msg.set_content(custom_body if custom_body else default_body)
    
    # Attach the screenshot
    msg.add_attachment(screenshot_bytes, maintype='image', subtype='png', filename='waha_qr_code.png')
    
    try:
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_SENDER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        print(f"QR Code Email successfully sent to {settings.ALERT_EMAIL}")
    except Exception as e:
        print(f"Failed to send QR email: {e}")

async def email_poller():
    if not settings.SMTP_SENDER or not settings.SMTP_PASSWORD:
        print("EMAIL POLLER: SMTP credentials missing. Poller disabled.")
        return
        
    headers = {"X-Api-Key": settings.WAHA_API_KEY}
    print("EMAIL POLLER: Started listening for 'QR' email replies...")
    
    while True:
        try:
            mail = await asyncio.to_thread(imaplib.IMAP4_SSL, "imap.gmail.com")
            await asyncio.to_thread(mail.login, settings.SMTP_SENDER, settings.SMTP_PASSWORD)
            await asyncio.to_thread(mail.select, "inbox")
            
            status, messages = await asyncio.to_thread(mail.search, None, 'UNSEEN')
            if status == "OK" and messages[0]:
                for num in messages[0].split():
                    status, data = await asyncio.to_thread(mail.fetch, num, '(RFC822)')
                    if status == "OK":
                        msg = email.message_from_bytes(data[0][1])
                        subject = str(msg.get("Subject", "")).lower()
                        sender = str(msg.get("From", "")).lower()
                        
                        # Only respond to our own ALERT_EMAIL
                        if "qr" in subject and settings.ALERT_EMAIL.lower() in sender:
                            print("EMAIL POLLER: Received QR request via email reply!")
                            qr_resp = await asyncio.to_thread(
                                requests.get,
                                f"{settings.WAHA_URL}/api/screenshot?session=default",
                                headers=headers,
                                timeout=15
                            )
                            if qr_resp.status_code == 200:
                                import utils
                                cropped_qr = utils.crop_qr_code(qr_resp.content)
                                await asyncio.to_thread(
                                    send_qr_email, 
                                    cropped_qr, 
                                    "✅ Live WAHA QR Code Attached", 
                                    "Here is your fresh, live QR code. Please scan it immediately."
                                )
            await asyncio.to_thread(mail.logout)
        except Exception:
            pass
            
        await asyncio.sleep(15)
