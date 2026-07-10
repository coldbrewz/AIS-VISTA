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
        cache.deserialize(open("token_cache.bin", "r").read())
    app = msal.PublicClientApplication(
        settings.MICROSOFT_CLIENT_ID, 
        authority="https://login.microsoftonline.com/common", 
        token_cache=cache
    )
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(["Files.ReadWrite.All"], account=accounts[0])
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
    
    # 1. Fetch only the bounding box address to avoid downloading massive amounts of data
    range_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/usedRange?$select=address"
    range_resp = session.get(range_url, headers=headers, timeout=30)
    range_resp.raise_for_status()
    used_range = range_resp.json()
    
    address = used_range.get("address", "")
    if "!" in address:
        cells = address.split("!")[1]
    else:
        cells = address
        
    if ":" in cells:
        start_cell, end_cell = cells.split(":")
    else:
        start_cell = end_cell = cells
        
    start_row = int(''.join(filter(str.isdigit, start_cell)))
    start_col_str = ''.join(filter(str.isalpha, start_cell))
    end_row = int(''.join(filter(str.isdigit, end_cell)))
    end_col_str = ''.join(filter(str.isalpha, end_cell))
    
    # 2. Fetch ONLY the first column (where Kode SLA is) to find the row
    kode_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{start_col_str}{start_row}:{start_col_str}{end_row}')?$select=values,text"
    kode_resp = session.get(kode_url, headers=headers, timeout=30)
    kode_resp.raise_for_status()
    kode_data = kode_resp.json()
    
    values = kode_data.get("values", [])
    texts = kode_data.get("text", [])
    
    row_index = -1
    kode_str = str(kode).strip().lower()
    
    for i in range(len(values)):
        val = str(values[i][0]).strip().lower() if i < len(values) and len(values[i]) > 0 and values[i][0] is not None else ""
        txt = str(texts[i][0]).strip().lower() if i < len(texts) and len(texts[i]) > 0 and texts[i][0] is not None else ""
        
        if val == kode_str or txt == kode_str:
            row_index = i
            break
            
    if row_index == -1:
        raise Exception(f"Kode '{kode}' not found in sheet '{sheet_name}'")
    
    start_col_idx = col_letter_to_num(start_col_str)
    actual_excel_row = start_row + row_index
    
    # 3. Fetch ONLY the first 10 rows to find the headers
    header_end = min(start_row + 9, end_row)
    header_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{start_col_str}{start_row}:{end_col_str}{header_end}')?$select=values"
    header_resp = session.get(header_url, headers=headers, timeout=30)
    header_resp.raise_for_status()
    header_values = header_resp.json().get("values", [])
    
    col_tanggal = find_col_letter(header_values, "TANGGAL PERBAIKAN", "T", start_col_idx)
    col_link = find_col_letter(header_values, "LINK DOKUMENTASI PERBAIKAN", "U", start_col_idx)
    
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
