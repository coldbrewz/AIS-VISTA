from datetime import date
import os
import base64
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import msal
from config import settings

_WORKBOOK_LOCKS_GUARD = threading.Lock()
_WORKBOOK_LOCKS: dict[str, threading.Lock] = {}
_MONTHLY_CREATE_LOCK = threading.Lock()

OPNAME_MONTH_NAMES = {
    1: "JANUARI",
    2: "FEBRUARI",
    3: "MARET",
    4: "APRIL",
    5: "MEI",
    6: "JUNI",
    7: "JULI",
    8: "AGUSTUS",
    9: "SEPTEMBER",
    10: "OKTOBER",
    11: "NOVEMBER",
    12: "DESEMBER",
}

CYCLE_START_CELLS: tuple[tuple[str, str], ...] = (
    ("PV W1", "D7"),
    ("PV2", "E7"),
    ("Rambu W1", "E7"),
    ("Rambu W2", "E7"),
    ("GR WR W1", "E7"),
    ("GR WR W2", "E7"),
    ("RM LC W1", "E7"),
    ("RMLC2", "E7"),
    ("TRC W1", "F7"),
    ("TRC2", "E7"),
    ("DR W1", "D7"),
    ("DR2", "D7"),
    ("FE W1", "E7"),
    ("FE2", "E7"),
)


def _get_workbook_lock(share_url: str) -> threading.Lock:
    with _WORKBOOK_LOCKS_GUARD:
        lock = _WORKBOOK_LOCKS.get(share_url)
        if lock is None:
            lock = threading.Lock()
            _WORKBOOK_LOCKS[share_url] = lock
        return lock

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
    
    # Check if the existing token cache file is valid
    existing_valid = False
    if os.path.exists(token_cache_path):
        try:
            with open(token_cache_path, "r") as f:
                content = f.read().strip()
                if content and content.startswith("{") and "RefreshToken" in content:
                    existing_valid = True
        except Exception:
            existing_valid = False

    # Auto-seed from environment variable if missing, empty, or corrupted
    env_cache_data = os.environ.get("MICROSOFT_TOKEN_CACHE_DATA")
    if not existing_valid and env_cache_data:
        print(f"INIT: Seeding/Fixing Microsoft token cache from environment variable to: {token_cache_path}")
        try:
            os.makedirs(os.path.dirname(token_cache_path), exist_ok=True)
            with open(token_cache_path, "w") as f:
                f.write(env_cache_data.strip())
        except Exception as e:
            print(f"INIT: Failed to write token cache from env: {e}")
            
    # Auto-seed fallback from repository root (if committed and volume file is missing)
    elif not os.path.exists(token_cache_path) and os.path.exists("token_cache.bin") and token_cache_path != "token_cache.bin":
        print(f"INIT: Seeding Microsoft token cache from repository root to volume: {token_cache_path}")
        import shutil
        try:
            os.makedirs(os.path.dirname(token_cache_path), exist_ok=True)
            shutil.copy("token_cache.bin", token_cache_path)
        except Exception as e:
            print(f"INIT: Failed to copy token cache: {e}")

    # Read the cache (whether newly seeded or existing)
    if os.path.exists(token_cache_path):
        try:
            with open(token_cache_path, "r") as f:
                cache.deserialize(f.read())
        except Exception as e:
            print(f"ERROR: Failed to deserialize token cache: {e}")
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

def upload_file_to_onedrive(
    file_bytes: bytes,
    filename: str,
    folder_path: str,
    content_type: str = "application/octet-stream",
) -> tuple[str, str]:
    """Upload bytes to `/me/drive/root:/{folder_path}/{filename}` and return `(item_id, web_url)`."""
    token = get_ms_token()
    session = get_retry_session()

    upload_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_path}/{filename}:/content"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }
    resp = session.put(upload_url, headers=headers, data=file_bytes, timeout=60)
    resp.raise_for_status()
    meta = resp.json()
    item_id = meta["id"]
    web_url = meta.get("webUrl", "")

    link_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/createLink"
    link_body = {"type": "view", "scope": "anonymous"}
    link_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    link_resp = session.post(link_url, headers=link_headers, json=link_body, timeout=20)
    if link_resp.ok:
        web_url = link_resp.json().get("link", {}).get("webUrl", web_url)
    elif not web_url:
        link_resp.raise_for_status()

    return item_id, web_url


