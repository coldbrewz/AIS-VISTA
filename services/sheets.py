import datetime
import gspread
from schemas import VistaInspectionPayload
from config import settings

def append_to_sheet(payload: VistaInspectionPayload):
    """
    Appends the parsed inspection payload as a new row in Google Sheets.
    """
    if not settings.GOOGLE_APPLICATION_CREDENTIALS or not settings.SPREADSHEET_ID:
        print("[Mock Sheets Append] Credentials or Spreadsheet ID not configured.")
        print(f"Row data: {payload.model_dump()}")
        return
        
    try:
        # Authenticate using the service account credentials
        gc = gspread.service_account(filename=settings.GOOGLE_APPLICATION_CREDENTIALS)
        sh = gc.open_by_key(settings.SPREADSHEET_ID)
        worksheet = sh.sheet1
        
        # Prepare the row data
        row = [
            datetime.datetime.now().isoformat(),
            payload.location,
            payload.damage_type,
            payload.lane,
            payload.severity
        ]
        
        # Append the row
        worksheet.append_row(row)
        print("Successfully appended data to Google Sheets.")
    except Exception as e:
        print(f"Error appending to Google Sheets: {e}")
