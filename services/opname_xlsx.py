from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import io
import re
from typing import Any, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.filters import AutoFilter
from openpyxl.worksheet.table import Table, TableColumn, TableFormula, TableStyleInfo

from services.message_utils import parse_opname_date_str, resolve_billing_cycle
from services.opname_catalog import (
    ALLOWED_VENDORS_BY_ASSET,
    ASSET_TITLES,
    ASSET_TO_TABLE,
    BOQItem,
    DR_ITEMS,
    FE_ITEMS,
    GR_WR_ITEMS,
    LC_ITEMS,
    PV_ITEMS,
    RM_LC_ITEMS,
    SG_ITEMS,
    TRC_ITEMS,
    check_roster_pairing,
    normalize_asset_code,
    normalize_vendor,
    resolve_boq_item,
    resolve_wilayah,
)
from services.opname_roster import get_allowed_vendors_for_asset

MONTH_ABBRS = ("JAN", "FEB", "MAR", "APR", "MEI", "JUN", "JUL", "AGT", "SEP", "OKT", "NOV", "DES")
MONTH_INDEX_TO_ABBR = {idx: abbr for idx, abbr in enumerate(MONTH_ABBRS, start=1)}
MONTH_FULL_ID = {
    "JAN": "JANUARI",
    "FEB": "FEBRUARI",
    "MAR": "MARET",
    "APR": "APRIL",
    "MEI": "MEI",
    "JUN": "JUNI",
    "JUL": "JULI",
    "AGT": "AGUSTUS",
    "SEP": "SEPTEMBER",
    "OKT": "OKTOBER",
    "NOV": "NOVEMBER",
    "DES": "DESEMBER",
}

SKIP_SHEETS = {"DAFTAR_BOQ", "REKAP_TAHUNAN", "REKAP_TAGIHAN", "PETUNJUK_WA"}


@dataclass
class XlsxSlotBatch:
    slot_id: str
    cycle_key: str
    cycle_month: int
    cycle_year: int
    aset: str
    wilayah: str
    vendor: str
    minggu: str
    table_name: str
    entries: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class XlsxParseResult:
    is_standard_form: bool
    aset: Optional[str] = None
    slots: list[XlsxSlotBatch] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    roster_warnings: list[str] = field(default_factory=list)


def _norm_hdr(val: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(val or "").lower()).strip()


