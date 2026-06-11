from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
from config import settings

def upload_photo_to_gdrive(file_bytes: bytes, filename: str) -> str:
    """
    Uploads a photo to Google Drive and returns the shareable link.
    """
    if not settings.GOOGLE_APPLICATION_CREDENTIALS or not settings.GOOGLE_DRIVE_FOLDER_ID:
        raise Exception("Google Drive credentials or Folder ID missing in .env")
        
    # Authenticate with the JSON key we downloaded earlier
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_APPLICATION_CREDENTIALS,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    service = build('drive', 'v3', credentials=creds)
    
    file_metadata = {
        'name': filename,
        'parents': [settings.GOOGLE_DRIVE_FOLDER_ID]
    }
    
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='image/jpeg', resumable=True)
    
    # Execute the upload
    file = service.files().create(
        body=file_metadata, 
        media_body=media, 
        fields='id, webViewLink'
    ).execute()
    
    # Make the photo viewable by anyone with the link (so analysts can see it when they click the Excel link)
    service.permissions().create(
        fileId=file.get('id'),
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    return file.get('webViewLink')
