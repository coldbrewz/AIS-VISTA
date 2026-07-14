import requests
import os
import sys
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("WAHA_API_KEY")
if not api_key:
    print("WAHA_API_KEY not found in .env")
    sys.exit(1)

print("Fetching QR Code from WAHA...")
headers = {
    "X-Api-Key": api_key,
    "Accept": "image/png"
}

try:
    response = requests.get("http://localhost:3000/api/default/auth/qr", headers=headers)
    if response.status_code == 200:
        with open("qr.png", "wb") as f:
            f.write(response.content)
        print("Successfully downloaded qr.png!")
        os.startfile("qr.png")
    else:
        print(f"Failed to get QR code. Status: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"Error connecting to WAHA: {e}")
