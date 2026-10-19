import re
from urllib.parse import urlparse

VALID_SHEET_CODES = ("PV", "DR", "FE", "GR", "SG", "LC", "RM", "CA", "WR")
KODE_PATTERN = re.compile(
    rf"Kode\s*:\s*(\d{{6}}(?:{'|'.join(VALID_SHEET_CODES)})\d{{3,6}})",
    re.IGNORECASE,
)


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
