from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
from typing import Any, Callable

ROSTER_CONFIG_FOLDER = "Arsip Opname/_config"
ROSTER_CONFIG_FILENAME = "opname_roster.json"
ROSTER_SCHEMA_VERSION = 1


def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_vendor_code(raw: str) -> str:
    """Normalize a canonical vendor short code (2-20 uppercase alphanumeric chars)."""
    s = re.sub(r"[^A-Za-z0-9 ]+", " ", (raw or "").upper())
    s = re.sub(r"\b(?:PT|CV|UD|KOPERASI)\b", " ", s)
    code = re.sub(r"[^A-Z0-9]", "", s)
    if len(code) < 2 or len(code) > 20:
        raise ValueError("Kode vendor harus 2 sampai 20 huruf/angka (contoh: MIJ, KARYA).")
    return code


def _normalize_alias_token(raw: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 ]+", " ", (raw or "").upper())
    s = re.sub(r"\b(?:PT|CV|UD|KOPERASI)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_aliases_input(code: str, raw_aliases: Any) -> list[str]:
    items: list[str] = [code]
    if isinstance(raw_aliases, str):
        parts = re.split(r"[,;\n]+", raw_aliases)
    elif isinstance(raw_aliases, (list, tuple)):
        parts = [str(x) for x in raw_aliases]
    else:
        parts = []
    seen = {code}
    for part in parts:
        cleaned = _normalize_alias_token(part)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            items.append(cleaned)
    return items


def _read_db_if_ready(db_path: str | None) -> sqlite3.Connection | None:
    if not db_path:
        from config import settings
        db_path = settings.DB_URL
    if not db_path or db_path == ":memory:" or not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        has_tbl = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='opname_roster'"
        ).fetchone()
        if not has_tbl:
            conn.close()
            return None
        return conn
    except Exception:
        return None


def _seed_defaults_if_empty(conn: sqlite3.Connection) -> None:
    from services.opname_catalog import OFFICIAL_VENDOR_ROSTER, VENDOR_ALIASES

    v_cnt = conn.execute("SELECT COUNT(*) FROM opname_vendors").fetchone()[0]
    r_cnt = conn.execute("SELECT COUNT(*) FROM opname_roster").fetchone()[0]
    now = _now_str()

    if v_cnt == 0:
        aliases_by_code: dict[str, list[str]] = {}
        for alias, target in VENDOR_ALIASES.items():
            lst = aliases_by_code.setdefault(target, [target])
            norm_a = _normalize_alias_token(alias)
            if norm_a and norm_a not in lst:
                lst.append(norm_a)
        for code, aliases in sorted(aliases_by_code.items()):
            conn.execute(
                "INSERT OR IGNORE INTO opname_vendors (code, aliases_json, active, updated_at) VALUES (?, ?, 1, ?)",
                (code, json.dumps(aliases), now),
            )

    if r_cnt == 0:
        for aset, vendor, wilayah in OFFICIAL_VENDOR_ROSTER:
            conn.execute(
                "INSERT OR IGNORE INTO opname_roster (aset, vendor, wilayah, active, updated_at) VALUES (?, ?, ?, 1, ?)",
                (aset, vendor, wilayah, now),
            )


