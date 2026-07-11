import os
import base64
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import msal
from config import settings

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
    if os.path.exists("token_cache.bin"):
        with open("token_cache.bin", "r") as f:
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
            with open("token_cache.bin", "w") as f:
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
    end_row = 20000
    
    # 2. Use Excel's MATCH function on Microsoft's servers to find the row instantly
    # This completely bypasses downloading the massive column and prevents 504 Timeouts!
    match_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/functions/match"
    # Ensure sheet name with spaces is properly quoted for the address
    safe_sheet_name = f"'{sheet_name}'" if " " in sheet_name else sheet_name
    
    match_payload = {
        "lookupValue": str(kode).strip(),
        # Passing just the string address often fails in Graph, it needs a Range reference object
        "lookupArray": {"address": f"{safe_sheet_name}!{start_col_str}{start_row}:{start_col_str}{end_row}"},
        "matchType": 0  # 0 = exact match
    }
    
    match_resp = session.post(match_url, headers=headers, json=match_payload, timeout=15)
    match_resp.raise_for_status()
    match_data = match_resp.json()
    
    match_value = match_data.get("value")
    
    # If not found, Excel returns "#N/A" string or similar error value instead of an integer
    if not isinstance(match_value, int):
        raise Exception(f"Kode '{kode}' not found in sheet '{sheet_name}' (MATCH returned: {match_value})")
        
    # MATCH returns a 1-based relative index. 
    # If start_row is 1, and match is 1st item, actual row is 1 + 1 - 1 = 1
    actual_excel_row = start_row + match_value - 1
    start_col_idx = col_letter_to_num(start_col_str)
    
    # 3. Fetch ONLY the first 10 rows to find the headers
    header_end = min(start_row + 9, end_row)
    header_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{start_col_str}{start_row}:{end_col_str}{header_end}')?$select=values"
    header_resp = session.get(header_url, headers=headers, timeout=30)
    header_resp.raise_for_status()
    header_values = header_resp.json().get("values", [])
    
    col_tanggal = find_col_letter(header_values, "TANGGAL PERBAIKAN", "T", start_col_idx)
    col_link = find_col_letter(header_values, "LINK DOKUMENTASI PERBAIKAN", "U", start_col_idx)
    
    # FIX #2: Re-acquire a fresh token right before writes to avoid 401 mid-operation
    # The read phase (usedRange, kode column, headers) can take 30-90 seconds total.
    # The original token may have expired by the time we reach here.
    fresh_token = get_ms_token()
    headers["Authorization"] = f"Bearer {fresh_token}"
    
    t_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_tanggal}{actual_excel_row}')"
    session.patch(t_url, headers=headers, json={"values": [[tanggal]]}).raise_for_status()
    
    doc_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_link}{actual_excel_row}')"
    session.patch(doc_url, headers=headers, json={"values": [[link]]}).raise_for_status()
    
    if sheet_name.upper() == "PV":
        col_metode = find_col_letter(header_values, "METODE PERBAIKAN", "X", start_col_idx)
        col_panjang = find_col_letter(header_values, "Panjang_Realisasi", "AD", start_col_idx)
        col_lebar = find_col_letter(header_values, "Lebar_Realisasi", "AE", start_col_idx)
        col_tebal = find_col_letter(header_values, "Tebal_Realisasi", "AF", start_col_idx)
        
        if metode:
            m_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_metode}{actual_excel_row}')"
            session.patch(m_url, headers=headers, json={"values": [[metode]]}).raise_for_status()
            
        if panjang:
            p_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_panjang}{actual_excel_row}')"
            session.patch(p_url, headers=headers, json={"values": [[panjang]]}).raise_for_status()
        if lebar:
            l_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_lebar}{actual_excel_row}')"
            session.patch(l_url, headers=headers, json={"values": [[lebar]]}).raise_for_status()
        if tebal:
            t_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{col_tebal}{actual_excel_row}')"
            session.patch(t_url, headers=headers, json={"values": [[tebal]]}).raise_for_status()

    return True
