# project ais-vista: comprehensive technical & executive presentation deck documentation

---

## 1. executive summary & problem statement

### 1.1 background & business context
project ais-vista is an enterprise automated sla (service level agreement) tracking and verification platform built for toll road maintenance operations at astra infra solutions. toll road infrastructure requires continuous monitoring, repair, and reporting across multiple asset categories (pavement, guardrails, drainage, road signs, expansion joints, etc.).

### 1.2 the operational problem
before ais-vista, field workers and site foremen (mandor) manually submitted daily repair photos through whatsapp chat groups. the manual process created major bottlenecks:
- **manual data re-entry:** administrators had to manually download photos from whatsapp, extract defect codes, calculate dimensions, and type data into central excel spreadsheets.
- **human errors and typos:** field workers frequently wrote repair methods or measurements with spelling variations (e.g. typing "coolmix" instead of "Coldmix", or "aspalt" instead of "Asphaltic Plug"), causing broken filters and inconsistent reporting.
- **unorganized evidence storage:** repair photos were scattered across personal phones or generic cloud drives without a structured date/sheet hierarchy.
- **slow audit trails & high operational costs:** verifying whether a pothole or damaged guardrail was repaired within the contractual sla window required hours of manual cross-referencing.

### 1.3 the ais-vista solution
ais-vista automates the entire lifecycle end-to-end:
1. field workers take a photo on site with a timestamp watermark and post it to the whatsapp group with a standard caption (e.g. `Kode: 240523PV001`, `Metode: Coldmix`, `Panjang: 1.5`, `Lebar: 0.8`, `Tebal: 0.05`).
2. the system instantly captures the image via webhook, executes multimodal ai vision extraction (google gemini 2.5 flash), extracts dimensions, and auto-corrects field typos.
3. the high-resolution photo is automatically uploaded to a structured onedrive archive (`Dokumentasi SLA/{sheet_name}/{year}/{month}/{day}/{kode}.jpg`).
4. the central shared microsoft excel worksheet is updated in real time via microsoft graph api with exact date formulas, dimensions, method names, and direct clickable photo hyperlinks.
5. an immediate whatsapp confirmation is sent back to the field worker, and the admin receives automated daily recap summaries, remote status checks, and self-healing alerts.

---

## 2. core capabilities & feature catalog

| feature module | technical description | business value |
| :--- | :--- | :--- |
| **multimodal ai vision & ocr** | analyzes both the image watermark and caption using google gemini 2.5 flash with zero-temperature structured json output. | eliminates manual data entry; reads messy watermarks and captions automatically. |
| **smart typo auto-correction** | two-layer fuzzy normalization that maps variations (e.g., `coolmix`, `aspaltik plug`, `sealant`) to official standardized terms (`Coldmix`, `Asphaltic Plug`, `Sealent`, `Hotmix`, `CnP`, `Scrapmix`, `Marka`). | ensures 100% database integrity on excel without requiring strict field worker training. |
| **cloud storage automation** | uploads photos directly to onedrive with organized folder hierarchy by year, month, and day. | audit-ready photographic evidence organized automatically for management reviews. |
| **live excel graph api injection** | dynamically resolves drive item ids, finds matching defect codes across sheets, and writes excel formulas (`=DATE(...)+TIME(...)`) and hyperlinks. | zero latency between field repair completion and executive management dashboards. |
| **anti-ban whatsapp engine** | powered by waha (whatsapp http api) with gows (go-based engine), selective typing simulation, status broadcast dropping, and rate-limiting. | 24/7 stable connection without getting the corporate whatsapp number banned. |
| **self-healing watchdog** | background asynchronous monitor checking session health, auto-restarting crashed containers, and applying exponential backoff. | zero maintenance required; automatically recovers from network drops or server reboots. |
| **offline catch-up sync** | scans unread messages received while the server or connection was offline and processes them sequentially upon reconnection. | guarantees zero data loss during power outages or internet disruptions. |
| **multi-channel remote administration** | telegram bot (`/status`, `/qr`) and email imap poller allowing admins to monitor uptime and scan login qr codes remotely from anywhere. | no need to open an ssh terminal to manage or re-authenticate the bot. |
| **daily recap scheduler** | automated cron-like scheduler firing at 08:00 wib every morning, tallying yesterday's completed repairs by category and sending a whatsapp summary to the admin. | keeps management informed every morning without manual report generation. |
| **web management console** | glassmorphic dark-mode web console served on port 5001 with dynamic domain routing, live log viewer, and interactive documentation. | clean, centralized dashboard for administrators and stakeholders. |

