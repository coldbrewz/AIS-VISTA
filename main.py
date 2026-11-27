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
    has_xlsx_opname_trigger,
    normalize_opname_batch,
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
    fuzzy_fix_ic_akses_typo,
    normalize_asset_code,
    normalize_vendor,
    resolve_boq_item,
    resolve_wilayah,
)
from services.opname_xlsx import (
    MONTH_INDEX_TO_ABBR,
    XlsxSlotBatch,
    build_prefilled_standard_xlsx,
    compute_geom_volume,
    compute_strict_dim_volume,
    parse_standard_opname_xlsx,
    to_float_num,
)
from services.whatsapp import send_whatsapp_document, send_whatsapp_message
from services.microsoft import (
    OPNAME_MONTH_NAMES,
    append_opname_rows,
    delete_opname_rows_by_id,
    download_file_by_path_from_onedrive,
    download_file_from_onedrive,
    download_share_file_from_onedrive,
    ensure_monthly_opname_workbook,
    replace_opname_slot_rows,
    update_excel_row,
    upload_file_to_onedrive,
    upload_photo_to_onedrive,
    upload_private_file_to_onedrive,
)
from services.opname_roster import (
    ensure_roster_tables,
    get_active_roster,
    pull_roster_from_onedrive,
)
from services.opname_web import (
    build_review_url,
    create_opname_web_router,
    make_opname_token,
)
from services.opname_web_ui import (
    render_console_page_html,
    render_guide_page_html,
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

async def _auto_restore_roster_from_onedrive():
    try:
        ok, note = await asyncio.to_thread(
            pull_roster_from_onedrive,
            settings.DB_URL,
            download_file_by_path_from_onedrive,
            True,
        )
        if ok:
            print(f"ROSTER SYNC: {note}")
    except Exception as e:
        print(f"ROSTER SYNC: skipped ({e})")


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
        asyncio.create_task(_auto_restore_roster_from_onedrive())
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
                 created_at TEXT,
                 reply_chat_id TEXT DEFAULT '',
                 session TEXT DEFAULT 'default',
                 sender_label TEXT DEFAULT ''
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS opname_slots (
                 slot_id TEXT PRIMARY KEY,
                 cycle_key TEXT,
                 aset TEXT,
                 wilayah TEXT,
                 vendor TEXT,
                 minggu TEXT,
                 payload_json TEXT,
                 source_json TEXT DEFAULT '',
                 xlsx_json TEXT DEFAULT '',
                 reply_chat_id TEXT DEFAULT '',
                 session TEXT DEFAULT 'default',
                 sender_label TEXT DEFAULT '',
                 status TEXT DEFAULT 'ACTIVE',
                 updated_at TEXT
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
    c.execute('''CREATE TABLE IF NOT EXISTS opname_deferred_disposal (
                 defer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                 source_slot_id TEXT,
                 cycle_key TEXT,
                 aset TEXT,
                 wilayah TEXT,
                 vendor TEXT,
                 tanggal TEXT,
                 lokasi TEXT,
                 item_key TEXT,
                 keyword TEXT,
                 volume REAL,
                 satuan TEXT,
                 keterangan TEXT,
                 status TEXT DEFAULT 'PENDING',
                 created_at TEXT
                 )''')
    # Upgrade older schemas gracefully if columns missing
    existing_cols = {row[1] for row in c.execute("PRAGMA table_info(opname_entries)").fetchall()}
    if "drive_id" not in existing_cols:
        c.execute("ALTER TABLE opname_entries ADD COLUMN drive_id TEXT DEFAULT ''")
    if "item_id" not in existing_cols:
        c.execute("ALTER TABLE opname_entries ADD COLUMN item_id TEXT DEFAULT ''")
    pending_cols = {row[1] for row in c.execute("PRAGMA table_info(opname_pending)").fetchall()}
    if "reply_chat_id" not in pending_cols:
        c.execute("ALTER TABLE opname_pending ADD COLUMN reply_chat_id TEXT DEFAULT ''")
    if "session" not in pending_cols:
        c.execute("ALTER TABLE opname_pending ADD COLUMN session TEXT DEFAULT 'default'")
    if "sender_label" not in pending_cols:
        c.execute("ALTER TABLE opname_pending ADD COLUMN sender_label TEXT DEFAULT ''")
    arc_cols = {row[1] for row in c.execute("PRAGMA table_info(opname_archives)").fetchall()}
    if "item_id" not in arc_cols:
        c.execute("ALTER TABLE opname_archives ADD COLUMN item_id TEXT DEFAULT ''")
    if "web_url" not in arc_cols:
        c.execute("ALTER TABLE opname_archives ADD COLUMN web_url TEXT DEFAULT ''")
    conn.commit()
    conn.close()
    ensure_roster_tables(settings.DB_URL)

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
                        "tanggal_temuan": e.get("tanggal_temuan", e.get("kode_temuan", "-")),
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
                        "hasil_baik": e.get("hasil_baik"),
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
    reply_chat_id: str = "",
    session: str = "default",
) -> list[dict]:
    if not settings.OPNAME_EXCEL_SHARE_LINK:
        raise Exception("`OPNAME_EXCEL_SHARE_LINK` belum diatur di server bot.")

    results = []
    created_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    archive_ref = next((it.get("web_url") for _, it in archive_items if it.get("web_url")), "-")
    src_arch_json = ""
    xls_arch_json = ""
    for f_src_type, arc in archive_items:
        if f_src_type == "SCAN_SRC" and arc and not src_arch_json:
            src_arch_json = json.dumps(arc)
        elif f_src_type in ("XLSX", "WEB_EDITOR") and arc and not xls_arch_json:
            xls_arch_json = json.dumps(arc)
    active_slots: list[tuple[dict, list[dict], list[dict]]] = []
    for sl in slots_data:
        active_ents = [
            e
            for e in (sl.get("entries") or [])
            if str(e.get("row_action") or "").strip().upper() != "REMOVED"
        ]
        if active_ents:
            disp_rows: list[dict] = []
            disp_seen: set[tuple[str, str, str]] = set()
            for is_explicit, src_list in ((False, sl.get("entries") or []), (True, sl.get("deferred_disposals") or [])):
                for de in src_list:
                    if not isinstance(de, dict):
                        continue
                    is_rem = is_explicit or str(de.get("row_action") or "").strip().upper() == "REMOVED"
                    rem_rsn = str(de.get("removal_reason") or "").strip().upper()
                    ket_low = str(de.get("keterangan") or "").lower()
                    if is_rem and (rem_rsn == "DISPOSAL" or "disposal" in ket_low):
                        dk = (
                            str(de.get("tanggal") or ""),
                            str(de.get("lokasi") or "-").strip().upper(),
                            str(de.get("item_key") or ""),
                        )
                        if dk[2] and dk not in disp_seen:
                            disp_seen.add(dk)
                            disp_rows.append(de)
            active_slots.append((sl, active_ents, disp_rows))
    if not active_slots:
        raise ValueError("Minimal 1 baris aktif wajib ada untuk disimpan ke DATA_UNTUK_VOL.")

    for sl, entries, disposal_rows in active_slots:
        slot_id = sl["slot_id"]
        cycle_key = sl["cycle_key"]
        cycle_m = int(sl["cycle_month"])
        cycle_y = int(sl["cycle_year"])
        aset = sl["aset"]
        wilayah = sl["wilayah"]
        vendor = sl["vendor"]
        minggu = sl["minggu"]
        table_name = sl["table_name"]

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
            ent_loc_u = str(ent.get("lokasi") or "-").strip().upper()
            c.execute(
                """
                UPDATE opname_deferred_disposal
                SET status = 'RESOLVED'
                WHERE status = 'PENDING'
                  AND aset = ?
                  AND wilayah = ?
                  AND vendor = ?
                  AND item_key = ?
                  AND UPPER(COALESCE(source_slot_id, '')) != ?
                  AND (UPPER(COALESCE(lokasi, '-')) = ? OR tanggal = ?)
                """,
                (aset, wilayah, vendor, ent["item_key"], slot_id.upper(), ent_loc_u, ent["tanggal"]),
            )
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
        for de in disposal_rows:
            de_tgl = str(de.get("tanggal") or "")
            de_loc = str(de.get("lokasi") or "-").strip() or "-"
            de_ik = str(de.get("item_key") or "")
            dup = c.execute(
                """
                SELECT defer_id FROM opname_deferred_disposal
                WHERE UPPER(source_slot_id) = ? AND tanggal = ? AND UPPER(lokasi) = ? AND item_key = ? AND status = 'PENDING'
                """,
                (slot_id.upper(), de_tgl, de_loc.upper(), de_ik),
            ).fetchone()
            if not dup:
                de_vol = to_float_num(de.get("vol_vendor"))
                if de_vol is None:
                    de_vol = to_float_num(de.get("volume")) or 0.0
                c.execute(
                    """
                    INSERT INTO opname_deferred_disposal (
                        source_slot_id, cycle_key, aset, wilayah, vendor, tanggal, lokasi,
                        item_key, keyword, volume, satuan, keterangan, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                    """,
                    (
                        slot_id,
                        cycle_key,
                        aset,
                        wilayah,
                        vendor,
                        de_tgl,
                        de_loc,
                        de_ik,
                        str(de.get("keyword") or de_ik),
                        float(de_vol),
                        str(de.get("satuan") or ""),
                        str(de.get("keterangan") or "disposal"),
                        created_now,
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
        existing_slot = c.execute(
            "SELECT COALESCE(source_json, ''), COALESCE(reply_chat_id, ''), COALESCE(session, 'default') FROM opname_slots WHERE UPPER(slot_id) = ?",
            (slot_id.upper(),),
        ).fetchone()
        slot_src_json = src_arch_json or (existing_slot[0] if existing_slot else "")
        slot_reply_chat = reply_chat_id or (existing_slot[1] if existing_slot else "")
        slot_session = session or (existing_slot[2] if existing_slot else "default")
        c.execute(
            """
            INSERT OR REPLACE INTO opname_slots (
                slot_id, cycle_key, aset, wilayah, vendor, minggu, payload_json,
                source_json, xlsx_json, reply_chat_id, session, sender_label, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
            """,
            (
                slot_id,
                cycle_key,
                aset,
                wilayah,
                vendor,
                minggu,
                json.dumps(sl),
                slot_src_json,
                xls_arch_json,
                slot_reply_chat,
                slot_session,
                sender_label,
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
        print(
            f"[Opname Commit] {slot_id} ({source_type}) -> {table_name} | "
            f"replaced={deleted_cnt} appended={appended_cnt}"
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
        edit_url = build_review_url(settings.PUBLIC_BASE_URL, res["slot_id"])
        edit_line = f"\n✏️ Edit ulang (HP/PC): {edit_url}" if edit_url else ""
        blocks.append(
            f"\nID: `{res['slot_id']}` ({action_note})\n"
            f"Siklus: {month_names[cycle_m - 1]} {cycle_y} | Opname: *{res['minggu']}*\n"
            f"Aset / Wilayah / Vendor: *{res['aset']}* / *{res['wilayah']}* / *{res['vendor']}*\n"
            f"Total Baris: {res['appended']}\n"
            f"{item_lines}{edit_line}\n"
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
    reply_chat_id: str = "",
    session: str = "default",
    sender_label: str = "",
) -> None:
    conn = sqlite3.connect(settings.DB_URL)
    conn.execute(
        """
        INSERT OR REPLACE INTO opname_pending (
            pending_id, kind, aset, payload_json, xlsx_path, source_path, warnings_text,
            status, created_at, reply_chat_id, session, sender_label
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?)
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
            reply_chat_id,
            session,
            sender_label,
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
    print(f"[Opname /simpan] Confirming {pending_id} by {sender_label}")
    conn = sqlite3.connect(settings.DB_URL)
    row = conn.execute(
        "SELECT kind, aset, payload_json, xlsx_path, source_path, status FROM opname_pending WHERE UPPER(pending_id) = ?",
        (pending_id,),
    ).fetchone()
    conn.close()
    if not row:
        print(f"[Opname /simpan] Not found: {pending_id}")
        send_whatsapp_message(reply_chat_id, f"⚠️ ID staging `{pending_id}` tidak ditemukan.", session)
        return
    kind, _aset, payload_json, xlsx_path, source_path, status = row
    if status != "PENDING":
        print(f"[Opname /simpan] Skipped {pending_id}: already {status}")
        send_whatsapp_message(reply_chat_id, f"⚠️ Data `{pending_id}` sudah diproses sebelumnya (`{status}`).", session)
        return

    slots_data = json.loads(payload_json)
    archive_items = []
    if source_path:
        archive_items.append(("SCAN_SRC", json.loads(source_path)))
    if xlsx_path:
        archive_items.append(("XLSX", json.loads(xlsx_path)))

    try:
        results = _commit_opname_slots(
            slots_data,
            sender_label,
            kind,
            archive_items,
            reply_chat_id=reply_chat_id,
            session=session,
        )
    except Exception as e:
        print(f"[Opname /simpan] Failed {pending_id}: {e}")
        send_whatsapp_message(reply_chat_id, f"❌ Gagal menyimpan `{pending_id}` ke OneDrive: {e}", session)
        return

    conn = sqlite3.connect(settings.DB_URL)
    conn.execute("UPDATE opname_pending SET status = 'CONFIRMED' WHERE UPPER(pending_id) = ?", (pending_id,))
    conn.commit()
    conn.close()
    print(f"[Opname /simpan] Confirmed {pending_id} -> {', '.join(r['slot_id'] for r in results)}")
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

    active_roster = get_active_roster(settings.DB_URL)
    lines = [f"📋 *STATUS OPNAME ROSTER ({cycle_y:04d}-{cycle_m:02d}, {len(active_roster)} Slot)*\n"]
    done_cnt = 0
    for aset, vend, wil in active_roster:
        wks = sorted(by_slot.get((aset, wil, vend), set()))
        if wks:
            done_cnt += 1
            lines.append(f"✅ {aset} | {wil} | {vend} : {', '.join(wks)}")
        else:
            lines.append(f"⏳ {aset} | {wil} | {vend} : belum ada")
    lines.append(f"\nTerisi: *{done_cnt}/{len(active_roster)}* slot.")
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
        c.execute(
            "UPDATE opname_slots SET status = 'VOID', updated_at = ? WHERE UPPER(slot_id) = ?",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), opname_id),
        )
        conn.commit()
        conn.close()
        print(f"[Opname /undo] Voided {opname_id} in {table_name} (deleted={deleted})")
        send_whatsapp_message(
            reply_chat_id,
            f"🗑️ *Opname Dibatalkan*\nID: `{opname_id}`\nBaris dihapus di `{table_name}`: {deleted}",
            session,
        )
    except Exception as e:
        conn.close()
        print(f"[Opname /undo] Failed {opname_id}: {e}")
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


def _record_tagihan_archive(slot_id: str, cycle_key: str, source_type: str, arc_info: dict, sheet_count: int) -> int:
    conn = sqlite3.connect(settings.DB_URL)
    cur = conn.execute(
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
    row_id = int(cur.lastrowid or 0)
    conn.commit()
    conn.close()
    return row_id


def save_tagihan_baseline(cycle_m: int, cycle_y: int, tmpl_filename: str, tmpl_bytes: bytes) -> dict:
    if not settings.OPNAME_ENABLED:
        raise ValueError("Fitur opname/tagihan sedang dinonaktifkan.")
    if not settings.OPNAME_EXCEL_SHARE_LINK:
        raise ValueError("`OPNAME_EXCEL_SHARE_LINK` belum dikonfigurasi di server bot.")
    if not tmpl_bytes:
        raise ValueError("File template MC tidak boleh kosong.")

    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    cycle_key = f"{cycle_y:04d}-{cycle_m:02d}"
    month_label = OPNAME_MONTH_NAMES.get(cycle_m, f"{cycle_m:02d}")
    next_m, next_y = (1, cycle_y + 1) if cycle_m == 12 else (cycle_m + 1, cycle_y)
    safe_name = tmpl_filename or f"MC-{cycle_m:02d}.xlsx"
    base_arc = _archive_opname_file_to_onedrive(cycle_key, "Tagihan", safe_name, tmpl_bytes, xlsx_mime)
    archive_id = _record_tagihan_archive(f"TAGIHAN-{cycle_key}", cycle_key, "TAGIHAN_OUTPUT", base_arc, 0)
    print(f"[Opname Tagihan] Saved baseline {cycle_key} | file={base_arc.get('filename', safe_name)}", flush=True)
    return {
        "cycle_key": cycle_key,
        "month_label": month_label,
        "next_cycle_key": f"{next_y:04d}-{next_m:02d}",
        "archive_id": archive_id,
        "filename": base_arc.get("filename", safe_name),
        "web_url": base_arc.get("web_url", ""),
        "item_id": base_arc.get("item_id", ""),
    }


def run_tagihan_generation(
    cycle_m: int,
    cycle_y: int,
    tmpl_bytes: bytes = b"",
    tmpl_filename: str = "",
) -> dict:
    if not settings.OPNAME_ENABLED:
        raise ValueError("Fitur opname/tagihan sedang dinonaktifkan.")
    if not settings.OPNAME_EXCEL_SHARE_LINK:
        raise ValueError("`OPNAME_EXCEL_SHARE_LINK` belum dikonfigurasi di server bot.")

    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    cycle_key = f"{cycle_y:04d}-{cycle_m:02d}"
    month_label = OPNAME_MONTH_NAMES.get(cycle_m, f"{cycle_m:02d}")
    prev_m, prev_y = (12, cycle_y - 1) if cycle_m == 1 else (cycle_m - 1, cycle_y)
    prev_cycle_key = f"{prev_y:04d}-{prev_m:02d}"
    rollover_prev = False

    if tmpl_bytes:
        tmpl_m, tmpl_y = parse_tagihan_cycle("", template_filename=tmpl_filename, default_cycle=(cycle_m, cycle_y))
        if (tmpl_m, tmpl_y) == (prev_m, prev_y):
            rollover_prev = True
            try:
                base_arc = _archive_opname_file_to_onedrive(prev_cycle_key, "Tagihan", tmpl_filename, tmpl_bytes, xlsx_mime)
                _record_tagihan_archive(f"TAGIHAN-{prev_cycle_key}", prev_cycle_key, "TAGIHAN_OUTPUT", base_arc, 0)
            except Exception as cache_err:
                print(f"Warning: Gagal arsip baseline Tagihan ke OneDrive: {cache_err}")
        else:
            try:
                tmpl_arc = _archive_opname_file_to_onedrive(cycle_key, "Tagihan", tmpl_filename, tmpl_bytes, xlsx_mime)
                _record_tagihan_archive(f"TAGIHAN-TMPL-{cycle_key}", cycle_key, "TAGIHAN_TEMPLATE", tmpl_arc, 0)
            except Exception as cache_err:
                print(f"Warning: Gagal arsip template Tagihan ke OneDrive: {cache_err}")
    else:
        conn = sqlite3.connect(settings.DB_URL)
        prev_out_row = conn.execute(
            """
            SELECT file_path, COALESCE(item_id, '')
            FROM opname_archives
            WHERE source_type = 'TAGIHAN_OUTPUT' AND cycle_key = ? AND item_id != ''
            ORDER BY archive_id DESC
            LIMIT 1
            """,
            (prev_cycle_key,),
        ).fetchone()
        if prev_out_row and prev_out_row[1]:
            conn.close()
            try:
                tmpl_bytes = download_file_from_onedrive(prev_out_row[1])
                tmpl_filename = prev_out_row[0] or f"MC-{prev_m:02d}.xlsx"
                rollover_prev = True
            except Exception as dl_err:
                print(f"Warning: Gagal unduh Tagihan bulan sebelumnya {prev_out_row[1]}: {dl_err}")
                tmpl_bytes = b""
        else:
            row = conn.execute(
                """
                SELECT file_path, COALESCE(item_id, ''), cycle_key
                FROM opname_archives
                WHERE source_type = 'TAGIHAN_TEMPLATE' AND item_id != ''
                ORDER BY (CASE WHEN cycle_key = ? THEN 0 ELSE 1 END), archive_id DESC
                LIMIT 1
                """,
                (cycle_key,),
            ).fetchone()
            latest_out_row = conn.execute(
                """
                SELECT cycle_key
                FROM opname_archives
                WHERE source_type = 'TAGIHAN_OUTPUT' AND item_id != ''
                ORDER BY cycle_key DESC, archive_id DESC
                LIMIT 1
                """
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
                    raise RuntimeError(f"Gagal mengunduh `TAGIHAN_TEMPLATE_SHARE_LINK`: {share_err}") from share_err

            if not tmpl_bytes:
                if latest_out_row and latest_out_row[0] and latest_out_row[0] < prev_cycle_key:
                    ly, lm = map(int, latest_out_row[0].split("-"))
                    nx_m, nx_y = (1, ly + 1) if lm == 12 else (lm + 1, ly)
                    raise ValueError(
                        f"⚠️ Baseline Tagihan terakhir tersimpan pada `{latest_out_row[0]}` (`{prev_cycle_key}` belum ada).\n"
                        f"Jalankan `/tagihan {nx_y:04d}-{nx_m:02d}` secara berurutan agar `S.D. BULAN LALU` terakumulasi otomatis, "
                        f"atau lampirkan file `MC-{cycle_m:02d}.xlsx` bersama caption `/tagihan {cycle_key}`."
                    )
                raise ValueError(
                    "⚠️ Template `MC` belum tersedia.\n"
                    "Kirim file `MC` terakhir dengan caption `/tagihan base <YYYY-MM>` (untuk rollover otomatis bulan-bulan berikutnya), "
                    "atau kirim template bulan ini bersama caption `/tagihan`."
                )

    try:
        if settings.OPNAME_AUTO_MONTHLY:
            try:
                _di, drv_id, itm_id = _resolve_cycle_target_di(cycle_m, cycle_y)
                vista_bytes = download_file_from_onedrive(itm_id, drive_id=drv_id)
            except Exception:
                conn_wb = sqlite3.connect(settings.DB_URL)
                conn_wb.execute("DELETE FROM opname_workbooks WHERE cycle_key = ?", (cycle_key,))
                conn_wb.commit()
                conn_wb.close()
                _di, drv_id, itm_id = _resolve_cycle_target_di(cycle_m, cycle_y)
                vista_bytes = download_file_from_onedrive(itm_id, drive_id=drv_id)
        else:
            vista_bytes, _ = download_share_file_from_onedrive(settings.OPNAME_EXCEL_SHARE_LINK)
    except Exception as silo_err:
        raise RuntimeError(
            f"Gagal mengambil `DATA_UNTUK_VOL_{month_label}_{cycle_y}.xlsx` dari OneDrive: {silo_err}"
        ) from silo_err

    try:
        res = generate_tagihan_workbook(
            vista_bytes,
            tmpl_bytes,
            cycle_m,
            cycle_y,
            rollover_previous_month=rollover_prev,
        )
    except Exception as gen_err:
        raise ValueError(f"Gagal membuat file Tagihan MC ({cycle_key}): {gen_err}") from gen_err

    out_bytes = res["output_bytes"]
    out_filename = res["output_filename"]
    try:
        out_arc = _archive_opname_file_to_onedrive(cycle_key, "Tagihan", out_filename, out_bytes, xlsx_mime)
        archive_id = _record_tagihan_archive(
            f"TAGIHAN-{cycle_key}", cycle_key, "TAGIHAN_OUTPUT", out_arc, len(res["ordered_sheets"])
        )
    except Exception as arch_err:
        raise RuntimeError(f"Gagal mengunggah hasil Tagihan ke OneDrive: {arch_err}") from arch_err

    print(
        f"[Opname Tagihan] Generated {cycle_key} | file={out_filename} | total=Rp {res['total_grand']:,.2f} | rollover={bool(res.get('rollover_applied'))}",
        flush=True,
    )
    return {
        "cycle_key": cycle_key,
        "prev_cycle_key": prev_cycle_key,
        "month_label": month_label,
        "output_filename": out_filename,
        "output_bytes": out_bytes,
        "web_url": out_arc.get("web_url", ""),
        "item_id": out_arc.get("item_id", ""),
        "archive_id": archive_id,
        "rollover_applied": bool(res.get("rollover_applied")),
        "ordered_sheets": list(res["ordered_sheets"]),
        "grand_totals": dict(res["grand_totals"]),
        "total_grand": float(res["total_grand"]),
        "warnings": list(res["warnings"]),
    }


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
    is_base_cmd = bool(re.match(r"^/tagihan\s+base\b", body_text.strip(), re.IGNORECASE))

    tmpl_bytes = b""
    tmpl_filename = ""
    if has_xlsx_attachment:
        try:
            tmpl_bytes = _extract_image_bytes_from_message(message)
            tmpl_filename = media_filename or "MC_TEMPLATE.xlsx"
        except Exception as dl_err:
            send_whatsapp_message(reply_chat_id, f"❌ Gagal mengunduh file template MC: {dl_err}", session)
            return

    if is_base_cmd:
        if not has_xlsx_attachment:
            send_whatsapp_message(
                reply_chat_id,
                "⚠️ Lampirkan file `MC` terakhir (misal `MC-9 MENCARI VOLUME.xlsx`) bersama caption `/tagihan base 2026-09`.",
                session,
            )
            return
        base_m, base_y = parse_tagihan_cycle(
            re.sub(r"^/tagihan\s+base\b", "/tagihan", body_text, flags=re.IGNORECASE),
            template_filename=tmpl_filename,
        )
        try:
            base_res = save_tagihan_baseline(base_m, base_y, tmpl_filename, tmpl_bytes)
        except Exception as arch_err:
            send_whatsapp_message(reply_chat_id, f"❌ Gagal menyimpan baseline Tagihan ke OneDrive: {arch_err}", session)
            return
        send_whatsapp_message(
            reply_chat_id,
            f"✅ *Baseline Tagihan `{base_res['month_label']} {base_y}` Tersimpan*\n"
            f"File: `{base_res['filename']}`\n"
            f"🔗 {base_res['web_url']}\n\n"
            f"Untuk membuat tagihan bulan berikutnya dengan auto-rollover `S.D. BULAN LALU`, ketik:\n"
            f"`/tagihan {base_res['next_cycle_key']}`",
            session,
        )
        return

    cycle_m, cycle_y = parse_tagihan_cycle(body_text, template_filename=tmpl_filename)
    try:
        res = run_tagihan_generation(cycle_m, cycle_y, tmpl_bytes=tmpl_bytes, tmpl_filename=tmpl_filename)
    except ValueError as val_err:
        msg = str(val_err)
        send_whatsapp_message(reply_chat_id, msg if msg.startswith(("⚠️", "❌")) else f"❌ {msg}", session)
        return
    except RuntimeError as run_err:
        send_whatsapp_message(reply_chat_id, f"❌ {run_err}", session)
        return

    gt_lines = "\n".join(
        f"• {s}: Rp {res['grand_totals'][s]:,.2f}"
        for s in res["ordered_sheets"]
        if res["grand_totals"].get(s, 0.0) > 0
    ) or "• Belum ada volume opname > 0 pada siklus ini."
    roll_note = f"\n🔄 Rollover `S.D. BULAN LALU`: dari `{res['prev_cycle_key']}`" if res.get("rollover_applied") else ""
    warn_block = ""
    if res["warnings"]:
        warn_block = "\n\n⚠️ *Catatan:*\n" + "\n".join(f"- {w}" for w in res["warnings"][:5])
    caption = (
        f"📑 *Tagihan MC Selesai (`{res['month_label']} {cycle_y}`)*{roll_note}\n"
        f"Total Pilar 1 (sheet aktif): *Rp {res['total_grand']:,.2f}*\n\n"
        f"{gt_lines}{warn_block}\n\n"
        f"🔗 {res.get('web_url', '')}"
    )
    send_whatsapp_document(
        reply_chat_id,
        res["output_bytes"],
        res["output_filename"],
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

    print(f"[Opname XLSX] Start | file={filename or '-'} | bytes={len(file_bytes)} | sender={sender_label}")
    res = parse_standard_opname_xlsx(file_bytes, filename=filename, caption=caption)
    if not res.is_standard_form:
        print(f"[Opname XLSX] Ignored (not standard opname workbook): {filename or '-'}")
        return False

    if res.errors:
        print(f"[Opname XLSX] Rejected ({len(res.errors)} error(s)): {'; '.join(res.errors[:5])}")
        err_txt = "\n".join(f"- {e}" for e in res.errors[:12])
        send_whatsapp_message(reply_chat_id, f"⚠️ *File Excel Opname Ditolak*\n{err_txt}", session)
        return True

    first_sl = res.slots[0]
    total_rows = sum(len(s.entries) for s in res.slots)
    print(f"[Opname XLSX] Parsed {len(res.slots)} slot(s), {total_rows} row(s) -> archiving to OneDrive...")
    arch_name = filename or f"{first_sl.slot_id}.xlsx"
    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    try:
        xlsx_arch_info = _archive_opname_file_to_onedrive(
            first_sl.cycle_key, first_sl.aset, arch_name, file_bytes, xlsx_mime
        )
    except Exception as arch_err:
        unmark_processed(processing_key)
        print(f"[Opname XLSX] Archive failed: {arch_err}")
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
            reply_chat_id=reply_chat_id,
            session=session,
            sender_label=sender_label,
        )
        print(f"[Opname XLSX] Staged pending confirmation {conf_id} ({len(res.roster_warnings)} warning(s))")
        warn_txt = "\n".join(f"• {w}" for w in res.roster_warnings)
        slot_txt = ", ".join(s["slot_id"] for s in slots_data)
        review_link = build_review_url(settings.PUBLIC_BASE_URL, conf_id)
        link_block = f"\n\n🌐 Review / edit lewat HP & PC:\n{review_link}" if review_link else ""
        send_whatsapp_message(
            reply_chat_id,
            f"⚠️ *Butuh Konfirmasi Roster ({conf_id})*\n"
            f"Slot terdeteksi: `{slot_txt}`\n"
            f"{warn_txt}\n\n"
            f"Tetap simpan data ini ke DATA UNTUK VOL? Ketik:\n`/simpan {conf_id}`{link_block}",
            session,
        )
        return True

    try:
        results = _commit_opname_slots(
            slots_data,
            sender_label,
            "XLSX",
            [("XLSX", xlsx_arch_info)],
            reply_chat_id=reply_chat_id,
            session=session,
        )
    except Exception as e:
        unmark_processed(processing_key)
        print(f"[Opname XLSX] Commit failed: {e}")
        send_whatsapp_message(reply_chat_id, f"❌ Gagal menulis data Excel ke OneDrive: {e}", session)
        return True

    print(f"[Opname XLSX] Done | committed {len(results)} slot(s): {', '.join(r['slot_id'] for r in results)}")
    send_whatsapp_message(reply_chat_id, _format_commit_reply(results, "Excel Form"), session)
    return True


def _load_baseline_slot_entries(
    aset: str,
    wilayah: str,
    vendor: str,
    minggu: str,
    cycle_key: str,
) -> tuple[str, list[dict]]:
    if not (aset and wilayah in ("W1", "W2") and vendor and re.fullmatch(r"\d{4}-\d{2}", cycle_key or "")):
        return "", []
    yy = int(cycle_key[:4]) % 100
    mm = int(cycle_key[5:7])
    candidate_ids: list[str] = []
    if minggu:
        candidate_ids.append(f"XLS-{yy:02d}{mm:02d}-{aset}-{wilayah}-{vendor}-{minggu}")
    full_id = f"XLS-{yy:02d}{mm:02d}-{aset}-{wilayah}-{vendor}-FULL"
    if full_id not in candidate_ids:
        candidate_ids.append(full_id)

    conn = sqlite3.connect(settings.DB_URL)
    try:
        for cand in candidate_ids:
            row = conn.execute(
                "SELECT slot_id, payload_json FROM opname_slots WHERE UPPER(slot_id) = ? AND status = 'ACTIVE'",
                (cand.upper(),),
            ).fetchone()
            if row and row[1]:
                try:
                    sl = json.loads(row[1])
                except Exception:
                    sl = {}
                if isinstance(sl, list):
                    sl = sl[0] if sl else {}
                entries = sl.get("entries") if isinstance(sl, dict) else []
                if isinstance(entries, list) and entries:
                    return str(row[0] or cand), [e for e in entries if isinstance(e, dict)]

        rows = conn.execute(
            """
            SELECT slot_id, payload_json
            FROM opname_slots
            WHERE cycle_key = ? AND aset = ? AND wilayah = ? AND vendor = ? AND status = 'ACTIVE'
            ORDER BY updated_at DESC, slot_id ASC
            """,
            (cycle_key, aset, wilayah, vendor),
        ).fetchall()
    finally:
        conn.close()

    merged_entries: list[dict] = []
    first_sid = ""
    for sid, p_json in rows:
        try:
            sl = json.loads(p_json or "{}")
        except Exception:
            continue
        if isinstance(sl, list):
            sl = sl[0] if sl else {}
        entries = sl.get("entries") if isinstance(sl, dict) else []
        if isinstance(entries, list) and entries:
            if not first_sid:
                first_sid = str(sid or "")
            merged_entries.extend(e for e in entries if isinstance(e, dict))
    return first_sid, merged_entries


def _match_ocr_row_to_baseline(
    item_key: str,
    t_str: str,
    vol_vnd: float | None,
    kode_tem: str,
    p_val: float | None,
    l_val: float | None,
    t_val: float | None,
    j_val: float | None,
    baseline: list[dict],
    used_idxs: set[int],
) -> tuple[int, dict] | None:
    def _b_vol(b: dict) -> float | None:
        v = to_float_num(b.get("vol_vendor"))
        return v if v is not None else to_float_num(b.get("volume"))

    candidates = [(i, b) for i, b in enumerate(baseline) if i not in used_idxs]
    if vol_vnd is not None:
        for i, b in candidates:
            if b.get("tanggal") == t_str and b.get("item_key") == item_key:
                bv = _b_vol(b)
                if bv is not None and abs(bv - vol_vnd) <= 0.015:
                    return i, b
    k_up = (kode_tem or "").strip().upper()
    if k_up and k_up != "-":
        for i, b in candidates:
            b_kt = str(b.get("tanggal_temuan") or b.get("kode_temuan") or "").strip().upper()
            if b.get("item_key") == item_key and b_kt == k_up:
                return i, b
    ocr_dims = (p_val, l_val, t_val, j_val)
    for i, b in candidates:
        if b.get("tanggal") == t_str and b.get("item_key") == item_key:
            b_dims = (
                to_float_num(b.get("p")),
                to_float_num(b.get("l")),
                to_float_num(b.get("t")),
                to_float_num(b.get("jml")),
            )
            hits = sum(
                1
                for ov, bv in zip(ocr_dims, b_dims)
                if ov is not None and bv is not None and abs(ov - bv) <= 0.01
            )
            if hits >= 2:
                return i, b
    for i, b in candidates:
        if b.get("tanggal") == t_str and b.get("item_key") == item_key:
            return i, b

    # Pass 5: item-change fallback (Permanen -> Salob, etc.) using Tanggal/Kode Temuan, Vol. Vendor, or >=2 dims
    if k_up and k_up != "-":
        for i, b in candidates:
            b_kt = str(b.get("tanggal_temuan") or b.get("kode_temuan") or "").strip().upper()
            if b_kt == k_up:
                return i, b
    if vol_vnd is not None:
        for i, b in candidates:
            if b.get("tanggal") == t_str:
                bv = _b_vol(b)
                if bv is not None and abs(bv - vol_vnd) <= 0.015:
                    return i, b
    for i, b in candidates:
        if b.get("tanggal") == t_str:
            b_dims = (
                to_float_num(b.get("p")),
                to_float_num(b.get("l")),
                to_float_num(b.get("t")),
                to_float_num(b.get("jml")),
            )
            hits = sum(
                1
                for ov, bv in zip(ocr_dims, b_dims)
                if ov is not None and bv is not None and abs(ov - bv) <= 0.01
            )
            if hits >= 2:
                return i, b
    return None


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

    print(f"[Opname Scan] Start | caption={caption!r} | hint={scan_hint} | sender={sender_label}")
    if not message.get("hasMedia"):
        print("[Opname Scan] Rejected: no media attached")
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
        print(f"[Opname Scan] Download failed: {dl_err}")
        send_whatsapp_message(reply_chat_id, f"❌ Gagal mengunduh lampiran Scan Opname: {dl_err}", session)
        return

    print(f"[Opname Scan] Downloaded | file={filename or '-'} | mime={mimetype or '-'} | bytes={len(raw_bytes)}")
    is_pdf = (
        mimetype == "application/pdf"
        or filename.lower().endswith(".pdf")
        or raw_bytes[:4] == b"%PDF"
    )
    if is_pdf:
        try:
            page_images = _render_pdf_pages_to_jpeg(raw_bytes)
            print(f"[Opname Scan] Rendered PDF -> {len(page_images)} page(s)")
        except Exception as pdf_err:
            unmark_processed(processing_key)
            print(f"[Opname Scan] PDF render failed: {pdf_err}")
            send_whatsapp_message(reply_chat_id, f"❌ Gagal membaca PDF Scan Opname: {pdf_err}", session)
            return
    else:
        page_images = [raw_bytes]

    hint_aset = scan_hint.get("aset") or ""
    boq_menu = format_boq_cheat_sheet(hint_aset, max_items=40) if hint_aset else ""
    print(f"[Opname Scan] Running OCR on {len(page_images)} page(s) (hint aset={hint_aset or 'auto'})...")
    ocr_res, ocr_err = extract_opname_form_ocr(page_images, hint_aset, caption, boq_menu)
    if ocr_err and not ocr_res.get("rows"):
        unmark_processed(processing_key)
        print(f"[Opname Scan] OCR failed: {ocr_err}")
        send_whatsapp_message(reply_chat_id, f"❌ OCR Scan Opname gagal: {ocr_err}", session)
        return

    aset = normalize_asset_code(hint_aset or str(ocr_res.get("aset", "")))
    if not aset:
        print("[Opname Scan] Rejected: asset code not detected")
        send_whatsapp_message(
            reply_chat_id,
            "⚠️ Jenis pekerjaan tidak terbaca dari scan. Sertakan kode di caption, contoh: `Scan Opname PV`.",
            session,
        )
        return

    raw_rows = ocr_res.get("rows") or []
    if not raw_rows:
        print("[Opname Scan] Rejected: 0 table rows extracted from scan")
        send_whatsapp_message(reply_chat_id, "⚠️ Tidak ada baris pekerjaan terbaca pada lampiran scan.", session)
        return

    fallback_dt = datetime.datetime.now().strftime("%Y-%m-%d")
    hdr_vend = str(ocr_res.get("vendor") or "").strip()
    hdr_wil = str(ocr_res.get("wilayah") or scan_hint.get("wilayah") or "").strip().upper()
    raw_batch_hint = ocr_res.get("opname_ke") or ocr_res.get("minggu") or scan_hint.get("minggu")
    hdr_wk = normalize_opname_batch(raw_batch_hint, default="OP1")

    probe_vend_raw = hdr_vend or next(
        (str(r.get("vendor") or "").strip() for r in raw_rows if isinstance(r, dict) and r.get("vendor")),
        "",
    )
    probe_wil = hdr_wil if hdr_wil in ("W1", "W2") else next(
        (
            str(r.get("wilayah") or "").strip().upper()
            for r in raw_rows
            if isinstance(r, dict) and str(r.get("wilayah") or "").strip().upper() in ("W1", "W2")
        ),
        "",
    )
    first_dt_probe = next(
        (
            parse_opname_date_str(str(r.get("tanggal") or ""))
            for r in raw_rows
            if isinstance(r, dict) and parse_opname_date_str(str(r.get("tanggal") or ""))
        ),
        fallback_dt,
    )
    cm_probe, cy_probe = resolve_billing_cycle(datetime.datetime.strptime(first_dt_probe, "%Y-%m-%d").date())
    _, canon_hdr_vend, _ = normalize_vendor(probe_vend_raw, aset)
    baseline_slot_id, baseline_entries = _load_baseline_slot_entries(
        aset, probe_wil, canon_hdr_vend or "", hdr_wk, f"{cy_probe:04d}-{cm_probe:02d}"
    )
    used_base_idxs: set[int] = set()
    anchored_count = 0

    parsed_entries: list[dict] = []
    warnings: list[str] = []
    warn_seen: set[str] = set()
    if baseline_slot_id and baseline_slot_id.upper().endswith("-FULL") and hdr_wk != "FULL":
        full_note = (
            f"Baseline Excel tersimpan sebagai slot penuh ({baseline_slot_id}); "
            f"bila scan {hdr_wk} hanya sebagian tanggal, /undo {baseline_slot_id} setelah simpan agar tidak double-count."
        )
        warn_seen.add(full_note)
        warnings.append(full_note)
    errors: list[str] = []
    preview_lines: list[str] = []

    for i_r, r_obj in enumerate(raw_rows, start=1):
        if not isinstance(r_obj, dict):
            continue
        row_action = str(r_obj.get("row_action") or "").strip().upper()
        if row_action not in ("ADDED", "REMOVED"):
            row_action = ""

        t_str = parse_opname_date_str(str(r_obj.get("tanggal") or "")) or fallback_dt
        raw_tem_v = str(r_obj.get("tanggal_temuan") or r_obj.get("kode_temuan") or "-").strip() or "-"
        kode_tem = parse_opname_date_str(raw_tem_v) or raw_tem_v
        ket_raw = str(r_obj.get("keterangan") or "").strip()
        loc = str(r_obj.get("lokasi") or "").strip()
        raw_wil = str(r_obj.get("wilayah") or hdr_wil or "").strip().upper()
        jalur = " ".join(p for p in (str(r_obj.get("jalur") or "").strip(), str(r_obj.get("lajur") or "").strip()) if p) or "-"
        lokasi_edited = bool(r_obj.get("lokasi_edited"))
        m_ket_loc = re.search(r"(?i)\b(?:sta|lok(?:asi)?)\s*[:=]\s*([^;,\n]+)", ket_raw)
        if m_ket_loc:
            ket_loc_cand = m_ket_loc.group(1).strip()
            if ket_loc_cand and ket_loc_cand.upper() not in loc.upper():
                loc = ket_loc_cand
                lokasi_edited = True
        raw_baik = r_obj.get("hasil_baik")
        hasil_baik: bool | None = raw_baik if isinstance(raw_baik, bool) else None

        v_ok, canon_v, v_err = normalize_vendor(str(r_obj.get("vendor") or hdr_vend), aset)
        if not v_ok or not canon_v:
            errors.append(f"Baris {i_r}: {v_err}")
            continue

        boq_item, b_err = resolve_boq_item(
            aset,
            str(r_obj.get("raw_item") or ""),
            lokasi=loc,
            wilayah=(raw_wil if raw_wil in ("W1", "W2") else hdr_wil),
        )
        if not boq_item:
            errors.append(f"Baris {i_r}: {b_err}")
            continue

        p_val = to_float_num(r_obj.get("p"))
        l_val = to_float_num(r_obj.get("l"))
        t_val = to_float_num(r_obj.get("t"))
        j_val = to_float_num(r_obj.get("jml"))
        vol_opn = to_float_num(r_obj.get("vol_opname"))
        vol_vnd = to_float_num(r_obj.get("vol_vendor"))
        item_edited = bool(r_obj.get("item_edited"))

        vendor_p: float | None = None
        vendor_l: float | None = None
        vendor_t: float | None = None
        vendor_jml: float | None = None
        vendor_item_key = ""
        vendor_keyword = ""
        vendor_lokasi = ""
        anchored_from_excel = False
        base_match = (
            _match_ocr_row_to_baseline(
                boq_item.item_key,
                t_str,
                vol_vnd,
                kode_tem,
                p_val,
                l_val,
                t_val,
                j_val,
                baseline_entries,
                used_base_idxs,
            )
            if (baseline_entries and row_action != "ADDED")
            else None
        )
        if base_match is not None:
            b_idx, base = base_match
            used_base_idxs.add(b_idx)
            anchored_count += 1
            t_str = str(base.get("tanggal") or t_str)
            base_loc = str(base.get("lokasi") or "").strip()
            if lokasi_edited:
                loc, typo_fix = fuzzy_fix_ic_akses_typo(loc)
                if typo_fix:
                    print(f"[Opname Scan] Auto-fixed OCR lokasi typo: {typo_fix}", flush=True)
                if base_loc and loc and base_loc.lower() != loc.lower():
                    vendor_lokasi = base_loc
                elif not loc:
                    loc = base_loc
            else:
                if base_loc:
                    loc = base_loc
                base_wil = str(base.get("wilayah") or "").strip().upper()
                if base_wil in ("W1", "W2"):
                    raw_wil = base_wil
                base_jal = str(base.get("jalur_lajur") or "").strip()
                if base_jal and base_jal != "-":
                    jalur = base_jal
            base_kode = str(base.get("tanggal_temuan") or base.get("kode_temuan") or "").strip()
            if base_kode and base_kode != "-":
                kode_tem = base_kode
            b_vol = to_float_num(base.get("vol_vendor"))
            if b_vol is None:
                b_vol = to_float_num(base.get("volume"))
            if b_vol is not None:
                vol_vnd = b_vol
            vendor_p = to_float_num(base.get("p"))
            vendor_l = to_float_num(base.get("l"))
            vendor_t = to_float_num(base.get("t"))
            vendor_jml = to_float_num(base.get("jml"))
            base_ik = str(base.get("item_key") or "").strip()
            base_kw = str(base.get("keyword") or base_ik).strip()
            base_sat = str(base.get("satuan") or "").strip()
            if base_ik and base_ik != boq_item.item_key:
                vendor_item_key = base_ik
                vendor_keyword = base_kw or base_ik
                item_edited = True
                if base_sat and base_sat.lower() != boq_item.satuan.lower():
                    unit_msg = (
                        f"Baris {i_r}: Item berubah '{vendor_keyword}' ({base_sat}) -> '{boq_item.keyword}' "
                        f"({boq_item.satuan}); periksa kembali volume di web review."
                    )
                    if unit_msg not in warn_seen:
                        warn_seen.add(unit_msg)
                        warnings.append(unit_msg)
            anchored_from_excel = True
        else:
            loc, typo_fix = fuzzy_fix_ic_akses_typo(loc)
            if typo_fix:
                print(f"[Opname Scan] Auto-fixed OCR lokasi typo: {typo_fix}", flush=True)

        if anchored_from_excel:
            boq_fixed, _ = resolve_boq_item(
                aset,
                str(r_obj.get("raw_item") or ""),
                lokasi=loc,
                wilayah=(raw_wil if raw_wil in ("W1", "W2") else hdr_wil),
            )
            if boq_fixed:
                boq_item = boq_fixed

        wil = raw_wil
        if loc:
            direct_ok, direct_wil, _, _ = resolve_wilayah(loc)
            if lokasi_edited and direct_ok and direct_wil:
                wil = direct_wil
            elif wil in ("W1", "W2"):
                w_ok, loc_w, _, w_err = resolve_wilayah(f"{loc} {wil}")
                if not w_ok or not loc_w:
                    errors.append(f"Baris {i_r}: {w_err}")
                    continue
                if not direct_ok:
                    w_msg = (
                        f"Baris {i_r}: Lokasi '{loc}' tidak cocok daftar KM/IC, "
                        f"memakai Wilayah header {loc_w} (periksa di web review)."
                    )
                    if w_msg not in warn_seen:
                        warn_seen.add(w_msg)
                        warnings.append(w_msg)
                wil = loc_w
            else:
                w_ok, loc_w, _, w_err = resolve_wilayah(loc)
                if not w_ok or not loc_w:
                    errors.append(f"Baris {i_r}: {w_err}")
                    continue
                wil = loc_w
        if wil not in ("W1", "W2"):
            errors.append(f"Baris {i_r}: Wilayah W1/W2 tidak terbaca.")
            continue

        dim_edited = bool(r_obj.get("dimension_edited"))
        hw_edited = bool(r_obj.get("handwritten_edited")) or item_edited or lokasi_edited
        removal_reason = ""

        if row_action == "REMOVED":
            vol_num = 0.0
            is_edited = True
            hw_edited = True
            is_disposal = "disposal" in ket_raw.lower()
            removal_reason = "DISPOSAL" if is_disposal else "REMOVED"
            r_ok, r_warn = check_roster_pairing(aset, canon_v, wil)
            if not r_ok and r_warn not in warn_seen:
                warn_seen.add(r_warn)
                warnings.append(r_warn)
            if is_disposal:
                preview_lines.append(
                    f"{i_r}. ⏭️ *{boq_item.keyword}* (`{boq_item.item_key}`) | {loc or wil} | *TUNDA DISPOSAL* (masuk opname berikutnya)"
                )
                rem_msg = (
                    f"Baris {i_r}: '{boq_item.keyword}' ({loc or wil}) ditandai TUNDA DISPOSAL "
                    f"(dikeluarkan dari opname ini dan diingatkan untuk opname berikutnya)."
                )
            else:
                preview_lines.append(
                    f"{i_r}. ❌ *{boq_item.keyword}* (`{boq_item.item_key}`) | {loc or wil} | *DIHAPUS / BATAL*"
                )
                rem_msg = (
                    f"Baris {i_r}: '{boq_item.keyword}' ({loc or wil}) ditandai DIHAPUS / BATAL "
                    f"(tidak disimpan ke DATA_UNTUK_VOL kecuali dipulihkan di web review)."
                )
            if rem_msg not in warn_seen:
                warn_seen.add(rem_msg)
                warnings.append(rem_msg)
        else:
            strict_dim_vol = compute_strict_dim_volume(
                boq_item.satuan,
                p_val,
                l_val,
                t_val,
                j_val,
                allow_countable_jml=(dim_edited or (p_val is None and l_val is None and t_val is None and j_val is not None)),
            )

            auto_recalc_dim = False
            is_edited = hw_edited or dim_edited
            if vol_opn is not None:
                vol_num = vol_opn
            elif strict_dim_vol is not None and strict_dim_vol > 0 and (
                dim_edited or hw_edited or vol_vnd is None or abs(strict_dim_vol - vol_vnd) > 0.01
            ):
                vol_num = strict_dim_vol
                auto_recalc_dim = True
                is_edited = True
            elif vol_vnd is not None:
                vol_num = vol_vnd
            else:
                vol_num = compute_geom_volume(boq_item.satuan, p_val, l_val, t_val, j_val) or 0.0

            if vol_num <= 0:
                errors.append(f"Baris {i_r}: Volume '{boq_item.keyword}' tidak terbaca / <= 0.")
                continue

            r_ok, r_warn = check_roster_pairing(aset, canon_v, wil)
            if not r_ok and r_warn not in warn_seen:
                warn_seen.add(r_warn)
                warnings.append(r_warn)

            if hasil_baik is False:
                baik_msg = (
                    f"Baris {i_r}: Hasil pekerjaan '{boq_item.keyword}' ({loc or wil}) "
                    f"ditandai TDK BAIK - periksa di web review."
                )
                if baik_msg not in warn_seen:
                    warn_seen.add(baik_msg)
                    warnings.append(baik_msg)

            vol_changed_from_vendor = (vol_vnd is None) or (abs(vol_num - vol_vnd) > 0.001)
            item_mark = f" (item: {vendor_keyword}→{boq_item.keyword})" if vendor_keyword else ""
            loc_mark = f" (lok: {vendor_lokasi}→{loc})" if vendor_lokasi else ""
            baik_mark = " ⚠️ TDK BAIK" if hasil_baik is False else ""
            if row_action == "ADDED":
                is_edited = True
                hw_edited = True
                preview_lines.append(
                    f"{i_r}. ➕ *{boq_item.keyword}* (`{boq_item.item_key}`) | {loc or wil} | *{vol_num:g} {boq_item.satuan}* (tambahan){baik_mark}"
                )
            else:
                if auto_recalc_dim and vol_changed_from_vendor:
                    is_jml_only = p_val is None and l_val is None and t_val is None
                    edited_mark = " ✏️ (auto)" if is_jml_only else " ✏️ (auto P×L×T)"
                elif is_edited and not item_edited and not lokasi_edited and vol_opn is None and not vol_changed_from_vendor:
                    edited_mark = " ⚠️✏️ (cek revisi di web)"
                    u_msg = (
                        f"Baris {i_r}: Coretan terdeteksi pada '{boq_item.keyword}' ({loc or wil}), "
                        f"tetapi angka masih sama dengan Vol. Vendor ({vol_num:g}) - cek di web review."
                    )
                    if u_msg not in warn_seen:
                        warn_seen.add(u_msg)
                        warnings.append(u_msg)
                elif is_edited:
                    edited_mark = " ✏️"
                else:
                    edited_mark = ""
                preview_lines.append(
                    f"{i_r}. *{boq_item.keyword}* (`{boq_item.item_key}`) | {loc or wil} | *{vol_num:g} {boq_item.satuan}*{edited_mark}{item_mark}{loc_mark}{baik_mark}"
                )

        parsed_entries.append(
            {
                "tanggal": t_str,
                "minggu": hdr_wk,
                "kode_temuan": kode_tem,
                "tanggal_temuan": kode_tem,
                "wilayah": wil,
                "vendor": canon_v,
                "lokasi": loc or "-",
                "vendor_lokasi": vendor_lokasi,
                "lokasi_edited": bool(lokasi_edited),
                "jalur_lajur": jalur,
                "item": boq_item,
                "item_key": boq_item.item_key,
                "keyword": boq_item.keyword,
                "uraian": boq_item.uraian,
                "satuan": boq_item.satuan,
                "p": p_val,
                "l": l_val,
                "t": t_val,
                "jml": j_val,
                "vol_vendor": vol_vnd,
                "vendor_p": vendor_p,
                "vendor_l": vendor_l,
                "vendor_t": vendor_t,
                "vendor_jml": vendor_jml,
                "vendor_item_key": vendor_item_key,
                "vendor_keyword": vendor_keyword,
                "item_edited": bool(item_edited),
                "volume": round(vol_num, 4),
                "hasil_baik": hasil_baik,
                "removal_reason": removal_reason,
                "handwritten_edited": bool(is_edited),
                "row_action": row_action,
                "anchored_from_excel": anchored_from_excel,
                "material_status": "",
                "keterangan": ket_raw,
            }
        )

    if errors or not parsed_entries:
        print(f"[Opname Scan] Validation failed ({len(errors)} error(s)): {'; '.join(errors[:5])}")
        err_msg = "\n".join(f"- {e}" for e in errors[:10]) if errors else "Baris opname tidak valid."
        send_whatsapp_message(reply_chat_id, f"⚠️ *Scan Opname Perlu Perbaikan*\n{err_msg}", session)
        return

    if anchored_count > 0:
        print(
            f"[Opname Scan] Anchored {anchored_count}/{len(parsed_entries)} row(s) to baseline slot {baseline_slot_id}",
            flush=True,
        )

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
    rekap_rev_rows = ocr_res.get("rekap_revisi") or []
    if isinstance(rekap_rev_rows, list) and rekap_rev_rows:
        active_by_ik: dict[str, float] = {}
        for pe in parsed_entries:
            if pe.get("row_action") != "REMOVED":
                active_by_ik[pe["item_key"]] = active_by_ik.get(pe["item_key"], 0.0) + float(pe["volume"] or 0.0)
        first_loc_c = next((pe.get("lokasi", "") for pe in parsed_entries if pe.get("lokasi")), "")
        first_wil_c = first_slot["wilayah"]
        rekap_dt = max(str(pe.get("tanggal") or fallback_dt) for pe in parsed_entries)
        for rr in rekap_rev_rows:
            if not isinstance(rr, dict):
                continue
            rev_val = to_float_num(rr.get("vol_revisi"))
            if rev_val is None or rev_val <= 0:
                continue
            raw_rk_item = str(rr.get("raw_item") or "").strip()
            rb_item, rb_err = resolve_boq_item(aset, raw_rk_item, lokasi=first_loc_c, wilayah=first_wil_c)
            if not rb_item:
                unres_msg = (
                    f"Item '{raw_rk_item or '-'}' pada REKAP VOLUME PER ITEM ({rev_val:g}) belum lengkap "
                    f"({rb_err or 'butuh STA/KM'}) - tambahkan manual via '+ Tambah Baris' di web review."
                )
                if unres_msg not in warn_seen:
                    warn_seen.add(unres_msg)
                    warnings.append(unres_msg)
                continue
            if rb_item.item_key not in active_by_ik:
                new_ent = {
                    "tanggal": rekap_dt,
                    "minggu": first_slot["minggu"],
                    "kode_temuan": "-",
                    "tanggal_temuan": "-",
                    "wilayah": first_slot["wilayah"],
                    "vendor": first_slot["vendor"],
                    "lokasi": "-",
                    "vendor_lokasi": "",
                    "lokasi_edited": False,
                    "jalur_lajur": "-",
                    "item": rb_item,
                    "item_key": rb_item.item_key,
                    "keyword": rb_item.keyword,
                    "uraian": rb_item.uraian,
                    "satuan": rb_item.satuan,
                    "p": None,
                    "l": None,
                    "t": None,
                    "jml": None,
                    "vol_vendor": None,
                    "vendor_p": None,
                    "vendor_l": None,
                    "vendor_t": None,
                    "vendor_jml": None,
                    "vendor_item_key": "",
                    "vendor_keyword": "",
                    "item_edited": False,
                    "volume": round(rev_val, 4),
                    "hasil_baik": None,
                    "removal_reason": "",
                    "handwritten_edited": True,
                    "row_action": "ADDED",
                    "anchored_from_excel": False,
                    "material_status": "",
                    "keterangan": "Tambahan dari REKAP VOLUME PER ITEM (lengkapi STA/KM)",
                }
                parsed_entries.append(new_ent)
                dt_r = datetime.datetime.strptime(rekap_dt, "%Y-%m-%d").date()
                cm_r, cy_r = resolve_billing_cycle(dt_r)
                sid_r = f"XLS-{cy_r % 100:02d}{cm_r:02d}-{aset}-{first_slot['wilayah']}-{first_slot['vendor']}-{first_slot['minggu']}"
                target_slot_r = slots_by_id.get(sid_r, first_slot)
                target_slot_r["entries"].append({k: v for k, v in new_ent.items() if k != "item"})
                active_by_ik[rb_item.item_key] = round(rev_val, 4)
                preview_lines.append(
                    f"{len(preview_lines) + 1}. ➕ *{rb_item.keyword}* (`{rb_item.item_key}`) | (dari Rekap) | "
                    f"*{rev_val:g} {rb_item.satuan}* (lengkapi STA/KM)"
                )
                add_rk_msg = (
                    f"Tambahan dari REKAP VOLUME PER ITEM: '{rb_item.keyword}' ({rev_val:g} {rb_item.satuan}) "
                    f"dibuat sebagai baris tambahan - lengkapi Tanggal & STA/KM di web review."
                )
                if add_rk_msg not in warn_seen:
                    warn_seen.add(add_rk_msg)
                    warnings.append(add_rk_msg)
            else:
                calc_sum = round(active_by_ik.get(rb_item.item_key, 0.0), 3)
                if abs(calc_sum - rev_val) > 0.02:
                    rc_msg = (
                        f"Rekap '{rb_item.keyword}': total baris aktif ({calc_sum:g} {rb_item.satuan}) "
                        f"berbeda dengan tulisan tangan Vol. Revisi ({rev_val:g} {rb_item.satuan})."
                    )
                    if rc_msg not in warn_seen:
                        warn_seen.add(rc_msg)
                        warnings.append(rc_msg)

    conn_def = sqlite3.connect(settings.DB_URL)
    try:
        pending_defs = conn_def.execute(
            """
            SELECT source_slot_id, tanggal, lokasi, item_key, keyword, volume, satuan
            FROM opname_deferred_disposal
            WHERE status = 'PENDING' AND aset = ? AND wilayah = ? AND vendor = ?
            ORDER BY defer_id ASC
            """,
            (aset, first_slot["wilayah"], first_slot["vendor"]),
        ).fetchall()
    finally:
        conn_def.close()
    if pending_defs:
        active_pairs = {
            (str(pe.get("item_key") or ""), str(pe.get("lokasi") or "-").strip().upper())
            for pe in parsed_entries
            if pe.get("row_action") != "REMOVED"
        }
        for d_src, _d_tgl, d_loc, d_ik, d_kw, d_vol, d_sat in pending_defs:
            if (str(d_ik or ""), str(d_loc or "-").strip().upper()) not in active_pairs:
                rem_d_msg = (
                    f"Pengingat Disposal tertunda dari {d_src}: '{d_kw or d_ik}' di {d_loc or '-'} "
                    f"({float(d_vol or 0):g} {d_sat or ''}) belum masuk opname ini."
                ).strip()
                if rem_d_msg not in warn_seen:
                    warn_seen.add(rem_d_msg)
                    warnings.append(rem_d_msg)

    scan_id = f"SCAN-{datetime.datetime.now():%y%m%d}-{uuid.uuid4().hex[:4].upper()}"
    print(f"[Opname Scan] Validated {len(parsed_entries)} row(s) into {len(slots_by_id)} slot(s) | staging {scan_id}...")
    src_ext = ".pdf" if is_pdf else ".jpg"
    src_mime = "application/pdf" if is_pdf else "image/jpeg"
    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    active_for_xlsx = [e for e in parsed_entries if e.get("row_action") != "REMOVED"]
    xlsx_bytes = build_prefilled_standard_xlsx(aset, first_slot["cycle_month"], first_slot["cycle_year"], active_for_xlsx)
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
        print(f"[Opname Scan] Archive failed for {scan_id}: {arch_err}")
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
        reply_chat_id=reply_chat_id,
        session=session,
        sender_label=sender_label,
    )
    print(f"[Opname Scan] Staged {scan_id} | aset={aset} | rows={len(parsed_entries)} | warnings={len(warnings)}")

    warn_block = ("\n\n⚠️ *Catatan Roster:*\n" + "\n".join(f"• {w}" for w in warnings)) if warnings else ""
    review_link = build_review_url(settings.PUBLIC_BASE_URL, scan_id)
    link_block = f"\n\n🌐 *Review & edit cepat (HP / PC):*\n{review_link}" if review_link else ""
    more_line = (
        f"\n_... dan {len(preview_lines) - 20} baris lainnya (total {len(preview_lines)} baris)._"
        if len(preview_lines) > 20
        else ""
    )
    preview_msg = (
        f"🔎 *Hasil Scan Opname (`{scan_id}`)*\n"
        f"Aset / Opname: *{aset}* / *{first_slot['minggu']}* | Vendor: *{first_slot['vendor']}*\n"
        + "\n".join(preview_lines[:20])
        + more_line
        + warn_block
        + link_block
        + f"\n\n✅ Ketik `/simpan {scan_id}` jika angka sudah benar, atau edit via link di atas / file Excel di bawah."
    )
    send_whatsapp_message(reply_chat_id, preview_msg, session)
    send_whatsapp_document(
        reply_chat_id,
        xlsx_bytes,
        xlsx_name,
        caption=f"Excel hasil OCR `{scan_id}`. Edit jika ada koreksi lalu kirim balik dengan caption `Opname`, atau balas `/simpan {scan_id}`.",
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
    is_xlsx_file = bool(
        message.get("hasMedia")
        and (
            media_filename.lower().endswith(".xlsx")
            or "spreadsheetml" in media_mimetype
        )
    )
    is_xlsx_opname = is_xlsx_file and has_xlsx_opname_trigger(body)
    if is_group:
        body_clean = body.strip().lower() if isinstance(body, str) else ""
        is_cmd = body_clean.startswith(("/rekap", "/undo", "/simpan", "/status opname", "/arsip", "/tagihan"))
        has_sla_code = message.get("hasMedia") and extract_kode_from_text(body)
        has_scan_trig = bool(extract_scan_opname_hint(body))
        if not is_cmd and not has_sla_code and not has_scan_trig and not is_xlsx_opname:
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

    # Route Standard .xlsx Opname Workbook Drop-In (only when caption explicitly contains `Opname`)
    if is_xlsx_opname:
        try:
            xlsx_bytes = _extract_image_bytes_from_message(message)
        except Exception as dl_err:
            unmark_processed(processing_key)
            print(f"[Opname XLSX] Download failed ({media_filename or '-'}): {dl_err}")
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

from fastapi.responses import HTMLResponse, FileResponse

@app.get("/logo.svg", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
def favicon_file():
    return FileResponse(
        Path(__file__).with_name("logo.svg"),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    host = request.headers.get("host", "")
    if "astrainfrasolutions.id" in host:
        waha_url = "https://waha.astrainfrasolutions.id"
        logs_url = "/logs"
        guide_url = "/guide"
    else:
        ip_only = host.split(":")[0] if host else "129.225.9.167"
        waha_url = settings.WAHA_PUBLIC_URL or f"http://{ip_only}:3000"
        logs_url = "/logs"
        guide_url = "/guide"

    opname_excel_link = settings.OPNAME_EXCEL_SHARE_LINK or "#"
    opname_cycle_label = "siklus 26-25"
    def_m, def_y = resolve_billing_cycle(datetime.date.today())
    active_cycle = f"{def_y:04d}-{def_m:02d}"
    pending_count = 0
    roster_done = 0
    roster_total = len(OFFICIAL_VENDOR_ROSTER)
    sla_today_count = 0

    try:
        conn = sqlite3.connect(settings.DB_URL)
        try:
            if settings.OPNAME_AUTO_MONTHLY:
                latest_wb = conn.execute(
                    "SELECT cycle_key, web_url FROM opname_workbooks ORDER BY cycle_key DESC LIMIT 1"
                ).fetchone()
                if latest_wb and latest_wb[1]:
                    opname_excel_link = latest_wb[1]
                    opname_cycle_label = f"siklus {latest_wb[0]}"

            pend_row = conn.execute(
                "SELECT COUNT(*) FROM opname_pending WHERE status = 'PENDING'"
            ).fetchone()
            pending_count = int(pend_row[0]) if pend_row else 0

            cycles_found = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT cycle_key FROM opname_slots WHERE status = 'ACTIVE' ORDER BY cycle_key DESC"
                ).fetchall()
                if r and r[0]
            ]
            if cycles_found and active_cycle not in cycles_found:
                active_cycle = cycles_found[0]

            cy_y, cy_m = map(int, active_cycle.split("-"))
            yy_mm = f"{cy_y % 100:02d}{cy_m:02d}"
            active_pairs = {
                (normalize_asset_code(a) or a, v, w)
                for a, v, w in conn.execute(
                    "SELECT aset, vendor, wilayah FROM opname_slots WHERE cycle_key = ? AND status = 'ACTIVE'",
                    (active_cycle,),
                ).fetchall()
            }
            active_pairs |= {
                (normalize_asset_code(a) or a, v, w)
                for a, v, w in conn.execute(
                    "SELECT DISTINCT aset, vendor, wilayah FROM opname_entries WHERE status = 'ACTIVE' AND opname_id LIKE ?",
                    (f"XLS-{yy_mm}-%",),
                ).fetchall()
            }
            active_roster = get_active_roster(settings.DB_URL)
            roster_total = len(active_roster)
            roster_done = sum(1 for item in active_roster if item in active_pairs)

            today_str = datetime.date.today().strftime("%Y-%m-%d")
            sla_row = conn.execute(
                "SELECT COUNT(DISTINCT kode) FROM daily_updates WHERE date = ?",
                (today_str,),
            ).fetchone()
            sla_today_count = int(sla_row[0]) if sla_row else 0
        finally:
            conn.close()
    except Exception:
        pass

    opname_editor_url = f"/opname?token={make_opname_token('DASHBOARD')}"
    html_content = render_console_page_html(
        waha_url=waha_url,
        logs_url=logs_url,
        guide_url=guide_url,
        opname_editor_url=opname_editor_url,
        sla_excel_url=settings.EXCEL_SHARE_LINK or "#",
        opname_excel_url=opname_excel_link,
        opname_cycle_label=opname_cycle_label,
        stats={
            "cycle_key": active_cycle,
            "pending_count": pending_count,
            "roster_done": roster_done,
            "roster_total": roster_total,
            "sla_today_count": sla_today_count,
        },
    )
    return HTMLResponse(content=html_content)


@app.get("/guide", response_class=HTMLResponse)
def get_guide(request: Request):
    host = request.headers.get("host", "")
    if "astrainfrasolutions.id" in host:
        waha_dash_link = "https://waha.astrainfrasolutions.id"
    else:
        ip_only = host.split(":")[0] if host else "129.225.9.167"
        waha_dash_link = settings.WAHA_PUBLIC_URL or f"http://{ip_only}:3000"
    opname_editor_url = f"/opname?token={make_opname_token('DASHBOARD')}"
    return HTMLResponse(content=render_guide_page_html(waha_dash_link, opname_editor_url))

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

app.include_router(
    create_opname_web_router(
        {
            "commit_slots": lambda *a, **kw: _commit_opname_slots(*a, **kw),
            "delete_slot_rows": lambda *a, **kw: delete_opname_rows_by_id(*a, **kw),
            "archive_file": lambda *a, **kw: _archive_opname_file_to_onedrive(*a, **kw),
            "download_onedrive": lambda *a, **kw: download_file_from_onedrive(*a, **kw),
            "upload_private_onedrive": lambda *a, **kw: upload_private_file_to_onedrive(*a, **kw),
            "download_path_onedrive": lambda *a, **kw: download_file_by_path_from_onedrive(*a, **kw),
            "render_pdf_pages": lambda *a, **kw: _render_pdf_pages_to_jpeg(*a, **kw),
            "send_whatsapp": lambda *a, **kw: send_whatsapp_message(*a, **kw),
            "format_commit_reply": lambda *a, **kw: _format_commit_reply(*a, **kw),
            "save_tagihan_baseline": lambda *a, **kw: save_tagihan_baseline(*a, **kw),
            "run_tagihan_generation": lambda *a, **kw: run_tagihan_generation(*a, **kw),
            "get_db_url": lambda: settings.DB_URL,
        }
    )
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5001, reload=True)
