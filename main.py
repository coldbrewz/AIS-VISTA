import asyncio
import io
import json
import os
from pathlib import Path
import subprocess
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Query, Response, BackgroundTasks
import requests
import datetime
import re
import time
import sqlite3
from config import settings
from services.llm import extract_opname_form_ocr, extract_sla_data
from services.message_utils import (
    extract_kode_from_text,
    extract_media_metadata,
    extract_message_id,
    extract_scan_opname_hint,
    parse_opname_date_str,
    reconcile_date_with_message_time,
    resolve_billing_cycle,
    resolve_media_download_url,
    resolve_reply_chat_id,
)
from services.opname_catalog import (
    ASSET_TO_TABLE,
    OFFICIAL_VENDOR_ROSTER,
    check_roster_pairing,
    format_boq_cheat_sheet,
    normalize_asset_code,
    normalize_vendor,
    resolve_boq_item,
    resolve_wilayah,
)
from services.opname_xlsx import (
    MONTH_INDEX_TO_ABBR,
    XlsxSlotBatch,
    build_prefilled_standard_xlsx,
    parse_standard_opname_xlsx,
)
from services.whatsapp import send_whatsapp_document, send_whatsapp_message
from services.microsoft import (
    OPNAME_MONTH_NAMES,
    append_opname_rows,
    delete_opname_rows_by_id,
    download_file_from_onedrive,
    download_share_file_from_onedrive,
    ensure_monthly_opname_workbook,
    replace_opname_slot_rows,
    update_excel_row,
    upload_file_to_onedrive,
    upload_photo_to_onedrive,
)
from services.tagihan_generator import generate_tagihan_workbook, parse_tagihan_cycle

import logging
from logging.handlers import RotatingFileHandler

# FIX #9/10: Use Python's RotatingFileHandler instead of manual TailLogger
# This prevents file handle churn and auto-caps the log at 10MB (3 backups = 30MB max)
class TailLogger:
    """Redirect both stdout and stderr to a rotating log file AND the console."""
    is_tail_logger = True
    def __init__(self, log_file: str):
        self.terminal = sys.stdout
        self._logger = logging.getLogger("vista")
        self._logger.setLevel(logging.DEBUG)
        handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter('%(message)s'))
        if not self._logger.handlers:
            self._logger.addHandler(handler)

    def write(self, message):
        try:
            self.terminal.write(message)
        except (UnicodeEncodeError, OSError):
            # Windows cp1252 terminal can't handle emoji - write ASCII-safe version
            try:
                self.terminal.write(message.encode('ascii', 'replace').decode('ascii'))
            except OSError:
                pass
        if message.strip():
            self._logger.info(message.rstrip())
            
    def flush(self):
        try:
            self.terminal.flush()
        except OSError:
            # uvicorn reload subprocess invalidates the original terminal handle
            pass
        
    def isatty(self):
        if hasattr(self.terminal, 'isatty'):
            return self.terminal.isatty()
        return False

import sys

if not hasattr(sys.stdout, "is_tail_logger"):
    sys.stdout = TailLogger("vista_bot.log")
    sys.stderr = sys.stdout

is_updating = False
# Grace period: don't process messages for 60s after login to avoid
# triggering WhatsApp anti-bot detection from burst activity
session_ready_at = 0  # timestamp when session became WORKING

_has_docker_cache = None

def has_docker() -> bool:
    global _has_docker_cache
    if _has_docker_cache is not None:
        return _has_docker_cache
    
    import shutil
    if not shutil.which("docker"):
        _has_docker_cache = False
        return False
        
    try:
        res = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        _has_docker_cache = (res.returncode == 0)
    except Exception:
        _has_docker_cache = False
        
    return _has_docker_cache

async def auto_update_waha():
    global is_updating
    if not has_docker():
        print("AUTO-UPDATE: Docker daemon not available. Skipping auto-update service.")
        return
    while True:
        now = datetime.datetime.now()
        target = now.replace(hour=8, minute=5, second=0, microsecond=0)
        if now >= target:
            target += datetime.timedelta(days=7)
        wait_seconds = (target - now).total_seconds()
        print(f"AUTO-UPDATE: Scheduled next WAHA update in {wait_seconds/3600:.2f} hours (at {target})")
        await asyncio.sleep(wait_seconds)
        
        is_updating = True
        print("AUTO-UPDATE: Pulling latest WAHA image...")
        try:
            # FIX #6: Explicitly use the production compose file, not the default dev one
            await asyncio.to_thread(subprocess.run, ["docker", "compose", "-f", "docker-compose.prod.yml", "pull", "waha"], check=False)
            await asyncio.to_thread(subprocess.run, ["docker", "compose", "-f", "docker-compose.prod.yml", "up", "-d", "waha"], check=False)
            print("AUTO-UPDATE: WAHA updated successfully.")
        except Exception as e:
            print(f"AUTO-UPDATE: Failed to update WAHA: {e}")
        finally:
            await asyncio.sleep(15)
            is_updating = False

from services.email import send_qr_email, email_poller
from services.telegram import send_telegram_alert, telegram_poller

async def daily_recap_scheduler():
    """Sends a daily recap at 08:00 WIB of the previous day's unique SLA updates."""
    while True:
        now = datetime.datetime.now()
        # Target 08:00 today
        target = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now >= target:
            target += datetime.timedelta(days=1)
            
        wait_seconds = (target - now).total_seconds()
        print(f"RECAP SCHEDULER: Next recap scheduled for {target} (in {wait_seconds/3600:.2f} hours)")
        await asyncio.sleep(wait_seconds)
        
        try:
            # It's now 08:00. We want to check yesterday's date.
            ydt = datetime.datetime.now() - datetime.timedelta(days=1)
            yesterday_str = ydt.strftime('%Y-%m-%d')
            
            conn = sqlite3.connect(settings.DB_URL)
            c = conn.cursor()
            # Failsafe create table if not initialized yet
            c.execute('''CREATE TABLE IF NOT EXISTS daily_updates (kode TEXT, date TEXT, UNIQUE(kode, date))''')
            c.execute("SELECT kode FROM daily_updates WHERE date = ?", (yesterday_str,))
            kodes = [row[0] for row in c.fetchall()]
            conn.close()
            
            total_count = len(kodes)
            category_counts = {}
            for k in kodes:
                match = re.match(r"^\d{6}([A-Z]{2})\d+$", k)
                if match:
                    cat = match.group(1)
                    category_counts[cat] = category_counts.get(cat, 0) + 1
            
            cat_text = "\n".join([f"- *{cat}*: {cnt} Kode" for cat, cnt in sorted(category_counts.items())])
            if not cat_text:
                cat_text = "- _Tidak ada update_"
            
            admin_phone = settings.ADMIN_PHONE
            if admin_phone:
                admin_phone = re.sub(r'\D', '', admin_phone)
                
                # Format date beautifully (e.g., "24 Juni 2026")
                months_id = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
                date_display = f"{ydt.day} {months_id[ydt.month - 1]} {ydt.year}"
                
                msg = f"📊 *Rekap Harian VISTA* 📊\n\nUntuk tanggal: *{date_display}*\nTotal Keseluruhan: *{total_count}* Kode SLA unik telah diperbarui.\n\nRincian per Kategori:\n{cat_text}"
                
                print(f"RECAP SCHEDULER: Sending recap for {total_count} codes to {admin_phone}")
                await asyncio.to_thread(send_whatsapp_message, admin_phone, msg, "default")
                
        except Exception as e:
            print(f"RECAP SCHEDULER: Failed to send recap: {e}")
            
        # Sleep a bit to avoid double-triggering right at 08:00:00
        await asyncio.sleep(60)

async def sync_offline_messages(session_name: str = "default", offline_since: float = None):
    # If we don't know exactly when we went offline (e.g. computer restarted), default to 24 hours ago
    if offline_since is None:
        offline_since = datetime.datetime.now().timestamp() - (24 * 3600)

    print(f"OFFLINE SYNC: Checking for missed messages in session '{session_name}' since {datetime.datetime.fromtimestamp(offline_since).strftime('%Y-%m-%d %H:%M:%S')}...")
    headers = {"X-Api-Key": settings.WAHA_API_KEY}
    try:
        chats_resp = await asyncio.to_thread(
            requests.get,
            f"{settings.WAHA_URL}/api/{session_name}/chats",
            headers=headers,
            timeout=15
        )
        if chats_resp.status_code != 200:
            return
        chats = chats_resp.json()
        if not isinstance(chats, list):
            return
            
        for chat in chats:
            if not isinstance(chat, dict):
                continue
            unread_count = chat.get("unreadCount", 0)
            if unread_count > 0:
                chat_id = chat.get("id", {}).get("_serialized")
                if not chat_id:
                    chat_id = chat.get("id")
                    if isinstance(chat_id, dict):
                        continue
                
                print(f"OFFLINE SYNC: Found {unread_count} unread messages in chat {chat_id}. Fetching...")
                msgs_resp = await asyncio.to_thread(
                    requests.get,
                    f"{settings.WAHA_URL}/api/{session_name}/chats/{chat_id}/messages?limit={unread_count}",
                    headers=headers,
                    timeout=15
                )
                if msgs_resp.status_code == 200:
                    messages = msgs_resp.json()
                    if isinstance(messages, list):
                        for msg in messages:
                            msg_timestamp = msg.get("timestamp", 0)
                            
                            # Skip messages that arrived before we went offline
                            if msg_timestamp < offline_since:
                                continue
                                
                            raw_id = msg.get("id")
                            msg_id = raw_id.get("_serialized") if isinstance(raw_id, dict) else raw_id
                            
                            if not msg_id:
                                continue
                                
                            payload = dict(msg)
                            payload["id"] = msg_id
                            payload["_session"] = session_name
                            
                            is_from_me = payload.get("fromMe", False) or (isinstance(raw_id, dict) and raw_id.get("fromMe", False))
                            if not is_from_me:
                                print(f"OFFLINE SYNC: Injecting missed message {msg_id} into processing queue...")
                                await asyncio.to_thread(process_message, payload)
                                
                # Mark chat as seen to clear the unread badge
                await asyncio.to_thread(
                    requests.post,
                    f"{settings.WAHA_URL}/api/sendSeen",
                    headers=headers,
                    json={"session": session_name, "chatId": chat_id},
                    timeout=10
                )
    except Exception as e:
        print(f"OFFLINE SYNC: Failed to sync messages: {e}")


