"""Generate Tagihan MC workbooks directly from monthly DATA_UNTUK_VOL silo bytes."""

from __future__ import annotations

import ast
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
import io
import operator
import re
import xml.etree.ElementTree as ET
import zipfile

import openpyxl

from services.microsoft import OPNAME_MONTH_NAMES
from services.opname_catalog import GROUP_TO_ITEMS

ALL_ITEMS_BY_GROUP_AND_KEY = {
    grp: {it.item_key: it for it in items}
    for grp, items in GROUP_TO_ITEMS.items()
}

LOG_TO_TAGIHAN_SHEET: dict[tuple[str, str], str] = {
    ("LOG_PV", "W1"): "PML PV W1",
    ("LOG_PV", "W2"): "PML PV W2",
    ("LOG_SG", "W1"): "PML RMB W1",
    ("LOG_SG", "W2"): "PML RMB W2",
    ("LOG_GR_WR", "W1"): "PML GR-WR W1",
    ("LOG_GR_WR", "W2"): "PML GR-WR W2",
    ("LOG_RM_LC", "W1"): "PML RP-LS W1",
    ("LOG_RM_LC", "W2"): "PML RP-LS W2",
    ("LOG_TRC", "W1"): "PML TRC W1",
    ("LOG_TRC", "W2"): "PML TRC W2",
    ("LOG_DR", "W1"): "PML DR W1",
    ("LOG_DR", "W2"): "PML DR W2",
    ("LOG_FE", "W1"): "PML FE W1",
    ("LOG_FE", "W2"): "PML FE W2",
}

LOG_SHEET_TO_GROUP: dict[str, str] = {
    "LOG_PV": "PV",
    "LOG_SG": "SG",
    "LOG_GR_WR": "GR_WR",
    "LOG_RM_LC": "RM_LC",
    "LOG_TRC": "TRC",
    "LOG_DR": "DR",
    "LOG_FE": "FE",
}

_LAYOUT_SCHEME_BY_INPUT_COL: dict[str, tuple[str, ...]] = {
    "L": ("D", "H", "I", "J", "L", "M", "N", "O", "P", "Q"),
    "M": ("C", "I", "J", "K", "M", "N", "O", "P", "Q", "R"),
    "N": ("D", "J", "K", "L", "N", "O", "P", "Q", "R", "S"),
    "Q": ("D", "J", "K", "L", "Q", "R", "S", "T", "U", "V"),
}

_SAFE_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_SAFE_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_CELL_SCAN_RE = re.compile(
    r'<c\b([^>]*\br="([A-Z]+)(\d+)"[^>]*)/>|<c\b([^>]*\br="([A-Z]+)(\d+)"[^>]*)>(.*?)</c>',
    re.DOTALL,
)
_CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")

_MONTH_NAME_ALIASES: dict[str, int] = {
    "jan": 1, "januari": 1, "january": 1,
    "feb": 2, "februari": 2, "february": 2,
    "mar": 3, "maret": 3, "march": 3,
    "apr": 4, "april": 4,
    "mei": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6,
    "jul": 7, "juli": 7, "july": 7,
    "agu": 8, "agt": 8, "agst": 8, "agustus": 8, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oct": 10, "oktober": 10, "october": 10,
    "nov": 11, "nop": 11, "november": 11, "nopember": 11,
    "des": 12, "dec": 12, "desember": 12, "december": 12,
}


@dataclass(frozen=True)
class TemplateItem:
    row: int
    code: str
    description: str
    unit: str
    unit_price: float | None


@dataclass(frozen=True)
class SheetLayout:
    sheet_name: str
    unit_col: str
    unit_price_col: str
    annual_total_col: str
    prev_qty_col: str
    prev_price_col: str
    input_col: str
    price_col: str
    bobot_col: str
    cum_qty_col: str
    cum_price_col: str
    cum_bobot_col: str
    first_item_row: int
    last_item_row: int
    subtotal_row: int
    annual_row: int
    dpp_row: int
    ppn_row: int
    grand_total_row: int

    @property
    def grand_total_coord(self) -> str:
        return f"{self.price_col}{self.grand_total_row}"


@dataclass
class SheetPatch:
    sheet_name: str
    row_values: dict[int, int | float | str | None] = field(default_factory=dict)
    owned_rows: set[int] = field(default_factory=set)
    active: bool = True


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split()).lower()


def _round2(value: float | int | Decimal) -> Decimal:
    clean = value if isinstance(value, Decimal) else Decimal(f"{float(value):.10f}")
    return clean.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_excel_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _parse_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
            return float(cleaned)
    return None