def ensure_roster_tables(db_path: str) -> None:
    """Create portable vendor/roster tables and seed defaults once on an empty DB."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS opname_vendors (
                code TEXT PRIMARY KEY,
                aliases_json TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS opname_roster (
                aset TEXT NOT NULL,
                vendor TEXT NOT NULL,
                wilayah TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (aset, vendor, wilayah)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS opname_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        _seed_defaults_if_empty(conn)
        conn.commit()
    finally:
        conn.close()


def _mark_modified_locally(conn: sqlite3.Connection, now: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO opname_meta (key, value, updated_at) VALUES ('roster_modified_locally', '1', ?)",
        (now,),
    )


def get_vendor_alias_map(db_path: str | None = None) -> dict[str, str]:
    from services.opname_catalog import VENDOR_ALIASES

    conn = _read_db_if_ready(db_path)
    if conn is None:
        return dict(VENDOR_ALIASES)

    try:
        rows = conn.execute(
            "SELECT code, aliases_json, active FROM opname_vendors ORDER BY active ASC, code ASC"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return dict(VENDOR_ALIASES)

    alias_map: dict[str, str] = {}
    for code, aliases_json, _active in rows:
        alias_map[code] = code
        try:
            aliases = json.loads(aliases_json or "[]")
        except Exception:
            aliases = []
        for al in aliases:
            tok = _normalize_alias_token(str(al))
            if tok:
                alias_map[tok] = code
    return alias_map


def get_active_roster(db_path: str | None = None) -> list[tuple[str, str, str]]:
    from services.opname_catalog import OFFICIAL_VENDOR_ROSTER, VALID_OPNAME_ASSETS

    conn = _read_db_if_ready(db_path)
    if conn is None:
        return list(OFFICIAL_VENDOR_ROSTER)

    try:
        rows = conn.execute(
            """
            SELECT r.aset, r.vendor, r.wilayah
            FROM opname_roster r
            JOIN opname_vendors v ON v.code = r.vendor
            WHERE r.active = 1 AND v.active = 1
            """
        ).fetchall()
    finally:
        conn.close()

    asset_rank = {a: i for i, a in enumerate(VALID_OPNAME_ASSETS)}
    return sorted(
        [(str(a), str(v), str(w)) for a, v, w in rows],
        key=lambda t: (asset_rank.get(t[0], 99), t[2], t[1]),
    )


def get_allowed_vendors_for_asset(aset: str, db_path: str | None = None) -> list[str]:
    from services.opname_catalog import ALLOWED_VENDORS_BY_ASSET, normalize_asset_code

    canon_aset = normalize_asset_code(aset) or aset.upper()
    fallback = list(ALLOWED_VENDORS_BY_ASSET.get(canon_aset, ("MMS",)))
    conn = _read_db_if_ready(db_path)
    if conn is None:
        return fallback

    try:
        assigned = [
            row[0]
            for row in conn.execute(
                """
                SELECT DISTINCT r.vendor
                FROM opname_roster r
                JOIN opname_vendors v ON v.code = r.vendor
                WHERE r.aset = ? AND r.active = 1 AND v.active = 1
                ORDER BY r.vendor ASC
                """,
                (canon_aset,),
            ).fetchall()
        ]
        active_vendors = {
            row[0]
            for row in conn.execute("SELECT code FROM opname_vendors WHERE active = 1").fetchall()
        }
    finally:
        conn.close()

    merged: list[str] = []
    for v in assigned + [b for b in fallback if b in active_vendors]:
        if v not in merged:
            merged.append(v)
    return merged or fallback


def export_roster_payload(db_path: str) -> dict[str, Any]:
    ensure_roster_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        vendor_rows = conn.execute(
            "SELECT code, aliases_json, active, updated_at FROM opname_vendors ORDER BY active DESC, code ASC"
        ).fetchall()
        roster_rows = conn.execute(
            "SELECT aset, vendor, wilayah, active, updated_at FROM opname_roster ORDER BY active DESC, aset ASC, wilayah ASC, vendor ASC"
        ).fetchall()
        meta_row = conn.execute(
            "SELECT value FROM opname_meta WHERE key = 'onedrive_last_sync'"
        ).fetchone()
    finally:
        conn.close()

    vendors_out = []
    for code, aliases_json, active, updated_at in vendor_rows:
        try:
            aliases = json.loads(aliases_json or "[]")
        except Exception:
            aliases = [code]
        vendors_out.append(
            {
                "code": code,
                "aliases": aliases,
                "active": bool(active),
                "updated_at": updated_at,
            }
        )

    roster_out = [
        {
            "aset": aset,
            "vendor": vendor,
            "wilayah": wilayah,
            "active": bool(active),
            "updated_at": updated_at,
        }
        for aset, vendor, wilayah, active, updated_at in roster_rows
    ]

    return {
        "version": ROSTER_SCHEMA_VERSION,
        "updated_at": _now_str(),
        "onedrive_last_sync": meta_row[0] if meta_row else "",
        "vendors": vendors_out,
        "roster": roster_out,
    }


def upsert_vendor(
    db_path: str,
    raw_code: str,
    aliases: Any = None,
    active: bool = True,
) -> dict[str, Any]:
    ensure_roster_tables(db_path)
    code = clean_vendor_code(raw_code)
    new_aliases = _parse_aliases_input(code, aliases)
    now = _now_str()

    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute(
            "SELECT aliases_json FROM opname_vendors WHERE code = ?", (code,)
        ).fetchone()
        merged_aliases = list(new_aliases)
        if existing:
            try:
                old_list = json.loads(existing[0] or "[]")
            except Exception:
                old_list = []
            for item in old_list:
                tok = _normalize_alias_token(str(item))
                if tok and tok not in merged_aliases:
                    merged_aliases.append(tok)
        conn.execute(
            "INSERT OR REPLACE INTO opname_vendors (code, aliases_json, active, updated_at) VALUES (?, ?, ?, ?)",
            (code, json.dumps(merged_aliases), 1 if active else 0, now),
        )
        _mark_modified_locally(conn, now)
        conn.commit()
    finally:
        conn.close()

    return {"code": code, "aliases": merged_aliases, "active": bool(active), "updated_at": now}


def upsert_roster_slot(
    db_path: str,
    aset: str,
    raw_vendor: str,
    wilayah: str,
    active: bool = True,
    aliases: Any = None,
) -> dict[str, Any]:
    from services.opname_catalog import VALID_OPNAME_ASSETS, normalize_asset_code

    canon_aset = normalize_asset_code(aset)
    if not canon_aset or canon_aset not in VALID_OPNAME_ASSETS:
        raise ValueError(f"Kode aset tidak valid: {aset}")
    wil = (wilayah or "").strip().upper()
    if wil not in ("W1", "W2"):
        raise ValueError("Wilayah wajib W1 atau W2.")

    v_info = upsert_vendor(db_path, raw_vendor, aliases=aliases, active=True if active else True)
    vendor = v_info["code"]
    now = _now_str()

    conn = sqlite3.connect(db_path)
    try:
        if active:
            conn.execute(
                "UPDATE opname_vendors SET active = 1, updated_at = ? WHERE code = ?",
                (now, vendor),
            )
        conn.execute(
            "INSERT OR REPLACE INTO opname_roster (aset, vendor, wilayah, active, updated_at) VALUES (?, ?, ?, ?, ?)",
            (canon_aset, vendor, wil, 1 if active else 0, now),
        )
        _mark_modified_locally(conn, now)
        conn.commit()
    finally:
        conn.close()

    return {
        "aset": canon_aset,
        "vendor": vendor,
        "wilayah": wil,
        "active": bool(active),
        "aliases": v_info["aliases"],
        "updated_at": now,
    }


def set_roster_slot_active(
    db_path: str,
    aset: str,
    vendor: str,
    wilayah: str,
    active: bool,
) -> bool:
    from services.opname_catalog import normalize_asset_code

    ensure_roster_tables(db_path)
    canon_aset = normalize_asset_code(aset) or (aset or "").strip().upper()
    code = clean_vendor_code(vendor)
    wil = (wilayah or "").strip().upper()
    now = _now_str()

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE opname_roster SET active = ?, updated_at = ? WHERE aset = ? AND vendor = ? AND wilayah = ?",
            (1 if active else 0, now, canon_aset, code, wil),
        )
        changed = cur.rowcount > 0
        if changed:
            if active:
                conn.execute(
                    "UPDATE opname_vendors SET active = 1, updated_at = ? WHERE code = ?",
                    (now, code),
                )
            _mark_modified_locally(conn, now)
            conn.commit()
        return changed
    finally:
        conn.close()


def set_vendor_active(db_path: str, raw_code: str, active: bool) -> bool:
    ensure_roster_tables(db_path)
    code = clean_vendor_code(raw_code)
    now = _now_str()
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE opname_vendors SET active = ?, updated_at = ? WHERE code = ?",
            (1 if active else 0, now, code),
        )
        changed = cur.rowcount > 0
        if changed:
            _mark_modified_locally(conn, now)
            conn.commit()
        return changed
    finally:
        conn.close()


def import_roster_payload(
    db_path: str,
    payload: dict[str, Any],
    mark_local_mod: bool = True,
) -> dict[str, Any]:
    from services.opname_catalog import VALID_OPNAME_ASSETS, normalize_asset_code

    if not isinstance(payload, dict) or int(payload.get("version") or 0) != ROSTER_SCHEMA_VERSION:
        raise ValueError(f"Format JSON roster tidak valid (wajib version = {ROSTER_SCHEMA_VERSION}).")

    raw_vendors = payload.get("vendors")
    raw_roster = payload.get("roster")
    if not isinstance(raw_vendors, list) or not isinstance(raw_roster, list) or not raw_vendors:
        raise ValueError("JSON roster wajib memiliki daftar vendors dan roster.")

    clean_vendors: list[tuple[str, str, int, str]] = []
    seen_codes: set[str] = set()
    now = _now_str()

    for v in raw_vendors:
        if not isinstance(v, dict):
            raise ValueError("Item vendor dalam JSON tidak valid.")
        code = clean_vendor_code(str(v.get("code") or ""))
        if code in seen_codes:
            continue
        seen_codes.add(code)
        aliases = _parse_aliases_input(code, v.get("aliases") or [])
        active = 1 if v.get("active", True) else 0
        upd = str(v.get("updated_at") or now)
        clean_vendors.append((code, json.dumps(aliases), active, upd))

    clean_roster: list[tuple[str, str, str, int, str]] = []
    seen_slots: set[tuple[str, str, str]] = set()
    for r in raw_roster:
        if not isinstance(r, dict):
            raise ValueError("Item slot roster dalam JSON tidak valid.")
        canon_aset = normalize_asset_code(str(r.get("aset") or ""))
        if not canon_aset or canon_aset not in VALID_OPNAME_ASSETS:
            raise ValueError(f"Aset tidak valid pada roster JSON: {r.get('aset')}")
        vendor = clean_vendor_code(str(r.get("vendor") or ""))
        wil = str(r.get("wilayah") or "").strip().upper()
        if wil not in ("W1", "W2"):
            raise ValueError(f"Wilayah tidak valid pada roster JSON: {r.get('wilayah')}")
        if vendor not in seen_codes:
            seen_codes.add(vendor)
            clean_vendors.append((vendor, json.dumps([vendor]), 1, now))
        slot_key = (canon_aset, vendor, wil)
        if slot_key in seen_slots:
            continue
        seen_slots.add(slot_key)
        active = 1 if r.get("active", True) else 0
        upd = str(r.get("updated_at") or now)
        clean_roster.append((canon_aset, vendor, wil, active, upd))

    ensure_roster_tables(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM opname_roster")
        conn.execute("DELETE FROM opname_vendors")
        conn.executemany(
            "INSERT INTO opname_vendors (code, aliases_json, active, updated_at) VALUES (?, ?, ?, ?)",
            clean_vendors,
        )
        conn.executemany(
            "INSERT INTO opname_roster (aset, vendor, wilayah, active, updated_at) VALUES (?, ?, ?, ?, ?)",
            clean_roster,
        )
        if mark_local_mod:
            _mark_modified_locally(conn, now)
        else:
            conn.execute(
                "INSERT OR REPLACE INTO opname_meta (key, value, updated_at) VALUES ('onedrive_last_sync', ?, ?)",
                (now, now),
            )
        conn.commit()
    finally:
        conn.close()

    return export_roster_payload(db_path)


def push_roster_to_onedrive(
    db_path: str,
    upload_private_fn: Callable[[bytes, str, str, str], str],
) -> tuple[bool, str]:
    try:
        payload = export_roster_payload(db_path)
        raw_bytes = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        upload_private_fn(
            raw_bytes,
            ROSTER_CONFIG_FILENAME,
            ROSTER_CONFIG_FOLDER,
            "application/json",
        )
        now = _now_str()
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO opname_meta (key, value, updated_at) VALUES ('onedrive_last_sync', ?, ?)",
                (now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return True, f"Tersinkron ke OneDrive ({ROSTER_CONFIG_FOLDER}/{ROSTER_CONFIG_FILENAME})."
    except Exception as err:
        return False, f"Tersimpan lokal di SQLite, namun gagal sync ke OneDrive: {err}"


def pull_roster_from_onedrive(
    db_path: str,
    download_by_path_fn: Callable[[str, str], bytes | None],
    only_if_unmodified: bool = False,
) -> tuple[bool, str]:
    ensure_roster_tables(db_path)
    if only_if_unmodified:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT value FROM opname_meta WHERE key = 'roster_modified_locally'"
            ).fetchone()
            if row and row[0] == "1":
                return False, "Daftar roster lokal sudah diubah; auto-restore OneDrive dilewati."
        finally:
            conn.close()

    try:
        raw_bytes = download_by_path_fn(ROSTER_CONFIG_FOLDER, ROSTER_CONFIG_FILENAME)
    except Exception as err:
        return False, f"Gagal mengunduh konfigurasi roster dari OneDrive: {err}"

    if not raw_bytes:
        return False, "File konfigurasi roster belum ada di OneDrive."

    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
        import_roster_payload(db_path, payload, mark_local_mod=False)
        return True, "Konfigurasi vendor & roster berhasil dipulihkan dari OneDrive."
    except Exception as parse_err:
        return False, f"File roster OneDrive tidak valid: {parse_err}"
