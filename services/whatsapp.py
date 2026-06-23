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
    Sends a text message using the local WAHA Docker container.
    """
    url = f"{settings.WAHA_URL}/api/sendText"
    
    # WAHA requires chat IDs to end in @c.us for regular contacts
    chat_id = to_phone if "@" in to_phone else f"{to_phone}@c.us"
    
    payload = {
        "chatId": chat_id,
        "text": message,
        "session": session
    }
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Api-Key": settings.WAHA_API_KEY
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
