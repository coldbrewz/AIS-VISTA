import requests
from config import settings

WAHA_URL = "http://localhost:3000"

def send_whatsapp_message(to_phone: str, message: str, session: str = "default"):
    """
    Sends a text message using the local WAHA Docker container.
    """
    url = f"{WAHA_URL}/api/sendText"
    
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
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending WAHA message: {e}")
        if e.response is not None:
            print(f"Response: {e.response.text}")
        return None
