from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    META_VERIFY_TOKEN: str = "vista_secure_token_123"
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    SPREADSHEET_ID: str = ""
    
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    
    EXCEL_SHARE_LINK: str = ""
    GOOGLE_DRIVE_FOLDER_ID: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
