import re

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
    direct_from = normalize_chat_id(_clean_string(message.get("from")))
    if direct_from and not direct_from.endswith("@lid"):
        return direct_from

    raw_data = message.get("_data") if isinstance(message.get("_data"), dict) else {}
    info = raw_data.get("Info") if isinstance(raw_data.get("Info"), dict) else {}

    for candidate in (
        info.get("Chat"),
        info.get("Sender"),
        message.get("chatId"),
        message.get("author"),
        message.get("to"),
    ):
        normalized = normalize_chat_id(_clean_string(candidate))
        if normalized and not normalized.endswith("@lid"):
            return normalized

    return direct_from


def extract_kode_from_text(text: str) -> str | None:
    if not isinstance(text, str):
        return None

    match = KODE_PATTERN.search(text)
    if not match:
        return None

    return match.group(1)
