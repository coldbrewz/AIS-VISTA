# 👁️ Project VISTA (Visual Intelligence SLA Tracker API)

VISTA is an AI-powered WhatsApp bot designed to automatically track, process, and log toll road maintenance reports for the Tangerang-Merak highway. It serves as the intelligent ingestion engine for the AIS-IRIS ecosystem.

Field workers simply send a photo of the repair along with a brief caption via WhatsApp. VISTA automatically reads the image using **Google Gemini Vision**, extracts the required data, uploads the photo to OneDrive, and perfectly formats and injects the data into the master SLA tracking Excel file via the **Microsoft Graph API**.

## 🏗 Architecture
This project is designed for 24/7 uptime on a dedicated server using:
- **WhatsApp Engine:** Docker WAHA (WhatsApp HTTP API) by devlikeapro.
- **Backend Service:** Python 3 (FastAPI & Uvicorn).
- **AI Vision:** Google Gemini 1.5 Pro/Flash.
- **Data Storage:** Microsoft OneDrive & Excel Online.

## 🚀 Installation & Setup

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
pip install fastapi uvicorn requests google-generativeai msal
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory. You must not commit this file to version control.
```env
# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Microsoft Graph API Credentials
MS_CLIENT_ID=your_azure_client_id
MS_CLIENT_SECRET=your_azure_client_secret
MS_TENANT_ID=your_azure_tenant_id
EXCEL_SHARE_LINK=your_excel_document_url
```
*(Note: For the first Microsoft Graph API run, `credentials.json` from a desktop OAuth flow might be required depending on your exact MSAL setup).*

### 5. Start the Services

**Step A: Start WAHA Docker Engine**
Run the following command in your terminal to start the WhatsApp Web engine. It automatically forwards webhooks to your local Python server on Port 5000.
```bash
docker run -it -p 3000:3000/tcp -e WHATSAPP_WEBHOOK_URL=http://host.docker.internal:5000/webhook --name waha devlikeapro/waha
```

**Step B: Link your WhatsApp Account**
1. Open your browser and go to `http://localhost:3000`
2. Navigate to the `/api/sessions/start` endpoint in the Swagger UI.
3. Click "Try it out" -> "Execute" to generate the QR Code.
4. Scan the QR code using your WhatsApp application (Linked Devices).

**Step C: Start the Python AI Bot**
In a new terminal window, start the VISTA FastAPI server:
```bash
python main.py
```

## 🧠 Workflow Pipeline
1. **Webhook Trigger:** WAHA receives a WhatsApp image message and hits `http://localhost:5000/webhook`.
2. **Media Download:** Python downloads the image buffer directly from the local WAHA Docker container.
3. **AI Extraction:** Gemini Vision parses the image and caption to find the KODE, Sheet Name, Repair Method, and Dimensions.
4. **Cloud Storage:** The image is uploaded dynamically to a chronological OneDrive folder (e.g., `VISTA_Photos/PV/2026/Juni/11`).
5. **Excel Injection:** Microsoft Graph API pushes the newly formatted row straight into the live Excel spreadsheet.

---
*Built for Astra Tol Nusantara | AIS-IRIS Ecosystem*
