from datetime import date, datetime
import re
from urllib.parse import urlparse

from services.opname_catalog import normalize_asset_code

VALID_SHEET_CODES = ("PV", "DR", "FE", "GR", "SG", "LC", "RM", "CA", "WR")
KODE_PATTERN = re.compile(
    rf"Kode\s*:\s*(\d{{6}}(?:{'|'.join(VALID_SHEET_CODES)})\d{{3,6}})",
    re.IGNORECASE,
)
SCAN_OPNAME_PATTERN = re.compile(r"\b(?:scan\s+opname|opname\s+scan)\b", re.IGNORECASE)


def _clean_string(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or value.lower() == "none":
        return None
    return value


def normalize_chat_id(chat_id: str | None) -> str:
    chat_id = _clean_string(chat_id)
    if not chat_id:
        return ""

    if "@" not in chat_id:
        return f"{chat_id}@c.us"

    local_part, domain = chat_id.split("@", 1)
    local_part = local_part.split(":", 1)[0]

    if domain == "s.whatsapp.net":
        return f"{local_part}@c.us"

    return f"{local_part}@{domain}"


def extract_message_id(message: dict) -> str | None:
    raw_id = message.get("id")
    if isinstance(raw_id, dict):
        serialized = _clean_string(raw_id.get("_serialized"))
        if serialized:
            return serialized

        direct_id = _clean_string(raw_id.get("id"))
        if direct_id:
            return direct_id
    else:
        direct_id = _clean_string(raw_id)
        if direct_id:
            return direct_id

    raw_data = message.get("_data") if isinstance(message.get("_data"), dict) else {}
    raw_data_id = raw_data.get("id")
    if isinstance(raw_data_id, dict):
        serialized = _clean_string(raw_data_id.get("_serialized"))
        if serialized:
            return serialized

        direct_id = _clean_string(raw_data_id.get("id"))
        if direct_id:
            return direct_id
    else:
        direct_id = _clean_string(raw_data_id)
        if direct_id:
            return direct_id

    info = raw_data.get("Info") if isinstance(raw_data.get("Info"), dict) else {}
    info_id = (
        _clean_string(info.get("ID"))
        or _clean_string(info.get("Id"))
        or _clean_string(info.get("id"))
    )
    if not info_id:
        return None

    remote_chat = _clean_string(message.get("from")) or _clean_string(message.get("chatId"))
    if not remote_chat:
        remote_chat = normalize_chat_id(
            _clean_string(info.get("Chat")) or _clean_string(info.get("Sender"))
        )

    if not remote_chat:
        return None

    from_me = bool(message.get("fromMe", info.get("IsFromMe", False)))
    return f"{str(from_me).lower()}_{remote_chat}_{info_id}"


def resolve_reply_chat_id(message: dict) -> str:
    # WPP fully supports sending to @lid addresses.
    # Just return the direct sender or the group chat ID.
    direct_from = normalize_chat_id(_clean_string(message.get("from")))
    if direct_from:
        return direct_from
        
    chat_id = normalize_chat_id(_clean_string(message.get("chatId")))
    if chat_id:
        return chat_id
        
    return ""


def extract_kode_from_text(text: str) -> str | None:
    if not isinstance(text, str):
        return None

    match = KODE_PATTERN.search(text)
    if not match:
        return None

    return match.group(1)


def resolve_media_download_url(message: dict, base_waha_url: str) -> str | None:
    media_url = _clean_string(message.get("mediaUrl"))
    if not media_url:
        media = message.get("media")
        if isinstance(media, dict):
            media_url = _clean_string(media.get("url"))

    if media_url:
        parsed_url = urlparse(media_url)
        if parsed_url.scheme and parsed_url.netloc:
            return f"{base_waha_url}{parsed_url.path}" if parsed_url.path else media_url
        return media_url

    message_id = extract_message_id(message)
    if not message_id:
        return None

    session = _clean_string(message.get("_session")) or "default"
    return f"{base_waha_url}/api/{session}/messages/{message_id}/download"


def reconcile_date_with_message_time(
    parsed_dt, msg_dt
):
    """
    Reconciles ambiguous day/month order (DD-MM vs MM-DD) using WhatsApp message timestamp.
    Runs locally in Python with zero extra LLM tokens.
    """
    changed = False

    # 1. Year sanity check: if OCR read a wildly wrong year, snap to message year
    if abs(parsed_dt.year - msg_dt.year) > 1:
        try:
            parsed_dt = parsed_dt.replace(year=msg_dt.year)
            changed = True
        except ValueError:
            pass

    # 2. Ambiguous day/month check:
    # If the extracted month does NOT match the message month, but the extracted day matches the message month,
    # check if swapping day and month produces the actual message month.
    # E.g. extracted 2026-05-08 (8 May) when message arrived in August (month 8).
    # Swapping yields 2026-08-05 (5 August).
    if parsed_dt.month != msg_dt.month and parsed_dt.day == msg_dt.month:
        candidate_day = parsed_dt.month
        candidate_month = parsed_dt.day
        try:
            swapped = parsed_dt.replace(month=candidate_month, day=candidate_day)
            # Verify swapped date is not in future relative to message arrival
            if (swapped.date() - msg_dt.date()).days <= 1:
                return swapped, True
        except ValueError:
            pass

    return parsed_dt, changed


def extract_media_metadata(message: dict) -> tuple[str, str]:
    """Extract (filename, mimetype) from a WAHA message webhook payload cleanly."""
    if not isinstance(message, dict):
        return "", ""
    media = message.get("media") if isinstance(message.get("media"), dict) else {}
    raw_data = message.get("_data") if isinstance(message.get("_data"), dict) else {}
    msg_obj = raw_data.get("Message") if isinstance(raw_data.get("Message"), dict) else {}
    doc_msg = msg_obj.get("documentMessage") if isinstance(msg_obj.get("documentMessage"), dict) else {}

    filename = (
        _clean_string(media.get("filename"))
        or _clean_string(message.get("filename"))
        or _clean_string(raw_data.get("filename"))
        or _clean_string(doc_msg.get("fileName"))
        or _clean_string(doc_msg.get("title"))
        or ""
    )
    mimetype = (
        _clean_string(media.get("mimetype"))
        or _clean_string(message.get("mimetype"))
        or _clean_string(raw_data.get("mimetype"))
        or _clean_string(doc_msg.get("mimetype"))
        or ""
    )
    return filename, mimetype.lower()


def extract_scan_opname_hint(text: str) -> dict | None:
    """
    Detect `Scan Opname` / `Opname Scan` trigger and extract optional asset, wilayah, vendor, and minggu hints.
    """
    if not isinstance(text, str) or not SCAN_OPNAME_PATTERN.search(text):
        return None
    up = text.upper()
    aset = ""
    for tok in re.findall(r"\b([A-Z]{2,10})\b", up):
        if tok in ("SCAN", "OPNAME", "W1", "W2", "WIL", "PT", "CV"):
            continue
        norm = normalize_asset_code(tok)
        if norm:
            aset = norm
            break
    m_wil = re.search(r"\b(W[12])\b", up)
    m_wk = re.search(r"\b(M[1-5])\b", up)
    return {
        "aset": aset,
        "wilayah": m_wil.group(1) if m_wil else "",
        "minggu": m_wk.group(1) if m_wk else "",
    }


def parse_opname_date_str(raw: str) -> str | None:
    """Normalize DD-MM-YYYY, DD/MM/YYYY, or YYYY-MM-DD into YYYY-MM-DD."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    m_dmy = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$", s)
    if m_dmy:
        d, m, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, m, d).strftime("%Y-%m-%d")
        except ValueError:
            return None
    m_ymd = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", s)
    if m_ymd:
        y, m, d = int(m_ymd.group(1)), int(m_ymd.group(2)), int(m_ymd.group(3))
        try:
            return date(y, m, d).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def resolve_billing_cycle(dt: date | datetime) -> tuple[int, int]:
    """
    Monthly 26th..25th billing cycle:
    26 Oct .. 25 Nov -> month 11 (November) of Nov's year.
    26 Dec 2026 .. 25 Jan 2027 -> month 1 of 2027.
    """
    d = dt.date() if isinstance(dt, datetime) else dt
    if d.day >= 26:
        if d.month == 12:
            return 1, d.year + 1
        return d.month + 1, d.year
    return d.month, d.year
