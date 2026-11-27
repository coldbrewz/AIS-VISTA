from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Optional, Tuple


ASSET_ALIASES: Dict[str, str] = {
    "TRC": "CA",
    "RAMBU": "SG",
    "SIGN": "SG",
    "PAVEMENT": "PV",
    "DRAINASE": "DR",
    "FENCE": "FE",
    "PAGAR": "FE",
    "GUARDRAIL": "GR",
    "WIREROPE": "WR",
    "WIRE ROPE": "WR",
    "RUMPUT": "RM",
    "LANDSCAPE": "LC",
}

VALID_OPNAME_ASSETS = ("PV", "DR", "FE", "GR", "SG", "LC", "RM", "CA", "WR")

ASSET_TITLES: Dict[str, str] = {
    "PV": "Pavement",
    "SG": "Rambu, Guide Post & Delineator",
    "GR": "Guardrail",
    "WR": "Wire Rope",
    "RM": "Pemotongan Rumput, Ketrik & Striping",
    "LC": "Landscape & Penghijauan",
    "CA": "TRC & Pembersihan Perambuan",
    "DR": "Drainase",
    "FE": "Pagar ROW",
}

# Maps canonical asset code -> (log_sheet_name, excel_table_name, group_key)
ASSET_TO_TABLE: Dict[str, Tuple[str, str, str]] = {
    "PV": ("LOG_PV", "TBL_LOG_PV", "PV"),
    "SG": ("LOG_SG", "TBL_LOG_SG", "SG"),
    "GR": ("LOG_GR_WR", "TBL_LOG_GR_WR", "GR_WR"),
    "WR": ("LOG_GR_WR", "TBL_LOG_GR_WR", "GR_WR"),
    "RM": ("LOG_RM_LC", "TBL_LOG_RM_LC", "RM_LC"),
    "LC": ("LOG_RM_LC", "TBL_LOG_RM_LC", "RM_LC"),
    "CA": ("LOG_TRC", "TBL_LOG_TRC", "TRC"),
    "DR": ("LOG_DR", "TBL_LOG_DR", "DR"),
    "FE": ("LOG_FE", "TBL_LOG_FE", "FE"),
}

# Vendor canonical names and accepted aliases
VENDOR_ALIASES: Dict[str, str] = {
    "APG": "APG",
    "ADHI PERSADA GEDUNG": "APG",
    "MIJ": "MIJ",
    "MUSTIKA": "MIJ",
    "MUSTIKA IFRA JAYA": "MIJ",
    "DANU": "DANU",
    "DANUDIAN": "DANU",
    "DM": "DANU",
    "BIPR": "BIPR",
    "BUMI INDAH": "BIPR",
    "WILFA": "WILFA",
    "WILFANISTA": "WILFA",
    "PUK": "PUK",
    "ATLA": "ATLA",
    "ATLA JAYA": "ATLA",
    "CSP": "CSP",
    "CAKRA": "CSP",
    "CAKRA SARANA": "CSP",
    "CIPTA SARANA": "CSP",
    "KOPKAR": "KOPKAR",
    "KOPERASI": "KOPKAR",
    "RPG": "RPG",
    "RAJA": "RPG",
    "MMS": "MMS",
    "ASTRA": "MMS",
}

ALLOWED_VENDORS_BY_ASSET: Dict[str, Tuple[str, ...]] = {
    "PV": ("APG", "MIJ", "DANU", "BIPR", "WILFA", "PUK"),
    "GR": ("ATLA", "CSP", "KOPKAR", "MMS"),
    "WR": ("CSP", "ATLA", "KOPKAR", "MMS"),
    "SG": ("ATLA", "KOPKAR", "MMS"),
    "RM": ("KOPKAR", "BIPR", "MMS"),
    "LC": ("KOPKAR", "BIPR", "MMS"),
    "CA": ("KOPKAR", "BIPR", "RPG", "MMS"),
    "DR": ("KOPKAR", "RPG", "BIPR", "MMS"),
    "FE": ("KOPKAR", "ATLA", "RPG", "MMS"),
}

# Official 21-slot (aset, canonical_vendor, wilayah) roster per site assignment table
OFFICIAL_VENDOR_ROSTER: Tuple[Tuple[str, str, str], ...] = (
    ("PV", "MIJ", "W1"),
    ("PV", "APG", "W1"),
    ("PV", "DANU", "W1"),
    ("PV", "BIPR", "W2"),
    ("PV", "WILFA", "W2"),
    ("DR", "KOPKAR", "W1"),
    ("DR", "RPG", "W2"),
    ("FE", "KOPKAR", "W1"),
    ("FE", "KOPKAR", "W2"),
    ("GR", "ATLA", "W1"),
    ("GR", "ATLA", "W2"),
    ("SG", "ATLA", "W1"),
    ("SG", "ATLA", "W2"),
    ("LC", "KOPKAR", "W1"),
    ("LC", "BIPR", "W2"),
    ("RM", "KOPKAR", "W1"),
    ("RM", "BIPR", "W2"),
    ("CA", "KOPKAR", "W1"),
    ("CA", "BIPR", "W2"),
    ("WR", "CSP", "W1"),
    ("WR", "CSP", "W2"),
)


def check_roster_pairing(aset: str, canonical_vendor: str, wilayah: str) -> Tuple[bool, str]:
    """Validate `(aset, vendor, wilayah)` against active roster without blocking override after confirm."""
    if not aset or not canonical_vendor or not wilayah:
        return False, "Aset, vendor, atau wilayah belum lengkap."
    try:
        from services.opname_roster import get_active_roster
        roster = get_active_roster()
    except Exception:
        roster = list(OFFICIAL_VENDOR_ROSTER)

    if (aset, canonical_vendor, wilayah) in roster:
        return True, ""
    expected_wil = sorted({w for a, v, w in roster if a == aset and v == canonical_vendor})
    if expected_wil:
        return (
            False,
            f"Di roster resmi, vendor *{canonical_vendor}* untuk *{aset}* bertugas di *{'/'.join(expected_wil)}*, bukan *{wilayah}*.",
        )
    expected_vends = sorted({v for a, v, w in roster if a == aset and w == wilayah})
    if expected_vends:
        return (
            False,
            f"Vendor *{canonical_vendor}* tidak terdaftar di roster aktif *{aset} {wilayah}* (resmi: {', '.join(expected_vends)}).",
        )
    return False, f"Kombinasi *{aset} {wilayah} {canonical_vendor}* tidak ada di roster aktif."

# Official Wilayah boundaries per Service Level Agreement 2026.xlsx Legend sheet
W1_MIN_METERS = 26035
W1_MAX_EXCLUSIVE_METERS = 60000
W2_MAX_METERS = 98200

# Boundary IC at KM 60+000 shared by W1 and W2
BOUNDARY_IC_AKSES: Dict[str, str] = {
    "1.4": "Ciujung",
    "CIUJUNG": "Ciujung",
}

IC_AKSES_WILAYAH: Dict[str, Tuple[str, str]] = {
    # W1 (Bitung .. Cikande / KM 26+035 .. KM 60+000)
    "0.1": ("Bitung", "W1"),
    "BITUNG": ("Bitung", "W1"),
    "1.1": ("Cikupa", "W1"),
    "1.10": ("Cikupa", "W1"),
    "1.12": ("Cikupa", "W1"),
    "CIKUPA": ("Cikupa", "W1"),
    "PASAR KEMIS": ("Pasar Kemis", "W1"),
    "PS. KEMIS": ("Pasar Kemis", "W1"),
    "PS.KEMIS": ("Pasar Kemis", "W1"),
    "PS KEMIS": ("Pasar Kemis", "W1"),
    "PASKEM": ("Pasar Kemis", "W1"),
    "1.2": ("Balaraja Timur", "W1"),
    "BALTIM": ("Balaraja Timur", "W1"),
    "BALARAJA TIMUR": ("Balaraja Timur", "W1"),
    "1.3": ("Balaraja Barat", "W1"),
    "BALBAR": ("Balaraja Barat", "W1"),
    "BALARAJA BARAT": ("Balaraja Barat", "W1"),
    "BALARAJA": ("Balaraja", "W1"),
    "1.31": ("Cikande", "W1"),
    "CIKANDE": ("Cikande", "W1"),
    "GORDA": ("Cikande", "W1"),
    "RA 43": ("Rest Area KM 43", "W1"),
    "RA43": ("Rest Area KM 43", "W1"),
    "REST AREA 43": ("Rest Area KM 43", "W1"),
    "RA 45": ("Rest Area KM 45", "W1"),
    "RA45": ("Rest Area KM 45", "W1"),
    "REST AREA 45": ("Rest Area KM 45", "W1"),
    # W2 (Serang Timur .. Merak / KM 60+000 .. KM 98+200)
    "2.5": ("Serang Timur", "W2"),
    "SERTIM": ("Serang Timur", "W2"),
    "SERANG TIMUR": ("Serang Timur", "W2"),
    "2.6": ("Serang Barat", "W2"),
    "SERBAR": ("Serang Barat", "W2"),
    "SERANG BARAT": ("Serang Barat", "W2"),
    "SERANG": ("Serang", "W2"),
    "2.7": ("Cilegon Timur", "W2"),
    "CILTIM": ("Cilegon Timur", "W2"),
    "CILEGON TIMUR": ("Cilegon Timur", "W2"),
    "2.8": ("Cilegon Barat", "W2"),
    "CILBAR": ("Cilegon Barat", "W2"),
    "CILEGON BARAT": ("Cilegon Barat", "W2"),
    "CILEGON": ("Cilegon", "W2"),
    "2.9": ("Merak", "W2"),
    "MERAK": ("Merak", "W2"),
    "PETAK PAPAT": ("Petak Papat", "W2"),
    "PETAKPAPAT": ("Petak Papat", "W2"),
    "RA 68": ("Rest Area KM 68", "W2"),
    "RA68": ("Rest Area KM 68", "W2"),
    "REST AREA 68": ("Rest Area KM 68", "W2"),
}


@dataclass(frozen=True)
class BOQItem:
    item_key: str
    display_code: str
    keyword: str
    uraian: str
    satuan: str
    group: str
    aliases: Tuple[str, ...] = ()


def _norm_kw(text: str) -> str:
    return re.sub(r"[^a-z0-9<>]+", " ", (text or "").lower()).strip()


def normalize_asset_code(raw: str) -> Optional[str]:
    if not raw:
        return None
    cleaned = re.sub(r"[^A-Z ]", "", raw.strip().upper()).strip()
    if cleaned in VALID_OPNAME_ASSETS:
        return cleaned
    return ASSET_ALIASES.get(cleaned)


def parse_km_meters_list(text: str) -> List[int]:
    """Extract all KM/STA positions in meters (e.g. 'KM 45+200', '36+150', 'KM 45.2')."""
    if not text:
        return []
    matches: List[int] = []
    # Pattern 1: KM xx+yyy or xx+yyy (avoid matching bare 2.6 IC prefix without KM/+)
    for km_str, plus_str in re.findall(r"(?:KM|STA)?\s*(\d{2})\s*\+\s*(\d{1,3})", text, re.IGNORECASE):
        km_val = int(km_str)
        m_val = int(plus_str.ljust(3, "0")[:3]) if len(plus_str) < 3 else int(plus_str)
        matches.append(km_val * 1000 + m_val)
    if matches:
        return matches
    # Pattern 2: explicit "KM 45" or "KM 45.200" without "+"
    for km_str, dec_str in re.findall(r"\b(?:KM|STA)\s*(\d{2})(?:[.,](\d{1,3}))?\b", text, re.IGNORECASE):
        km_val = int(km_str)
        if dec_str:
            m_val = int(dec_str.ljust(3, "0")[:3])
        else:
            m_val = 0
        matches.append(km_val * 1000 + m_val)
    return matches


