import asyncio
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Query, Response, BackgroundTasks
import requests
import datetime
import re
import time
import sqlite3
from config import settings
from services.llm import extract_sla_data
from services.whatsapp import send_whatsapp_message
from services.microsoft import update_excel_row, upload_photo_to_onedrive

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
        self.terminal.write(message)
        if message.strip():
            self._logger.info(message.rstrip())
            
    def flush(self):
        self.terminal.flush()
        
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

async def auto_update_waha():
    global is_updating
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
            if data and isinstance(data, list):
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
                if status == "WORKING":
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

def download_whatsapp_media(media_url: str) -> bytes:
    headers = {"X-Api-Key": settings.WAHA_API_KEY}
    resp = requests.get(media_url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.content

def handle_whatsapp_command(sender_phone, command, session):
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
        
        send_whatsapp_message(sender_phone, msg, session)
    except Exception as e:
        print(f"Error handling whatsapp command: {e}")

def process_message(message: dict):
    sender_phone = message.get("from", "").replace("@c.us", "")
    msg_type = message.get("type") or message.get("_data", {}).get("type")
    session = message.get("_session", "default")
    
    # ANTI-BAN: Skip ALL status@broadcast messages (WhatsApp Stories).
    # These are irrelevant to SLA processing and flood the bot after reconnecting.
    if "status@broadcast" in sender_phone or "status@broadcast" in message.get("from", ""):
        return
    
    # ANTI-BAN: Skip messages during the grace period after login
    if session_ready_at > 0 and (time.time() - session_ready_at) < 60:
        print(f"GRACE PERIOD: Skipping message from {sender_phone} (settling after login)")
        return
    
    print(f"\n--- New WAHA Message Received ---")
    print(f"Sender: {sender_phone} | hasMedia: {message.get('hasMedia')}")
    
    message_id = message["id"]
    body = message.get("body", "")
    
    # Intercept WhatsApp Commands
    if body and isinstance(body, str):
        text_lower = body.strip().lower()
        # FIX #4: Use startswith so custom ranges like "/rekap 6 juli" are also captured
        if text_lower.startswith("/rekap"):
            if not mark_processed(message_id):
                return
            handle_whatsapp_command(sender_phone, text_lower, session)
            return
    
    # ATOMIC RACE-CONDITION LOCK: Immediately insert into DB.
    # If it's already there (rowcount == 0), another thread/webhook is already processing it!
    if not mark_processed(message_id):
        print(f"Skipping duplicate message {message_id}...")
        return
        
    if message.get("hasMedia"):
        caption = message.get("body", "")
        
        # Hard filter to avoid consuming LLM API unnecessarily
        # Pattern checks for "Kode: " followed by ddmmyy, valid sheet code, and 3 digits
        kode_match = re.search(r"Kode\s*:\s*(\d{6}(?:PV|DR|FE|GR|SG|LC|RM|CA|WR)\d{3})", caption, re.IGNORECASE)
        if not kode_match:
            # If they clearly attempted to submit an SLA but failed the regex format
            if "kode" in caption.lower():
                send_whatsapp_message(sender_phone, "⚠️ *Update Ditolak*\nFormat Kode tidak valid atau tidak dikenali oleh sistem. Harap pastikan format kode SLA benar (contoh: *Kode: 240523PV001*).", session)
            print(f"Skipping message {message_id}: Caption does not contain a valid SLA code format.")
            return
        detected_kode = kode_match.group(1)
        
        print(f"Message ID: {message_id} | Caption: {caption}")
        
        timestamp_unix = message.get("timestamp", "")
        msg_datetime_str = ""
        if timestamp_unix:
            dt = datetime.datetime.fromtimestamp(int(timestamp_unix))
            msg_datetime_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        
        print("Step 1: Downloading photo via WAHA...")
        
        try:
            media_url = message.get("media", {}).get("url")
            if not media_url:
                # WPP engine does not provide media.url in the webhook payload.
                # We must use the WAHA standard download API endpoint.
                internal_media_url = f"{settings.WAHA_URL}/api/{session}/messages/{message_id}/download"
            else:
                # WAHA may return localhost in the payload, but we are inside Docker
                import urllib.parse
                parsed_url = urllib.parse.urlparse(media_url)
                internal_media_url = f"{settings.WAHA_URL}{parsed_url.path}"
            
            img_bytes = download_whatsapp_media(internal_media_url)
            
            # 2. Process with Gemini Vision FIRST so we get the date/sheet name
            print("Step 2: Extracting AI data...")
            payload, err = extract_sla_data(img_bytes, caption, msg_datetime_str)
            
            if payload:
                try:
                    parsed_dt = datetime.datetime.strptime(payload.tanggal_perbaikan, '%Y-%m-%d %H:%M:%S')
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
                send_whatsapp_message(sender_phone, f"✅ Update SLA berhasil!\nKode: {payload.kode}", session)
                
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
                send_whatsapp_message(sender_phone, f"⚠️ Ekstraksi data gagal untuk Kode *{detected_kode}*: {err}\nPastikan format teks dan gambar sudah sesuai.", session)
        except Exception as process_err:
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
                
            send_whatsapp_message(sender_phone, reply_msg, session)
    else:
        # No media attached
        body = message.get("body", "")
        kode_match = re.search(r"Kode\s*:\s*(\d{6}(?:PV|DR|FE|GR|SG|LC|RM|CA|WR)\d{3})", body, re.IGNORECASE)
        if kode_match:
            send_whatsapp_message(sender_phone, f"⚠️ *Update Gagal untuk {kode_match.group(1)}*\nAnda mengirimkan teks tanpa foto. Harap kirimkan foto dokumentasi dengan caption kode tersebut.", session)
        elif "kode:" in body.lower() or "kode :" in body.lower():
            send_whatsapp_message(sender_phone, "⚠️ *Update Gagal*\nHarap kirimkan *foto dokumentasi* beserta caption dengan format Kode yang benar (contoh: *Kode: 240523PV001*).", session)

@app.get("/")
def read_root():
    return {"status": "VISTA Webhook is running."}

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