async def waha_watchdog():
    """Background task to monitor WAHA health and auto-restart if stuck."""
    global is_updating, session_ready_at
    consecutive_failures = 0
    restart_count = 0
    MAX_RESTARTS_BEFORE_BACKOFF = 3  # After 3 docker restarts, back off to prevent WhatsApp ban
    was_offline = True  # Start as True so we do an offline sync on the very first boot
    offline_since = None
    qr_email_sent = False
    headers = {"X-Api-Key": settings.WAHA_API_KEY}
    
    while True:
        if is_updating:
            await asyncio.sleep(30)
            continue
            
        try:
            # Run requests.get in a separate thread to not block the async event loop
            resp = await asyncio.to_thread(
                requests.get,
                f"{settings.WAHA_URL}/api/sessions?all=true",
                headers=headers,
                timeout=5
            )
            data = resp.json()
            if isinstance(data, list):
                if not data:
                    print("WATCHDOG: No active sessions found in WAHA. Re-initializing default session...")
                    asyncio.create_task(init_waha_session())
                    consecutive_failures = 0
                    await asyncio.sleep(10)
                    continue
                status = data[0].get("status")
                
                # Send QR code email if WAHA logs out
                if status == "SCAN_QR_CODE":
                    if not qr_email_sent:
                        print("WATCHDOG: WAHA is logged out. Grabbing native QR and sending email...")
                        try:
                            # Grab raw QR code using WAHA API
                            qr_headers = headers.copy()
                            qr_headers["Accept"] = "image/png"
                            qr_resp = await asyncio.to_thread(
                                requests.get,
                                f"{settings.WAHA_URL}/api/default/auth/qr",
                                headers=qr_headers,
                                timeout=60
                            )
                            if qr_resp.status_code == 200 and 'image' in qr_resp.headers.get('Content-Type', ''):
                                await asyncio.to_thread(send_qr_email, qr_resp.content)
                                await asyncio.to_thread(send_telegram_alert, "🚨 WAHA Bot Logged Out! When you are ready to scan the QR code, reply to this chat with /qr")
                                qr_email_sent = True
                            else:
                                print(f"WATCHDOG: Failed to grab QR. Status {qr_resp.status_code}")
                        except Exception as e:
                            print(f"WATCHDOG: Error sending QR email: {e}")
                elif status == "WORKING":
                    qr_email_sent = False
                
                # Check docker logs specifically for the known web.js crash 
                # since presence='offline' is natively true when the main phone is dead
                is_crashed = False
                if status == "WORKING" and has_docker():
                    try:
                        logs_out = await asyncio.to_thread(subprocess.run, ["docker", "logs", "--tail", "20", "waha"], capture_output=True, text=True, check=False)
                        if "reading 'getContact'" in logs_out.stderr or "reading 'getContact'" in logs_out.stdout:
                            is_crashed = True
                    except Exception:
                        pass

                if status == "WORKING" and not is_crashed:
                    consecutive_failures = 0
                    restart_count = 0  # Reset backoff counter on recovery
                    if was_offline:
                        print("\n✅ WATCHDOG: WAHA is online and WORKING!\n")
                        was_offline = False
                        
                        # Set grace period - don't process messages for 60s
                        # to let WAHA settle and avoid burst activity that triggers WhatsApp bans
                        session_ready_at = time.time()
                        print("WATCHDOG: 60-second grace period started. Messages will be queued but not processed.")
                        
                        session_name = data[0].get("name", "default")
                        
                        # Delay offline sync by 90 seconds to let WAHA fully settle first
                        async def delayed_sync(sn, os_ts):
                            await asyncio.sleep(90)
                            await sync_offline_messages(sn, os_ts)
                        asyncio.create_task(delayed_sync(session_name, offline_since))
                        offline_since = None
                        
                        # Send recovery alert via Telegram only (NOT WhatsApp)
                        # Sending a WhatsApp message immediately after login contributes to ban detection
                        await asyncio.to_thread(send_telegram_alert, "✅ WAHA Bot is back online and WORKING!")
                else:
                    if not was_offline:
                        offline_since = datetime.datetime.now().timestamp()
                    was_offline = True
                    
                    if is_crashed or status in ["FAILED", "STOPPED"]:
                        consecutive_failures += 1
                        print(f"WATCHDOG: WAHA status={status}, crashed={is_crashed}. Failure count: {consecutive_failures}/3")
                    else:
                        # e.g. SCAN_QR_CODE or STARTING - Do NOT restart the container while waiting for user!
                        consecutive_failures = 0
            else:
                consecutive_failures += 1
                was_offline = True
                print(f"WATCHDOG: Invalid WAHA response. Failure count: {consecutive_failures}/3")
        except Exception as e:
            consecutive_failures += 1
            was_offline = True
            print(f"WATCHDOG: Cannot reach WAHA ({type(e).__name__}). Failure count: {consecutive_failures}/3")
            
        if consecutive_failures >= 3:
            restart_count += 1
            if not has_docker():
                print("WATCHDOG: WAHA is offline, but Docker daemon is not available. Skipping container restart (normal for Railway/Serverless environments).")
                consecutive_failures = 0
                await asyncio.sleep(30)
                continue
                
            if restart_count <= MAX_RESTARTS_BEFORE_BACKOFF:
                print(f"WATCHDOG: WAHA stuck. Restarting Docker container (attempt {restart_count}/{MAX_RESTARTS_BEFORE_BACKOFF})...")
                try:
                    subprocess.run(["docker", "restart", "waha"], check=False)
                    print("WATCHDOG: Docker restart command sent. Waiting 30s for recovery...")
                except Exception as e:
                    print(f"WATCHDOG: Failed to run docker restart: {e}")
                consecutive_failures = 0
                await asyncio.sleep(30)
            else:
                # Too many restarts — stop hammering to avoid WhatsApp account restrictions.
                # Each restart generates a new session/QR registration with WhatsApp's servers.
                backoff_minutes = 10
                print(f"WATCHDOG: ⚠️ Hit {MAX_RESTARTS_BEFORE_BACKOFF} restart attempts. Backing off for {backoff_minutes} minutes to protect WhatsApp account.")
                await asyncio.to_thread(send_telegram_alert, f"⚠️ WAHA has failed {MAX_RESTARTS_BEFORE_BACKOFF} restart attempts. Watchdog is backing off for {backoff_minutes} minutes to prevent WhatsApp account ban. Check /status manually.")
                consecutive_failures = 0
                restart_count = 0
                await asyncio.sleep(backoff_minutes * 60)
            
        await asyncio.sleep(30)


