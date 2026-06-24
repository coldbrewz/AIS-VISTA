# On-Premise Server Deployment Guide (AIS-VISTA)

This guide is intended for the IT Department to deploy the **AIS-VISTA WhatsApp Bot** onto the company's internal bare-metal server. 

The application is fully containerized using Docker, meaning it is environment-agnostic and will not pollute the host machine with Python dependencies. It consists of a headless Chromium browser (WAHA engine) and a Python FastAPI backend.

## Prerequisites
- A server running Linux (Ubuntu 22.04 / 24.04 recommended) or Windows Server with WSL2/Docker Desktop.
- Outbound internet access (TCP Port 443) to connect to WhatsApp Web servers, Telegram API, and Microsoft Graph APIs.
- No inbound ports need to be exposed to the public internet! The bot connects to WhatsApp via outbound WebSockets.

---

## Step 1: Install Dependencies
Ensure the host machine has `git`, `docker`, and `docker-compose` (v2) installed.

For Ubuntu/Debian:
```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-v2
sudo systemctl enable --now docker
```

---

## Step 2: Clone the Repository
Clone the production-ready code from the GitHub repository into your preferred application directory (e.g., `/opt/ais-vista/`):

```bash
cd /opt
git clone https://github.com/coldbrewz/AIS-VISTA.git
cd AIS-VISTA
```

---

## Step 3: Inject Secrets (.env)
For security, the `.env` file containing API keys is excluded from version control. 
1. Request the raw text of the `.env` file directly from the bot administrator (they will securely transmit it to you).
2. Create a `.env` file in the root of the cloned repository:
```bash
nano .env
```
3. Paste the variables exactly as provided. Save and exit.

---

## Step 4: Launch the Containers
The repository includes a `docker-compose.prod.yml` file specifically configured for production servers. It utilizes `restart: always` policies to automatically recover from system reboots or transient crashes.

From inside the `AIS-VISTA` directory, run:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### What happens now?
1. Docker pulls the `devlikeapro/waha` image (~1.5GB, containing Chromium).
2. Docker dynamically builds the Python backend image using the provided `Dockerfile`.
3. The containers start up on an isolated private Docker network.
4. The Python Watchdog will automatically start bridging the connection.

---

## Step 5: (Optional) Verify Logs
To ensure everything booted up correctly without errors, you can trail the logs:

```bash
# View backend Python logs
docker compose -f docker-compose.prod.yml logs -f vista_bot

# View WAHA Engine logs
docker compose -f docker-compose.prod.yml logs -f waha
```

**Note:** If the WhatsApp session is fresh, the Python Watchdog will automatically generate a QR Code and send it via Telegram to the Administrator for remote login. **You do not need to intervene or look at the WAHA dashboard.**

## Maintenance & Updates
If the developers push an update to GitHub, applying it is a 3-step process:
```bash
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```
All SQLite databases and WhatsApp session tokens are stored in persistent Docker volumes (`/app/.sessions` and `processed_messages.db`), so updates are completely safe and will not log the bot out.
