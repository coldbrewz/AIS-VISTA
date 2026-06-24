# 👁️ Project VISTA (Visual Intelligence SLA Tracker API)

VISTA is an AI-powered WhatsApp bot designed to automatically track, process, and log toll road maintenance reports for the Tangerang-Merak highway. It serves as the intelligent ingestion engine for the AIS-IRIS ecosystem.

Field workers simply send a photo of the repair along with a brief caption via WhatsApp. VISTA automatically reads the image using **Google Gemini Vision**, extracts the required data, uploads the photo to OneDrive, and perfectly formats and injects the data into the master SLA tracking Excel file via the **Microsoft Graph API**.

## 🏗 Architecture
This project is designed for 24/7 uptime on a dedicated server using:
- **WhatsApp Engine:** Docker WAHA (WhatsApp HTTP API) by devlikeapro.
- **Backend Service:** Python 3 (FastAPI & Uvicorn) with intelligent watchdog.
- **AI Vision:** Google Gemini 1.5 Pro/Flash.
- **Data Storage:** Microsoft OneDrive & Excel Online.
- **Notifications:** Telegram Bot API & SMTP Email.

## 🚀 Installation & Setup (Local Windows Desktop)

### 1. Prerequisites
- **Python 3.10+** installed.
- **Docker Desktop** installed (with WSL 2 enabled for Windows).
- A dedicated Microsoft Azure App Registration (for the MSAL token).

### 2. Clone the Repository
```bash
git clone https://github.com/coldbrewz/AIS-VISTA.git
cd AIS-VISTA
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory. You must not commit this file to version control.
```env
# Google Gemini API
GEMINI_API_KEY=your_gemini_key

# WhatsApp / WAHA Config
WAHA_URL=http://localhost:3000
WAHA_API_KEY=your_secure_waha_api_key

# Microsoft Graph API Credentials
MS_CLIENT_ID=your_azure_client_id
MS_CLIENT_SECRET=your_azure_client_secret
MS_TENANT_ID=your_azure_tenant_id
EXCEL_SHARE_LINK=your_excel_document_url

# Notification Alerts
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=123456789,-987654321
EMAIL_SENDER=your@email.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=admin@email.com
ADMIN_PHONE=628123456789
```

### 5. Start the Services
Simply double-click the `start_vista_bot.bat` file! 
This script will automatically:
1. Boot the `waha` container via Docker Compose.
2. Launch the Python backend and Watchdog.
3. If the bot is logged out, it will automatically send the live WAHA QR code to your Telegram group! Simply reply `/qr` in Telegram to fetch the latest QR at any time.

---

## 🌍 Server Deployment (Linux VPS / Bare Metal)

Deploying to a production server is extremely easy because VISTA is completely containerized. 

Ensure the server has **Docker** and **Docker Compose** installed.

1. Clone the repository onto the server:
```bash
git clone https://github.com/coldbrewz/AIS-VISTA.git
cd AIS-VISTA
```

2. Create and fill out your `.env` file:
```bash
nano .env
```

3. Launch the Production Stack:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

**That's it!** Docker will build the Python backend natively on the server and link it seamlessly to the WAHA container. If the server ever reboots, `docker-compose.prod.yml` has restart policies to bring your bot back online automatically.

## 🧠 Workflow Pipeline
1. **Webhook Trigger:** WAHA receives a WhatsApp image message and hits the local `/webhook`.
2. **Media Download:** Python downloads the image buffer securely.
3. **AI Extraction:** Gemini Vision parses the image and caption to find the KODE, Sheet Name, Repair Method, and Dimensions.
4. **Cloud Storage:** The image is uploaded dynamically to a chronological OneDrive folder (e.g., `Dokumentasi SLA/PV/2026/Juni/11`).
5. **Excel Injection:** Microsoft Graph API pushes the newly formatted row straight into the live Excel spreadsheet.

---
*Built for Astra Tol Nusantara | AIS-IRIS Ecosystem*
