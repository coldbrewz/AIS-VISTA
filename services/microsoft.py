import os
import base64
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import msal
from config import settings

def num_to_col_letter(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

def get_retry_session():
    session = requests.Session()
    try:
        retry = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "POST", "PATCH", "DELETE", "OPTIONS", "TRACE"]
        )
    except TypeError:
        retry = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "PUT", "POST", "PATCH", "DELETE", "OPTIONS", "TRACE"]
        )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

def get_ms_token():
    cache = msal.SerializableTokenCache()
    token_cache_path = os.environ.get("TOKEN_CACHE_PATH", "token_cache.bin")
    if os.path.exists(token_cache_path):
        with open(token_cache_path, "r") as f:
            cache.deserialize(f.read())
    app = msal.PublicClientApplication(
        settings.MICROSOFT_CLIENT_ID, 
        authority="https://login.microsoftonline.com/common", 
        token_cache=cache
    )
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(["Files.ReadWrite.All"], account=accounts[0])
        # FIX #5: Save the refreshed token cache back to disk immediately
        # Without this, MSAL refresh tokens eventually expire and auth breaks permanently
        if cache.has_state_changed:
            with open(token_cache_path, "w") as f:
                f.write(cache.serialize())
        if result and "access_token" in result:
            return result["access_token"]
        print(f"MSAL Silent Token Error: {result}")
    else:
        print("MSAL Error: No accounts found in token_cache.bin. The file might be for a different Client ID or empty.")
    raise Exception("Microsoft Authentication Failed. Please run auth_microsoft.py again.")

def encode_share_url(url: str) -> str:
    encoded = base64.urlsafe_b64encode(url.encode('utf-8')).decode('utf-8')
    return "u!" + encoded.rstrip('=')

def col_letter_to_num(letter: str) -> int:
    num = 0
    for c in letter.upper():
        if c.isalpha():
            num = num * 26 + (ord(c) - ord('A')) + 1
    return num

def col_num_to_letter(n: int) -> str:
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string

def find_col_letter(values, target_header, default_col, start_col_idx):
    for row_idx in range(min(10, len(values))):
        for col_idx, cell in enumerate(values[row_idx]):
            if str(cell).strip().lower() == target_header.lower():
                return col_num_to_letter(start_col_idx + col_idx)
    return default_col

def upload_photo_to_onedrive(file_bytes: bytes, filename: str, folder_path: str = "Dokumentasi SLA") -> str:
    token = get_ms_token()
    session = get_retry_session()
    
    # 1. Upload to the specified nested folder path
    upload_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}/{filename}:/content"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "image/jpeg"
    }
    resp = session.put(upload_url, headers=headers, data=file_bytes)
    resp.raise_for_status()
    item_id = resp.json()["id"]
    
    # 2. Create sharing link
    link_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/createLink"
    link_body = {"type": "view", "scope": "anonymous"}
    link_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    link_resp = session.post(link_url, headers=link_headers, json=link_body)
    link_resp.raise_for_status()
    
    return link_resp.json()["link"]["webUrl"]