def resolve_wilayah(lokasi: str) -> Tuple[bool, Optional[str], Optional[str], str]:
    """
    Determine W1 or W2 deterministically from Lokasi.
    Returns: (ok, wilayah, canonical_loc_note, error_message)
    """
    if not lokasi or not lokasi.strip():
        return False, None, None, "Lokasi kosong. Wajib isi KM/STA (contoh: KM 45+200 A) atau nama IC/Akses."

    upper_loc = re.sub(r"\s+", " ", lokasi.upper()).strip()

    # Check explicit W1/W2 hint if the user wrote one, purely for contradiction guardrails
    explicit_hint: Optional[str] = None
    if re.search(r"\b(?:W1|WIL\s*1|WILAYAH\s*1|WIL-1)\b", upper_loc):
        explicit_hint = "W1"
    elif re.search(r"\b(?:W2|WIL\s*2|WILAYAH\s*2|WIL-2)\b", upper_loc):
        explicit_hint = "W2"

    # 1. Try KM / STA numbers first
    meters_list = parse_km_meters_list(upper_loc)
    if meters_list:
        target_m = sum(meters_list) // len(meters_list)
        if W1_MIN_METERS <= target_m < W1_MAX_EXCLUSIVE_METERS:
            wilayah = "W1"
        elif W1_MAX_EXCLUSIVE_METERS <= target_m <= W2_MAX_METERS:
            wilayah = "W2"
        else:
            km_disp = f"{target_m // 1000}+{target_m % 1000:03d}"
            return (
                False,
                None,
                None,
                f"Lokasi KM {km_disp} di luar batas ruas tol Tangerang-Merak (KM 26+035 s/d KM 98+200).",
            )
        if explicit_hint and explicit_hint != wilayah:
            return (
                False,
                None,
                None,
                f"Wilayah tidak konsisten: Lokasi masuk {wilayah} (batas KM 60+000), bukan {explicit_hint}.",
            )
        return True, wilayah, None, ""

    # 2. Boundary IC at KM 60 (Ciujung) is valid for both W1 and W2
    for key in sorted(BOUNDARY_IC_AKSES.keys(), key=len, reverse=True):
        if re.search(rf"(?<![0-9A-Z]){re.escape(key)}(?![0-9A-Z])", upper_loc):
            return True, (explicit_hint or "W1"), BOUNDARY_IC_AKSES[key], ""

    # 3. Try official IC / Akses names and codes (longer patterns first to match 1.31 before 1.3, 1.10 before 1.1)
    for key in sorted(IC_AKSES_WILAYAH.keys(), key=len, reverse=True):
        if re.search(rf"(?<![0-9A-Z]){re.escape(key)}(?![0-9A-Z])", upper_loc):
            canon_name, wilayah = IC_AKSES_WILAYAH[key]
            if explicit_hint and explicit_hint != wilayah:
                return (
                    False,
                    None,
                    None,
                    f"Wilayah tidak konsisten: {canon_name} termasuk {wilayah}, bukan {explicit_hint}.",
                )
            return True, wilayah, canon_name, ""

    # 4. Informal site labels or minor OCR typos fallback to explicit form/header Wilayah when present
    if explicit_hint:
        return True, explicit_hint, None, ""

    # 5. No KM, no IC/Akses match, and no explicit Wilayah header
    return (
        False,
        None,
        None,
        "Lokasi tidak dikenali sebagai KM 26+035..98+200 atau IC/Akses resmi (Bitung..Merak).",
    )


