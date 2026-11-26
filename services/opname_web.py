from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import re
import sqlite3
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from config import settings
from services.message_utils import parse_opname_date_str, resolve_billing_cycle
from services.opname_catalog import (
    ASSET_TITLES,
    ASSET_TO_TABLE,
    VALID_OPNAME_ASSETS,
    check_roster_pairing,
    normalize_asset_code,
    normalize_vendor,
    resolve_boq_item,
    resolve_wilayah,
)
from services.opname_roster import (
    ROSTER_CONFIG_FILENAME,
    ROSTER_CONFIG_FOLDER,
    export_roster_payload,
    get_active_roster,
    get_allowed_vendors_for_asset,
    import_roster_payload,
    pull_roster_from_onedrive,
    push_roster_to_onedrive,
    set_roster_slot_active,
    set_vendor_active,
    upsert_roster_slot,
)
from services.opname_web_ui import (
    render_forbidden_page_html,
    render_opname_list_page_html,
    render_review_page_html,
)
from services.opname_xlsx import _items_for_asset_boq, build_prefilled_standard_xlsx

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _get_web_secret() -> str:
    return (
        settings.OPNAME_WEB_SECRET
        or settings.WAHA_API_KEY
        or settings.MICROSOFT_CLIENT_SECRET
        or "ais-vista-local-dev-secret"
    )


def make_opname_token(scope: str) -> str:
    """Create a deterministic HMAC-SHA256 access token for a record or DASHBOARD scope."""
    norm_scope = (scope or "").strip().upper().encode("utf-8")
    digest = hmac.new(_get_web_secret().encode("utf-8"), norm_scope, hashlib.sha256).hexdigest()
    return digest[:32]


def verify_opname_token(scope: str, token: str) -> bool:
    """Validate token against the target scope token or the DASHBOARD master token."""
    cand = (token or "").strip()
    if not cand:
        return False
    expected_scope = make_opname_token(scope)
    expected_dash = make_opname_token("DASHBOARD")
    return hmac.compare_digest(cand, expected_scope) or hmac.compare_digest(cand, expected_dash)


