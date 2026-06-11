import pandas as pd
import requests
import math

# Configuration
EXCEL_FILE = r"D:\Users\muhammad.najih\Documents\AIS-VISTA\Data Source\Service Level Agreement 2026(1).xlsx"
SHEET_NAMES = ['PV', 'DR', 'FE', 'GR', 'SG', 'LC', 'RM', 'CA', 'WR'] # Only import data from these SLA sheets
WEBHOOK_URL = "http://127.0.0.1:8000/api/bot-webhook" # Change this to your live IRIS URL when deploying!

def clean_val(val):
    if pd.isna(val) or val == "-" or str(val).strip() == "":
        return None
    return val

print(f"Reading massive Excel file: {EXCEL_FILE}...")
xl = pd.ExcelFile(EXCEL_FILE)

total_imported = 0

for sheet in SHEET_NAMES:
    if sheet not in xl.sheet_names:
        continue
        
    print(f"\n--- Processing Sheet: {sheet} ---")
    
    # Read the sheet, skipping the first 3 rows to hit the real headers
    df = xl.parse(sheet, skiprows=3)
    
    batch = []
    
    for index, row in df.iterrows():
        kode = row.get("KODE")
        if pd.isna(kode) or str(kode).strip() == "":
            continue # Skip empty rows
            
        payload = {
            "kode": str(kode),
            "sheet_name": sheet,
            "panjang": clean_val(row.get("PANJANG")),
            "lebar": clean_val(row.get("LEBAR")),
            "tebal": clean_val(row.get("TEBAL")),
            "tanggal_temuan": str(row["TANGGAL TEMUAN"]) if "TANGGAL TEMUAN" in row and pd.notna(row["TANGGAL TEMUAN"]) else None,
            "tanggal_perbaikan": str(row["TANGGAL PERBAIKAN"]) if "TANGGAL PERBAIKAN" in row and pd.notna(row["TANGGAL PERBAIKAN"]) else None,
            "link_dokumentasi": clean_val(row.get("LINK DOKUMENTASI PERBAIKAN")),
            "metode_perbaikan": clean_val(row.get("METODE PERBAIKAN")),
            "panjang_realisasi": clean_val(row.get("Panjang_Realisasi")),
            "lebar_realisasi": clean_val(row.get("Lebar_Realisasi")),
            "tebal_realisasi": clean_val(row.get("Tebal_Realisasi")),
        }
        batch.append(payload)
        
        if len(batch) >= 500:
            try:
                resp = requests.post(WEBHOOK_URL, json={"bulk_data": batch}, headers={'Accept': 'application/json'})
                if resp.status_code == 200:
                    total_imported += len(batch)
                    print(f"[SUCCESS] Bulk Injected {len(batch)} records! Total: {total_imported}")
                else:
                    print(f"[FAILED] Error: {resp.status_code} - {resp.text}")
            except Exception as e:
                print(f"[CONNECTION ERROR] Ensure Laravel is running! Error: {e}")
            batch = [] # Reset batch

    # Send remaining rows in the last batch
    if len(batch) > 0:
        try:
            resp = requests.post(WEBHOOK_URL, json={"bulk_data": batch}, headers={'Accept': 'application/json'})
            if resp.status_code == 200:
                total_imported += len(batch)
                print(f"[SUCCESS] Bulk Injected final {len(batch)} records for sheet {sheet}!")
            else:
                print(f"[FAILED] Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"[CONNECTION ERROR] Ensure Laravel is running! Error: {e}")

print(f"\n[DONE] SUPERFAST IMPORT COMPLETE! Successfully injected {total_imported} historical records into IRIS!")