async def init_waha_session():
    print("INIT: Checking WAHA session configuration...")
    for _ in range(30):
        try:
            resp = await asyncio.to_thread(
                requests.get, 
                f"{settings.WAHA_URL}/api/sessions", 
                headers={"X-Api-Key": settings.WAHA_API_KEY}, 
                timeout=5
            )
            if resp.status_code == 200:
                sessions = resp.json()
                if not any(s.get("name") == "default" for s in sessions):
                    print("INIT: Creating 'default' session...")
                    payload = {
                        "name": "default",
                        "config": {
                            "noweb": {
                                "store": {
                                    "enabled": True,
                                    "fullSync": False
                                }
                            }
                        }
                    }
                    await asyncio.to_thread(
                        requests.post, 
                        f"{settings.WAHA_URL}/api/sessions/start", 
                        json=payload, 
                        headers={"X-Api-Key": settings.WAHA_API_KEY},
                        timeout=10
                    )
                    print("INIT: Session created successfully.")
                else:
                    print("INIT: 'default' session already exists.")
                return
        except Exception:
            await asyncio.sleep(2)
    print("INIT: Failed to reach WAHA after 60 seconds.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        print("==============================")
        print("Starting VISTA Integration")
        print("==============================")
        
        task_init = asyncio.create_task(init_waha_session())
        task1 = asyncio.create_task(waha_watchdog())
        task2 = asyncio.create_task(auto_update_waha())
        task3 = asyncio.create_task(daily_recap_scheduler())
        asyncio.create_task(telegram_poller())
        asyncio.create_task(email_poller())
        yield
        # Clean up tasks on shutdown
        task1.cancel()
        task2.cancel()
        task3.cancel()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise

app = FastAPI(title="Project VISTA Webhook API", lifespan=lifespan)

def init_db():
    conn = sqlite3.connect(settings.DB_URL)
    c = conn.cursor()
    # FIX #7: Enable WAL mode for safe concurrent reads/writes from multiple threads
    c.execute("PRAGMA journal_mode=WAL")
    c.execute('''CREATE TABLE IF NOT EXISTS processed (
                 message_id TEXT PRIMARY KEY
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_updates (
                 kode TEXT,
                 date TEXT,
                 UNIQUE(kode, date)
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS opname_entries (
                 opname_id TEXT,
                 aset TEXT,
                 wilayah TEXT,
                 tanggal TEXT,
                 lokasi TEXT,
                 vendor TEXT,
                 item_key TEXT,
                 volume REAL,
                 satuan TEXT,
                 table_name TEXT,
                 status TEXT DEFAULT 'ACTIVE',
                 created_at TEXT,
                 pic TEXT,
                 kode_temuan TEXT,
                 drive_id TEXT DEFAULT '',
                 item_id TEXT DEFAULT ''
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS opname_workbooks (
                 cycle_key TEXT PRIMARY KEY,
                 drive_id TEXT,
                 item_id TEXT,
                 web_url TEXT,
                 created_at TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS opname_pending (
                 pending_id TEXT PRIMARY KEY,
                 kind TEXT,
                 aset TEXT,
                 payload_json TEXT,
                 xlsx_path TEXT,
                 source_path TEXT,
                 warnings_text TEXT,
                 status TEXT DEFAULT 'PENDING',
                 created_at TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS opname_archives (
                 archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
                 slot_id TEXT,
                 cycle_key TEXT,
                 aset TEXT,
                 wilayah TEXT,
                 vendor TEXT,
                 minggu TEXT,
                 source_type TEXT,
                 file_path TEXT,
                 item_id TEXT DEFAULT '',
                 web_url TEXT DEFAULT '',
                 row_count INTEGER,
                 created_at TEXT
                 )''')
    # Upgrade older schemas gracefully if columns missing
    existing_cols = {row[1] for row in c.execute("PRAGMA table_info(opname_entries)").fetchall()}
    if "drive_id" not in existing_cols:
        c.execute("ALTER TABLE opname_entries ADD COLUMN drive_id TEXT DEFAULT ''")
    if "item_id" not in existing_cols:
        c.execute("ALTER TABLE opname_entries ADD COLUMN item_id TEXT DEFAULT ''")
    arc_cols = {row[1] for row in c.execute("PRAGMA table_info(opname_archives)").fetchall()}
    if "item_id" not in arc_cols:
        c.execute("ALTER TABLE opname_archives ADD COLUMN item_id TEXT DEFAULT ''")
    if "web_url" not in arc_cols:
        c.execute("ALTER TABLE opname_archives ADD COLUMN web_url TEXT DEFAULT ''")
    conn.commit()
    conn.close()

init_db()

def mark_processed(message_id: str) -> bool:
    conn = sqlite3.connect(settings.DB_URL)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO processed (message_id) VALUES (?)", (message_id,))
    inserted = c.rowcount > 0
    conn.commit()
    conn.close()
    return inserted

def unmark_processed(message_id: str):
    conn = sqlite3.connect(settings.DB_URL)
    c = conn.cursor()
    c.execute("DELETE FROM processed WHERE message_id = ?", (message_id,))
    conn.commit()
    conn.close()

def download_whatsapp_media(media_url: str) -> bytes:
    headers = {"X-Api-Key": settings.WAHA_API_KEY}
    resp = requests.get(media_url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.content


def _extract_image_bytes_from_message(message: dict) -> bytes:
    raw_data_body = message.get("_data", {}).get("body", "")
    if raw_data_body and isinstance(raw_data_body, str) and (
        raw_data_body.startswith("/9j/") or raw_data_body.startswith("iVBORw0K")
    ):
        import base64
        return base64.b64decode(raw_data_body)

    internal_media_url = resolve_media_download_url(message, settings.WAHA_URL)
    if not internal_media_url:
        raise Exception(
            "WAHA webhook did not provide a usable media URL or message ID, so the photo cannot be downloaded. Please resend the photo."
        )
    return download_whatsapp_media(internal_media_url)


def _archive_opname_file_to_onedrive(
    cycle_key: str,
    aset: str,
    filename: str,
    data_bytes: bytes,
    mimetype: str,
) -> dict:
    """Upload opname .xlsx or signed scan to OneDrive `/Arsip Opname/{cycle_key}/{aset}` (zero local disk storage)."""
    safe_name = re.sub(r"[^A-Za-z0-9_.\-]+", "_", os.path.basename(filename or "opname.bin"))
    folder_path = f"Arsip Opname/{cycle_key}/{aset}"
    item_id, web_url = upload_file_to_onedrive(data_bytes, safe_name, folder_path, content_type=mimetype)
    return {
        "filename": safe_name,
        "item_id": item_id,
        "web_url": web_url,
        "mimetype": mimetype,
    }


def _render_pdf_pages_to_jpeg(pdf_bytes: bytes, max_pages: int = 5) -> list[bytes]:
    import pypdfium2 as pdfium
    pages: list[bytes] = []
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        n_pages = min(len(doc), max_pages)
        for idx in range(n_pages):
            page = doc[idx]
            bitmap = page.render(scale=2.2)
            pil_img = bitmap.to_pil()
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=88)
            pages.append(buf.getvalue())
    finally:
        doc.close()
    return pages


def _serialize_slots(slots: list[XlsxSlotBatch]) -> str:
    serializable = []
    for sl in slots:
        serializable.append(
            {
                "slot_id": sl.slot_id,
                "cycle_key": sl.cycle_key,
                "cycle_month": sl.cycle_month,
                "cycle_year": sl.cycle_year,
                "aset": sl.aset,
                "wilayah": sl.wilayah,
                "vendor": sl.vendor,
                "minggu": sl.minggu,
                "table_name": sl.table_name,
                "entries": [
                    {
                        "tanggal": e["tanggal"],
                        "minggu": e.get("minggu", sl.minggu),
                        "kode_temuan": e.get("kode_temuan", "-"),
                        "wilayah": e["wilayah"],
                        "vendor": e["vendor"],
                        "lokasi": e["lokasi"],
                        "jalur_lajur": e.get("jalur_lajur", "-"),
                        "item_key": e["item_key"],
                        "keyword": e.get("keyword", e["item_key"]),
                        "uraian": e.get("uraian", ""),
                        "satuan": e["satuan"],
                        "p": e.get("p"),
                        "l": e.get("l"),
                        "t": e.get("t"),
                        "jml": e.get("jml"),
                        "volume": e["volume"],
                        "material_status": e.get("material_status", ""),
                        "keterangan": e.get("keterangan", ""),
                    }
                    for e in sl.entries
                ],
            }
        )
    return json.dumps(serializable)


def _resolve_cycle_target_di(cycle_m: int, cycle_y: int) -> tuple[tuple[str, str] | None, str, str]:
    if not settings.OPNAME_AUTO_MONTHLY:
        return None, "", ""
    cycle_key = f"{cycle_y:04d}-{cycle_m:02d}"
    conn_wb = sqlite3.connect(settings.DB_URL)
    cached = conn_wb.execute(
        "SELECT drive_id, item_id FROM opname_workbooks WHERE cycle_key = ?",
        (cycle_key,),
    ).fetchone()
    conn_wb.close()
    if cached and cached[0] and cached[1]:
        return (cached[0], cached[1]), cached[0], cached[1]
    target_drive_id, target_item_id, wb_web_url = ensure_monthly_opname_workbook(
        settings.OPNAME_EXCEL_SHARE_LINK, cycle_m, cycle_y
    )
    conn_wb = sqlite3.connect(settings.DB_URL)
    conn_wb.execute(
        "INSERT OR REPLACE INTO opname_workbooks (cycle_key, drive_id, item_id, web_url, created_at) VALUES (?, ?, ?, ?, ?)",
        (cycle_key, target_drive_id, target_item_id, wb_web_url, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn_wb.commit()
    conn_wb.close()
    return (target_drive_id, target_item_id), target_drive_id, target_item_id


def _commit_opname_slots(
    slots_data: list[dict],
    sender_label: str,
    source_type: str,
    archive_items: list[tuple[str, dict]],
) -> list[dict]:
    if not settings.OPNAME_EXCEL_SHARE_LINK:
        raise Exception("`OPNAME_EXCEL_SHARE_LINK` belum diatur di server bot.")

    results = []
    created_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    archive_ref = next((it.get("web_url") for _, it in archive_items if it.get("web_url")), "-")
    for sl in slots_data:
        slot_id = sl["slot_id"]
        cycle_key = sl["cycle_key"]
        cycle_m = int(sl["cycle_month"])
        cycle_y = int(sl["cycle_year"])
        aset = sl["aset"]
        wilayah = sl["wilayah"]
        vendor = sl["vendor"]
        minggu = sl["minggu"]
        table_name = sl["table_name"]
        entries = sl["entries"]

        target_di, drive_id, item_id = _resolve_cycle_target_di(cycle_m, cycle_y)
        excel_rows = []
        for ent in entries:
            has_dims = any(ent.get(k) is not None for k in ("p", "l", "t", "jml"))
            vol_cell = ent["volume"]
            if has_dims:
                p_v, l_v, t_v, j_v = ent.get("p"), ent.get("l"), ent.get("t"), ent.get("jml")
                calc_prod = 1.0
                for d_v in (p_v, l_v, t_v, j_v):
                    if d_v is not None:
                        calc_prod *= float(d_v)
                if abs(calc_prod - float(ent["volume"])) < 0.01:
                    vol_cell = "=[@[Volume_Calc]]"
            excel_rows.append(
                [
                    slot_id,
                    ent.get("kode_temuan") or "-",
                    ent["tanggal"],
                    aset,
                    wilayah,
                    ent.get("lokasi") or "-",
                    ent.get("jalur_lajur") or "-",
                    vendor,
                    ent["item_key"],
                    ent.get("uraian") or "",
                    ent.get("p"),
                    ent.get("l"),
                    ent.get("t"),
                    ent.get("jml"),
                    '=IF(COUNT([@P]:[@Jumlah])>0,PRODUCT([@P]:[@Jumlah]),"")',
                    vol_cell,
                    ent["satuan"],
                    ent.get("material_status") or "",
                    sender_label,
                    archive_ref,
                    f"[{minggu}] {ent.get('keterangan') or ''}".strip(),
                ]
            )

        try:
            deleted_cnt, appended_cnt = replace_opname_slot_rows(
                settings.OPNAME_EXCEL_SHARE_LINK,
                table_name,
                slot_id,
                excel_rows,
                target_drive_item=target_di,
            )
        except Exception:
            if settings.OPNAME_AUTO_MONTHLY:
                conn_wb = sqlite3.connect(settings.DB_URL)
                conn_wb.execute("DELETE FROM opname_workbooks WHERE cycle_key = ?", (cycle_key,))
                conn_wb.commit()
                conn_wb.close()
            raise

        conn = sqlite3.connect(settings.DB_URL)
        c = conn.cursor()
        c.execute(
            "UPDATE opname_entries SET status = 'REPLACED' WHERE UPPER(opname_id) = ? AND status = 'ACTIVE'",
            (slot_id.upper(),),
        )
        for ent in entries:
            c.execute(
                """
                INSERT INTO opname_entries (
                    opname_id, aset, wilayah, tanggal, lokasi, vendor,
                    item_key, volume, satuan, table_name, status, created_at, pic, kode_temuan,
                    drive_id, item_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?)
                """,
                (
                    slot_id,
                    aset,
                    wilayah,
                    ent["tanggal"],
                    ent.get("lokasi") or "-",
                    vendor,
                    ent["item_key"],
                    ent["volume"],
                    ent["satuan"],
                    table_name,
                    created_now,
                    f"{sender_label} [{minggu}]",
                    ent.get("kode_temuan") or "-",
                    drive_id,
                    item_id,
                ),
            )
        for f_src_type, arc in archive_items:
            if arc and (arc.get("item_id") or arc.get("web_url")):
                c.execute(
                    """
                    INSERT INTO opname_archives (
                        slot_id, cycle_key, aset, wilayah, vendor, minggu, source_type, file_path, item_id, web_url, row_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slot_id,
                        cycle_key,
                        aset,
                        wilayah,
                        vendor,
                        minggu,
                        f_src_type,
                        arc.get("filename", ""),
                        arc.get("item_id", ""),
                        arc.get("web_url", ""),
                        len(entries),
                        created_now,
                    ),
                )
        conn.commit()
        conn.close()

        results.append(
            {
                "slot_id": slot_id,
                "cycle_key": cycle_key,
                "aset": aset,
                "wilayah": wilayah,
                "vendor": vendor,
                "minggu": minggu,
                "table_name": table_name,
                "deleted": deleted_cnt,
                "appended": appended_cnt,
                "entries": entries,
            }
        )
    return results


def _format_commit_reply(results: list[dict], source_label: str) -> str:
    month_names = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    ]
    blocks = [f"✅ *Opname Berhasil Dicatat ({source_label})*"]
    for res in results:
        cycle_y, cycle_m = map(int, res["cycle_key"].split("-"))
        action_note = f"revisi menggantikan {res['deleted']} baris lama" if res["deleted"] else "slot baru"
        agg: dict[tuple[str, str, str], float] = {}
        for e in res["entries"]:
            k = (e.get("keyword") or e["item_key"], e["item_key"], e["satuan"])
            agg[k] = agg.get(k, 0.0) + float(e["volume"])
        item_lines = "\n".join(
            f"  • *{kw}* (`{ik}`): *{vol:g} {sat}*" for (kw, ik, sat), vol in agg.items()
        )
        blocks.append(
            f"\nID: `{res['slot_id']}` ({action_note})\n"
            f"Siklus: {month_names[cycle_m - 1]} {cycle_y} | Minggu: *{res['minggu']}*\n"
            f"Aset / Wilayah / Vendor: *{res['aset']}* / *{res['wilayah']}* / *{res['vendor']}*\n"
            f"Total Baris: {res['appended']}\n"
            f"{item_lines}\n"
            f"_Batalkan? Ketik `/undo {res['slot_id']}`_"
        )
    return "\n".join(blocks)


def _stage_pending_confirmation(
    pending_id: str,
    kind: str,
    aset: str,
    slots_data: list[dict],
    xlsx_path: str,
    source_path: str,
    warnings: list[str],
) -> None:
    conn = sqlite3.connect(settings.DB_URL)
    conn.execute(
        """
        INSERT OR REPLACE INTO opname_pending (
            pending_id, kind, aset, payload_json, xlsx_path, source_path, warnings_text, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
        """,
        (
            pending_id,
            kind,
            aset,
            json.dumps(slots_data),
            xlsx_path,
            source_path,
            "\n".join(warnings),
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()


def handle_simpan_command(reply_chat_id: str, sender_label: str, body_text: str, session: str) -> None:
    parts = body_text.strip().split()
    if len(parts) < 2:
        send_whatsapp_message(reply_chat_id, "❌ Format salah. Ketik `/simpan SCAN-...` atau `/simpan CONF-...`.", session)
        return
    pending_id = parts[1].strip().upper()
    conn = sqlite3.connect(settings.DB_URL)
    row = conn.execute(
        "SELECT kind, aset, payload_json, xlsx_path, source_path, status FROM opname_pending WHERE UPPER(pending_id) = ?",
        (pending_id,),
    ).fetchone()
    conn.close()
    if not row:
        send_whatsapp_message(reply_chat_id, f"⚠️ ID staging `{pending_id}` tidak ditemukan.", session)
        return
    kind, _aset, payload_json, xlsx_path, source_path, status = row
    if status != "PENDING":
        send_whatsapp_message(reply_chat_id, f"⚠️ Data `{pending_id}` sudah diproses sebelumnya (`{status}`).", session)
        return

    slots_data = json.loads(payload_json)
    archive_items = []
    if source_path:
        archive_items.append(("SCAN_SRC", json.loads(source_path)))
    if xlsx_path:
        archive_items.append(("XLSX", json.loads(xlsx_path)))

    try:
        results = _commit_opname_slots(slots_data, sender_label, kind, archive_items)
    except Exception as e:
        send_whatsapp_message(reply_chat_id, f"❌ Gagal menyimpan `{pending_id}` ke OneDrive: {e}", session)
        return

    conn = sqlite3.connect(settings.DB_URL)
    conn.execute("UPDATE opname_pending SET status = 'CONFIRMED' WHERE UPPER(pending_id) = ?", (pending_id,))
    conn.commit()
    conn.close()
    send_whatsapp_message(reply_chat_id, _format_commit_reply(results, f"Konfirmasi {pending_id}"), session)


def handle_status_opname_command(reply_chat_id: str, text_lower: str, session: str) -> None:
    now = datetime.datetime.now()
    m_cyc = re.search(r"(\d{4})[-/](\d{1,2})", text_lower)
    if m_cyc:
        cycle_y, cycle_m = int(m_cyc.group(1)), int(m_cyc.group(2))
    else:
        cycle_m, cycle_y = resolve_billing_cycle(now)
    yy_mm = f"{cycle_y % 100:02d}{cycle_m:02d}"

    conn = sqlite3.connect(settings.DB_URL)
    rows = conn.execute(
        """
        SELECT DISTINCT aset, wilayah, vendor, opname_id
        FROM opname_entries
        WHERE status = 'ACTIVE' AND opname_id LIKE ?
        """,
        (f"XLS-{yy_mm}-%",),
    ).fetchall()
    conn.close()

    by_slot: dict[tuple[str, str, str], set[str]] = {}
    for aset, wil, vend, op_id in rows:
        wk = str(op_id).rsplit("-", 1)[-1]
        by_slot.setdefault((aset, wil, vend), set()).add(wk)

    lines = [f"📋 *STATUS OPNAME ROSTER ({cycle_y:04d}-{cycle_m:02d}, 21 Slot)*\n"]
    done_cnt = 0
    for aset, vend, wil in OFFICIAL_VENDOR_ROSTER:
        wks = sorted(by_slot.get((aset, wil, vend), set()))
        if wks:
            done_cnt += 1
            lines.append(f"✅ {aset} | {wil} | {vend} : {', '.join(wks)}")
        else:
            lines.append(f"⏳ {aset} | {wil} | {vend} : belum ada")
    lines.append(f"\nTerisi: *{done_cnt}/{len(OFFICIAL_VENDOR_ROSTER)}* slot.")
    send_whatsapp_message(reply_chat_id, "\n".join(lines), session)


def handle_arsip_command(reply_chat_id: str, body_text: str, session: str) -> None:
    query = body_text.strip().split(None, 1)
    if len(query) < 2:
        send_whatsapp_message(reply_chat_id, "❌ Format: `/arsip <SLOT_ID>` atau `/arsip <ASET> [YYYY-MM]`.", session)
        return
    arg = query[1].strip().upper()
    conn = sqlite3.connect(settings.DB_URL)
    if arg.startswith("XLS-"):
        rows = conn.execute(
            "SELECT DISTINCT file_path, source_type, slot_id, COALESCE(item_id, ''), COALESCE(web_url, '') FROM opname_archives WHERE UPPER(slot_id) = ? ORDER BY archive_id DESC LIMIT 3",
            (arg,),
        ).fetchall()
    else:
        toks = arg.split()
        aset_tok = normalize_asset_code(toks[0]) or toks[0]
        cyc_tok = toks[1] if len(toks) > 1 else ""
        if cyc_tok:
            rows = conn.execute(
                "SELECT DISTINCT file_path, source_type, slot_id, COALESCE(item_id, ''), COALESCE(web_url, '') FROM opname_archives WHERE aset = ? AND cycle_key = ? ORDER BY archive_id DESC LIMIT 3",
                (aset_tok, cyc_tok),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT file_path, source_type, slot_id, COALESCE(item_id, ''), COALESCE(web_url, '') FROM opname_archives WHERE aset = ? ORDER BY archive_id DESC LIMIT 3",
                (aset_tok,),
            ).fetchall()
    conn.close()

    sent = 0
    for f_name, src_type, sl_id, item_id, web_url in rows:
        fname = os.path.basename(f_name or f"{sl_id}.xlsx")
        ext = os.path.splitext(fname)[1].lower()
        mime = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if ext == ".xlsx"
            else ("application/pdf" if ext == ".pdf" else "image/jpeg")
        )
        link_line = f"\n🔗 {web_url}" if web_url else ""
        if item_id:
            try:
                file_bytes = download_file_from_onedrive(item_id)
                send_whatsapp_document(
                    reply_chat_id,
                    file_bytes,
                    fname,
                    caption=f"📁 Arsip `{sl_id}` ({src_type}){link_line}",
                    mimetype=mime,
                    session=session,
                )
                sent += 1
                continue
            except Exception as dl_err:
                print(f"Warning: Gagal unduh arsip {item_id} dari OneDrive: {dl_err}")
        if web_url:
            send_whatsapp_message(reply_chat_id, f"📁 Arsip `{sl_id}` ({src_type}): {web_url}", session)
            sent += 1
    if sent == 0:
        send_whatsapp_message(reply_chat_id, f"⚠️ Arsip `{arg}` tidak ditemukan.", session)


def handle_undo_command(reply_chat_id: str, body_text: str, session: str):
    parts = body_text.strip().split()
    if len(parts) < 2:
        send_whatsapp_message(
            reply_chat_id,
            "❌ Format salah. Ketik `/undo OPN-XXXXXX` sesuai ID pada balasan opname.",
            session,
        )
        return
    opname_id = parts[1].strip().upper()
    conn = sqlite3.connect(settings.DB_URL)
    c = conn.cursor()
    c.execute(
        "SELECT DISTINCT table_name, COALESCE(drive_id, ''), COALESCE(item_id, '') FROM opname_entries WHERE UPPER(opname_id) = ? AND status = 'ACTIVE'",
        (opname_id,),
    )
    rows = c.fetchall()
    if not rows:
        conn.close()
        send_whatsapp_message(
            reply_chat_id,
            f"⚠️ Data opname `{opname_id}` tidak ditemukan atau sudah dibatalkan.",
            session,
        )
        return
    table_name, drive_id, item_id = rows[0]
    target_di = (drive_id, item_id) if (drive_id and item_id) else None
    try:
        deleted = delete_opname_rows_by_id(
            settings.OPNAME_EXCEL_SHARE_LINK,
            table_name,
            opname_id,
            target_drive_item=target_di,
        )
        c.execute(
            "UPDATE opname_entries SET status = 'VOID' WHERE UPPER(opname_id) = ?",
            (opname_id,),
        )
        conn.commit()
        conn.close()
        send_whatsapp_message(
            reply_chat_id,
            f"🗑️ *Opname Dibatalkan*\nID: `{opname_id}`\nBaris dihapus di `{table_name}`: {deleted}",
            session,
        )
    except Exception as e:
        conn.close()
        send_whatsapp_message(reply_chat_id, f"❌ Gagal /undo `{opname_id}`: {e}", session)


def handle_rekap_opname_command(reply_chat_id: str, text_lower: str, session: str):
    now = datetime.datetime.now()
    target_date = now.strftime("%Y-%m-%d")
    m_date = re.search(r"(\d{4}-\d{2}-\d{2})", text_lower)
    m_dmy = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", text_lower)
    if m_date:
        target_date = m_date.group(1)
    elif m_dmy:
        target_date = f"{int(m_dmy.group(3)):04d}-{int(m_dmy.group(2)):02d}-{int(m_dmy.group(1)):02d}"

    conn = sqlite3.connect(settings.DB_URL)
    c = conn.cursor()
    c.execute(
        """
        SELECT wilayah, aset, COUNT(DISTINCT opname_id), SUM(volume), satuan
        FROM opname_entries
        WHERE status = 'ACTIVE' AND tanggal = ?
        GROUP BY wilayah, aset, satuan
        ORDER BY wilayah, aset
        """,
        (target_date,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        send_whatsapp_message(
            reply_chat_id,
            f"📊 *REKAP OPNAME ({target_date})*\nBelum ada data opname tercatat pada tanggal ini.",
            session,
        )
        return

    lines = [f"📊 *REKAP OPNAME HARIAN ({target_date})*\n"]
    cur_w = None
    for wil, aset, cnt, vol, sat in rows:
        if wil != cur_w:
            lines.append(f"*{wil}*")
            cur_w = wil
        vol_fmt = f"{vol:,.2f}".rstrip("0").rstrip(".")
        lines.append(f"- {aset}: {cnt} laporan | {vol_fmt} {sat}")
    send_whatsapp_message(reply_chat_id, "\n".join(lines), session)


def _record_tagihan_archive(slot_id: str, cycle_key: str, source_type: str, arc_info: dict, sheet_count: int) -> None:
    conn = sqlite3.connect(settings.DB_URL)
    conn.execute(
        """
        INSERT INTO opname_archives (
            slot_id, cycle_key, aset, wilayah, vendor, minggu, source_type, file_path, item_id, web_url, row_count, created_at
        ) VALUES (?, ?, 'TAGIHAN', 'W1-W2', 'ALL', 'MC', ?, ?, ?, ?, ?, ?)
        """,
        (
            slot_id,
            cycle_key,
            source_type,
            arc_info.get("filename", ""),
            arc_info.get("item_id", ""),
            arc_info.get("web_url", ""),
            sheet_count,
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()


def handle_tagihan_command(reply_chat_id: str, body_text: str, message: dict, session: str) -> None:
    if not settings.OPNAME_ENABLED:
        send_whatsapp_message(reply_chat_id, "⚠️ Fitur opname/tagihan sedang dinonaktifkan.", session)
        return
    if not settings.OPNAME_EXCEL_SHARE_LINK:
        send_whatsapp_message(reply_chat_id, "❌ `OPNAME_EXCEL_SHARE_LINK` belum dikonfigurasi di server bot.", session)
        return

    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    media_filename, media_mimetype = extract_media_metadata(message)
    has_xlsx_attachment = bool(
        message.get("hasMedia")
        and (media_filename.lower().endswith(".xlsx") or "spreadsheetml" in media_mimetype)
    )

    tmpl_bytes = b""
    tmpl_filename = ""
    if has_xlsx_attachment:
        try:
            tmpl_bytes = _extract_image_bytes_from_message(message)
            tmpl_filename = media_filename or "MC_TEMPLATE.xlsx"
        except Exception as dl_err:
            send_whatsapp_message(reply_chat_id, f"❌ Gagal mengunduh file template MC: {dl_err}", session)
            return

    cycle_m, cycle_y = parse_tagihan_cycle(body_text, template_filename=tmpl_filename)
    cycle_key = f"{cycle_y:04d}-{cycle_m:02d}"
    month_label = OPNAME_MONTH_NAMES.get(cycle_m, f"{cycle_m:02d}")

    if has_xlsx_attachment:
        try:
            tmpl_arc = _archive_opname_file_to_onedrive(cycle_key, "Tagihan", tmpl_filename, tmpl_bytes, xlsx_mime)
            _record_tagihan_archive(f"TAGIHAN-TMPL-{cycle_key}", cycle_key, "TAGIHAN_TEMPLATE", tmpl_arc, 0)
        except Exception as cache_err:
            print(f"Warning: Gagal arsip template Tagihan ke OneDrive: {cache_err}")
    else:
        conn = sqlite3.connect(settings.DB_URL)
        row = conn.execute(
            """
            SELECT file_path, COALESCE(item_id, '')
            FROM opname_archives
            WHERE source_type = 'TAGIHAN_TEMPLATE' AND item_id != ''
            ORDER BY (CASE WHEN cycle_key = ? THEN 0 ELSE 1 END), archive_id DESC
            LIMIT 1
            """,
            (cycle_key,),
        ).fetchone()
        conn.close()

        if row and row[1]:
            try:
                tmpl_bytes = download_file_from_onedrive(row[1])
                tmpl_filename = row[0] or f"MC-{cycle_m:02d}.xlsx"
            except Exception as dl_err:
                print(f"Warning: Gagal unduh template MC cached {row[1]}: {dl_err}")
                tmpl_bytes = b""

        if not tmpl_bytes and settings.TAGIHAN_TEMPLATE_SHARE_LINK:
            try:
                tmpl_bytes, tmpl_filename = download_share_file_from_onedrive(settings.TAGIHAN_TEMPLATE_SHARE_LINK)
            except Exception as share_err:
                send_whatsapp_message(reply_chat_id, f"❌ Gagal mengunduh `TAGIHAN_TEMPLATE_SHARE_LINK`: {share_err}", session)
                return

        if not tmpl_bytes:
            send_whatsapp_message(
                reply_chat_id,
                "⚠️ Template `MC` belum tersedia.\n"
                "Kirim file template `MC-<XX> MENCARI VOLUME.xlsx` dengan caption `/tagihan` "
                "(atau `/tagihan 2026-11`), setelah itu perintah `/tagihan` berikutnya akan otomatis memakai template tersebut.",
                session,
            )
            return

    # Download DATA_UNTUK_VOL_<BULAN>_<TAHUN>.xlsx from OneDrive
    try:
        if settings.OPNAME_AUTO_MONTHLY:
            try:
                target_di, drv_id, itm_id = _resolve_cycle_target_di(cycle_m, cycle_y)
                vista_bytes = download_file_from_onedrive(itm_id, drive_id=drv_id)
            except Exception:
                conn_wb = sqlite3.connect(settings.DB_URL)
                conn_wb.execute("DELETE FROM opname_workbooks WHERE cycle_key = ?", (cycle_key,))
                conn_wb.commit()
                conn_wb.close()
                target_di, drv_id, itm_id = _resolve_cycle_target_di(cycle_m, cycle_y)
                vista_bytes = download_file_from_onedrive(itm_id, drive_id=drv_id)
        else:
            vista_bytes, _ = download_share_file_from_onedrive(settings.OPNAME_EXCEL_SHARE_LINK)
    except Exception as silo_err:
        send_whatsapp_message(
            reply_chat_id,
            f"❌ Gagal mengambil `DATA_UNTUK_VOL_{month_label}_{cycle_y}.xlsx` dari OneDrive: {silo_err}",
            session,
        )
        return

    try:
        res = generate_tagihan_workbook(vista_bytes, tmpl_bytes, cycle_m, cycle_y)
    except Exception as gen_err:
        send_whatsapp_message(reply_chat_id, f"❌ Gagal membuat file Tagihan MC ({cycle_key}): {gen_err}", session)
        return

    out_bytes = res["output_bytes"]
    out_filename = res["output_filename"]
    try:
        out_arc = _archive_opname_file_to_onedrive(cycle_key, "Tagihan", out_filename, out_bytes, xlsx_mime)
        _record_tagihan_archive(f"TAGIHAN-{cycle_key}", cycle_key, "TAGIHAN_OUTPUT", out_arc, len(res["ordered_sheets"]))
    except Exception as arch_err:
        send_whatsapp_message(reply_chat_id, f"❌ Gagal mengunggah hasil Tagihan ke OneDrive: {arch_err}", session)
        return

    gt_lines = "\n".join(
        f"• {s}: Rp {res['grand_totals'][s]:,.2f}"
        for s in res["ordered_sheets"]
        if res["grand_totals"].get(s, 0.0) > 0
    ) or "• Belum ada volume opname > 0 pada siklus ini."
    warn_block = ""
    if res["warnings"]:
        warn_block = "\n\n⚠️ *Catatan:*\n" + "\n".join(f"- {w}" for w in res["warnings"][:5])
    caption = (
        f"📑 *Tagihan MC Selesai (`{month_label} {cycle_y}`)*\n"
        f"Total Pilar 1 (sheet aktif): *Rp {res['total_grand']:,.2f}*\n\n"
        f"{gt_lines}{warn_block}\n\n"
        f"🔗 {out_arc.get('web_url', '')}"
    )
    send_whatsapp_document(
        reply_chat_id,
        out_bytes,
        out_filename,
        caption=caption,
        mimetype=xlsx_mime,
        session=session,
    )


def process_opname_xlsx_message(
    file_bytes: bytes,
    filename: str,
    reply_chat_id: str,
    sender_label: str,
    caption: str,
    processing_key: str,
    session: str,
) -> bool:
    if not settings.OPNAME_ENABLED:
        return False

    res = parse_standard_opname_xlsx(file_bytes, filename=filename, caption=caption)
    if not res.is_standard_form:
        return False

    if res.errors:
        err_txt = "\n".join(f"- {e}" for e in res.errors[:12])
        send_whatsapp_message(reply_chat_id, f"⚠️ *File Excel Opname Ditolak*\n{err_txt}", session)
        return True

    first_sl = res.slots[0]
    arch_name = filename or f"{first_sl.slot_id}.xlsx"
    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    try:
        xlsx_arch_info = _archive_opname_file_to_onedrive(
            first_sl.cycle_key, first_sl.aset, arch_name, file_bytes, xlsx_mime
        )
    except Exception as arch_err:
        unmark_processed(processing_key)
        send_whatsapp_message(reply_chat_id, f"❌ Gagal arsip file Excel ke OneDrive: {arch_err}", session)
        return True
    slots_data = json.loads(_serialize_slots(res.slots))

    if res.roster_warnings:
        conf_id = f"CONF-{datetime.datetime.now():%y%m%d}-{uuid.uuid4().hex[:4].upper()}"
        _stage_pending_confirmation(
            conf_id,
            "XLSX_MISMATCH",
            res.aset or first_sl.aset,
            slots_data,
            json.dumps(xlsx_arch_info),
            "",
            res.roster_warnings,
        )
        warn_txt = "\n".join(f"• {w}" for w in res.roster_warnings)
        slot_txt = ", ".join(s["slot_id"] for s in slots_data)
        send_whatsapp_message(
            reply_chat_id,
            f"⚠️ *Butuh Konfirmasi Roster ({conf_id})*\n"
            f"Slot terdeteksi: `{slot_txt}`\n"
            f"{warn_txt}\n\n"
            f"Tetap simpan data ini ke DATA UNTUK VOL? Ketik:\n`/simpan {conf_id}`",
            session,
        )
        return True

    try:
        results = _commit_opname_slots(slots_data, sender_label, "XLSX", [("XLSX", xlsx_arch_info)])
    except Exception as e:
        unmark_processed(processing_key)
        send_whatsapp_message(reply_chat_id, f"❌ Gagal menulis data Excel ke OneDrive: {e}", session)
        return True

    send_whatsapp_message(reply_chat_id, _format_commit_reply(results, "Excel Form"), session)
    return True


def process_opname_scan_message(
    message: dict,
    reply_chat_id: str,
    sender_label: str,
    caption: str,
    scan_hint: dict,
    processing_key: str,
    session: str,
) -> None:
    if not settings.OPNAME_ENABLED:
        return

    if not message.get("hasMedia"):
        send_whatsapp_message(
            reply_chat_id,
            "⚠️ *Scan Opname Ditolak*\nLampirkan foto atau PDF form opname bersama caption `Scan Opname`.",
            session,
        )
        return

    filename, mimetype = extract_media_metadata(message)
    try:
        raw_bytes = _extract_image_bytes_from_message(message)
    except Exception as dl_err:
        unmark_processed(processing_key)
        send_whatsapp_message(reply_chat_id, f"❌ Gagal mengunduh lampiran Scan Opname: {dl_err}", session)
        return

    is_pdf = (
        mimetype == "application/pdf"
        or filename.lower().endswith(".pdf")
        or raw_bytes[:4] == b"%PDF"
    )
    if is_pdf:
        try:
            page_images = _render_pdf_pages_to_jpeg(raw_bytes)
        except Exception as pdf_err:
            unmark_processed(processing_key)
            send_whatsapp_message(reply_chat_id, f"❌ Gagal membaca PDF Scan Opname: {pdf_err}", session)
            return
    else:
        page_images = [raw_bytes]

    hint_aset = scan_hint.get("aset") or ""
    boq_menu = format_boq_cheat_sheet(hint_aset, max_items=40) if hint_aset else ""
    ocr_res, ocr_err = extract_opname_form_ocr(page_images, hint_aset, caption, boq_menu)
    if ocr_err and not ocr_res.get("rows"):
        unmark_processed(processing_key)
        send_whatsapp_message(reply_chat_id, f"❌ OCR Scan Opname gagal: {ocr_err}", session)
        return

    aset = normalize_asset_code(hint_aset or str(ocr_res.get("aset", "")))
    if not aset:
        send_whatsapp_message(
            reply_chat_id,
            "⚠️ Jenis pekerjaan tidak terbaca dari scan. Sertakan kode di caption, contoh: `Scan Opname PV`.",
            session,
        )
        return

    raw_rows = ocr_res.get("rows") or []
    if not raw_rows:
        send_whatsapp_message(reply_chat_id, "⚠️ Tidak ada baris pekerjaan terbaca pada lampiran scan.", session)
        return

    fallback_dt = datetime.datetime.now().strftime("%Y-%m-%d")
    hdr_vend = str(ocr_res.get("vendor") or "").strip()
    hdr_wil = str(ocr_res.get("wilayah") or scan_hint.get("wilayah") or "").strip().upper()
    hdr_wk = str(ocr_res.get("minggu") or scan_hint.get("minggu") or "M1").strip().upper()
    if not re.fullmatch(r"M[1-5]", hdr_wk):
        hdr_wk = "M1"

    parsed_entries: list[dict] = []
    warnings: list[str] = []
    warn_seen: set[str] = set()
    errors: list[str] = []
    preview_lines: list[str] = []

    for i_r, r_obj in enumerate(raw_rows, start=1):
        t_str = parse_opname_date_str(str(r_obj.get("tanggal") or "")) or fallback_dt
        loc = str(r_obj.get("lokasi") or "").strip()
        wil = str(r_obj.get("wilayah") or hdr_wil or "").strip().upper()
        if loc:
            w_ok, loc_w, _, w_err = resolve_wilayah(f"{loc} {wil}".strip() if wil in ("W1", "W2") else loc)
            if not w_ok or not loc_w:
                errors.append(f"Baris {i_r}: {w_err}")
                continue
            wil = loc_w
        if wil not in ("W1", "W2"):
            errors.append(f"Baris {i_r}: Wilayah W1/W2 tidak terbaca.")
            continue

        v_ok, canon_v, v_err = normalize_vendor(str(r_obj.get("vendor") or hdr_vend), aset)
        if not v_ok or not canon_v:
            errors.append(f"Baris {i_r}: {v_err}")
            continue

        boq_item, b_err = resolve_boq_item(aset, str(r_obj.get("raw_item") or ""), lokasi=loc, wilayah=wil)
        if not boq_item:
            errors.append(f"Baris {i_r}: {b_err}")
            continue

        vol_opn = r_obj.get("vol_opname")
        vol_vnd = r_obj.get("vol_vendor")
        vol_final = vol_opn if vol_opn is not None else vol_vnd
        try:
            vol_num = float(vol_final) if vol_final is not None else 0.0
        except (TypeError, ValueError):
            vol_num = 0.0
        if vol_num <= 0:
            errors.append(f"Baris {i_r}: Volume '{boq_item.keyword}' tidak terbaca / <= 0.")
            continue

        r_ok, r_warn = check_roster_pairing(aset, canon_v, wil)
        if not r_ok and r_warn not in warn_seen:
            warn_seen.add(r_warn)
            warnings.append(r_warn)

        jalur = " ".join(p for p in (str(r_obj.get("jalur") or "").strip(), str(r_obj.get("lajur") or "").strip()) if p) or "-"
        edited_mark = " ✏️" if r_obj.get("handwritten_edited") else ""
        preview_lines.append(
            f"{i_r}. *{boq_item.keyword}* (`{boq_item.item_key}`) | {loc or wil} | *{vol_num:g} {boq_item.satuan}*{edited_mark}"
        )
        parsed_entries.append(
            {
                "tanggal": t_str,
                "minggu": hdr_wk,
                "kode_temuan": str(r_obj.get("kode_temuan") or "-").strip() or "-",
                "wilayah": wil,
                "vendor": canon_v,
                "lokasi": loc or "-",
                "jalur_lajur": jalur,
                "item": boq_item,
                "item_key": boq_item.item_key,
                "keyword": boq_item.keyword,
                "uraian": boq_item.uraian,
                "satuan": boq_item.satuan,
                "p": r_obj.get("p"),
                "l": r_obj.get("l"),
                "t": r_obj.get("t"),
                "jml": r_obj.get("jml"),
                "vol_vendor": vol_vnd,
                "volume": round(vol_num, 4),
                "material_status": "",
                "keterangan": str(r_obj.get("keterangan") or "").strip(),
            }
        )

    if errors or not parsed_entries:
        err_msg = "\n".join(f"- {e}" for e in errors[:10]) if errors else "Baris opname tidak valid."
        send_whatsapp_message(reply_chat_id, f"⚠️ *Scan Opname Perlu Perbaikan*\n{err_msg}", session)
        return

    slots_by_id: dict[str, dict] = {}
    _, table_name, _ = ASSET_TO_TABLE[aset]
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
        ent_copy = {k: v for k, v in ent.items() if k != "item"}
        slots_by_id[sid]["entries"].append(ent_copy)

    first_slot = next(iter(slots_by_id.values()))
    scan_id = f"SCAN-{datetime.datetime.now():%y%m%d}-{uuid.uuid4().hex[:4].upper()}"
    src_ext = ".pdf" if is_pdf else ".jpg"
    src_mime = "application/pdf" if is_pdf else "image/jpeg"
    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    xlsx_bytes = build_prefilled_standard_xlsx(aset, first_slot["cycle_month"], first_slot["cycle_year"], parsed_entries)
    xlsx_name = f"{aset}_{first_slot['wilayah']}_{first_slot['vendor']}_{first_slot['minggu']}_{scan_id}.xlsx"
    try:
        src_arch_info = _archive_opname_file_to_onedrive(
            first_slot["cycle_key"], aset, f"{scan_id}_signed{src_ext}", raw_bytes, src_mime
        )
        xlsx_arch_info = _archive_opname_file_to_onedrive(
            first_slot["cycle_key"], aset, xlsx_name, xlsx_bytes, xlsx_mime
        )
    except Exception as arch_err:
        unmark_processed(processing_key)
        send_whatsapp_message(reply_chat_id, f"❌ Gagal arsip scan opname ke OneDrive: {arch_err}", session)
        return

    _stage_pending_confirmation(
        scan_id,
        "SCAN_OCR",
        aset,
        list(slots_by_id.values()),
        json.dumps(xlsx_arch_info),
        json.dumps(src_arch_info),
        warnings,
    )

    warn_block = ("\n\n⚠️ *Catatan Roster:*\n" + "\n".join(f"• {w}" for w in warnings)) if warnings else ""
    preview_msg = (
        f"🔎 *Hasil Scan Opname (`{scan_id}`)*\n"
        f"Aset / Minggu: *{aset}* / *{first_slot['minggu']}* | Vendor: *{first_slot['vendor']}*\n"
        + "\n".join(preview_lines[:20])
        + warn_block
        + f"\n\n✅ Ketik `/simpan {scan_id}` jika angka sudah benar, atau edit file Excel di bawah lalu kirim balik ke chat ini."
    )
    send_whatsapp_message(reply_chat_id, preview_msg, session)
    send_whatsapp_document(
        reply_chat_id,
        xlsx_bytes,
        xlsx_name,
        caption=f"Excel hasil OCR `{scan_id}`. Edit jika ada koreksi, atau balas `/simpan {scan_id}`.",
        session=session,
    )

def handle_whatsapp_command(reply_chat_id, command, session):
    try:
        now = datetime.datetime.now()
        months_id = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
        
        month_map = {m.lower(): i+1 for i, m in enumerate(months_id)}
        
        start_date = None
        end_date = None
        period_name = ""
        
        if command in ["/rekap", "/rekap hari ini"]:
            start_date = now.strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d')
            period_name = f"{now.day} {months_id[now.month - 1]} {now.year}"
            
        elif command == "/rekap minggu":
            # Monday of the current week (weekday() returns 0 for Monday)
            monday = now - datetime.timedelta(days=now.weekday())
            sunday = monday + datetime.timedelta(days=6)
            start_date = monday.strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d')  # Safe query up to current day
            
            start_str = f"{monday.day} {months_id[monday.month - 1]} {monday.year}"
            end_str = f"{sunday.day} {months_id[sunday.month - 1]} {sunday.year}"
            period_name = f"{start_str} - {end_str}"
            
        elif command == "/rekap bulan":
            # First day of the current month
            first_day = now.replace(day=1)
            start_date = first_day.strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d')
            
            period_name = f"Bulan {months_id[now.month - 1]} {now.year}"
            
        else:
            # Custom date parsing
            cmd_content = command.replace("/rekap", "").strip()
            month_names = "|".join(month_map.keys())
            
            # Pattern 1: DD-DD Month YYYY (e.g. 6-12 juli 2026)
            m1 = re.match(fr"^(\d+)\s*-\s*(\d+)\s+({month_names})(?:\s+(\d{{4}}))?$", cmd_content)
            # Pattern 2: DD Month - DD Month YYYY
            m2 = re.match(fr"^(\d+)\s+({month_names})(?:\s+(\d{{4}}))?\s*-\s*(\d+)\s+({month_names})(?:\s+(\d{{4}}))?$", cmd_content)
            # Pattern 3: DD Month YYYY
            m3 = re.match(fr"^(\d+)\s+({month_names})(?:\s+(\d{{4}}))?$", cmd_content)
            
            try:
                if m1:
                    d1_day = int(m1.group(1))
                    d2_day = int(m1.group(2))
                    month_name = m1.group(3)
                    year = int(m1.group(4)) if m1.group(4) else now.year
                    month_num = month_map[month_name]
                    
                    d1 = datetime.date(year, month_num, d1_day)
                    d2 = datetime.date(year, month_num, d2_day)
                    
                    start_date = d1.strftime('%Y-%m-%d')
                    end_date = d2.strftime('%Y-%m-%d')
                    period_name = f"{d1.day} {months_id[d1.month-1]} {d1.year} - {d2.day} {months_id[d2.month-1]} {d2.year}"
                    
                elif m2:
                    d1_day = int(m2.group(1))
                    m1_name = m2.group(2)
                    y1 = int(m2.group(3)) if m2.group(3) else None
                    
                    d2_day = int(m2.group(4))
                    m2_name = m2.group(5)
                    y2 = int(m2.group(6)) if m2.group(6) else now.year
                    
                    if not y1: y1 = y2
                    
                    d1 = datetime.date(y1, month_map[m1_name], d1_day)
                    d2 = datetime.date(y2, month_map[m2_name], d2_day)
                    
                    start_date = d1.strftime('%Y-%m-%d')
                    end_date = d2.strftime('%Y-%m-%d')
                    period_name = f"{d1.day} {months_id[d1.month-1]} {d1.year} - {d2.day} {months_id[d2.month-1]} {d2.year}"
                    
                elif m3:
                    d1_day = int(m3.group(1))
                    m1_name = m3.group(2)
                    y1 = int(m3.group(3)) if m3.group(3) else now.year
                    
                    d1 = datetime.date(y1, month_map[m1_name], d1_day)
                    start_date = d1.strftime('%Y-%m-%d')
                    end_date = d1.strftime('%Y-%m-%d')
                    period_name = f"{d1.day} {months_id[d1.month-1]} {d1.year}"
            except Exception as parse_err:
                print(f"Failed to parse custom date: {parse_err}")
                
        if not start_date:
            return
        
        conn = sqlite3.connect(settings.DB_URL)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS daily_updates (kode TEXT, date TEXT, UNIQUE(kode, date))''')
        c.execute("SELECT DISTINCT kode FROM daily_updates WHERE date >= ? AND date <= ?", (start_date, end_date))
        kodes = [row[0] for row in c.fetchall()]
        conn.close()
        
        total_count = len(kodes)
        category_counts = {}
        for k in kodes:
            match = re.match(r"^\d{6}([A-Z]{2})\d+$", k)
            if match:
                cat = match.group(1)
                category_counts[cat] = category_counts.get(cat, 0) + 1
        
        cat_text = "\n".join([f"- *{cat}*: {cnt} Kode" for cat, cnt in sorted(category_counts.items())])
        if not cat_text:
            cat_text = "- _Belum ada data SLA_"
            
        msg = f"📊 *Live Rekap VISTA* 📊\n\nPeriode: *{period_name}*\nTotal Keseluruhan: *{total_count}* Kode SLA unik telah diperbarui.\n\nRincian per Kategori:\n{cat_text}"
        
        send_whatsapp_message(reply_chat_id, msg, session)
    except Exception as e:
        print(f"Error handling whatsapp command: {e}")

def process_message(message: dict):
    sender_chat_id = str(message.get("from", "") or "")
    sender_label = sender_chat_id.replace("@c.us", "").replace("@lid", "")
    reply_chat_id = resolve_reply_chat_id(message) or sender_chat_id
    msg_type = message.get("type") or message.get("_data", {}).get("type")
    session = message.get("_session", "default")
    
    # ANTI-BAN: Skip ALL status@broadcast messages (WhatsApp Stories).
    # These are irrelevant to SLA processing and flood the bot after reconnecting.
    if "status@broadcast" in sender_label or "status@broadcast" in sender_chat_id:
        return
    
    
    # ANTI-BAN: Skip messages during the grace period after login
    if session_ready_at > 0 and (time.time() - session_ready_at) < 60:
        return
    
    # ANTI-BAN: For group messages, do an early SLA-relevance check BEFORE any logging,
    # ID extraction, or DB writes. This prevents 8+ irrelevant group photos from
    # flooding the logs and generating unnecessary WAHA API calls.
    is_group = "@g.us" in sender_chat_id
    body = message.get("body", "")
    media_filename, media_mimetype = extract_media_metadata(message)
    is_xlsx_msg = bool(
        message.get("hasMedia")
        and (
            media_filename.lower().endswith(".xlsx")
            or "spreadsheetml" in media_mimetype
        )
    )
    if is_group:
        body_clean = body.strip().lower() if isinstance(body, str) else ""
        is_cmd = body_clean.startswith(("/rekap", "/undo", "/simpan", "/status opname", "/arsip", "/tagihan"))
        has_sla_code = message.get("hasMedia") and extract_kode_from_text(body)
        has_scan_trig = bool(extract_scan_opname_hint(body))
        if not is_cmd and not has_sla_code and not has_scan_trig and not is_xlsx_msg:
            return  # Silently drop irrelevant group messages
    
    print(f"\n--- New WAHA Message Received ---")
    print(f"Sender: {sender_chat_id or sender_label} | hasMedia: {message.get('hasMedia')}")
    
    message_id = extract_message_id(message)
    processing_key = message_id
    if not processing_key:
        print("WARNING: Could not extract WAHA message ID from webhook payload. Using fallback key for dedup only.")
        processing_key = f"fallback_{message.get('timestamp', time.time())}_{sender_label or sender_chat_id}"
        
    
    # Intercept WhatsApp Commands
    if body and isinstance(body, str):
        text_lower = body.strip().lower()
        if text_lower.startswith("/tagihan"):
            if not mark_processed(processing_key):
                return
            handle_tagihan_command(reply_chat_id, body, message, session)
            return
        if text_lower.startswith("/simpan"):
            if not mark_processed(processing_key):
                return
            handle_simpan_command(reply_chat_id, sender_label, body, session)
            return
        if text_lower.startswith("/status opname"):
            if not mark_processed(processing_key):
                return
            handle_status_opname_command(reply_chat_id, text_lower, session)
            return
        if text_lower.startswith("/arsip"):
            if not mark_processed(processing_key):
                return
            handle_arsip_command(reply_chat_id, body, session)
            return
        if text_lower.startswith("/undo"):
            if not mark_processed(processing_key):
                return
            handle_undo_command(reply_chat_id, body, session)
            return
        if text_lower.startswith("/rekap opname"):
            if not mark_processed(processing_key):
                return
            handle_rekap_opname_command(reply_chat_id, text_lower, session)
            return
        # FIX #4: Use startswith so custom ranges like "/rekap 6 juli" are also captured
        if text_lower.startswith("/rekap"):
            if not mark_processed(processing_key):
                return
            handle_whatsapp_command(reply_chat_id, text_lower, session)
            return
    
    # ATOMIC RACE-CONDITION LOCK: Immediately insert into DB.
    # If it's already there (rowcount == 0), another thread/webhook is already processing it!
    if not mark_processed(processing_key):
        print(f"Skipping duplicate message {processing_key}...")
        return

    # Route Scan Opname (signed paper photo / PDF -> OCR preview + pre-filled .xlsx -> /simpan)
    scan_hint = extract_scan_opname_hint(body if isinstance(body, str) else "")
    if scan_hint:
        process_opname_scan_message(
            message,
            reply_chat_id,
            sender_label,
            body if isinstance(body, str) else "",
            scan_hint,
            processing_key,
            session,
        )
        return

    # Route Standard .xlsx Opname Workbook Drop-In
    if is_xlsx_msg:
        try:
            xlsx_bytes = _extract_image_bytes_from_message(message)
        except Exception as dl_err:
            unmark_processed(processing_key)
            send_whatsapp_message(reply_chat_id, f"❌ Gagal mengunduh file Excel opname: {dl_err}", session)
            return
        handled = process_opname_xlsx_message(
            xlsx_bytes,
            media_filename,
            reply_chat_id,
            sender_label,
            body if isinstance(body, str) else "",
            processing_key,
            session,
        )
        if handled:
            return
        
    if message.get("hasMedia"):
        caption = message.get("body", "")
        
        # Hard filter to avoid consuming LLM API unnecessarily
        detected_kode = extract_kode_from_text(caption)
        if not detected_kode:
            # If they clearly attempted to submit an SLA but failed the regex format
            if "kode" in caption.lower():
                send_whatsapp_message(reply_chat_id, "⚠️ *Update Ditolak*\nFormat Kode tidak valid atau tidak dikenali oleh sistem. Harap pastikan format kode SLA benar (contoh: *Kode: 240523PV001*).", session)
            print(f"Skipping message {processing_key}: Caption does not contain a valid SLA code format.")
            return
        
        print(f"Message ID: {message_id or '[missing]'} | Caption: {caption}")
        
        timestamp_unix = message.get("timestamp", "")
        msg_datetime_str = ""
        if timestamp_unix:
            try:
                dt = datetime.datetime.fromtimestamp(int(timestamp_unix))
                msg_datetime_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                msg_datetime_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            msg_datetime_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        print("Step 1: Downloading photo via WAHA...")
        
        try:
            img_bytes = _extract_image_bytes_from_message(message)
            
            # 2. Process with AI Vision FIRST so we get the date/sheet name
            print("Step 2: Extracting AI data...")
            payload, err = extract_sla_data(img_bytes, caption, msg_datetime_str)
            
            if payload:
                # Post-processing: Correct 'metode_perbaikan' typos specifically for the "PV" sheet
                if payload.sheet_name == "PV" and payload.metode_perbaikan:
                    val = payload.metode_perbaikan.strip()
                    valid_methods = ["CnP", "Hotmix", "Coldmix", "Scrapmix", "Sealent", "Asphaltic Plug", "Marka"]
                    
                    # 1. Normalize character casing and symbols for comparison
                    lower_val = val.lower().replace(" ", "").replace("-", "").replace("_", "")
                    matched = None
                    
                    # 2. Try to find an exact case-insensitive match first
                    for m in valid_methods:
                        lower_m = m.lower().replace(" ", "").replace("-", "").replace("_", "")
                        if lower_val == lower_m:
                            matched = m
                            break
                    
                    # 3. If no exact match, fallback to smart keyword fuzzy matching
                    if not matched:
                        if "cool" in lower_val or "col" in lower_val or "cold" in lower_val:
                            matched = "Coldmix"
                        elif "hot" in lower_val or "hopt" in lower_val or "hoot" in lower_val:
                            matched = "Hotmix"
                        elif "scrap" in lower_val or "scrab" in lower_val:
                            matched = "Scrapmix"
                        elif "seal" in lower_val or "selent" in lower_val or "sealen" in lower_val or "sealant" in lower_val:
                            matched = "Sealent"
                        elif "plug" in lower_val or "asphaltic" in lower_val or "asphalt" in lower_val or "aspalt" in lower_val:
                            matched = "Asphaltic Plug"
                        elif "mark" in lower_val:
                            matched = "Marka"
                        elif "cnp" in lower_val:
                            matched = "CnP"
                    
                    # 4. Apply the corrected formal method name if matched
                    if matched:
                        print(f"🔧 Auto-corrected PV Metode: '{val}' -> '{matched}'")
                        payload.metode_perbaikan = matched
                
                try:
                    parsed_dt = datetime.datetime.strptime(payload.tanggal_perbaikan, '%Y-%m-%d %H:%M:%S')

                    # 1. Ambiguous day/month reconciliation:
                    # Resolve DD-MM-YYYY vs MM-DD-YYYY using WhatsApp message arrival time (0 extra AI tokens)
                    if msg_datetime_str:
                        try:
                            msg_dt = datetime.datetime.strptime(msg_datetime_str, '%Y-%m-%d %H:%M:%S')
                            reconciled_dt, was_swapped = reconcile_date_with_message_time(parsed_dt, msg_dt)
                            if was_swapped:
                                print(f"📅 Date auto-corrected: Swapped ambiguous day/month from {parsed_dt.strftime('%Y-%m-%d')} to {reconciled_dt.strftime('%Y-%m-%d')} based on WhatsApp message timestamp.")
                                parsed_dt = reconciled_dt
                                payload.tanggal_perbaikan = parsed_dt.strftime('%Y-%m-%d %H:%M:%S')
                        except Exception as dt_err:
                            print(f"Warning: Failed to reconcile date with message time: {dt_err}")

                    # 2. Safety net: if model returned 00:00:00, borrow the time component from the WhatsApp message timestamp
                    if parsed_dt.hour == 0 and parsed_dt.minute == 0 and parsed_dt.second == 0 and msg_datetime_str:
                        try:
                            fallback_dt = datetime.datetime.strptime(msg_datetime_str, '%Y-%m-%d %H:%M:%S')
                            parsed_dt = parsed_dt.replace(hour=fallback_dt.hour, minute=fallback_dt.minute, second=fallback_dt.second)
                            payload.tanggal_perbaikan = parsed_dt.strftime('%Y-%m-%d %H:%M:%S')
                            print(f"🕒 Fallback time applied: Replaced 00:00:00 with {parsed_dt.strftime('%H:%M:%S')} from message timestamp.")
                        except Exception:
                            pass

                    excel_date_formula = f"=DATE({parsed_dt.year},{parsed_dt.month},{parsed_dt.day})+TIME({parsed_dt.hour},{parsed_dt.minute},{parsed_dt.second})"
                    
                    months_id = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
                    month_name = months_id[parsed_dt.month - 1]
                    year_str = str(parsed_dt.year)
                    day_str = str(parsed_dt.day)
                except Exception:
                    excel_date_formula = payload.tanggal_perbaikan
                    month_name = "Unknown"
                    year_str = "Unknown"
                    day_str = "Unknown"
                    
                # 3. Upload to OneDrive dynamically
                folder_path = f"Dokumentasi SLA/{payload.sheet_name}/{year_str}/{month_name}/{day_str}"
                print(f"Step 3: Uploading to OneDrive at {folder_path}...")
                photo_link = upload_photo_to_onedrive(img_bytes, f"{payload.kode}.jpg", folder_path)
                
                # 4. Update Excel
                print(f"Step 4: Injecting into Excel (Kode: {payload.kode}, Sheet: {payload.sheet_name})...")
                update_excel_row(
                    share_url=settings.EXCEL_SHARE_LINK,
                    sheet_name=payload.sheet_name,
                    kode=payload.kode,
                    tanggal=excel_date_formula,
                    link=photo_link,
                    metode=payload.metode_perbaikan,
                    panjang=str(payload.panjang).replace(",", ".") if payload.panjang else "",
                    lebar=str(payload.lebar).replace(",", ".") if payload.lebar else "",
                    tebal=str(payload.tebal).replace(",", ".") if payload.tebal else ""
                )
                
                print("✅ Success!")
                send_whatsapp_message(reply_chat_id, f"✅ Update SLA berhasil!\nKode: {payload.kode}", session)
                
                # Log successful update into daily_updates tracking
                try:
                    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
                    conn = sqlite3.connect(settings.DB_URL)
                    c = conn.cursor()
                    c.execute("INSERT OR IGNORE INTO daily_updates (kode, date) VALUES (?, ?)", (payload.kode, today_str))
                    conn.commit()
                    conn.close()
                except Exception as log_err:
                    print(f"Error logging daily update: {log_err}")
            else:
                print(f"⚠️ Ignored non-SLA image or failed to extract data: {err}")
                send_whatsapp_message(reply_chat_id, f"⚠️ Ekstraksi data gagal untuk Kode *{detected_kode}*: {err}\nPastikan format teks dan gambar sudah sesuai.", session)
        except Exception as process_err:
            unmark_processed(processing_key)
            import traceback
            err_trace = traceback.format_exc()
            err_str = str(process_err)
            print(f"Error processing image:\n{err_trace}")
            
            # Provide specific, helpful error messages to the WhatsApp user
            if "not found in sheet" in err_str:
                reply_msg = f"❌ *Update Gagal*\nKode SLA *{detected_kode}* tidak ditemukan di dalam sheet Excel. Mohon periksa kembali apakah kodenya sudah benar."
            elif "504" in err_str or "Timeout" in err_str or "MaxRetryError" in err_str:
                reply_msg = f"⚠️ *Server Microsoft Sibuk*\nSistem gagal menghubungi file Excel karena server Microsoft sedang lambat/sibuk. Mohon tunggu 1 menit dan kirim ulang fotonya."
            elif "Token" in err_str or "401" in err_str:
                reply_msg = f"🔐 *Sesi Kedaluwarsa*\nSesi Microsoft Excel terputus. Sistem akan otomatis menyambung ulang, mohon kirim ulang fotonya."
            else:
                reply_msg = f"⚠️ *Kendala Teknis*\nTerjadi error sistem saat memproses Kode *{detected_kode}*. Mohon coba lagi atau lapor ke IT.\n\n_Pesan Error: {err_str[:100]}..._"
                
            send_whatsapp_message(reply_chat_id, reply_msg, session)
    else:
        # No media attached
        body = message.get("body", "")
        detected_kode = extract_kode_from_text(body)
        if detected_kode:
            send_whatsapp_message(reply_chat_id, f"⚠️ *Update Gagal untuk {detected_kode}*\nAnda mengirimkan teks tanpa foto. Harap kirimkan foto dokumentasi dengan caption kode tersebut.", session)
        elif "kode:" in body.lower() or "kode :" in body.lower():
            send_whatsapp_message(reply_chat_id, "⚠️ *Update Gagal*\nHarap kirimkan *foto dokumentasi* beserta caption dengan format Kode yang benar (contoh: *Kode: 240523PV001*).", session)

from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    # Retrieve current VPS hostname/IP dynamically from request headers
    host = request.headers.get("host", "")
    
    # Check if we are running in the production workspace (domain-based)
    if "astrainfrasolutions.id" in host:
        # Production reverse-proxied links (Nginx maps port 80/443 directly)
        waha_url = "https://waha.astrainfrasolutions.id"
        logs_url = "/logs"
        guide_url = "/guide"
    else:
        # Local / private VPS backup links
        ip_only = host.split(":")[0] if host else "129.225.9.167"
        waha_url = f"http://{ip_only}:3000"
        logs_url = f"http://{ip_only}:5001/logs"
        guide_url = f"http://{ip_only}:5001/guide"

    opname_excel_link = settings.OPNAME_EXCEL_SHARE_LINK or "#"
    opname_cycle_label = "siklus 26-25"
    if settings.OPNAME_AUTO_MONTHLY:
        try:
            conn_wb = sqlite3.connect(settings.DB_URL)
            latest_wb = conn_wb.execute(
                "SELECT cycle_key, web_url FROM opname_workbooks ORDER BY cycle_key DESC LIMIT 1"
            ).fetchone()
            conn_wb.close()
            if latest_wb and latest_wb[1]:
                opname_excel_link = latest_wb[1]
                opname_cycle_label = f"siklus {latest_wb[0]}"
        except Exception:
            pass

    html_content = f"""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VISTA Integration Console</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            body {{
                font-family: 'Plus Jakarta Sans', sans-serif;
                background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
                color: #f8fafc;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .container {{
                width: 100%;
                max-width: 900px;
                background: rgba(30, 41, 59, 0.5);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 24px;
                padding: 40px;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
            }}
            header {{
                text-align: center;
                margin-bottom: 40px;
            }}
            h1 {{
                font-size: 2.5rem;
                font-weight: 700;
                background: linear-gradient(to right, #38bdf8, #818cf8);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 10px;
            }}
            .subtitle {{
                color: #94a3b8;
                font-size: 1.1rem;
            }}
            .status-badge {{
                display: inline-flex;
                align-items: center;
                background: rgba(16, 185, 129, 0.1);
                color: #34d399;
                padding: 6px 16px;
                border-radius: 99px;
                font-size: 0.9rem;
                font-weight: 600;
                border: 1px solid rgba(52, 211, 153, 0.2);
                margin-top: 15px;
            }}
            .status-badge::before {{
                content: '';
                display: inline-block;
                width: 8px;
                height: 8px;
                background-color: #10b981;
                border-radius: 50%;
                margin-right: 8px;
                box-shadow: 0 0 8px #10b981;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 25px;
                margin-bottom: 30px;
            }}
            .card {{
                background: rgba(15, 23, 42, 0.4);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 18px;
                padding: 30px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                transition: transform 0.2s ease, border-color 0.2s ease;
            }}
            .card:hover {{
                transform: translateY(-4px);
                border-color: rgba(129, 140, 248, 0.3);
            }}
            .card-title {{
                font-size: 1.3rem;
                font-weight: 600;
                margin-bottom: 12px;
                color: #e2e8f0;
            }}
            .card-desc {{
                color: #94a3b8;
                font-size: 0.95rem;
                line-height: 1.5;
                margin-bottom: 25px;
                flex-grow: 1;
            }}
            .btn {{
                display: block;
                text-align: center;
                padding: 12px 20px;
                background: linear-gradient(to right, #4f46e5, #6366f1);
                color: #ffffff;
                text-decoration: none;
                border-radius: 12px;
                font-weight: 600;
                transition: opacity 0.2s ease;
            }}
            .btn:hover {{
                opacity: 0.9;
            }}
            .btn-secondary {{
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #e2e8f0;
            }}
            .btn-secondary:hover {{
                background: rgba(255, 255, 255, 0.12);
            }}
            footer {{
                text-align: center;
                color: #64748b;
                font-size: 0.85rem;
                margin-top: 30px;
            }}
            a.excel-btn {{
                background: linear-gradient(to right, #059669, #10b981);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>VISTA Integration Console</h1>
                <p class="subtitle">Console Manajemen Central untuk WAHA &amp; Python Bot</p>
                <div class="status-badge">Sistem Online</div>
            </header>
            
            <div class="grid">
                <!-- Card 1: WAHA Dashboard -->
                <div class="card">
                    <div>
                        <div class="card-title">WhatsApp Scanner</div>
                        <p class="card-desc">Gunakan ini untuk scan QR Code WhatsApp baru, memantau session engine, dan menghubungkan nomor mandor ke bot.</p>
                    </div>
                    <a href="{waha_url}" target="_blank" class="btn">Buka WAHA Dashboard</a>
                </div>

                <!-- Card 2: System Logs -->
                <div class="card">
                    <div>
                        <div class="card-title">System Log Terminal</div>
                        <p class="card-desc">Pantau aktivitas bot secara real-time. Bagus untuk memverifikasi proses update SLA, AI OCR, dan debug.</p>
                    </div>
                    <a href="{logs_url}" target="_blank" class="btn btn-secondary">Lihat Log Bot</a>
                </div>

                <!-- Card 3: MS Excel Link -->
                <div class="card">
                    <div>
                        <div class="card-title">Excel Spreadsheet</div>
                        <p class="card-desc">Buka dokumen Excel pusat yang sinkron dengan bot ini untuk melihat data progress SLA secara real-time.</p>
                    </div>
                    <a href="{settings.EXCEL_SHARE_LINK}" target="_blank" class="btn excel-btn">Buka Excel Online</a>
                </div>

                <!-- Card 3b: MS Excel Opname Link -->
                <div class="card">
                    <div>
                        <div class="card-title">Excel Opname (Volume)</div>
                        <p class="card-desc">Buka database volume opname bulanan ({opname_cycle_label}) yang terhubung ke tabel log &amp; matriks W1/W2.</p>
                    </div>
                    <a href="{opname_excel_link}" target="_blank" class="btn excel-btn">Buka Excel Opname</a>
                </div>

                <!-- Card 4: FAQ & Docs -->
                <div class="card">
                    <div>
                        <div class="card-title">Panduan &amp; FAQ</div>
                        <p class="card-desc">Buka dokumentasi lengkap cara ganti nomor WA, troubleshooting error SQLite/Docker, dan daftar perintah penting.</p>
                    </div>
                    <a href="{guide_url}" target="_blank" class="btn btn-secondary" style="background: linear-gradient(to right, #7c3aed, #8b5cf6);">Buka Panduan</a>
                </div>
            </div>

            <footer>
                <p>&copy; 2026 Project AIS-VISTA. Running on Oracle Ampere VPS (ARM64).</p>
            </footer>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/guide", response_class=HTMLResponse)
def get_guide(request: Request):
    # Retrieve current host dynamically to construct the back link and WAHA link
    host = request.headers.get("host", "")
    if "astrainfrasolutions.id" in host:
        waha_dash_link = "https://waha.astrainfrasolutions.id"
    else:
        ip_only = host.split(":")[0] if host else "129.225.9.167"
        waha_dash_link = f"http://{ip_only}:3000"
        
    html_content = f"""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>VISTA Bot Guide &amp; FAQ</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            body {{
                font-family: 'Plus Jakarta Sans', sans-serif;
                background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
                color: #f8fafc;
                min-height: 100vh;
                padding: 40px 20px;
                display: flex;
                flex-direction: column;
                align-items: center;
            }}
            .container {{
                width: 100%;
                max-width: 900px;
                background: rgba(30, 41, 59, 0.5);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 24px;
                padding: 40px;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
            }}
            header {{
                margin-bottom: 35px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding-bottom: 25px;
            }}
            .back-btn {{
                display: inline-flex;
                align-items: center;
                color: #38bdf8;
                text-decoration: none;
                font-weight: 600;
                font-size: 0.95rem;
                margin-bottom: 20px;
                transition: opacity 0.2s ease;
            }}
            .back-btn:hover {{
                opacity: 0.8;
            }}
            h1 {{
                font-size: 2.3rem;
                font-weight: 700;
                background: linear-gradient(to right, #38bdf8, #818cf8);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 8px;
            }}
            .subtitle {{
                color: #94a3b8;
                font-size: 1.05rem;
            }}
            .section {{
                margin-bottom: 35px;
            }}
            h2 {{
                font-size: 1.5rem;
                font-weight: 600;
                color: #e2e8f0;
                margin-bottom: 15px;
                display: flex;
                align-items: center;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                padding-bottom: 8px;
            }}
            h3 {{
                font-size: 1.15rem;
                font-weight: 600;
                color: #f1f5f9;
                margin: 20px 0 10px 0;
            }}
            p {{
                color: #94a3b8;
                font-size: 0.98rem;
                line-height: 1.6;
                margin-bottom: 12px;
            }}
            ul, ol {{
                margin-left: 25px;
                margin-bottom: 15px;
                color: #94a3b8;
                font-size: 0.98rem;
                line-height: 1.6;
            }}
            li {{
                margin-bottom: 8px;
            }}
            code {{
                font-family: monospace;
                background: rgba(15, 23, 42, 0.6);
                color: #f43f5e;
                padding: 2px 6px;
                border-radius: 6px;
                font-size: 0.9rem;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }}
            pre {{
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 12px;
                padding: 16px;
                margin: 15px 0;
                overflow-x: auto;
            }}
            pre code {{
                background: none;
                border: none;
                color: #38bdf8;
                padding: 0;
                font-size: 0.9rem;
            }}
            footer {{
                text-align: center;
                color: #64748b;
                font-size: 0.85rem;
                margin-top: 30px;
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                padding-top: 25px;
            }}
            .note {{
                background: rgba(56, 189, 248, 0.05);
                border-left: 4px solid #38bdf8;
                padding: 15px;
                border-radius: 4px 12px 12px 4px;
                margin: 20px 0;
            }}
            .note p {{
                margin-bottom: 0;
                color: #e2e8f0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <a href="/" class="back-btn">&larr; Kembali ke Konsol Utama</a>
                <h1>Panduan Penggunaan &amp; FAQ</h1>
                <p class="subtitle">Bantuan operasional, perintah penting, dan panduan troubleshooting sistem VISTA.</p>
            </header>

            <!-- Section 1 -->
            <div class="section">
                <h2>📱 Operasional Akun WhatsApp</h2>
                <h3>Cara Mengganti Nomor WhatsApp yang Terhubung</h3>
                <p>Jika Anda ingin mengganti nomor WhatsApp bot dengan nomor baru, ikuti prosedur aman berikut:</p>
                <ol>
                    <li><strong>Log out nomor lama:</strong> Di HP lama Anda, buka WhatsApp &rarr; <strong>Perangkat Tertaut (Linked Devices)</strong> &rarr; Pilih sesi WAHA &rarr; Klik <strong>Keluar (Log out)</strong>. (Atau gunakan tombol Logout di <a href="{waha_dash_link}" target="_blank" style="color: #38bdf8; text-decoration: none; font-weight: 600;">WAHA Dashboard</a>).</li>
                    <li><strong>Stop containers di VPS:</strong> Masuk ke SSH server, masuk ke folder <code>AIS-VISTA</code>, dan matikan layanannya:
                        <pre><code>docker-compose -f docker-compose.prod.yml down</code></pre>
                    </li>
                    <li><strong>Hapus file sesi lama:</strong> Hapus folder token lama untuk menghindari konflik data:
                        <pre><code>rm -rf waha_sessions/*</code></pre>
                    </li>
                    <li><strong>Nyalakan kembali:</strong>
                        <pre><code>docker-compose -f docker-compose.prod.yml up -d</code></pre>
                    </li>
                    <li><strong>Scan QR Code baru:</strong> Tunggu 10 detik agar engine GOWS inisialisasi, lalu buka Telegram bot Anda dan ketik <code>/qr</code>. Scan gambar QR yang dikirim bot menggunakan HP baru Anda.</li>
                </ol>
            </div>

            <!-- Section 2 -->
            <div class="section">
                <h2>🛠️ Troubleshooting &amp; Solusi Error</h2>
                
                <h3>1. Error: <code>sqlite3.OperationalError: unable to open database file</code></h3>
                <p><strong>Penyebab:</strong> Docker secara otomatis membuat <code>processed_messages.db</code> sebagai folder kosong karena filenya belum ada di VPS saat pertama kali dijalankan.</p>
                <p><strong>Solusi:</strong> Hapus folder palsu tersebut dan buat sebagai file kosong:</p>
                <pre><code>docker-compose -f docker-compose.prod.yml down
rm -rf processed_messages.db
touch processed_messages.db
docker-compose -f docker-compose.prod.yml up -d</code></pre>

                <h3>2. Error: <code>KeyError: 'ContainerConfig'</code></h3>
                <p><strong>Penyebab:</strong> Program <code>docker-compose</code> versi lama mengalami bug saat mencoba menimpa container yang sedang berjalan.</p>
                <p><strong>Solusi:</strong> Hapus container yang lama terlebih dahulu secara manual, baru nyalakan kembali:</p>
                <pre><code>docker rm -f $(docker ps -aq --filter name=waha) $(docker ps -aq --filter name=vista_bot)
docker-compose -f docker-compose.prod.yml up -d</code></pre>

                <h3>3. Error: <code>Unprotected Private Key File / Bad permissions</code></h3>
                <p><strong>Penyebab:</strong> SSH client di Windows mendeteksi file key <code>.key</code> Anda dapat diakses oleh akun user Windows lain dan menolak untuk membukanya.</p>
                <p><strong>Solusi (Gunakan Git Bash):</strong> Copy file key ke folder virtual <code>/tmp</code> di Git Bash yang secara otomatis mengunci izin akses file:</p>
                <pre><code>cp "/d/Users/muhammad.najih/Documents/AIS-VISTA/ssh-key-2026-07-22.key" /tmp/oracle.key
chmod 600 /tmp/oracle.key
ssh -o ServerAliveInterval=60 -i /tmp/oracle.key ubuntu@129.225.9.167</code></pre>
            </div>

            <!-- Section 3 -->
            <div class="section">
                <h2>📋 Perintah Penting (Cheat Sheet)</h2>
                <p>Gunakan perintah-perintah berikut langsung di folder <code>~/AIS-VISTA</code> pada terminal VPS Anda:</p>
                
                <h3>Memantau Log (Real-time)</h3>
                <ul>
                    <li>Melihat log Bot Python: <code>docker logs -f vista_bot</code></li>
                    <li>Melihat log WAHA WhatsApp: <code>docker logs -f waha</code></li>
                </ul>
                <div class="note">
                    <p>💡 <strong>Tips:</strong> Tekan tombol keyboard <code>Ctrl + C</code> untuk keluar dari tampilan log tanpa mematikan bot.</p>
                </div>

                <h3>Melihat Status Kontainer</h3>
                <ul>
                    <li>Melihat semua kontainer (termasuk yang mati): <code>docker ps -a</code></li>
                    <li>Melihat hanya kontainer yang aktif: <code>docker ps</code></li>
                </ul>

                <h3>Mengupdate Kode ke Versi Terbaru</h3>
                <p>Pilih file compose yang sesuai dengan arsitektur server Anda:</p>
                <pre><code>git pull
docker rm -f $(docker ps -aq --filter name=waha) $(docker ps -aq --filter name=vista_bot)

# On Office VPS (Intel/AMD):
docker-compose -f docker-compose.prod.yml up -d --build

# On Oracle Ampere VPS (ARM64):
docker-compose -f docker-compose.arm.yml up -d --build</code></pre>
            </div>

            <footer>
                <p>&copy; 2026 Project AIS-VISTA. Running on Oracle Ampere VPS (ARM64).</p>
            </footer>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/logs")
def get_logs(lines: int = 200):
    try:
        with open("vista_bot.log", "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return Response(content="".join(all_lines[-lines:]), media_type="text/plain")
    except Exception as e:
        return {"error": str(e)}

@app.post("/webhook")
async def webhook_event(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    try:
        # WAHA Webhook Payload
        if body.get("event") == "message":
            payload = body.get("payload", {})
            session = body.get("session", "default")
            
            # Ignore messages that the bot itself sent
            if payload.get("fromMe") == True:
                return {"status": "ignored"}
            
            # ANTI-BAN: Drop status@broadcast messages at the earliest possible point.
            # After reconnecting, WhatsApp dumps ALL accumulated Status Stories
            # (can be 30-100+ messages). Processing them overloads WAHA and
            # the burst of activity triggers WhatsApp's anti-bot detection.
            msg_from = payload.get("from", "")
            if "status@broadcast" in msg_from:
                return {"status": "ignored_status"}
                
            payload["_session"] = session
            background_tasks.add_task(process_message, payload)
                                
        return {"status": "success"}
    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5001, reload=True)