def download_file_from_onedrive(item_id: str, drive_id: str = "") -> bytes:
    """Download file bytes from OneDrive by drive item ID (supports shared drives when `drive_id` is passed)."""
    token = get_ms_token()
    session = get_retry_session()
    if drive_id:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content"
    else:
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/content"
    resp = session.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    resp.raise_for_status()
    return resp.content


def download_share_file_from_onedrive(share_url: str) -> tuple[bytes, str]:
    """Download file bytes and filename resolved from a OneDrive share link."""
    token = get_ms_token()
    session = get_retry_session()
    headers = {"Authorization": f"Bearer {token}"}
    drive_id, item_id, _, _ = _resolve_share_drive_item_full(session, headers, share_url)
    meta_resp = session.get(
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}",
        headers=headers,
        timeout=20,
    )
    filename = meta_resp.json().get("name", "template.xlsx") if meta_resp.ok else "template.xlsx"
    return download_file_from_onedrive(item_id, drive_id=drive_id), filename


def upload_photo_to_onedrive(file_bytes: bytes, filename: str, folder_path: str = "Dokumentasi SLA") -> str:
    _, web_url = upload_file_to_onedrive(file_bytes, filename, folder_path, content_type="image/jpeg")
    return web_url

def _resolve_share_drive_item_full(session, headers: dict, share_url: str) -> tuple[str, str, str, str]:
    encoded_url = encode_share_url(share_url)
    share_resp = session.get(
        f"https://graph.microsoft.com/v1.0/shares/{encoded_url}/driveItem",
        headers=headers,
        allow_redirects=False,
    )
    redirects = 0
    while share_resp.status_code in [301, 302, 303, 307, 308] and redirects < 5:
        redirect_url = share_resp.headers.get("Location")
        if not redirect_url:
            break
        share_resp = session.get(redirect_url, headers=headers, allow_redirects=False)
        redirects += 1

    if share_resp.status_code not in [200, 201]:
        raise Exception(
            f"Microsoft API blocked the link. Status {share_resp.status_code}. Response: {share_resp.text}"
        )
    try:
        drive_item = share_resp.json()
    except Exception:
        raise Exception(
            f"Microsoft API returned an empty or invalid response. Status {share_resp.status_code}. Raw text: '{share_resp.text}'"
        )
    parent_ref = drive_item.get("parentReference", {})
    return (
        parent_ref["driveId"],
        drive_item["id"],
        parent_ref.get("id", ""),
        drive_item.get("webUrl", ""),
    )


def _resolve_share_drive_item(session, headers: dict, share_url: str) -> tuple[str, str]:
    drive_id, item_id, _, _ = _resolve_share_drive_item_full(session, headers, share_url)
    return drive_id, item_id


def update_excel_row(share_url: str, sheet_name: str, kode: str, tanggal: str, link: str, metode: str = "", panjang: str = "", lebar: str = "", tebal: str = ""):
    token = get_ms_token()
    session = get_retry_session()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    drive_id, item_id = _resolve_share_drive_item(session, headers, share_url)
    
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


def _excel_serial_for_cycle(cycle_month: int, cycle_year: int) -> int:
    start_dt = (
        date(cycle_year - 1, 12, 26)
        if cycle_month == 1
        else date(cycle_year, cycle_month - 1, 26)
    )
    return (start_dt - date(1899, 12, 30)).days


