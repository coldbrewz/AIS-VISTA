import time
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import settings

# WAHA_URL is now dynamic via settings.WAHA_URL

# Setup robust session for WAHA API calls to prevent silent message drops
req_session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[408, 429, 500, 502, 503, 504])
req_session.mount("http://", HTTPAdapter(max_retries=retries))

def send_whatsapp_message(to_phone: str, message: str, session: str = "default"):
    """
    Sends a text message using the local WAHA Docker container with human-like typing simulation.
    """
    # WAHA requires chat IDs to end in @c.us for regular contacts
    chat_id = to_phone if "@" in to_phone else f"{to_phone}@c.us"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Api-Key": settings.WAHA_API_KEY
    }
    
    # --- ANTI-BAN SIMULATION ---
    try:
        # 1. Send Seen (read receipt)
        req_session.post(f"{settings.WAHA_URL}/api/sendSeen", json={"chatId": chat_id, "session": session}, headers=headers, timeout=5)
        
        # 2. Start Typing
        req_session.post(f"{settings.WAHA_URL}/api/startTyping", json={"chatId": chat_id, "session": session}, headers=headers, timeout=5)
        
        # FIX #8: Cap delay at 3s (was up to 7s) to prevent thread pool exhaustion during
        # burst message bursts. FastAPI default thread pool is 40 threads.
        # If 40 messages all sleep 7s, no new webhooks can be processed.
        delay = min(max(len(message) * 0.05, 1.5), 3.0)
        jitter = random.uniform(0.0, 0.5)
        time.sleep(delay + jitter)
        
        # 4. Stop Typing
        req_session.post(f"{settings.WAHA_URL}/api/stopTyping", json={"chatId": chat_id, "session": session}, headers=headers, timeout=5)
    except Exception as e:
        print(f"Warning: Failed during anti-ban simulation, proceeding to send: {e}")
    # ---------------------------
    
    url = f"{settings.WAHA_URL}/api/sendText"
    payload = {
        "chatId": chat_id,
        "text": message,
        "session": session
    }
    
    try:
        response = req_session.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending WAHA message: {e}")
        if e.response is not None:
            print(f"Response: {e.response.text}")
        return None