def update_excel_row(share_url: str, sheet_name: str, kode: str, tanggal: str, link: str, metode: str = "", panjang: str = "", lebar: str = "", tebal: str = ""):
    token = get_ms_token()
    session = get_retry_session()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    encoded_url = encode_share_url(share_url)
    share_resp = session.get(f"https://graph.microsoft.com/v1.0/shares/{encoded_url}/driveItem", headers=headers, allow_redirects=False)
    
    # Robustly follow all redirects (Microsoft Graph heavily uses 308 redirects across tenants)
    redirects = 0
    while share_resp.status_code in [301, 302, 303, 307, 308] and redirects < 5:
        redirect_url = share_resp.headers.get("Location")
        if not redirect_url:
            break
        share_resp = session.get(redirect_url, headers=headers, allow_redirects=False)
        redirects += 1
            
    if share_resp.status_code not in [200, 201]:
        raise Exception(f"Microsoft API blocked the link. Status {share_resp.status_code}. Response: {share_resp.text}")
    try:
        drive_item = share_resp.json()
    except Exception:
        raise Exception(f"Microsoft API returned an empty or invalid response. Status {share_resp.status_code}. Raw text: '{share_resp.text}'")
    drive_id = drive_item["parentReference"]["driveId"]
    item_id = drive_item["id"]
    
    # 1. Skip usedRange entirely! It takes up to 90s (30s x 3 retries) to fail on large files.
    # We know Kode is always in column A, and headers are within A to AZ.
    start_col_str = "A"
    start_row = 1
    end_col_str = "AZ"
    end_row = 100000
    
    # CRITICAL PERFORMANCE FIX: Create an Excel Session FIRST!
    # Opening the workbook takes time. Creating a session keeps it open for all operations.
    session_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/createSession"
    session_resp = session.post(session_url, headers=headers, json={"persistChanges": True}, timeout=60)
    session_resp.raise_for_status()
    workbook_session_id = session_resp.json().get("id")
    
    # Add the session ID to the headers for all subsequent operations
    headers["workbook-session-id"] = workbook_session_id
    
    try:
    
        # 2. Use Excel's MATCH function on Microsoft's servers to find the row instantly
        match_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/functions/match"
        safe_sheet_name = f"'{sheet_name}'" if " " in sheet_name else sheet_name
        
        match_payload = {
            "lookupValue": str(kode).strip(),
            "lookupArray": {"address": f"{safe_sheet_name}!{start_col_str}{start_row}:{start_col_str}{end_row}"},
            "matchType": 0
        }
        
        match_resp = session.post(match_url, headers=headers, json=match_payload, timeout=30)
        match_resp.raise_for_status()
        match_data = match_resp.json()
        
        match_value = match_data.get("value")
        
        if not isinstance(match_value, int):
            raise Exception(f"Kode '{kode}' not found in sheet '{sheet_name}' (MATCH returned: {match_value})")
            
        actual_excel_row = start_row + match_value - 1
        start_col_idx = col_letter_to_num(start_col_str)
    
        # Dynamically fetch headers from Row 4 to handle shifted columns
        header_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='A4:BZ4')"
        header_resp = session.get(header_url, headers=headers, timeout=15)
        header_resp.raise_for_status()
        header_values = header_resp.json().get("values", [[]])[0]
        
        def find_col(header_name, default_col):
            for i, val in enumerate(header_values):
                if str(val).strip() == header_name:
                    return num_to_col_letter(i + 1)
            return default_col
            
        col_tanggal = find_col("TANGGAL PERBAIKAN", "T")
        col_link = find_col("LINK DOKUMENTASI", "U")
        
        # FIX #2: Re-acquire a fresh token right before writes to avoid 401 mid-operation
        fresh_token = get_ms_token()
        headers["Authorization"] = f"Bearer {fresh_token}"
        
        t_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_tanggal}{actual_excel_row}')"
        doc_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_link}{actual_excel_row}')"
        
        def safe_patch(url, val, name):
            import time
            for attempt in range(3):
                try:
                    resp = session.patch(url, headers=headers, json={"values": [[val]]}, timeout=15)
                    if resp.ok:
                        return
                    if resp.status_code in (429, 500, 502, 503, 504):
                        time.sleep(2 ** attempt)
                        continue
                    raise Exception(f"Microsoft Graph rejected update for {name} ({val}) at {url}. Status {resp.status_code}: {resp.text}")
                except Exception as e:
                    if attempt == 2:
                        raise Exception(f"Network error on Microsoft Graph API for {name}: {e}")
                    time.sleep(2 ** attempt)
            raise Exception(f"Failed to update {name} after 3 network retries.")
                
        safe_patch(t_url, tanggal, "Tanggal")
        safe_patch(doc_url, link, "Link")
    
        if sheet_name.upper() == "PV":
            col_metode = find_col("METODE PERBAIKAN", "X")
            col_panjang = find_col("Panjang_Realisasi", "AE")
            col_lebar = find_col("Lebar_Realisasi", "AF")
            col_tebal = find_col("Tebal_Realisasi", "AG")
            
            if metode:
                m_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_metode}{actual_excel_row}')"
                safe_patch(m_url, metode, "Metode")
                
            if panjang:
                p_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_panjang}{actual_excel_row}')"
                safe_patch(p_url, panjang, "Panjang")
            if lebar:
                l_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_lebar}{actual_excel_row}')"
                safe_patch(l_url, lebar, "Lebar")
            if tebal:
                t_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_tebal}{actual_excel_row}')"
                safe_patch(t_url, tebal, "Tebal")
    finally:
        # ALWAYS close the session so the Excel file doesn't stay locked for other users!
        try:
            close_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/closeSession"
            session.post(close_url, headers=headers, timeout=10)
        except Exception as e:
            print(f"Warning: Failed to close Excel session: {e}")

    return True