def to_float_num(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        s = val.strip()
        if not s or s == "-" or s.startswith("="):
            return None
        s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _normalize_minggu(raw: Any, sheet_name: str = "") -> str:
    s = str(raw or "").strip().upper()
    if s:
        m = re.search(r"(?:M|MINGGU|W)[\s\-_]*([1-5])\b", s)
        if m:
            return f"M{m.group(1)}"
        if re.fullmatch(r"[1-5]", s):
            return f"M{s}"
    m_sh = re.search(r"MINGGU[\s\-_]*([1-5])\b", sheet_name.upper())
    if m_sh:
        return f"M{m_sh.group(1)}"
    return "FULL"


def _parse_excel_date(val: Any) -> Optional[date]:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s or s.startswith("="):
            return None
        iso = parse_opname_date_str(s)
        if iso:
            return datetime.strptime(iso, "%Y-%m-%d").date()
        # Handle Indonesian textual month dates such as "18 Nov 2026"
        month_map = {
            "jan": 1, "januari": 1, "feb": 2, "februari": 2, "mar": 3, "maret": 3,
            "apr": 4, "april": 4, "mei": 5, "may": 5, "jun": 6, "juni": 6,
            "jul": 7, "juli": 7, "agu": 8, "agst": 8, "agt": 8, "agustus": 8, "aug": 8,
            "sep": 9, "september": 9, "okt": 10, "oktober": 10, "oct": 10,
            "nov": 11, "november": 11, "des": 12, "desember": 12, "dec": 12,
        }
        m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$", s)
        if m and m.group(2).lower() in month_map:
            try:
                return date(int(m.group(3)), month_map[m.group(2).lower()], int(m.group(1)))
            except ValueError:
                return None
    return None


def _detect_asset_and_presets(wb_val: openpyxl.Workbook, filename: str, caption: str) -> tuple[bool, Optional[str], str, str]:
    preset_wil = ""
    preset_vend = ""
    detected_aset: Optional[str] = None
    is_std = False

    if "DAFTAR_BOQ" in wb_val.sheetnames:
        is_std = True
        boq_ws = wb_val["DAFTAR_BOQ"]
        g1 = str(boq_ws.cell(1, 7).value or "").strip().upper()
        g2 = str(boq_ws.cell(2, 7).value or "").strip().upper()
        g3 = str(boq_ws.cell(3, 7).value or "").strip().upper()
        detected_aset = normalize_asset_code(g1)
        if g2 in ("W1", "W2"):
            preset_wil = g2
        if g3:
            preset_vend = g3

    sheet_map = {
        "OPNAME_PAVEMENT": "PV",
        "OPNAME_GR": "GR",
        "OPNAME_RB": "SG",
        "OPNAME_WR": "WR",
        "OPNAME_RUMPUT": "RM",
        "OPNAME_LANDSCAPE": "LC",
        "OPNAME_TRC": "CA",
        "OPNAME_DR": "DR",
        "OPNAME_FE": "FE",
    }
    for sname in wb_val.sheetnames:
        if sname.upper() in sheet_map:
            is_std = True
            if not detected_aset:
                detected_aset = sheet_map[sname.upper()]
        elif sname.upper() in MONTH_ABBRS:
            is_std = True

    if not detected_aset:
        # Check filename tokens (e.g. PV_W1_MIJ_2026.xlsx or 02_STD_Opname_Guardrail.xlsx)
        fn_up = (filename or "").upper()
        for tok, aset_code in (
            ("PAVEMENT", "PV"), ("GUARDRAIL", "GR"), ("RAMBU", "SG"), ("WIREROPE", "WR"),
            ("RUMPUT", "RM"), ("LANDSCAPE", "LC"), ("TRC", "CA"), ("DRAINASE", "DR"), ("PAGAR", "FE"),
        ):
            if tok in fn_up:
                detected_aset = aset_code
                break
        if not detected_aset:
            m_fn = re.match(r"^(PV|GR|SG|WR|RM|LC|CA|DR|FE)[_\-\s]", fn_up)
            if m_fn:
                detected_aset = m_fn.group(1)

    if not detected_aset and caption:
        m_cap = re.search(r"\b(PV|GR|SG|WR|RM|LC|CA|DR|FE|TRC|RAMBU|PAVEMENT|GUARDRAIL|WIREROPE|RUMPUT|LANDSCAPE|DRAINASE|PAGAR)\b", caption, re.IGNORECASE)
        if m_cap:
            detected_aset = normalize_asset_code(m_cap.group(1))

    if not is_std and caption and "opname" in caption.lower():
        is_std = True

    return is_std, detected_aset, preset_wil, preset_vend


def _find_header_and_map(ws) -> tuple[Optional[int], dict[str, int]]:
    for r in range(1, min(ws.max_row, 18) + 1):
        row_norm = {_norm_hdr(ws.cell(r, c).value): c for c in range(1, min(ws.max_column, 35) + 1) if ws.cell(r, c).value}
        if ("item keyword rab" in row_norm or "uraian keyword item" in row_norm) and any(
            k in row_norm for k in ("tanggal", "tanggal pekerjaan", "vol vendor", "vol opname", "wilayah", "vendor")
        ):
            return r, row_norm
    return None, {}


def _extract_sheet_header_meta(ws, hdr_row: int) -> tuple[str, str]:
    """Read optional sheet-level Wilayah (W1/W2) and Vendor from header box rows above hdr_row."""
    sheet_wil = ""
    sheet_vend = ""
    for r in range(1, hdr_row):
        for c in range(1, min(ws.max_column, 12) + 1):
            raw = str(ws.cell(r, c).value or "").strip().lower()
            if not raw:
                continue
            if raw.startswith("wilayah"):
                for nc in range(c + 1, min(c + 4, ws.max_column + 1)):
                    v = str(ws.cell(r, nc).value or "").strip().upper()
                    if v in ("W1", "W2"):
                        sheet_wil = v
                        break
            elif raw.startswith(("vendor", "pelaksana")):
                for nc in range(c + 1, min(c + 4, ws.max_column + 1)):
                    v = str(ws.cell(r, nc).value or "").strip()
                    if v:
                        sheet_vend = v
                        break
    return sheet_wil, sheet_vend


def _col_by_aliases(hmap: dict[str, int], *aliases: str) -> Optional[int]:
    for a in aliases:
        na = _norm_hdr(a)
        if na in hmap:
            return hmap[na]
    return None


def compute_geom_volume(satuan: str, p: float | None, l: float | None, t: float | None, jml: float | None) -> float | None:
    mul = jml if (jml is not None and jml > 0) else 1.0
    sat_l = (satuan or "").lower().strip()
    if p is not None and sat_l in ("m", "m'"):
        return round(p * mul, 3)
    if p is not None and l is not None and sat_l == "m2":
        return round(p * l * mul, 3)
    if p is not None and l is not None and t is not None and sat_l == "m3":
        return round(p * l * t * mul, 3)
    if jml is not None:
        return round(jml, 3)
    if p is not None:
        return round(p, 3)
    return None


def compute_strict_dim_volume(
    satuan: str,
    p: float | None,
    l: float | None,
    t: float | None,
    jml: float | None,
    allow_countable_jml: bool = False,
) -> float | None:
    """Compute volume strictly when all required dimensions for the unit are present."""
    mul = jml if (jml is not None and jml > 0) else 1.0
    sat_l = (satuan or "").lower().strip()
    if sat_l in ("m", "m'"):
        return round(p * mul, 3) if p is not None else None
    if sat_l == "m2":
        return round(p * l * mul, 3) if (p is not None and l is not None) else None
    if sat_l == "m3":
        return round(p * l * t * mul, 3) if (p is not None and l is not None and t is not None) else None
    if (
        allow_countable_jml
        and jml is not None
        and p is None
        and l is None
        and t is None
        and sat_l not in ("ton", "kg", "liter", "ltr", "ls")
    ):
        return round(jml, 3)
    return None


def _format_lokasi(sta_km: Any, sta_awal: Any, sta_akhir: Any) -> str:
    def _fmt_sta(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            n = int(round(v))
            return f"KM {n // 1000}+{n % 1000:03d}"
        s = str(v).strip()
        return s if not s.isdigit() else f"KM {int(s) // 1000}+{int(s) % 1000:03d}"

    single = _fmt_sta(sta_km)
    if single:
        return single
    s1 = _fmt_sta(sta_awal)
    s2 = _fmt_sta(sta_akhir)
    if s1 and s2:
        return f"{s1} s/d {s2}"
    return s1 or s2


def parse_standard_opname_xlsx(
    file_bytes: bytes,
    filename: str = "",
    caption: str = "",
) -> XlsxParseResult:
    try:
        wb_val = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        wb_fml = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
    except Exception as exc:
        return XlsxParseResult(is_standard_form=False, errors=[f"File Excel tidak dapat dibaca: {exc}"])

    is_std, aset, preset_wil, preset_vend = _detect_asset_and_presets(wb_val, filename, caption)
    if not is_std:
        return XlsxParseResult(is_standard_form=False)
    if not aset:
        return XlsxParseResult(
            is_standard_form=True,
            errors=["Tidak dapat mengenali jenis pekerjaan (PV/GR/SG/WR/RM/LC/CA/DR/FE) dari file Excel ini."],
        )

    errors: list[str] = []
    warnings_seen: set[str] = set()
    roster_warnings: list[str] = []
    slots_by_id: dict[str, XlsxSlotBatch] = {}
    _, table_name, _ = ASSET_TO_TABLE[aset]

    for sname in wb_val.sheetnames:
        if sname.upper() in SKIP_SHEETS or sname.upper().startswith("REKAP"):
            continue
        ws_v = wb_val[sname]
        ws_f = wb_fml[sname]
        hdr_row, hmap = _find_header_and_map(ws_f)
        if hdr_row is None:
            continue

        c_tgl = _col_by_aliases(hmap, "Tanggal", "Tanggal Pekerjaan")
        c_minggu = _col_by_aliases(hmap, "Minggu")
        c_kode_tem = _col_by_aliases(hmap, "Kode Temuan")
        c_wil = _col_by_aliases(hmap, "Wilayah")
        c_vend = _col_by_aliases(hmap, "Vendor")
        c_sta = _col_by_aliases(hmap, "STA / KM", "Lokasi")
        c_sta1 = _col_by_aliases(hmap, "STA Awal")
        c_sta2 = _col_by_aliases(hmap, "STA Akhir")
        c_jal = _col_by_aliases(hmap, "Jalur")
        c_laj1 = _col_by_aliases(hmap, "Lajur", "Lajur 1")
        c_laj2 = _col_by_aliases(hmap, "Lajur 2")
        c_kode = _col_by_aliases(hmap, "KODE")
        c_kw = _col_by_aliases(hmap, "Item / Keyword RAB", "Uraian / Keyword Item")
        c_p = _col_by_aliases(hmap, "P", "P (m)")
        c_l = _col_by_aliases(hmap, "L", "L (m)")
        c_t = _col_by_aliases(hmap, "T", "T (m)")
        c_jml = _col_by_aliases(hmap, "Jml", "Jumlah")
        c_vv = _col_by_aliases(hmap, "Vol. Vendor", "Volume Pekerjaan")
        c_ov = _col_by_aliases(hmap, "Vol. Opname", "Volume Opname")
        c_stat = _col_by_aliases(hmap, "Status Material")
        c_ket = _col_by_aliases(hmap, "Keterangan")
        sheet_wil, sheet_vend = _extract_sheet_header_meta(ws_v, hdr_row)

        last_row_date: Optional[date] = None
        last_row_minggu: str = ""
        last_row_lokasi: str = ""
        last_row_jalur_lajur: str = ""
        last_row_kode_tem: str = ""

        for r in range(hdr_row + 1, ws_v.max_row + 1):
            lead_txt = " ".join(str(ws_v.cell(r, c).value or "") for c in range(1, 6)).upper()
            if any(stop in lead_txt for stop in ("TOTAL PEMERIKSAAN", "REKAP VOLUME PER ITEM", "REALISASI", "DIBUAT OLEH")):
                break

            raw_kw = ws_v.cell(r, c_kw).value if c_kw else None
            raw_kode = ws_v.cell(r, c_kode).value if c_kode else None
            raw_item = str(raw_kw or raw_kode or "").strip()

            p_val = to_float_num(ws_v.cell(r, c_p).value) if c_p else None
            l_val = to_float_num(ws_v.cell(r, c_l).value) if c_l else None
            t_val = to_float_num(ws_v.cell(r, c_t).value) if c_t else None
            j_val = to_float_num(ws_v.cell(r, c_jml).value) if c_jml else None
            ov_val = to_float_num(ws_v.cell(r, c_ov).value) if c_ov else None
            vv_val = to_float_num(ws_v.cell(r, c_vv).value) if c_vv else None

            # Also check uncached raw numeric values when file was saved by script/tool without Excel cache
            if ov_val is None and c_ov:
                ov_val = to_float_num(ws_f.cell(r, c_ov).value)
            if vv_val is None and c_vv:
                vv_val = to_float_num(ws_f.cell(r, c_vv).value)

            # Skip blank starter/trailing rows
            if not raw_item and p_val is None and j_val is None and ov_val is None and vv_val is None:
                continue

            # Determine sheet-specific asset if combined workbook had OPNAME_GR + OPNAME_RB
            row_aset = aset
            if sname.upper() == "OPNAME_RB":
                row_aset = "SG"
            elif sname.upper() == "OPNAME_GR":
                row_aset = "GR"
            elif sname.upper() == "OPNAME_LANDSCAPE":
                row_aset = "LC"
            elif sname.upper() == "OPNAME_RUMPUT":
                row_aset = "RM"

            row_dt = _parse_excel_date(ws_v.cell(r, c_tgl).value) if c_tgl else None
            if row_dt is not None:
                last_row_date = row_dt
            elif last_row_date is not None:
                row_dt = last_row_date
            else:
                errors.append(f"[{sname} Baris {r}] Tanggal wajib diisi.")
                continue

            raw_lokasi = _format_lokasi(
                ws_v.cell(r, c_sta).value if c_sta else None,
                ws_v.cell(r, c_sta1).value if c_sta1 else None,
                ws_v.cell(r, c_sta2).value if c_sta2 else None,
            )
            raw_jalur_parts = [
                str(ws_v.cell(r, col).value or "").strip()
                for col in (c_jal, c_laj1, c_laj2)
                if col
            ]
            raw_jalur = " ".join(p for p in raw_jalur_parts if p)
            raw_kode_tem = str(ws_v.cell(r, c_kode_tem).value or "").strip() if c_kode_tem else ""

            if raw_lokasi:
                lokasi = raw_lokasi
                last_row_lokasi = lokasi
                jalur_lajur = raw_jalur or "-"
                last_row_jalur_lajur = jalur_lajur
                kode_temuan = raw_kode_tem or "-"
                last_row_kode_tem = kode_temuan
            else:
                # Ditto continuation row for multiple RAB items at the same location
                lokasi = last_row_lokasi
                jalur_lajur = raw_jalur or last_row_jalur_lajur or "-"
                kode_temuan = raw_kode_tem or last_row_kode_tem or "-"

            raw_wil = str((ws_v.cell(r, c_wil).value if c_wil else "") or sheet_wil or preset_wil or "").strip().upper()
            wilayah = raw_wil if raw_wil in ("W1", "W2") else ""
            if lokasi:
                loc_hint = f"{lokasi} {wilayah}".strip() if wilayah else lokasi
                w_ok, loc_wil, _, w_err = resolve_wilayah(loc_hint)
                if not w_ok or not loc_wil:
                    errors.append(f"[{sname} Baris {r}] {w_err}")
                    continue
                wilayah = loc_wil
            elif not wilayah:
                errors.append(f"[{sname} Baris {r}] Lokasi STA/KM atau Wilayah wajib diisi.")
                continue

            raw_vend = str((ws_v.cell(r, c_vend).value if c_vend else "") or sheet_vend or preset_vend or "").strip()
            v_ok, canon_vend, v_err = normalize_vendor(raw_vend, row_aset)
            if not v_ok or not canon_vend:
                errors.append(f"[{sname} Baris {r}] {v_err}")
                continue

            boq_item, b_err = resolve_boq_item(row_aset, raw_item, lokasi=lokasi, wilayah=wilayah)
            if not boq_item:
                errors.append(f"[{sname} Baris {r}] {b_err}")
                continue

            # Explicit 0 in Vol. Opname is respected (only fall back when None)
            if ov_val is not None:
                vol = ov_val
            elif vv_val is not None:
                vol = vv_val
            else:
                vol = compute_geom_volume(boq_item.satuan, p_val, l_val, t_val, j_val)

            if vol is None or vol <= 0:
                errors.append(f"[{sname} Baris {r}] Volume untuk '{boq_item.keyword}' kosong atau <= 0.")
                continue

            r_ok, r_warn = check_roster_pairing(row_aset, canon_vend, wilayah)
            if not r_ok and r_warn not in warnings_seen:
                warnings_seen.add(r_warn)
                roster_warnings.append(r_warn)

            raw_minggu_val = ws_v.cell(r, c_minggu).value if c_minggu else None
            if raw_minggu_val is not None and str(raw_minggu_val).strip():
                minggu = _normalize_minggu(raw_minggu_val, sname)
                last_row_minggu = minggu
            elif last_row_minggu:
                minggu = last_row_minggu
            else:
                minggu = _normalize_minggu("", sname)
            cycle_m, cycle_y = resolve_billing_cycle(row_dt)
            cycle_key = f"{cycle_y:04d}-{cycle_m:02d}"
            _, slot_table, _ = ASSET_TO_TABLE[row_aset]
            slot_id = f"XLS-{cycle_y % 100:02d}{cycle_m:02d}-{row_aset}-{wilayah}-{canon_vend}-{minggu}"

            if slot_id not in slots_by_id:
                slots_by_id[slot_id] = XlsxSlotBatch(
                    slot_id=slot_id,
                    cycle_key=cycle_key,
                    cycle_month=cycle_m,
                    cycle_year=cycle_y,
                    aset=row_aset,
                    wilayah=wilayah,
                    vendor=canon_vend,
                    minggu=minggu,
                    table_name=slot_table,
                )

            mat_status = str(ws_v.cell(r, c_stat).value or "").strip() if c_stat else ""
            ket = str(ws_v.cell(r, c_ket).value or "").strip() if c_ket else ""

            slots_by_id[slot_id].entries.append(
                {
                    "tanggal": row_dt.strftime("%Y-%m-%d"),
                    "minggu": minggu,
                    "kode_temuan": kode_temuan or "-",
                    "wilayah": wilayah,
                    "vendor": canon_vend,
                    "lokasi": lokasi or "-",
                    "jalur_lajur": jalur_lajur,
                    "item": boq_item,
                    "item_key": boq_item.item_key,
                    "keyword": boq_item.keyword,
                    "uraian": boq_item.uraian,
                    "satuan": boq_item.satuan,
                    "p": p_val,
                    "l": l_val,
                    "t": t_val,
                    "jml": j_val,
                    "volume": float(round(vol, 4)),
                    "material_status": mat_status,
                    "keterangan": ket,
                }
            )

    if not errors and not slots_by_id:
        errors.append(f"Belum ada baris opname yang terisi pada file {filename or aset}.")

    return XlsxParseResult(
        is_standard_form=True,
        aset=aset,
        slots=list(slots_by_id.values()),
        errors=errors,
        roster_warnings=roster_warnings,
    )


def _items_for_asset_boq(aset: str) -> list[BOQItem]:
    if aset == "PV":
        return list(PV_ITEMS)
    if aset == "GR":
        return [it for it in GR_WR_ITEMS if it.group in ("GR", "GR_WR")]
    if aset == "WR":
        return [it for it in GR_WR_ITEMS if it.group in ("WR", "GR_WR")]
    if aset == "SG":
        return list(SG_ITEMS)
    if aset == "LC":
        return list(LC_ITEMS)
    if aset == "RM":
        return [
            BOQItem("RM.MAIN", "I.1", "Rumput", "Pemotongan Rumput Mainlane/IC/Akses", "m2", "RM"),
            BOQItem("RM.KETRIK", "II.1", "Ketrik", "Ketrik Bahu Jalan Mainlane/IC/Akses", "m'", "RM"),
            BOQItem("RM.STRIP", "II.3", "Striping", "Striping Bahu Jalan Mainlane/IC/Akses", "m'", "RM"),
        ] + [it for it in RM_LC_ITEMS if it not in LC_ITEMS]
    if aset == "CA":
        return list(TRC_ITEMS)
    if aset == "DR":
        return list(DR_ITEMS)
    if aset == "FE":
        return list(FE_ITEMS)
    return list(PV_ITEMS)


def build_prefilled_standard_xlsx(
    aset: str,
    cycle_month: int,
    cycle_year: int,
    entries: list[dict[str, Any]],
) -> bytes:
    """
    Build a ready-to-edit Option A single-month standard .xlsx workbook pre-populated from OCR rows
    so PICs can either confirm directly via /simpan or adjust 1 cell and drop back to WhatsApp.
    """
    canon_aset = normalize_asset_code(aset) or "PV"
    mon_abbr = MONTH_INDEX_TO_ABBR.get(cycle_month, "NOV")
    mon_full = MONTH_FULL_ID.get(mon_abbr, mon_abbr)
    boq_items = _items_for_asset_boq(canon_aset)
    vendors = get_allowed_vendors_for_asset(canon_aset) or list(ALLOWED_VENDORS_BY_ASSET.get(canon_aset, ("MMS",)))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = mon_abbr

    thin = Side(style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill("solid", fgColor="D9D9D9")
    sub_fill = PatternFill("solid", fgColor="5B9BD5")

    cols = [
        ("No.", 4.2), ("Tanggal", 11.2), ("Minggu", 7.2), ("Kode Temuan", 13.5),
        ("STA / KM", 12.0), ("Jalur", 5.5), ("Lajur", 5.5), ("KODE", 8.5),
        ("Item / Keyword RAB", 22.5), ("P", 7.5), ("L", 7.5), ("T", 7.5),
        ("Jml", 7.5), ("Vol. Vendor", 11.5), ("Vol. Opname", 12.5), ("Satuan", 13.5),
        ("Baik", 5.5), ("Tdk Baik", 6.8), ("Keterangan", 19.0),
    ]
    last_col_idx = 1 + len(cols)
    last_col_l = get_column_letter(last_col_idx)

    first_ent = entries[0] if entries else {}
    hdr_wil = str(first_ent.get("wilayah") or "").strip().upper()
    hdr_vend = str(first_ent.get("vendor") or "").strip()

    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=last_col_idx)
    ws.merge_cells(start_row=2, start_column=2, end_row=2, end_column=last_col_idx)
    ws.merge_cells(start_row=3, start_column=2, end_row=3, end_column=last_col_idx)
    mon_idx = MONTH_ABBRS.index(mon_abbr) if mon_abbr in MONTH_ABBRS else 0
    prev_full = MONTH_FULL_ID[MONTH_ABBRS[(mon_idx - 1) % 12]]
    period_str = (
        f"PERIODE: {mon_full} {cycle_year} (26 {prev_full} {cycle_year - 1} - 25 {mon_full} {cycle_year})"
        if mon_idx == 0
        else f"PERIODE: {mon_full} {cycle_year} (26 {prev_full} - 25 {mon_full} {cycle_year})"
    )
    ws.cell(1, 2, "LAPORAN OPNAME DAN BACKUP QUANTITY (HASIL SCAN OCR)").font = Font(name="Calibri", size=11, bold=True)
    ws.cell(2, 2, f"PEKERJAAN {ASSET_TITLES.get(canon_aset, canon_aset).upper()}").font = Font(name="Calibri", size=11, bold=True)
    ws.cell(3, 2, period_str).font = Font(name="Calibri", size=10, bold=True)
    for r_k in (1, 2, 3):
        ws.cell(r_k, 2).alignment = Alignment(horizontal="center", vertical="center")

    ws.cell(7, 2, "Wilayah:").font = Font(name="Calibri", size=9.5, bold=True)
    ws.cell(7, 4, hdr_wil).font = Font(name="Calibri", size=9.5, bold=True)
    ws.cell(7, 5, "Vendor:").font = Font(name="Calibri", size=9.5, bold=True)
    ws.cell(7, 6, hdr_vend).font = Font(name="Calibri", size=9.5, bold=True)

    for i, (lbl, width) in enumerate(cols):
        col_i = 2 + i
        ws.column_dimensions[get_column_letter(col_i)].width = width
        c = ws.cell(10, col_i, lbl)
        c.fill = hdr_fill
        c.font = Font(name="Calibri", size=9.5, bold=True)
        c.border = border
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    row_count = max(5, len(entries))
    end_row = 10 + row_count
    for r in range(11, end_row + 1):
        ws.row_dimensions[r].height = 25.0
        for c in range(2, last_col_idx + 1):
            cell = ws.cell(r, c)
            cell.border = border
            cell.font = Font(name="Tahoma", size=9)
        ws.cell(r, 2, "=ROW()-10")
        ws.cell(r, 9, f'=IF(J{r}="","",IFERROR(INDEX(DAFTAR_BOQ!$B:$B,MATCH(J{r},DAFTAR_BOQ!$A:$A,0)),""))')
        ws.cell(r, 17, f'=IF(J{r}="","",IFERROR(INDEX(DAFTAR_BOQ!$D:$D,MATCH(J{r},DAFTAR_BOQ!$A:$A,0)),""))')
        ws.cell(
            r,
            15,
            f'=IF(J{r}="","",IF(AND(COUNT(K{r})>0,OR(Q{r}="m\'",Q{r}="m")),ROUND(K{r}*IF(N{r}="",1,N{r}),3),'
            f'IF(AND(COUNT(K{r}:L{r})=2,Q{r}="m2"),ROUND(K{r}*L{r}*IF(N{r}="",1,N{r}),3),'
            f'IF(AND(COUNT(K{r}:M{r})=3,Q{r}="m3"),ROUND(K{r}*L{r}*M{r}*IF(N{r}="",1,N{r}),3),'
            f'IF(COUNT(N{r})>0,N{r},"")))))',
        )

    for idx_e, ent in enumerate(entries, start=11):
        dt_val = ent.get("tanggal")
        if isinstance(dt_val, str):
            try:
                dt_val = datetime.strptime(dt_val, "%Y-%m-%d").date()
            except ValueError:
                pass
        ws.cell(idx_e, 3, dt_val)
        ws.cell(idx_e, 3).number_format = "dd mmm yyyy"
        ws.cell(idx_e, 4, ent.get("minggu") or "M1")
        ws.cell(idx_e, 5, ent.get("kode_temuan") or "-")
        ws.cell(idx_e, 6, ent.get("lokasi") or "")
        jal_parts = str(ent.get("jalur_lajur") or "").split(None, 1)
        ws.cell(idx_e, 7, jal_parts[0] if jal_parts else "")
        ws.cell(idx_e, 8, jal_parts[1] if len(jal_parts) > 1 else "")
        ws.cell(idx_e, 10, ent.get("keyword") or ent.get("item_key") or "")
        if ent.get("p") is not None:
            ws.cell(idx_e, 11, ent["p"])
        if ent.get("l") is not None:
            ws.cell(idx_e, 12, ent["l"])
        if ent.get("t") is not None:
            ws.cell(idx_e, 13, ent["t"])
        if ent.get("jml") is not None:
            ws.cell(idx_e, 14, ent["jml"])
        if ent.get("vol_vendor") is not None:
            ws.cell(idx_e, 15, ent["vol_vendor"])
        if ent.get("volume") is not None:
            ws.cell(idx_e, 16, ent["volume"])
        ws.cell(idx_e, 18, 1)
        ws.cell(idx_e, 20, ent.get("keterangan") or "")

    tname = f"TBL_{mon_abbr}"
    tbl = Table(displayName=tname, ref=f"B10:{last_col_l}{end_row}")
    tbl.autoFilter = AutoFilter(ref=tbl.ref)
    tbl.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    calc_map = {
        "No.": "ROW()-10",
        "KODE": f'IF({tname}[[#This Row],[Item / Keyword RAB]]="","",IFERROR(INDEX(DAFTAR_BOQ!$B:$B,MATCH({tname}[[#This Row],[Item / Keyword RAB]],DAFTAR_BOQ!$A:$A,0)),""))',
        "Satuan": f'IF({tname}[[#This Row],[Item / Keyword RAB]]="","",IFERROR(INDEX(DAFTAR_BOQ!$D:$D,MATCH({tname}[[#This Row],[Item / Keyword RAB]],DAFTAR_BOQ!$A:$A,0)),""))',
    }
    tbl.tableColumns = [
        TableColumn(
            id=tc_i,
            name=lbl,
            calculatedColumnFormula=TableFormula(attr_text=calc_map[lbl]) if lbl in calc_map else None,
        )
        for tc_i, (lbl, _) in enumerate(cols, start=1)
    ]
    ws.add_table(tbl)

    tot_row = end_row + 1
    for c in range(2, last_col_idx + 1):
        cell = ws.cell(tot_row, c)
        cell.fill = sub_fill
        cell.font = Font(name="Calibri", size=9.5, bold=True, color="FFFFFF")
        cell.border = border
    ws.cell(tot_row, 2, "TOTAL PEMERIKSAAN")

    ws_boq = wb.create_sheet("DAFTAR_BOQ")
    for c, h in enumerate(("Keyword_Item", "Item_Key", "Uraian_BOQ", "Satuan", "Vendor_Resmi"), start=1):
        ws_boq.cell(1, c, h).font = Font(name="Calibri", size=10, bold=True)
    for i, it in enumerate(boq_items, start=2):
        ws_boq.cell(i, 1, it.keyword)
        ws_boq.cell(i, 2, it.item_key)
        ws_boq.cell(i, 3, it.uraian)
        ws_boq.cell(i, 4, it.satuan)
    for v_i, v in enumerate(vendors, start=2):
        ws_boq.cell(v_i, 5, v)
    ws_boq.cell(1, 7, canon_aset)
    ws_boq.cell(2, 7, hdr_wil)
    ws_boq.cell(3, 7, hdr_vend)
    ws_boq.column_dimensions["G"].hidden = True

    boq_end = 4 if canon_aset == "RM" else 1 + len(boq_items)
    dv_item = DataValidation(
        type="list",
        formula1='"Rumput,Ketrik,Striping"' if canon_aset == "RM" else f"=DAFTAR_BOQ!$A$2:$A${boq_end}",
        allow_blank=True,
        errorStyle="stop",
        showErrorMessage=True,
        errorTitle="Item BOQ Tidak Valid",
        error="Wajib pilih item dari dropdown daftar BOQ resmi. Jangan ketik manual.",
        showInputMessage=True,
        promptTitle="Pilih dari Dropdown",
        prompt="Klik panah dropdown untuk memilih item BOQ resmi.",
    )
    ws.add_data_validation(dv_item)
    dv_item.add("J11:J500")

    dv_week = DataValidation(
        type="list",
        formula1='"M1,M2,M3,M4,M5"',
        allow_blank=True,
        errorStyle="stop",
        showErrorMessage=True,
        errorTitle="Minggu Tidak Valid",
        error="Pilih M1, M2, M3, M4, atau M5 dari dropdown.",
    )
    ws.add_data_validation(dv_week)
    dv_week.add("D11:D500")

    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_options.horizontalCentered = True
    ws.print_title_rows = "$1:$10"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