def build_review_url(base_url: str, record_id: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base or not record_id:
        return ""
    rid = record_id.strip().upper()
    return f"{base}/review/{rid}?token={make_opname_token(rid)}"


def build_dashboard_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/opname?token={make_opname_token('DASHBOARD')}"


def _safe_json_loads(raw: Any, default: Any) -> Any:
    if not raw:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


def _to_opt_float(val: Any) -> tuple[bool, float | None]:
    if val is None or val == "":
        return True, None
    if isinstance(val, bool):
        return False, None
    if isinstance(val, (int, float)):
        return True, float(val)
    if isinstance(val, str):
        s = val.strip().replace(",", ".")
        if not s:
            return True, None
        try:
            return True, float(s)
        except ValueError:
            return False, None
    return False, None


def _cycle_from_slot_id(slot_id: str) -> tuple[str, int, int, str] | None:
    m = re.match(r"^XLS-(\d{2})(\d{2})-([A-Z]+)-(W[12])-([A-Z0-9]+)-(M[1-5])$", (slot_id or "").upper())
    if not m:
        return None
    yy = int(m.group(1))
    mm = int(m.group(2))
    cy = 2000 + yy
    return f"{cy:04d}-{mm:02d}", mm, cy, m.group(6)


def _load_record(db_path: str, record_id: str) -> dict[str, Any] | None:
    rid = (record_id or "").strip().upper()
    if not rid:
        return None

    conn = sqlite3.connect(db_path)
    try:
        p_row = conn.execute(
            """
            SELECT pending_id, kind, aset, payload_json, xlsx_path, source_path, warnings_text,
                   status, created_at, COALESCE(reply_chat_id, ''), COALESCE(session, 'default'), COALESCE(sender_label, '')
            FROM opname_pending
            WHERE UPPER(pending_id) = ?
            """,
            (rid,),
        ).fetchone()
        if p_row:
            pending_id, kind, aset, payload_json, xlsx_path, source_path, warnings_text, status, created_at, reply_chat_id, session, sender_label = p_row
            slots = _safe_json_loads(payload_json, [])
            first_sl = slots[0] if slots else {}
            entries = []
            for sl in slots:
                entries.extend(sl.get("entries") or [])
            norm_aset = normalize_asset_code(aset or first_sl.get("aset") or "") or (aset or "PV")
            return {
                "record_type": "PENDING",
                "record_id": pending_id,
                "kind": kind,
                "status": status or "PENDING",
                "aset": norm_aset,
                "wilayah": first_sl.get("wilayah") or (entries[0].get("wilayah") if entries else "W1") or "W1",
                "vendor": first_sl.get("vendor") or (entries[0].get("vendor") if entries else "") or "",
                "minggu": first_sl.get("minggu") or (entries[0].get("minggu") if entries else "M1") or "M1",
                "cycle_key": first_sl.get("cycle_key") or "",
                "slots": slots,
                "entries": entries,
                "source_arch": _safe_json_loads(source_path, {}),
                "xlsx_arch": _safe_json_loads(xlsx_path, {}),
                "warnings": [w.strip() for w in (warnings_text or "").splitlines() if w.strip()],
                "reply_chat_id": reply_chat_id or "",
                "session": session or "default",
                "sender_label": sender_label or "",
                "updated_at": created_at or "",
            }

        s_row = conn.execute(
            """
            SELECT slot_id, cycle_key, aset, wilayah, vendor, minggu, payload_json, source_json, xlsx_json,
                   status, updated_at, COALESCE(reply_chat_id, ''), COALESCE(session, 'default'), COALESCE(sender_label, '')
            FROM opname_slots
            WHERE UPPER(slot_id) = ? AND status = 'ACTIVE'
            """,
            (rid,),
        ).fetchone()
        if s_row:
            slot_id, cycle_key, aset, wilayah, vendor, minggu, payload_json, source_json, xlsx_json, status, updated_at, reply_chat_id, session, sender_label = s_row
            sl = _safe_json_loads(payload_json, {})
            if isinstance(sl, list):
                sl = sl[0] if sl else {}
            entries = sl.get("entries") or []
            norm_aset = normalize_asset_code(aset or sl.get("aset") or "") or (aset or "PV")
            _, warn = check_roster_pairing(norm_aset, vendor, wilayah)
            return {
                "record_type": "SLOT",
                "record_id": slot_id,
                "kind": "SLOT",
                "status": status,
                "aset": norm_aset,
                "wilayah": wilayah or sl.get("wilayah") or "W1",
                "vendor": vendor or sl.get("vendor") or "",
                "minggu": minggu or sl.get("minggu") or "M1",
                "cycle_key": cycle_key or sl.get("cycle_key") or "",
                "slots": [sl] if sl else [],
                "entries": entries,
                "source_arch": _safe_json_loads(source_json, {}),
                "xlsx_arch": _safe_json_loads(xlsx_json, {}),
                "warnings": [warn] if warn else [],
                "reply_chat_id": reply_chat_id or "",
                "session": session or "default",
                "sender_label": sender_label or "",
                "updated_at": updated_at or "",
            }

        # Fallback for pre-upgrade active rows in opname_entries without an opname_slots snapshot
        ent_rows = conn.execute(
            """
            SELECT aset, wilayah, tanggal, lokasi, vendor, item_key, volume, satuan,
                   table_name, created_at, COALESCE(pic, ''), COALESCE(kode_temuan, '-')
            FROM opname_entries
            WHERE UPPER(opname_id) = ? AND status = 'ACTIVE'
            ORDER BY rowid ASC
            """,
            (rid,),
        ).fetchall()
        if not ent_rows:
            return None

        first_aset = normalize_asset_code(ent_rows[0][0]) or ent_rows[0][0]
        first_wil = ent_rows[0][1] or "W1"
        first_vend = ent_rows[0][4] or ""
        first_pic = ent_rows[0][10] or ""
        parsed_slot = _cycle_from_slot_id(rid)
        if parsed_slot:
            cycle_key, cycle_month, cycle_year, minggu = parsed_slot
        else:
            dt_fallback = parse_opname_date_str(ent_rows[0][2]) or datetime.date.today().strftime("%Y-%m-%d")
            cm, cy = resolve_billing_cycle(datetime.datetime.strptime(dt_fallback, "%Y-%m-%d").date())
            cycle_key, cycle_month, cycle_year = f"{cy:04d}-{cm:02d}", cm, cy
            m_wk = re.search(r"\[(M[1-5])\]", first_pic.upper())
            minggu = m_wk.group(1) if m_wk else "M1"

        rebuilt_entries = []
        for aset_v, wil_v, tgl_v, loc_v, vend_v, ik_v, vol_v, sat_v, _, _, _, kode_v in ent_rows:
            boq, _ = resolve_boq_item(first_aset, ik_v, lokasi="" if loc_v == "-" else loc_v, wilayah=wil_v)
            rebuilt_entries.append(
                {
                    "tanggal": tgl_v,
                    "minggu": minggu,
                    "kode_temuan": kode_v or "-",
                    "wilayah": wil_v,
                    "vendor": vend_v,
                    "lokasi": loc_v or "-",
                    "jalur_lajur": "-",
                    "item_key": ik_v,
                    "keyword": boq.keyword if boq else ik_v,
                    "uraian": boq.uraian if boq else "",
                    "satuan": sat_v or (boq.satuan if boq else ""),
                    "p": None,
                    "l": None,
                    "t": None,
                    "jml": None,
                    "vol_vendor": None,
                    "volume": float(vol_v),
                    "material_status": "",
                    "keterangan": "",
                }
            )

        arc_rows = conn.execute(
            """
            SELECT source_type, file_path, COALESCE(item_id, ''), COALESCE(web_url, '')
            FROM opname_archives
            WHERE UPPER(slot_id) = ?
            ORDER BY archive_id DESC
            """,
            (rid,),
        ).fetchall()
        src_arch: dict[str, str] = {}
        xls_arch: dict[str, str] = {}
        for src_t, fname, itm_id, w_url in arc_rows:
            if src_t == "SCAN_SRC" and not src_arch:
                ext_l = fname.lower()
                mime = "application/pdf" if ext_l.endswith(".pdf") else "image/jpeg"
                src_arch = {"filename": fname, "item_id": itm_id, "web_url": w_url, "mimetype": mime}
            elif src_t in ("XLSX", "WEB_EDITOR") and not xls_arch:
                xls_arch = {"filename": fname, "item_id": itm_id, "web_url": w_url, "mimetype": _XLSX_MIME}

        _, warn = check_roster_pairing(first_aset, first_vend, first_wil)
        return {
            "record_type": "SLOT",
            "record_id": rid,
            "kind": "SLOT_LEGACY",
            "status": "ACTIVE",
            "aset": first_aset,
            "wilayah": first_wil,
            "vendor": first_vend,
            "minggu": minggu,
            "cycle_key": cycle_key,
            "slots": [
                {
                    "slot_id": rid,
                    "cycle_key": cycle_key,
                    "cycle_month": cycle_month,
                    "cycle_year": cycle_year,
                    "aset": first_aset,
                    "wilayah": first_wil,
                    "vendor": first_vend,
                    "minggu": minggu,
                    "table_name": ent_rows[0][8],
                    "entries": rebuilt_entries,
                }
            ],
            "entries": rebuilt_entries,
            "source_arch": src_arch,
            "xlsx_arch": xls_arch,
            "warnings": [warn] if warn else [],
            "reply_chat_id": "",
            "session": "default",
            "sender_label": re.sub(r"\s*\[M[1-5]\]\s*$", "", first_pic).strip(),
            "updated_at": ent_rows[0][9] or "",
        }
    finally:
        conn.close()


def _build_boq_options_for_asset(aset: str, existing_entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    canon = normalize_asset_code(aset) or "PV"
    items = _items_for_asset_boq(canon)
    seen: set[str] = set()
    options: list[dict[str, str]] = []
    for it in items:
        if it.item_key in seen:
            continue
        seen.add(it.item_key)
        options.append(
            {
                "item_key": it.item_key,
                "keyword": it.keyword,
                "uraian": it.uraian,
                "satuan": it.satuan,
            }
        )
    for ent in existing_entries:
        ik = str(ent.get("item_key") or "").strip()
        if ik and ik not in seen:
            seen.add(ik)
            options.append(
                {
                    "item_key": ik,
                    "keyword": str(ent.get("keyword") or ik),
                    "uraian": str(ent.get("uraian") or ""),
                    "satuan": str(ent.get("satuan") or ""),
                }
            )
    return options


def _validate_and_build_slots(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []

    raw_aset = str(payload.get("aset") or "").strip()
    aset = normalize_asset_code(raw_aset)
    if not aset or aset not in ASSET_TO_TABLE:
        errors.append({"row": 0, "field": "aset", "message": "Aset pekerjaan tidak valid."})

    hdr_wil = str(payload.get("wilayah") or "").strip().upper()
    if hdr_wil not in ("W1", "W2"):
        errors.append({"row": 0, "field": "wilayah", "message": "Wilayah wajib W1 atau W2."})

    raw_vend = str(payload.get("vendor") or "").strip()
    canon_vend = ""
    if aset:
        v_ok, v_canon, v_err = normalize_vendor(raw_vend, aset)
        if not v_ok or not v_canon:
            errors.append({"row": 0, "field": "vendor", "message": v_err or "Vendor tidak valid."})
        else:
            canon_vend = v_canon

    hdr_minggu = str(payload.get("minggu") or "").strip().upper()
    if not re.fullmatch(r"M[1-5]", hdr_minggu):
        errors.append({"row": 0, "field": "minggu", "message": "Minggu wajib bernilai M1 sampai M5."})

    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list) or len(raw_entries) == 0:
        errors.append({"row": 0, "field": "entries", "message": "Minimal 1 baris pekerjaan wajib diisi."})
        return [], [], [], errors

    parsed_entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    warn_seen: set[str] = set()

    for idx, raw_r in enumerate(raw_entries, start=1):
        if not isinstance(raw_r, dict):
            errors.append({"row": idx, "field": "row", "message": "Format baris tidak valid."})
            continue

        row_has_error = False
        parsed_date = parse_opname_date_str(str(raw_r.get("tanggal") or ""))
        if not parsed_date:
            errors.append({"row": idx, "field": "tanggal", "message": "Tanggal wajib diisi (format YYYY-MM-DD)."})
            row_has_error = True

        loc = str(raw_r.get("lokasi") or "").strip()
        row_wil = hdr_wil if hdr_wil in ("W1", "W2") else "W1"
        if loc and loc != "-":
            loc_hint = f"{loc} {row_wil}".strip()
            w_ok, loc_wil, _, w_err = resolve_wilayah(loc_hint)
            if not w_ok or not loc_wil:
                errors.append({"row": idx, "field": "lokasi", "message": w_err})
                row_has_error = True
            else:
                row_wil = loc_wil

        boq_item = None
        if aset:
            raw_item = str(raw_r.get("item_key") or raw_r.get("keyword") or "").strip()
            boq_item, b_err = resolve_boq_item(
                aset,
                raw_item,
                lokasi="" if loc == "-" else loc,
                wilayah=row_wil,
            )
            if not boq_item:
                errors.append({"row": idx, "field": "item_key", "message": b_err})
                row_has_error = True

        dim_vals: dict[str, float | None] = {}
        for d_key in ("p", "l", "t", "jml", "vol_vendor"):
            d_ok, d_num = _to_opt_float(raw_r.get(d_key))
            if not d_ok:
                errors.append({"row": idx, "field": d_key, "message": f"Kolom {d_key.upper()} harus berupa angka."})
                row_has_error = True
            dim_vals[d_key] = d_num

        vol_ok, vol_num = _to_opt_float(raw_r.get("volume"))
        if not vol_ok or vol_num is None or vol_num <= 0:
            errors.append({"row": idx, "field": "volume", "message": "Vol. Opname wajib lebih besar dari 0."})
            row_has_error = True

        if row_has_error or errors:
            continue

        assert aset and canon_vend and parsed_date and boq_item and vol_num is not None
        r_ok, r_warn = check_roster_pairing(aset, canon_vend, row_wil)
        if not r_ok and r_warn not in warn_seen:
            warn_seen.add(r_warn)
            warnings.append(r_warn)

        jal_p = str(raw_r.get("jalur") or "").strip()
        laj_p = str(raw_r.get("lajur") or "").strip()
        if jal_p or laj_p:
            jalur_lajur = " ".join(p for p in (jal_p, laj_p) if p)
        else:
            jalur_lajur = str(raw_r.get("jalur_lajur") or "-").strip() or "-"

        parsed_entries.append(
            {
                "tanggal": parsed_date,
                "minggu": hdr_minggu,
                "kode_temuan": str(raw_r.get("kode_temuan") or "-").strip() or "-",
                "wilayah": row_wil,
                "vendor": canon_vend,
                "lokasi": loc or "-",
                "jalur_lajur": jalur_lajur,
                "item_key": boq_item.item_key,
                "keyword": boq_item.keyword,
                "uraian": boq_item.uraian,
                "satuan": boq_item.satuan,
                "p": dim_vals["p"],
                "l": dim_vals["l"],
                "t": dim_vals["t"],
                "jml": dim_vals["jml"],
                "vol_vendor": dim_vals["vol_vendor"],
                "volume": round(vol_num, 4),
                "material_status": str(raw_r.get("material_status") or "").strip(),
                "keterangan": str(raw_r.get("keterangan") or "").strip(),
            }
        )

    if errors:
        return [], [], warnings, errors

    assert aset
    _, table_name, _ = ASSET_TO_TABLE[aset]
    slots_by_id: dict[str, dict[str, Any]] = {}
    for ent in parsed_entries:
        dt_obj = datetime.datetime.strptime(ent["tanggal"], "%Y-%m-%d").date()
        cm, cy = resolve_billing_cycle(dt_obj)
        ck = f"{cy:04d}-{cm:02d}"
        sid = f"XLS-{cy % 100:02d}{cm:02d}-{aset}-{ent['wilayah']}-{ent['vendor']}-{ent['minggu']}"
        if sid not in slots_by_id:
            slots_by_id[sid] = {
                "slot_id": sid,
                "cycle_key": ck,
                "cycle_month": cm,
                "cycle_year": cy,
                "aset": aset,
                "wilayah": ent["wilayah"],
                "vendor": ent["vendor"],
                "minggu": ent["minggu"],
                "table_name": table_name,
                "entries": [],
            }
        slots_by_id[sid]["entries"].append(ent)

    return list(slots_by_id.values()), parsed_entries, warnings, []


def _lookup_workbook_drive_item(db_path: str, cycle_key: str) -> tuple[str, str] | None:
    if not cycle_key:
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT drive_id, item_id FROM opname_workbooks WHERE cycle_key = ?",
            (cycle_key,),
        ).fetchone()
    finally:
        conn.close()
    if row and row[0] and row[1]:
        return row[0], row[1]
    return None


def _cleanup_replaced_slot(
    db_path: str,
    old_slot_id: str,
    old_aset: str,
    old_cycle_key: str,
    delete_slot_rows_fn: Callable[..., int],
) -> None:
    _, old_table_name, _ = ASSET_TO_TABLE.get(old_aset, ("", "TBL_LOG_PV", ""))
    target_di = _lookup_workbook_drive_item(db_path, old_cycle_key)
    delete_slot_rows_fn(
        settings.OPNAME_EXCEL_SHARE_LINK,
        old_table_name,
        old_slot_id,
        target_drive_item=target_di,
    )
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE opname_entries SET status = 'REPLACED' WHERE UPPER(opname_id) = ? AND status = 'ACTIVE'",
            (old_slot_id.upper(),),
        )
        conn.execute(
            "UPDATE opname_slots SET status = 'REPLACED', updated_at = ? WHERE UPPER(slot_id) = ? AND status = 'ACTIVE'",
            (now_str, old_slot_id.upper()),
        )
        conn.commit()
    finally:
        conn.close()