---

## 3. complete system architecture

```
                     +-----------------------------------------------------------+
                     |                     FIELD LEVEL                           |
                     |  Site Foreman / Mandor (WhatsApp Group or Private Chat)   |
                     +-----------------------------+-----------------------------+
                                                   |
                                                   | 1. Sends Photo + Caption
                                                   v
                     +-----------------------------------------------------------+
                     |                 WHATSAPP GATEWAY (WAHA)                   |
                     |     - Engine: GOWS (Go-based, Ultra-lightweight ~30MB)    |
                     |     - Webhook Event Dispatcher: /webhook                  |
                     |     - Multi-session Manager & Anti-ban Filter             |
                     +-----------------------------+-----------------------------+
                                                   |
                                                   | 2. HTTP POST (JSON + Base64)
                                                   v
+---------------------------------------------------------------------------------------------------------+
|                                    CORE BACKEND CONTAINER (VISTA_BOT)                                   |
|                                                                                                         |
|  +-----------------------------------+   +---------------------------------+   +---------------------+  |
|  |     FastAPI Webhook Listener      |   |       SQLite Deduplication      |   |  Background Tasks   |  |
|  | - Relevancy Regex Gate            |-->| - processed_messages.db         |-->| - Async Worker Pool |  |
|  | - Anti-Status Broadcast Filter    |   | - Message ID deduplication      |   | - Grace Period Gate |  |
|  +-----------------------------------+   +---------------------------------+   +----------+----------+  |
|                                                                                           |             |
|  +----------------------------------------------------------------------------------------+             |
|  |                                                                                                      |
|  v                                                                                                      |
|  +------------------------------------+   +----------------------------------+   +-------------------+  |
|  |      Multimodal AI Extraction      |   |   Fuzzy Normalization Layer      |   | Cloudflare Proxy  |  |
|  | - Google Gemini 2.5 Flash          |-->| - PV Sheet Method Standardizer   |<--| (Bypasses GeoIP   |  |
|  | - Structured JSON Pydantic Schema  |   | - CnP, Hotmix, Coldmix, Sealent  |   |  Datacenter Block)|  |
|  +------------------------------------+   +-----------------+----------------+   +-------------------+  |
|                                                             |                                           |
|  +----------------------------------------------------------+                                           |
|  |                                                                                                      |
|  v                                                                                                      |
|  +------------------------------------+   +----------------------------------+   +-------------------+  |
|  |      Microsoft Graph API Client    |   |     Background Daemon Services   |   | Web Management UI |  |
|  | - MSAL Silent Token Refresh Cache  |   | - WAHA Watchdog & Health Check   |   | - Root Console /  |  |
|  | - OneDrive Photo Hierarchy Upload  |   | - Offline Catch-up Sync Daemon   |   | - /logs Terminal  |  |
|  | - Excel Formula & Row Injector     |   | - Daily 08:00 WIB Recap Daemon   |   | - /guide FAQ Docs |  |
|  +------------------------------------+   +-----------------+----------------+   +-------------------+  |
|                                                             |                                           |
+-------------------------------------------------------------|-------------------------------------------+
                                                              |
                 +--------------------------------------------+-------------------------------------------+
                 |                                            |                                           |
                 v                                            v                                           v
+---------------------------------+          +---------------------------------+         +--------------------------------+
|      MICROSOFT 365 CLOUD        |          |      REMOTE ADMIN CHANNELS      |         |      FIELD CONFIRMATION        |
| - OneDrive: /Dokumentasi SLA/   |          | - Telegram Bot: /status, /qr    |         | - WAHA sendText API            |
| - Excel Online: Live Worksheets |          | - Gmail IMAP/SMTP Alert Poller  |         | - Real-time WhatsApp Reply     |
|   (PV, DR, FE, GR, SG, etc.)    |          | - Automated Daily Recap Alerts  |         |   "✅ Update SLA berhasil!"    |
+---------------------------------+          +---------------------------------+         +--------------------------------+
```

