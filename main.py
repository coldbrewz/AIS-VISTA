from fastapi import FastAPI, Request, HTTPException, Query, Response, BackgroundTasks
import requests
import datetime
from config import settings
from services.llm import extract_sla_data
from services.whatsapp import send_whatsapp_message
from services.microsoft import update_excel_row, upload_photo_to_onedrive

app = FastAPI(title="Project VISTA Webhook API")

def download_whatsapp_media(message_id: str, session: str = "default") -> bytes:
    url = f"http://localhost:3000/api/{session}/messages/{message_id}/download"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.content

def process_message(message: dict):
    sender_phone = message.get("from", "").replace("@c.us", "")
    msg_type = message.get("type")
    session = message.get("_session", "default")
    
    print(f"\n--- New WAHA Message Received ---")
    print(f"Sender: {sender_phone} | Type: {msg_type}")
    
    if message.get("hasMedia") and msg_type in ["image", "document"]:
        message_id = message["id"]
        caption = message.get("body", "")
        
        print(f"Message ID: {message_id} | Caption: {caption}")
        
        timestamp_unix = message.get("timestamp", "")
        msg_datetime_str = ""
        if timestamp_unix:
            dt = datetime.datetime.fromtimestamp(int(timestamp_unix))
            msg_datetime_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        
        print("Step 1: Downloading photo via WAHA...")
        
        try:
            img_bytes = download_whatsapp_media(message_id, session)
            
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
                folder_path = f"VISTA_Photos/{payload.sheet_name}/{year_str}/{month_name}/{day_str}"
                print(f"Step 3: Uploading to OneDrive at {folder_path}...")
                photo_link = upload_photo_to_onedrive(img_bytes, f"{payload.kode}_{message_id}.jpg", folder_path)
                
                # 4. Update Excel
                print(f"Step 4: Injecting into Excel (Kode: {payload.kode}, Sheet: {payload.sheet_name})...")
                update_excel_row(
                    share_url=settings.EXCEL_SHARE_LINK,
                    sheet_name=payload.sheet_name,
                    kode=payload.kode,
                    tanggal=excel_date_formula,
                    link=photo_link,
                    metode=payload.metode_perbaikan,
                    panjang=str(payload.panjang) if payload.panjang else "",
                    lebar=str(payload.lebar) if payload.lebar else "",
                    tebal=str(payload.tebal) if payload.tebal else ""
                )
                print("✅ Success!")
                send_whatsapp_message(sender_phone, f"✅ Update SLA berhasil!\nKode: {payload.kode}", session)
            else:
                print(f"⚠️ Ignored non-SLA image or failed to extract data: {err}")
                # Silent Ninja Mode: No error message sent to the group
        except Exception as process_err:
            import traceback
            err_trace = traceback.format_exc()
            print(f"Error processing image:\n{err_trace}")
            # Silent Ninja Mode: No system error message sent to the group

@app.get("/")
def read_root():
    return {"status": "VISTA Webhook is running."}

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
                
            payload["_session"] = session
            background_tasks.add_task(process_message, payload)
                                
        return {"status": "success"}
    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
