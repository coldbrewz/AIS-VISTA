from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    VIKEY_API_KEY: Optional[str] = None
    VIKEY_BASE_URL: str = "https://api.vikey.ai/v1/chat/completions"
    VIKEY_MODEL: str = "deepseek/deepseek-v4.1-flash"
    VIKEY_OCR_MODEL: str = ""
    
    WAHA_API_KEY: str = ""
    WAHA_URL: str = "http://localhost:3000"
    
    ADMIN_PHONE: str = ""
    DB_URL: str = "processed_messages.db"
    
    ALERT_EMAIL: str = "aistamer@outlook.com"
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_SENDER: str = ""
    SMTP_PASSWORD: str = ""
    
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    
    EXCEL_SHARE_LINK: str = ""
    OPNAME_EXCEL_SHARE_LINK: str = ""
    TAGIHAN_TEMPLATE_SHARE_LINK: str = ""
    OPNAME_ENABLED: bool = True
    OPNAME_AUTO_MONTHLY: bool = True
    OPNAME_CYCLE_YEAR: int = 2026

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def model_post_init(self, __context):
        # Auto-prepend http:// if scheme is missing (prevents MissingSchema error in requests)
        url = self.WAHA_URL.strip() if self.WAHA_URL else ""
        if url and not url.startswith(("http://", "https://")):
            self.WAHA_URL = f"http://{url}"

        vikey_url = self.VIKEY_BASE_URL.strip() if self.VIKEY_BASE_URL else ""
        if vikey_url:
            if not vikey_url.startswith(("http://", "https://")):
                vikey_url = f"https://{vikey_url}"
            if not vikey_url.endswith("/chat/completions"):
                vikey_url = vikey_url.rstrip("/") + "/chat/completions"
            self.VIKEY_BASE_URL = vikey_url

settings = Settings()
