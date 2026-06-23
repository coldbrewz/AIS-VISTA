import msal
import os
import atexit
from config import settings

# Setup configuration
CLIENT_ID = settings.MICROSOFT_CLIENT_ID
# We use 'common' to allow both personal and organizational Microsoft accounts
AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES = ["Files.ReadWrite.All"]

# Setup Token Cache
cache = msal.SerializableTokenCache()
if os.path.exists("token_cache.bin"):
    cache.deserialize(open("token_cache.bin", "r").read())

# Save cache automatically when program exits
atexit.register(lambda:
    open("token_cache.bin", "w").write(cache.serialize())
    if cache.has_state_changed else None
)

app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

def authenticate():
    accounts = app.get_accounts()
    result = None

    if accounts:
        print(f"Found saved account: {accounts[0]['username']}. Attempting to use saved token...")
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        print("No valid token found. Popping open browser for you to log in...")
        result = app.acquire_token_interactive(scopes=SCOPES, port=8400)

    if "access_token" in result:
        print("\n✅ SUCCESS! Authenticated with Microsoft.")
        print("Your token is securely saved in 'token_cache.bin'. The bot will now use this forever!")
    else:
        print("\n❌ FAILED to authenticate.")
        print(result.get("error"))
        print(result.get("error_description"))

if __name__ == "__main__":
    authenticate()