---

## 4. detailed end-to-end data flow & workflow

```
[Mandor on Site]
       |
       | 1. Takes photo with GPS/Timestamp watermark & sends WhatsApp message:
       |    "Kode: 240523PV001, Metode: coolmix, P: 1.5, L: 0.8, T: 0.05"
       v
[WAHA Gateway Engine]
       |
       | 2. Receives raw WhatsApp message packet from Meta network.
       |    Extracts Base64 image data directly from payload body.
       |    Dispatches webhook POST to http://vistabot:5001/webhook.
       v
[FastAPI Gatekeeper (main.py)]
       |
       | 3. Step 3a: Drops broadcast status stories instantly (Anti-ban prevention).
       |    Step 3b: Checks if message is from bot itself (fromMe == True) -> Ignore.
       |    Step 3c: Relevancy check: Scans text for regex pattern `Kode:\s*(\d{6}[A-Z]{2}\d+)`.
       |             If non-SLA casual chat in group -> Drop immediately without writing DB.
       |    Step 3d: Checks SQLite processed_messages.db. If already processed -> Drop.
       |    Step 3e: Queues processing into asynchronous BackgroundTasks.
       v
[Gemini 2.5 Flash Vision Engine (services/llm.py)]
       |
       | 4. Outbound call routed through Cloudflare Worker proxy (bypassing datacenter restrictions).
       |    Gemini analyzes image watermark + text caption simultaneously.
       |    Enforces Pydantic schema: kode, tanggal_perbaikan, metode_perbaikan,
       |    sheet_name, panjang, lebar, tebal.
       v
[Two-Layer Normalization & Safety Net]
       |
       | 5. If sheet_name == "PV", intercepts metode_perbaikan:
       |    - Strips whitespace, dashes, special characters.
       |    - Runs exact case-insensitive match against valid methods.
       |    - Runs fuzzy keyword fallback ("cool" -> "Coldmix", "aspalt" -> "Asphaltic Plug",
       |      "sealant" -> "Sealent", "mark" -> "Marka", etc.).
       |    - Formats date string into Excel native formula: =DATE(Y,M,D)+TIME(H,M,S).
       v
[Microsoft Graph API Integration (services/microsoft.py)]
       |
       | 6. Acquires silent OAuth2 token via MSAL SerializableTokenCache.
       |    Step 6a: Uploads photo binary to OneDrive folder:
       |             Dokumentasi SLA/{sheet_name}/{year}/{month}/{day}/{kode}.jpg
       |             Generates webUrl hyperlink for the photo.
       |    Step 6b: Encodes shared Excel URL into drive item endpoint.
       |    Step 6c: Fetches sheet columns and row data, finds row index matching Kode.
       |    Step 6d: Writes Tanggal formula, photo hyperlink, Metode, Panjang, Lebar, Tebal.
       v
[Confirmation & Daily Logging]
       |
       | 7. Records Kode + Date in SQLite daily_updates table.
       |    Sends instant WhatsApp reply to Mandor:
       |    "✅ Update SLA berhasil! Kode: 240523PV001"
       v
[Daily Executive Reporting]
       |
       | 8. At 08:00 WIB every morning, background daemon tallies all updates from yesterday,
       |    groups them by category (PV, DR, FE, etc.), and sends formatted WhatsApp recap to Admin.
```

---

## 5. deep dive: component breakdown & technical implementations