def create_opname_web_router(deps: dict[str, Any]) -> APIRouter:
    """Create FastAPI APIRouter for the phone/PC Opname web review & slot editor."""
    router = APIRouter()

    def _db_url() -> str:
        return str(deps["get_db_url"]())

    @router.get("/opname", response_class=HTMLResponse)
    def opname_list_page(token: str = Query("")):
        if not verify_opname_token("DASHBOARD", token):
            return HTMLResponse(
                content=render_forbidden_page_html("Token dashboard tidak valid."),
                status_code=403,
            )
        return HTMLResponse(content=render_opname_list_page_html(token))

    @router.get("/api/opname/slots")
    def api_list_opname_slots(
        token: str = Query(""),
        cycle: str = Query(""),
        aset: str = Query(""),
    ):
        if not verify_opname_token("DASHBOARD", token):
            raise HTTPException(status_code=403, detail="Token dashboard tidak valid.")

        filter_aset = normalize_asset_code(aset) if aset.strip() else ""
        default_m, default_y = resolve_billing_cycle(datetime.date.today())
        default_cycle = f"{default_y:04d}-{default_m:02d}"

        db_path = _db_url()
        conn = sqlite3.connect(db_path)
        try:
            cycle_set: set[str] = {default_cycle}
            for (ck,) in conn.execute("SELECT cycle_key FROM opname_workbooks").fetchall():
                if ck:
                    cycle_set.add(ck)
            cycles_with_slots: set[str] = set()
            for (ck,) in conn.execute("SELECT DISTINCT cycle_key FROM opname_slots WHERE status = 'ACTIVE'").fetchall():
                if ck:
                    cycle_set.add(ck)
                    cycles_with_slots.add(ck)
            for (op_id,) in conn.execute(
                "SELECT DISTINCT opname_id FROM opname_entries WHERE status = 'ACTIVE'"
            ).fetchall():
                parsed = _cycle_from_slot_id(op_id)
                if parsed:
                    cycle_set.add(parsed[0])
                    cycles_with_slots.add(parsed[0])

            pending_rows = conn.execute(
                """
                SELECT pending_id, kind, aset, payload_json, warnings_text, created_at
                FROM opname_pending
                WHERE status = 'PENDING'
                ORDER BY created_at DESC
                """
            ).fetchall()
            pending_list: list[dict[str, Any]] = []
            for p_id, kind, p_aset, p_json, warn_txt, p_created in pending_rows:
                norm_a = normalize_asset_code(p_aset) or p_aset
                if filter_aset and norm_a != filter_aset:
                    continue
                slots_p = _safe_json_loads(p_json, [])
                first_s = slots_p[0] if slots_p else {}
                row_cnt = sum(len(s.get("entries") or []) for s in slots_p)
                ck = first_s.get("cycle_key") or ""
                if ck:
                    cycle_set.add(ck)
                pending_list.append(
                    {
                        "pending_id": p_id,
                        "kind": kind,
                        "aset": norm_a,
                        "wilayah": first_s.get("wilayah") or "",
                        "vendor": first_s.get("vendor") or "",
                        "minggu": first_s.get("minggu") or "",
                        "cycle_key": ck,
                        "row_count": row_cnt,
                        "warnings": [w for w in (warn_txt or "").splitlines() if w.strip()],
                        "created_at": p_created or "",
                        "review_url": f"/review/{p_id}?token={make_opname_token(p_id)}",
                    }
                )

            cycles = sorted(cycle_set, reverse=True)
            if cycle.strip():
                active_cycle = cycle.strip()
            elif default_cycle in cycles_with_slots or not cycles_with_slots:
                active_cycle = default_cycle
            else:
                active_cycle = sorted(cycles_with_slots, reverse=True)[0]
            if active_cycle not in cycle_set:
                cycles = sorted(cycle_set | {active_cycle}, reverse=True)

            # Build archive web_url lookup by slot_id
            arc_urls: dict[str, str] = {}
            for s_id, w_url in conn.execute(
                """
                SELECT slot_id, web_url
                FROM opname_archives
                WHERE source_type IN ('XLSX', 'WEB_EDITOR') AND COALESCE(web_url, '') != ''
                ORDER BY archive_id DESC
                """
            ).fetchall():
                key_u = (s_id or "").upper()
                if key_u and key_u not in arc_urls:
                    arc_urls[key_u] = w_url

            slots_map: dict[str, dict[str, Any]] = {}
            for s_id, ck, s_aset, s_wil, s_vend, s_wk, p_json, x_json, upd_at in conn.execute(
                """
                SELECT slot_id, cycle_key, aset, wilayah, vendor, minggu, payload_json, xlsx_json, updated_at
                FROM opname_slots
                WHERE cycle_key = ? AND status = 'ACTIVE'
                ORDER BY updated_at DESC, slot_id ASC
                """,
                (active_cycle,),
            ).fetchall():
                norm_a = normalize_asset_code(s_aset) or s_aset
                sl_obj = _safe_json_loads(p_json, {})
                if isinstance(sl_obj, list):
                    sl_obj = sl_obj[0] if sl_obj else {}
                xls_obj = _safe_json_loads(x_json, {})
                slots_map[s_id.upper()] = {
                    "slot_id": s_id,
                    "cycle_key": ck,
                    "aset": norm_a,
                    "wilayah": s_wil,
                    "vendor": s_vend,
                    "minggu": s_wk,
                    "row_count": len(sl_obj.get("entries") or []),
                    "updated_at": upd_at or "",
                    "xlsx_web_url": xls_obj.get("web_url") or arc_urls.get(s_id.upper(), ""),
                    "review_url": f"/review/{s_id}?token={make_opname_token(s_id)}",
                }

            # Merge fallback active slots from opname_entries (pre-migration rows)
            cy_y, cy_m = map(int, active_cycle.split("-"))
            yy_mm = f"{cy_y % 100:02d}{cy_m:02d}"
            for s_id, e_aset, e_wil, e_vend, cnt, last_ts in conn.execute(
                """
                SELECT opname_id, MAX(aset), MAX(wilayah), MAX(vendor), COUNT(*), MAX(created_at)
                FROM opname_entries
                WHERE status = 'ACTIVE' AND opname_id LIKE ?
                GROUP BY opname_id
                """,
                (f"XLS-{yy_mm}-%",),
            ).fetchall():
                u_id = (s_id or "").upper()
                if u_id not in slots_map:
                    parsed = _cycle_from_slot_id(u_id)
                    wk = parsed[3] if parsed else u_id.rsplit("-", 1)[-1]
                    norm_a = normalize_asset_code(e_aset) or e_aset
                    slots_map[u_id] = {
                        "slot_id": s_id,
                        "cycle_key": active_cycle,
                        "aset": norm_a,
                        "wilayah": e_wil,
                        "vendor": e_vend,
                        "minggu": wk,
                        "row_count": int(cnt),
                        "updated_at": last_ts or "",
                        "xlsx_web_url": arc_urls.get(u_id, ""),
                        "review_url": f"/review/{s_id}?token={make_opname_token(s_id)}",
                    }
        finally:
            conn.close()

        active_pairs = {(v["aset"], v["vendor"], v["wilayah"]) for v in slots_map.values()}
        active_roster = get_active_roster(db_path)
        roster_done = sum(1 for item in active_roster if item in active_pairs)

        filtered_slots = [
            v for v in slots_map.values() if not filter_aset or v["aset"] == filter_aset
        ]
        filtered_slots.sort(key=lambda item: (item["aset"], item["wilayah"], item["vendor"], item["minggu"]))

        return {
            "cycles": cycles,
            "active_cycle": active_cycle,
            "roster_progress": {"done": roster_done, "total": len(active_roster)},
            "pending": pending_list,
            "slots": filtered_slots,
        }

    @router.get("/review/{record_id}", response_class=HTMLResponse)
    def review_page(record_id: str, token: str = Query("")):
        rid = (record_id or "").strip().upper()
        if not verify_opname_token(rid, token):
            return HTMLResponse(
                content=render_forbidden_page_html("Token review tidak valid."),
                status_code=403,
            )
        dash_url = f"/opname?token={make_opname_token('DASHBOARD')}"
        return HTMLResponse(content=render_review_page_html(rid, token, dash_url))

    @router.get("/api/opname/review/{record_id}")
    def api_get_review(record_id: str, token: str = Query("")):
        rid = (record_id or "").strip().upper()
        if not verify_opname_token(rid, token):
            raise HTTPException(status_code=403, detail="Token review tidak valid.")

        record = _load_record(_db_url(), rid)
        if not record:
            raise HTTPException(
                status_code=404,
                detail=f"Data '{rid}' tidak ditemukan atau sudah dibatalkan.",
            )

        aset = record["aset"]
        entries = record["entries"]
        source_arch = record.get("source_arch") or {}
        has_media = bool(source_arch.get("item_id"))
        src_name = str(source_arch.get("filename") or "").lower()
        is_pdf = source_arch.get("mimetype") == "application/pdf" or src_name.endswith(".pdf")

        return {
            "record_type": record["record_type"],
            "record_id": record["record_id"],
            "kind": record["kind"],
            "status": record["status"],
            "aset": aset,
            "aset_title": ASSET_TITLES.get(aset, aset),
            "wilayah": record["wilayah"],
            "vendor": record["vendor"],
            "minggu": record["minggu"],
            "cycle_key": record["cycle_key"],
            "default_date": datetime.date.today().strftime("%Y-%m-%d"),
            "entries": entries,
            "boq_options": _build_boq_options_for_asset(aset, entries),
            "vendor_options": get_allowed_vendors_for_asset(aset, _db_url()),
            "official_roster": [list(t) for t in get_active_roster(_db_url())],
            "warnings": record["warnings"],
            "has_media": has_media,
            "is_pdf": is_pdf,
            "media_url": f"/api/opname/media/{record['record_id']}?token={token}" if has_media else "",
            "xlsx_web_url": (record.get("xlsx_arch") or {}).get("web_url") or "",
        }

    @router.get("/api/opname/media/{record_id}")
    def api_get_review_media(
        record_id: str,
        token: str = Query(""),
        page: int = Query(0, ge=0),
        raw: int = Query(0),
    ):
        rid = (record_id or "").strip().upper()
        if not verify_opname_token(rid, token):
            raise HTTPException(status_code=403, detail="Token media tidak valid.")

        record = _load_record(_db_url(), rid)
        if not record:
            raise HTTPException(status_code=404, detail=f"Data '{rid}' tidak ditemukan.")

        source_arch = record.get("source_arch") or {}
        item_id = source_arch.get("item_id") or ""
        if not item_id:
            raise HTTPException(status_code=404, detail="Lampiran scan tidak tersedia untuk data ini.")

        try:
            raw_bytes = deps["download_onedrive"](item_id)
        except Exception as dl_err:
            raise HTTPException(status_code=502, detail=f"Gagal mengunduh scan dari OneDrive: {dl_err}")

        filename = str(source_arch.get("filename") or f"{rid}_scan")
        mime = str(source_arch.get("mimetype") or "")
        is_pdf = mime == "application/pdf" or filename.lower().endswith(".pdf") or raw_bytes[:4] == b"%PDF"

        if raw == 1:
            dl_mime = "application/pdf" if is_pdf else (mime or "image/jpeg")
            safe_fname = re.sub(r"[^A-Za-z0-9_.\-]+", "_", filename)
            return Response(
                content=raw_bytes,
                media_type=dl_mime,
                headers={"Content-Disposition": f'inline; filename="{safe_fname}"', "Cache-Control": "no-store"},
            )

        if is_pdf:
            try:
                pages = deps["render_pdf_pages"](raw_bytes)
            except Exception as pdf_err:
                raise HTTPException(status_code=500, detail=f"Gagal merender halaman PDF: {pdf_err}")
            if not pages:
                raise HTTPException(status_code=500, detail="PDF tidak memiliki halaman yang dapat ditampilkan.")
            idx = max(0, min(page, len(pages) - 1))
            return Response(
                content=pages[idx],
                media_type="image/jpeg",
                headers={"X-PDF-Pages": str(len(pages)), "Cache-Control": "no-store"},
            )

        return Response(
            content=raw_bytes,
            media_type=mime or "image/jpeg",
            headers={"X-PDF-Pages": "1", "Cache-Control": "no-store"},
        )

    @router.post("/api/opname/review/{record_id}/save")
    async def api_save_review(record_id: str, request: Request, token: str = Query("")):
        rid = (record_id or "").strip().upper()
        if not verify_opname_token(rid, token):
            raise HTTPException(status_code=403, detail="Token review tidak valid.")

        db_path = _db_url()
        record = _load_record(db_path, rid)
        if not record:
            raise HTTPException(
                status_code=404,
                detail=f"Data '{rid}' tidak ditemukan atau sudah dibatalkan.",
            )

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Payload JSON tidak valid.")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Payload JSON harus berupa objek.")

        if not body.get("aset"):
            body["aset"] = record["aset"]

        slots_data, flat_entries, warnings, errors = _validate_and_build_slots(body)
        if errors:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": f"Terdapat {len(errors)} kesalahan input yang perlu diperbaiki.",
                    "errors": errors,
                },
            )

        first_slot = slots_data[0]
        aset = first_slot["aset"]
        xlsx_name = f"{aset}_{first_slot['wilayah']}_{first_slot['vendor']}_{first_slot['minggu']}_{rid}.xlsx"
        xlsx_bytes = build_prefilled_standard_xlsx(
            aset,
            int(first_slot["cycle_month"]),
            int(first_slot["cycle_year"]),
            flat_entries,
        )

        try:
            xlsx_arch_info = deps["archive_file"](
                first_slot["cycle_key"],
                aset,
                xlsx_name,
                xlsx_bytes,
                _XLSX_MIME,
            )
        except Exception as arch_err:
            raise HTTPException(status_code=502, detail=f"Gagal mengunggah file Excel ke OneDrive: {arch_err}")

        archive_items: list[tuple[str, dict[str, Any]]] = []
        source_arch = record.get("source_arch") or {}
        if source_arch and (source_arch.get("item_id") or source_arch.get("web_url")):
            archive_items.append(("SCAN_SRC", source_arch))
        archive_items.append(("WEB_EDITOR", xlsx_arch_info))

        new_slot_ids = {sl["slot_id"] for sl in slots_data}
        # Remove orphaned rows in DATA_UNTUK_VOL if header metadata rename changed the target slot ID
        try:
            if record["record_type"] == "SLOT" and rid not in new_slot_ids:
                _cleanup_replaced_slot(
                    db_path,
                    rid,
                    record["aset"],
                    record["cycle_key"],
                    deps["delete_slot_rows"],
                )
            elif record["record_type"] == "PENDING" and record["status"] == "CONFIRMED":
                for prev_sl in record.get("slots") or []:
                    prev_sid = str(prev_sl.get("slot_id") or "").strip().upper()
                    if prev_sid and prev_sid not in new_slot_ids:
                        _cleanup_replaced_slot(
                            db_path,
                            prev_sid,
                            str(prev_sl.get("aset") or record["aset"]),
                            str(prev_sl.get("cycle_key") or ""),
                            deps["delete_slot_rows"],
                        )
        except Exception as del_err:
            raise HTTPException(
                status_code=502,
                detail=f"Gagal membersihkan baris slot lama di OneDrive: {del_err}",
            )

        sender_label = record.get("sender_label") or "WebEditor"
        reply_chat_id = record.get("reply_chat_id") or ""
        session_name = record.get("session") or "default"

        try:
            results = deps["commit_slots"](
                slots_data,
                sender_label,
                f"WEB_EDITOR:{rid}",
                archive_items,
                reply_chat_id=reply_chat_id,
                session=session_name,
            )
        except Exception as commit_err:
            raise HTTPException(
                status_code=502,
                detail=f"Gagal menyimpan baris ke DATA_UNTUK_VOL di OneDrive: {commit_err}",
            )

        if record["record_type"] == "PENDING":
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "UPDATE opname_pending SET status = 'CONFIRMED', payload_json = ?, xlsx_path = ? WHERE UPPER(pending_id) = ?",
                    (json.dumps(slots_data), json.dumps(xlsx_arch_info), rid),
                )
                conn.commit()
            finally:
                conn.close()

        wa_notified = False
        if reply_chat_id:
            try:
                msg = deps["format_commit_reply"](results, f"Web Editor {rid}")
                deps["send_whatsapp"](reply_chat_id, msg, session_name)
                wa_notified = True
            except Exception as wa_err:
                print(f"Warning: Gagal kirim notifikasi Web Editor ke WhatsApp ({reply_chat_id}): {wa_err}")

        slot_urls = {
            res["slot_id"]: f"/review/{res['slot_id']}?token={make_opname_token(res['slot_id'])}"
            for res in results
        }
        return {
            "ok": True,
            "results": results,
            "warnings": warnings,
            "xlsx_url": xlsx_arch_info.get("web_url") or "",
            "whatsapp_notified": wa_notified,
            "slot_urls": slot_urls,
        }

    def _sync_roster_best_effort(db_path: str) -> tuple[bool, str]:
        upload_fn = deps.get("upload_private_onedrive")
        if not upload_fn:
            return False, "Tersimpan lokal di SQLite (sync OneDrive belum terhubung)."
        return push_roster_to_onedrive(db_path, upload_fn)

    @router.get("/api/opname/roster")
    def api_get_roster(token: str = Query("")):
        if not verify_opname_token("DASHBOARD", token):
            raise HTTPException(status_code=403, detail="Token dashboard tidak valid.")
        data = export_roster_payload(_db_url())
        data["valid_assets"] = [{"code": a, "title": ASSET_TITLES.get(a, a)} for a in VALID_OPNAME_ASSETS]
        data["onedrive_path"] = f"{ROSTER_CONFIG_FOLDER}/{ROSTER_CONFIG_FILENAME}"
        return data

    @router.post("/api/opname/roster/slot")
    async def api_upsert_roster_slot(request: Request, token: str = Query("")):
        if not verify_opname_token("DASHBOARD", token):
            raise HTTPException(status_code=403, detail="Token dashboard tidak valid.")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Payload JSON tidak valid.")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Payload JSON harus berupa objek.")

        db_path = _db_url()
        try:
            slot_res = upsert_roster_slot(
                db_path,
                str(body.get("aset") or ""),
                str(body.get("vendor") or ""),
                str(body.get("wilayah") or ""),
                active=bool(body.get("active", True)),
                aliases=body.get("aliases"),
            )
        except ValueError as val_err:
            raise HTTPException(status_code=422, detail=str(val_err))

        synced, sync_note = _sync_roster_best_effort(db_path)
        return {
            "ok": True,
            "slot": slot_res,
            "onedrive_synced": synced,
            "sync_note": sync_note,
            "roster": export_roster_payload(db_path),
        }

    @router.post("/api/opname/roster/slot/toggle")
    async def api_toggle_roster_slot(request: Request, token: str = Query("")):
        if not verify_opname_token("DASHBOARD", token):
            raise HTTPException(status_code=403, detail="Token dashboard tidak valid.")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Payload JSON tidak valid.")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Payload JSON harus berupa objek.")

        db_path = _db_url()
        try:
            ok = set_roster_slot_active(
                db_path,
                str(body.get("aset") or ""),
                str(body.get("vendor") or ""),
                str(body.get("wilayah") or ""),
                bool(body.get("active", True)),
            )
        except ValueError as val_err:
            raise HTTPException(status_code=422, detail=str(val_err))

        if not ok:
            raise HTTPException(status_code=404, detail="Slot roster tidak ditemukan.")
        synced, sync_note = _sync_roster_best_effort(db_path)
        return {
            "ok": True,
            "onedrive_synced": synced,
            "sync_note": sync_note,
            "roster": export_roster_payload(db_path),
        }

    @router.post("/api/opname/roster/vendor/toggle")
    async def api_toggle_vendor(request: Request, token: str = Query("")):
        if not verify_opname_token("DASHBOARD", token):
            raise HTTPException(status_code=403, detail="Token dashboard tidak valid.")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Payload JSON tidak valid.")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Payload JSON harus berupa objek.")

        db_path = _db_url()
        try:
            ok = set_vendor_active(db_path, str(body.get("code") or ""), bool(body.get("active", True)))
        except ValueError as val_err:
            raise HTTPException(status_code=422, detail=str(val_err))

        if not ok:
            raise HTTPException(status_code=404, detail="Kode vendor tidak ditemukan.")
        synced, sync_note = _sync_roster_best_effort(db_path)
        return {
            "ok": True,
            "onedrive_synced": synced,
            "sync_note": sync_note,
            "roster": export_roster_payload(db_path),
        }

    @router.get("/api/opname/roster/export")
    def api_export_roster(token: str = Query("")):
        if not verify_opname_token("DASHBOARD", token):
            raise HTTPException(status_code=403, detail="Token dashboard tidak valid.")
        payload = export_roster_payload(_db_url())
        raw = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        return Response(
            content=raw,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{ROSTER_CONFIG_FILENAME}"',
                "Cache-Control": "no-store",
            },
        )

    @router.post("/api/opname/roster/import")
    async def api_import_roster(request: Request, token: str = Query("")):
        if not verify_opname_token("DASHBOARD", token):
            raise HTTPException(status_code=403, detail="Token dashboard tidak valid.")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="File JSON tidak valid.")
        db_path = _db_url()
        try:
            imported = import_roster_payload(db_path, body, mark_local_mod=True)
        except ValueError as val_err:
            raise HTTPException(status_code=422, detail=str(val_err))
        synced, sync_note = _sync_roster_best_effort(db_path)
        return {
            "ok": True,
            "onedrive_synced": synced,
            "sync_note": sync_note,
            "roster": imported,
        }

    @router.post("/api/opname/roster/sync-onedrive")
    def api_sync_roster_from_onedrive(token: str = Query("")):
        if not verify_opname_token("DASHBOARD", token):
            raise HTTPException(status_code=403, detail="Token dashboard tidak valid.")
        dl_fn = deps.get("download_path_onedrive")
        if not dl_fn:
            raise HTTPException(status_code=501, detail="Sinkronisasi path OneDrive belum terhubung.")
        db_path = _db_url()
        ok, note = pull_roster_from_onedrive(db_path, dl_fn, only_if_unmodified=False)
        if not ok:
            status_code = 404 if "belum ada" in note.lower() else 502
            raise HTTPException(status_code=status_code, detail=note)
        return {
            "ok": True,
            "sync_note": note,
            "roster": export_roster_payload(db_path),
        }

    return router
