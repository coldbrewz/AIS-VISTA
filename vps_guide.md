# VISTA Bot Integration Guide & FAQ
==================================
This documentation provides common operations, troubleshooting guides, and FAQs for managing the VISTA AI WhatsApp Bot on your Linux VPS.

---

## 📱 WhatsApp Account Operations

### How to Change the Connected WhatsApp Number
If you want to swap the number associated with the bot:
1. **Log out of WhatsApp:** On the current phone, go to **Settings** -> **Linked Devices** -> Select the bot session -> Click **Log out**. (Alternatively, click **Logout** in the WAHA Dashboard).
2. **Stop the containers:** Run this on the VPS terminal:
   ```bash
   cd ~/AIS-VISTA
   docker-compose -f docker-compose.prod.yml down
   ```
3. **Wipe session files:** Delete the cached tokens:
   ```bash
   rm -rf waha_sessions/*
   ```
4. **Restart containers:**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```
5. **Scan QR Code:** Open your Telegram bot, wait 10 seconds, type `/qr`, and scan the returned QR Code with your new phone.

---

## 🛠️ Common Errors & Troubleshooting

### Error: `sqlite3.OperationalError: unable to open database file`
* **Why it happens:** SQLite was missing from the host before start, so Docker created `processed_messages.db` as an empty folder instead of a database file.
* **The Fix:**
  ```bash
  cd ~/AIS-VISTA
  docker-compose -f docker-compose.prod.yml down
  rm -rf processed_messages.db
  touch processed_messages.db
  docker-compose -f docker-compose.prod.yml up -d
  ```

### Error: `KeyError: 'ContainerConfig'` (Legacy docker-compose v1 bug)
* **Why it happens:** Legacy Python-based `docker-compose` crashes when attempting to inspect and replace running containers.
* **The Fix:** Force delete the containers first before restarting:
  ```bash
  cd ~/AIS-VISTA
  docker rm -f $(docker ps -aq --filter name=waha) $(docker ps -aq --filter name=vista_bot)
  docker-compose -f docker-compose.prod.yml up -d
  ```

### Error: `Unprotected Private Key File / Bad permissions` (Windows laptop connecting to VPS)
* **Why it happens:** Windows SSH client refuses to open `.key` files if they are accessible by other users.
* **The Fix (Git Bash):** Copy the key to the Git Bash virtual `/tmp/` folder which has native secure permissions:
  ```bash
  cp "/d/Users/muhammad.najih/Documents/AIS-VISTA/ssh-key-2026-07-22.key" /tmp/oracle.key
  chmod 600 /tmp/oracle.key
  ssh -i /tmp/oracle.key ubuntu@129.225.9.167
  ```

---

## 📋 Standard Lifecycle Commands

### Reconnecting to the VPS (from Git Bash)
```bash
cp "/d/Users/muhammad.najih/Documents/AIS-VISTA/ssh-key-2026-07-22.key" /tmp/oracle.key
chmod 600 /tmp/oracle.key
ssh -i /tmp/oracle.key ubuntu@129.225.9.167
cd AIS-VISTA
```

### Pulling Updates & Rebuilding Code
```bash
git pull
docker rm -f $(docker ps -aq --filter name=waha) $(docker ps -aq --filter name=vista_bot)
docker-compose -f docker-compose.prod.yml up -d --build
```

### Watching Logs Live
* **Python Bot Logs:** `docker logs -f vista_bot`
* **WAHA Logs:** `docker logs -f waha`
*(Press `Ctrl+C` to exit log views without stopping the bot)*