def normalize_vendor(raw_vendor: str, aset: str) -> Tuple[bool, Optional[str], str]:
    """Strictly validate and normalize vendor name against dynamic SQLite/catalog roster."""
    try:
        from services.opname_roster import get_allowed_vendors_for_asset, get_vendor_alias_map
        alias_map = get_vendor_alias_map()
        allowed_list = get_allowed_vendors_for_asset(aset)
    except Exception:
        alias_map = VENDOR_ALIASES
        allowed_list = list(ALLOWED_VENDORS_BY_ASSET.get(aset, ()))

    allowed = ", ".join(allowed_list)
    if not raw_vendor or not raw_vendor.strip():
        return False, None, f"Vendor wajib diisi (tidak boleh kosong). Pilihan {aset}: {allowed}."

    cleaned = re.sub(r"[^A-Z0-9 ]", " ", raw_vendor.upper())
    cleaned = re.sub(r"\b(?:PT|CV|UD|KOPERASI)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return False, None, f"Vendor '{raw_vendor}' tidak valid. Pilihan {aset}: {allowed}."

    canonical = alias_map.get(cleaned)
    if not canonical:
        for alias, target in sorted(alias_map.items(), key=lambda kv: len(kv[0]), reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", cleaned):
                canonical = target
                break

    if not canonical:
        return False, None, f"Vendor '{raw_vendor}' tidak dikenal. Vendor resmi {aset}: {allowed}."

    return True, canonical, ""


def _i(
    code: str,
    uraian: str,
    satuan: str,
    group: str,
    *aliases: str,
    key: Optional[str] = None,
    kw: Optional[str] = None,
) -> BOQItem:
    final_kw = kw or (aliases[0].title() if aliases else uraian.split("(")[0].strip()[:36])
    return BOQItem(
        item_key=key or code,
        display_code=code,
        keyword=final_kw,
        uraian=uraian,
        satuan=satuan,
        group=group,
        aliases=tuple(a.lower() for a in aliases),
    )


# ---------------------------------------------------------------------------
# Canonical BOQ Catalog mapped 1:1 to DATA UNTUK VOL matrix sheets
# ---------------------------------------------------------------------------

PV_ITEMS: Tuple[BOQItem, ...] = (
    _i("I.1", "Dokumentasi dan Pelaporan", "LS (bulan)", "PV", kw="Dokumentasi"),
    _i("I.2", "Traffic Managemen dan Perambuan 1 (satu) sisi", "set / tim / hari", "PV", "tm 1 sisi", kw="TM 1 Sisi"),
    _i("I.3", "Traffic Managemen dan Perambuan 2 (dua) sisi", "set / tim / hari", "PV", "tm 2 sisi", kw="TM 2 Sisi"),
    _i("I.4", "Penerangan Pekerjaan Malam Hari", "set / tim / hari", "PV", "penerangan malam", kw="Penerangan Malam"),
    _i("I.5", "APD (rompi, helm, sarung tangan, safety shoes) dan Perlengkapan K3", "set / tim / hari", "PV", "apd", kw="APD"),
    _i("I.6", "Sewa Kendaraan Mobilisasi/demobilisasi penumpang inc BBM, Toll (Minibus Harian)", "set / tim / hari", "PV", kw="Minibus"),
    _i("I.7", "Sewa Kendaraan Mengangkut Hotmix inc BBM, Toll (truk)", "unit / tim / hari", "PV", kw="Truk Hotmix"),
    _i("I.8", "Sewa Kendaraan mobilisasi/demobilisasi Peralatan Patching, K3 dan Perambuan inc BBM, Toll (truk)", "set unit / hari", "PV", kw="Truk Patching"),
    _i("I.9", "Sewa Kendaraan mobilisasi K3 dan Perambuan tambahan (pick up)", "set unit / hari", "PV", kw="Pick Up K3"),
    _i("II.1", "Jasa Patching perkerasan flexible material hotmix", "m3", "PV", "permanen", "jasa hotmix", "patching permanen", "patching flexible", "hotmix patching", "patching aspal", kw="Permanen"),
    _i("II.2", "Jasa Patching perkerasan rigid atau sapu lubang (material hotmix/coldmix)", "m3", "PV", "salob", "sapu lubang", "patching rigid", "coldmix patching", kw="Salob"),
    _i("II.2A", "Jasa Pengolahan Srcapmix (Jasa Demob Material, Jasa Saringan, Jasa Mix (in.Mixer), Jasa Packing dan Pembuangan disposal)", "m3", "PV", "jasa scrapmix", "jasa srcapmix", "pengolahan scrapmix", "scrapmix jasa", kw="Jasa Scrapmix"),
    _i("II.3", "Cat marka (Cold Paint)", "m2", "PV", "cat marka", "cold paint", kw="Cat Marka"),
    _i("II.4", "Marka Jalan (Thermoplast Putih)", "m2", "PV", "marka putih", "thermoplast putih", kw="Marka Putih"),
    _i("II.5", "Marka Jalan (Thermoplast Kuning)", "m2", "PV", "marka kuning", "thermoplast kuning", kw="Marka Kuning"),
    _i("II.6", "Pengadaan hotmix", "Ton", "PV", "hotmix", "docket", "docket hotmix", "ton hotmix", kw="Hotmix"),
    _i("II.7", "Pengadaan coldmix", "Zak", "PV", "coldmix", "sak coldmix", kw="Coldmix"),
    _i("II.7A", "Pengadaan Material Bahan Tambah Srcapmix (Pertamax, Dexlite, Semen dan Plastik Polyetilen)", "ls", "PV", "bahan tambah scrapmix", "material scrapmix", kw="Material Scrapmix"),
    _i("II.8", "Pengadaan Plastik Polyetilen", "Lbr", "PV", "plastik polyetilen", kw="Plastik Polyetilen"),
    _i("II.9a", "Pengadaan Minyak Tanah", "Ltr", "PV", "minyak tanah", kw="Minyak Tanah"),
    _i("II.9b", "Pengadaan Pertamax", "Ltr", "PV", "pertamax", kw="Pertamax"),
    _i("II.9c", "Pengadaan Dexlite", "Ltr", "PV", "dexlite", kw="Dexlite"),
    _i("II.10", "Pengadaan Semen 50 Kg ex. Indocement", "Zak", "PV", "semen", kw="Semen"),
    _i("III.1", "Sealant (maksimal 1,00 cm)", "m'", "PV", "sealant 1cm", "sealant 1", "sealant <=1", "sealant lebar 1", kw="Sealant 1cm"),
    _i("III.2", "Sealant TJ (4 cm)", "m'", "PV", "sealant 4cm", "sealant tj 4", "sealant 1-4", kw="Sealant 4cm"),
    _i("III.3", "Sealant TJ (4-6 cm) + agregat", "m'", "PV", "sealant 4-6cm", "sealant 4-6", "sealant agregat", kw="Sealant 4-6cm"),
    _i("III.4", "Aspaltic plug + agregat", "m2", "PV", "asphaltic plug", "aspaltic plug", kw="Asphaltic Plug"),
    _i("IV.1", "Expansion joint tebal 7cm", "m'", "PV", "ex joint", "expansion joint", kw="Ex Joint"),
    _i("IV.2", "Penggantian plat sumbat expansion joint tebal minimal 3 mm", "kg", "PV", "plat sumbat", "plat besi", kw="Plat Sumbat"),
    _i("V.1", "Sopir/mandor/pelaksana", "Hok", "PV", "mandor", "sopir", "pelaksana", kw="Mandor"),
    _i("V.2", "Pekerja", "Hok", "PV", "pekerja", "tenaga kerja", kw="Pekerja"),
    _i("V.3", "Lembur antara jam 17.00 - 21.00 WIB /mandor", "Jam", "PV", "lembur mandor", kw="Lembur Mandor"),
    _i("V.4", "Lembur antara jam 17.00 - 21.00 WIB /pekerja", "Jam", "PV", "lembur pekerja", kw="Lembur Pekerja"),
    _i("V.5", "Lembur diatas jam 21.00 WIB /mandor", "Ls", "PV", "lembur21 mandor", kw="Lembur 21 Mandor"),
    _i("V.6", "Lembur diatas jam 21.00 WIB /pekerja", "Ls", "PV", "lembur21 pekerja", kw="Lembur 21 Pekerja"),
    _i("VI.1", "Sewa Molen 500 Ltr (Inc. BBM)", "hr", "PV", "molen", kw="Molen"),
    _i("VI.2", "Traffic Managemen dan Perambuan 1 (satu) sisi", "set / tim / hari", "PV", "tf tm 1 sisi", kw="TF TM 1 Sisi"),
    _i("VI.3", "Traffic Managemen dan Perambuan 2 (dua) sisi", "set / tim / hari", "PV", "tf tm 2 sisi", kw="TF TM 2 Sisi"),
    _i("VI.4", "Penerangan Pekerjaan Malam Hari", "set / tim / hari", "PV", "tf penerangan malam", kw="TF Penerangan"),
    _i("VI.5", "APD (rompi, helm, sarung tangan, safety shoes) dan Perlengkapan K3", "set / tim / hari", "PV", "tf apd", kw="TF APD"),
    _i("VI.6", "Sewa Kendaraan Mobilisasi/demobilisasi penumpang inc BBM, Toll (Minibus Harian)", "set / tim / hari", "PV", "tf minibus", kw="TF Minibus"),
    _i("VI.7", "Sewa Kendaraan Mengangkut Hotmix inc BBM, Toll (truk)", "unit / tim / hari", "PV", "tf truk hotmix", kw="TF Truk Hotmix"),
    _i("VI.8", "Sewa Kendaraan mobilisasi/demobilisasi Peralatan Patching, K3 dan Perambuan inc BBM, Toll (truk)", "set unit / hari", "PV", "tf truk patching", kw="TF Truk Patching"),
    _i("VI.9", "Sewa Kendaraan mobilisasi K3 dan Perambuan tambahan (pick up)", "set unit / hari", "PV", "tf pick up", kw="TF Pick Up"),
)

SG_ITEMS: Tuple[BOQItem, ...] = (
    _i("I.1", "Dokumentasi dan Pelaporan", "ls", "SG", kw="Dokumentasi"),
    _i("I.2", "APD (rompi, helm, sarung tangan, safety shoes) dan perlengkapan K3", "ls", "SG", kw="APD"),
    _i("I.3", "Sewa Kendaraan Mobilisasi/demobilisasi penumpang inc BBM, Toll (Minibus)", "set / tim / hari", "SG", kw="Minibus"),
    _i("I.4", "Sewa Kendaraan Mobilisasi/demobilisasi peralatan inc BBM, Toll (truk)", "set / tim / hari", "SG", kw="Truk Peralatan"),
    _i("I.5", "Traffic Managemen dan Perambuan", "set / tim / hari", "SG", kw="Traffic Management"),
    _i("I.6", "Pemasangan Rambu Utuh", "Unit", "SG", "rambu utuh", kw="Rambu Utuh"),
    _i("I.7", "Pembuatan dan pemasangan KM lengkap", "Unit", "SG", "patok km", "km lengkap", kw="Patok KM"),
    _i("I.8", "Pembuatan dan pemasangan tiang / rangka rambu regulatory", "Unit", "SG", "tiang regulatory", kw="Tiang Regulatory"),
    _i("I.9", "Pembuatan dan pemasangan tiang / rangka rambu cevron", "Unit", "SG", "tiang chevron", "chevron", "cevron", kw="Tiang Chevron"),
    _i("I.10", "Pembuatan dan pemasangan tiang", "m", "SG", "tiang rambu", kw="Tiang Rambu"),
    _i("I.11", "Pembuatan dan pemasangan rangka rambu lain - lain (umum)", "kg", "SG", "rangka rambu", kw="Rangka Rambu"),
    _i("I.12", "Penyediaan Panel Rambu Alumunium", "m2", "SG", "panel alumunium", "alumunium", kw="Panel Alumunium"),
    _i("I.13", "Penyediaan Panel Rambu Polycarbonate", "m2", "SG", "panel polycarbonate", "polycarbonate", kw="Panel Polycarbonate"),
    _i("I.14", "Penyediaan Panel Rambu ACP", "m2", "SG", "panel acp", "acp", kw="Panel ACP"),
    _i("I.15", "Penyediaan Panel Rambu PVC Foam Board Outdoor 8 mm", "m2", "SG", "panel pvc", "pvc foam", key="I.15-PVC", kw="Panel PVC"),
    _i("I.15", "Penyediaan stiker gambar rambu (A)", "m2", "SG", "stiker a", "gambar rambu a", key="I.15-STIKER", kw="Stiker A"),
    _i("I.16", "Penyediaan stiker gambar rambu (B)", "m2", "SG", "stiker b", kw="Stiker B"),
    _i("I.17", "Penyediaan stiker gambar rambu (C)", "m2", "SG", "stiker c", kw="Stiker C"),
    _i("I.18", "Penyediaan stiker gambar rambu (D)", "m2", "SG", "stiker d", kw="Stiker D"),
    _i("I.19", "Penyediaan stiker gambar rambu (E)", "m2", "SG", "stiker e", kw="Stiker E"),
    _i("I.20", "Penyediaan stiker gambar rambu (F)", "m2", "SG", "stiker f", kw="Stiker F"),
    _i("I.21", "Penyediaan stiker gambar rambu (G)", "m2", "SG", "stiker g", kw="Stiker G"),
    _i("I.22", "Penyediaan stiker 3M/setara, DG Warna putih", "m2", "SG", "stiker dg putih", kw="Stiker DG Putih"),
    _i("I.23", "Penyediaan stiker 3M/setara, DG colour selain putih", "m2", "SG", "stiker dg warna", kw="Stiker DG Warna"),
    _i("I.24", "Penyediaan stiker 3M/setara, EG Prismatik", "m2", "SG", "eg prismatik", kw="Stiker EG Prismatik"),
    _i("I.25", "Penyediaan stiker 3M/setara, EG Biasa/Classic", "m2", "SG", "eg biasa", kw="Stiker EG Biasa"),
    _i("I.26", "Penyediaan Stiker Hitam", "m2", "SG", "stiker hitam", kw="Stiker Hitam"),
    _i("I.27", "Pengeboran dan pemasangan Anchor", "Titik", "SG", "anchor", kw="Anchor"),
    _i("I.28", "Pemasangan rambu RPPJ kupu kupu", "Unit", "SG", "rppj", kw="RPPJ"),
    _i("I.29", "Pengecatan ulang tiang/rangka/panel rambu", "m1", "SG", "cat tiang rambu", kw="Cat Tiang Rambu"),
    _i("I.30", "Pembuatan pondasi rambu umum lainnya", "m3", "SG", "pondasi rambu", kw="Pondasi Rambu"),
    _i("I.31", "Pembesian untuk Pondasi", "Kg", "SG", "pembesian rambu", kw="Pembesian Pondasi"),
    _i("I.32", "Pembongkaran Guide Post", "unit", "SG", "bongkar guide post", kw="Bongkar Guide Post"),
    _i("I.33", "Pembongkaran Delineator", "unit", "SG", "bongkar delineator", kw="Bongkar Delineator"),
    _i("I.34", "Perbaikan rambu, inc. pengelasan", "Kg", "SG", "perbaikan rambu", "las rambu", kw="Perbaikan Rambu"),
    _i("I.35", "Pengecatan rambu", "m2", "SG", "pengecatan rambu", kw="Cat Rambu"),
    _i("II.1", "Pengadaan & Pemasangan Guide Post Tipe 1", "Unit", "SG", "guide post 1", kw="Guide Post 1"),
    _i("II.2", "Pengadaan & Pemasangan Guide Post Tipe 2", "Unit", "SG", "guide post 2", kw="Guide Post 2"),
    _i("II.3", "Pengadaan & Pemasangan Guide Post Tipe 3", "Unit", "SG", "guide post 3", kw="Guide Post 3"),
    _i("II.4", "Pondasi Guide Post Tipe 1", "Unit", "SG", "pondasi guide post", kw="Pondasi Guide Post"),
    _i("II.5", "Pengadaan dan Pemasangan Deliniator Tipe 1", "Unit", "SG", "delineator 1", "deliniator 1", kw="Delineator 1"),
    _i("II.6", "Pengadaan dan Pemasangan Deliniator Tipe 2", "Unit", "SG", "delineator 2", "deliniator 2", kw="Delineator 2"),
    _i("II.7", "Pengadaan dan Pemasangan Deliniator Tipe 3", "Unit", "SG", "delineator 3", "deliniator 3", kw="Delineator 3"),
)

GR_WR_ITEMS: Tuple[BOQItem, ...] = (
    _i("I.1", "Dokumentasi dan Pelaporan", "ls", "GR_WR", kw="Dokumentasi"),
    _i("I.2", "Traffic Managemen dan Perambuan", "set / tim / hari", "GR_WR", kw="Traffic Management"),
    _i("I.3", "APD (rompi, helm, sarung tangan, safety shoes) dan perlengkapan K3", "ls", "GR_WR", kw="APD"),
    _i("I.4", "Sewa Kendaraan Mobilisasi/demobilisasi penumpang inc BBM, Toll (Minibus)", "set / tim / hari", "GR_WR", kw="Minibus"),
    _i("I.5", "Sewa Kendaraan Mobilisasi/demobilisasi peralatan inc BBM, Toll (truk)", "set / tim / hari", "GR_WR", kw="Truk Peralatan"),
    _i("II.1", "Bongkar beam", "Btg", "GR", "bongkar beam", kw="Bongkar Beam"),
    _i("II.2", "Bongkar Tiang Beton", "Tiang", "GR", "bongkar tiang beton", kw="Bongkar Tiang Beton"),
    _i("II.3", "Bongkar Tiang Baja", "Tiang", "GR", "bongkar tiang baja", kw="Bongkar Tiang Baja"),
    _i("II.4", "Bongkar Block Piece", "Buah", "GR", "bongkar block piece", "bongkar block", kw="Bongkar Block"),
    _i("II.5", "Bongkar End Terminal", "Buah", "GR", "bongkar end terminal", "bongkar end", kw="Bongkar End"),
    _i("II.6", "Bongkar Terminal Type C Buffer Head (40x110,5x2.7)", "Buah", "GR", "bongkar type c", kw="Bongkar Type C"),
    _i("II.7", "Bongkar Antiglare Type 1 (Antiglare + Lengan Pipa Besi)", "Buah", "GR", "bongkar antiglare", kw="Bongkar Antiglare"),
    _i("II.8", "Bongkar Crash Cusion", "set", "GR", "bongkar crash cushion", key="II.8-BONGKAR", kw="Bongkar Crash Cushion"),
    _i("II.8", "Pasang Beam", "Btg", "GR", "pasang beam", key="II.8-PASANG", kw="Pasang Beam"),
    _i("II.9", "Pasang Tiang Baja (178x78x6x1800)", "Tiang", "GR", "pasang tiang 1800", kw="Pasang Tiang 1800"),
    _i("II.10", "Pasang Tiang Baja (178x78x6x2400)", "Tiang", "GR", "pasang tiang 2400", kw="Pasang Tiang 2400"),
    _i("II.11", "Pasang Block Piece", "Buah", "GR", "pasang block piece", "pasang block", kw="Pasang Block"),
    _i("II.12", "Pasang End Teriminal", "Buah", "GR", "pasang end", "pasang end terminal", "pasang end post", kw="Pasang End"),
    _i("II.13", "Pasang Terminal Type C Buffer Head (40x110,5x2.7)", "Buah", "GR", "pasang type c", kw="Pasang Type C"),
    _i("II.14", "Pasang Antiglare Type 1 (Antiglare + Lengan Pipa Besi)", "Buah", "GR", "pasang antiglare", kw="Pasang Antiglare"),
    _i("II.15", "Pasang penggantian three beam (tidak termasuk bobok parapet)", "Buah", "GR", "pasang three beam", "pasang tribeam", key="II.15-PASANG", kw="Pasang Tribeam"),
    _i("II.16", "Pasang reducer three beam", "Buah", "GR", "pasang reducer", key="II.16-PASANG", kw="Pasang Reducer"),
    _i("II.17", "Pasang chanel post three beam", "Tiang", "GR", "pasang channel post", key="II.17-PASANG", kw="Pasang Channel Post"),
    _i("II.18", "Pasang blocking piece three beam", "Buah", "GR", "pasang blocking three beam", key="II.18-PASANG", kw="Pasang Blocking Tribeam"),
    _i("II.19", "Pasang blocking piece reducer three beam", "Buah", "GR", "pasang blocking reducer", key="II.19-PASANG", kw="Pasang Blocking Reducer"),
    _i("II.20", "pasang connector three beam", "Buah", "GR", "pasang connector", key="II.20-PASANG", kw="Pasang Connector"),
    _i("II.15", "Pengadaan Beam (312x83x2,7x4318)", "Btg", "GR", "pengadaan beam", "material beam", key="II.15-MAT", kw="Pengadaan Beam"),
    _i("II.16", "Pengadaan tiang baja (178x78x6x1800)", "Tiang", "GR", "pengadaan tiang 1800", key="II.16-MAT", kw="Pengadaan Tiang 1800"),
    _i("II.17", "Pengadaan tiang baja (178x78x6x2400)", "Tiang", "GR", "pengadaan tiang 2400", key="II.17-MAT", kw="Pengadaan Tiang 2400"),
    _i("II.18", "Pengadaan Block Piece (178x78x6x350)", "Buah", "GR", "pengadaan block piece", "pengadaan block", key="II.18-MAT", kw="Pengadaan Block"),
    _i("II.19", "Pengadaan end Terminal (254x2,7x725)", "Buah", "GR", "pengadaan end terminal", "pengadaan end", key="II.19-MAT", kw="Pengadaan End"),
    _i("II.20", "Pengadaan Terminal Type C Buffer Head (40x110,5x2.7)", "buah", "GR", "pengadaan type c", key="II.20-MAT", kw="Pengadaan Type C"),
    _i("II.21", "Pengadaan Antiglare Type 1 (Antiglare + Lengan Pipa Besi)", "Buah", "GR", "pengadaan antiglare", kw="Pengadaan Antiglare"),
    _i("II.21B", "Pengadaan dan Pemasangan crush cushion 7 sirip", "Set", "GR", "crash cushion 7 sirip", kw="Crash Cushion 7 Sirip"),
    _i("II.22", "Pengadaan dan Pemasangan Deliniator Tipe 1", "Unit", "GR", kw="GR Delineator 1"),
    _i("II.23", "Pengadaan dan Pemasangan Deliniator Tipe 2", "Unit", "GR", kw="GR Delineator 2"),
    _i("II.24", "Pengadaan dan Pemasangan Deliniator Tipe 3", "Unit", "GR", kw="GR Delineator 3"),
    _i("II.25", "Tribeam 4320 x 506 2.7 mm", "unit", "GR", "pengadaan tribeam", kw="Pengadaan Tribeam"),
    _i("II.26", "reducer tribeam 2223 x 506 x 312 x 2.7 mm", "unit", "GR", "pengadaan reducer", kw="Pengadaan Reducer"),
    _i("II.27", "Channel post tribeam 1800x178x78x6 mm", "unit", "GR", "pengadaan channel post", kw="Pengadaan Channel Post"),
    _i("II.28", "Blocking piece tribeam 400x178x78x6", "unit", "GR", kw="Blocking Tribeam 400"),
    _i("II.29", "Blocking piece tribeam 570x178x78x6", "unit", "GR", kw="Blocking Tribeam 570"),
    _i("II.30", "Connector tribeam", "unit", "GR", kw="Pengadaan Connector"),
    _i("III.1", "Line Post 1080mm", "Tiang", "WR", "pengadaan line post", "line post", kw="Pengadaan Line Post"),
    _i("III.2", "Post Cap", "Unit", "WR", "pengadaan post cap", kw="Pengadaan Post Cap"),
    _i("III.3", "Peg Bobbin", "Buah", "WR", "pengadaan peg bobbin", kw="Pengadaan Peg Bobbin"),
    _i("III.4", "Excluder", "Unit", "WR", "pengadaan excluder", kw="Pengadaan Excluder"),
    _i("III.5", "Socket Post", "Unit", "WR", "pengadaan socket post", kw="Pengadaan Socket Post"),
    _i("III.6", "Wire Rope only", "mtr", "WR", "wire rope only", "sling wire rope", kw="Wire Rope"),
    _i("III.7", "Check Rope", "Unit", "WR", "pengadaan check rope", kw="Pengadaan Check Rope"),
    _i("III.8", "Shackle", "Unit", "WR", "pengadaan shackle", kw="Pengadaan Shackle"),
    _i("III.9", "End Fitting", "Unit", "WR", "end fitting", kw="End Fitting"),
    _i("III.10", "Rigging Screw", "Unit", "WR", "rigging screw", kw="Rigging Screw"),
    _i("III.11", "Reflective sticker only", "Buah", "WR", "reflective sticker", kw="Reflective Sticker"),
    _i("III.12", "Cable Ties", "Buah", "WR", "cable ties", kw="Cable Ties"),
    _i("III.13", "Besi Behel", "Buah", "WR", "besi behel", kw="Besi Behel"),
    _i("III.14", "Bongkar Tiang Wire Rope (Termasuk Perapihan Kembali)", "Tiang", "WR", "bongkar tiang wire rope", "bongkar tiang wr", kw="Bongkar Tiang WR"),
    _i("III.15", "Line / Deflection post (upah pasang) 1.080", "Tiang", "WR", "pasang line post 1080", "pasang line post", kw="Pasang Line Post 1080"),
    _i("III.16", "Line / Deflection post (upah pasang) 1.403", "Tiang", "WR", "pasang line post 1403", kw="Pasang Line Post 1403"),
    _i("III.17", "Socket post (Upah Pasang)", "Buah", "WR", "pasang socket post", kw="Pasang Socket Post"),
    _i("III.18", "Post Cap (Upah Pasang)", "Buah", "WR", "pasang post cap", kw="Pasang Post Cap"),
    _i("III.19", "Excluder (Upah Pasang)", "Buah", "WR", "pasang excluder", kw="Pasang Excluder"),
    _i("III.20", "Peg Bobin (Upah Pasang)", "Buah", "WR", "pasang peg bobbin", "pasang peg bobin", kw="Pasang Peg Bobbin"),
    _i("III.21", "Check Rope & Shackle (Upah Pasang)", "unit", "WR", "pasang check rope", kw="Pasang Check Rope"),
    _i("III.22", "Pengrepesan beam Guardrail", "Btg", "GR", "press beam", "pengrepesan beam", kw="Press Beam"),
    _i("III.23", "Pengepresan Tiang Guardrail (178x78x6x1800) Termasuk biaya angkut", "Tiang", "GR", "press tiang 1800", kw="Press Tiang 1800"),
    _i("III.24", "Pengepresan Tiang Guardrail (178x78x6x2400) Termasuk biaya angkut", "Tiang", "GR", "press tiang 2400", kw="Press Tiang 2400"),
    _i("III.25", "Pengadaan dan Pengelasan Mur & Baut Galvaniz", "Buah", "GR_WR", "mur baut", "baut guardrail", kw="Mur Baut"),
    _i("III.26", "Lining / Perapihan Guardrail", "Span beam", "GR", "lining", "perapihan guardrail", kw="Lining"),
    _i("III.27", "Pemasangan Anti Silau (Material MMS)", "Titik", "GR", "pasang anti silau mms", kw="Anti Silau MMS"),
    _i("III.28", "Pengepresan Tiang Wire Rope + Galvaniz", "Batang", "WR", "press tiang wire rope", "press tiang wr", kw="Press Tiang WR"),
    _i("III.29", "Cor Socket Post (adk 1ps:1,5pc:2kr) dia=30cm, h=90cm", "Unit", "WR", "cor socket post", "cor socket", kw="Cor Socket"),
    _i("III.30", "Urugan Tanah Merah", "m3", "GR_WR", kw="Urugan Tanah"),
    _i("III.31", "Pasang Batu Kali (adk 1:4)", "m3", "GR_WR", kw="Batu Kali"),
    _i("III.32", "Rabat Beton", "m3", "GR_WR", kw="Rabat Beton"),
    _i("III.33", "Pengelasan Wire rope", "Titik", "WR", "las wire rope", "las wr", kw="Las WR"),
    _i("III.34", "Penyambungan Wire rope", "Titik", "WR", "sambung wire rope", "sambung wr", kw="Sambung WR"),
    _i("III.35", "Tensioning Wirerope", "Meter", "WR", "tensioning", kw="Tensioning"),
    _i("III.36", "Mechanical Fitting", "set", "WR", "mechanical fitting", kw="Mechanical Fitting"),
    _i("III.37-CAT", "Pengecatan Guardrail menggunakan cat type PU (all asset)", "m", "GR", "cat guardrail", key="III.37-CAT", kw="Cat Guardrail"),
    _i("III.37", "Sopir/mandor/pelaksana", "Hok", "GR_WR", "mandor", key="III.37-HOK", kw="Mandor"),
    _i("III.38", "Pekerja", "Hok", "GR_WR", "pekerja", kw="Pekerja"),
    _i("III.39", "Lembur antara jam 17.00 - 21.00 WIB /mandor", "Jam", "GR_WR", kw="Lembur Mandor"),
    _i("III.40", "Lembur antara jam 17.00 - 21.00 WIB /pekerja", "Jam", "GR_WR", kw="Lembur Pekerja"),
    _i("III.41", "Lembur diatas jam 21.00 WIB /mandor", "Ls", "GR_WR", kw="Lembur 21 Mandor"),
    _i("III.42", "Lembur diatas jam 21.00 WIB /pekerja", "Ls", "GR_WR", kw="Lembur 21 Pekerja"),
)

# Rumput STA mainlane segments mapped directly to RM LC W1 and RMLC2 rows
# tuple: (item_key, pass_no, wilayah, lajur_label, km_start, km_end, exact_label)
RUMPUT_MAINLANE_SEGMENTS: Tuple[Tuple[str, int, str, str, int, int, str], ...] = (
    # W1 Pass 1
    ("RM.P1.W1.26400", 1, "W1", "Mainlane Lajur Ke-4", 26400, 27500, "- Type B KM 26+400 s/d KM 27+500"),
    ("RM.P1.W1.27500", 1, "W1", "Mainlane Lajur Ke-4", 27500, 29560, "- Type F KM 27+500 s/d KM 29+560"),
    ("RM.P1.W1.29560", 1, "W1", "Mainlane Lajur Ke-4", 29560, 31150, "- Type G KM 29+560 s/d KM 31+150"),
    ("RM.P1.W1.31150", 1, "W1", "Mainlane Lajur Ke-4", 31150, 36150, "- Type E KM 31+150 s/d KM 36+150"),
    ("RM.P1.W1.36150", 1, "W1", "Mainlane Lajur Ke-4", 36150, 38750, "- Type A KM 36+150 s/d KM 38+750"),
    ("RM.P1.W1.38750", 1, "W1", "Mainlane Lajur Ke-4", 38750, 41000, "- Type E KM 38+750 s/d KM 41+000"),
    ("RM.P1.W1.41000", 1, "W1", "Mainlane Lajur Ke-3", 41000, 43000, "- Type A KM 41+000 s/d KM 43+000"),
    ("RM.P1.W1.43000", 1, "W1", "Mainlane Lajur Ke-3", 43000, 47000, "- Type A KM 43+000 s/d KM 47+000"),
    ("RM.P1.W1.47000", 1, "W1", "Mainlane Lajur Ke-3", 47000, 47600, "- Type E KM 47+000 s/d KM 47+600"),
    ("RM.P1.W1.47600", 1, "W1", "Mainlane Lajur Ke-3", 47600, 47750, "- Type B KM 47+600 s/d KM 47+750"),
    ("RM.P1.W1.47750", 1, "W1", "Mainlane Lajur Ke-3", 47750, 48750, "- Type E KM 47+750 s/d KM 48+750"),
    ("RM.P1.W1.48750", 1, "W1", "Mainlane Lajur Ke-3", 48750, 52750, "- Type A KM 48+750 s/d KM 52+750"),
    ("RM.P1.W1.52750", 1, "W1", "Mainlane Lajur Ke-3", 52750, 53750, "- Type B KM 52+750 s/d KM 53+750"),
    ("RM.P1.W1.53750", 1, "W1", "Mainlane Lajur Ke-3", 53750, 55500, "- Type A KM 53+750 s/d KM 55+500"),
    ("RM.P1.W1.55500", 1, "W1", "Mainlane Lajur Ke-3", 55500, 56000, "- Type B KM 55+500 s/d KM 56+000"),
    ("RM.P1.W1.56000", 1, "W1", "Mainlane Lajur Ke-3", 56000, 57000, "- Type A KM 56+000 s/d KM 57+000"),
    ("RM.P1.W1.57000", 1, "W1", "Mainlane Lajur Ke-3", 57000, 59000, "- Type B KM 57+000 s/d KM 59+000"),
    ("RM.P1.W1.59000", 1, "W1", "Mainlane Lajur Ke-3", 59000, 60000, "- Type A KM 59+000 s/d KM 60+000"),
    # W1 Pass 2
    ("RM.P2.W1.26400", 2, "W1", "Mainlane Lajur Ke-4", 26400, 27500, "- Type B KM 26+400 s/d KM 27+500"),
    ("RM.P2.W1.27500", 2, "W1", "Mainlane Lajur Ke-4", 27500, 29560, "- Type F KM 27+500 s/d KM 29+560"),
    ("RM.P2.W1.29560", 2, "W1", "Mainlane Lajur Ke-4", 29560, 31150, "- Type G KM 29+560 s/d KM 31+150"),
    ("RM.P2.W1.31150", 2, "W1", "Mainlane Lajur Ke-4", 31150, 36150, "- Type E KM 31+150 s/d KM 36+150"),
    ("RM.P2.W1.36150", 2, "W1", "Mainlane Lajur Ke-4", 36150, 38750, "- Type A KM 36+150 s/d KM 38+750"),
    ("RM.P2.W1.38750", 2, "W1", "Mainlane Lajur Ke-4", 38750, 41000, "- Type E KM 38+750 s/d KM 41+000"),
    ("RM.P2.W1.41000", 2, "W1", "Mainlane Lajur Ke-3", 41000, 43000, "- Type A KM 41+000 s/d KM 43+000"),
    ("RM.P2.W1.43000", 2, "W1", "Mainlane Lajur Ke-3", 43000, 47000, "- Type A KM 43+000 s/d KM 47+000"),
    ("RM.P2.W1.47000", 2, "W1", "Mainlane Lajur Ke-3", 47000, 47600, "- Type E KM 47+000 s/d KM 47+600"),
    ("RM.P2.W1.47600", 2, "W1", "Mainlane Lajur Ke-3", 47600, 47750, "- Type B KM 47+600 s/d KM 47+750"),
    ("RM.P2.W1.47750", 2, "W1", "Mainlane Lajur Ke-3", 47750, 48750, "- Type E KM 47+750 s/d KM 48+750"),
    ("RM.P2.W1.48750", 2, "W1", "Mainlane Lajur Ke-3", 48750, 52750, "- Type A KM 48+750 s/d KM 52+750"),
    ("RM.P2.W1.52750", 2, "W1", "Mainlane Lajur Ke-3", 52750, 53750, "- Type B KM 52+750 s/d KM 53+750"),
    ("RM.P2.W1.53750", 2, "W1", "Mainlane Lajur Ke-3", 53750, 55500, "- Type A KM 53+750 s/d KM 55+500"),
    ("RM.P2.W1.55500", 2, "W1", "Mainlane Lajur Ke-3", 55500, 56000, "- Type B KM 55+500 s/d KM 56+000"),
    ("RM.P2.W1.56000", 2, "W1", "Mainlane Lajur Ke-3", 56000, 57000, "- Type A KM 56+000 s/d KM 57+000"),
    ("RM.P2.W1.57000", 2, "W1", "Mainlane Lajur Ke-3", 57000, 59000, "- Type B KM 57+000 s/d KM 59+000"),
    ("RM.P2.W1.59000", 2, "W1", "Mainlane Lajur Ke-3", 59000, 60000, "- Type A KM 59+000 s/d KM 60+000"),
    # W2 Pass 1
    ("RM.P1.W2.60000", 1, "W2", "Mainlane Lajur Ke-3", 60000, 73700, "- Type A KM 60+000 s/d KM 73+700"),
    ("RM.P1.W2.73700", 1, "W2", "Mainlane Lajur Ke-2", 73700, 77350, "- Type B KM 73+700 s/d KM 77+350"),
    ("RM.P1.W2.77350", 1, "W2", "Mainlane Lajur Ke-2", 77350, 79000, "- Type E KM 77+350 s/d KM 79+000"),
    ("RM.P1.W2.79000", 1, "W2", "Mainlane Lajur Ke-2", 79000, 83000, "- Type E KM 79+000 s/d KM 83+000"),
    ("RM.P1.W2.83000", 1, "W2", "Mainlane Lajur Ke-2", 83000, 90200, "- Type A KM 83+000 s/d KM 90+200"),
    ("RM.P1.W2.90200", 1, "W2", "Mainlane Lajur Ke-2", 90200, 94100, "- Type E KM 90+200 s/d KM 94+100"),
    ("RM.P1.W2.94100", 1, "W2", "Mainlane Lajur Ke-2", 94100, 94900, "- Type D KM 94+100 s/d KM 94+900"),
    ("RM.P1.W2.94900", 1, "W2", "Mainlane Lajur Ke-2", 94900, 96200, "- Type C KM 94+900 s/d KM 96+200"),
    ("RM.P1.W2.96200", 1, "W2", "Mainlane Lajur Ke-2", 96200, 98200, "- Type B KM 96+200 s/d KM 98+200"),
    # W2 Pass 2
    ("RM.P2.W2.60000", 2, "W2", "Mainlane Lajur Ke-3", 60000, 73000, "- Type A KM 60+000 s/d KM 73+000"),
    ("RM.P2.W2.73700", 2, "W2", "Mainlane Lajur Ke-2", 73700, 77350, "- Type B KM 73+700 s/d KM 77+350"),
    ("RM.P2.W2.77350", 2, "W2", "Mainlane Lajur Ke-2", 77350, 79000, "- Type E KM 77+350 s/d KM 79+000"),
    ("RM.P2.W2.79000", 2, "W2", "Mainlane Lajur Ke-2", 79000, 83000, "- Type E KM 79+000 s/d KM 83+000"),
    ("RM.P2.W2.83000", 2, "W2", "Mainlane Lajur Ke-2", 83000, 90200, "- Type A KM 83+000 s/d KM 90+200"),
    ("RM.P2.W2.90200", 2, "W2", "Mainlane Lajur Ke-2", 90200, 94100, "- Type E KM 90+200 s/d KM 94+100"),
    ("RM.P2.W2.96200", 2, "W2", "Mainlane Lajur Ke-2", 96200, 98200, "- Type B KM 96+200 s/d KM 98+200"),
)

_RM_LOC_ITEMS: Tuple[BOQItem, ...] = (
    # Rumput Mainlane entries (generated programmatically from RUMPUT_MAINLANE_SEGMENTS)
    *[
        _i(
            seg[0],
            f"Potong Rumput ke-{seg[1]} ({seg[6].lstrip('- ')})",
            "m2",
            "RM",
            key=seg[0],
            kw=f"Rumput P{seg[1]} KM {seg[4]//1000}+{seg[4]%1000:03d}-{seg[5]//1000}+{seg[5]%1000:03d}",
        )
        for seg in RUMPUT_MAINLANE_SEGMENTS
    ],
    # Rumput Interchange
    _i("RM.IC.BITUNG", "Potong Rumput Interchange Bitung", "m2", "RM", key="RM.IC.BITUNG", kw="Rumput IC Bitung"),
    _i("RM.IC.CIKUPA", "Potong Rumput Interchange Cikupa", "m2", "RM", key="RM.IC.CIKUPA", kw="Rumput IC Cikupa"),
    _i("RM.IC.BALTIM", "Potong Rumput Interchange Balaraja Timur", "m2", "RM", key="RM.IC.BALTIM", kw="Rumput IC Baltim"),
    _i("RM.IC.BALBAR", "Potong Rumput Interchange Balaraja Barat", "m2", "RM", key="RM.IC.BALBAR", kw="Rumput IC Balbar"),
    _i("RM.IC.CIKANDE", "Potong Rumput Interchange Cikande", "m2", "RM", key="RM.IC.CIKANDE", kw="Rumput IC Cikande"),
    _i("RM.IC.CIUJUNG", "Potong Rumput Interchange Ciujung", "m2", "RM", key="RM.IC.CIUJUNG", kw="Rumput IC Ciujung"),
    _i("RM.IC.SERTIM", "Potong Rumput Interchange Serang Timur", "m2", "RM", key="RM.IC.SERTIM", kw="Rumput IC Sertim"),
    _i("RM.IC.SERBAR", "Potong Rumput Interchange Serang Barat", "m2", "RM", key="RM.IC.SERBAR", kw="Rumput IC Serbar"),
    _i("RM.IC.CILTIM", "Potong Rumput Interchange Cilegon Timur", "m2", "RM", key="RM.IC.CILTIM", kw="Rumput IC Ciltim"),
    _i("RM.IC.CILBAR", "Potong Rumput Interchange Cilegon Barat", "m2", "RM", key="RM.IC.CILBAR", kw="Rumput IC Cilbar"),
    _i("RM.IC.MERAK", "Potong Rumput Interchange Merak", "m2", "RM", key="RM.IC.MERAK", kw="Rumput IC Merak"),
    # Rumput Akses
    _i("RM.AK.BITUNG", "Potong Rumput Akses Bitung", "m2", "RM", key="RM.AK.BITUNG", kw="Rumput Akses Bitung"),
    _i("RM.AK.CIKUPA", "Potong Rumput Akses Cikupa", "m2", "RM", key="RM.AK.CIKUPA", kw="Rumput Akses Cikupa"),
    _i("RM.AK.BALTIM", "Potong Rumput Akses Balaraja Timur", "m2", "RM", key="RM.AK.BALTIM", kw="Rumput Akses Baltim"),
    _i("RM.AK.BALBAR", "Potong Rumput Akses Balaraja Barat", "m2", "RM", key="RM.AK.BALBAR", kw="Rumput Akses Balbar"),
    _i("RM.AK.CIKANDE", "Potong Rumput Akses Cikande", "m2", "RM", key="RM.AK.CIKANDE", kw="Rumput Akses Cikande"),
    _i("RM.AK.CIUJUNG", "Potong Rumput Akses Ciujung", "m2", "RM", key="RM.AK.CIUJUNG", kw="Rumput Akses Ciujung"),
    _i("RM.AK.SERTIM", "Potong Rumput Akses Serang Timur", "m2", "RM", key="RM.AK.SERTIM", kw="Rumput Akses Sertim"),
    _i("RM.AK.SERBAR", "Potong Rumput Akses Serang Barat", "m2", "RM", key="RM.AK.SERBAR", kw="Rumput Akses Serbar"),
    _i("RM.AK.CILTIM", "Potong Rumput Akses Cilegon Timur", "m2", "RM", key="RM.AK.CILTIM", kw="Rumput Akses Ciltim"),
    _i("RM.AK.CILBAR", "Potong Rumput Akses Cilegon Barat", "m2", "RM", key="RM.AK.CILBAR", kw="Rumput Akses Cilbar"),
    _i("RM.AK.MERAK", "Potong Rumput Akses Merak", "m2", "RM", key="RM.AK.MERAK", kw="Rumput Akses Merak"),
    _i("RM.AK.PETAKPAPAT", "Potong Rumput Akses Petak Papat", "m2", "RM", key="RM.AK.PETAKPAPAT", kw="Rumput Akses Petak Papat"),
    # Ketrik
    _i("II.1", "Ketrik Bahu Jalan Mainlane", "m'", "RM", "ketrik mainlane", "ketrik bahu jalan", kw="Ketrik Mainlane"),
    _i("II.2.BITUNG", "Ketrik Bahu Jalan IC/Akses Bitung", "m'", "RM", key="II.2.BITUNG", kw="Ketrik IC/Akses Bitung"),
    _i("II.2.CIKUPA", "Ketrik Bahu Jalan IC/Akses Cikupa", "m'", "RM", key="II.2.CIKUPA", kw="Ketrik IC/Akses Cikupa"),
    _i("II.2.BALTIM", "Ketrik Bahu Jalan IC/Akses Balaraja Timur", "m'", "RM", key="II.2.BALTIM", kw="Ketrik IC/Akses Baltim"),
    _i("II.2.BALBAR", "Ketrik Bahu Jalan IC/Akses Balaraja Barat", "m'", "RM", key="II.2.BALBAR", kw="Ketrik IC/Akses Balbar"),
    _i("II.2.CIKANDE", "Ketrik Bahu Jalan IC/Akses Cikande", "m'", "RM", key="II.2.CIKANDE", kw="Ketrik IC/Akses Cikande"),
    _i("II.2.CIUJUNG", "Ketrik Bahu Jalan IC/Akses Ciujung", "m'", "RM", key="II.2.CIUJUNG", kw="Ketrik IC/Akses Ciujung"),
    _i("II.2.SERTIM", "Ketrik Bahu Jalan IC/Akses Serang Timur", "m'", "RM", key="II.2.SERTIM", kw="Ketrik IC/Akses Sertim"),
    _i("II.2.SERBAR", "Ketrik Bahu Jalan IC/Akses Serang Barat", "m'", "RM", key="II.2.SERBAR", kw="Ketrik IC/Akses Serbar"),
    _i("II.2.CILTIM", "Ketrik Bahu Jalan IC/Akses Cilegon Timur", "m'", "RM", key="II.2.CILTIM", kw="Ketrik IC/Akses Ciltim"),
    _i("II.2.CILBAR", "Ketrik Bahu Jalan IC/Akses Cilegon Barat", "m'", "RM", key="II.2.CILBAR", kw="Ketrik IC/Akses Cilbar"),
    _i("II.2.MERAK", "Ketrik Bahu Jalan IC/Akses Merak", "m'", "RM", key="II.2.MERAK", kw="Ketrik IC/Akses Merak"),
    _i("II.2.PETAKPAPAT", "Ketrik Bahu Jalan IC/Akses Petak Papat", "m'", "RM", key="II.2.PETAKPAPAT", kw="Ketrik Akses Petak Papat"),
    # Striping
    _i("II.3", "Striping Bahu Jalan Mainlane", "m'", "RM", "striping mainlane", "striping bahu jalan", kw="Striping Mainlane"),
    _i("II.4.BITUNG", "Striping Bahu Jalan IC/Akses Bitung", "m'", "RM", key="II.4.BITUNG", kw="Striping IC/Akses Bitung"),
    _i("II.4.CIKUPA", "Striping Bahu Jalan IC/Akses Cikupa", "m'", "RM", key="II.4.CIKUPA", kw="Striping IC/Akses Cikupa"),
    _i("II.4.BALTIM", "Striping Bahu Jalan IC/Akses Balaraja Timur", "m'", "RM", key="II.4.BALTIM", kw="Striping IC/Akses Baltim"),
    _i("II.4.BALBAR", "Striping Bahu Jalan IC/Akses Balaraja Barat", "m'", "RM", key="II.4.BALBAR", kw="Striping IC/Akses Balbar"),
    _i("II.4.CIKANDE", "Striping Bahu Jalan IC/Akses Cikande", "m'", "RM", key="II.4.CIKANDE", kw="Striping IC/Akses Cikande"),
    _i("II.4.CIUJUNG", "Striping Bahu Jalan IC/Akses Ciujung", "m'", "RM", key="II.4.CIUJUNG", kw="Striping IC/Akses Ciujung"),
    _i("II.4.SERTIM", "Striping Bahu Jalan IC/Akses Serang Timur", "m'", "RM", key="II.4.SERTIM", kw="Striping IC/Akses Sertim"),
    _i("II.4.SERBAR", "Striping Bahu Jalan IC/Akses Serang Barat", "m'", "RM", key="II.4.SERBAR", kw="Striping IC/Akses Serbar"),
    _i("II.4.CILTIM", "Striping Bahu Jalan IC/Akses Cilegon Timur", "m'", "RM", key="II.4.CILTIM", kw="Striping IC/Akses Ciltim"),
    _i("II.4.CILBAR", "Striping Bahu Jalan IC/Akses Cilegon Barat", "m'", "RM", key="II.4.CILBAR", kw="Striping IC/Akses Cilbar"),
    _i("II.4.MERAK", "Striping Bahu Jalan IC/Akses Merak", "m'", "RM", key="II.4.MERAK", kw="Striping IC/Akses Merak"),
    _i("II.4.PETAKPAPAT", "Striping Bahu Jalan IC/Akses Petak Papat", "m'", "RM", key="II.4.PETAKPAPAT", kw="Striping Akses Petak Papat"),
)

LC_ITEMS: Tuple[BOQItem, ...] = (
    _i("III.1", "Pendangiran Tanaman hias Border (Type A)", "m'", "LC", "pendangiran border", "pendangiran type a", kw="Pendangiran Border"),
    _i("III.2", "Pendangiran Tanaman hias pada Pot (Type B)", "m'", "LC", "pendangiran pot", "pendangiran type b", kw="Pendangiran Pot"),
    _i("III.3", "Pendangiran Tanaman hias pada FCB (Type C)", "m'", "LC", "pendangiran fcb", "pendangiran type c", kw="Pendangiran FCB"),
    _i("III.4", "Pendangiran Pohon hias (Pucuk Merah dan sejenisnya)", "Pohon", "LC", "pendangiran pucuk merah", kw="Pendangiran Pucuk Merah"),
    _i("III.5", "Pemangkasan Tanaman hias Border (Type A)", "m'", "LC", "pangkas border", "pemangkasan border", "border type a", kw="Pangkas Border"),
    _i("III.6", "Pemangkasan Tanaman hias pada Pot (Type B)", "m'", "LC", "pangkas pot", "pot type b", kw="Pangkas Pot"),
    _i("III.7", "Pemangkasan Tanaman hias pada FCB (Type C)", "m'", "LC", "pangkas fcb", "fcb type c", kw="Pangkas FCB"),
    _i("III.8", "Pangkas Pohon Bambu", "m'", "LC", "pangkas bambu", "pohon bambu", kw="Pangkas Bambu"),
    _i("III.9", "Pemangkasan Pohon hias (Pucuk Merah dan sejenisnya)", "Pohon", "LC", "pangkas pucuk merah", kw="Pangkas Pucuk Merah"),
    _i("III.10a", "Pangkas Pohon Dia. <30 cm (Full Dahan, Ranting dibuang keluar tol)", "Pohon", "LC", "pangkas <30", "pangkas <30cm", "pangkas pohon kecil", kw="Pangkas <30cm"),
    _i("III.10b", "Pangkas Pohon Dia >30 cm (Full Dahan, Ranting dibuang keluar tol)", "Pohon", "LC", "pangkas >30", "pangkas >30cm", "pangkas pohon besar", kw="Pangkas >30cm"),
    _i("III.11", "Penebangan Pohon Besar", "Pohon", "LC", "tebang pohon", "penebangan pohon", kw="Tebang Pohon"),
    _i("III.12", "Pemupukan dengan NPK", "Kg", "LC", "pupuk npk", "npk", kw="Pupuk NPK"),
    _i("III.13", "Pemupukan dengan Kompos", "Kg", "LC", "pupuk kompos", "kompos", kw="Pupuk Kompos"),
    _i("III.14", "Penanaman Tanaman dan Pembuatan Border (metode stek)*", "m'", "LC", "tanam border stek", kw="Tanam Border Stek"),
    _i("III.15", "Penanaman Tanaman pada Pot Border Kosong (metode stek)*", "m'", "LC", "tanam pot stek", kw="Tanam Pot Stek"),
    _i("III.16", "Penanaman Tanaman dan Pembuatan Border (jenis Kembang Sepatu)", "pohon", "LC", kw="Tanam Border Sepatu"),
    _i("III.17", "Penanaman Tanaman dan Pembuatan Border (jenis Bougenville)", "pohon", "LC", kw="Tanam Border Bougenville"),
    _i("III.18", "Penanaman Tanaman dan Pembuatan Border (jenis Lawelia)", "pohon", "LC", kw="Tanam Border Lawelia"),
    _i("III.19", "Penanaman Tanaman pada Pot Border Kosong (jenis Kembang Sepatu)", "pohon", "LC", kw="Tanam Pot Sepatu"),
    _i("III.20", "Penanaman Tanaman pada Pot Border Kosong (jenis Bougenville)", "pohon", "LC", kw="Tanam Pot Bougenville"),
    _i("III.21", "Penanaman Tanaman pada Pot Border Kosong (jenis Lawelia)", "pohon", "LC", kw="Tanam Pot Lawelia"),
    _i("IV.1", "Sopir/mandor/pelaksana", "Hok", "RM_LC", "mandor", kw="Mandor"),
    _i("IV.2", "Pekerja", "Hok", "RM_LC", "pekerja", kw="Pekerja"),
    _i("IV.3", "Lembur antara jam 17.00 - 21.00 WIB /mandor", "Jam", "RM_LC", kw="Lembur Mandor"),
    _i("IV.4", "Lembur antara jam 17.00 - 21.00 WIB /pekerja", "Jam", "RM_LC", kw="Lembur Pekerja"),
    _i("IV.5", "Lembur diatas jam 21.00 WIB /mandor", "Ls", "RM_LC", kw="Lembur 21 Mandor"),
    _i("IV.6", "Lembur diatas jam 21.00 WIB /pekerja", "Ls", "RM_LC", kw="Lembur 21 Pekerja"),
    _i("IV.7", "Sewa Kendaraan Mobilisasi/demobilisasi peralatan inc BBM, Toll (truk)", "set / tim / bulan", "RM_LC", kw="Truk Peralatan"),
    _i("IV.8", "Sewa Kendaraan Mobilisasi/demobilisasi peralatan inc BBM, Toll (Pickup)", "set / tim / bulan", "RM_LC", kw="Pick Up Peralatan"),
    _i("IV.9", "Sewa Kendaraan Mobilisasi/demobilisasi penumpang inc BBM, Toll (elf)", "set / tim / bulan", "RM_LC", kw="Elf Penumpang"),
    _i("IV.10", "Sewa Kendaraan Mobilisasi/demobilisasi penumpang inc BBM, Toll (Minibus)", "set / tim / bulan", "RM_LC", kw="Minibus"),
    _i("IV.11", "Traffic Managemen dan Perambuan (Non-Mobile) + Safety Watcher", "set / tim / bulan", "RM_LC", kw="TM Non-Mobile"),
    _i("IV.12", "Traffic Managemen dan Perambuan (Mobile)", "Hari", "RM_LC", "tm mobile", key="IV.12-TM", kw="TM Mobile"),
    _i("IV.13", "Dokumentasi dan Pelaporan", "LS (bulan)", "RM_LC", "dokumentasi", key="IV.13-DOK", kw="Dokumentasi"),
)

RM_LC_ITEMS: Tuple[BOQItem, ...] = _RM_LOC_ITEMS + LC_ITEMS

TRC_ITEMS: Tuple[BOQItem, ...] = (
    _i("I.1", "Dokumentasi dan Pelaporan", "LS (bulan)", "TRC", kw="Dokumentasi"),
    _i("I.2", "APD (rompi, helm, sarung tangan, safety shoes) dan perlengkapan K3", "set / tim / bulan", "TRC", kw="APD"),
    _i("I.3", "Sewa Kendaraan Mobilisasi/demobilisasi penumpang inc BBM, Toll (Minibus, Aksesoris)", "set / tim / bulan", "TRC", kw="Minibus"),
    _i("I.4", "Sewa Kendaraan Mobilisasi/demobilisasi peralatan inc BBM, Toll (truk)", "set / tim / bulan", "TRC", kw="Truk Peralatan"),
    _i("I.5", "Traffic Managemen dan Perambuan (Non-Mobile) (inc Safety Watcher)", "set / tim / bulan", "TRC", kw="TM Non-Mobile"),
    _i("I.6", "Traffic Managemen dan Perambuan (Mobile) (inc Mobil, Driver, Safety Watcher, Aksesoris, RC)", "set / tim / bulan", "TRC", kw="TM Mobile"),
    _i("I.7-SWEEPER", "Sewa Kendaraan Road Sweeper Kap. 6000 Ltr (Inc. Operator + BBM)", "Jam", "TRC", "road sweeper", key="I.7-SWEEPER", kw="Road Sweeper"),
    _i("I.7", "Sewa Kendaraan Mobilisasi/demobilisasi peralatan inc BBM, Toll (pick up)", "set / tim / bulan", "TRC", "pick up", "pickup", kw="Pick Up"),
    _i("II.1", "Sopir/mandor/pelaksana", "Hok", "TRC", "mandor", "sopir", "pelaksana", kw="Mandor"),
    _i("II.2", "Pekerja", "Hok", "TRC", "pekerja", "tenaga kerja", kw="Pekerja"),
    _i("II.2A", "Pengawas / Pengawas Safety", "Hok", "TRC", "pengawas safety", "pengawas", "safety", kw="Pengawas Safety"),
    _i("II.2B", "Pekerja Ketinggian (TKBT/TKPK)", "Hok", "TRC", "tkbt", "tkpk", "ketinggian", kw="TKBT"),
    _i("II.3", "Lembur antara jam 17.00 - 21.00 WIB /mandor", "Jam", "TRC", "lembur mandor", kw="Lembur Mandor"),
    _i("II.4", "Lembur antara jam 17.00 - 21.00 WIB /pekerja", "Jam", "TRC", "lembur pekerja", kw="Lembur Pekerja"),
    _i("II.5", "Lembur diatas jam 21.00 WIB /mandor", "Ls", "TRC", kw="Lembur 21 Mandor"),
    _i("II.6", "Lembur diatas jam 21.00 WIB /pekerja", "Ls", "TRC", kw="Lembur 21 Pekerja"),
)

DR_ITEMS: Tuple[BOQItem, ...] = (
    _i("I.1", "Dokumentasi dan Pelaporan", "LS (bulan)", "DR", kw="Dokumentasi"),
    _i("I.2", "APD (rompi, helm, sarung tangan, safety shoes) dan perlengkapan K3", "set / tim / bulan", "DR", kw="APD"),
    _i("I.3", "Sewa Kendaraan Mobilisasi/demobilisasi penumpang inc BBM, Toll (Minibus)", "set / tim / bulan", "DR", kw="Minibus"),
    _i("I.4", "Sewa Kendaraan Mobilisasi/demobilisasi peralatan inc BBM, Toll (truk)", "set / tim / bulan", "DR", kw="Truk Peralatan"),
    _i("I.5", "Traffic Managemen dan Perambuan", "set / tim / bulan", "DR", kw="Traffic Management"),
    _i("I.6", "Mobilisasi Excavator PC 75 (Besar)", "Rit", "DR", kw="Mob Exca PC75 Besar"),
    _i("I.7", "Mobilisasi Excavator PC 75 (Lokal)", "Rit", "DR", kw="Mob Exca PC75 Lokal"),
    _i("I.8", "Sewa Excavator PC 75 (Inc. Operator + BBM)", "Jam", "DR", kw="Sewa Exca PC75"),
    _i("I.9", "Mobilisasi Excavator PC 200 (Besar)", "Rit", "DR", kw="Mob Exca PC200 Besar"),
    _i("I.10", "Mobilisasi Excavator PC 200 (Lokal)", "Rit", "DR", kw="Mob Exca PC200 Lokal"),
    _i("I.11", "Sewa Excavator PC 200 (Inc. Operator + BBM)", "Jam", "DR", kw="Sewa Exca PC200"),
    _i("I.12", "Pengerukan lumpur/tanah saluran terbuka (dibuang ke luar lokasi jalan tol)", "m3", "DR", "keruk saluran terbuka", "pengerukan saluran terbuka", "lumpur terbuka", kw="Keruk Saluran Terbuka"),
    _i("I.13", "Pengerukan lumpur/tanah saluran tertutup; RCP dan box culvert (dibuang keluar lokasi jalan tol)", "m3", "DR", "keruk saluran tertutup", "pengerukan tertutup", "rcp", "box culvert", kw="Keruk Saluran Tertutup"),
    _i("II.1", "Pembersihan linning median dibuang ke luar lokasi jalan tol", "m", "DR", "bersih lining median", "pembersihan linning", "pembersihan median", kw="Bersih Lining Median"),
    _i("II.2", "Pembersihan saluran batu kali", "m2", "DR", "bersih batu kali", "pembersihan saluran batu kali", "babatan saluran", kw="Bersih Batu Kali"),
    _i("II.3", "Galian tanah dibuang keluar", "m3", "DR", "galian keluar", kw="Galian Keluar"),
    _i("II.4", "Galian tanah dibuang di sekitar ROW", "m3", "DR", "galian row", kw="Galian ROW"),
    _i("II.5", "Timbunan tanah merah (material dari luar) tidak dipadatkan", "m3", "DR", kw="Timbunan Tidak Padat"),
    _i("II.6", "Timbunan tanah merah (material dari luar) dipadatkan", "m3", "DR", "timbunan tanah merah", kw="Timbunan Dipadatkan"),
    _i("II.7", "Pasangan batu kali dengan batu kali baru", "m3", "DR", "batu kali baru", "pasangan batu kali baru", kw="Batu Kali Baru"),
    _i("II.8", "Pasangan batu kali dengan batu kali bekas", "m3", "DR", "batu kali bekas", "pasangan batu kali bekas", kw="Batu Kali Bekas"),
    _i("II.9", "Plesteran + aci", "m2", "DR", "plesteran aci", kw="Plesteran Aci"),
    _i("II.10", "Plesteran", "m2", "DR", "plesteran", kw="Plesteran"),
    _i("II.11", "Acian", "m2", "DR", "acian", kw="Acian"),
    _i("II.12", "Pasangan batu bata", "m2", "DR", "batu bata", kw="Batu Bata"),
    _i("II.13", "Rabat beton", "m2", "DR", "rabat beton", kw="Rabat Beton"),
    _i("II.14", "Beton terpasang setara K-175", "m3", "DR", "beton k-175", "k175", kw="Beton K-175"),
    _i("II.15", "Beton terpasang setara K-225", "m3", "DR", "beton k-225", "k225", kw="Beton K-225"),
    _i("II.16", "Beton terpasang setara K-350", "m3", "DR", "beton k-350", "k350", kw="Beton K-350"),
    _i("II.17", "Pembesian beton", "kg", "DR", "pembesian beton", kw="Pembesian Beton"),
    _i("II.18", "Wire mesh", "Kg", "DR", "wiremesh drainase", "wire mesh", kw="Wire Mesh"),
    _i("II.19", "Bekisting (Multiplex 18 mm + single film)", "m2", "DR", "bekisting", key="II.19-BEKISTING", kw="Bekisting"),
    _i("II.19", "Cerucuk terpasang panjang", "Btg", "DR", "cerucuk", key="II.19-CERUCUK", kw="Cerucuk"),
    _i("II.20", "Pasangan wheep hole pipa PVC", "Bh", "DR", "weep hole", "wheep hole", kw="Weep Hole"),
    _i("II.21", "Gebalan rumput", "m2", "DR", "gebalan rumput", kw="Gebalan Rumput"),
    _i("II.22", "Pasang rib bambu", "m2", "DR", "rib bambu", kw="Rib Bambu"),
    _i("II.23", "Pengadaan kayu dolken", "Btg", "DR", "kayu dolken", "dolken", kw="Kayu Dolken"),
    _i("II.24", "Pengadaan pasir dalam karung", "Bh", "DR", "pasir karung", kw="Pasir Karung"),
    _i("II.25", "Pembuatan tali air/sodetan", "m", "DR", "tali air", "sodetan", kw="Tali Air"),
    _i("II.26", "Bongkaran batu kali", "m3", "DR", "bongkar batu kali", "bongkaran batu kali", kw="Bongkar Batu Kali"),
    _i("II.27", "Bongkaran batu bata", "m2", "DR", "bongkar batu bata", "bongkaran batu bata", kw="Bongkar Batu Bata"),
    _i("II.28", "Bongkaran bangunan kayu", "m2", "DR", kw="Bongkar Kayu"),
    _i("II.29", "Perbaikan kansteen", "m", "DR", "kansteen", "perbaikan kansteen", kw="Kansteen"),
    _i("II.30", "Pengecatan kansteen", "m2", "DR", "cat kansteen", "pengecatan kansteen", kw="Cat Kansteen"),
    _i("II.31", "Saluran u-ditch 100x100", "m", "DR", "u-ditch", "uditch", kw="U-Ditch"),
    _i("III.1", "Sopir/mandor/pelaksana", "Hok", "DR", "mandor", kw="Mandor"),
    _i("III.2", "Pekerja", "Hok", "DR", "pekerja", kw="Pekerja"),
    _i("III.3", "Lembur antara jam 17.00 - 21.00 WIB /mandor", "Jam", "DR", kw="Lembur Mandor"),
    _i("III.4", "Lembur antara jam 17.00 - 21.00 WIB /pekerja", "Jam", "DR", kw="Lembur Pekerja"),
    _i("III.5", "Lembur diatas jam 21.00 WIB /mandor", "Ls", "DR", kw="Lembur 21 Mandor"),
    _i("III.6", "Lembur diatas jam 21.00 WIB /pekerja", "Ls", "DR", kw="Lembur 21 Pekerja"),
    _i("IV.1", "Payment for urgent work not in the contract", "ls", "DR", kw="Urgent Work"),
)

FE_ITEMS: Tuple[BOQItem, ...] = (
    _i("I.1", "Dokumentasi dan Pelaporan", "Ls", "FE", kw="Dokumentasi"),
    _i("I.2", "Sewa Kendaraan Mobilisasi/demobilisasi penumpang inc BBM, Toll (Minibus)", "set / tim / bulan", "FE", kw="Minibus"),
    _i("I.3", "Sewa Kendaraan Mobilisasi/demobilisasi peralatan inc BBM, Toll (truk)", "set / tim / bulan", "FE", kw="Truk Peralatan"),
    _i("I.4", "APD (rompi, helm, sarung tangan, safety shoes) dan perlengkapan K3", "set / tim / bulan", "FE", kw="APD"),
    _i("I.5", "Traffic Managemen dan Perambuan", "set / tim / bulan", "FE", kw="Traffic Management"),
    _i("II.1", "Pengadaan tiang panel beton uk. 230x18x17,5 cm, mutu K-225", "Unit", "FE", "pengadaan tiang panel 230", kw="Pengadaan Tiang 230"),
    _i("II.2", "Pengadaan tiang panel beton uk. 300x18x17,5 cm, mutu K-225", "Unit", "FE", "pengadaan tiang panel 300", kw="Pengadaan Tiang 300"),
    _i("II.3", "Pengadaan tiang panel beton uk. 380x18x17,5 cm, mutu K-225", "Unit", "FE", "pengadaan tiang panel 380", kw="Pengadaan Tiang 380"),
    _i("II.4", "Pengadaan tiang panel beton uk. 350x26x26 cm, mutu K-225", "Unit", "FE", "pengadaan tiang panel 350", kw="Pengadaan Tiang 350"),
    _i("II.5", "Pengadaan panel beton profil 240x40x5 cm, mutu K-225", "Unit", "FE", "pengadaan panel profil", kw="Pengadaan Panel Profil"),
    _i("II.6", "Pengadaan panel beton uk. 240x40x10 cm, mutu K-225", "Unit", "FE", "pengadaan panel 10cm", kw="Pengadaan Panel 10cm"),
    _i("II.7", "Pengadaan panel beton uk. 240x40x5 cm, mutu K-225", "Unit", "FE", "pengadaan panel 5cm", "pengadaan panel beton", "pengadaan panel polos", kw="Pengadaan Panel 5cm"),
    _i("II.8", "Pengadaan tiang kawat uk. 210x12x12 cm, mutu K-225", "Unit", "FE", "pengadaan tiang kawat", kw="Pengadaan Tiang Kawat"),
    _i("II.9", "Pengadaan kawat duri Ø 2 mm galvanized", "m", "FE", "pengadaan kawat duri", kw="Pengadaan Kawat Duri"),
    _i("II.10", "Pengadaan tiang kawat duri silet", "Unit", "FE", "pengadaan tiang silet", kw="Pengadaan Tiang Silet"),
    _i("II.11", "Pengadaan kawat duri silet CBT 65", "m", "FE", "pengadaan kawat silet", kw="Pengadaan Kawat Silet"),
    _i("III.1", "Pemasangan tiang panel beton uk. 230x18x17,5 cm, mutu K-225 (termasuk pondasi)", "Unit", "FE", "pasang tiang panel 230", kw="Pasang Tiang 230"),
    _i("III.2", "Pemasangan tiang panel beton uk. 300x18x17,5 cm, mutu K-225 (termasuk pondasi)", "Unit", "FE", "pasang tiang panel 300", kw="Pasang Tiang 300"),
    _i("III.3", "Pemasangan tiang panel beton uk. 380x18x17,5 cm, mutu K-225 (termasuk pondasi)", "Unit", "FE", "pasang tiang panel 380", kw="Pasang Tiang 380"),
    _i("III.4", "Pemasangan tiang panel beton uk. 350x26x26 cm, mutu K-225 (termasuk pondasi)", "Unit", "FE", "pasang tiang panel 350", kw="Pasang Tiang 350"),
    _i("III.5", "Pemasangan panel beton profil 240x40x5 cm, mutu K-225", "Unit", "FE", "pasang panel profil", kw="Pasang Panel Profil"),
    _i("III.6", "Pemasangan panel beton uk. 240x40x5 cm, mutu K-225", "Unit", "FE", "pasang panel 5cm", "pasang panel beton", kw="Pasang Panel 5cm"),
    _i("III.7", "Pemasangan panel beton uk. 240x40x10 cm, mutu K-225", "Unit", "FE", "pasang panel 10cm", kw="Pasang Panel 10cm"),
    _i("III.8", "Pemasangan tiang kawat uk. 210x12x12 cm, mutu K-225 (termasuk pondasi)", "Unit", "FE", "pasang tiang kawat", kw="Pasang Tiang Kawat"),
    _i("III.9", "Pemasangan kawat duri Ø 2 mm galvanized", "m", "FE", "pasang kawat duri", kw="Pasang Kawat Duri"),
    _i("III.10", "Pemasangan tiang kawat duri silet", "Unit", "FE", "pasang tiang silet", kw="Pasang Tiang Silet"),
    _i("III.11", "Pemasangan kawat duri silet CBT 65", "m", "FE", "pasang kawat silet", kw="Pasang Kawat Silet"),
    _i("III.12", "Pengadaan dan pemasangan tiang BRC uk. 225 cm Ø 2 inch (termasuk pondasi)", "Unit", "FE", kw="Tiang BRC 225"),
    _i("III.13", "Pengadaan dan pemasangan tiang BRC uk. 240 cm Ø 2 inch (termasuk pondasi)", "Unit", "FE", kw="Tiang BRC 240"),
    _i("III.14", "Pengadaan dan pemasangan tiang BRC uk. 300 cm Ø 2 inch (termasuk pondasi)", "Unit", "FE", kw="Tiang BRC 300"),
    _i("III.15", "Pengadaan dan pemasangan panel BRC uk. 175 x 240 cm, hot dip galvanized", "Unit", "FE", "panel brc 175", kw="Panel BRC 175"),
    _i("III.16", "Pengadaan dan pemasangan panel BRC uk. 190 x 240 cm, hot dip galvanized", "Unit", "FE", "panel brc 190", kw="Panel BRC 190"),
    _i("III.17", "Pengadaan dan pemasangan panel BRC uk. 240 x 240 cm, hot dip galvanized", "Unit", "FE", "panel brc 240", kw="Panel BRC 240"),
    _i("III.18", "Pengadaan dan pemasangan skur besi siku uk. 50x50x5 mm (termasuk pondasi)", "Unit", "FE", kw="Skur BRC"),
    _i("III.19", "Pengadaan dan pemasangan tiang besi siku uk.60x60x6 mm (termasuk pondasi)", "Unit", "FE", kw="Tiang Besi Siku"),
    _i("III.20", "Pengadaan dan pemasangan panel wire mesh M8 uk. 210 x 270 cm, hot dip galvanized", "Unit", "FE", "wire mesh pagar", kw="Panel Wire Mesh"),
    _i("III.21", "Pembersihan pohon rambat di pagar", "m'", "FE", "pohon rambat", "tanaman rambat", kw="Pohon Rambat"),
    _i("III.22", "Pengadaan dan pemasangan baut BRC, hot dip galvanized", "Bh", "FE", "baut brc", kw="Baut BRC"),
    _i("III.23", "Pembongkaran Pagar Panel", "m2", "FE", "bongkar pagar", kw="Bongkar Pagar"),
    _i("III.24", "Pembongkaran pondasi batu kali", "m3", "FE", "bongkar pondasi", kw="Bongkar Pondasi"),
    _i("III.25", "Pemasangan pondasi batu kali baru", "m3", "FE", "pondasi batu kali baru", kw="Pondasi Batu Baru"),
    _i("III.26", "Pemasangan pondasi batu kali menggunakan material eksisting", "m3", "FE", "pondasi batu kali eksisting", kw="Pondasi Batu Eksisting"),
    _i("III.27", "Pemasangan pondasi beton K-225 untuk pagar panel uk. 240x40x10 cm", "m3", "FE", kw="Pondasi Beton"),
    _i("III.28", "Pengelasan", "Titik", "FE", "pengelasan pagar", kw="Pengelasan"),
    _i("III.29", "Pembersihan FCB (Jet Pressure)", "m2", "FE", "jet pressure", "pembersihan fcb", kw="Jet Pressure"),
    _i("III.30", "Safety Line (500 m)", "roll", "FE", "safety line", kw="Safety Line"),
)

GROUP_TO_ITEMS: Dict[str, Tuple[BOQItem, ...]] = {
    "PV": PV_ITEMS,
    "SG": SG_ITEMS,
    "GR_WR": GR_WR_ITEMS,
    "RM_LC": RM_LC_ITEMS,
    "TRC": TRC_ITEMS,
    "DR": DR_ITEMS,
    "FE": FE_ITEMS,
}

_LOC_KEY_CODE_MAP: Dict[str, str] = {
    "Bitung": "BITUNG",
    "Cikupa": "CIKUPA",
    "Balaraja Timur": "BALTIM",
    "Balaraja Barat": "BALBAR",
    "Cikande": "CIKANDE",
    "Ciujung": "CIUJUNG",
    "Serang Timur": "SERTIM",
    "Serang Barat": "SERBAR",
    "Cilegon Timur": "CILTIM",
    "Cilegon Barat": "CILBAR",
    "Merak": "MERAK",
    "Petak Papat": "PETAKPAPAT",
}


def resolve_rumput_segment(
    wilayah: str,
    lokasi: str,
    item_hint: str = "",
) -> Tuple[Optional[BOQItem], str]:
    """
    Resolve a `RM` line (Rumput, Ketrik, Striping) against lokasi + optional hint.
    Returns (BOQItem | None, error_or_reason).
    """
    hint_l = (item_hint or "").lower()
    loc_l = (lokasi or "").lower()

    # Check IC/Akses location first
    ic_canon_pairs = sorted(
        [(k, cn) for k, cn in BOUNDARY_IC_AKSES.items()]
        + [(k, cn) for k, (cn, _) in IC_AKSES_WILAYAH.items()],
        key=lambda kv: len(kv[0]),
        reverse=True,
    )
    matched_loc_code: Optional[str] = None
    for _, canon_name in ic_canon_pairs:
        if canon_name.lower() in loc_l or canon_name.lower() in hint_l:
            matched_loc_code = _LOC_KEY_CODE_MAP.get(canon_name)
            if matched_loc_code:
                break
    if not matched_loc_code:
        for k, canon_name in ic_canon_pairs:
            if re.search(rf"(?<![0-9A-Z]){re.escape(k)}(?![0-9A-Z])", lokasi.upper()):
                matched_loc_code = _LOC_KEY_CODE_MAP.get(canon_name)
                if matched_loc_code:
                    break

    catalog = {it.item_key: it for it in RM_LC_ITEMS}

    # Striping
    if "striping" in hint_l or "ii.3" in hint_l or "ii.4" in hint_l:
        if "akses" in hint_l or "ic" in hint_l or "interchange" in hint_l or matched_loc_code:
            if matched_loc_code and f"II.4.{matched_loc_code}" in catalog:
                return catalog[f"II.4.{matched_loc_code}"], ""
            return None, "Striping IC/Akses wajib menyebut lokasi IC/Akses resmi (misal Bitung, Cikupa, Sertim, Merak)."
        return catalog["II.3"], ""

    # Ketrik
    if "ketrik" in hint_l or "ii.1" in hint_l or "ii.2" in hint_l:
        if "akses" in hint_l or "ic" in hint_l or "interchange" in hint_l or matched_loc_code:
            if matched_loc_code and f"II.2.{matched_loc_code}" in catalog:
                return catalog[f"II.2.{matched_loc_code}"], ""
            return None, "Ketrik IC/Akses wajib menyebut lokasi IC/Akses resmi."
        return catalog["II.1"], ""

    # Rumput Pemotongan
    if matched_loc_code:
        prefix = "RM.AK" if ("akses" in hint_l or "akses" in loc_l) else "RM.IC"
        candidate_key = f"{prefix}.{matched_loc_code}"
        if candidate_key in catalog:
            return catalog[candidate_key], ""
        # Petak Papat is Akses-only
        if f"RM.AK.{matched_loc_code}" in catalog:
            return catalog[f"RM.AK.{matched_loc_code}"], ""

    # Mainlane KM matching
    meters = parse_km_meters_list(lokasi)
    if not meters:
        return None, "Lokasi pemotongan rumput harus memuat KM/STA mainlane atau nama IC/Akses."

    target_m = sum(meters) // len(meters)
    pass_no = 2 if re.search(r"\b(?:ke-?\s*2|potong\s*2|p2|tahap\s*2)\b", hint_l) else 1

    # Prefer exact segment match for pass_no, fallback to pass 1 if pass 2 omits that range
    for p_try in (pass_no, 1):
        for seg in RUMPUT_MAINLANE_SEGMENTS:
            key, p, w, _, km_s, km_e, _ = seg
            if w == wilayah and p == p_try and km_s <= target_m <= km_e:
                return catalog[key], ""

    # Handle boundary < 26+400 (W1 starts at 26+400 in RUMPUT table)
    if wilayah == "W1" and 26035 <= target_m < 26400:
        key = "RM.P2.W1.26400" if pass_no == 2 else "RM.P1.W1.26400"
        return catalog[key], ""

    return None, f"Tidak ditemukan segmen rumput {wilayah} untuk KM tersebut."


def resolve_boq_item(
    aset: str,
    raw_item: str,
    lokasi: str = "",
    wilayah: str = "",
) -> Tuple[Optional[BOQItem], str]:
    """
    Resolve a user-supplied code or short item label into an exact canonical BOQItem.
    Returns (BOQItem | None, error_message).
    """
    _, _, group = ASSET_TO_TABLE[aset]
    items: Iterable[BOQItem] = GROUP_TO_ITEMS[group]
    token = (raw_item or "").strip()
    if not token:
        return None, "Nama atau kode item BOQ tidak boleh kosong."

    token_upper = re.sub(r"\s+", " ", token.upper()).strip()
    token_lower = token_upper.lower()
    token_norm = _norm_kw(token)

    # Special handling for RM routine items ("Rumput", "Ketrik", "Striping", or RM.* key)
    if aset == "RM" and (
        token_lower in {"rumput", "potong rumput", "ketrik", "striping"}
        or any(w in token_lower for w in ("rumput", "ketrik", "striping", "ii.1", "ii.2", "ii.3", "ii.4"))
        or token_upper.startswith("RM.")
    ):
        exact = next((it for it in items if it.item_key.upper() == token_upper), None)
        if exact:
            return exact, ""
        resolved_rm, err_rm = resolve_rumput_segment(wilayah, lokasi, token)
        if resolved_rm:
            return resolved_rm, ""
        return None, err_rm

    scoped = [it for it in items if it.group in (aset, group)]

    # 1. Exact keyword match FIRST (primary human-friendly site workflow)
    for it in scoped:
        if it.keyword.lower() == token_lower:
            return it, ""
    for it in scoped:
        if _norm_kw(it.keyword) == token_norm:
            return it, ""

    # 2. Exact item_key match (still supported for Excel / technical codes)
    for it in items:
        if it.item_key.upper() == token_upper:
            return it, ""

    # 2b. Combined Code + Keyword or Keyword (Code) mode:
    # e.g. "II.1 Permanen", "Permanen (II.1)", "I.15 Panel PVC", "II.8 Pasang Beam"
    m_code = re.search(r"\b([IVX]{1,3}\.\d+[A-Za-z]?(?:-[A-Za-z0-9]+)?)\b", token_upper)
    if m_code:
        extracted_code = m_code.group(1).upper()
        rem_text = re.sub(rf"\(?{re.escape(extracted_code)}\)?", "", token_upper).strip(" -–—:()/")
        for it in items:
            if it.item_key.upper() == extracted_code:
                return it, ""
        cand = [it for it in scoped if it.display_code.upper() == extracted_code]
        if len(cand) == 1:
            return cand[0], ""
        if len(cand) > 1 and rem_text:
            rem_norm = _norm_kw(rem_text)
            for it in cand:
                if _norm_kw(it.keyword) == rem_norm or rem_norm in _norm_kw(it.keyword) or rem_norm in _norm_kw(it.uraian):
                    return it, ""
            for it in cand:
                if any(rem_norm in _norm_kw(a) or _norm_kw(a) in rem_norm for a in it.aliases):
                    return it, ""

    # 3. Match by display_code when unambiguous
    code_matches = [it for it in scoped if it.display_code.upper() == token_upper]
    if len(code_matches) == 1:
        return code_matches[0], ""
    if len(code_matches) > 1:
        kw_str = " / ".join(it.keyword for it in code_matches)
        return (
            None,
            f"Kode {token_upper} punya lebih dari 1 item. Gunakan keyword: {kw_str}.",
        )

    # 4. Exact alias match, then longest-alias substring match
    for it in scoped:
        if token_lower in it.aliases or any(_norm_kw(a) == token_norm for a in it.aliases):
            return it, ""

    alias_hits = [
        it
        for it in scoped
        if any(a in token_lower or (_norm_kw(a) and _norm_kw(a) in token_norm) for a in it.aliases)
    ]
    if len(alias_hits) == 1:
        return alias_hits[0], ""
    if len(alias_hits) > 1:
        # Prefer the longest matched alias to break ties cleanly (e.g., "batu kali baru" vs "batu kali")
        scored = sorted(
            alias_hits,
            key=lambda it: max((len(a) for a in it.aliases if a in token_lower), default=0),
            reverse=True,
        )
        top_score = max((len(a) for a in scored[0].aliases if a in token_lower), default=0)
        second_score = max((len(a) for a in scored[1].aliases if a in token_lower), default=0)
        if top_score > second_score:
            return scored[0], ""

    desc_hits = [it for it in scoped if token_lower in it.uraian.lower()]
    if len(desc_hits) == 1:
        return desc_hits[0], ""

    return None, f"Item '{raw_item}' tidak cocok dengan daftar keyword BOQ {aset}. Cek sheet DAFTAR_BOQ di template standar."


def get_boq_menu_for_asset(aset: str) -> List[BOQItem]:
    canon = normalize_asset_code(aset) or "PV"
    _, _, group = ASSET_TO_TABLE[canon]
    if canon == "GR":
        items = [it for it in GR_WR_ITEMS if it.group in ("GR", "GR_WR")]
    elif canon == "WR":
        items = [it for it in GR_WR_ITEMS if it.group in ("WR", "GR_WR")]
    elif canon == "RM":
        items = [
            it
            for it in RM_LC_ITEMS
            if it.item_key.startswith(("II.", "RM.IC.", "RM.AK.")) or it.group == "RM_LC"
        ]
    elif canon == "LC":
        items = [it for it in RM_LC_ITEMS if it.group in ("LC", "RM_LC")]
    else:
        items = list(GROUP_TO_ITEMS[group])

    # Put core field execution items before prep / task-force mobilization rows
    def _sort_key(it: BOQItem) -> tuple[int, str]:
        k = it.item_key
        if canon == "DR" and k in ("I.12", "I.13"):
            return (0, k)
        if canon == "PV" and k.startswith(("II.", "III.", "IV.")):
            return (0, k)
        if canon in ("GR", "WR", "SG", "LC", "FE") and not k.startswith("I."):
            if k.startswith(("II.", "III.")):
                return (0, k)
        if canon in ("GR", "WR", "SG") and k.startswith("I.") and k not in {"I.1", "I.2", "I.3", "I.4", "I.5"}:
            return (0, k)
        if canon == "CA" and k.startswith("II."):
            return (0, k)
        if k.startswith(("I.", "V.", "VI.")):
            return (2, k)
        return (1, k)

    return sorted(items, key=_sort_key)


def format_boq_cheat_sheet(aset: str, max_items: int = 24) -> str:
    items = get_boq_menu_for_asset(aset)
    lines = []
    for it in items[:max_items]:
        lines.append(f"- `{it.keyword}` ({it.item_key}) : {it.uraian} ({it.satuan})")
    if len(items) > max_items:
        lines.append(f"... ({len(items) - max_items} item lainnya lihat form standar / Excel)")
    return "\n".join(lines)