def ensure_monthly_opname_workbook(
    template_share_url: str,
    cycle_month: int,
    cycle_year: int,
) -> tuple[str, str, str]:
    """
    Find or auto-create `DATA_UNTUK_VOL_<BULAN>_<TAHUN>.xlsx` in the same OneDrive folder
    as `template_share_url` (or fallback `/me/drive/root:/Database Opname/...`), patching row 7
    cycle start dates across all 14 daily matrix sheets on first creation.
    Returns `(drive_id, item_id, web_url)`.
    """
    if not template_share_url:
        raise Exception("OPNAME_EXCEL_SHARE_LINK belum dikonfigurasi.")

    month_label = OPNAME_MONTH_NAMES[cycle_month]
    filename = f"DATA_UNTUK_VOL_{month_label}_{cycle_year}.xlsx"

    with _MONTHLY_CREATE_LOCK:
        token = get_ms_token()
        session = get_retry_session()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        src_drive_id, src_item_id, parent_id, _ = _resolve_share_drive_item_full(
            session, headers, template_share_url
        )

        # 1. Check same folder where the base template sits
        if parent_id:
            lookup_url = f"https://graph.microsoft.com/v1.0/drives/{src_drive_id}/items/{parent_id}:/{filename}"
            chk = session.get(lookup_url, headers=headers, timeout=20)
            if chk.status_code == 200:
                meta = chk.json()
                return meta["parentReference"]["driveId"], meta["id"], meta.get("webUrl", "")

        # Also check fallback folder in user's own drive
        me_lookup_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/Database Opname/{filename}"
        chk_me = session.get(me_lookup_url, headers=headers, timeout=20)
        if chk_me.status_code == 200:
            meta = chk_me.json()
            return meta["parentReference"]["driveId"], meta["id"], meta.get("webUrl", "")

        # 2. Download clean template bytes and upload as the new monthly workbook
        dl_url = f"https://graph.microsoft.com/v1.0/drives/{src_drive_id}/items/{src_item_id}/content"
        dl_resp = session.get(dl_url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        dl_resp.raise_for_status()
        template_bytes = dl_resp.content

        up_headers = {
            "Authorization": f"Bearer {get_ms_token()}",
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        up_resp = None
        if parent_id:
            up_url = f"https://graph.microsoft.com/v1.0/drives/{src_drive_id}/items/{parent_id}:/{filename}:/content"
            up_resp = session.put(up_url, headers=up_headers, data=template_bytes, timeout=60)
        if up_resp is None or up_resp.status_code in (401, 403, 404):
            up_resp = session.put(f"{me_lookup_url}:/content", headers=up_headers, data=template_bytes, timeout=60)
        up_resp.raise_for_status()
        new_meta = up_resp.json()
        new_drive_id = new_meta["parentReference"]["driveId"]
        new_item_id = new_meta["id"]
        new_web_url = new_meta.get("webUrl", "")

        # 3. Initialize 26th..25th start dates on all 14 daily matrix sheets
        serial_val = _excel_serial_for_cycle(cycle_month, cycle_year)
        xl_headers = {
            "Authorization": f"Bearer {get_ms_token()}",
            "Content-Type": "application/json",
        }
        sess_url = f"https://graph.microsoft.com/v1.0/drives/{new_drive_id}/items/{new_item_id}/workbook/createSession"
        sess_resp = session.post(sess_url, headers=xl_headers, json={"persistChanges": True}, timeout=60)
        sess_resp.raise_for_status()
        xl_headers["workbook-session-id"] = sess_resp.json().get("id")
        try:
            for sheet_name, cell_ref in CYCLE_START_CELLS:
                patch_url = (
                    f"https://graph.microsoft.com/v1.0/drives/{new_drive_id}/items/{new_item_id}"
                    f"/workbook/worksheets/{sheet_name}/range(address='{cell_ref}')"
                )
                session.patch(patch_url, headers=xl_headers, json={"values": [[serial_val]]}, timeout=15)
        finally:
            try:
                session.post(
                    f"https://graph.microsoft.com/v1.0/drives/{new_drive_id}/items/{new_item_id}/workbook/closeSession",
                    headers=xl_headers,
                    timeout=10,
                )
            except Exception:
                pass

        return new_drive_id, new_item_id, new_web_url


def append_opname_rows(
    share_url: str,
    table_name: str,
    rows: list[list],
    target_drive_item: tuple[str, str] | None = None,
) -> bool:
    """
    Append one or more 21-column rows to an Excel Table (`TBL_LOG_*`) inside a persisted workbook session
    guarded by a per-workbook lock.
    """
    if not rows:
        return True
    if not share_url and not target_drive_item:
        raise Exception("OPNAME_EXCEL_SHARE_LINK belum dikonfigurasi.")

    lock_key = f"{target_drive_item[0]}:{target_drive_item[1]}" if target_drive_item else share_url
    lock = _get_workbook_lock(lock_key)
    with lock:
        token = get_ms_token()
        session = get_retry_session()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if target_drive_item:
            drive_id, item_id = target_drive_item
        else:
            drive_id, item_id = _resolve_share_drive_item(session, headers, share_url)

        session_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/createSession"
        session_resp = session.post(session_url, headers=headers, json={"persistChanges": True}, timeout=60)
        session_resp.raise_for_status()
        workbook_session_id = session_resp.json().get("id")
        headers["workbook-session-id"] = workbook_session_id

        try:
            fresh_token = get_ms_token()
            headers["Authorization"] = f"Bearer {fresh_token}"
            add_url = (
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
                f"/workbook/tables/{table_name}/rows/add"
            )
            resp = session.post(add_url, headers=headers, json={"values": rows}, timeout=45)
            if not resp.ok:
                raise Exception(
                    f"Gagal append ke tabel {table_name} ({resp.status_code}): {resp.text}"
                )
        finally:
            try:
                close_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/closeSession"
                session.post(close_url, headers=headers, timeout=10)
            except Exception as e:
                print(f"Warning: Failed to close Excel Opname session: {e}")

    return True


def delete_opname_rows_by_id(
    share_url: str,
    table_name: str,
    opname_id: str,
    target_drive_item: tuple[str, str] | None = None,
) -> int:
    """
    Delete all rows matching `opname_id` (col 0) from `table_name` for `/undo <OPN-ID>`.
    Deletes bottom-to-top so indices stay valid. Returns count deleted.
    """
    if (not share_url and not target_drive_item) or not opname_id:
        return 0

    lock_key = f"{target_drive_item[0]}:{target_drive_item[1]}" if target_drive_item else share_url
    lock = _get_workbook_lock(lock_key)
    deleted = 0
    with lock:
        token = get_ms_token()
        session = get_retry_session()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if target_drive_item:
            drive_id, item_id = target_drive_item
        else:
            drive_id, item_id = _resolve_share_drive_item(session, headers, share_url)
        session_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/createSession"
        session_resp = session.post(session_url, headers=headers, json={"persistChanges": True}, timeout=60)
        session_resp.raise_for_status()
        headers["workbook-session-id"] = session_resp.json().get("id")

        try:
            rows_url = (
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
                f"/workbook/tables/{table_name}/rows"
            )
            list_resp = session.get(rows_url, headers=headers, timeout=30)
            list_resp.raise_for_status()
            rows_data = list_resp.json().get("value", [])

            target_upper = opname_id.strip().upper()
            matching_indices = []
            for row_obj in rows_data:
                vals = row_obj.get("values", [[]])
                if vals and vals[0] and str(vals[0][0]).strip().upper() == target_upper:
                    matching_indices.append(row_obj["index"])

            for idx in sorted(matching_indices, reverse=True):
                del_url = f"{rows_url}/itemAt(index={idx})"
                del_resp = session.delete(del_url, headers=headers, timeout=20)
                if del_resp.ok:
                    deleted += 1
        finally:
            try:
                close_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/closeSession"
                session.post(close_url, headers=headers, timeout=10)
            except Exception as e:
                print(f"Warning: Failed to close Excel Opname session on undo: {e}")

    return deleted


def replace_opname_slot_rows(
    share_url: str,
    table_name: str,
    slot_id: str,
    new_rows: list[list],
    target_drive_item: tuple[str, str] | None = None,
) -> tuple[int, int]:
    """
    Atomically delete any existing rows in `table_name` whose col 0 (`Opname_ID`) == `slot_id`
    and append `new_rows` inside a single Excel session lock.
    Returns `(deleted_count, appended_count)`.
    """
    if not share_url and not target_drive_item:
        raise Exception("OPNAME_EXCEL_SHARE_LINK belum dikonfigurasi.")
    if not slot_id:
        return 0, 0

    lock_key = f"{target_drive_item[0]}:{target_drive_item[1]}" if target_drive_item else share_url
    lock = _get_workbook_lock(lock_key)
    deleted = 0
    with lock:
        token = get_ms_token()
        session = get_retry_session()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if target_drive_item:
            drive_id, item_id = target_drive_item
        else:
            drive_id, item_id = _resolve_share_drive_item(session, headers, share_url)

        session_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/createSession"
        session_resp = session.post(session_url, headers=headers, json={"persistChanges": True}, timeout=60)
        session_resp.raise_for_status()
        headers["workbook-session-id"] = session_resp.json().get("id")

        try:
            rows_url = (
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
                f"/workbook/tables/{table_name}/rows"
            )
            list_resp = session.get(rows_url, headers=headers, timeout=30)
            list_resp.raise_for_status()
            rows_data = list_resp.json().get("value", [])

            target_upper = slot_id.strip().upper()
            matching_indices = []
            for row_obj in rows_data:
                vals = row_obj.get("values", [[]])
                if vals and vals[0] and str(vals[0][0]).strip().upper() == target_upper:
                    matching_indices.append(row_obj["index"])

            for idx in sorted(matching_indices, reverse=True):
                del_url = f"{rows_url}/itemAt(index={idx})"
                del_resp = session.delete(del_url, headers=headers, timeout=20)
                if del_resp.ok:
                    deleted += 1

            if new_rows:
                fresh_token = get_ms_token()
                headers["Authorization"] = f"Bearer {fresh_token}"
                add_url = f"{rows_url}/add"
                add_resp = session.post(add_url, headers=headers, json={"values": new_rows}, timeout=45)
                if not add_resp.ok:
                    raise Exception(
                        f"Gagal menulis slot {slot_id} ke {table_name} ({add_resp.status_code}): {add_resp.text}"
                    )
        finally:
            try:
                close_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/closeSession"
                session.post(close_url, headers=headers, timeout=10)
            except Exception as e:
                print(f"Warning: Failed to close Excel Opname session on slot upsert: {e}")

    return deleted, len(new_rows)


def lookup_sla_location(share_url: str, sheet_name: str, kode: str) -> tuple[str, str] | None:
    """
    Optional lookup into SLA workbook when a PIC submits `Opname: <KODE_TEMUAN>` without typing `Lokasi:`.
    Returns `(lokasi, jalur_lajur)` if found, else `None`.
    """
    if not share_url or not kode:
        return None
    try:
        token = get_ms_token()
        session = get_retry_session()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        drive_id, item_id = _resolve_share_drive_item(session, headers, share_url)

        session_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/createSession"
        session_resp = session.post(session_url, headers=headers, json={"persistChanges": False}, timeout=45)
        session_resp.raise_for_status()
        headers["workbook-session-id"] = session_resp.json().get("id")
        try:
            safe_sheet = f"'{sheet_name}'" if " " in sheet_name else sheet_name
            match_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/functions/match"
            match_resp = session.post(
                match_url,
                headers=headers,
                json={"lookupValue": kode.strip(), "lookupArray": {"address": f"{safe_sheet}!A1:A100000"}, "matchType": 0},
                timeout=25,
            )
            if not match_resp.ok:
                return None
            match_val = match_resp.json().get("value")
            if not isinstance(match_val, int):
                return None

            row_num = match_val
            hdr_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='A4:BZ4')"
            hdr_vals = session.get(hdr_url, headers=headers, timeout=15).json().get("values", [[]])[0]
            row_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='A{row_num}:BZ{row_num}')"
            row_vals = session.get(row_url, headers=headers, timeout=15).json().get("values", [[]])[0]

            def pick(candidates):
                for idx, h in enumerate(hdr_vals):
                    hu = str(h).strip().upper()
                    if any(c in hu for c in candidates) and idx < len(row_vals):
                        v = str(row_vals[idx]).strip()
                        if v:
                            return v
                return ""

            awal = pick(["AWAL", "LOKASI", "KM"])
            jalur = pick(["JALUR", "LAJUR"])
            if awal:
                return awal, jalur
        finally:
            try:
                session.post(
                    f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/closeSession",
                    headers=headers,
                    timeout=10,
                )
            except Exception:
                pass
    except Exception:
        return None
    return None