### 5.1 supported asset sheets & code taxonomy
every defect code in the toll road maintenance system follows a strict alphanumeric convention:
`YYMMDD` + `[SHEET_CODE]` + `[INDEX]` (e.g. `240523PV001` = 23 may 2024, pavement repair #001).

the platform automatically routes and validates data across all official operational sheets:
- **`PV` (Pavement / Perkerasan Jalan):** pothole repairs, patchings, sealing. supports dimensions (`Panjang`, `Lebar`, `Tebal`) and strict method standardization (`CnP`, `Hotmix`, `Coldmix`, `Scrapmix`, `Sealent`, `Asphaltic Plug`, `Marka`).
- **`DR` (Drainase):** culverts, drainage channels, water flows.
- **`FE` (Fasilitas Enclosure / Pagar & Pembatas):** right-of-way fencing, sound barriers.
- **`GR` (Guardrail):** highway flex-beam guardrails, end treatments, post repairs.
- **`SG` (Signage / Rambu Lalu Lintas):** guide signs, regulatory signs, warning signs.
- **`LC` (Lansekap & Kebersihan):** slope grass cutting, median beautification.
- **`RM` (Road Marking):** thermoplastic road line markings, chevron markings.
- **`CA` (Civil Assets / Struktur Jembatan & Overpass):** parapets, expansion joints, abutments.
- **`WR` (Water Retaining / Dinding Penahan):** retaining walls, gabions.

---

### 5.2 multimodal ai extraction & double-layer fuzzy normalization
1. **gemini 2.5 flash structured output:** the prompt enforces strict json extraction with `response_mime_type="application/json"` and `temperature=0.0`. caption data always takes precedence over image watermarks.
2. **fuzzy keyword matching logic:**
   ```python
   # automated correction table implemented in main.py
   "cool" | "col" | "cold"       --> "Coldmix"
   "hot" | "hopt" | "hoot"       --> "Hotmix"
   "scrap" | "scrab"             --> "Scrapmix"
   "seal" | "selent" | "sealant" --> "Sealent"
   "plug" | "asphalt" | "aspalt" --> "Asphaltic Plug"
   "mark" | "marker"             --> "Marka"
   "cnp"  | "c-n-p"              --> "CnP"
   ```

---

### 5.3 microsoft graph api & authentication engineering
- **token cache serialization:** utilizes `msal.PublicClientApplication` with serialized disk caching in `token_cache.bin`. whenever access tokens refresh, the updated state is flushed immediately to disk, ensuring authentication survives container restarts without interactive logins.
- **cloud drive item resolution:** converts public onedrive sharing links into base64-encoded api paths (`/shares/u!{encoded_url}/driveItem`), allowing programmatic access to corporate excel files without hardcoding volatile file ids.
- **safe column letter calculation:** dynamic numeric-to-alphabet converter (`num_to_col_letter(n)`) maps column numbers (e.g., column 28 -> `AB`), preventing cell range syntax errors when updating wide spreadsheets.
- **http retry adapter:** configured with exponential backoff on http status codes `429`, `500`, `502`, `503`, and `504` to handle microsoft cloud throttling.

---

### 5.4 anti-ban engineering & whatsapp stability
running automation on whatsapp requires specialized protection mechanisms to prevent account bans:
1. **gows engine:** utilizes pure go-based socket connections (~30mb ram) instead of heavy headless chrome/puppeteer instances (~500mb ram), eliminating memory leaks and browser crashes.
2. **anti-burst status story drop:** immediately drops incoming `status@broadcast` packets at the webhook entry point. (whatsapp pushes 30-100 stories upon reconnection; processing them triggers anti-bot detection).
3. **smart group typing bypass:** disables typing and read-receipt simulations on group chats (`@g.us`) to avoid unnatural bot activity patterns. applies randomized jitter typing (1.5s - 3.0s) only on direct private messages.
4. **reconnection grace period:** enforces a mandatory 60-second processing freeze when a session transitions to `WORKING`, allowing socket buffers to stabilize before handling queued messages.
5. **watchdog exponential backoff:** limits automatic docker container restarts to a maximum of 3 consecutive attempts. if issues persist, backs off for 10 minutes and dispatches an alert to telegram to prevent server hammering.

---

### 5.5 multi-channel remote administration & self-healing
- **telegram bot poller (`services/telegram.py`):** long-polling daemon listening for authorized chat ids.
  - `/status`: returns active session name, engine, and connection state without generating new session credentials.
  - `/qr`: requests a fresh live qr code from waha with a mandatory 30-second cooldown to prevent session exhaustion, delivering the qr directly as an instant photo message.
- **email imap/smtp listener (`services/email.py`):** if the bot is disconnected, it captures the raw login qr code and emails it to administrators. admins can reply with `"QR"` to receive an updated code directly in their inbox.
- **offline catch-up sync daemon:** upon regaining connection, queries `/api/{session}/chats` for unread counters and backfills all missed messages sent during the downtime.

---

### 5.6 web management console & developer experience
served on port `5001` via fastapi:
- **dynamic domain routing:** detects request headers. if accessed via corporate domain (`vista.astrainfrasolutions.id`), routes links to `https://waha.astrainfrasolutions.id` and `/logs`. if accessed via ip/local development, routes to `:3000` and `:5001`.
- **dark-mode console dashboard (`/`):** visual launcher linking directly to waha scanner, live logs, excel online, and documentation.
- **interactive documentation (`/guide`):** embedded documentation covering number changes, troubleshooting, and commands.
- **live terminal stream (`/logs`):** rotating file handler exposing the last 200 lines of system logs directly in the browser.

---

## 6. deployment topology & multi-architecture support

the project repository supports dual deployment targets out of the box:

```
                          +---------------------------------------+
                          |        PROJECT AIS-VISTA CODEBASE     |
                          +-------------------+-------------------+
                                              |
                     +------------------------+------------------------+
                     |                                                 |
                     v                                                 v
   +------------------------------------+            +------------------------------------+
   |     OFFICE ON-PREM VPS (x86_64)    |            |     ORACLE CLOUD VM (ARM64)        |
   | - Architecture: Intel / AMD64      |            | - Architecture: Ampere A1 (aarch64)|
   | - Compose: docker-compose.prod.yml |            | - Compose: docker-compose.arm.yml  |
   | - WAHA Image: devlikeapro/waha     |            | - WAHA Image: devlikeapro/waha:arm |
   | - Reverse Proxy: Corporate Nginx   |            | - Outbound: Cloudflare Worker Proxy|
   | - Domains:                         |            | - Public IP: 129.225.9.167         |
   |   vista.astrainfrasolutions.id     |            | - Role: 24/7 Redundant Cloud Backup|
   |   waha.astrainfrasolutions.id      |            +------------------------------------+
   +------------------------------------+
```

---

## 7. business value, roi & operational impact

```
+------------------------------------+------------------------------------+
|        BEFORE AIS-VISTA            |          AFTER AIS-VISTA           |
|            (MANUAL)                |            (AUTOMATED)             |
+------------------------------------+------------------------------------+
| ⏱️ 15-30 mins per repair report    | ⚡ < 5 seconds per repair report    |
| 📝 Manual typing into Excel        | 🤖 Zero human data entry           |
| ⚠️ Frequent typos in repair method | 🎯 100% normalized & auto-corrected|
| 📁 Photos lost in WhatsApp media   | ☁️ Structured OneDrive repository  |
| 📊 End-of-month manual reporting   | 📈 Daily 08:00 AM automated recap  |
| 📉 Risk of missed SLA penalties    | 🛡️ 100% verifiable audit trail    |
+------------------------------------+------------------------------------+
```

### quantitative business benefits:
1. **95%+ time savings:** eliminates hundreds of hours spent every month on administrative data entry.
2. **zero data loss:** sqlite deduplication and offline catch-up sync ensure every single repair submitted is captured and stored.
3. **instant compliance auditing:** direct excel hyperlinks to onedrive photos allow toll road regulators to verify repair quality in one click.
4. **low infrastructure footprint:** runs seamlessly on a 1 vcpu / 512mb ram instance with near-zero operating cost.

---

## 8. slide-by-slide presentation deck blueprint

use this structured 10-slide outline to create your presentation deck:

### slide 1: title & introduction
- **title:** ais-vista: autonomous sla verification & toll road maintenance automation
- **subtitle:** transforming field operations with multimodal ai, whatsapp automation, and enterprise cloud integration
- **presenter:** astra infra solutions innovation team

### slide 2: the field operation challenge
- **bullet 1:** high-volume maintenance across hundreds of kilometers of highway.
- **bullet 2:** manual data entry bottlenecks from whatsapp chat groups to central excel sheets.
- **bullet 3:** human errors, typos in repair methods, and missing photo audit trails.
- **bullet 4:** delayed executive visibility into daily contractual sla compliance.

### slide 3: the solution: ais-vista
- **bullet 1:** an intelligent, autonomous backend bridge connecting field workers to enterprise spreadsheets.
- **bullet 2:** field workers simply send a photo on whatsapp — ais-vista handles the rest in under 5 seconds.
- **bullet 3:** automated visual extraction, fuzzy normalization, onedrive archiving, and excel injection.

### slide 4: core architecture & technology stack
- **show diagram:** system architecture diagram from section 3.
- **backend:** python 3.11, fastapi, sqlite3, pydantic.
- **ai vision:** google gemini 2.5 flash multimodal model.
- **whatsapp engine:** waha gows (go-based, ultra-lightweight).
- **enterprise cloud:** microsoft graph api, onedrive for business, excel online.

### slide 5: multimodal ai extraction & typo correction
- **visual comparison:** show raw whatsapp caption (`Metode: coolmix, P: 1.5, L: 0.8, T: 0.05`) vs normalized excel row (`Metode: Coldmix`).
- **highlight:** two-layer fuzzy normalization ensuring 100% standardized data across all asset categories (`PV`, `DR`, `FE`, `GR`, `SG`, `LC`, `RM`, `CA`, `WR`).

### slide 6: enterprise microsoft 365 integration
- **bullet 1:** dynamic folder archiving in onedrive: `Dokumentasi SLA/{sheet}/{year}/{month}/{day}/{kode}.jpg`.
- **bullet 2:** live excel updates using native `=DATE()+TIME()` formulas and direct photo hyperlinks.
- **bullet 3:** persistent msal silent token refresh for 100% unattended operation.

### slide 7: reliability, anti-ban & self-healing engineering
- **bullet 1:** anti-ban protection: socket-level gows engine, burst status filters, and group typing bypass.
- **bullet 2:** self-healing watchdog with automated container recovery and exponential backoff.
- **bullet 3:** offline catch-up sync: zero missed messages after network outages.

### slide 8: remote monitoring & multi-channel admin controls
- **bullet 1:** telegram bot remote control: instant `/status` checks and live `/qr` code photo retrieval.
- **bullet 2:** emergency email qr alerts with automated reply-to-refresh listener.
- **bullet 3:** automated daily 08:00 wib recap summarizing completed repairs by category.

### slide 9: unified management web console
- **bullet 1:** dark-mode glassmorphic web dashboard on port `5001`.
- **bullet 2:** dynamic domain routing (`vista.astrainfrasolutions.id` & `waha.astrainfrasolutions.id`).
- **bullet 3:** live real-time server log streaming and embedded interactive operator documentation.

### slide 10: business impact, roi & future roadmap
- **metrics:** 95% reduction in reporting latency; 100% photographic audit compliance.
- **roi:** zero additional licensing costs; runs on ultra-low-cost cloud infrastructure.
- **future roadmap:** automated anomaly detection for road cracks, gps map overlay, and voice note transcription.
