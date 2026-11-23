from datetime import date, datetime
import re
from urllib.parse import urlparse

from services.opname_catalog import normalize_asset_code

VALID_SHEET_CODES = ("PV", "DR", "FE", "GR", "SG", "LC", "RM", "CA", "WR")
KODE_PATTERN = re.compile(
    rf"Kode\s*:\s*(\d{{6}}(?:{'|'.join(VALID_SHEET_CODES)})\d{{3,6}})",
    re.IGNORECASE,
)
OPNAME_KODE_PATTERN = re.compile(
    rf"Opname\s*:\s*(\d{{6}}({'|'.join(VALID_SHEET_CODES)})\d{{3,6}})\b",
    re.IGNORECASE,
)
OPNAME_ASSET_PATTERN = re.compile(
    r"Opname\s*:\s*([A-Za-z][A-Za-z ]{1,15})\b",
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


def extract_opname_trigger(text: str) -> dict | None:
    """
    Detect `Opname: <KODE_TEMUAN>` or `Opname: <KODE_ASET>` trigger in caption/text.
    Returns dict with keys: `aset`, `kode_temuan` ("" if routine), or None if not opname.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    m_kode = OPNAME_KODE_PATTERN.search(text)
    if m_kode:
        kode = m_kode.group(1).upper()
        aset = normalize_asset_code(m_kode.group(2))
        if aset:
            return {"aset": aset, "kode_temuan": kode}

    m_aset = OPNAME_ASSET_PATTERN.search(text)
    if m_aset:
        raw_token = m_aset.group(1).strip().splitlines()[0].strip()
        aset = normalize_asset_code(raw_token)
        if aset:
            return {"aset": aset, "kode_temuan": ""}

    return None


def _to_float(raw: str) -> float | None:
    if not raw:
        return None
    cleaned = raw.strip().replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


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


def _extract_jalur_lajur_from_lokasi(lokasi: str) -> str:
    if not lokasi:
        return ""
    tokens: list[str] = []
    m_ab = re.search(r"\b(A|B)\b(?=\s|$|\s+L\d)", lokasi, re.IGNORECASE)
    if m_ab:
        tokens.append(m_ab.group(1).upper())
    m_l = re.search(r"\b(L\d|BAHU(?:\s+LUAR|\s+DALAM)?|MEDIAN|ROW|RAMP\s+(?:ON|OFF))\b", lokasi, re.IGNORECASE)
    if m_l:
        tokens.append(m_l.group(1).upper())
    return " ".join(tokens).strip()


def _parse_qty_expression(expr: str) -> dict:
    """
    Parse qty/dimensions, optional unit, and optional `| Baru/Eksisting` from RHS of an item line.
    Examples:
      `4.5 x 1.2 x 0.05 m3` -> p=4.5, l=1.2, t=0.05, volume=0.27, satuan="m3"
      `25 x 1 x 0.45 m3 | Baru` -> p=25, l=1, t=0.45, volume=11.25, satuan="m3", material_status="Baru"
      `0.62 ton` -> volume=0.62, satuan="ton"
      `2 hok` -> volume=2.0, satuan="hok"
    """
    status = ""
    main_part = expr.strip()
    if "|" in main_part:
        main_part, status_raw = main_part.split("|", 1)
        status_clean = status_raw.strip().lower()
        if "baru" in status_clean:
            status = "Baru"
        elif "eks" in status_clean or "bekas" in status_clean:
            status = "Eksisting"
        else:
            status = status_raw.strip()
        main_part = main_part.strip()

    dim_re = re.match(
        r"^(\d+(?:[.,]\d+)?)\s*[xX*]\s*(\d+(?:[.,]\d+)?)"
        r"(?:\s*[xX*]\s*(\d+(?:[.,]\d+)?))?"
        r"(?:\s*[xX*]\s*(\d+(?:[.,]\d+)?))?"
        r"(?:\s+(.*))?$",
        main_part,
    )
    if dim_re:
        p = _to_float(dim_re.group(1))
        l_val = _to_float(dim_re.group(2))
        t = _to_float(dim_re.group(3)) if dim_re.group(3) else None
        jml = _to_float(dim_re.group(4)) if dim_re.group(4) else None
        satuan = (dim_re.group(5) or "").strip()
        vol = 1.0
        for v in (p, l_val, t, jml):
            if v is not None:
                vol *= v
        return {
            "p": p,
            "l": l_val,
            "t": t,
            "jumlah": jml,
            "volume": round(vol, 4),
            "satuan": satuan,
            "material_status": status,
        }

    scalar_re = re.match(r"^(\d+(?:[.,]\d+)?)\s*(.*)$", main_part)
    if scalar_re:
        val = _to_float(scalar_re.group(1))
        satuan = (scalar_re.group(2) or "").strip()
        return {
            "p": None,
            "l": None,
            "t": None,
            "jumlah": None,
            "volume": val,
            "satuan": satuan,
            "material_status": status,
        }

    return {
        "p": None,
        "l": None,
        "t": None,
        "jumlah": None,
        "volume": None,
        "satuan": "",
        "material_status": status,
    }


_UNITS_PATTERN = (
    r"m3|m2|m1|m'|m|meter|mtr|ton|zak|bh|buah|unit|btg|batang|tiang|hok|jam|"
    r"ls|ltr|liter|lbr|lembar|set|span(?:\s+beam)?|titik|pohon|kg|roll|rit|hr|hari"
)


def _split_item_line(content: str) -> tuple[str, str] | None:
    """
    Split an item line into (raw_item, rhs_qty) supporting:
      - Colon mode:      `Permanen: 4.5 x 1.2 x 0.05 m3` or `II.1: 0.27 m3`
      - Equals mode:     `Permanen = 4.5 x 1.2 x 0.05 m3`
      - Colonless mode:  `Permanen 4.5 x 1.2 x 0.05 m3` or `Pasang Tiang 2400 3 tiang`
    """
    if ":" in content:
        lhs, rhs = content.split(":", 1)
        return lhs.strip(), rhs.strip()
    if "=" in content:
        lhs, rhs = content.split("=", 1)
        return lhs.strip(), rhs.strip()

    # Colonless dimensions: `<item> <P x L [x T [x Jml]]> [unit] [| Baru/Eksisting]`
    m_dim = re.match(
        r"^(.+?)\s+(\d+(?:[.,]\d+)?\s*[xX*]\s*\d+(?:[.,]\d+)?.*)$",
        content,
    )
    if m_dim:
        return m_dim.group(1).strip(), m_dim.group(2).strip()

    # Colonless scalar with explicit unit or terminal number: `<item> <qty> [<unit>] [| Status]`
    m_unit = re.match(
        rf"^(.+?)\s+(\d+(?:[.,]\d+)?\s*(?:{_UNITS_PATTERN})(?:\s*\|.*)?)$",
        content,
        re.IGNORECASE,
    )
    if m_unit:
        return m_unit.group(1).strip(), m_unit.group(2).strip()

    m_num = re.match(r"^(.+?)\s+(\d+(?:[.,]\d+)?(?:\s*\|.*)?)$", content)
    if m_num:
        return m_num.group(1).strip(), m_num.group(2).strip()

    return None


def parse_structured_opname_caption(text: str) -> dict:
    """
    Deterministically parse structured WhatsApp Opname caption fields:
      Lokasi:, Vendor:, Tanggal:, Jalur:, Keterangan:, and item lines (with or without `:`).
    """
    result = {
        "lokasi": "",
        "vendor": "",
        "tanggal": "",
        "jalur_lajur": "",
        "keterangan": "",
        "items": [],  # list of dicts: raw_item, p, l, t, jumlah, volume, satuan, material_status, error
        "unparsed_item_lines": [],
    }
    if not isinstance(text, str) or not text.strip():
        return result

    in_item_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Bulleted or starred item line (allowed inside or outside `Item:` section)
        if re.match(r"^[-*•]\s+", line):
            content = re.sub(r"^[-*•]\s+", "", line).strip()
            split_res = _split_item_line(content)
            if not split_res:
                result["unparsed_item_lines"].append(line)
                continue
            raw_item, rhs = split_res
            parsed_qty = _parse_qty_expression(rhs)
            result["items"].append({"raw_item": raw_item, **parsed_qty})
            continue

        m_hdr = re.match(r"^(Opname|Lokasi|Vendor|Tanggal|Tgl|Jalur|Lajur|Item|Ket|Keterangan)\s*:\s*(.*)$", line, re.IGNORECASE)
        if m_hdr:
            key = m_hdr.group(1).lower()
            val = m_hdr.group(2).strip()
            in_item_block = key == "item"
            if key == "lokasi":
                result["lokasi"] = val
            elif key == "vendor":
                result["vendor"] = val
            elif key in {"tanggal", "tgl"}:
                result["tanggal"] = parse_opname_date_str(val) or ""
            elif key in {"jalur", "lajur"}:
                result["jalur_lajur"] = val
            elif key in {"ket", "keterangan"}:
                result["keterangan"] = val
            elif key == "item" and val:
                split_res = _split_item_line(val)
                if split_res:
                    raw_item, rhs = split_res
                    result["items"].append({"raw_item": raw_item, **_parse_qty_expression(rhs)})
                else:
                    result["unparsed_item_lines"].append(val)
            continue

        if in_item_block:
            split_res = _split_item_line(line)
            if split_res:
                raw_item, rhs = split_res
                result["items"].append({"raw_item": raw_item, **_parse_qty_expression(rhs)})
            else:
                result["unparsed_item_lines"].append(line)

    if not result["jalur_lajur"] and result["lokasi"]:
        result["jalur_lajur"] = _extract_jalur_lajur_from_lokasi(result["lokasi"])

    return result
