import os
import base64
import requests
import msal
from config import settings

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
    raise Exception("Microsoft Authentication Failed. Please run auth_microsoft.py again.")

def encode_share_url(url: str) -> str:
    encoded = base64.urlsafe_b64encode(url.encode('utf-8')).decode('utf-8')
    return "u!" + encoded.rstrip('=')

def upload_photo_to_onedrive(file_bytes: bytes, filename: str, folder_path: str = "VISTA_Photos") -> str:
    token = get_ms_token()
    
    # 1. Upload to the specified nested folder path
    upload_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}/{filename}:/content"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "image/jpeg"
    }
    resp = requests.put(upload_url, headers=headers, data=file_bytes)
    resp.raise_for_status()
    item_id = resp.json()["id"]
    
    # 2. Create sharing link
    link_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/createLink"
    link_body = {"type": "view", "scope": "anonymous"}
    link_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    link_resp = requests.post(link_url, headers=link_headers, json=link_body)
    link_resp.raise_for_status()
    
    return link_resp.json()["link"]["webUrl"]

def update_excel_row(share_url: str, sheet_name: str, kode: str, tanggal: str, link: str, metode: str = "", panjang: str = "", lebar: str = "", tebal: str = ""):
    token = get_ms_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    encoded_url = encode_share_url(share_url)
    share_resp = requests.get(f"https://graph.microsoft.com/v1.0/shares/{encoded_url}/driveItem", headers=headers, allow_redirects=False)
    
    # Robustly follow all redirects (Microsoft Graph heavily uses 308 redirects across tenants)
    redirects = 0
    while share_resp.status_code in [301, 302, 303, 307, 308] and redirects < 5:
        redirect_url = share_resp.headers.get("Location")
        if not redirect_url:
            break
        share_resp = requests.get(redirect_url, headers=headers, allow_redirects=False)
        redirects += 1
            
    if share_resp.status_code not in [200, 201]:
        raise Exception(f"Microsoft API blocked the link. Status {share_resp.status_code}. Response: {share_resp.text}")
    try:
        drive_item = share_resp.json()
    except Exception:
        raise Exception(f"Microsoft API returned an empty or invalid response. Status {share_resp.status_code}. Raw text: '{share_resp.text}'")
    drive_id = drive_item["parentReference"]["driveId"]
    item_id = drive_item["id"]
    
    range_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/usedRange"
    range_resp = requests.get(range_url, headers=headers)
    range_resp.raise_for_status()
    used_range = range_resp.json()
    
    values = used_range.get("values", [])
    row_index = -1
    for i, row in enumerate(values):
        if len(row) > 0 and str(row[0]).strip() == str(kode).strip():
            row_index = i
            break
            
    if row_index == -1:
        raise Exception(f"Kode '{kode}' not found in sheet '{sheet_name}'")
    
    address = used_range.get("address", "")
    start_row = 1
    if "!" in address:
        cells = address.split("!")[1]
        start_cell = cells.split(":")[0] 
        start_row = int(''.join(filter(str.isdigit, start_cell)))
    
    actual_excel_row = start_row + row_index
    
    tu_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='T{actual_excel_row}:U{actual_excel_row}')"
    requests.patch(tu_url, headers=headers, json={"values": [[tanggal, link]]}).raise_for_status()
    
    if sheet_name.upper() == "PV":
        if metode:
            x_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='X{actual_excel_row}')"
            requests.patch(x_url, headers=headers, json={"values": [[metode]]}).raise_for_status()
            
        if panjang or lebar or tebal:
            adaeaf_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='AD{actual_excel_row}:AF{actual_excel_row}')"
            requests.patch(adaeaf_url, headers=headers, json={"values": [[panjang, lebar, tebal]]}).raise_for_status()

    return True