def _safe_eval_expr(expr: object) -> float | None:
    if isinstance(expr, bool):
        return None
    if isinstance(expr, (int, float)):
        return float(expr)
    if not isinstance(expr, str):
        return None
    text = expr.strip()
    if not text:
        return None
    if text.startswith("="):
        text = text[1:].strip()
    if text.startswith("+"):
        text = text[1:].strip()
    if not text:
        return None
    if text.endswith("%"):
        inner = _safe_eval_expr(text[:-1])
        return inner / 100.0 if inner is not None else None
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_UNARY_OPS:
            return _SAFE_UNARY_OPS[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BIN_OPS:
            right = _eval(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise ZeroDivisionError
            return _SAFE_BIN_OPS[type(node.op)](_eval(node.left), right)
        raise ValueError("Unsupported AST node")

    try:
        return float(_eval(tree))
    except (ValueError, ZeroDivisionError, TypeError):
        return None


def parse_tagihan_cycle(
    arg_text: str,
    template_filename: str = "",
    default_cycle: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """
    Resolve target `(cycle_month, cycle_year)` from `/tagihan [args]` text,
    falling back to `MC-<MM>` / month token in `template_filename`, or active cycle.
    """
    now = datetime.datetime.now()
    if default_cycle is None:
        from services.message_utils import resolve_billing_cycle
        default_cycle = resolve_billing_cycle(now.date())

    cleaned = re.sub(r"^/tagihan\b", "", arg_text or "", flags=re.IGNORECASE).strip()

    # 1. Explicit YYYY-MM or MM/YYYY in command
    m_ym = re.search(r"\b(20\d{2})[-/](\d{1,2})\b", cleaned)
    if m_ym:
        y, m = int(m_ym.group(1)), int(m_ym.group(2))
        if 1 <= m <= 12:
            return m, y

    m_my = re.search(r"\b(\d{1,2})[-/](20\d{2})\b", cleaned)
    if m_my:
        m, y = int(m_my.group(1)), int(m_my.group(2))
        if 1 <= m <= 12:
            return m, y

    # 2. Month name or number token in command (+ optional year)
    m_yr = re.search(r"\b(20\d{2})\b", cleaned)
    yr_val = int(m_yr.group(1)) if m_yr else default_cycle[1]

    for tok in re.findall(r"[A-Za-z0-9]+", cleaned.lower()):
        if tok in _MONTH_NAME_ALIASES:
            return _MONTH_NAME_ALIASES[tok], yr_val
        if tok.isdigit() and 1 <= int(tok) <= 12:
            return int(tok), yr_val

    # 3. Infer from template filename e.g. `MC-11 MENCARI VOLUME 2026.xlsx`
    fname = template_filename or ""
    m_fn_yr = re.search(r"\b(20\d{2})\b", fname)
    fn_yr = int(m_fn_yr.group(1)) if m_fn_yr else default_cycle[1]
    m_mc = re.search(r"\bMC[-_\s]?(\d{1,2})\b", fname, re.IGNORECASE)
    if m_mc:
        m_num = int(m_mc.group(1))
        if 1 <= m_num <= 12:
            return m_num, fn_yr
    for tok in re.findall(r"[A-Za-z]+", fname.lower()):
        if tok in _MONTH_NAME_ALIASES:
            return _MONTH_NAME_ALIASES[tok], fn_yr

    return default_cycle


def _resolve_sheet_xml_paths(zf: zipfile.ZipFile) -> dict[str, str]:
    wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rid_to_target: dict[str, str] = {}
    for rel in rels_root:
        rid = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rid and target:
            rid_to_target[rid] = target

    sheet_map: dict[str, str] = {}
    r_id_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for elem in wb_root.iter():
        if elem.tag.endswith("}sheet") or elem.tag == "sheet":
            name = elem.attrib.get("name")
            rid = elem.attrib.get(r_id_attr) or elem.attrib.get("id")
            if name and rid and rid in rid_to_target:
                target = rid_to_target[rid].lstrip("/")
                if not target.startswith("xl/"):
                    target = "xl/" + target
                sheet_map[name] = target
    return sheet_map


def _load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    ss_xml = zf.read("xl/sharedStrings.xml").decode("utf-8")
    strings: list[str] = []
    for si in re.finditer(r"<si\b[^>]*>(.*?)</si>", ss_xml, re.DOTALL):
        parts = re.findall(r"<t\b[^>]*>([^<]*)</t>", si.group(1))
        strings.append("".join(parts))
    return strings


def _index_sheet_cells(
    xml: str,
    shared_strings: list[str],
    min_row: int = 1,
    max_row: int = 300,
) -> dict[str, tuple[str, str, str]]:
    cells: dict[str, tuple[str, str, str]] = {}
    for m in _CELL_SCAN_RE.finditer(xml):
        if m.group(1) is not None:
            attrs, col, row_s, inner = m.group(1), m.group(2), m.group(3), ""
        else:
            attrs, col, row_s, inner = m.group(4), m.group(5), m.group(6), m.group(7)
        row_n = int(row_s)
        if row_n < min_row or row_n > max_row:
            continue
        coord = f"{col}{row_s}"
        if not inner:
            cells[coord] = ("", "", attrs)
            continue
        f_m = re.search(r"<f\b[^>]*>(.*?)</f>", inner, re.DOTALL)
        f_txt = f_m.group(1) if f_m else ("<shared>" if "<f" in inner else "")
        if 't="inlineStr"' in attrs:
            t_parts = re.findall(r"<t\b[^>]*>([^<]*)</t>", inner)
            cells[coord] = ("".join(t_parts), f_txt, attrs)
            continue
        v_m = re.search(r"<v>([^<]*)</v>", inner)
        if not v_m:
            cells[coord] = ("", f_txt, attrs)
            continue
        raw_v = v_m.group(1)
        if 't="s"' in attrs:
            idx = int(raw_v)
            txt = shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
        else:
            txt = raw_v
        cells[coord] = (txt, f_txt, attrs)
    return cells


def _detect_sheet_layout(
    sheet_name: str,
    cells: dict[str, tuple[str, str, str]],
) -> SheetLayout:
    vol_cols: list[str] = []
    unit_price_col = ""
    for col_idx in range(5, 24):
        col = openpyxl.utils.get_column_letter(col_idx)
        val8 = _normalize_text(cells.get(f"{col}8", ("", "", ""))[0])
        if val8 == "harga satuan":
            unit_price_col = col
        elif val8 == "volume":
            vol_cols.append(col)

    input_col = ""
    if len(vol_cols) >= 3 and vol_cols[1] in _LAYOUT_SCHEME_BY_INPUT_COL:
        input_col = vol_cols[1]
    elif unit_price_col == "G":
        input_col = "L"
    elif unit_price_col == "H":
        input_col = "M"
    elif unit_price_col == "I":
        input_col = "Q" if "PV" in sheet_name.upper() else "N"

    if input_col not in _LAYOUT_SCHEME_BY_INPUT_COL:
        raise ValueError(f"Format kolom sheet `{sheet_name}` tidak dikenali (vol_cols={vol_cols}).")

    (
        unit_col,
        annual_total_col,
        prev_qty_col,
        prev_price_col,
        input_col,
        price_col,
        bobot_col,
        cum_qty_col,
        cum_price_col,
        cum_bobot_col,
    ) = _LAYOUT_SCHEME_BY_INPUT_COL[input_col]
    if not unit_price_col:
        unit_price_col = {"L": "G", "M": "H", "N": "I", "Q": "I"}[input_col]

    subtotal_row = annual_row = dpp_row = ppn_row = grand_total_row = 0
    for r in range(20, 260):
        a_txt = _normalize_text(cells.get(f"A{r}", ("", "", ""))[0]).upper()
        b_txt = _normalize_text(cells.get(f"B{r}", ("", "", ""))[0])
        if a_txt == "A" and "total nilai perbulan" in b_txt:
            subtotal_row = r
        elif a_txt == "B" and "total nilai pertahun" in b_txt:
            annual_row = r
        elif a_txt == "C" and ("dasar pengenaan pajak" in b_txt or "dpp" in b_txt):
            dpp_row = r
        elif a_txt == "D" and "ppn" in b_txt:
            ppn_row = r
        elif a_txt == "E" and "grand total" in b_txt:
            grand_total_row = r
            break

    if not subtotal_row or not grand_total_row:
        raise ValueError(f"Baris total footer tidak ditemukan pada sheet `{sheet_name}`.")

    return SheetLayout(
        sheet_name=sheet_name,
        unit_col=unit_col,
        unit_price_col=unit_price_col,
        annual_total_col=annual_total_col,
        prev_qty_col=prev_qty_col,
        prev_price_col=prev_price_col,
        input_col=input_col,
        price_col=price_col,
        bobot_col=bobot_col,
        cum_qty_col=cum_qty_col,
        cum_price_col=cum_price_col,
        cum_bobot_col=cum_bobot_col,
        first_item_row=10,
        last_item_row=subtotal_row - 1,
        subtotal_row=subtotal_row,
        annual_row=annual_row or (subtotal_row + 1),
        dpp_row=dpp_row or (subtotal_row + 2),
        ppn_row=ppn_row or (subtotal_row + 3),
        grand_total_row=grand_total_row,
    )


def _extract_sheet_items(
    layout: SheetLayout,
    cells: dict[str, tuple[str, str, str]],
) -> list[TemplateItem]:
    items: list[TemplateItem] = []
    for r in range(layout.first_item_row, layout.last_item_row + 1):
        code = cells.get(f"A{r}", ("", "", ""))[0].strip()
        desc = " ".join(cells.get(f"B{r}", ("", "", ""))[0].split())
        unit = cells.get(f"{layout.unit_col}{r}", ("", "", ""))[0].strip()
        if not unit:
            alt_col = "C" if layout.unit_col == "D" else "D"
            unit = cells.get(f"{alt_col}{r}", ("", "", ""))[0].strip()
        price = _parse_number(cells.get(f"{layout.unit_price_col}{r}", ("", "", ""))[0])
        if code or desc or price is not None:
            items.append(TemplateItem(row=r, code=code, description=desc, unit=unit, unit_price=price))
    return items


def _match_template_item(
    items: list[TemplateItem],
    group_key: str,
    item_key: str,
    uraian_log: str,
) -> TemplateItem | None:
    cat_entry = ALL_ITEMS_BY_GROUP_AND_KEY.get(group_key, {}).get(item_key)
    target_uraian = cat_entry.uraian if cat_entry else uraian_log
    disp_code = cat_entry.display_code if cat_entry else re.sub(r"-[A-Z0-9]+$", "", item_key)
    norm_u = _normalize_text(target_uraian)

    if norm_u:
        for tmpl_it in items:
            if _normalize_text(tmpl_it.description) == norm_u:
                return tmpl_it

    if disp_code:
        code_hits = [it for it in items if it.code.strip().upper() == disp_code.strip().upper()]
        if len(code_hits) == 1:
            return code_hits[0]
        if len(code_hits) > 1 and norm_u:
            for it in code_hits:
                td = _normalize_text(it.description)
                if norm_u in td or td in norm_u:
                    return it

    if norm_u:
        for tmpl_it in items:
            td = _normalize_text(tmpl_it.description)
            if td and (norm_u in td or td in norm_u):
                return tmpl_it
    return None


def _eval_log_row_volume(ws_val, ws_fml, r_idx: int, col_map: dict[str, int]) -> float:
    c_vol = col_map.get("volume", 16)
    num_v = _parse_number(ws_val.cell(r_idx, c_vol).value)
    if num_v is not None:
        return num_v
    num_f = _parse_number(ws_fml.cell(r_idx, c_vol).value)
    if num_f is not None:
        return num_f

    dims = []
    for key, default_c in (("p", 11), ("l", 12), ("t", 13), ("jumlah", 14)):
        col_i = col_map.get(key, default_c)
        d = _parse_number(ws_val.cell(r_idx, col_i).value)
        if d is not None:
            dims.append(d)
    if dims:
        prod = 1.0
        for d in dims:
            prod *= d
        return prod
    return 0.0


def _fmt_xml_num(val: int | float | str) -> str:
    if isinstance(val, str):
        val = float(val)
    if isinstance(val, int) or (isinstance(val, float) and val.is_integer()):
        return str(int(val))
    return f"{val:.10f}".rstrip("0").rstrip(".")


def _eval_existing_cell(cells: dict[str, tuple[str, str, str]], coord: str) -> float:
    txt, f_txt, _attrs = cells.get(coord, ("", "", ""))
    num = _parse_number(txt)
    if num is not None:
        return float(num)
    if f_txt and f_txt != "<shared>":
        ev = _safe_eval_expr(f_txt)
        if ev is not None:
            return ev
    return 0.0


def _insert_missing_cell_in_row(xml: str, coord: str, cell_xml: str) -> str:
    m_coord = _CELL_REF_RE.match(coord)
    if not m_coord:
        raise ValueError(f"Koordinat sel tidak valid: {coord}")
    target_col_idx = openpyxl.utils.column_index_from_string(m_coord.group(1))
    row_s = m_coord.group(2)
    row_re = re.compile(rf'(<row\b[^>]*\br="{row_s}"[^>]*>)(.*?)(</row>)', re.DOTALL)
    m_row = row_re.search(xml)
    if not m_row:
        raise ValueError(f"Baris {row_s} tidak ditemukan untuk sel {coord}")

    row_open, row_inner, row_close = m_row.group(1), m_row.group(2), m_row.group(3)
    insert_pos = len(row_inner)
    for cm in re.finditer(r'<c\b[^>]*\br="([A-Z]+)\d+"[^>]*?(?:/>|>.*?</c>)', row_inner, re.DOTALL):
        c_idx = openpyxl.utils.column_index_from_string(cm.group(1))
        if c_idx > target_col_idx:
            insert_pos = cm.start()
            break
    new_row = f"{row_open}{row_inner[:insert_pos]}{cell_xml}{row_inner[insert_pos:]}{row_close}"
    return xml[: m_row.start()] + new_row + xml[m_row.end() :]


def _patch_sheet_xml(
    xml: str,
    layout: SheetLayout,
    patch: SheetPatch,
    cells: dict[str, tuple[str, str, str]],
    rollover_previous_month: bool = False,
) -> tuple[str, float, float]:
    if not patch.active:
        return (
            xml,
            _eval_existing_cell(cells, layout.grand_total_coord),
            _eval_existing_cell(cells, f"{layout.prev_price_col}{layout.grand_total_row}"),
        )

    annual_total = _eval_existing_cell(cells, f"{layout.annual_total_col}{layout.annual_row}")
    prev_bobot_col = openpyxl.utils.get_column_letter(
        openpyxl.utils.column_index_from_string(layout.prev_price_col) + 1
    )
    ops: dict[str, tuple[object, ...]] = {}
    subtotal = cum_subtotal = bobot_sum = cum_bobot_sum = 0.0
    prev_subtotal = prev_bobot_sum = 0.0

    start_r = 12 if layout.sheet_name.startswith("PML PV") else layout.first_item_row
    for row in range(layout.first_item_row, layout.last_item_row + 1):
        in_patch_range = row >= start_r
        unit_price = _eval_existing_cell(cells, f"{layout.unit_price_col}{row}")
        has_price_cell = (
            f"{layout.unit_price_col}{row}" in cells
            and _parse_number(cells[f"{layout.unit_price_col}{row}"][0]) is not None
        )
        old_prev_qty = _eval_existing_cell(cells, f"{layout.prev_qty_col}{row}")
        old_in_qty = _eval_existing_cell(cells, f"{layout.input_col}{row}")

        if rollover_previous_month and row >= start_r:
            prev_dec = Decimal(f"{old_prev_qty:.10f}") + Decimal(f"{old_in_qty:.10f}")
            prev_qty = float(prev_dec)
            prev_val = int(prev_dec) if prev_dec == prev_dec.to_integral_value() else prev_qty
            ops[f"{layout.prev_qty_col}{row}"] = ("patch", prev_val if prev_qty else 0)
            if layout.sheet_name.startswith("PML PV"):
                for nop_col in ("N", "O", "P"):
                    ops[f"{nop_col}{row}"] = ("patch", None)
        else:
            prev_qty = old_prev_qty

        in_coord = f"{layout.input_col}{row}"
        if row in patch.owned_rows and in_patch_range:
            in_spec = patch.row_values.get(row)
            q_val = 0.0 if in_spec is None else (_safe_eval_expr(in_spec) or 0.0)
            ops[in_coord] = ("patch", in_spec)
        else:
            q_val = _eval_existing_cell(cells, in_coord)

        if has_price_cell:
            if rollover_previous_month:
                p_price = prev_qty * unit_price
                prev_subtotal += p_price
                p_bobot = (p_price / annual_total * 100.0) if annual_total > 0 else 0.0
                prev_bobot_sum += p_bobot
                ops[f"{layout.prev_price_col}{row}"] = ("cached_v", p_price)
                ops[f"{prev_bobot_col}{row}"] = ("cached_v", p_bobot)

            m_price = q_val * unit_price
            subtotal += m_price
            m_bobot = (m_price / annual_total * 100.0) if annual_total > 0 else 0.0
            bobot_sum += m_bobot

            cum_qty = prev_qty + q_val
            cum_price = cum_qty * unit_price
            cum_subtotal += cum_price
            cum_bobot = (cum_price / annual_total * 100.0) if annual_total > 0 else 0.0
            cum_bobot_sum += cum_bobot

            ops[f"{layout.price_col}{row}"] = ("cached_v", m_price)
            ops[f"{layout.bobot_col}{row}"] = ("cached_v", m_bobot)
            ops[f"{layout.cum_qty_col}{row}"] = ("cached_v", cum_qty)
            ops[f"{layout.cum_price_col}{row}"] = ("cached_v", cum_price)
            ops[f"{layout.cum_bobot_col}{row}"] = ("cached_v", cum_bobot)

    dpp = subtotal * 11.0 / 12.0
    ppn = dpp * 0.12
    grand_total = subtotal + ppn
    cum_dpp = cum_subtotal * 11.0 / 12.0
    cum_ppn = cum_dpp * 0.12
    cum_gt = cum_subtotal + cum_ppn

    if rollover_previous_month:
        prev_dpp = prev_subtotal * 11.0 / 12.0
        prev_ppn = prev_dpp * 0.12
        prev_gt = prev_subtotal + prev_ppn
        ops[f"{layout.prev_price_col}{layout.subtotal_row}"] = ("cached_v", prev_subtotal)
        ops[f"{layout.prev_price_col}{layout.dpp_row}"] = ("cached_v", prev_dpp)
        ops[f"{layout.prev_price_col}{layout.ppn_row}"] = ("cached_v", prev_ppn)
        ops[f"{layout.prev_price_col}{layout.grand_total_row}"] = ("cached_v", prev_gt)
        ops[f"{prev_bobot_col}{layout.subtotal_row}"] = ("cached_v", prev_bobot_sum)
    else:
        prev_gt = _eval_existing_cell(cells, f"{layout.prev_price_col}{layout.grand_total_row}")

    ops[f"{layout.price_col}{layout.subtotal_row}"] = ("cached_v", subtotal)
    ops[f"{layout.price_col}{layout.dpp_row}"] = ("cached_v", dpp)
    ops[f"{layout.price_col}{layout.ppn_row}"] = ("cached_v", ppn)
    ops[f"{layout.price_col}{layout.grand_total_row}"] = ("cached_v", grand_total)
    ops[f"{layout.bobot_col}{layout.subtotal_row}"] = ("cached_v", bobot_sum)

    ops[f"{layout.cum_price_col}{layout.subtotal_row}"] = ("cached_v", cum_subtotal)
    ops[f"{layout.cum_price_col}{layout.dpp_row}"] = ("cached_v", cum_dpp)
    ops[f"{layout.cum_price_col}{layout.ppn_row}"] = ("cached_v", cum_ppn)
    ops[f"{layout.cum_price_col}{layout.grand_total_row}"] = ("cached_v", cum_gt)
    ops[f"{layout.cum_bobot_col}{layout.subtotal_row}"] = ("cached_v", cum_bobot_sum)

    seen_coords: set[str] = set()

    def _replace_cell(m: re.Match[str]) -> str:
        if m.group(1) is not None:
            raw_attrs, col, row_s, inner = m.group(1), m.group(2), m.group(3), ""
        else:
            raw_attrs, col, row_s, inner = m.group(4), m.group(5), m.group(6), m.group(7)
        coord = f"{col}{row_s}"
        op = ops.get(coord)
        if op is None:
            return m.group(0)
        seen_coords.add(coord)
        if op[0] == "patch":
            spec = op[1]
            if spec in ("0", 0, 0.0):
                spec = None
            clean_attrs = re.sub(r'\s+\bt="[^"]*"', "", raw_attrs)
            return f"<c{clean_attrs}/>" if spec is None else f"<c{clean_attrs}><v>{_fmt_xml_num(spec)}</v></c>"
        if "<f" not in inner:
            return f"<c{raw_attrs}>{inner}</c>" if inner else f"<c{raw_attrs}/>"
        v_str = f"<v>{_fmt_xml_num(float(op[1]))}</v>"
        inner_new = re.sub(r"<v>.*?</v>", v_str, inner, count=1, flags=re.DOTALL) if "<v>" in inner else (inner + v_str)
        return f"<c{raw_attrs}>{inner_new}</c>"

    new_xml = _CELL_SCAN_RE.sub(_replace_cell, xml)

    for coord, op in ops.items():
        if coord in seen_coords or op[0] != "patch":
            continue
        spec = op[1]
        if spec in (None, "0", 0, 0.0):
            continue
        new_xml = _insert_missing_cell_in_row(new_xml, coord, f'<c r="{coord}"><v>{_fmt_xml_num(spec)}</v></c>')

    return new_xml, grand_total, prev_gt


def _update_formula_cached_v(xml: str, coord: str, cached_num: float) -> str:
    pattern = re.compile(rf'(<c\b[^>]*\br="{coord}"[^>]*>)(.*?)(</c>)', re.DOTALL)

    def repl(match: re.Match[str]) -> str:
        open_tag, inner, close_tag = match.group(1), match.group(2), match.group(3)
        if "<f" not in inner:
            return match.group(0)
        v_str = f"<v>{_fmt_xml_num(cached_num)}</v>"
        inner_new = re.sub(r"<v>.*?</v>", v_str, inner, count=1, flags=re.DOTALL) if "<v>" in inner else (inner + v_str)
        return f"{open_tag}{inner_new}{close_tag}"

    return pattern.sub(repl, xml, count=1)


def _update_rekap_sheets(
    rekap_inc_xml: str | None,
    rekap_p1_xml: str | None,
    patched_grand_totals: dict[str, float],
    prev_grand_totals: dict[str, float] | None = None,
) -> tuple[str | None, str | None]:
    inc_x_vals: dict[int, float] = {}
    sheet_ref_re = re.compile(r"^'([^']+)'!([A-Z]+\d+)$")

    if rekap_inc_xml is not None:
        inc_cells = _index_sheet_cells(rekap_inc_xml, [], 8, 25)
        for r in range(8, 22):
            coord = f"X{r}"
            _txt, f_txt, _a = inc_cells.get(coord, ("", "", ""))
            m_ref = sheet_ref_re.match(f_txt.replace("&amp;", "&").strip())
            if m_ref and m_ref.group(1) in patched_grand_totals:
                new_val = patched_grand_totals[m_ref.group(1)]
                rekap_inc_xml = _update_formula_cached_v(rekap_inc_xml, coord, new_val)
                inc_x_vals[r] = new_val
            else:
                inc_x_vals[r] = _eval_existing_cell(inc_cells, coord)

    if rekap_p1_xml is None:
        return rekap_inc_xml, None

    p1_cells = _index_sheet_cells(rekap_p1_xml, [], 8, 30)
    v_vals: dict[int, float] = {}
    w_vals: dict[int, float] = {}
    x_vals: dict[int, float] = {}
    for r in range(8, 29):
        v_coord = f"V{r}"
        _vt, vf_txt, _va = p1_cells.get(v_coord, ("", "", ""))
        m_vref = sheet_ref_re.match(vf_txt.replace("&amp;", "&").strip())
        v_updated = False
        if prev_grand_totals and m_vref and m_vref.group(1) in prev_grand_totals:
            v_val = prev_grand_totals[m_vref.group(1)]
            rekap_p1_xml = _update_formula_cached_v(rekap_p1_xml, v_coord, v_val)
            v_updated = True
        else:
            v_val = _eval_existing_cell(p1_cells, v_coord)
        v_vals[r] = v_val

        coord = f"W{r}"
        _txt, f_txt, _a = p1_cells.get(coord, ("", "", ""))
        clean_f = f_txt.replace("&amp;", "&").strip()
        m_ref = sheet_ref_re.match(clean_f)
        updated = False
        if m_ref:
            ref_sheet, ref_coord = m_ref.group(1), m_ref.group(2)
            if ref_sheet in patched_grand_totals:
                new_val = patched_grand_totals[ref_sheet]
                rekap_p1_xml = _update_formula_cached_v(rekap_p1_xml, coord, new_val)
                w_vals[r] = new_val
                updated = True
            elif ref_sheet == "REKAP INC PPN" and ref_coord.startswith("X"):
                inc_row = int(ref_coord[1:])
                if inc_row in inc_x_vals and r <= 21:
                    new_val = inc_x_vals[inc_row]
                    rekap_p1_xml = _update_formula_cached_v(rekap_p1_xml, coord, new_val)
                    w_vals[r] = new_val
                    updated = True
        if not updated:
            w_vals[r] = _eval_existing_cell(p1_cells, coord)

        if (updated or v_updated) and 8 <= r <= 21:
            f_val = _eval_existing_cell(p1_cells, f"F{r}")
            _xt, xf, _xa = p1_cells.get(f"X{r}", ("", "", ""))
            if "V" in xf and "W" in xf:
                x_val = v_val + w_vals[r]
                rekap_p1_xml = _update_formula_cached_v(rekap_p1_xml, f"X{r}", x_val)
                x_vals[r] = x_val
                if f_val > 0:
                    y_val = x_val / f_val
                    rekap_p1_xml = _update_formula_cached_v(rekap_p1_xml, f"Y{r}", y_val)
                    rekap_p1_xml = _update_formula_cached_v(rekap_p1_xml, f"Z{r}", 1.0 - y_val)
            else:
                x_vals[r] = _eval_existing_cell(p1_cells, f"X{r}")
        else:
            x_vals[r] = _eval_existing_cell(p1_cells, f"X{r}")

    _v29t, v29_f, _v29a = p1_cells.get("V29", ("", "", ""))
    if "SUM(V8:V28)" in v29_f.upper():
        rekap_p1_xml = _update_formula_cached_v(rekap_p1_xml, "V29", sum(v_vals.get(r, 0.0) for r in range(8, 29)))
    _w29t, w29_f, _w29a = p1_cells.get("W29", ("", "", ""))
    if "SUM(W8:W28)" in w29_f.upper():
        rekap_p1_xml = _update_formula_cached_v(rekap_p1_xml, "W29", sum(w_vals.get(r, 0.0) for r in range(8, 29)))
    _x29t, x29_f, _x29a = p1_cells.get("X29", ("", "", ""))
    if "SUM(X8:X28)" in x29_f.upper():
        rekap_p1_xml = _update_formula_cached_v(rekap_p1_xml, "X29", sum(x_vals.get(r, 0.0) for r in range(8, 29)))

    return rekap_inc_xml, rekap_p1_xml


def generate_tagihan_workbook(
    vista_bytes: bytes,
    template_bytes: bytes,
    cycle_month: int,
    cycle_year: int,
    rollover_previous_month: bool = False,
) -> dict:
    """
    Aggregate all 7 `LOG_*` sheets from `DATA_UNTUK_VOL` bytes and surgically patch
    the 14 `PML *` sheets + `REKAP` tabs of `template_bytes` into output `.xlsx` bytes.
    When `rollover_previous_month=True`, `S.D. BULAN INI` (`prev_qty + input_qty`) from
    `template_bytes` is rolled into `S.D. BULAN LALU` (`prev_qty`) before writing `Bulan Ini`.
    """
    wb_val = openpyxl.load_workbook(io.BytesIO(vista_bytes), data_only=True)
    wb_fml = openpyxl.load_workbook(io.BytesIO(vista_bytes), data_only=False)

    patches: dict[str, SheetPatch] = {}
    warnings: list[str] = []
    grand_totals: dict[str, float] = {}
    prev_grand_totals: dict[str, float] = {}
    patched_xml_by_internal_path: dict[str, bytes] = {}
    out_buf = io.BytesIO()

    try:
        with zipfile.ZipFile(io.BytesIO(template_bytes), "r") as zin:
            sheet_paths = _resolve_sheet_xml_paths(zin)
            shared_strings = _load_shared_strings(zin)

            raw_xml_cache: dict[str, str] = {}
            cells_cache: dict[str, dict[str, tuple[str, str, str]]] = {}
            layout_cache: dict[str, SheetLayout] = {}
            items_cache: dict[str, list[TemplateItem]] = {}

            def _load_sheet(t_sheet: str) -> tuple[str, dict[str, tuple[str, str, str]], SheetLayout, list[TemplateItem]]:
                if t_sheet not in raw_xml_cache:
                    raw_xml = zin.read(sheet_paths[t_sheet]).decode("utf-8")
                    cells = _index_sheet_cells(raw_xml, shared_strings, 1, 260)
                    layout = _detect_sheet_layout(t_sheet, cells)
                    items = _extract_sheet_items(layout, cells)
                    raw_xml_cache[t_sheet] = raw_xml
                    cells_cache[t_sheet] = cells
                    layout_cache[t_sheet] = layout
                    items_cache[t_sheet] = items
                return raw_xml_cache[t_sheet], cells_cache[t_sheet], layout_cache[t_sheet], items_cache[t_sheet]

            for log_name, group_key in LOG_SHEET_TO_GROUP.items():
                if log_name not in wb_val.sheetnames:
                    continue
                ws_v = wb_val[log_name]
                ws_f = wb_fml[log_name]

                col_map: dict[str, int] = {}
                for c in range(1, min(ws_f.max_column, 25) + 1):
                    hdr = _normalize_text(ws_f.cell(1, c).value)
                    if hdr:
                        col_map[hdr] = c

                c_wil = col_map.get("wilayah", 5)
                c_key = col_map.get("item_key", 9)
                c_ur = col_map.get("uraian_boq", 10)

                for wil in ("W1", "W2"):
                    t_sheet = LOG_TO_TAGIHAN_SHEET[(log_name, wil)]
                    if t_sheet not in sheet_paths or t_sheet in patches:
                        continue
                    _, _, _, t_items = _load_sheet(t_sheet)
                    patches[t_sheet] = SheetPatch(
                        sheet_name=t_sheet,
                        row_values={it.row: 0 for it in t_items},
                        owned_rows={it.row for it in t_items},
                        active=True,
                    )

                row_accum: dict[tuple[str, int], Decimal] = defaultdict(lambda: Decimal("0"))
                for r in range(2, ws_v.max_row + 1):
                    wil = str(ws_v.cell(r, c_wil).value or "").strip().upper()
                    item_key = str(ws_v.cell(r, c_key).value or "").strip()
                    uraian = str(ws_v.cell(r, c_ur).value or "").strip()
                    if not item_key and not uraian:
                        continue
                    if wil not in ("W1", "W2"):
                        warnings.append(f"{log_name} R{r}: Wilayah `{wil}` tidak valid.")
                        continue
                    t_sheet = LOG_TO_TAGIHAN_SHEET[(log_name, wil)]
                    if t_sheet not in sheet_paths:
                        continue
                    vol = _eval_log_row_volume(ws_v, ws_f, r, col_map)
                    if vol <= 0:
                        continue
                    _, _, _, t_items = _load_sheet(t_sheet)
                    matched = _match_template_item(t_items, group_key, item_key, uraian)
                    if not matched:
                        warnings.append(f"{log_name} R{r}: Item `{item_key}` ({uraian}) tidak cocok di `{t_sheet}`.")
                        continue
                    row_accum[(t_sheet, matched.row)] += Decimal(f"{vol:.10f}")

                for (t_sheet, t_row), total_dec in row_accum.items():
                    patches[t_sheet].row_values[t_row] = _to_excel_number(_round2(total_dec))

            for t_sheet, patch in patches.items():
                raw_xml, cells, layout, _ = _load_sheet(t_sheet)
                new_xml, gt, prev_gt = _patch_sheet_xml(
                    raw_xml,
                    layout,
                    patch,
                    cells,
                    rollover_previous_month=rollover_previous_month,
                )
                patched_xml_by_internal_path[sheet_paths[t_sheet]] = new_xml.encode("utf-8")
                grand_totals[t_sheet] = gt
                prev_grand_totals[t_sheet] = prev_gt

            rekap_p1_path = sheet_paths.get("REKAP PILAR 1 PEMEL")
            rekap_inc_path = sheet_paths.get("REKAP INC PPN")
            rekap_p1_raw = zin.read(rekap_p1_path).decode("utf-8") if rekap_p1_path else None
            rekap_inc_raw = zin.read(rekap_inc_path).decode("utf-8") if rekap_inc_path else None
            rekap_inc_new, rekap_p1_new = _update_rekap_sheets(
                rekap_inc_raw,
                rekap_p1_raw,
                grand_totals,
                prev_grand_totals=prev_grand_totals if rollover_previous_month else None,
            )
            if rekap_p1_path and rekap_p1_new is not None:
                patched_xml_by_internal_path[rekap_p1_path] = rekap_p1_new.encode("utf-8")
            if rekap_inc_path and rekap_inc_new is not None:
                patched_xml_by_internal_path[rekap_inc_path] = rekap_inc_new.encode("utf-8")

            with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    fname = item.filename
                    if fname == "xl/calcChain.xml":
                        continue
                    if fname in patched_xml_by_internal_path:
                        data = patched_xml_by_internal_path[fname]
                    else:
                        data = zin.read(fname)
                        if fname == "xl/workbook.xml":
                            wb_str = data.decode("utf-8")
                            if 'fullCalcOnLoad="1"' not in wb_str:
                                wb_str = re.sub(r"<calcPr\b", '<calcPr fullCalcOnLoad="1"', wb_str, count=1)
                            data = wb_str.encode("utf-8")
                        elif fname == "xl/_rels/workbook.xml.rels":
                            data = re.sub(
                                r'<Relationship\b[^>]*\bTarget="calcChain\.xml"[^>]*/>', "", data.decode("utf-8")
                            ).encode("utf-8")
                        elif fname == "[Content_Types].xml":
                            data = re.sub(
                                r'<Override\b[^>]*\bPartName="/xl/calcChain\.xml"[^>]*/>', "", data.decode("utf-8")
                            ).encode("utf-8")
                    zout.writestr(item, data)
    finally:
        wb_val.close()
        wb_fml.close()

    ordered_sheets = [s for s in LOG_TO_TAGIHAN_SHEET.values() if s in grand_totals]
    month_label = OPNAME_MONTH_NAMES.get(cycle_month, f"{cycle_month:02d}")
    return {
        "output_bytes": out_buf.getvalue(),
        "output_filename": f"MC-{cycle_month:02d}_TAGIHAN_{month_label}_{cycle_year}.xlsx",
        "ordered_sheets": ordered_sheets,
        "grand_totals": grand_totals,
        "prev_grand_totals": prev_grand_totals,
        "total_grand": sum(grand_totals.values()),
        "rollover_applied": rollover_previous_month,
        "warnings": warnings,
    }
